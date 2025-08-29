# XBalanseBot/app/handlers/admin_commands.py
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
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, User
from psycopg.rows import dict_row

from app.config import (CURRENCY_SYMBOL, DEFAULT_GIDE_TEXT, DEFAULT_REMINDER_TEXT,
                        DEFAULT_TEST_COMMANDS_TEXT)
from app.database import db
from app.handlers import activity_handlers as act_handlers
from app.handlers import event_handlers as event_handlers
from app.keyboards import (get_back_to_settings_keyboard, get_settings_keyboard)
from app.states import AdminEditStates
from app.utils import (format_amount, format_transactions_history, is_admin)
from app.callbacks import (
    GeneralAction, ActivityAction, EventCreationAction, SettingsAction
)

router = Router()
logger = logging.getLogger(__name__)


# --- MIDDLEWARES ---

@router.message.middleware()
async def admin_message_middleware(handler, event: Message, data):
    if not await is_admin(data['event_from_user'].id):
        await event.reply("❌ У вас нет прав для выполнения этой команды.")
        return
    return await handler(event, data)


@router.callback_query.middleware()
async def admin_callback_middleware(handler, event: CallbackQuery, data):
    if not await is_admin(data['event_from_user'].id):
        await event.answer("❌ У вас нет прав для этого действия.", show_alert=True)
        return
    return await handler(event, data)


# --- HELPERS ---

async def _parse_user_amount_comment(message: Message) -> tuple | None:
    args = message.text.split()
    if len(args) < 3:
        await message.reply(f"❌ Неверный формат. Используйте:\n`{args[0]} @username сумма [комментарий]`")
        return None
    username = args[1].lstrip('@').lower()
    try:
        amount = Decimal(args[2].replace(',', '.'))
        if amount <= 0: raise ValueError
    except (InvalidOperation, ValueError):
        await message.reply("❌ Неверная сумма. Укажите положительное число.")
        return None
    comment = ' '.join(args[3:]) if len(args) > 3 else "Административная операция"
    user = await db.get_user(username=username)
    if not user:
        await message.reply(f"❌ Пользователь @{username} не найден.")
        return None
    return user, amount, comment


async def _change_balance(
    bot: Bot, admin_user: User, target_user: dict, amount: Decimal,
    comment: str, transaction_type: str
):
    try:
        async with db.pool.connection() as conn:
            async with conn.transaction():
                from_user_id = 0 if transaction_type == 'manual_add' else target_user['id']
                to_user_id = target_user['id'] if transaction_type == 'manual_add' else 0
                await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount, target_user['id']))
                await conn.execute("INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, %s, %s)", (from_user_id, to_user_id, abs(amount), transaction_type, comment))
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id = %s", (target_user['id'],))
        action_word = "Начислено" if amount > 0 else "Списано"
        preposition = "на" if amount > 0 else "с"
        logger.info(f"Admin {admin_user.id} performed '{transaction_type}' for user {target_user['telegram_id']} ({target_user['username']}). Amount: {amount}, Comment: {comment}")
        await bot.send_message(admin_user.id, f"✅ {action_word} <b>{format_amount(abs(amount))} {CURRENCY_SYMBOL}</b> {preposition} счет пользователя @{target_user['username']}.")
        try:
            await bot.send_message(target_user['telegram_id'], f"ℹ️ Администратор @{admin_user.username} выполнил операцию с вашим счетом.\n<b>{action_word}:</b> {format_amount(abs(amount))} {CURRENCY_SYMBOL}\n<b>Комментарий:</b> {comment}")
        except Exception as e:
            logger.warning(f"Could not send notification to user {target_user['telegram_id']}: {e}")
    except Exception as e:
        logger.error(f"Failed to change balance for user {target_user['telegram_id']}: {e}", exc_info=True)
        await bot.send_message(admin_user.id, "❌ Произошла ошибка при выполнении операции.")


# --- INFO & USER MANAGEMENT COMMANDS ---

@router.message(Command("gide", "гид", ignore_case=True))
async def cmd_gide(message: Message):
    gide_text = DEFAULT_GIDE_TEXT.format(currency_symbol=CURRENCY_SYMBOL)
    await message.answer(gide_text, parse_mode="HTML")

@router.message(Command("test", ignore_case=True))
async def cmd_test(message: Message):
    await message.answer(DEFAULT_TEST_COMMANDS_TEXT, parse_mode="HTML")

@router.message(Command("users", ignore_case=True))
async def cmd_users(message: Message):
    users = await db.get_all_users()
    if not users:
        await message.answer("В системе пока нет пользователей.")
        return
    page_size = 20
    total_users = len(users)
    response_parts = [f"👥 <b>Всего пользователей: {total_users}</b>\n\n"]
    for i, user in enumerate(users[:page_size]):
        admin_mark = "👮" if user['is_admin'] else ""
        username_str = f"@{user['username']}" if user['username'] else f"ID:{user['telegram_id']}"
        created_date = user['created_at'].strftime('%d.%m.%Y')
        response_parts.append(f"{i+1}. {admin_mark}{username_str}\n   💰 {format_amount(user['balance'])} {CURRENCY_SYMBOL} | 📊 {user['transaction_count']} тр. | 📅 {created_date}\n")
    if total_users > page_size:
        response_parts.append(f"\n<i>Показаны первые {page_size} из {total_users} пользователей</i>")
    await message.answer("".join(response_parts), parse_mode="HTML")

@router.message(Command("check", ignore_case=True))
async def cmd_check(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("❌ Укажите @username пользователя для проверки.")
        return
    username = args[1].lstrip('@').lower()
    user = await db.get_user(username=username)
    if not user:
        await message.reply(f"❌ Пользователь @{username} не найден.")
        return
    async with db.pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("SELECT t.*, sender.username as sender_username, recipient.username as recipient_username FROM transactions t LEFT JOIN users sender ON t.from_user_id = sender.id LEFT JOIN users recipient ON t.to_user_id = recipient.id WHERE (t.to_user_id = %s OR t.from_user_id = %s) ORDER BY t.created_at DESC LIMIT 10", (user['id'], user['id']))
            transactions = await cur.fetchall()
    history_text = "<i>Нет транзакций</i>"
    if transactions:
        history_text = format_transactions_history(transactions, user['id'])
    response = (f"👤 <b>Информация о пользователе @{user['username']}</b>\n\n"
                f"<b>Telegram ID:</b> <code>{user['telegram_id']}</code>\n"
                f"<b>Баланс:</b> {format_amount(user['balance'])} {CURRENCY_SYMBOL}\n"
                f"<b>Админ:</b> {'Да' if user['is_admin'] else 'Нет'}\n"
                f"<b>Всего транзакций:</b> {user['transaction_count']}\n\n"
                f"<b>Последние 10 транзакций:</b>\n{history_text}")
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
        await message.reply(f"❌ Формат: {args[0]} @username")
        return
    username = args[1].lstrip('@').lower()
    user = await db.get_user(username=username)
    if not user:
        await message.reply(f"❌ Пользователь @{username} не найден.")
        return
    if user['is_admin'] == make_admin:
        status = "уже является" if make_admin else "не является"
        await message.reply(f"✅ Пользователь @{username} {status} администратором.")
        return
    await db.set_admin_status(user['telegram_id'], is_admin=make_admin)
    action = "назначен" if make_admin else "сняты права"
    await message.answer(f"✅ Пользователь @{username} {action} администратором.")

@router.message(Command("make_admin", ignore_case=True))
async def cmd_make_admin(message: Message):
    await _toggle_admin(message, make_admin=True)

@router.message(Command("remove_admin", ignore_case=True))
async def cmd_remove_admin(message: Message):
    await _toggle_admin(message, make_admin=False)

# --- SETTINGS MANAGEMENT ---

@router.message(Command("settings", ignore_case=True))
async def cmd_settings(message: Message):
    demurrage_enabled = await db.get_setting('demurrage_enabled', '0') == '1'
    keyboard = await get_settings_keyboard(demurrage_enabled)
    await message.answer("⚙️ <b>Меню настроек системы</b>", reply_markup=keyboard)

@router.callback_query(SettingsAction.filter())
async def process_settings_callbacks(callback: CallbackQuery, state: FSMContext, callback_data: SettingsAction):
    action = callback_data.action
    prompts = {
        "set_welcome_bonus": ("Введите новую сумму welcome-бонуса:", AdminEditStates.waiting_for_welcome_bonus),
        "set_exchange_rate": ("Введите новый курс обмена (например, 1.0):", AdminEditStates.waiting_for_exchange_rate),
        "set_demurrage_rate": ("Введите новый процент демерреджа (например, 0.01 для 1%):", AdminEditStates.waiting_for_demurrage_rate),
        "edit_welcome_bot": ("Введите новый текст приветствия для бота:", AdminEditStates.waiting_for_welcome_text),
        "edit_welcome_group": ("Введите новый текст приветствия для группы:", AdminEditStates.waiting_for_welcome_text_group),
        "edit_reminder": (f"Введите новый шаблон напоминания:\n\nТекущий: `{await db.get_setting('default_reminder_text', DEFAULT_REMINDER_TEXT)}`", AdminEditStates.waiting_for_reminder_text)
    }
    if action in prompts:
        prompt_text, new_state = prompts[action]
        await state.set_state(new_state)
        await callback.message.edit_text(f"{prompt_text}\n\nДля отмены введите /cancel")
        await callback.answer()
    elif action == "toggle_demurrage":
        is_on = callback_data.enabled
        await db.set_setting('demurrage_enabled', '1' if is_on else '0')
        new_keyboard = await get_settings_keyboard(is_on)
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        await callback.answer(f"Демерредж {'ВКЛЮЧЕН' if is_on else 'ВЫКЛЮЧЕН'}")
    elif action == "demurrage_status":
        enabled = "Включен" if await db.get_setting('demurrage_enabled') == '1' else "Выключен"
        rate = float(await db.get_setting('demurrage_rate')) * 100
        interval = await db.get_setting('demurrage_interval_days')
        last_run = await db.get_setting('demurrage_last_run')
        status_text = (f"📊 <b>Статус демерреджа</b>\n\n<b>Состояние:</b> {enabled}\n<b>Процент:</b> {rate}%\n<b>Интервал:</b> {interval} день/дней\n<b>Последний запуск:</b> {last_run}")
        await callback.message.edit_text(status_text, reply_markup=get_back_to_settings_keyboard())
        await callback.answer()
    elif action == "back_to_settings":
        demurrage_enabled = await db.get_setting('demurrage_enabled', '0') == '1'
        keyboard = await get_settings_keyboard(demurrage_enabled)
        await callback.message.edit_text("⚙️ <b>Меню настроек системы</b>", reply_markup=keyboard)
        await callback.answer()

async def _update_setting_and_finish(message: Message, state: FSMContext, key: str, value_transformer=str):
    try:
        value = value_transformer(message.text)
        await db.set_setting(key, str(value))
        await message.answer("✅ Настройка успешно обновлена.")
        await state.clear()
        await cmd_settings(message)
    except (ValueError, InvalidOperation):
        await message.reply("❌ Неверный формат. Попробуйте еще раз.")

@router.message(AdminEditStates.waiting_for_welcome_bonus)
async def process_welcome_bonus(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'welcome_bonus_amount', Decimal)
@router.message(AdminEditStates.waiting_for_exchange_rate)
async def process_exchange_rate(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'exchange_rate', Decimal)
@router.message(AdminEditStates.waiting_for_demurrage_rate)
async def process_demurrage_rate(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'demurrage_rate', Decimal)
@router.message(AdminEditStates.waiting_for_welcome_text)
async def process_welcome_text(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'welcome_message_bot')
@router.message(AdminEditStates.waiting_for_welcome_text_group)
async def process_welcome_text_group(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'welcome_message_group')
@router.message(AdminEditStates.waiting_for_reminder_text)
async def process_reminder_text(message: Message, state: FSMContext):
    await _update_setting_and_finish(message, state, 'default_reminder_text')

# --- ACTIVITY/EVENT MANAGEMENT CALLBACKS ---

@router.callback_query(GeneralAction.filter(F.action == "admin_create_activity"))
async def process_create_activity(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Запускаем процесс создания активности...")
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
        await callback.answer("Активность не найдена.", show_alert=True)
        return
    subscribers = await db.get_activity_subscribers(activity_id)
    text_parts = [f"<b>Подписчики активности «{activity['name']}»:</b>\n"]
    if not subscribers:
        text_parts.append("\n<i>На эту активность пока никто не подписан.</i>")
    else:
        for i, user in enumerate(subscribers, 1):
            username = f"@{user['username']}" if user['username'] else f"ID:{user['telegram_id']}"
            text_parts.append(f"\n{i}. {username}")
    text = "".join(text_parts)
    keyboard = callback.message.reply_markup
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer(f"Найдено {len(subscribers)} подписчиков.")
