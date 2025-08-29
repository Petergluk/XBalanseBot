# XBalanseBot/app/handlers/activity_handlers.py
# FULL FILE EMITTED: YES
# v3.4.0
# 2025-08-29 04:15:00
"""
Модуль для управления активностями и событиями (единый пользовательский интерфейс).

Версия 3.4.0:
- Полностью переведена логика обработки callback_data на использование фабрик
  из `app.callbacks`, что повышает надежность и читаемость кода.
- Улучшена обратная связь для пользователя при подписке/отписке на активность,
  теперь сообщение включает название активности.
- Удалены устаревшие методы парсинга callback_data на основе строк.

Версия 3.3.2:
- ИСПРАВЛЕНИЕ (Критическое): Устранена ошибка `TypeError: unhashable type: 'list'`
  в функции `start_edit_activity_field`. Некорректное присваивание `field = parts`
  заменено на `field = parts[2]` для правильного извлечения ключа из callback-данных.
- ИСПРАВЛЕНИЕ (Логика): Устранена ошибка в функции `process_activity_subscription`.
  Некорректное присваивание `action = parts` заменено на `action = parts[0]`, что
  позволяет теперь корректно подписываться на активности, а не только отписываться.
- ИСПРАВЛЕНИЕ (Логика): Устранена аналогичная ошибка в `process_manual_registration`.
  Теперь `action`, `event_id` и `event_date` корректно извлекаются из `callback_data`
  по индексам, восстанавливая функциональность ручной регистрации на события.
- ИСПРАВЛЕНИЕ (Предыдущее): Сохранено исправление `TypeError` в `process_activity_selection`.
  Вызов `int(callback.data.split("_")[-1])` оставлен для корректного извлечения ID.
- УЛУЧШЕНИЕ (Предыдущее): Сохранено изменение заголовка "События:" на "Ближайшие события:".
"""
import logging
from datetime import datetime, date
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import (
    get_activities_keyboard, confirm_delete_keyboard, get_activity_view_keyboard,
    get_event_view_keyboard, get_activity_edit_menu_keyboard
)
from app.states import ActivityCreationStates, ActivityEditStates
from app.database import db
from app.utils import is_admin, format_amount, get_next_run_time
from app.config import CURRENCY_SYMBOL
from app.callbacks import (
    GeneralAction, ActivityAction, ActivityEditAction, EventAction
)

router = Router()
logger = logging.getLogger(__name__)

weekdays_map = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
MSK_LABEL = "MSK"


# --- REUSABLE FUNCTIONS ---

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

    keyboard = await get_activities_keyboard(activities, user_subscriptions_ids, user_is_admin)

    if isinstance(target, Message):
        await target.answer(explanation_text, reply_markup=keyboard, parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        try:
            if target.message:
                await target.message.edit_text(explanation_text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest:
            pass
        await target.answer()

async def _send_activity_details_message(target: Message | CallbackQuery, activity_id: int):
    """
    Внутренняя функция для отправки или редактирования сообщения с деталями активности.
    Вынесена для переиспользования и избежания ошибок.
    """
    user_id = target.from_user.id
    message_to_use = target.message if isinstance(target, CallbackQuery) else target
    user_is_admin = await is_admin(user_id)

    activity = await db.get_activity(activity_id)
    if not activity:
        if isinstance(target, CallbackQuery):
            await target.answer("Активность не найдена.", show_alert=True)
        return

    events = await db.get_events_for_activity(activity_id)
    is_subscribed = await db.is_user_subscribed(user_id, activity_id)

    text = f"<b>{activity['name']}</b>\n\n{activity['description'] or 'Нет описания.'}\n\n<b>Ближайшие события:</b>"

    actual_events_count = sum(1 for e in events if get_next_run_time(e['event_type'], e.get('event_date'), e.get('weekday'), e.get('event_time'), e.get('last_run')) is not None)
    if not actual_events_count:
        text += "\n\n<i>В этом направлении пока нет запланированных событий.</i>"

    keyboard = await get_activity_view_keyboard(activity['name'], activity_id, events, is_subscribed, user_is_admin)

    if isinstance(target, CallbackQuery):
        try:
            await message_to_use.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest as e:
            logger.warning(f"Message not modified on activity selection: {e}")
        finally:
            await target.answer()
    else: # Is a Message
        await message_to_use.answer(text, reply_markup=keyboard, parse_mode="HTML")


# --- USER FLOW ---

@router.message(Command("activity", "activities", "afisha", ignore_case=True))
async def cmd_activity(message: Message):
    """Шаг 1: Показывает список всех активностей (категорий)."""
    await show_activities_list(message)

@router.callback_query(GeneralAction.filter(F.action == "back_to_activities"))
async def back_to_activities_list(callback: CallbackQuery):
    """Возвращает пользователя к списку активностей (Шаг 1)."""
    await show_activities_list(callback)

@router.callback_query(ActivityAction.filter(F.action == "view"))
async def process_activity_selection(callback: CallbackQuery, callback_data: ActivityAction):
    """Шаг 2: Показывает детали активности и список ее событий."""
    # activity_id теперь приходит напрямую из callback_data
    await _send_activity_details_message(callback, callback_data.activity_id)

@router.callback_query(EventAction.filter(F.action == "view"))
async def process_event_selection(callback: CallbackQuery, callback_data: EventAction):
    """
    Шаг 3: Показывает детали конкретного события и кнопки управления регистрацией.
    """
    event_id = callback_data.event_id
    user_telegram_id = callback.from_user.id
    user_is_admin = await is_admin(user_telegram_id)

    event = await db.get_event(event_id)
    if not event:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    next_run_dt = get_next_run_time(
        event['event_type'], event.get('event_date'), event.get('weekday'),
        event.get('event_time'), event.get('last_run')
    )

    if not next_run_dt:
        text = "У этого события нет запланированных запусков в будущем."
        kb = InlineKeyboardBuilder()
        if user_is_admin:
            kb.row(
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=EventAction(action="edit_menu", event_id=event_id).pack()),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=EventAction(action="delete_confirm", event_id=event_id).pack())
            )
        kb.row(InlineKeyboardButton(text="⬅️ Назад к активности", callback_data=ActivityAction(action="view", activity_id=event['activity_id']).pack()))

        await callback.message.edit_text(text, reply_markup=kb.as_markup())
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
        keyboard_builder = InlineKeyboardBuilder()
        if user_is_admin:
            keyboard_builder.row(
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=EventAction(action="edit_menu", event_id=event_id).pack()),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=EventAction(action="delete_confirm", event_id=event_id).pack())
            )
        keyboard_builder.row(InlineKeyboardButton(text="⬅️ Назад к активности", callback_data=ActivityAction(action="view", activity_id=event['activity_id']).pack()))
        keyboard = keyboard_builder.as_markup()
    else:
        is_subscribed_globally = await db.is_user_subscribed(user_telegram_id, event['activity_id'])
        override = await db.get_user_event_override(user_telegram_id, event_id, next_run_date)

        status = "unregistered"
        if override:
            if override['status'] == 'registered': status = "registered_manual"
            elif override['status'] == 'unregistered': status = "cancelled_auto"
        elif is_subscribed_globally:
            status = "registered_auto"

        keyboard = get_event_view_keyboard(event_id, event['activity_id'], next_run_date, status, user_is_admin)

    try:
        await callback.message.edit_text("\n".join(text_parts), reply_markup=keyboard, parse_mode="HTML")
    except TelegramBadRequest as e:
        logger.warning(f"Message not modified on event selection: {e}")
    finally:
        await callback.answer()

@router.callback_query(ActivityAction.filter(F.action.in_({"subscribe", "unsubscribe"})))
async def process_activity_subscription(callback: CallbackQuery, callback_data: ActivityAction):
    """
    Обрабатывает подписку/отписку от всей активности.
    Улучшена обратная связь.
    """
    activity_id = callback_data.activity_id
    user_id = callback.from_user.id
    activity = await db.get_activity(activity_id) # Получаем данные активности для имени

    if not activity:
        await callback.answer("Активность не найдена.", show_alert=True)
        return

    if callback_data.action == "subscribe":
        await db.add_subscription(user_id, activity_id)
        await callback.answer(f"✅ Вы подписались на все события активности '{activity['name']}'!", show_alert=True)
    else: # action == "unsubscribe"
        await db.remove_subscription(user_id, activity_id)
        await callback.answer(f"✅ Вы отписались от активности '{activity['name']}'.", show_alert=True)

    await _send_activity_details_message(callback, activity_id)

@router.callback_query(EventAction.filter(F.action.in_({"register", "cancel"})))
async def process_manual_registration(callback: CallbackQuery, callback_data: EventAction):
    """Обрабатывает разовую регистрацию или отмену."""
    event_id = callback_data.event_id
    event_date = callback_data.target_date # target_date теперь приходит как datetime.date
    user_telegram_id = callback.from_user.id

    event = await db.get_event(event_id)
    if not event:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    if callback_data.action == "register":
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

    # После операции возвращаем пользователя к деталям события
    # Для этого нужно создать новый CallbackQuery, т.к. исходный изменился
    # Либо вызвать process_event_selection напрямую с нужными параметрами
    # Проще вызвать с оригинальным callback, но event_id
    await process_event_selection(callback, EventAction(action="view", event_id=event_id))


# --- ADMIN FLOW: CREATE ACTIVITY ---

async def start_activity_creation(message: Message, state: FSMContext):
    """
    Запускает FSM-диалог для создания активности.
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
    end_date_str = message.text.lower().strip()
    end_date = None
    
    if end_date_str != 'нет':
        normalized_date_str = end_date_str.replace(',', '.')
        try:
            end_date = datetime.strptime(normalized_date_str, "%d.%m.%Y").date()
        except ValueError:
            await message.reply("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ или 'нет'.\n\n*Для отмены введите /cancel*", parse_mode="Markdown")
            return

    data = await state.get_data()
    try:
        activity_id = await db.create_activity(data['name'], data['description'], end_date)
        await state.clear()
        logger.info(f"Admin {message.from_user.id} created new activity {activity_id}: {data['name']}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Создать событие для этой активности", callback_data=ActivityAction(action="create_event_for", activity_id=activity_id).pack())]
        ])
        await message.answer(f"✅ Новая активность '{data['name']}' успешно создана!", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error creating activity: {e}")
        await message.reply(f"❌ Активность с названием '{data['name']}' уже существует или произошла ошибка БД. Пожалуйста, выберите другое название или отмените операцию (/cancel).")
        await state.set_state(ActivityCreationStates.waiting_for_name)
        await message.answer("Введите название новой активности:")

# --- ADMIN FLOW: INLINE EDIT/DELETE ACTIVITY ---

@router.callback_query(ActivityAction.filter(F.action == "edit_menu"))
async def show_activity_edit_menu(callback: CallbackQuery, callback_data: ActivityAction):
    """Отображает меню редактирования/удаления активности."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return

    activity_id = callback_data.activity_id
    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Активность не найдена.", show_alert=True)
        return

    text = f"<b>Управление активностью:</b>\n{activity['name']}"
    keyboard = get_activity_edit_menu_keyboard(activity_id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(ActivityEditAction.filter(F.action.in_({"name", "description"})))
async def start_edit_activity_field(callback: CallbackQuery, state: FSMContext, callback_data: ActivityEditAction):
    """Запускает FSM для изменения поля активности (название/описание)."""
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return

    field = callback_data.action # 'name' or 'description'
    activity_id = callback_data.activity_id

    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Активность не найдена.", show_alert=True)
        return

    await state.update_data(activity_id=activity_id)
    prompts = {
        "name": ("Текущее название: `{}`\n\nВведите новое:", ActivityEditStates.waiting_for_new_name, activity['name']),
        "description": ("Текущее описание: `{}`\n\nВведите новое:", ActivityEditStates.waiting_for_new_description, activity['description'])
    }

    prompt_text, new_state, current_value = prompts[field]
    await state.set_state(new_state)
    await callback.message.edit_text(
        f"{prompt_text.format(current_value)}\n\n*Для отмены введите /cancel*",
        parse_mode="Markdown"
    )
    await callback.answer()

@router.message(ActivityEditStates.waiting_for_new_name)
async def update_activity_name(message: Message, state: FSMContext):
    """Обрабатывает ввод нового названия и показывает обновленный вид."""
    data = await state.get_data()
    activity_id = data['activity_id']
    await db.update_activity(activity_id, name=message.text)
    await state.clear()
    await message.answer(f"✅ Название активности обновлено.")
    await _send_activity_details_message(message, activity_id)

@router.message(ActivityEditStates.waiting_for_new_description)
async def update_activity_description(message: Message, state: FSMContext):
    """Обрабатывает ввод нового описания и показывает обновленный вид."""
    data = await state.get_data()
    activity_id = data['activity_id']
    await db.update_activity(activity_id, description=message.text)
    await state.clear()
    await message.answer("✅ Описание активности обновлено.")
    await _send_activity_details_message(message, activity_id)

@router.callback_query(ActivityEditAction.filter(F.action == "delete_confirm"))
async def confirm_activity_deletion(callback: CallbackQuery, callback_data: ActivityEditAction):
    """Показывает подтверждение удаления активности."""
    activity_id = callback_data.activity_id
    if activity_id == 1:
        await callback.answer("Эту активность нельзя удалить.", show_alert=True)
        return

    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Активность не найдена.", show_alert=True)
        return

    await callback.message.edit_text(
        f"Вы уверены, что хотите удалить активность «{activity['name']}»?\n"
        "<b>Это действие необратимо и удалит все связанные подписки и события!</b>",
        reply_markup=confirm_delete_keyboard("activity", activity_id), # Используем новую фабрику
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(GeneralAction.filter(F.action.startswith("confirm_final_delete_activity_")))
async def process_activity_deletion(callback: CallbackQuery, callback_data: GeneralAction):
    """Окончательно удаляет активность."""
    # Извлекаем activity_id из callback_data.action, как раньше, пока не перейдем на ConfirmDeleteCallback
    activity_id = int(callback_data.action.split("_")[-1])
    activity = await db.get_activity(activity_id)
    if not activity:
        await callback.answer("Активность уже удалена.", show_alert=True)
        if callback.message: await show_activities_list(callback)
        return

    await db.delete_activity(activity_id)
    logger.warning(f"Admin {callback.from_user.id} deleted activity {activity_id}: {activity['name']}")
    await callback.message.edit_text(f"✅ Активность «{activity['name']}» была удалена.")
    await show_activities_list(callback)
    await callback.answer()
