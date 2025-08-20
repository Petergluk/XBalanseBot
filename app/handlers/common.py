# XBalanseBot/app/handlers/common.py
# v1.5.4 - 2025-08-16
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart, ChatMemberUpdatedFilter, JOIN_TRANSITION, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import any_state
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery
from app.config import (
    CURRENCY_SYMBOL, MAIN_GROUP_ID, DEFAULT_WELCOME_MESSAGE_BOT, 
    DEFAULT_WELCOME_MESSAGE_GROUP, DEFAULT_HELP_TEXT_USER, DEFAULT_HELP_TEXT_ADMIN_ADDON,
    DEFAULT_HELP_TEXT_GROUP
)
from app.utils import ensure_user_exists, is_admin, is_user_in_group, format_amount
from app.database import db
from app.keyboards import get_activities_keyboard
from decimal import Decimal, InvalidOperation

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command("cancel", ignore_case=True), StateFilter(any_state))
async def cmd_cancel(message: Message, state: FSMContext):
    """Обработчик команды /cancel для выхода из любого диалога."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного диалога для отмены.")
        return

    logger.info(f"User {message.from_user.id} cancelled state {current_state}")
    await state.clear()
    await message.answer("Действие отменено. Вы вышли из диалога.")

@router.callback_query(F.data == "cancel_delete", StateFilter(any_state))
async def process_cancel_delete(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки 'Отмена' в любом диалоге подтверждения.
    """
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
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
    
    if not await is_user_in_group(message.bot, message.from_user.id):
        admins = await db.get_all_admins()
        admin_contact = "администратору"
        if admins:
            first_admin = await db.get_user(telegram_id=admins[0]['telegram_id'])
            if first_admin and first_admin['username']:
                admin_contact = f"@{first_admin['username']}"
        
        logger.warning(f"User {message.from_user.id} tried to start bot but not in group")
        await message.answer(
            f"❌ Вы не состоите в основной группе сообщества.\n\n"
            f"Для получения доступа к боту обратитесь к {admin_contact}."
        )
        return
    
    is_new_user = await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
    
    if is_new_user:
        bonus_amount_str = await db.get_setting('welcome_bonus_amount', '0')
        try:
            welcome_bonus = Decimal(bonus_amount_str)
            logger.info(f"Calculated welcome_bonus for user {message.from_user.id}: {welcome_bonus} from string '{bonus_amount_str}'")

            if welcome_bonus > 0:
                async with db.pool.connection() as conn:
                    # ИСПРАВЛЕНО: Правильный паттерн
                    result_cursor = await conn.execute("SELECT id FROM users WHERE telegram_id = %s", (message.from_user.id,))
                    user_row = await result_cursor.fetchone()
                    if user_row:
                        user_id = user_row[0]
                        await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (welcome_bonus, user_id))
                        await conn.execute(
                            "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (0, %s, %s, 'welcome_bonus', %s)",
                            (user_id, welcome_bonus, "Welcome-бонус для нового участника")
                        )
                        logger.info(f"Welcome bonus {welcome_bonus} credited to user {message.from_user.id}")
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.error(f"Could not parse welcome_bonus_amount '{bonus_amount_str}': {e}")
            welcome_bonus = Decimal('0')

    welcome_text = await db.get_setting('welcome_message_bot', DEFAULT_WELCOME_MESSAGE_BOT)
    
    welcome_text = welcome_text.replace('{username}', message.from_user.mention_html())
    bot_info = await message.bot.get_me()
    welcome_text = welcome_text.replace('{bot_username}', f"@{bot_info.username}")
    
    if is_new_user and 'welcome_bonus' in locals() and welcome_bonus > 0:
        welcome_text += f"\n\n💰 Вам начислен welcome-бонус: <b>{format_amount(welcome_bonus)} {CURRENCY_SYMBOL}</b>!"
    
    await message.answer(welcome_text, parse_mode="HTML")
    logger.info(f"Sent welcome message to user {message.from_user.id}")

    all_activities = await db.get_all_activities()
    general_activity_events = await db.get_events_for_activity(1)
    activities_to_show = []
    for act in all_activities:
        if act['id'] == 1:
            if general_activity_events:
                activities_to_show.append(act)
        else:
            activities_to_show.append(act)
    
    if activities_to_show:
        user_subscriptions = await db.get_user_subscriptions(message.from_user.id)
        keyboard = await get_activities_keyboard(activities_to_show, user_subscriptions)
        await message.answer(
            "👇 Вы можете выбрать интересующие вас активности для подписки:",
            reply_markup=keyboard
        )


@router.message(Command("help", ignore_case=True))
async def cmd_help(message: Message):
    """
    Обработчик команды /help.
    Показывает разную справку в зависимости от типа чата и прав пользователя.
    """
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
    
    if message.chat.type in ('group', 'supergroup'):
        help_text = DEFAULT_HELP_TEXT_GROUP
    else:
        help_text = DEFAULT_HELP_TEXT_USER
        if await is_admin(message.from_user.id):
            help_text += DEFAULT_HELP_TEXT_ADMIN_ADDON
    
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
        bonus_amount_str = await db.get_setting('welcome_bonus_amount', '0')
        try:
            welcome_bonus = Decimal(bonus_amount_str)
            logger.info(f"Calculated welcome_bonus for new member {new_member.id}: {welcome_bonus} from string '{bonus_amount_str}'")

            if welcome_bonus > 0:
                async with db.pool.connection() as conn:
                    # ИСПРАВЛЕНО: Правильный паттерн
                    result_cursor = await conn.execute("SELECT id FROM users WHERE telegram_id = %s", (new_member.id,))
                    user_row = await result_cursor.fetchone()
                    if user_row:
                        user_id = user_row[0]
                        await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (welcome_bonus, user_id))
                        await conn.execute(
                            "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (0, %s, %s, 'welcome_bonus', %s)",
                            (user_id, welcome_bonus, "Welcome-бонус за вступление в группу")
                        )
                        logger.info(f"Welcome bonus {welcome_bonus} credited to new member {new_member.id}")
        except (ValueError, TypeError, InvalidOperation) as e:
            logger.error(f"Could not parse welcome_bonus_amount for new member '{bonus_amount_str}': {e}")
            welcome_bonus = Decimal('0')

    welcome_text = await db.get_setting('welcome_message_group', DEFAULT_WELCOME_MESSAGE_GROUP)
    
    try:
        bot_info = await bot.get_me()
        formatted_text = welcome_text.replace('{username}', new_member.mention_html())
        formatted_text = formatted_text.replace('{bot_username}', f"@{bot_info.username}")
        
        if is_new_user and 'welcome_bonus' in locals() and welcome_bonus > 0:
            formatted_text += f"\n\n💰 Вам начислен welcome-бонус: <b>{format_amount(welcome_bonus)} {CURRENCY_SYMBOL}</b>!"
        
        await bot.send_message(MAIN_GROUP_ID, formatted_text, parse_mode="HTML")
        logger.info(f"Sent group welcome message for user {new_member.id}")
    except Exception as e:
        logger.error(f"Failed to send welcome message for user {new_member.id}: {e}", exc_info=True)

@router.callback_query(F.data == "already_subscribed")
async def process_already_subscribed(callback: CallbackQuery):
    """
    Обрабатывает нажатие на кнопку активности, на которую пользователь уже подписан.
    """
    await callback.answer("Вы уже подписаны на эту активность.", show_alert=False)
