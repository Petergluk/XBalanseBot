# XBalanseBot/app/handlers/admin_commands.py
# v1.9.2
# 2025-08-27 17:00:00
"""
Модуль с обработчиками команд, доступных только администраторам.
Этот файл расширяет функционал, добавляя обработчики для кнопок,
интегрированных в пользовательские интерфейсы.

Версия 1.9.2:
- ИСПРАВЛЕНИЕ: В `process_create_event_for_activity` убран вызов `callback.answer()`.
  Это устраняет ошибку двойного ответа на callback, из-за которой не запускался
  диалог создания события. Ответ теперь делегирован вызываемой функции.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database import db
from app.utils import is_admin
from app.handlers import activity_handlers as act_handlers # Импортируем, чтобы вызывать FSM
from app.handlers import event_handlers as event_handlers # Импортируем, чтобы вызывать FSM

router = Router()
logger = logging.getLogger(__name__)


# Мидлварь для проверки прав администратора на все хендлеры в этом роутере
@router.callback_query.middleware()
async def admin_middleware(handler, event, data):
    if not await is_admin(data['event_from_user'].id):
        await event.answer("❌ У вас нет прав для этого действия.", show_alert=True)
        return
    return await handler(event, data)


@router.callback_query(F.data == "admin_create_activity")
async def process_create_activity(callback: CallbackQuery, state: FSMContext):
    """Запускает FSM для создания новой активности."""
    await callback.answer("Запускаем процесс создания активности...")
    # ИСПРАВЛЕНИЕ: Вызываем новую функцию, которая только запускает FSM без проверки прав.
    # Права уже проверены в middleware этого роутера.
    await act_handlers.start_activity_creation(callback.message, state)


@router.callback_query(F.data.startswith("admin_create_event_for_"))
async def process_create_event_for_activity(callback: CallbackQuery, state: FSMContext):
    """Запускает FSM для создания события для конкретной активности."""
    activity_id = int(callback.data.split("_")[4])
    # ИСПРАВЛЕНИЕ: Убираем этот ответ, чтобы избежать двойного ответа на callback.
    # Ответ будет дан в вызываемой функции.
    # await callback.answer(f"Создаем событие для активности #{activity_id}...")
    
    # Модифицируем callback.data, чтобы его понял существующий хендлер
    callback.data = f"create_event_for_{activity_id}"
    await event_handlers.start_event_creation_from_activity(callback, state)


@router.callback_query(F.data.startswith("admin_list_subscribers_"))
async def process_list_subscribers(callback: CallbackQuery):
    """Показывает список подписчиков для конкретной активности."""
    activity_id = int(callback.data.split("_")[3])

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

    # Редактируем текущее сообщение, добавляя список и сохраняя кнопку "Назад"
    keyboard = callback.message.reply_markup
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer(f"Найдено {len(subscribers)} подписчиков.")
