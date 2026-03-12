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
from datetime import datetime, timedelta, time
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from app.database import db
from app.keyboards import (
    get_events_keyboard, get_event_details_keyboard, confirm_delete_keyboard,
    get_activities_keyboard_for_event, get_event_edit_keyboard, get_weekday_keyboard,
    get_use_default_keyboard, get_event_creation_confirmation_keyboard
)
from app.states import EventCreationStates, EventEditStates
from app.utils import is_admin, format_amount, get_next_run_time, format_weekdays
from app.config import CURRENCY_SYMBOL
from app.lexicon import LEXICON_RU
from app.services.scheduler_jobs import schedule_event_jobs, remove_event_jobs
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.callbacks import (
    GeneralAction, ActivityAction, EventAction, EventEditAction, EventCreationAction,
    ConfirmDeleteAction
)

router = Router()
logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
MSK_LABEL = "MSK"

REMINDER_VARIABLES_HELP_TEXT = LEXICON_RU["msg_event_reminder_vars_help"]

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
        from app.keyboards import get_back_to_menu_keyboard
        await message.answer(LEXICON_RU["msg_events_none_soon"], reply_markup=get_back_to_menu_keyboard())
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
        from app.keyboards import get_back_to_menu_keyboard
        await message.answer(LEXICON_RU["msg_events_none_this_week"], reply_markup=get_back_to_menu_keyboard())
        return

    keyboard = await get_events_keyboard(this_week_events)
    await message.answer(
        LEXICON_RU["msg_events_this_week_header"],
        reply_markup=keyboard
    )

@router.callback_query(EventAction.filter(F.action == "view"))
async def process_event_selection(callback: CallbackQuery, callback_data: EventAction):
    event_id = callback_data.event_id
    event = await db.get_event(event_id)
    if not event:
        await callback.answer(LEXICON_RU["err_event_not_found"], show_alert=True)
        return

    event_name = event['name'] or event['activity_name']
    event_description = event['description'] or event['activity_description']

    schedule_str = LEXICON_RU["msg_event_schedule_not_determined"]
    if event['event_type'] == 'single' and event['event_date']:
        schedule_str = LEXICON_RU["msg_event_schedule_single"].format(date_str=event['event_date'].strftime('%d.%m.%Y в %H:%M'), msk_label=MSK_LABEL)
    elif event['event_type'] == 'recurring' and event['weekday'] is not None and event['event_time'] is not None:
        next_run = get_next_run_time(
            event['event_type'], event.get('event_date'),
            event.get('weekday'), event.get('event_time'),
            event.get('last_run')
        )
        if next_run:
            schedule_str = LEXICON_RU["msg_event_schedule_recurring_next"].format(weekdays=format_weekdays(event['weekday']), next_date_str=next_run.strftime('%d.%m.%Y в %H:%M'), msk_label=MSK_LABEL)
        else:
            schedule_str = LEXICON_RU["msg_event_schedule_recurring_only"].format(weekdays=format_weekdays(event['weekday']), time_str=event['event_time'].strftime('%H:%M'), msk_label=MSK_LABEL)

    text = LEXICON_RU["msg_event_view_details"].format(
        event_name=event_name,
        event_description=event_description,
        schedule_str=schedule_str,
        cost=format_amount(event['cost']),
        currency_symbol=CURRENCY_SYMBOL
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
            await callback.message.edit_text(LEXICON_RU["msg_events_none_this_week"])
        else:
            keyboard = await get_events_keyboard(this_week_events)
            await callback.message.edit_text(LEXICON_RU["msg_events_this_week_header"], reply_markup=keyboard)

    await callback.answer()

# --- ADMIN: CREATE EVENT (REWORKED FSM) ---

@router.message(Command("create_event", ignore_case=True))
async def cmd_create_event(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.reply(LEXICON_RU["err_no_admin_rights"])
        return

    activities = await db.get_all_activities()
    keyboard = await get_activities_keyboard_for_event(activities)
    await state.set_state(EventCreationStates.waiting_for_activity)
    sent_msg = await message.answer(LEXICON_RU["msg_event_ask_activity"], reply_markup=keyboard)
    await state.update_data(message_ids=[message.message_id, sent_msg.message_id])


@router.callback_query(EventCreationAction.filter(F.action == "select_activity"))
async def start_event_creation_from_activity(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction = None):
    if not await is_admin(callback.from_user.id):
        await callback.answer(LEXICON_RU["err_no_admin_rights_alert"], show_alert=True)
        return
    
    # If called from activity directly, activity_id might be in state already 
    # or we can extract it if callback_data is provided
    if callback_data:
        activity_id = callback_data.activity_id
        await state.update_data(activity_id=activity_id)
    else:
        data = await state.get_data()
        activity_id = data.get('activity_id')
    await state.set_state(EventCreationStates.waiting_for_event_name)

    data = await state.get_data()
    message_ids = data.get('message_ids', [callback.message.message_id])

    await callback.message.edit_text(
        LEXICON_RU["msg_event_ask_name"],
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
    
    prompt_text = LEXICON_RU["msg_event_ask_description"].format(activity_desc=activity['description'] or LEXICON_RU["msg_activity_no_description"])
    keyboard = get_use_default_keyboard(
        LEXICON_RU["btn_use_activity_desc"],
        EventCreationAction(action="use_activity_desc").pack()
    )
    
    sent_message = await message.answer(
        prompt_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    message_ids.append(sent_message.message_id)
    await state.update_data(message_ids=message_ids)

@router.callback_query(EventCreationAction.filter(F.action == "use_activity_desc"), EventCreationStates.waiting_for_event_description)
async def process_use_activity_description(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    await state.update_data(description=None)
    await state.set_state(EventCreationStates.waiting_for_type)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Разовое", callback_data=EventCreationAction(action="set_type", event_type="single").pack())],
        [InlineKeyboardButton(text="Регулярное", callback_data=EventCreationAction(action="set_type", event_type="recurring").pack())]
    ])
    await callback.message.edit_text(LEXICON_RU["msg_event_ask_type"], reply_markup=keyboard)
    await callback.answer()

@router.message(EventCreationStates.waiting_for_event_description)
async def process_event_description(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)
    
    await state.update_data(description=message.text)
    await state.set_state(EventCreationStates.waiting_for_type)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LEXICON_RU["btn_event_type_single"], callback_data=EventCreationAction(action="set_type", event_type="single").pack())],
        [InlineKeyboardButton(text=LEXICON_RU["btn_event_type_recurring"], callback_data=EventCreationAction(action="set_type", event_type="recurring").pack())]
    ])
    
    sent_message = await message.answer(
        LEXICON_RU["msg_event_ask_type"],
        reply_markup=keyboard
    )
    message_ids.append(sent_message.message_id)
    await state.update_data(message_ids=message_ids)

@router.callback_query(EventCreationAction.filter(F.action == "set_type"), EventCreationStates.waiting_for_type)
async def process_event_type(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    event_type = callback_data.event_type
    await state.update_data(event_type=event_type)

    if event_type == "single":
        await state.set_state(EventCreationStates.waiting_for_date)
        await callback.message.edit_text(
            LEXICON_RU["msg_event_ask_date_single"],
            parse_mode="HTML"
        )
    else:
        await state.update_data(weekdays=[])
        await state.set_state(EventCreationStates.waiting_for_weekday)
        keyboard = get_weekday_keyboard(selected_weekdays=[])
        await callback.message.edit_text(
            LEXICON_RU["msg_event_ask_weekdays"],
            reply_markup=keyboard
        )
    await callback.answer()

async def proceed_to_cost_from_date(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)
    
    await state.update_data(message_ids=message_ids)
    await state.set_state(EventCreationStates.waiting_for_cost)
    prompt_text = LEXICON_RU["msg_event_ask_cost"]
    
    sent_message = await message.answer(
        prompt_text,
        reply_markup=None,
        parse_mode="Markdown"
    )
    message_ids.append(sent_message.message_id)
    await state.update_data(message_ids=message_ids)

@router.message(EventCreationStates.waiting_for_date)
async def process_event_date(message: Message, state: FSMContext):
    date_text = message.text.replace(',', '.')
    try:
        naive = datetime.strptime(date_text, "%d.%m.%Y %H:%M")
        event_date = naive.replace(tzinfo=MOSCOW_TZ)

        if event_date < datetime.now(MOSCOW_TZ):
            await message.reply(LEXICON_RU["err_event_date_past"])
            return

        await state.update_data(event_date=event_date.isoformat(), weekday=None, event_time=None)
        await proceed_to_cost_from_date(message, state)
    except ValueError:
        await message.reply(LEXICON_RU["err_event_invalid_date_format"], parse_mode="HTML")

@router.callback_query(EventCreationAction.filter(F.action == "toggle_weekday"), EventCreationStates.waiting_for_weekday)
async def process_event_weekday_toggle(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    data = await state.get_data()
    selected = set(data.get('weekdays', []))
    weekday = callback_data.weekday
    if weekday in selected:
        selected.remove(weekday)
    else:
        selected.add(weekday)
    selected_list = sorted(list(selected))
    await state.update_data(weekdays=selected_list)
    keyboard = get_weekday_keyboard(selected_weekdays=selected_list)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@router.callback_query(EventCreationAction.filter(F.action == "confirm_weekdays"), EventCreationStates.waiting_for_weekday)
async def process_event_weekday_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('weekdays', [])
    if not selected:
        await callback.answer(LEXICON_RU["err_event_no_weekdays_selected"], show_alert=True)
        return
    weekday_str = ",".join(map(str, sorted(selected)))
    await state.update_data(weekday=weekday_str)
    await state.set_state(EventCreationStates.waiting_for_time)
    await callback.message.edit_text(
        LEXICON_RU["msg_event_ask_time_recurring"].format(weekdays=format_weekdays(weekday_str)),
        parse_mode="HTML"
    )
    await callback.answer()

# Fix 1: Allow typing time directly in weekday state (auto-confirm selected days)
@router.message(EventCreationStates.waiting_for_weekday)
async def process_time_in_weekday_state(message: Message, state: FSMContext):
    """Handles time input directly in weekday state - auto-confirm selected days first."""
    data = await state.get_data()
    selected = data.get('weekdays', [])
    if not selected:
        await message.reply(LEXICON_RU["err_event_no_weekdays_selected"])
        return
    try:
        event_time = datetime.strptime(message.text.strip(), "%H:%M").time()
        weekday_str = ",".join(map(str, sorted(selected)))
        await state.update_data(weekday=weekday_str, event_time=event_time.isoformat(), event_date=None)
        await state.set_state(EventCreationStates.waiting_for_end_date)
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text=LEXICON_RU["btn_event_no_end_date"],
            callback_data=EventCreationAction(action="no_end_date").pack()
        ))
        await message.answer(
            LEXICON_RU["msg_event_ask_end_date"].format(
                weekdays=format_weekdays(weekday_str),
                time_str=event_time.strftime("%H:%M")
            ),
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except ValueError:
        await message.reply(LEXICON_RU["err_event_invalid_time_format"], parse_mode="HTML")

@router.message(EventCreationStates.waiting_for_time)
async def process_event_time(message: Message, state: FSMContext):
    try:
        event_time = datetime.strptime(message.text.strip(), "%H:%M").time()
        await state.update_data(event_time=event_time.isoformat(), event_date=None)
        # After time, ask for end_date
        data = await state.get_data()
        await state.set_state(EventCreationStates.waiting_for_end_date)
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(
            text=LEXICON_RU["btn_event_no_end_date"],
            callback_data=EventCreationAction(action="no_end_date").pack()
        ))
        await message.answer(
            LEXICON_RU["msg_event_ask_end_date"].format(
                weekdays=format_weekdays(data.get('weekday', '')),
                time_str=event_time.strftime("%H:%M")
            ),
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    except ValueError:
        await message.reply(LEXICON_RU["err_event_invalid_time_format"], parse_mode="HTML")

@router.callback_query(EventCreationAction.filter(F.action == "no_end_date"), EventCreationStates.waiting_for_end_date)
async def process_event_no_end_date(callback: CallbackQuery, state: FSMContext):
    await state.update_data(end_date=None)
    await callback.message.edit_reply_markup(reply_markup=None)
    await proceed_to_cost_from_date(callback.message, state)
    await callback.answer()

@router.message(EventCreationStates.waiting_for_end_date)
async def process_event_end_date(message: Message, state: FSMContext):
    try:
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        await state.update_data(end_date=end_date.isoformat())
        await proceed_to_cost_from_date(message, state)
    except ValueError:
        await message.reply("\u274c Неверный формат. Введите дату в формате <b>ДД.ММ.ГГГГ</b>.", parse_mode="HTML")


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
        
        sent_message = await message.answer(
            LEXICON_RU["msg_event_ask_link"],
            parse_mode="Markdown"
        )
        message_ids.append(sent_message.message_id)
        await state.update_data(message_ids=message_ids)

    except (InvalidOperation, ValueError):
        await message.reply(LEXICON_RU["err_event_invalid_cost"])


@router.message(EventCreationStates.waiting_for_link)
async def process_event_link(message: Message, state: FSMContext):
    data = await state.get_data()
    message_ids = data.get('message_ids', [])
    message_ids.append(message.message_id)

    await state.update_data(link=message.text)
    await state.set_state(EventCreationStates.waiting_for_reminder_time)

    sent_message = await message.answer(
        LEXICON_RU["msg_event_ask_reminder_time"]
    )
    message_ids.append(sent_message.message_id)
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
            default_reminder = await db.get_setting('default_reminder_text', LEXICON_RU["default_reminder"])
            
            prompt_text = LEXICON_RU["msg_event_ask_reminder_text"].format(
                default_reminder=default_reminder,
                vars_help=REMINDER_VARIABLES_HELP_TEXT
            )
            keyboard = get_use_default_keyboard("Использовать шаблон по умолчанию", EventCreationAction(action="use_default_reminder").pack())
            sent_message = await message.answer(prompt_text, reply_markup=keyboard, parse_mode="HTML")
            message_ids.append(sent_message.message_id)
            await state.update_data(message_ids=message_ids)

        else:
            await state.update_data(reminder_text=None)
            await show_event_preview(message, state)

    except ValueError:
        await message.reply(LEXICON_RU["err_event_invalid_reminder_time"])
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
    
    schedule_str = LEXICON_RU["msg_event_schedule_not_determined"]
    if data['event_type'] == 'single':
        parsed_date = datetime.fromisoformat(data['event_date'])
        schedule_str = LEXICON_RU["msg_event_preview_schedule_single"].format(date_str=parsed_date.strftime('%d.%m.%Y в %H:%M'), msk_label=MSK_LABEL)
    else:
        parsed_time = time.fromisoformat(data['event_time'])
        end_date_str = None
        if data.get('end_date'):
            from datetime import date as date_type
            end_date_str = date_type.fromisoformat(data['end_date']).strftime('%d.%m.%Y')
        end_date_label = LEXICON_RU["msg_event_end_date_label"].format(end_date=end_date_str) if end_date_str else LEXICON_RU["msg_event_no_end_date_label"]
        schedule_str = LEXICON_RU["msg_event_preview_schedule_recurring"].format(weekdays=format_weekdays(data['weekday']), time_str=parsed_time.strftime('%H:%M'), msk_label=MSK_LABEL) + f" ({end_date_label})"

    cost = format_amount(Decimal(data['cost']))
    reminder = f"{data['reminder_time']} мин." if data['reminder_time'] > 0 else LEXICON_RU["msg_event_no_reminder"]

    preview_text = LEXICON_RU["msg_event_preview_details"].format(
        name=name,
        activity_name=activity['name'],
        description=description,
        schedule_str=schedule_str,
        cost=cost,
        currency_symbol=CURRENCY_SYMBOL,
        link=data['link'],
        reminder=reminder
    )

    await state.set_state(EventCreationStates.waiting_for_confirmation)
    keyboard = get_event_creation_confirmation_keyboard()
    await target.bot.edit_message_text(preview_text, chat_id=chat_id, message_id=message_to_edit_id, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(message_ids=message_ids)

@router.callback_query(EventCreationAction.filter(F.action == "confirm_create"), EventCreationStates.waiting_for_confirmation)
async def confirm_event_creation(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction, scheduler: AsyncIOScheduler):
    """
    Обрабатывает финальное подтверждение и создает событие.
    """
    await create_event_from_state(callback, state, scheduler)

async def create_event_from_state(target: CallbackQuery, state: FSMContext, scheduler: AsyncIOScheduler):
    data = await state.get_data()
    bot = target.bot
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
        'event_date': datetime.fromisoformat(data['event_date']) if data.get('event_date') else None,
        'weekday': data.get('weekday'),
        'event_time': time.fromisoformat(data['event_time']) if data.get('event_time') else None,
        'end_date': __import__('datetime').date.fromisoformat(data['end_date']) if data.get('end_date') else None,
    }

    event_id = await db.create_event(**event_data)
    event_details = await db.get_event(event_id)
    if event_details:
        await schedule_event_jobs(event_details, bot, scheduler)

    logger.info(f"Admin {from_user_id} created new event {event_id}.")
    await bot.send_message(chat_id, LEXICON_RU["msg_event_created_success"].format(event_id=event_id))


# --- ADMIN: INLINE EDIT/DELETE FLOW ---

@router.callback_query(EventAction.filter(F.action == "edit_menu"))
async def show_event_edit_menu(callback: CallbackQuery, state: FSMContext, callback_data: EventAction):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return
    event_id = callback_data.event_id
    event = await db.get_event(event_id)
    if not event:
        await callback.answer(LEXICON_RU["err_event_not_found"], show_alert=True)
        return
    await state.update_data(event_id=event_id, activity_id=event['activity_id'])
    event_name = event['name'] or event['activity_name']
    info_text = LEXICON_RU["msg_event_edit_menu"].format(event_name=event_name)
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
        await callback.answer(LEXICON_RU["err_event_already_deleted"], show_alert=True)
        return
    event_name = event['name'] or event['activity_name']
    text = LEXICON_RU["msg_event_delete_confirm"].format(event_name=event_name)
    keyboard = confirm_delete_keyboard("event", event_id) # Используем новую фабрику
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(ConfirmDeleteAction.filter(F.item_type == "event"))
async def process_event_deletion(callback: CallbackQuery, callback_data: ConfirmDeleteAction, scheduler: AsyncIOScheduler):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ У вас нет прав.", show_alert=True)
        return
    event_id = callback_data.item_id
    event = await db.get_event(event_id)
    if not event:
        await callback.message.edit_text(LEXICON_RU["err_event_already_deleted"])
        await callback.answer()
        return
    event_name = event['name'] or event['activity_name']
    remove_event_jobs(event_id, scheduler)
    await db.delete_event(event_id)
    logger.warning(f"Admin {callback.from_user.id} deleted event {event_id}: {event_name}")
    await callback.message.edit_text(LEXICON_RU["msg_event_deleted"].format(event_name=event_name))
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
        LEXICON_RU["msg_event_edit_name"].format(current_name=current_name),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_name)
async def update_event_name(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data['event_id']
    new_name = message.text if message.text != '.' else None
    await db.update_event(event_id, name=new_name)
    await message.answer(LEXICON_RU["msg_event_name_updated"])
    await state.clear()

@router.callback_query(EventEditAction.filter(F.action == "description"))
async def process_edit_event_description(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_description)
    event = await db.get_event(event_id)
    current_desc = event['description'] or event['activity_description']
    await callback.message.edit_text(
        LEXICON_RU["msg_event_edit_description"].format(current_desc=current_desc),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_description)
async def update_event_description(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data['event_id']
    new_desc = message.text if message.text != '.' else None
    await db.update_event(event_id, description=new_desc)
    await message.answer(LEXICON_RU["msg_event_description_updated"])
    await state.clear()

@router.callback_query(EventEditAction.filter(F.action == "schedule"))
async def process_edit_event_schedule(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    event = await db.get_event(event_id)
    await state.update_data(event_id=event_id)
    try:
        if event['event_type'] == 'single':
            await state.set_state(EventEditStates.waiting_for_new_date)
            await callback.message.edit_text(
                LEXICON_RU["msg_event_edit_date"],
                parse_mode="HTML"
            )
        else:
            from app.utils import parse_weekdays
            current_weekdays = parse_weekdays(event.get('weekday'))
            await state.update_data(weekdays=current_weekdays)
            await state.set_state(EventEditStates.waiting_for_new_weekday)
            keyboard = get_weekday_keyboard(selected_weekdays=current_weekdays)
            await callback.message.edit_text(LEXICON_RU["msg_event_edit_weekdays"], reply_markup=keyboard)
    except TelegramBadRequest:
        if event['event_type'] == 'single':
            await callback.message.answer(
                LEXICON_RU["msg_event_edit_date"],
                parse_mode="HTML"
            )
        else:
            from app.utils import parse_weekdays
            current_weekdays = parse_weekdays(event.get('weekday'))
            await state.update_data(weekdays=current_weekdays)
            keyboard = get_weekday_keyboard(selected_weekdays=current_weekdays)
            await callback.message.answer(LEXICON_RU["msg_event_edit_weekdays"], reply_markup=keyboard)
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_date)
async def update_event_date(message: Message, state: FSMContext, scheduler: AsyncIOScheduler):
    try:
        naive = datetime.strptime(message.text.replace(',', '.'), "%d.%m.%Y %H:%M")
        new_date = naive.replace(tzinfo=MOSCOW_TZ)
        data = await state.get_data()
        event_id = data['event_id']
        await db.update_event(event_id, event_date=new_date)
        bot = message.bot
        remove_event_jobs(event_id, scheduler)
        event = await db.get_event(event_id)
        if event:
            await schedule_event_jobs(event, bot, scheduler)
        await message.answer(LEXICON_RU["msg_event_date_updated"])
        await state.clear()
    except ValueError:
        await message.reply(LEXICON_RU["err_event_invalid_date_format"], parse_mode="HTML")

@router.callback_query(EventCreationAction.filter(F.action == "toggle_weekday"), EventEditStates.waiting_for_new_weekday)
async def update_event_weekday_toggle(callback: CallbackQuery, state: FSMContext, callback_data: EventCreationAction):
    data = await state.get_data()
    selected = set(data.get('weekdays', []))
    weekday = callback_data.weekday
    if weekday in selected:
        selected.remove(weekday)
    else:
        selected.add(weekday)
    selected_list = sorted(list(selected))
    await state.update_data(weekdays=selected_list)
    keyboard = get_weekday_keyboard(selected_weekdays=selected_list)
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except TelegramBadRequest:
        pass
    await callback.answer()

@router.callback_query(EventCreationAction.filter(F.action == "confirm_weekdays"), EventEditStates.waiting_for_new_weekday)
async def update_event_weekday_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get('weekdays', [])
    if not selected:
        await callback.answer(LEXICON_RU["err_event_no_weekdays_selected"], show_alert=True)
        return
    weekday_str = ",".join(map(str, sorted(selected)))
    await state.update_data(weekday=weekday_str)
    await state.set_state(EventEditStates.waiting_for_new_time)
    
    text = LEXICON_RU["msg_event_edit_time_recurring"].format(weekdays=format_weekdays(weekday_str))
    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except TelegramBadRequest:
        await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_time)
async def update_event_time(message: Message, state: FSMContext, scheduler: AsyncIOScheduler):
    try:
        new_time = datetime.strptime(message.text, "%H:%M").time()
        data = await state.get_data()
        event_id = data['event_id']
        weekday = data['weekday']
        await db.update_event(event_id, weekday=weekday, event_time=new_time)
        bot = message.bot
        remove_event_jobs(event_id, scheduler)
        event = await db.get_event(event_id)
        if event:
            await schedule_event_jobs(event, bot, scheduler)
        await message.answer(LEXICON_RU["msg_event_schedule_updated"])
        await state.clear()
    except ValueError:
        await message.reply(LEXICON_RU["err_event_invalid_time_format"], parse_mode="HTML")

@router.callback_query(EventEditAction.filter(F.action == "cost"))
async def process_edit_event_cost(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_cost)
    event = await db.get_event(event_id)
    current_cost = format_amount(event['cost'])
    text = LEXICON_RU["msg_event_edit_cost"].format(current_cost=current_cost, currency_symbol=CURRENCY_SYMBOL)
    if event['activity_id'] == 1:
        text += LEXICON_RU["msg_event_edit_cost_warning"]
    text += LEXICON_RU["msg_event_edit_cost_prompt"]
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
        await message.answer(LEXICON_RU["msg_event_cost_updated"])
        await state.clear()
    except (InvalidOperation, ValueError):
        await message.reply(LEXICON_RU["err_event_invalid_cost"])

@router.callback_query(EventEditAction.filter(F.action == "link"))
async def process_edit_event_link(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_link)
    event = await db.get_event(event_id)
    await callback.message.edit_text(
        LEXICON_RU["msg_event_edit_link"].format(current_link=event['link']),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_link)
async def update_event_link(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data['event_id']
    await db.update_event(event_id, link=message.text)
    await message.answer(LEXICON_RU["msg_event_link_updated"])
    await state.clear()

@router.callback_query(EventEditAction.filter(F.action == "reminder"))
async def process_edit_event_reminder(callback: CallbackQuery, state: FSMContext, callback_data: EventEditAction):
    event_id = callback_data.event_id
    await state.update_data(event_id=event_id)
    await state.set_state(EventEditStates.waiting_for_new_reminder_time)
    event = await db.get_event(event_id)
    current_time = event['reminder_time'] or 0
    current_time_str = f"За {current_time} мин." if current_time else LEXICON_RU["msg_event_no_reminder"]
    await callback.message.edit_text(
        LEXICON_RU["msg_event_edit_reminder_time"].format(current_time_str=current_time_str),
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(EventEditStates.waiting_for_new_reminder_time)
async def update_event_reminder_time(message: Message, state: FSMContext, scheduler: AsyncIOScheduler):
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
                LEXICON_RU["msg_event_edit_reminder_text"].format(vars_help=REMINDER_VARIABLES_HELP_TEXT),
                parse_mode="HTML"
            )
        else:
            await db.update_event(event_id, reminder_time=0, reminder_text=None)
            try:
                scheduler.remove_job(f"event_reminder_{event_id}")
            except Exception:
                pass
            await message.answer(LEXICON_RU["msg_event_reminder_disabled"])
            await state.clear()
    except ValueError:
        await message.reply(LEXICON_RU["err_event_invalid_reminder_time"])

@router.message(EventEditStates.waiting_for_new_reminder_text)
async def update_event_reminder_text(message: Message, state: FSMContext, scheduler: AsyncIOScheduler):
    data = await state.get_data()
    event_id = data['event_id']
    reminder_time = data['reminder_time']
    reminder_text = message.text if message.text != '.' else LEXICON_RU["default_reminder"]
    await db.update_event(event_id, reminder_time=reminder_time, reminder_text=reminder_text)
    bot = message.bot
    event = await db.get_event(event_id)
    remove_event_jobs(event_id, scheduler)
    if event:
        await schedule_event_jobs(event, bot, scheduler)
    await message.answer(LEXICON_RU["msg_event_reminder_updated"])
    await state.clear()
