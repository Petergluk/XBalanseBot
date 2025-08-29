# XBalanseBot/app/handlers/user_commands.py
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
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from psycopg.rows import dict_row

from app.config import CURRENCY_SYMBOL
from app.database import db
from app.handlers import activity_handlers, common as common_handlers, event_handlers
from app.keyboards import (get_back_to_menu_keyboard, get_main_menu_keyboard,
                           get_transfer_confirmation_keyboard)
from app.states import TransferStates
from app.utils import (ensure_user_exists, format_amount,
                       format_transactions_history, get_transaction_count,
                       get_user_balance, is_user_in_group)
from app.callbacks import GeneralAction, TransferAction

router = Router()
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
    async with db.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
            user_db_id_row = await cur.fetchone()
            if not user_db_id_row:
                return "Не удалось найти ваш профиль в системе."
            user_db_id = user_db_id_row['id']
            date_limit = datetime.now() - timedelta(days=days)
            await cur.execute(
                "SELECT t.*, sender.username as sender_username, recipient.username as recipient_username "
                "FROM transactions t "
                "LEFT JOIN users sender ON t.from_user_id = sender.id "
                "LEFT JOIN users recipient ON t.to_user_id = recipient.id "
                "WHERE (t.to_user_id = %s OR t.from_user_id = %s) AND t.created_at > %s "
                "ORDER BY t.created_at DESC",
                (user_db_id, user_db_id, date_limit)
            )
            all_txs = await cur.fetchall()

    if not all_txs:
        return f"За последние {days} дней транзакций не найдено."

    response_parts = [f"📊 <b>История транзакций за последние {days} дней:</b>"]
    history_text = format_transactions_history(all_txs, user_db_id)
    response_parts.append(history_text)
    response_parts.append(f"\n💰 <b>Текущий баланс:</b> {format_amount(current_balance)} {CURRENCY_SYMBOL}")
    return "".join(response_parts)


# --- Обработчик /cancel специально для состояний TransferStates ---
@router.message(Command("cancel"), StateFilter(TransferStates))
async def cancel_transfer_dialog(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)
    await state.update_data(message_ids=message_ids)
    
    await cleanup_transfer_dialog(state, bot, message.chat.id)
    await message.answer("Перевод отменен.")


# --- БЛОК ГЛАВНОГО МЕНЮ ---

async def show_main_menu(message: Message | CallbackQuery):
    text = "🤖 **Главное меню**\n\nВыберите действие:"
    keyboard = get_main_menu_keyboard()
    
    if isinstance(message, Message):
        await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
    elif isinstance(message, CallbackQuery):
        try:
            await message.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await message.bot.send_message(message.from_user.id, text, reply_markup=keyboard, parse_mode="Markdown")
        await message.answer()

@router.message(Command("menu", ignore_case=True))
async def cmd_menu(message: Message):
    if not await is_user_in_group(message.bot, message.from_user.id):
        return
    await show_main_menu(message)

@router.callback_query(GeneralAction.filter(F.action == "main_menu"))
async def process_back_to_menu(callback: CallbackQuery):
    await show_main_menu(callback)

@router.callback_query(GeneralAction.filter(F.action == "menu_balance"))
async def process_menu_balance(callback: CallbackQuery):
    await ensure_user_exists(callback.from_user.id, callback.from_user.username, callback.from_user.is_bot)
    balance = await get_user_balance(callback.from_user.id)
    tx_count = await get_transaction_count(callback.from_user.id)
    text = (
        f"💰 Ваш баланс: <b>{format_amount(balance)} {CURRENCY_SYMBOL}</b>\n"
        f"📊 Совершено транзакций: <b>{tx_count}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_back_to_menu_keyboard(),
    )
    await callback.answer()

@router.callback_query(GeneralAction.filter(F.action == "menu_history"))
async def process_menu_history(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    user = callback.from_user
    await ensure_user_exists(user.id, user.username, user.is_bot)
    
    history_text = await _get_history_text(user.id, days=30)
    
    await callback.message.answer(
        history_text,
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
    await callback.message.delete()
    await event_handlers.cmd_event(callback.message)

@router.callback_query(GeneralAction.filter(F.action == "menu_help"))
async def process_menu_help(callback: CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    await common_handlers.cmd_help(callback.message)

@router.callback_query(GeneralAction.filter(F.action == "menu_send"))
async def process_menu_send(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(TransferStates.waiting_for_recipient)
    sent_message = await callback.message.edit_text(
        "Кому вы хотите сделать перевод? Укажите @username получателя.\n\nДля отмены введите /cancel",
        reply_markup=None
    )
    await state.update_data(message_ids=[sent_message.message_id])


# --- СУЩЕСТВУЮЩИЕ КОМАНДЫ (продолжают работать автономно) ---

@router.message(Command("balance", "баланс", ignore_case=True))
async def cmd_balance(message: Message):
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
    balance = await get_user_balance(message.from_user.id)
    tx_count = await get_transaction_count(message.from_user.id)
    await message.answer(
        f"💰 Ваш баланс: <b>{format_amount(balance)} {CURRENCY_SYMBOL}</b>\n"
        f"📊 Совершено транзакций: <b>{tx_count}</b>",
        parse_mode="HTML"
    )

@router.message(Command("send", ignore_case=True))
async def cmd_send(message: Message, state: FSMContext, bot: Bot):
    await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
    args = message.text.split()
    
    if len(args) >= 3:
        recipient_username = args[1].lstrip('@').lower()
        if recipient_username == (message.from_user.username or '').lower():
            await message.reply("❌ Нельзя отправить средства самому себе.")
            return
        try:
            amount = Decimal(args[2])
            if amount <= 0: raise ValueError
        except (InvalidOperation, ValueError):
            await message.reply("❌ Неверная сумма. Пожалуйста, укажите положительное число.")
            return
        recipient = await db.get_user(username=recipient_username)
        if not recipient or (recipient['telegram_id'] != 0 and not await is_user_in_group(bot, recipient['telegram_id'])):
            await message.reply(f"❌ Пользователь @{recipient_username} не найден или не является участником группы.")
            return
        comment = ' '.join(args[3:]) if len(args) > 3 else "Перевод"
        await perform_transfer_and_notify(message, state, bot, recipient, amount, comment, is_dialog=False)
        return

    if len(args) == 1:
        await state.set_state(TransferStates.waiting_for_recipient)
        sent_message = await message.answer("Кому вы хотите сделать перевод? Укажите @username получателя.\n\nДля отмены введите /cancel")
        await state.update_data(message_ids=[message.message_id, sent_message.message_id])
        return
        
    await message.reply("❌ Неверный формат. Используйте:\n`/send @username сумма [комментарий]`\nили просто `/send` для запуска диалога.", parse_mode="Markdown")

@router.message(TransferStates.waiting_for_recipient)
async def process_recipient_input(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)

    recipient_username = message.text.lstrip('@').lower()
    if recipient_username == (message.from_user.username or '').lower():
        sent_message = await message.reply("❌ Нельзя отправить средства самому себе. Укажите другой @username.")
        message_ids.append(sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return

    recipient = await db.get_user(username=recipient_username)
    if not recipient or (recipient['telegram_id'] != 0 and not await is_user_in_group(bot, recipient['telegram_id'])):
        sent_message = await message.reply(f"❌ Пользователь @{recipient_username} не найден или не является участником группы. Попробуйте еще раз.\n\nДля отмены введите /cancel")
        message_ids.append(sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return
    
    await state.update_data(recipient_id=recipient['id'], recipient_telegram_id=recipient['telegram_id'], recipient_username=recipient_username)
    await state.set_state(TransferStates.waiting_for_amount)
    sent_message = await message.answer(f"Отлично. Какую сумму в {CURRENCY_SYMBOL} вы хотите перевести @{recipient_username}?\n\nДля отмены введите /cancel")
    message_ids.append(sent_message.message_id)
    await state.update_data(message_ids=message_ids)

@router.message(TransferStates.waiting_for_amount)
async def process_amount_input(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)
    
    try:
        amount = Decimal(message.text.replace(',', '.'))
        if amount <= 0: raise ValueError
    except (InvalidOperation, ValueError):
        sent_message = await message.reply("❌ Сумма должна быть положительным числом. Попробуйте еще раз.\n\nДля отмены введите /cancel")
        message_ids.append(sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return
        
    sender_balance = await get_user_balance(message.from_user.id)
    if sender_balance < amount:
        sent_message = await message.reply(f"❌ Недостаточно средств. Ваш баланс: <b>{format_amount(sender_balance)} {CURRENCY_SYMBOL}</b>. Введите другую сумму.\n\nДля отмены введите /cancel", parse_mode="HTML")
        message_ids.append(sent_message.message_id)
        await state.update_data(message_ids=message_ids)
        return

    await state.update_data(amount=str(amount))
    await state.set_state(TransferStates.waiting_for_comment)
    sent_message = await message.answer("Теперь добавьте короткий комментарий к переводу (например, 'За кофе').\n\nДля отмены введите /cancel")
    message_ids.append(sent_message.message_id)
    await state.update_data(message_ids=message_ids)

@router.message(TransferStates.waiting_for_comment)
async def process_comment_input(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)
    
    await state.update_data(comment=message.text)
    
    dialog_data = await state.get_data()
    amount = Decimal(dialog_data['amount'])
    recipient_username = dialog_data['recipient_username']
    
    confirmation_text = (f"Пожалуйста, проверьте детали перевода:\n\n➡️ <b>Получатель:</b> @{recipient_username}\n💰 <b>Сумма:</b> {format_amount(amount)} {CURRENCY_SYMBOL}\n💬 <b>Комментарий:</b> {message.text}\n\nВсё верно?")
    
    await state.set_state(TransferStates.waiting_for_confirmation)
    sent_message = await message.answer(confirmation_text, reply_markup=get_transfer_confirmation_keyboard(), parse_mode="HTML")
    message_ids.append(sent_message.message_id)
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
    await callback.message.answer("Перевод отменен.")
    await callback.answer()


async def perform_transfer_and_notify(message: Message | CallbackQuery, state: FSMContext, bot: Bot, recipient: dict, amount: Decimal, comment: str, is_dialog: bool):
    sender = message.from_user
    chat_id = message.chat.id if isinstance(message, Message) else message.message.chat.id
    
    if is_dialog:
        await cleanup_transfer_dialog(state, bot, chat_id)

    sender_balance = await get_user_balance(sender.id)
    if sender_balance < amount:
        await bot.send_message(chat_id, f"❌ Недостаточно средств. Ваш баланс: <b>{format_amount(sender_balance)} {CURRENCY_SYMBOL}</b>", parse_mode="HTML")
        return

    try:
        async with db.pool.connection() as conn:
            async with conn.transaction():
                result_cursor = await conn.execute("SELECT id FROM users WHERE telegram_id = %s", (sender.id,))
                sender_db_id = (await result_cursor.fetchone())[0]
                await conn.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (amount, sender_db_id))
                await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount, recipient['id']))
                await conn.execute("INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'transfer', %s)", (sender_db_id, recipient['id'], amount, comment))
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id IN (%s, %s)", (sender_db_id, recipient['id']))
        
        logger.info(f"Transfer successful: {sender.id} -> {recipient['telegram_id']}, amount: {amount}")
        await db.handle_debt_repayment(recipient['id'])

        response_text = (f"✅ Перевод выполнен!\n\n<b>Получатель:</b> @{recipient['username']}\n<b>Сумма:</b> {format_amount(amount)} {CURRENCY_SYMBOL}\n<b>Комментарий:</b> {comment}")
        await bot.send_message(chat_id, response_text, parse_mode="HTML")
        
        if recipient['telegram_id'] != 0:
            try:
                sender_username = sender.username or f"user{sender.id}"
                await bot.send_message(recipient['telegram_id'], f"💸 Вам поступил перевод!\n\n<b>Отправитель:</b> @{sender_username}\n<b>Сумма:</b> {format_amount(amount)} {CURRENCY_SYMBOL}\n<b>Комментарий:</b> {comment}", parse_mode="HTML")
            except Exception as e:
                logger.warning(f"Could not send notification to recipient {recipient['telegram_id']}: {e}")

    except Exception as e:
        logger.error(f"Transaction failed between users {sender.id} -> {recipient['telegram_id']}: {e}", exc_info=True)
        await bot.send_message(chat_id, "❌ Произошла ошибка при выполнении перевода. Попробуйте позже.")


@router.message(Command("history", ignore_case=True))
async def cmd_history(message: Message):
    user = message.from_user
    await ensure_user_exists(user.id, user.username, user.is_bot)
    args = message.text.split()
    try:
        days = int(args[1]) if len(args) > 1 else 30
    except (ValueError, IndexError):
        days = 30
    
    history_text = await _get_history_text(user.id, days=days)
    await message.answer(history_text, parse_mode="HTML")


@router.message(Command("gdp", "ввп", ignore_case=True))
async def cmd_gdp(message: Message):
    async with db.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            now = datetime.now()
            async def get_turnover_and_count(days=None):
                query = "SELECT COALESCE(SUM(amount), 0) as turnover, COUNT(id) as tx_count FROM transactions WHERE type = 'transfer'"
                params = []
                if days:
                    query += " AND created_at > %s"
                    params.append(now - timedelta(days=days))
                await cur.execute(query, params)
                return await cur.fetchone()
            turnover_7d_data = await get_turnover_and_count(7)
            turnover_30d_data = await get_turnover_and_count(30)
            turnover_all_data = await get_turnover_and_count()
            await cur.execute("SELECT COALESCE(SUM(balance), 0) as total FROM users")
            total_supply = (await cur.fetchone())['total']
            await cur.execute("SELECT balance FROM users WHERE id = 0")
            fund_balance = (await cur.fetchone())['balance']
            response = f"""
📊 <b>Экономика сообщества:</b>

💱 <b>Оборот (переводы между пользователями):</b>
• За 7 дней: {format_amount(turnover_7d_data['turnover'])} {CURRENCY_SYMBOL} ({turnover_7d_data['tx_count']} транзакций)
• За 30 дней: {format_amount(turnover_30d_data['turnover'])} {CURRENCY_SYMBOL} ({turnover_30d_data['tx_count']} транзакций)
• За все время: {format_amount(turnover_all_data['turnover'])} {CURRENCY_SYMBOL} ({turnover_all_data['tx_count']} транзакций)

💰 <b>Денежная масса:</b>
• Всего в системе: {format_amount(total_supply)} {CURRENCY_SYMBOL}
• В фонде сообщества: {format_amount(fund_balance)} {CURRENCY_SYMBOL}
"""
            await message.answer(response, parse_mode="HTML")
