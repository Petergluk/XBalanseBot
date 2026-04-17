# XBalanseBot/app/handlers/common.py
# FULL FILE EMITTED: YES
# v1.5.6
# 2025-08-29 04:15:00
"""
Модуль с общими обработчиками (/start, /help, /cancel, вступление в группу).

Версия 1.5.6:
- Полностью переведена логика обработки callback_data на использование фабрик
  из `app.callbacks`, что повышает надежность и читаемость кода.
- Удалены устаревшие методы парсинга callback_data на основе строк.

Версия 1.5.5:
- В cmd_start добавлен вызов нового главного меню пользователя.
- Из cmd_start убран показ списка активностей, так как он доступен из меню.
- В cmd_help добавлено форматирование имени бота для групповой справки.
"""
import logging
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.filters import (ChatMemberUpdatedFilter, Command, CommandStart,
                             StateFilter, JOIN_TRANSITION)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import any_state
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from app.config import CURRENCY_SYMBOL, MAIN_GROUP_ID
from app.lexicon import LEXICON_RU
from app.database import db
from app.handlers.user_commands import show_main_menu
from app.utils import ensure_user_exists, format_amount, is_admin
from app.callbacks import GeneralAction

router = Router()
logger = logging.getLogger(__name__)


async def _credit_welcome_bonus(telegram_id: int, comment: str):
    """Обёртка для db.credit_welcome_bonus, возвращающая Decimal."""
    return await db.credit_welcome_bonus(telegram_id, comment)

@router.message(Command("cancel", ignore_case=True), StateFilter(any_state))
async def cmd_cancel(message: Message, state: FSMContext):
    """Обработчик команды /cancel для выхода из любого диалога."""
    current_state = await state.get_state()
    if current_state is None:
        from app.handlers.user_commands import show_main_menu
        await show_main_menu(message)
        return

    logger.info(f"User {message.from_user.id} cancelled state {current_state}")
    # Попытаемся удалить сообщения, если они были сохранены в FSM
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    if message_ids:
        try:
            await message.bot.delete_messages(chat_id=message.chat.id, message_ids=message_ids)
        except Exception as e:
            logger.warning(f"Could not delete messages in cancel dialog: {e}")
    
    await state.clear()
    await message.answer(LEXICON_RU["msg_action_cancelled_plain"])
    # Показываем главное меню, чтобы пользователь не остался без кнопок
    from app.handlers.user_commands import show_main_menu
    await show_main_menu(message)

@router.callback_query(GeneralAction.filter(F.action == "cancel_dialog"), StateFilter(any_state))
async def process_cancel_delete(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки 'Отмена' в любом диалоге подтверждения.
    """
    # Также очищаем сообщения, если были
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    if message_ids:
        try:
            await callback.bot.delete_messages(chat_id=callback.message.chat.id, message_ids=message_ids)
        except Exception as e:
            logger.warning(f"Could not delete messages in cancel_dialog callback: {e}")

    await state.clear()
    from app.keyboards import get_back_to_menu_keyboard
    await callback.message.edit_text(LEXICON_RU["msg_action_cancelled"], reply_markup=get_back_to_menu_keyboard())
    await callback.answer()


@router.message(CommandStart(ignore_case=True))
async def cmd_start(message: Message, state: FSMContext):
    """
    Обработчик команды /start.
    """
    if message.from_user.is_bot:
        return
        
    await state.clear()
    logger.info(f"User {message.from_user.id} (@{message.from_user.username}) started bot")
    
    user = await db.get_user(telegram_id=message.from_user.id)
    is_new = not bool(user)
    
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
    
    # Гарантируем права суперадмина при каждом /start
    from app.config import SUPER_ADMIN_ID
    if message.from_user.id == SUPER_ADMIN_ID:
        user_db = await db.get_user(telegram_id=SUPER_ADMIN_ID)
        if user_db and not user_db['is_admin']:
            await db.set_admin_status(SUPER_ADMIN_ID, True)
            logger.info(f"Super admin {SUPER_ADMIN_ID} re-promoted via /start")
    
    if not is_new:
        stats = await db.get_returning_user_stats(message.from_user.id)
        if stats and (stats['sent'] > 0 or stats['received'] > 0 or stats['deducted'] > 0):
            # Returning active user — show full stats greeting
            text = LEXICON_RU["msg_welcome_back"].format(
                mention=message.from_user.mention_html(),
                balance=format_amount(stats['balance']),
                currency_symbol=CURRENCY_SYMBOL,
                sent=format_amount(stats['sent']),
                received=format_amount(stats['received']),
                deducted=format_amount(stats['deducted'])
            )
            from app.keyboards import get_back_to_menu_keyboard
            await message.answer(text, reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")
        else:
            # Already in DB but no transactions yet — playful short greeting, then menu
            text = LEXICON_RU["msg_welcome_back_simple"].format(
                mention=message.from_user.mention_html()
            )
            from app.keyboards import get_back_to_menu_keyboard
            await message.answer(text, reply_markup=get_back_to_menu_keyboard(), parse_mode="HTML")
        return
        
    # Пользователь новый -> Начинаем онбординг
    welcome_text_template = await db.get_setting('welcome_message_bot', LEXICON_RU["default_welcome_bot"])
    welcome_text = welcome_text_template.replace('{username}', message.from_user.mention_html())
    
    from app.keyboards import get_onboarding_keyboard
    await message.answer(welcome_text, reply_markup=get_onboarding_keyboard(), parse_mode="HTML")
    logger.info(f"Sent onboarding message to new user {message.from_user.id}")

@router.callback_query(GeneralAction.filter(F.action == "onboarding_agree"))
async def process_onboarding_agree(callback: CallbackQuery):
    """Обработка нажатия кнопки 'Согласен'."""
    await callback.answer()
    try:
        from app.config import MAIN_GROUP_ID
        import time
        from app.handlers.tag_reward_handler import get_redis_client
        
        user_id = callback.from_user.id
        redis = get_redis_client()
        cache_key = f"invite_link:{user_id}"
        cached_link = await redis.get(cache_key)
        
        if cached_link:
            await callback.message.edit_text(
                LEXICON_RU["msg_invite_link"].format(invite_link=cached_link),
                reply_markup=None,
                disable_web_page_preview=True
            )
            return

        expire_date = int(time.time()) + 86400  # 24 hours
        invite_link_obj = await callback.bot.create_chat_invite_link(
            chat_id=MAIN_GROUP_ID, 
            member_limit=1,
            expire_date=expire_date,
            name=f"Invite for {callback.from_user.full_name}"
        )
        
        await redis.setex(cache_key, 86400, invite_link_obj.invite_link)
        
        await callback.message.edit_text(
            LEXICON_RU["msg_invite_link"].format(invite_link=invite_link_obj.invite_link),
            reply_markup=None,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Failed to create invite link: {e}")
        await callback.message.edit_text(
            LEXICON_RU["err_invite_link"],
            reply_markup=None
        )


@router.message(Command("help", ignore_case=True))
async def cmd_help(message: Message):
    """
    Обработчик команды /help.
    Показывает разную справку в зависимости от типа чата и прав пользователя.
    """
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
    
    if message.chat.type in ('group', 'supergroup'):
        help_text = LEXICON_RU["help_group"]
        bot_info = await message.bot.get_me()
        help_text = help_text.format(bot_username=bot_info.username, currency_symbol=CURRENCY_SYMBOL)
    else:
        help_text = LEXICON_RU["help_user"].format(currency_symbol=CURRENCY_SYMBOL)
        if await is_admin(message.from_user.id):
            help_text += LEXICON_RU["help_admin_addon"]
    
    await message.answer(help_text, parse_mode="HTML")

@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_join(event: ChatMemberUpdated, bot: Bot):
    """Обработка вступления нового участника в группу."""
    logger.info(f"User {event.new_chat_member.user.id} joined chat {event.chat.id}")
    
    if str(event.chat.id) != str(MAIN_GROUP_ID):
        return
    
    new_member = event.new_chat_member.user
    if new_member.is_bot:
        logger.info(f"A bot named {new_member.full_name} ({new_member.id}) joined the main group. Ignoring.")
        return

    logger.info(f"User {new_member.full_name} ({new_member.id}) joined the main group")
    
    is_new_user = await ensure_user_exists(new_member.id, new_member.username, new_member.is_bot)
    
    if is_new_user:
        await _credit_welcome_bonus(new_member.id, "Велком-бонус за вступление по приглашению")
        bonus_amount = await db.get_setting('welcome_bonus_amount', '1500')
        bonus_text_template = await db.get_setting('welcome_bonus_message', LEXICON_RU["default_welcome_bonus"])
        
        bonus_text = bonus_text_template.format(
            amount=bonus_amount,
            currency_symbol=CURRENCY_SYMBOL,
            username=new_member.full_name or new_member.first_name
        )
        
        try:
            from app.keyboards import get_back_to_menu_keyboard
            await bot.send_message(
                new_member.id,
                bonus_text,
                reply_markup=get_back_to_menu_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not send welcome DM to {new_member.id}: {e}")

    # Проверяем, нужно ли отправлять приветствие в саму группу
    if await db.get_setting('welcome_group_enabled', '0') == '1':
        welcome_text_template = await db.get_setting('welcome_message_group', LEXICON_RU["default_welcome_group"])
        bot_info = await bot.get_me()
        welcome_text = welcome_text_template.format(username=new_member.mention_html(), bot_username=bot_info.username)
        await bot.send_message(event.chat.id, welcome_text, parse_mode="HTML")
    else:
        logger.info(f"Processed join for user {new_member.id} silently (group welcome disabled).")

@router.callback_query(F.data == "already_subscribed")
async def process_already_subscribed(callback: CallbackQuery):
    """
    Обрабатывает нажатие на кнопку активности, на которую пользователь уже подписан.
    """
    await callback.answer(LEXICON_RU["msg_already_subscribed"], show_alert=False)
