# XBalanseBot/app/handlers/user_commands.py
# FULL FILE EMITTED: YES
# v1.7.3
# 2025-08-29 04:15:00
"""
Модуль с обработчиками команд, доступных обычным пользователям.

Версия 1.7.3:
- Полностью переведена логика обработки callback_data на использование фабрик
  из `app.callbacks`, что повышает надежность и читаемость кода.
- Удалены устаревшие методы парсинга callback_data на основе строк.

Версия 1.7.2:
- ИСПРАВЛЕНИЕ: `process_menu_activity` теперь корректно вызывает новую
  универсальную функцию `show_activities_list`.
"""
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from psycopg.rows import dict_row

from app.config import CURRENCY_SYMBOL, MAIN_GROUP_ID
from app.database import db
from app.lexicon import LEXICON_RU
from app.handlers import activity_handlers, common as common_handlers, event_handlers
from app.keyboards import (get_back_to_menu_keyboard, get_main_menu_keyboard,
                           get_transfer_confirmation_keyboard, get_cancel_dialog_keyboard)
from app.states import TransferStates
from app.utils import (ensure_user_exists, format_amount,
                       format_transactions_history, get_transaction_count,
                       get_user_balance, is_admin, validate_amount,
                       add_message_id_to_state, check_is_group_member, get_next_run_time)
from app.callbacks import GeneralAction, TransferAction, HelpAction

router = Router()
_bottom_kb_role_cache: dict[int, str] = {}


async def ensure_role_bottom_keyboard(bot: Bot, user_id: int, user_is_admin: bool | None = None, force: bool = False):
    """
    Гарантирует правильный режим интерфейса в ЛС:
    - Для обычного пользователя: закрепляет единственную нижнюю кнопку «🏠 Главное меню» (1 клик)
      и очищает персональный список команд (если он был закэширован).
    - Для администратора: удаляет нижние кнопки (ReplyKeyboardRemove), оставляя только команды /.
    """
    try:
        if user_is_admin is None:
            user_is_admin = await is_admin(user_id)
        target_role = "admin" if user_is_admin else "user"
        if not force and _bottom_kb_role_cache.get(user_id) == target_role:
            return
        _bottom_kb_role_cache[user_id] = target_role
        if user_is_admin:
            from aiogram.types import ReplyKeyboardRemove
            await bot.send_message(
                user_id,
                "⌨️ <i>Нижняя панель кнопок убрана (для администратора активно меню команд).</i>",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="HTML",
                disable_notification=True,
            )
        else:
            from aiogram.types import BotCommandScopeChat
            from app.keyboards import get_persistent_bottom_keyboard
            try:
                await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))
            except Exception:
                pass
            await bot.send_message(
                user_id,
                "⌨️ <i>Быстрая кнопка меню закреплена внизу экрана.</i>",
                reply_markup=get_persistent_bottom_keyboard(),
                parse_mode="HTML",
                disable_notification=True,
            )
    except Exception as e:
        logger.debug(f"Could not sync bottom keyboard for {user_id}: {e}")
logger = logging.getLogger(__name__)


# --- Вспомогательные функции ---

async def cleanup_transfer_dialog(state: FSMContext, bot: Bot, chat_id: int):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    if message_ids:
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=message_ids)
        except Exception as e:
            logger.warning(f"Could not delete messages in transfer dialog cleanup: {e}")
    await state.clear()

async def _get_history_text(telegram_id: int, days: int = 30) -> str:
    current_balance = await get_user_balance(telegram_id)
    date_limit = datetime.now(ZoneInfo("Europe/Moscow")) - timedelta(days=days)
    user_db_id, all_txs = await db.get_transaction_history(telegram_id, date_limit)

    if user_db_id is None:
        return LEXICON_RU["msg_user_not_found_profile"]

    if not all_txs:
        return LEXICON_RU["msg_no_transactions"].format(days=days)

    response_parts = [LEXICON_RU["msg_history_header"].format(days=days)]
    history_text = format_transactions_history(all_txs, user_db_id)
    response_parts.append(history_text)
    response_parts.append(LEXICON_RU["msg_current_balance"].format(balance=format_amount(current_balance), currency_symbol=CURRENCY_SYMBOL))
    return "".join(response_parts)


# --- Обработчик /cancel специально для состояний TransferStates ---
@router.message(Command("cancel"), StateFilter(TransferStates))
async def cancel_transfer_dialog(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    message_ids = add_message_id_to_state(data, message.message_id)
    await state.update_data(message_ids=message_ids)

    await cleanup_transfer_dialog(state, bot, message.chat.id)
    await show_main_menu(message)


# --- БЛОК ГЛАВНОГО МЕНЮ ---

async def show_main_menu(message: Message | CallbackQuery):
    from app.config import SUPER_ADMIN_ID
    user_id = message.from_user.id
    bot = message.bot
    is_member = await check_is_group_member(bot, user_id)

    user = await db.get_user(telegram_id=user_id)
    if not user and user_id != SUPER_ADMIN_ID:
        if not is_member:
            await common_handlers.send_onboarding_prompt(message)
            return
        await ensure_user_exists(user_id, message.from_user.username, message.from_user.is_bot)

    balance = await get_user_balance(user_id)
    from_user = message.from_user
    name = from_user.full_name or from_user.first_name or "Участник"
    username_part = f" (@{from_user.username})" if from_user.username else ""

    # Собираем данные дашборда: обязательства и активные лоты
    commitments_str = ""
    try:
        commitments = await db.get_user_commitments(user_id)
        deals_blocks = []
        if commitments.get("owed_by_me"):
            items = []
            for o in commitments["owed_by_me"]:
                buyer = f"@{o['buyer_username']}" if o.get("buyer_username") else "покупателю"
                items.append(LEXICON_RU["msg_dashboard_owed_by_me_item"].format(title=escape(o["title"]), buyer=buyer))
            nl = chr(10)
            deals_blocks.append(LEXICON_RU["msg_dashboard_owed_by_me_header"] + nl + nl.join(items))

        if commitments.get("owed_to_me"):
            items = []
            for o in commitments["owed_to_me"]:
                seller = f"@{o['seller_username']}" if o.get("seller_username") else "продавца"
                items.append(LEXICON_RU["msg_dashboard_owed_to_me_item"].format(title=escape(o["title"]), seller=seller))
            nl = chr(10)
            deals_blocks.append(LEXICON_RU["msg_dashboard_owed_to_me_header"] + nl + nl.join(items))

        if commitments.get("active_selling_count", 0) > 0:
            deals_blocks.append(LEXICON_RU["msg_dashboard_active_offers"].format(count=commitments["active_selling_count"]))

        if deals_blocks:
            nl2 = chr(10) + chr(10)
            commitments_str = nl2 + nl2.join(deals_blocks)
    except Exception as e:
        logger.debug(f"Could not load commitments for dashboard: {e}")

    # Ближайшее событие для пользователя (если есть в ближайшие 7 дней)
    upcoming_event_str = ""
    try:
        user_subs = await db.get_user_subscriptions(user_id)
        sub_activity_ids = {s["activity_id"] for s in user_subs}
        all_events = await db.get_all_events()
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        week_ahead = now + timedelta(days=7)
        dated = []
        for ev in all_events:
            if not sub_activity_ids or ev["activity_id"] in sub_activity_ids:
                next_run = get_next_run_time(
                    ev["event_type"], ev.get("event_date"), ev.get("weekday"),
                    ev.get("event_time"), ev.get("last_run"), ev.get("end_date")
                )
                if next_run and now <= next_run <= week_ahead:
                    dated.append((next_run, ev))
        if dated:
            dated.sort(key=lambda x: x[0])
            next_time, next_ev = dated[0]
            upcoming_event_str = LEXICON_RU["msg_dashboard_upcoming_event"].format(
                event_name=escape(next_ev["name"]),
                event_time=next_time.strftime("%d.%m %H:%M")
            )
    except Exception as e:
        logger.debug(f"Could not load upcoming events for dashboard: {e}")

    text = LEXICON_RU["msg_main_menu"].format(
        name=escape(name),
        username_part=username_part,
        balance=format_amount(balance),
        currency_symbol=CURRENCY_SYMBOL,
        upcoming_event_str=upcoming_event_str,
        commitments_str=commitments_str
    )

    # Инвайт-ссылка для кнопки перехода в группу (если ещё не в группе)
    invite_link = None
    if not is_member:
        try:
            expire_date = int(time.time()) + 86400
            invite_obj = await bot.create_chat_invite_link(
                chat_id=MAIN_GROUP_ID,
                member_limit=1,
                expire_date=expire_date,
                name=f"Invite for {from_user.full_name}"
            )
            invite_link = invite_obj.invite_link
        except Exception as e:
            logger.warning(f"Failed to create invite link for main menu: {e}")

    keyboard = get_main_menu_keyboard(is_member=is_member, invite_link=invite_link)

    # Для обычного пользователя закрепляем 1 нижнюю кнопку, а у админа убираем нижние кнопки
    await ensure_role_bottom_keyboard(bot, user_id)

    if isinstance(message, Message):
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    elif isinstance(message, CallbackQuery):
        try:
            await message.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await message.bot.send_message(message.from_user.id, text, reply_markup=keyboard, parse_mode="HTML")
        await message.answer()

@router.message(Command("menu", ignore_case=True), StateFilter("*"))
async def cmd_menu(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    await show_main_menu(message)


@router.message(F.chat.type == "private", F.text == "🏠 Главное меню", StateFilter("*"))
async def handle_bottom_btn_main_menu(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    if await is_admin(message.from_user.id):
        await ensure_role_bottom_keyboard(message.bot, message.from_user.id, user_is_admin=True, force=True)
    await show_main_menu(message)


@router.message(F.chat.type == "private", F.text == "⚙️ Настройки", StateFilter("*"))
async def handle_bottom_btn_settings(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    await ensure_role_bottom_keyboard(message.bot, message.from_user.id, user_is_admin=True, force=True)
    from app.handlers.admin_commands import cmd_settings
    await cmd_settings(message)


@router.message(F.chat.type == "private", F.text == "🩺 Статус", StateFilter("*"))
async def handle_bottom_btn_status(message: Message, state: FSMContext = None, scheduler=None):
    if state is not None:
        await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    await ensure_role_bottom_keyboard(message.bot, message.from_user.id, user_is_admin=True, force=True)
    from app.handlers.admin_commands import cmd_status
    await cmd_status(message, bot=message.bot, scheduler=scheduler)


@router.message(F.chat.type == "private", F.text == "🔐 Гид админа", StateFilter("*"))
async def handle_bottom_btn_gide(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    try:
        await message.delete()
    except Exception:
        pass
    await ensure_role_bottom_keyboard(message.bot, message.from_user.id, user_is_admin=True, force=True)
    from app.handlers.admin_commands import cmd_gide
    await cmd_gide(message)

@router.callback_query(GeneralAction.filter(F.action == "main_menu"), StateFilter("*"))
async def process_back_to_menu(callback: CallbackQuery, state: FSMContext = None):
    if state is not None:
        await state.clear()
    await show_main_menu(callback)

@router.callback_query(GeneralAction.filter(F.action == "menu_balance_history"))
async def process_menu_balance_history(callback: CallbackQuery):
    """Показывает баланс и историю транзакций в одном сообщении."""
    await callback.answer()
    user = callback.from_user
    await ensure_user_exists(user.id, user.username, user.is_bot)
    balance = await get_user_balance(user.id)

    history_text = await _get_history_text(user.id, days=30)

    text = LEXICON_RU["msg_balance_and_history"].format(balance=format_amount(balance), currency_symbol=CURRENCY_SYMBOL, history_text=history_text)

    try:
        await callback.message.edit_text(
            text,
            reply_markup=get_back_to_menu_keyboard(),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.delete()
        await callback.message.answer(
            text,
            reply_markup=get_back_to_menu_keyboard(),
            parse_mode="HTML"
        )

@router.callback_query(GeneralAction.filter(F.action == "menu_activity"))
async def process_menu_activity(callback: CallbackQuery):
    """Обрабатывает кнопку 'Активности', вызывая новую универсальную функцию."""
    await activity_handlers.show_activities_list(callback)

@router.callback_query(GeneralAction.filter(F.action == "menu_event"))
async def process_menu_event(callback: CallbackQuery):
    await callback.answer()
    await event_handlers.cmd_event(callback)

@router.callback_query(GeneralAction.filter(F.action == "menu_help"))
async def process_menu_help(callback: CallbackQuery):
    """Показывает модульную справку с учётом роли пользователя."""
    await callback.answer()
    from app.lexicon import LEXICON_RU
    from app.keyboards import get_user_help_keyboard
    user_is_admin = await is_admin(callback.from_user.id)
    help_text = LEXICON_RU.get("help_user_main", LEXICON_RU["help_user"]).format(currency_symbol=CURRENCY_SYMBOL)
    await callback.message.edit_text(
        help_text,
        reply_markup=get_user_help_keyboard("help_user_main", is_admin=user_is_admin),
        parse_mode="HTML"
    )


@router.callback_query(HelpAction.filter())
async def process_help_section(callback: CallbackQuery, callback_data: HelpAction):
    """Переключает разделы модульной справки (/help и /gide)."""
    from app.lexicon import LEXICON_RU
    from app.keyboards import get_user_help_keyboard, get_admin_help_keyboard
    section_key = callback_data.section
    user_is_admin = await is_admin(callback.from_user.id)
    if section_key.startswith("help_admin_") and not user_is_admin:
        await callback.answer("❌ Доступно только администраторам.", show_alert=True)
        return
    raw_text = LEXICON_RU.get(section_key, LEXICON_RU.get("help_user_main", ""))
    formatted = raw_text.format(currency_symbol=CURRENCY_SYMBOL)
    if section_key.startswith("help_admin_"):
        kb = get_admin_help_keyboard(section_key)
    else:
        kb = get_user_help_keyboard(section_key, is_admin=user_is_admin)
    try:
        await callback.message.edit_text(formatted, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()

@router.callback_query(GeneralAction.filter(F.action == "menu_send"))
async def process_menu_send(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(TransferStates.waiting_for_recipient)
    from app.keyboards import get_back_to_menu_keyboard
    sent_message = await callback.message.edit_text(
        LEXICON_RU["msg_transfer_ask_recipient"],
        reply_markup=get_back_to_menu_keyboard()
    )
    await state.update_data(message_ids=[sent_message.message_id])


# --- СУЩЕСТВУЮЩИЕ КОМАНДЫ (продолжают работать автономно) ---

@router.message(Command("balance", "баланс", ignore_case=True), StateFilter("*"))
async def cmd_balance(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
    balance = await get_user_balance(message.from_user.id)
    history_text = await _get_history_text(message.from_user.id, days=30)

    text = LEXICON_RU["msg_balance_and_history"].format(balance=format_amount(balance), currency_symbol=CURRENCY_SYMBOL, history_text=history_text)
    kb = None if getattr(message.chat, 'type', 'private') in ('group', 'supergroup') else get_back_to_menu_keyboard()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(Command("send", ignore_case=True))
async def cmd_send(message: Message, state: FSMContext, bot: Bot):
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
    args = message.text.split()

    if len(args) >= 3:
        recipient_username = args[1].lstrip('@').lower()
        if recipient_username == (message.from_user.username or '').lower():
            await message.reply(LEXICON_RU["err_transfer_self"])
            return
        try:
            amount = validate_amount(args[2])
        except ValueError:
            await message.reply(LEXICON_RU["err_transfer_invalid_amount"])
            return
        recipient = await db.get_user(username=recipient_username)
        if not recipient:
            await message.reply(LEXICON_RU["err_user_not_found"].format(recipient_username=recipient_username))
            return
        comment = ' '.join(args[3:]) if len(args) > 3 else "Перевод"
        await perform_transfer_and_notify(message, state, bot, recipient, amount, comment, is_dialog=False)
        return

    if len(args) == 1:
        await state.set_state(TransferStates.waiting_for_recipient)
        sent_message = await message.answer(
            LEXICON_RU["msg_transfer_ask_recipient"],
            reply_markup=get_cancel_dialog_keyboard()
        )
        await state.update_data(message_ids=[message.message_id, sent_message.message_id])
        return

    await message.reply(LEXICON_RU["err_transfer_format"], parse_mode="HTML")

@router.message(TransferStates.waiting_for_recipient)
async def process_recipient_input(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    message_ids = add_message_id_to_state(data, message.message_id)

    msg_text = (message.text or "").strip()
    if msg_text.lower() == "cancel" or msg_text.startswith("/"):
        await state.update_data(message_ids=message_ids)
        from app.handlers.user_commands import cancel_transfer_dialog
        await cancel_transfer_dialog(message, state, bot)
        return

    recipient_username = message.text.lstrip('@').lower()
    if recipient_username == (message.from_user.username or '').lower():
        sent_message = await message.reply(LEXICON_RU["err_transfer_self_dialog"], reply_markup=get_cancel_dialog_keyboard())
        message_ids = add_message_id_to_state({'message_ids': message_ids}, sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return

    recipient = await db.get_user(username=recipient_username)
    if not recipient:
        sent_message = await message.reply(LEXICON_RU["err_user_not_found_dialog"].format(recipient_username=recipient_username), reply_markup=get_cancel_dialog_keyboard())
        message_ids = add_message_id_to_state({'message_ids': message_ids}, sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return

    await state.update_data(recipient_id=recipient['id'], recipient_telegram_id=recipient['telegram_id'], recipient_username=recipient_username)
    await state.set_state(TransferStates.waiting_for_amount)
    sent_message = await message.answer(
        LEXICON_RU["msg_transfer_ask_amount"].format(currency_symbol=CURRENCY_SYMBOL, recipient_username=recipient_username),
        reply_markup=get_cancel_dialog_keyboard()
    )
    message_ids = add_message_id_to_state({'message_ids': message_ids}, sent_message.message_id)
    await state.update_data(message_ids=message_ids)

@router.message(TransferStates.waiting_for_amount)
async def process_amount_input(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = add_message_id_to_state(data, message.message_id)

    msg_text = (message.text or "").strip()
    if msg_text.lower() == "cancel" or msg_text.startswith("/"):
        await state.update_data(message_ids=message_ids)
        from app.handlers.user_commands import cancel_transfer_dialog
        await cancel_transfer_dialog(message, state, message.bot)
        return

    try:
        amount = validate_amount(message.text)
    except ValueError:
        sent_message = await message.reply(
            LEXICON_RU["err_transfer_invalid_amount_dialog"],
            reply_markup=get_cancel_dialog_keyboard()
        )
        message_ids = add_message_id_to_state({'message_ids': message_ids}, sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return

    from app.config import SUPER_ADMIN_ID
    sender_balance = await get_user_balance(message.from_user.id)
    if message.from_user.id != SUPER_ADMIN_ID and sender_balance < amount:
        sent_message = await message.reply(
            LEXICON_RU["err_insufficient_funds"].format(balance=format_amount(sender_balance), currency_symbol=CURRENCY_SYMBOL),
            reply_markup=get_cancel_dialog_keyboard(),
            parse_mode="HTML"
        )
        message_ids = add_message_id_to_state({'message_ids': message_ids}, sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return

    await state.update_data(amount=str(amount))
    await state.set_state(TransferStates.waiting_for_comment)
    sent_message = await message.answer(
        LEXICON_RU["msg_transfer_ask_comment"],
        reply_markup=get_cancel_dialog_keyboard()
    )
    message_ids = add_message_id_to_state({'message_ids': message_ids}, sent_message.message_id)
    await state.update_data(message_ids=message_ids)

@router.message(TransferStates.waiting_for_comment)
async def process_comment_input(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = add_message_id_to_state(data, message.message_id)

    msg_text = (message.text or "").strip()
    if msg_text.lower() == "cancel" or msg_text.startswith("/"):
        await state.update_data(message_ids=message_ids)
        from app.handlers.user_commands import cancel_transfer_dialog
        await cancel_transfer_dialog(message, state, message.bot)
        return

    await state.update_data(comment=message.text)

    dialog_data = await state.get_data()
    amount = Decimal(dialog_data['amount'])
    recipient_username = dialog_data['recipient_username']

    from html import escape
    confirmation_text = LEXICON_RU["msg_transfer_confirm"].format(
        recipient_username=recipient_username, amount=format_amount(amount),
        currency_symbol=CURRENCY_SYMBOL, comment=escape(message.text or "")
    )

    await state.set_state(TransferStates.waiting_for_confirmation)
    sent_message = await message.answer(confirmation_text, reply_markup=get_transfer_confirmation_keyboard(), parse_mode="HTML")
    message_ids = add_message_id_to_state({'message_ids': message_ids}, sent_message.message_id)
    await state.update_data(message_ids=message_ids)

@router.callback_query(TransferStates.waiting_for_confirmation, TransferAction.filter(F.action == "confirm"))
async def process_transfer_confirmation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    recipient = {
        'id': data['recipient_id'],
        'telegram_id': data['recipient_telegram_id'],
        'username': data['recipient_username']
    }
    amount = Decimal(data['amount'])
    comment = data['comment']

    await perform_transfer_and_notify(callback, state, bot, recipient, amount, comment, is_dialog=True)
    await callback.answer()

@router.callback_query(TransferStates.waiting_for_confirmation, TransferAction.filter(F.action == "cancel"))
async def process_transfer_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await cleanup_transfer_dialog(state, bot, callback.message.chat.id)
    await callback.message.answer(LEXICON_RU["msg_action_cancelled_plain"])
    await callback.answer()


async def perform_transfer_and_notify(message: Message | CallbackQuery, state: FSMContext, bot: Bot, recipient: dict, amount: Decimal, comment: str, is_dialog: bool):
    sender = message.from_user
    chat_id = message.chat.id if isinstance(message, Message) else message.message.chat.id

    if is_dialog:
        await cleanup_transfer_dialog(state, bot, chat_id)

    try:
        result = await db.transfer(sender.id, recipient['id'], amount, comment)

        if not result['success']:
            if result['error'] == 'sender_not_found':
                await bot.send_message(chat_id, LEXICON_RU["err_sender_not_found"])
            elif result['error'] == 'insufficient_funds':
                await bot.send_message(chat_id, LEXICON_RU["err_insufficient_funds_plain"].format(balance=format_amount(result['sender_balance']), currency_symbol=CURRENCY_SYMBOL), parse_mode="HTML")
            return

        logger.info(f"Transfer successful: {sender.id} -> {recipient['telegram_id']}, amount: {amount}")
        await db.handle_debt_repayment(recipient['id'])

        response_text = LEXICON_RU["msg_transfer_success"].format(
            recipient_username=recipient['username'],
            amount=format_amount(amount),
            currency_symbol=CURRENCY_SYMBOL,
            comment=escape(comment or "")
        )

        recipient_notified = True
        if recipient['telegram_id'] != 0:
            try:
                sender_username = escape(sender.username or f"user{sender.id}")
                await bot.send_message(
                    recipient['telegram_id'],
                    LEXICON_RU["msg_transfer_received"].format(
                        sender_username=sender_username,
                        amount=format_amount(amount),
                        currency_symbol=CURRENCY_SYMBOL,
                        comment=escape(comment or "")
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not send notification to recipient {recipient['telegram_id']}: {e}")
                recipient_notified = False

        if not recipient_notified:
            response_text += LEXICON_RU["warning_recipient_not_notified"].format(recipient_username=recipient['username'])

        await bot.send_message(chat_id, response_text, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Transaction failed between users {sender.id} -> {recipient['telegram_id']}: {e}", exc_info=True)
        await bot.send_message(chat_id, LEXICON_RU["err_transfer_failed"])

@router.message(Command("history", ignore_case=True), StateFilter("*"))
async def cmd_history(message: Message, state: FSMContext = None):
    if state is not None:
        await state.clear()
    user = message.from_user
    await ensure_user_exists(user.id, user.username, user.is_bot)
    args = message.text.split()
    try:
        days = int(args[1]) if len(args) > 1 else 30
    except (ValueError, IndexError):
        days = 30

    history_text = await _get_history_text(user.id, days=days)
    kb = None if getattr(message.chat, 'type', 'private') in ('group', 'supergroup') else get_back_to_menu_keyboard()
    await message.answer(history_text, reply_markup=kb, parse_mode="HTML")



@router.message(Command("gdp", "ввп", ignore_case=True), StateFilter("*"))
async def cmd_gdp(message: Message, state: FSMContext = None):
    if state is not None and getattr(message.chat, 'type', 'private') == 'private':
        await state.clear()
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    stats = await db.get_gdp_stats(now)
    total_mass = stats.get('total_mass', Decimal('0'))
    if total_mass == 0:
        sigma_label = "Σ = 0"
    else:
        sigma_label = f"Σ = {format_amount(total_mass)} {CURRENCY_SYMBOL} ⚠️ дисбаланс"

    response = LEXICON_RU["msg_gdp_stats"].format(
        currency_symbol=CURRENCY_SYMBOL,
        turnover_7d=format_amount(stats['turnover_7d']['turnover']),
        tx_count_7d=stats['turnover_7d']['tx_count'],
        turnover_30d=format_amount(stats['turnover_30d']['turnover']),
        tx_count_30d=stats['turnover_30d']['tx_count'],
        turnover_all=format_amount(stats['turnover_all']['turnover']),
        tx_count_all=stats['turnover_all']['tx_count'],
        total_supply=format_amount(stats['total_supply']),
        fund_balance=format_amount(stats['fund_balance']),
        treasury_balance=format_amount(stats.get('treasury_balance', Decimal('0'))),
        sigma_label=sigma_label
    )
    kb = None if getattr(message.chat, 'type', 'private') in ('group', 'supergroup') else get_back_to_menu_keyboard()
    await message.answer(response, reply_markup=kb, parse_mode="HTML")
