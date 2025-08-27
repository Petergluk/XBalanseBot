# XBalanseBot/app/handlers/activity_handlers.py
# v2.1.0
# 2025-08-27 16:33:00
"""
Модуль для управления активностями и событиями (единый пользовательский интерфейс).

Версия 2.1.0:
- ИСПРАВЛЕНИЕ: Функция `cmd_create_activity` была разделена на две:
  `cmd_create_activity` (обработчик команды с проверкой прав) и `start_activity_creation`
  (публичная функция для запуска FSM). Это устраняет ошибку с правами доступа
  при вызове из callback-обработчика в `admin_commands.py`.
- ИЗМЕНЕНИЕ: В `show_activities_list` и `process_activity_selection` добавлена
  проверка `is_admin` и передача этого флага в функции генерации клавиатур.
"""
import logging
from datetime import datetime, date
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from app.keyboards import (
    get_activities_keyboard, confirm_delete_keyboard, get_activity_view_keyboard,
    get_event_view_keyboard
)
from app.states import ActivityCreationStates, ActivityEditStates
from app.database import db
from app.utils import is_admin, format_amount, get_next_run_time
from app.config import CURRENCY_SYMBOL

router = Router()
logger = logging.getLogger(__name__)

weekdays_map = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
MSK_LABEL = "MSK"


# --- REUSABLE FUNCTION TO SHOW ACTIVITY LIST ---

async def show_activities_list(target: Message | CallbackQuery):
    """
    Универсальная функция для отображения списка активностей.
    Корректно обрабатывает и сообщения, и колбэки.
    """
    user_id = target.from_user.id
    user_is_admin = await is_admin(user_id)

    activities = await db.get_all_activities()
    user_subscriptions = await db.get_user_subscriptions(user_id)
    user_subscriptions_ids = {sub['activity_id'] for sub in user_subscriptions}

    explanation_text = (
        "<b>🎨 Активности сообщества</b>\n\n"
        "«Активность» — это направление (курс, клуб), которое содержит одно или несколько событий.\n\n"
        "✅ - вы подписаны на все события\n"
        "🧘‍♀️ и др. - вы не подписаны\n\n"
        "Выберите направление, чтобы увидеть список событий и записаться:"
    )

    if not activities:
        explanation_text = "На данный момент нет ни одной доступной активности."

    keyboard = await get_activities_keyboard(activities, user_subscriptions_ids, user_is_admin, action="view_cat")

    if isinstance(target, Message):
        await target.answer(explanation_text, reply_markup=keyboard, parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(explanation_text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest:
            pass
        await target.answer()

# --- USER FLOW ---

@router.message(Command("activity", "activities", "afisha", ignore_case=True))
async def cmd_activity(message: Message):
    """Шаг 1: Показывает список всех активностей (категорий)."""
    await show_activities_list(message)

@router.callback_query(F.data == "back_to_activities")
async def back_to_activities_list(callback: CallbackQuery):
    """Возвращает пользователя к списку активностей (Шаг 1)."""
    await show_activities_list(callback)

@router.callback_query(F.data.startswith("view_activity_"))
async def process_activity_selection(callback: CallbackQuery):
    """
    Шаг 2: Показывает детали активности и список ее событий в виде кнопок.
    """
    activity_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    user_is_admin = await is_admin(user_id)

    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Активность не найдена.", show_alert=True)
        return

    events = await db.get_events_for_activity(activity_id)
    is_subscribed = await db.is_user_subscribed(user_id, activity_id)

    text = f"<b>{activity['name']}</b>\n\n{activity['description'] or 'Нет описания.'}\n\n<b>События:</b>"
    if not events:
        text += "\n\n<i>В этом направлении пока нет запланированных событий.</i>"

    keyboard = await get_activity_view_keyboard(activity['name'], activity_id, events, is_subscribed, user_is_admin)

    try:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        logger.warning(f"Message not modified on activity selection: {e}")
    finally:
        await callback.answer()


@router.callback_query(F.data.startswith("view_event_"))
async def process_event_selection(callback: CallbackQuery):
    """
    Шаг 3: Показывает детали конкретного события и кнопки управления регистрацией.
    """
    event_id = int(callback.data.split("_")[2])
    user_telegram_id = callback.from_user.id

    event = await db.get_event(event_id)
    if not event:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    next_run_dt = get_next_run_time(
        event['event_type'], event.get('event_date'), event.get('weekday'),
        event.get('event_time'), event.get('last_run')
    )

    if not next_run_dt:
        await callback.message.edit_text(
            "У этого события нет запланированных запусков в будущем.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Назад к активности", callback_data=f"view_activity_{event['activity_id']}")
            ]])
        )
        await callback.answer()
        return

    next_run_date = next_run_dt.date()

    event_name = event['name'] or event['activity_name']
    event_description = event['description'] or event['activity_description']

    schedule_str = "Не определено"
    if event['event_type'] == 'single' and event['event_date']:
        schedule_str = f"📅 Дата: {event['event_date'].strftime('%d.%m.%Y в %H:%M')} ({MSK_LABEL})"
    elif event['event_type'] == 'recurring' and event['weekday'] is not None and event['event_time'] is not None:
        schedule_str = f"📅 Регулярность: каждый {weekdays_map[event['weekday']]} в {event['event_time'].strftime('%H:%M')} ({MSK_LABEL})\n"
        schedule_str += f"🗓️ Следующее занятие: {next_run_dt.strftime('%d.%m.%Y')}"

    text_parts = [
        f"<b>{event_name}</b>\n",
        f"<i>{event_description}</i>\n",
        f"{schedule_str}",
        f"💰 Стоимость: {format_amount(event['cost'])} {CURRENCY_SYMBOL}\n"
    ]

    keyboard = None
    if not event['allow_manual_registration']:
        text_parts.append("<i>Для участия в этом событии необходимо подписаться на всю активность.</i>")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="⬅️ Назад к активности", callback_data=f"view_activity_{event['activity_id']}")
        ]])
    else:
        is_subscribed_globally = await db.is_user_subscribed(user_telegram_id, event['activity_id'])
        override = await db.get_user_event_override(user_telegram_id, event_id, next_run_date)

        status = "unregistered"
        if override:
            if override['status'] == 'registered':
                status = "registered_manual"
            elif override['status'] == 'unregistered':
                status = "cancelled_auto"
        elif is_subscribed_globally:
            status = "registered_auto"

        keyboard = get_event_view_keyboard(event_id, event['activity_id'], next_run_date, status)

    try:
        await callback.message.edit_text("\n".join(text_parts), reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        logger.warning(f"Message not modified on event selection: {e}")
    finally:
        await callback.answer()

@router.callback_query(F.data.startswith(("subscribe_act_", "unsubscribe_act_")))
async def process_activity_subscription(callback: CallbackQuery):
    """Обрабатывает подписку/отписку от всей активности."""
    parts = callback.data.split("_")
    action = parts[0]
    activity_id = int(parts[2])
    user_id = callback.from_user.id

    if action == "subscribe":
        await db.add_subscription(user_id, activity_id)
        await callback.answer("✅ Вы подписались на все события этой активности!", show_alert=True)
    else: # action == "unsubscribe"
        await db.remove_subscription(user_id, activity_id)
        await callback.answer("✅ Вы отписались от этой активности.", show_alert=True)

    await process_activity_selection(callback)

@router.callback_query(F.data.startswith(("register_reg_", "cancel_reg_")))
async def process_manual_registration(callback: CallbackQuery):
    """Обрабатывает разовую регистрацию или отмену."""
    parts = callback.data.split("_")
    action = parts[0]
    event_id = int(parts[2])
    event_date = date.fromisoformat(parts[3])
    user_telegram_id = callback.from_user.id

    event = await db.get_event(event_id)
    if not event:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    if action == "register":
        is_subscribed = await db.is_user_subscribed(user_telegram_id, event['activity_id'])
        override = await db.get_user_event_override(user_telegram_id, event_id, event_date)

        if is_subscribed and override and override['status'] == 'unregistered':
            await db.remove_event_override(user_telegram_id, event_id, event_date)
        else:
            await db.set_event_override(user_telegram_id, event_id, event_date, 'registered')
        await callback.answer("✅ Вы записаны на это событие!", show_alert=True)

    else: # action == "cancel"
        is_subscribed = await db.is_user_subscribed(user_telegram_id, event['activity_id'])
        if is_subscribed:
            await db.set_event_override(user_telegram_id, event_id, event_date, 'unregistered')
        else:
            await db.remove_event_override(user_telegram_id, event_id, event_date)
        await callback.answer("✅ Ваша запись на это событие отменена.", show_alert=True)

    await process_event_selection(callback)


# --- ADMIN FLOW ---

async def start_activity_creation(message: Message, state: FSMContext):
    """
    Запускает FSM-диалог для создания активности.
    Эта функция не содержит проверки прав и может быть вызвана из разных обработчиков.
    """
    await state.set_state(ActivityCreationStates.waiting_for_name)
    await message.answer("Введите название новой активности:\n\n*Для отмены введите /cancel*", parse_mode="Markdown")

@router.message(Command("create_act", ignore_case=True))
async def cmd_create_activity(message: Message, state: FSMContext):
    """Обработчик команды /create_act. Проверяет права и запускает FSM."""
    if not await is_admin(message.from_user.id):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return
    await start_activity_creation(message, state)

@router.message(ActivityCreationStates.waiting_for_name)
async def process_activity_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ActivityCreationStates.waiting_for_description)
    await message.answer("Отлично! Теперь введите описание активности:\n\n*Для отмены введите /cancel*", parse_mode="Markdown")

@router.message(ActivityCreationStates.waiting_for_description)
async def process_activity_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await state.set_state(ActivityCreationStates.waiting_for_end_date)
    await message.answer("Теперь введите дату окончания активности в формате ДД.ММ.ГГГГ или напишите 'нет', если она бессрочная.\n\n*Для отмены введите /cancel*", parse_mode="Markdown")

@router.message(ActivityCreationStates.waiting_for_end_date)
async def process_activity_end_date(message: Message, state: FSMContext):
    end_date_str = message.text.lower()
    end_date = None
    if end_date_str != 'нет':
        try:
            end_date = datetime.strptime(end_date_str, "%d.%m.%Y").date()
        except ValueError:
            await message.reply("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ или 'нет'.\n\n*Для отмены введите /cancel*", parse_mode="Markdown")
            return

    data = await state.get_data()
    try:
        activity_id = await db.create_activity(data['name'], data['description'], end_date)
        await state.clear()

        logger.info(f"Admin {message.from_user.id} created new activity {activity_id}: {data['name']}")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Создать событие для этой активности", callback_data=f"create_event_for_{activity_id}")]
        ])
        await message.answer(f"✅ Новая активность '{data['name']}' успешно создана!", reply_markup=keyboard)
    except Exception:
        await message.reply(f"❌ Активность с названием '{data['name']}' уже существует. Пожалуйста, выберите другое название или отмените операцию (/cancel).")
        await state.set_state(ActivityCreationStates.waiting_for_name)
        await message.answer("Введите название новой активности:")

@router.message(Command("edit_act", ignore_case=True))
async def cmd_edit_activity(message: Message):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    activities = await db.get_all_activities()
    if not activities:
        await message.answer("Нет активностей для редактирования.")
        return

    user_subscriptions = await db.get_user_subscriptions(message.from_user.id)
    user_subscriptions_ids = {s['activity_id'] for s in user_subscriptions}
    keyboard = await get_activities_keyboard(activities, user_subscriptions_ids, True, action="edit")
    await message.answer("Выберите активность для редактирования:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("edit_activity_"))
async def process_edit_activity_selection(callback: CallbackQuery, state: FSMContext):
    activity_id = int(callback.data.split("_")[2])
    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Активность не найдена.", show_alert=True)
        return

    await state.update_data(activity_id=activity_id)

    info_text = (
        f"<b>Редактирование активности:</b>\n"
        f"<b>Название:</b> {activity['name']}\n"
        f"<b>Описание:</b> {activity['description'][:100]}...\n"
        f"<b>Дата окончания:</b> {activity['end_date'] or 'Бессрочная'}\n\n"
        f"Что вы хотите изменить?"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Название", callback_data="edit_field_name")],
        [InlineKeyboardButton(text="Описание", callback_data="edit_field_desc")],
        [InlineKeyboardButton(text="Дату окончания", callback_data="edit_field_date")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_edit_list")]
    ])
    await callback.message.edit_text(info_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "back_to_edit_list")
async def back_to_edit_list(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    activities = await db.get_all_activities()
    user_subscriptions = await db.get_user_subscriptions(callback.from_user.id)
    user_subscriptions_ids = {s['activity_id'] for s in user_subscriptions}
    keyboard = await get_activities_keyboard(activities, user_subscriptions_ids, True, action="edit")
    await callback.message.edit_text("Выберите активность для редактирования:", reply_markup=keyboard)
    await callback.answer()

@router.callback_query(F.data.startswith("edit_field_"))
async def process_edit_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.split("_")[2]
    data = await state.get_data()
    activity_id = data.get('activity_id')

    if not activity_id:
        await callback.answer("Ошибка: ID активности не найден. Пожалуйста, начните заново.", show_alert=True)
        await state.clear()
        return

    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Ошибка: Активность не найдена.", show_alert=True)
        await state.clear()
        return

    prompts = {
        "name": (f"Текущее название: `{activity['name']}`\nВведите новое:", ActivityEditStates.waiting_for_new_name),
        "desc": (f"Текущее описание: `{activity['description']}`\nВведите новое:", ActivityEditStates.waiting_for_new_description),
        "date": (f"Текущая дата окончания: `{activity['end_date'] or 'нет'}`\nВведите новую (ДД.ММ.ГГГГ или 'нет'):", ActivityEditStates.waiting_for_new_end_date)
    }

    prompt_text, new_state = prompts[field]
    await state.set_state(new_state)
    await callback.message.edit_text(f"{prompt_text}\n\n*Для отмены введите /cancel*", parse_mode="Markdown")
    await callback.answer()

@router.message(ActivityEditStates.waiting_for_new_name)
async def update_activity_name(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.update_activity(data['activity_id'], name=message.text)
    await message.answer("✅ Название активности обновлено.")
    await state.clear()

@router.message(ActivityEditStates.waiting_for_new_description)
async def update_activity_description(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.update_activity(data['activity_id'], description=message.text)
    await message.answer("✅ Описание активности обновлено.")
    await state.clear()

@router.message(ActivityEditStates.waiting_for_new_end_date)
async def update_activity_end_date(message: Message, state: FSMContext):
    data = await state.get_data()
    end_date_str = message.text.lower()
    end_date = None
    if end_date_str != 'нет':
        try:
            end_date = datetime.strptime(end_date_str, "%d.%m.%Y").date()
        except ValueError:
            await message.reply("❌ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ или 'нет'.\n\n*Для отмены введите /cancel*", parse_mode="Markdown")
            return

    if 'activity_id' in data:
        await db.update_activity(data['activity_id'], end_date=end_date)
        await message.answer("✅ Дата окончания активности обновлена.")
    else:
        await message.answer("❌ Произошла ошибка. Не удалось найти ID активности для обновления.")

    await state.clear()

@router.message(Command("delete_act", ignore_case=True))
async def cmd_delete_activity(message: Message):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return
    all_activities = await db.get_all_activities()
    activities = [act for act in all_activities if act['id'] != 1]
    if not activities:
        await message.answer("Нет активностей для удаления.")
        return

    user_subscriptions = await db.get_user_subscriptions(message.from_user.id)
    user_subscriptions_ids = {s['activity_id'] for s in user_subscriptions}
    keyboard = await get_activities_keyboard(activities, user_subscriptions_ids, True, action="delete")
    await message.answer("Выберите активность для удаления:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("delete_activity_"))
async def process_delete_confirmation(callback: CallbackQuery):
    activity_id = int(callback.data.split("_")[2])
    if activity_id == 1:
        await callback.answer("Эту активность нельзя удалить.", show_alert=True)
        return

    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Активность не найдена.", show_alert=True)
        return

    await callback.message.edit_text(
        f"Вы уверены, что хотите удалить активность '{activity['name']}'?\n"
        "<b>Это действие необратимо и удалит все связанные подписки и события!</b>",
        reply_markup=confirm_delete_keyboard(f"confirm_delete_activity_{activity_id}"),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_delete_activity_"))
async def process_delete_activity(callback: CallbackQuery):
    activity_id = int(callback.data.split("_")[3])
    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Активность уже удалена.", show_alert=True)
        return

    await db.delete_activity(activity_id)
    logger.warning(f"Admin {callback.from_user.id} deleted activity {activity_id}: {activity['name']}")
    await callback.message.edit_text(f"✅ Активность '{activity['name']}' была удалена.")
    await callback.answer()
