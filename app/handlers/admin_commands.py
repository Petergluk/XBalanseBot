# XBalanseBot/app/handlers/admin_commands.py
# FULL FILE EMITTED: YES
# v2.2.0
# 2025-08-29 04:15:00
"""
Модуль с обработчиками команд, доступных только администраторам.

Версия 2.2.0:
- Полностью переведена логика обработки callback_data на использование фабрик
  из `app.callbacks`, что повышает надежность и читаемость кода.
- Удалены устаревшие методы парсинга callback_data на основе строк.

Версия 2.1.0:
- Восстановлены обработчики команд /users, /make_admin, /remove_admin,
  /gide, /test. Теперь весь административный функционал снова доступен.
"""
import logging
from decimal import Decimal, InvalidOperation
from html import escape
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, User
from psycopg.rows import dict_row

from app.config import CURRENCY_SYMBOL
from app.lexicon import LEXICON_RU
from app.database import db
from app.handlers import activity_handlers as act_handlers
from app.handlers import event_handlers as event_handlers
from app.keyboards import (get_back_to_settings_keyboard, get_settings_keyboard)
from app.states import AdminEditStates, TagRuleCreationStates
from app.utils import (format_amount, format_transactions_history, is_admin)
from app.callbacks import (
    GeneralAction, ActivityAction, EventCreationAction, SettingsAction
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

router = Router()
logger = logging.getLogger(__name__)


# --- MIDDLEWARES ---

@router.message.middleware()
async def admin_message_middleware(handler, event: Message, data):
    if not await is_admin(data['event_from_user'].id):
        await event.reply(LEXICON_RU["err_no_admin_rights"])
        return
    return await handler(event, data)


@router.callback_query.middleware()
async def admin_callback_middleware(handler, event: CallbackQuery, data):
    if not await is_admin(data['event_from_user'].id):
        await event.answer(LEXICON_RU["err_no_admin_rights_alert"], show_alert=True)
        return
    return await handler(event, data)


# --- HELPERS ---

async def _parse_user_amount_comment(message: Message) -> tuple | None:
    args = message.text.split()
    if len(args) < 3:
        await message.reply(LEXICON_RU["err_admin_format"].format(command=args[0]))
        return None
    username = args[1].lstrip('@').lower()
    try:
        amount = Decimal(args[2].replace(',', '.'))
        if amount <= 0: raise ValueError
    except (InvalidOperation, ValueError):
        await message.reply(LEXICON_RU["err_admin_invalid_amount"])
        return None
    comment = ' '.join(args[3:]) if len(args) > 3 else "Административная операция"
    user = await db.get_user(username=username)
    if not user:
        await message.reply(LEXICON_RU["err_admin_user_not_found"].format(username=username))
        return None
    return user, amount, comment


async def _change_balance(
    bot: Bot, admin_user: User, target_user: dict, amount: Decimal,
    comment: str, transaction_type: str
):
    try:
        await db.change_balance(target_user['id'], amount, transaction_type, comment)
        action_word = "Начислено" if amount > 0 else "Списано"
        preposition = "на" if amount > 0 else "с"
        logger.info(f"Admin {admin_user.id} performed '{transaction_type}' for user {target_user['telegram_id']} ({target_user['username']}). Amount: {amount}, Comment: {comment}")
        await bot.send_message(admin_user.id, LEXICON_RU["msg_admin_balance_changed"].format(action_word=action_word, amount=format_amount(abs(amount)), currency_symbol=CURRENCY_SYMBOL, preposition=preposition, username=target_user['username']))
        try:
            await bot.send_message(
                target_user['telegram_id'],
                LEXICON_RU["msg_admin_notified_user"].format(
                    admin_username=escape(admin_user.username or f"user{admin_user.id}"),
                    action_word=action_word,
                    amount=format_amount(abs(amount)),
                    currency_symbol=CURRENCY_SYMBOL,
                    comment=escape(comment or "")
                )
            )
        except Exception as e:
            logger.warning(f"Could not send notification to user {target_user['telegram_id']}: {e}")
    except Exception as e:
        logger.error(f"Failed to change balance for user {target_user['telegram_id']}: {e}", exc_info=True)
        await bot.send_message(admin_user.id, LEXICON_RU["err_admin_operation_failed"])


# --- INFO & USER MANAGEMENT COMMANDS ---

@router.message(Command("gide", "гид", ignore_case=True))
async def cmd_gide(message: Message):
    gide_text = LEXICON_RU["gide_text"].format(currency_symbol=CURRENCY_SYMBOL)
    await message.answer(gide_text, parse_mode="HTML")

@router.message(Command("test", ignore_case=True))
async def cmd_test(message: Message):
    await message.answer(LEXICON_RU["test_commands"], parse_mode="HTML")

@router.message(Command("users", ignore_case=True))
async def cmd_users(message: Message):
    users = await db.get_all_users()
    if not users:
        await message.answer(LEXICON_RU["msg_admin_no_users"])
        return
    page_size = 20
    total_users = len(users)
    response_parts = [LEXICON_RU["msg_admin_users_header"].format(total_users=total_users)]
    for i, user in enumerate(users[:page_size]):
        admin_mark = "👮" if user['is_admin'] else ""
        username_str = f"@{user['username']}" if user['username'] else f"ID:{user['telegram_id']}"
        response_parts.append(LEXICON_RU["msg_admin_user_row"].format(index=i+1, admin_mark=admin_mark, username=username_str, balance=format_amount(user['balance']), currency_symbol=CURRENCY_SYMBOL))
    if total_users > page_size:
        response_parts.append(LEXICON_RU["msg_admin_users_footer"].format(page_size=page_size, total_users=total_users))
    await message.answer("".join(response_parts), parse_mode="HTML")


@router.message(Command("check", ignore_case=True))
async def cmd_check(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply(LEXICON_RU["err_admin_specify_username"])
        return
    username = args[1].lstrip('@').lower()
    user = await db.get_user(username=username)
    if not user:
        await message.reply(LEXICON_RU["err_admin_user_not_found"].format(username=username))
        return
    async with db.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT t.*, sender.username as sender_username, recipient.username as recipient_username FROM transactions t LEFT JOIN users sender ON t.from_user_id = sender.id LEFT JOIN users recipient ON t.to_user_id = recipient.id WHERE (t.to_user_id = %s OR t.from_user_id = %s) ORDER BY t.created_at DESC LIMIT 10", (user['id'], user['id']))
            transactions = await cur.fetchall()
    history_text = LEXICON_RU["msg_admin_no_transactions"]
    if transactions:
        history_text = format_transactions_history(transactions, user['id'])
    response = LEXICON_RU["msg_admin_check_user"].format(
        username=user['username'],
        telegram_id=user['telegram_id'],
        balance=format_amount(user['balance']),
        currency_symbol=CURRENCY_SYMBOL,
        is_admin='Да' if user['is_admin'] else 'Нет',
        transaction_count=user['transaction_count'],
        history_text=history_text
    )
    await message.answer(response)

@router.message(Command("add", ignore_case=True))
async def cmd_add(message: Message, bot: Bot):
    parsed = await _parse_user_amount_comment(message)
    if not parsed: return
    user, amount, comment = parsed
    await _change_balance(bot, message.from_user, user, amount, comment, 'manual_add')

@router.message(Command("rem", ignore_case=True))
async def cmd_rem(message: Message, bot: Bot):
    parsed = await _parse_user_amount_comment(message)
    if not parsed: return
    user, amount, comment = parsed
    await _change_balance(bot, message.from_user, user, -amount, comment, 'manual_rem')

async def _toggle_admin(message: Message, make_admin: bool):
    args = message.text.split()
    if len(args) < 2:
        await message.reply(LEXICON_RU["err_admin_format_username"].format(command=args[0]))
        return
    username = args[1].lstrip('@').lower()
    user = await db.get_user(username=username)
    if not user:
        await message.reply(LEXICON_RU["err_admin_user_not_found"].format(username=username))
        return
    if user['is_admin'] == make_admin:
        status = "уже является" if make_admin else "не является"
        await message.reply(LEXICON_RU["msg_admin_status_already_set"].format(username=username, status=status))
        return
    await db.set_admin_status(user['telegram_id'], is_admin=make_admin)
    action = "назначен" if make_admin else "сняты права"
    await message.answer(LEXICON_RU["msg_admin_status_changed"].format(username=username, action=action))

@router.message(Command("make_admin", ignore_case=True))
async def cmd_make_admin(message: Message):
    await _toggle_admin(message, make_admin=True)

@router.message(Command("remove_admin", ignore_case=True))
async def cmd_remove_admin(message: Message):
    await _toggle_admin(message, make_admin=False)

# --- SETTINGS MANAGEMENT ---

@router.message(Command("settings", ignore_case=True))
async def cmd_settings(message: Message):
    keyboard = await get_settings_keyboard()
    await message.answer(LEXICON_RU["msg_admin_settings_menu"], reply_markup=keyboard)

@router.callback_query(SettingsAction.filter())
async def process_settings_callbacks(callback: CallbackQuery, state: FSMContext, callback_data: SettingsAction):
    action = callback_data.action
    
    from app.lexicon import LEXICON_RU
    
    prompts = {
        "set_welcome_bonus": (LEXICON_RU["msg_admin_prompt_set_welcome_bonus"], 'welcome_bonus_amount', '1500', AdminEditStates.waiting_for_welcome_bonus),
        "set_exchange_rate": (LEXICON_RU["msg_admin_prompt_set_exchange_rate"], 'exchange_rate', '1.0', AdminEditStates.waiting_for_exchange_rate),
        "set_demurrage_rate": (LEXICON_RU["msg_admin_prompt_set_demurrage_rate"], 'demurrage_rate', '1.0', AdminEditStates.waiting_for_demurrage_rate),
        "edit_welcome_bot": (LEXICON_RU["msg_admin_prompt_edit_welcome_bot"], 'welcome_message_bot', LEXICON_RU["default_welcome_bot"], AdminEditStates.waiting_for_welcome_text),
        "edit_welcome_group": (LEXICON_RU["msg_admin_prompt_edit_welcome_group"], 'welcome_message_group', LEXICON_RU["default_welcome_group"], AdminEditStates.waiting_for_welcome_text_group),
        "edit_reminder": (LEXICON_RU["msg_admin_prompt_edit_reminder"], 'default_reminder_text', LEXICON_RU["default_reminder"], AdminEditStates.waiting_for_reminder_text),
        "edit_activities_desc": (LEXICON_RU["msg_admin_prompt_edit_activities_desc"], 'activities_description', LEXICON_RU["msg_admin_default_activities_desc"], AdminEditStates.waiting_for_activities_description),
        "edit_bonus_message": (LEXICON_RU["msg_admin_prompt_edit_bonus_message"], 'welcome_bonus_message', LEXICON_RU["default_welcome_bonus"], AdminEditStates.waiting_for_welcome_bonus_text)
    }
    
    variable_tooltips = {
        "edit_welcome_bot": ["{username}"],
        "edit_welcome_group": ["{username}", "{bot_username}"],
        "edit_reminder": ["{event_name}", "{event_description}", "{start_date}", "{start_time}", "{cost}", "{currency_symbol}", "{link}", "{reminder_minutes}"],
        "edit_activities_desc": ["{username}"],
        "edit_bonus_message": ["{username}", "{amount}", "{currency_symbol}"]
    }
    
    if action in prompts:
        desc, db_key, default_val, new_state = prompts[action]
        current_val = str(await db.get_setting(db_key, default_val))
        
        if len(current_val) > 30 or '\n' in current_val:
            prompt_text = LEXICON_RU["msg_admin_prompt_current_long"].format(desc=desc, current_val=current_val)
        else:
            prompt_text = LEXICON_RU["msg_admin_prompt_current_short"].format(desc=desc, current_val=current_val)
        
        if action in variable_tooltips:
            tips = " ".join([f"{t}" for t in variable_tooltips[action]])
            prompt_text += LEXICON_RU["msg_admin_prompt_variables"].format(tips=tips)
        
        await state.set_state(new_state)
        
        # Специальная клавиатура для бонуса с кнопкой редактирования текста
        if action == "set_welcome_bonus":
            from app.keyboards import get_welcome_bonus_setting_keyboard
            kb = await get_welcome_bonus_setting_keyboard()
        elif action == "edit_welcome_group":
            from app.keyboards import get_welcome_group_prompt_keyboard
            enabled = (await db.get_setting('welcome_group_enabled', '0')) == '1'
            kb = get_welcome_group_prompt_keyboard(enabled)
        else:
            kb = get_back_to_settings_keyboard()
            
        await callback.message.edit_text(prompt_text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
    elif action == "menu_demurrage":
        enabled_val = await db.get_setting('demurrage_enabled', '0')
        enabled = enabled_val == '1'
        enabled_str = "Включен" if enabled else "Выключен"
        rate = float(await db.get_setting('demurrage_rate', '1.0'))
        interval = await db.get_setting('demurrage_interval_days')
        last_run = await db.get_setting('demurrage_last_run')
        status_text = LEXICON_RU["msg_admin_demurrage_status"].format(enabled=enabled_str, rate=rate, interval=interval, last_run=last_run)
        
        from app.keyboards import get_demurrage_settings_keyboard
        kb = await get_demurrage_settings_keyboard(enabled)
        await callback.message.edit_text(status_text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        
    elif action == "menu_tag_rules":
        await callback.message.delete()
        from app.handlers.admin_commands import cmd_list_tag_rules
        await cmd_list_tag_rules(callback.message)
        await callback.answer()

    elif action == "toggle_demurrage":
        is_on = callback_data.enabled
        await db.set_setting('demurrage_enabled', '1' if is_on else '0')
        
        enabled_str = "Включен" if is_on else "Выключен"
        rate = float(await db.get_setting('demurrage_rate', '1.0'))
        interval = await db.get_setting('demurrage_interval_days')
        last_run = await db.get_setting('demurrage_last_run')
        status_text = LEXICON_RU["msg_admin_demurrage_status"].format(enabled=enabled_str, rate=rate, interval=interval, last_run=last_run)
        
        from app.keyboards import get_demurrage_settings_keyboard
        new_keyboard = await get_demurrage_settings_keyboard(is_on)
        await callback.message.edit_text(status_text, reply_markup=new_keyboard, parse_mode="HTML")
        
        status_msg = 'ВКЛЮЧЕН' if is_on else 'ВЫКЛЮЧЕН'
        await callback.answer(LEXICON_RU["msg_admin_demurrage_toggled"].format(status=status_msg))
    elif action == "toggle_welcome_group":
        is_on = callback_data.enabled
        await db.set_setting('welcome_group_enabled', '1' if is_on else '0')
        from app.keyboards import get_welcome_group_prompt_keyboard
        current_state = await state.get_state()
        new_keyboard = get_welcome_group_prompt_keyboard(is_on)
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        status_text = 'ВКЛЮЧЕНО' if is_on else 'ВЫКЛЮЧЕНО'
        await callback.answer(LEXICON_RU["msg_admin_welcome_group_toggled"].format(status=status_text))

    elif action == "back_to_settings":
        await state.clear()
        keyboard = await get_settings_keyboard()
        await callback.message.edit_text(LEXICON_RU["msg_admin_settings_menu"], reply_markup=keyboard)
        await callback.answer()

async def _update_setting_and_finish(message: Message, state: FSMContext, key: str, value_transformer=str, validator=None):
    # Проверяем /cancel до попытки парсинга
    if message.text and message.text.strip().lower().startswith('/cancel'):
        await state.clear()
        await message.answer(LEXICON_RU["msg_action_cancelled_plain"])
        from app.handlers.user_commands import show_main_menu
        await show_main_menu(message)
        return
    try:
        value = value_transformer(message.text)
        if validator:
            error_msg = validator(value)
            if error_msg:
                await message.reply(LEXICON_RU["err_admin_validation"].format(error_msg=error_msg))
                return
        await db.set_setting(key, str(value))
        await message.answer(LEXICON_RU["msg_admin_setting_updated"])
        await state.clear()
        await cmd_settings(message)
    except (ValueError, InvalidOperation):
        await message.reply(LEXICON_RU["err_admin_format_retry"])

def _validate_rate(v):
    if v < 0 or v > 100:
        return LEXICON_RU["err_admin_rate_validation"]

def _validate_non_negative(v):
    if v < 0:
        return LEXICON_RU["err_admin_negative_validation"]

def _validate_positive(v):
    if v <= 0:
        return LEXICON_RU["err_admin_positive_validation"]

@router.message(AdminEditStates.waiting_for_welcome_bonus)
async def process_welcome_bonus(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'welcome_bonus_amount', Decimal, _validate_non_negative)
@router.message(AdminEditStates.waiting_for_exchange_rate)
async def process_exchange_rate(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'exchange_rate', Decimal, _validate_positive)
@router.message(AdminEditStates.waiting_for_demurrage_rate)
async def process_demurrage_rate(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'demurrage_rate', Decimal, _validate_rate)
@router.message(AdminEditStates.waiting_for_welcome_text)
async def process_welcome_text(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'welcome_message_bot')
@router.message(AdminEditStates.waiting_for_welcome_text_group)
async def process_welcome_text_group(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'welcome_message_group')
@router.message(AdminEditStates.waiting_for_reminder_text)
async def process_reminder_text(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'default_reminder_text')

@router.message(AdminEditStates.waiting_for_activities_description)
async def process_activities_description_update(message: Message, state: FSMContext):
    await db.set_setting('activities_description', message.text)
    await state.clear()
    await message.answer(LEXICON_RU["msg_admin_activities_desc_updated"])
    # Показываем результат
    from app.handlers.activity_handlers import show_activities_list
    await show_activities_list(message)

@router.message(AdminEditStates.waiting_for_welcome_bonus_text)
async def process_welcome_bonus_text(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'welcome_bonus_message')

# --- ACTIVITY/EVENT MANAGEMENT CALLBACKS ---

@router.callback_query(GeneralAction.filter(F.action == "admin_create_activity"))
async def process_create_activity(callback: CallbackQuery, state: FSMContext):
    await callback.answer(LEXICON_RU["msg_admin_creating_activity"])
    await act_handlers.start_activity_creation(callback.message, state)

@router.callback_query(ActivityAction.filter(F.action == "create_event_for"))
async def process_create_event_for_activity(callback: CallbackQuery, state: FSMContext, callback_data: ActivityAction):
    activity_id = callback_data.activity_id
    # Передаем activity_id в FSM-контекст для event_handlers
    await state.update_data(activity_id=activity_id)
    await event_handlers.start_event_creation_from_activity(callback, state)

@router.callback_query(ActivityAction.filter(F.action == "list_subscribers"))
async def process_list_subscribers(callback: CallbackQuery, callback_data: ActivityAction):
    activity_id = callback_data.activity_id
    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer(LEXICON_RU["err_activity_not_found"], show_alert=True)
        return
    subscribers = await db.get_activity_subscribers(activity_id)
    text_parts = [LEXICON_RU["msg_admin_subscribers_header"].format(activity_name=activity['name'])]
    if not subscribers:
        text_parts.append(LEXICON_RU["msg_admin_no_subscribers"])
    else:
        for i, user in enumerate(subscribers, 1):
            username = f"@{user['username']}" if user['username'] else f"ID:{user['telegram_id']}"
            text_parts.append(LEXICON_RU["msg_admin_subscriber_row"].format(index=i, username=username))
    text = "".join(text_parts)
    keyboard = callback.message.reply_markup
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer(LEXICON_RU["msg_admin_subscribers_found"].format(count=len(subscribers)))


@router.message(Command("cancel_broadcast", ignore_case=True))
async def cmd_cancel_broadcast(message: Message, scheduler: AsyncIOScheduler):
    """Отменяет запланированную рассылку по ID задачи APScheduler."""
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "❌ Укажите ID задачи.\nФормат: <code>/cancel_broadcast broadcast_2_1234567890</code>",
            parse_mode="HTML"
        )
        return
    job_id = parts[1].strip()
    job = scheduler.get_job(job_id)
    if not job:
        await message.reply(f"❌ Задача <code>{job_id}</code> не найдена. Возможно, она уже выполнилась.", parse_mode="HTML")
        return
    scheduler.remove_job(job_id)
    logger.info(f"Admin {message.from_user.id} cancelled broadcast job {job_id}")
    await message.reply(f"✅ Рассылка <code>{job_id}</code> отменена.", parse_mode="HTML")


# --- TAG RULE COMMANDS ---

def _skip_keyboard():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from app.callbacks import GeneralAction
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_skip"], callback_data="tag_rule_skip"))
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack()))
    return builder.as_markup()

def _cancel_keyboard():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from app.callbacks import GeneralAction
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack()))
    return builder.as_markup()


@router.message(Command("get_thread_id", ignore_case=True))
async def cmd_get_thread_id(message: Message):
    """Отвечает ID текущего топика."""
    if message.message_thread_id:
        await message.reply(LEXICON_RU["msg_get_thread_id"].format(thread_id=message.message_thread_id), parse_mode="HTML")
    else:
        await message.reply(LEXICON_RU["msg_no_thread_id"])


@router.message(Command("list_tag_rules", ignore_case=True))
async def cmd_list_tag_rules(message: Message):
    """Показывает все правила начисления по хэштегам."""
    rules = await db.get_all_tag_rules()
    if not rules:
        await message.answer(LEXICON_RU["msg_tag_rules_list_empty"])
        return
    text = LEXICON_RU["msg_tag_rules_list_header"]
    for rule in rules:
        limit_str = f", лимит {rule['daily_limit']}/день" if rule['daily_limit'] else ""
        thread_str = f", топик {rule['thread_id']}" if rule['thread_id'] else ""
        status = "" if rule['is_active'] else " [откл.]"
        text += LEXICON_RU["msg_tag_rule_row"].format(
            hashtag=rule['hashtag'], min_chars=rule['min_chars'],
            reward=rule['reward'], currency_symbol=CURRENCY_SYMBOL,
            limit_str=limit_str, thread_str=thread_str, rule_id=rule['id']
        ) + status
    
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from app.callbacks import SettingsAction
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки удаления для каждого правила
    for rule in rules:
        builder.row(InlineKeyboardButton(text=f"🗑 Удалить #{rule['hashtag']}", callback_data=f"del_tag_rule_{rule['id']}"))
        
    builder.row(InlineKeyboardButton(text="➕ Добавить правило", callback_data="add_tag_rule_btn"))
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=SettingsAction(action="back_to_settings").pack()))
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "add_tag_rule_btn")
async def process_add_tag_rule_btn(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await cmd_add_tag_rule_start(callback.message, state)
    await callback.answer()

@router.callback_query(F.data.startswith("del_tag_rule_"))
async def process_del_tag_rule(callback: CallbackQuery):
    rule_id = int(callback.data.split("_")[-1])
    rule = await db.get_tag_rule(rule_id)
    if not rule:
        await callback.answer(LEXICON_RU["err_tag_rule_not_found"], show_alert=True)
        return
        
    await db.delete_tag_rule(rule_id)
    logger.info(f"Admin {callback.from_user.id} deleted tag rule {rule_id} (#{rule['hashtag']})")
    await callback.answer(LEXICON_RU["msg_tag_rule_deleted"].format(rule_id=rule_id))
    
    # Обновляем список
    await callback.message.delete()
    await cmd_list_tag_rules(callback.message)


@router.message(Command("add_tag_rule", ignore_case=True))
async def cmd_add_tag_rule_start(message: Message, state: FSMContext):
    """Запускает FSM создания правила."""
    await state.set_state(TagRuleCreationStates.waiting_for_hashtag)
    # Удаляем обычную клавиатуру, если она застряла (ReplyKeyboardRemove), 
    # а инлайн отправляем через edit_text ниже, но так как это старт, мы просто 
    # шлем отдельное сообщение с удалением, а затем сам вопрос.
    from aiogram.types import ReplyKeyboardRemove
    temp_msg = await message.answer("Запускаю процесс создания...", reply_markup=ReplyKeyboardRemove())
    await temp_msg.delete()
    await message.answer(LEXICON_RU["msg_add_tag_rule_hashtag"], reply_markup=_cancel_keyboard(), parse_mode="HTML")


@router.message(TagRuleCreationStates.waiting_for_hashtag)
async def tag_rule_get_hashtag(message: Message, state: FSMContext):
    tag = message.text.strip().lstrip('#').lower()
    if not tag:
        await message.reply("Введите непустой хэштег.")
        return
    await state.update_data(hashtag=tag)
    await state.set_state(TagRuleCreationStates.waiting_for_min_chars)
    await message.answer(LEXICON_RU["msg_add_tag_rule_min_chars"], reply_markup=_cancel_keyboard())


@router.message(TagRuleCreationStates.waiting_for_min_chars)
async def tag_rule_get_min_chars(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.reply("Введите целое число ≥ 0.")
        return
    await state.update_data(min_chars=int(message.text.strip()))
    await state.set_state(TagRuleCreationStates.waiting_for_reward)
    await message.answer(LEXICON_RU["msg_add_tag_rule_reward"], reply_markup=_cancel_keyboard())


@router.message(TagRuleCreationStates.waiting_for_reward)
async def tag_rule_get_reward(message: Message, state: FSMContext):
    from decimal import Decimal, InvalidOperation
    try:
        reward = Decimal(message.text.strip().replace(',', '.'))
        if reward <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await message.reply("Введите положительное число, например: 100")
        return
    await state.update_data(reward=float(reward))
    await state.set_state(TagRuleCreationStates.waiting_for_daily_limit)
    await message.answer(LEXICON_RU["msg_add_tag_rule_daily_limit"], reply_markup=_cancel_keyboard())


@router.message(TagRuleCreationStates.waiting_for_daily_limit)
async def tag_rule_get_daily_limit(message: Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.reply("Введите целое число ≥ 0.")
        return
    await state.update_data(daily_limit=int(message.text.strip()))
    await state.set_state(TagRuleCreationStates.waiting_for_thread_id)
    await message.answer(LEXICON_RU["msg_add_tag_rule_thread_id"], reply_markup=_skip_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "tag_rule_skip", TagRuleCreationStates.waiting_for_thread_id)
async def tag_rule_skip_thread_id(callback: CallbackQuery, state: FSMContext):
    await state.update_data(thread_id=None)
    await state.set_state(TagRuleCreationStates.waiting_for_group_msg)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(LEXICON_RU["msg_add_tag_rule_group_msg"], reply_markup=_skip_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(TagRuleCreationStates.waiting_for_thread_id)
async def tag_rule_get_thread_id(message: Message, state: FSMContext):
    txt = message.text.strip()
    if not txt.lstrip('-').isdigit():
        await message.reply("Введите числовой ID топика или нажмите Skip.")
        return
    await state.update_data(thread_id=int(txt))
    await state.set_state(TagRuleCreationStates.waiting_for_group_msg)
    await message.answer(LEXICON_RU["msg_add_tag_rule_group_msg"], reply_markup=_skip_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "tag_rule_skip", TagRuleCreationStates.waiting_for_group_msg)
async def tag_rule_skip_group_msg(callback: CallbackQuery, state: FSMContext):
    await state.update_data(group_msg=None)
    await state.set_state(TagRuleCreationStates.waiting_for_bot_msg)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(LEXICON_RU["msg_add_tag_rule_bot_msg"], reply_markup=_skip_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(TagRuleCreationStates.waiting_for_group_msg)
async def tag_rule_get_group_msg(message: Message, state: FSMContext):
    await state.update_data(group_msg=message.text.strip())
    await state.set_state(TagRuleCreationStates.waiting_for_bot_msg)
    await message.answer(LEXICON_RU["msg_add_tag_rule_bot_msg"], reply_markup=_skip_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "tag_rule_skip", TagRuleCreationStates.waiting_for_bot_msg)
async def tag_rule_skip_bot_msg(callback: CallbackQuery, state: FSMContext):
    await state.update_data(bot_msg=None)
    await state.set_state(TagRuleCreationStates.waiting_for_reaction)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(LEXICON_RU["msg_add_tag_rule_reaction"], reply_markup=_skip_keyboard())
    await callback.answer()


@router.message(TagRuleCreationStates.waiting_for_bot_msg)
async def tag_rule_get_bot_msg(message: Message, state: FSMContext):
    await state.update_data(bot_msg=message.text.strip())
    await state.set_state(TagRuleCreationStates.waiting_for_reaction)
    await message.answer(LEXICON_RU["msg_add_tag_rule_reaction"], reply_markup=_skip_keyboard())


@router.callback_query(F.data == "tag_rule_skip", TagRuleCreationStates.waiting_for_reaction)
async def tag_rule_skip_reaction(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_reply_markup(reply_markup=None)
    await _finish_tag_rule(callback.message, state, reaction='🏅')
    await callback.answer()


@router.message(TagRuleCreationStates.waiting_for_reaction)
async def tag_rule_get_reaction(message: Message, state: FSMContext):
    await _finish_tag_rule(message, state, reaction=message.text.strip())


async def _finish_tag_rule(message, state: FSMContext, reaction: str):
    data = await state.get_data()
    await state.clear()
    rule_id = await db.create_tag_rule(
        hashtag=data['hashtag'],
        min_chars=data['min_chars'],
        reward=data['reward'],
        daily_limit=data['daily_limit'],
        thread_id=data.get('thread_id'),
        group_msg=data.get('group_msg'),
        bot_msg=data.get('bot_msg'),
        reaction=reaction
    )
    logger.info(f"Tag rule #{rule_id} created: #{data['hashtag']} -> {data['reward']}")
    await message.answer(
        LEXICON_RU["msg_tag_rule_created"].format(
            rule_id=rule_id, hashtag=data['hashtag'], reward=data['reward'],
            currency_symbol=CURRENCY_SYMBOL
        ),
        parse_mode="HTML"
    )
