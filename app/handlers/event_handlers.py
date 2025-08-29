# XBalanseBot/app/handlers/event_handlers.py
# FULL FILE EMITTED: YES
# v2.4.0
# 2025-08-29 04:15:00
"""
Модуль для управления событиями.

Версия 2.4.0:
- Полностью переведена логика обработки callback_data на использование фабрик
  из `app.callbacks`, что повышает надежность и читаемость кода.
- Удалены устаревшие методы парсинга callback_data на основе строк.

Версия 2.3.0:
- УЛУЧШЕНИЕ (UX): Полностью переработан FSM-диалог создания события.
- Добавлен шаг предпросмотра и подтверждения перед сохранением.
- Текстовые команды ('.', 'нет') заменены на инлайн-кнопки.
- При запросе описания и напоминания теперь показываются значения по умолчанию.
- Реализована автоматическая очистка сообщений диалога после успешного создания.
- Внесены исправления в FSM для корректного редактирования и удаления сообщений.
- Исправлена ошибка TypeError при обработке callback-данных `create_event_for_`.
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from app.database import db
from app.keyboards import (
    get_events_keyboard, get_event_details_keyboard, confirm_delete_keyboard,
    get_activities_keyboard_for_event, get_event_edit_keyboard, get_weekday_keyboard,
    get_use_default_keyboard, get_event_creation_confirmation_keyboard
)
from app.states import EventCreationStates, EventEditStates
from app.utils import is_admin, format_amount, get_next_run_time
from app.config import CURRENCY_SYMBOL, DEFAULT_REMINDER_TEXT
from app.services.scheduler_jobs import schedule_event_jobs, remove_event_jobs
from app.callbacks import (
    GeneralAction, ActivityAction, EventAction, EventEditAction, EventCreationAction
)

router = Router()
logger = logging.getLogger(__name__)

weekdays_map = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
MSK_LABEL = "MSK"

REMINDER_VARIABLES_HELP_TEXT = """
<b>Доступные переменные:</b>
<code>{event_name}</code> - название события
<code>{event_description}</code> - описание события
<code>{start_date}</code> - дата события (ДД.ММ.ГГГГ)
<code>{start_time}</code> - время события (ЧЧ:ММ)
<code>{cost}</code> - стоимость участия
<code>{currency_symbol}</code> - символ валюты
<code>{reminder_minutes}</code> - за сколько минут напоминание
<code>{link}</code> - ссылка на событие
"""

# --- HELPERS ---

async def cleanup_creation_dialog(bot: Bot, chat_id: int, state: FSMContext):
    """Удаляет все сообщения, связанные с диалогом создания события."""
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    if message_ids:
        try:
            # Удаляем все сообщения, кроме самого последнего (которое может быть уже удалено)
            # В случае ошибки edit_text, последнее сообщение может остаться
            await bot.delete_messages(chat_id=chat_id, message_ids=message_ids[:-1])
        except Exception as e:
            logger.warning(f"Could not delete messages in creation dialog cleanup: {e}")
    await state.clear()


# --- USER COMMANDS ---

@router.message(Command("event", ignore_case=True))
async def cmd_event(message: Message):
    events = await db.get_all_events()
    if not events:
        await message.answer("В ближайшее время событий не запланировано.")
        return

    now = datetime.now(MOSCOW_TZ)
    week_ahead = now + timedelta(days=7)

    dated_events = []
    for event in events:
        next_run = get_next_run_time(
            event['event_type'],
            event.get('event_date'),
            event.get('weekday'),
            event.get('event_time'),
            event.get('last_run')
        )
        if next_run:
            dated_events.append((next_run, event))

    dated_events.sort(key=lambda x: x[0]) # Сортируем по дате
    this_week_events = [event for run_time, event in dated_events if run_time <= week_ahead]
    
    if not this_week_events:
        await message.answer("На ближайшую неделю событий не запланировано.")
        return

    keyboard = await get_events_keyboard(this_week_events)
    await message.answer(
        "📅 События на ближайшие 7 дней (время указывается в MSK):",
        reply_markup=keyboard
    )

@router.callback_query(EventAction.filter(F.action == "view"))
async def process_event_selection(callback: CallbackQuery, callback_data: EventAction):
    event_id = callback_data.event_id
    event = await db.get_event(event_id)
    if not event:
        await callback.answer("Событие не найдено.", show_alert=True)
        return

    event_name = event['name'] or event['activity_name']
    event_description = event['description'] or event['activity_description']

    schedule_str = "Не определено"
    if event['event_type'] == 'single' and event['event_date']:
        schedule_str = f"📅 Дата: {event['event_date'].strftime('%d.%m.%Y в %H:%M')} ({MSK_LABEL})"
    elif event['event_type'] == 'recurring' and event['weekday'] is not None and event['event_time'] is not None:
        next_run = get_next_run_time(
            event['event_type'], event.get('event_date'),
            event.get('weekday'), event.get('event_time'),
            event.get('last_run')
        )
        if next_run:
            schedule_str = (
                f"📅 Регулярность: каждый {weekdays_map[event['weekday']]}\n"
                f"📅 Следующее: {next_run.strftime('%d.%m.%Y в %H:%M')} ({MSK_LABEL})"
            )
        else:
            schedule_str = (
                f"📅 Регулярность: каждый {weekdays_map[event['weekday']]} "
                f"в {event['event_time'].strftime('%H:%M')} ({MSK_LABEL})"
            )

    text = (
        f"<b>{event_name}</b>\n\n"
        f"<i>{event_description}</i>\n\n"
        f"{schedule_str}\n"
        f"💰 Стоимость: {format_amount(event['cost'])} {CURRENCY_SYMBOL}\n"
        f"🔗 Ссылка будет отправлена подписчикам в личные сообщения."
    )
    keyboard = await get_event_details_keyboard(event_id)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(GeneralAction.filter(F.action == "back_to_events"))
async def back_to_events_list(callback: CallbackQuery):
    if isinstance(callback.message, Message):
        await cmd_event(callback.message)
    else:
        # Для CallbackQuery нужно имитировать вызов cmd_event, но без Message объекта
        # Можно просто отредактировать сообщение с новым списком событий
        events = await db.get_all_events()
        now = datetime.now(MOSCOW_TZ)
        week_ahead = now + timedelta(days=7)
        dated_events = []
        for event in events:
            next_run = get_next_run_time(event['event_type'], event.get('event_date'), event.get('weekday'), event.get('event_time'), event.get('last_run'))
            if next_run:
                dated_events.append((next_run, event))
        dated_events.sort(key=lambda x: x[0])
        this_week_events = [event for run_time, event in dated_events if run_time <= week_ahead]
        
        if not this_week_events:
            await callback.message.edit_text("На ближайшую неделю событий не запланировано.")
        else:
            keyboard = await get_events_keyboard(this_week_events)
            await callback.message.edit_text("📅 События на ближайшие 7 дней (время указывается в MSK):", reply_markup=keyboard)

    await callback.answer()

# --- ADMIN: CREATE EVENT (REWORKED FSM) ---

@router.message(Command("create_event", ignore_case=True))
async def cmd_create_event(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.reply("❌ У вас нет прав для выполнения этой команды.")
        return

    activities = await db.get_all_activities()
    keyboard = await get_activities_keyboard_for_event(activities)
    await state.set_state(EventCreationStates.waiting_for_activity)
    sent_msg = await message.answer("К какой активности относится событие?", reply_markup=keyboard)
    await state.update_data(message_ids=[message.message_id, sent_msg.message_id])


@router.callback_query(EventCreationAction.filter(F.action == "select_activity"))
async def start_event_creation_from_activity(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return
    
    activity_id = callback_data.activity_id
    await state.update_data(activity_id=activity_id)
    await state.set_state(EventCreationStates.waiting_for_event_name)

    data = await state.get_data()
    message_ids = data.get('message_ids', [callback.message.message_id])

    await callback.message.edit_text(
        "Введите название для события. Отправьте `.` чтобы использовать название активности.\n\n"
        "*Для отмены введите /cancel*",
        parse_mode="Markdown"
    )
    await state.update_data(message_ids=message_ids)
    await callback.answer()


@router.message(EventCreationStates.waiting_for_event_name)
async def process_event_name(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)

    name = message.text
    if name.strip() == '.': name = None
    await state.update_data(name=name)
    await state.set_state(EventCreationStates.waiting_for_event_description)
    
    activity = await db.get_activity(data['activity_id'])
    
    prompt_text = (
        "Отлично! Теперь введите описание для события.\n\n"
        f"<i>Описание активности для справки:</i>\n<code>{activity['description'] or 'Не задано'}</code>\n\n"
        "Для отмены введите /cancel"
    )
    keyboard = get_use_default_keyboard(
        "Использовать описание активности",
        EventCreationAction(action="use_activity_desc").action # CallbackData action for using default
    )
    
    await message.bot.edit_message_text(
        prompt_text,
        chat_id=message.chat.id,
        message_id=message_ids[-2],
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.update_data(message_ids=message_ids)

@router.callback_query(EventCreationAction.filter(F.action == "use_activity_desc"), EventCreationStates.waiting_for_event_description)
async def process_use_activity_description(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    await state.update_data(description=None)
    await state.set_state(EventCreationStates.waiting_for_type)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Разовое", callback_data=EventCreationAction(action="set_type", event_type="single").pack())],
        [InlineKeyboardButton(text="Регулярное", callback_data=EventCreationAction(action="set_type", event_type="recurring").pack())]
    ])
    await callback.message.edit_text("Выберите тип события:", reply_markup=keyboard)
    await callback.answer()

@router.message(EventCreationStates.waiting_for_event_description)
async def process_event_description(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)
    
    await state.update_data(description=message.text)
    await state.set_state(EventCreationStates.waiting_for_type)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Разовое", callback_data=EventCreationAction(action="set_type", event_type="single").pack())],
        [InlineKeyboardButton(text="Регулярное", callback_data=EventCreationAction(action="set_type", event_type="recurring").pack())]
    ])
    
    await message.bot.edit_message_text(
        "Выберите тип события:",
        chat_id=message.chat.id,
        message_id=message_ids[-2],
        reply_markup=keyboard
    )
    await state.update_data(message_ids=message_ids)

@router.callback_query(EventCreationAction.filter(F.action == "set_type"), EventCreationStates.waiting_for_type)
async def process_event_type(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    event_type = callback_data.event_type
    await state.update_data(event_type=event_type)

    if event_type == "single":
        await state.set_state(EventCreationStates.waiting_for_date)
        await callback.message.edit_text(
            "Введите дату и время события в формате <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (время в MSK)\n\nДля отмены введите /cancel",
            parse_mode="HTML"
        )
    else:
        await state.set_state(EventCreationStates.waiting_for_weekday)
        keyboard = get_weekday_keyboard()
        await callback.message.edit_text(
            "Выберите день недели для регулярного события:",
            reply_markup=keyboard
        )
    await callback.answer()

async def proceed_to_cost_from_date(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)
    
    await state.update_data(message_ids=message_ids)
    await state.set_state(EventCreationStates.waiting_for_cost)
    prompt_text = "Отлично. Теперь введите стоимость участия (число, 0 для бесплатного).\n\n*Для отмены введите /cancel*"
    
    await message.bot.edit_message_text(
        prompt_text,
        chat_id=message.chat.id,
        message_id=message_ids[-2],
        reply_markup=None,
        parse_mode="Markdown"
    )

@router.message(EventCreationStates.waiting_for_date)
async def process_event_date(message: Message, state: FSMContext):
    date_text = message.text.replace(',', '.')
    try:
        naive = datetime.strptime(date_text, "%d.%m.%Y %H:%M")
        event_date = naive.replace(tzinfo=MOSCOW_TZ)

        if event_date < datetime.now(MOSCOW_TZ):
            await message.reply("❌ Нельзя создать событие в прошлом. Пожалуйста, введите будущую дату и время (MSK).")
            return

        await state.update_data(event_date=event_date, weekday=None, event_time=None)
        await proceed_to_cost_from_date(message, state)
    except ValueError:
        await message.reply("❌ Неверный формат. Введите дату и время в формате <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (MSK).", parse_mode="HTML")

@router.callback_query(EventCreationAction.filter(F.action == "select_weekday"), EventCreationStates.waiting_for_weekday)
async def process_event_weekday(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    weekday = callback_data.weekday
    await state.update_data(weekday=weekday)
    await state.set_state(EventCreationStates.waiting_for_time)
    await callback.message.edit_text(
        f"Вы выбрали: <b>{weekdays_map[weekday].capitalize()}</b>.\nТеперь введите время в формате <b>ЧЧ:ММ</b> (MSK).",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventCreationStates.waiting_for_time)
async def process_event_time(message: Message, state: FSMContext):
    try:
        event_time = datetime.strptime(message.text, "%H:%M").time()
        await state.update_data(event_time=event_time, event_date=None)
        await proceed_to_cost_from_date(message, state)
    except ValueError:
        await message.reply("❌ Неверный формат. Введите время в формате <b>ЧЧ:ММ</b> (MSK).", parse_mode="HTML")

@router.message(EventCreationStates.waiting_for_cost)
async def process_event_cost(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)

    try:
        cost = Decimal(message.text.replace(',', '.'))
        if cost < 0: raise ValueError()
        await state.update_data(cost=str(cost))
        await state.set_state(EventCreationStates.waiting_for_link)
        
        await message.bot.edit_message_text(
            "Теперь введите ссылку на событие (например, на чат или видеоконференцию).\n\n*Для отмены введите /cancel*",
            chat_id=message.chat.id,
            message_id=message_ids[-2],
            parse_mode="Markdown"
        )
        await state.update_data(message_ids=message_ids)

    except (InvalidOperation, ValueError):
        await message.reply("❌ Введите корректное неотрицательное число.")


@router.message(EventCreationStates.waiting_for_link)
async def process_event_link(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)

    await state.update_data(link=message.text)
    await state.set_state(EventCreationStates.waiting_for_reminder_time)

    await message.bot.edit_message_text(
        "За сколько минут до начала отправлять напоминание? Введите число (0 - не отправлять).\n\n*Для отмены введите /cancel*",
        chat_id=message.chat.id,
        message_id=message_ids[-2]
    )
    await state.update_data(message_ids=message_ids)


@router.message(EventCreationStates.waiting_for_reminder_time)
async def process_event_reminder_time(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)

    try:
        reminder_time = int(message.text)
        if reminder_time < 0: raise ValueError()
        await state.update_data(reminder_time=reminder_time)

        if reminder_time > 0:
            await state.set_state(EventCreationStates.waiting_for_reminder_text)
            default_reminder = await db.get_setting('default_reminder_text', DEFAULT_REMINDER_TEXT)
            
            prompt_text = (
                "Введите текст напоминания.\n\n"
                f"<i>Текущий шаблон по умолчанию:</i>\n<code>{default_reminder}</code>\n\n"
                f"{REMINDER_VARIABLES_HELP_TEXT}\n\n"
                "Для отмены введите /cancel"
            )
            keyboard = get_use_default_keyboard("Использовать шаблон по умолчанию", EventCreationAction(action="use_default_reminder").action)
            await message.bot.edit_message_text(prompt_text, chat_id=message.chat.id, message_id=message_ids[-2], reply_markup=keyboard, parse_mode="HTML")
            await state.update_data(message_ids=message_ids)

        else:
            await state.update_data(reminder_text=None)
            await show_event_preview(message, state)

    except ValueError:
        await message.reply("❌ Введите целое неотрицательное число.")
        message_ids.append(message.message_id)
        await state.update_data(message_ids=message_ids)

@router.callback_query(EventCreationAction.filter(F.action == "use_default_reminder"), EventCreationStates.waiting_for_reminder_text)
async def process_use_default_reminder(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    await state.update_data(reminder_text=None)
    await show_event_preview(callback, state)


@router.message(EventCreationStates.waiting_for_reminder_text)
async def process_event_reminder_text(message: Message, state: FSMContext):
    await state.update_data(reminder_text=message.text)
    await show_event_preview(message, state)

async def show_event_preview(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    if isinstance(target, Message):
        message_ids.append(target.message_id)
        message_to_edit_id = message_ids[-2]
        chat_id = target.chat.id
    else: # CallbackQuery
        message_to_edit_id = target.message.message_id
        chat_id = target.message.chat.id

    activity = await db.get_activity(data['activity_id'])
    
    name = data.get('name') or activity['name']
    description = data.get('description') or activity['description']
    
    schedule_str = "Не определено"
    if data['event_type'] == 'single':
        schedule_str = f"📅 Разовое: {data['event_date'].strftime('%d.%m.%Y в %H:%M')} ({MSK_LABEL})"
    else:
        schedule_str = f"📅 Регулярное: каждый {weekdays_map[data['weekday']]} в {data['event_time'].strftime('%H:%M')} ({MSK_LABEL})"

    cost = format_amount(Decimal(data['cost']))
    reminder = f"{data['reminder_time']} мин." if data['reminder_time'] > 0 else "Нет"

    preview_text = (
        f"<b>💡 Предпросмотр события</b>\n\n"
        f"<b>Название:</b> {name}\n"
        f"<b>Активность:</b> {activity['name']}\n"
        f"<b>Описание:</b> {description}\n\n"
        f"<b>Расписание:</b> {schedule_str}\n"
        f"<b>Стоимость:</b> {cost} {CURRENCY_SYMBOL}\n"
        f"<b>Ссылка:</b> {data['link']}\n"
        f"<b>Напоминание за:</b> {reminder}\n\n"
        "Сохранить событие?"
    )

    await state.set_state(EventCreationStates.waiting_for_confirmation)
    keyboard = get_event_creation_confirmation_keyboard()
    await target.bot.edit_message_text(preview_text, chat_id=chat_id, message_id=message_to_edit_id, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(message_ids=message_ids)

@router.callback_query(EventCreationAction.filter(F.action == "confirm_create"), EventCreationStates.waiting_for_confirmation)
async def confirm_event_creation(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    """
    Обрабатывает финальное подтверждение и создает событие.
    """
    await create_event_from_state(callback, state)

async def create_event_from_state(target: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bot = target.bot
    scheduler = bot.scheduler
    chat_id = target.message.chat.id
    from_user_id = target.from_user.id
    
    await cleanup_creation_dialog(bot, chat_id, state)
    
    event_data = {
        'activity_id': data.get('activity_id'),
        'name': data.get('name'),
        'description': data.get('description'),
        'event_type': data['event_type'],
        'cost': data['cost'],
        'link': data['link'],
        'reminder_time': data['reminder_time'],
        'reminder_text': data.get('reminder_text'),
        'created_by': from_user_id,
        'event_date': data.get('event_date'),
        'weekday': data.get('weekday'),
        'event_time': data.get('event_time')
    }

    event_id = await db.create_event(**event_data)
    event_details = await db.get_event(event_id)
    if event_details:
        await schedule_event_jobs(event_details, bot, scheduler)

    logger.info(f"Admin {from_user_id} created new event {event_id}.")
    await bot.send_message(chat_id, f"✅ Событие успешно создано и запланировано (ID: {event_id}).")


# --- ADMIN: INLINE EDIT/DELETE FLOW ---

@router.callback_query(EventAction.filter(F.action == "edit_menu"))
async def show_event_edit_menu(callback: CallbackQuery, state: FSMContext, callback_data: EventAction):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return
    event_id = callback_data.event_id
    event = await db.get_event(event_id)
    if not event:
        await callback.answer("Событие не найдено.", show_alert=True)
        return
    await state.update_data(event_id=event_id, activity_id=event['activity_id'])
    event_name = event['name'] or event['activity_name']
    info_text = f"<b>📝 Редактирование события:</b>\n<code>{event_name}</code>\n\nЧто вы хотите изменить?"
    keyboard = await get_event_edit_keyboard(event_id)
    await callback.message.edit_text(info_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(EventAction.filter(F.action == "delete_confirm"))
async def confirm_event_deletion(callback: CallbackQuery, callback_data: EventAction):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return
    event_id = callback_data.event_id
    event = await db.get_event(event_id)
    if not event:
        await callback.answer("Событие уже удалено.", show_alert=True)
        return
    event_name = event['name'] or event['activity_name']
    text = f"Вы уверены, что хотите удалить событие «<b>{event_name}</b>»?\n\nЭто действие необратимо."
    keyboard = confirm_delete_keyboard("event", event_id) # Используем новую фабрику
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(GeneralAction.filter(F.action.startswith("confirm_final_delete_event_")))
async def process_event_deletion(callback: CallbackQuery, callback_data: GeneralAction):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return
    # Извлекаем event_id из callback_data.action
    event_id = int(callback_data.action.split("_")[-1])
    event = await db.get_event(event_id)
    if not event:
        await callback.message.edit_text("Событие уже было удалено.")
        await callback.answer()
        return
    event_name = event['name'] or event['activity_name']
    scheduler = callback.bot.scheduler
    remove_event_jobs(event_id, scheduler)
    await db.delete_event(event_id)
    logger.warning(f"Admin {callback.from_user.id} deleted event {event_id}: {event_name}")
    await callback.message.edit_text(f"✅ Событие «<b>{event_name}</b>» успешно удалено.")
    await callback.answer()

# --- FSM for Event Editing ---

@router.callback_query(EventEditAction.filter(F.action == "name"))
async def process_edit_event_name(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_name)
    event = await db.get_event(event_id)
    current_name = event['name'] or event['activity_name']
    await callback.message.edit_text(
        f"Текущее название: <code>{current_name}</code>\n\n"
        "Введите новое название или `.` чтобы использовать название активности.\n\n"
        "Для отмены введите /cancel",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_name)
async def update_event_name(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data['event_id']
    new_name = message.text if message.text != '.' else None
    await db.update_event(event_id, name=new_name)
    await message.answer("✅ Название события обновлено.")
    await state.clear()

@router.callback_query(EventEditAction.filter(F.action == "description"))
async def process_edit_event_description(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_description)
    event = await db.get_event(event_id)
    current_desc = event['description'] or event['activity_description']
    await callback.message.edit_text(
        f"Текущее описание: <code>{current_desc}</code>\n\n"
        "Введите новое описание или `.` чтобы использовать описание активности.\n\n"
        "Для отмены введите /cancel",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_description)
async def update_event_description(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data['event_id']
    new_desc = message.text if message.text != '.' else None
    await db.update_event(event_id, description=new_desc)
    await message.answer("✅ Описание события обновлено.")
    await state.clear()

@router.callback_query(EventEditAction.filter(F.action == "schedule"))
async def process_edit_event_schedule(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    event = await db.get_event(event_id)
    await state.update_data(event_id=event_id)
    if event['event_type'] == 'single':
        await state.set_state(EventEditStates.waiting_for_new_date)
        await callback.message.edit_text(
            "Введите новую дату и время в формате <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (MSK)\n\n"
            "Для отмены введите /cancel",
            parse_mode="HTML"
        )
    else:
        await state.set_state(EventEditStates.waiting_for_new_weekday)
        keyboard = get_weekday_keyboard()
        await callback.message.edit_text("Выберите новый день недели:", reply_markup=keyboard)
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_date)
async def update_event_date(message: Message, state: FSMContext):
    try:
        naive = datetime.strptime(message.text.replace(',', '.'), "%d.%m.%Y %H:%M")
        new_date = naive.replace(tzinfo=MOSCOW_TZ)
        data = await state.get_data()
        event_id = data['event_id']
        await db.update_event(event_id, event_date=new_date)
        bot = message.bot
        scheduler = bot.scheduler
        remove_event_jobs(event_id, scheduler)
        event = await db.get_event(event_id)
        if event:
            await schedule_event_jobs(event, bot, scheduler)
        await message.answer("✅ Дата события обновлена и перепланирована.")
        await state.clear()
    except ValueError:
        await message.reply("❌ Неверный формат. Введите дату и время в формате <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (MSK).", parse_mode="HTML")

@router.callback_query(EventCreationAction.filter(F.action == "select_weekday"), EventEditStates.waiting_for_new_weekday)
async def update_event_weekday(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    weekday = callback_data.weekday
    await state.update_data(weekday=weekday)
    await state.set_state(EventEditStates.waiting_for_new_time)
    await callback.message.edit_text(
        f"Выбран: <b>{weekdays_map[weekday].capitalize()}</b>.\n"
        "Теперь введите новое время в формате <b>ЧЧ:ММ</b> (MSK).",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_time)
async def update_event_time(message: Message, state: FSMContext):
    try:
        new_time = datetime.strptime(message.text, "%H:%M").time()
        data = await state.get_data()
        event_id = data['event_id']
        weekday = data['weekday']
        await db.update_event(event_id, weekday=weekday, event_time=new_time)
        bot = message.bot
        scheduler = bot.scheduler
        remove_event_jobs(event_id, scheduler)
        event = await db.get_event(event_id)
        if event:
            await schedule_event_jobs(event, bot, scheduler)
        await message.answer("✅ Расписание события обновлено и перепланировано.")
        await state.clear()
    except ValueError:
        await message.reply("❌ Неверный формат. Введите время в формате <b>ЧЧ:ММ</b> (MSK).", parse_mode="HTML")

@router.callback_query(EventEditAction.filter(F.action == "cost"))
async def process_edit_event_cost(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_cost)
    event = await db.get_event(event_id)
    current_cost = format_amount(event['cost'])
    text = f"Текущая стоимость: <code>{current_cost} {CURRENCY_SYMBOL}</code>\n\n"
    if event['activity_id'] == 1:
        text += "⚠️ <b>Внимание!</b> Это общее событие. Изменение стоимости затронет всех пользователей!\n\n"
    text += "Введите новую стоимость (число).\n\nДля отмены введите /cancel"
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_cost)
async def update_event_cost(message: Message, state: FSMContext):
    try:
        new_cost = Decimal(message.text.replace(',', '.'))
        if new_cost < 0:
            raise ValueError()
        data = await state.get_data()
        event_id = data['event_id']
        await db.update_event(event_id, cost=str(new_cost))
        await message.answer("✅ Стоимость события обновлена.")
        await state.clear()
    except (InvalidOperation, ValueError):
        await message.reply("❌ Введите корректное неотрицательное число.")

@router.callback_query(EventEditAction.filter(F.action == "link"))
async def process_edit_event_link(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_link)
    event = await db.get_event(event_id)
    await callback.message.edit_text(
        f"Текущая ссылка: <code>{event['link']}</code>\n\n"
        "Введите новую ссылку.\n\n"
        "Для отмены введите /cancel",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_link)
async def update_event_link(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data['event_id']
    await db.update_event(event_id, link=message.text)
    await message.answer("✅ Ссылка на событие обновлена.")
    await state.clear()

@router.callback_query(EventEditAction.filter(F.action == "reminder"))
async def process_edit_event_reminder(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_reminder_time)
    event = await db.get_event(event_id)
    current_time = event['reminder_time'] or 0
    await callback.message.edit_text(
        f"Текущее время напоминания: <code>{'За ' + str(current_time) + ' мин.' if current_time else 'Нет'}</code>\n\n"
        "Введите за сколько минут до события отправлять напоминание (0 - отключить).\n\n"
        "Для отмены введите /cancel",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_reminder_time)
async def update_event_reminder_time(message: Message, state: FSMContext):
    try:
        new_time = int(message.text)
        if new_time < 0:
            raise ValueError()
        data = await state.get_data()
        event_id = data['event_id']
        await state.update_data(reminder_time=new_time)
        if new_time > 0:
            await state.set_state(EventEditStates.waiting_for_new_reminder_text)
            await message.answer(
                "Введите новый текст напоминания или `.` для шаблона по умолчанию.\n\n"
                f"{REMINDER_VARIABLES_HELP_TEXT}\n\n"
                "Для отмены введите /cancel",
                parse_mode="HTML"
            )
        else:
            await db.update_event(event_id, reminder_time=0, reminder_text=None)
            bot = message.bot
            scheduler = bot.scheduler
            try:
                scheduler.remove_job(f"event_reminder_{event_id}")
            except Exception:
                pass
            await message.answer("✅ Напоминание отключено.")
            await state.clear()
    except ValueError:
        await message.reply("❌ Введите целое неотрицательное число.")

@router.message(EventEditStates.waiting_for_new_reminder_text)
async def update_event_reminder_text(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data['event_id']
    reminder_time = data['reminder_time']
    reminder_text = message.text if message.text != '.' else DEFAULT_REMINDER_TEXT
    await db.update_event(event_id, reminder_time=reminder_time, reminder_text=reminder_text)
    bot = message.bot
    scheduler = bot.scheduler
    event = await db.get_event(event_id)
    remove_event_jobs(event_id, scheduler)
    if event:
        await schedule_event_jobs(event, bot, scheduler)
    await message.answer("✅ Параметры напоминания обновлены.")
    await state.clear()
