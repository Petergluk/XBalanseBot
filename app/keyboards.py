# XBalanseBot/app/keyboards.py
# v1.5.5
# 2025-08-27 02:40:00
"""
Модуль для создания инлайн-клавиатур.

Версия 1.5.5:
- ИЗМЕНЕНИЕ: Функции `get_activities_keyboard` и `get_activity_view_keyboard`
  теперь принимают флаг `is_admin`.
- НОВОЕ: Если `is_admin=True`, на клавиатурах динамически отображаются
  кнопки для администрирования ("Создать активность", "Создать событие" и т.д.).
"""
import random
from datetime import date
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.utils import get_next_run_time

MSK_LABEL = "MSK"

WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
MONTHS_RU = [
    "Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
    "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"
]
ACTIVITY_ICONS = ["🧘‍♀️", "☀️", "🌀", "🌐", "☸️", "☯️", "🕉", "🧿", "🏛", "🥁", "🎨", "📚", "💡", "🚀"]

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Перевести Ӫ другому участнику", callback_data="menu_send"))
    builder.row(
        InlineKeyboardButton(text="💰 Мой Баланс", callback_data="menu_balance"),
        InlineKeyboardButton(text="📜 История транзакций", callback_data="menu_history")
    )
    builder.row(
        InlineKeyboardButton(text="🎨 Активности", callback_data="menu_activity"),
        InlineKeyboardButton(text="📅 Ближайшие события", callback_data="menu_event")
    )
    builder.row(InlineKeyboardButton(text="📖 Справка", callback_data="menu_help"))
    return builder.as_markup()

def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="main_menu"))
    return builder.as_markup()

def confirm_delete_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=callback_data),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete")
    )
    return builder.as_markup()
    
def get_transfer_confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="transfer_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="transfer_cancel")
    )
    return builder.as_markup()

async def get_activities_keyboard(activities: list, user_subscriptions_ids: set, is_admin: bool, action: str = "view_cat") -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком активностей-категорий."""
    builder = InlineKeyboardBuilder()
    for activity in activities:
        is_subscribed = activity['id'] in user_subscriptions_ids
        icon = "✅" if is_subscribed else random.choice(ACTIVITY_ICONS)
        
        if action == "view_cat":
            cb = f"view_activity_{activity['id']}"
        else: # admin edit/delete
            cb = f"{action}_activity_{activity['id']}"
            
        builder.row(InlineKeyboardButton(text=f"{icon} {activity['name']}", callback_data=cb))
    
    # Добавляем админские кнопки
    if is_admin and action == "view_cat":
        builder.row(InlineKeyboardButton(text="➕ Создать новую активность", callback_data="admin_create_activity"))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="main_menu"))
    return builder.as_markup()

async def get_activity_view_keyboard(activity_name: str, activity_id: int, events: list, is_subscribed: bool, is_admin: bool) -> InlineKeyboardMarkup:
    """Создает клавиатуру для детального просмотра активности со списком ее событий."""
    builder = InlineKeyboardBuilder()
    
    for event in events:
        event_name = event['name'] or activity_name
        next_run_dt = get_next_run_time(
            event['event_type'], event.get('event_date'), event.get('weekday'), 
            event.get('event_time'), event.get('last_run')
        )
        
        date_str = ""
        if next_run_dt:
            weekday_name = WEEKDAYS_RU[next_run_dt.weekday()]
            month_name = MONTHS_RU[next_run_dt.month - 1]
            date_str = f" ({weekday_name}, {next_run_dt.day} {month_name})"
        
        button_text = f"🗓️ {event_name}{date_str}"
        builder.row(InlineKeyboardButton(text=button_text, callback_data=f"view_event_{event['id']}"))
    
    # Добавляем админские кнопки
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="➕ Создать событие", callback_data=f"admin_create_event_for_{activity_id}"),
            InlineKeyboardButton(text="👥 Подписчики", callback_data=f"admin_list_subscribers_{activity_id}")
        )
        
    if activity_id != 1:
        if is_subscribed:
            builder.row(InlineKeyboardButton(text="✅ Вы подписаны (Отписаться от всех)", callback_data=f"unsubscribe_act_{activity_id}"))
        else:
            builder.row(InlineKeyboardButton(text="🔔 Подписаться на все события", callback_data=f"subscribe_act_{activity_id}"))
            
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_activities"))
    return builder.as_markup()

def get_event_view_keyboard(event_id: int, activity_id: int, next_run_date: date, registration_status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    date_str = next_run_date.strftime('%d.%m')
    
    if registration_status == "registered_manual":
        text = f"✅ Вы записаны на {date_str} (Отменить)"
        cb = f"cancel_reg_{event_id}_{next_run_date.isoformat()}"
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "registered_auto":
        text = f"✅ Авто-запись на {date_str} (Отменить)"
        cb = f"cancel_reg_{event_id}_{next_run_date.isoformat()}"
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "unregistered":
        text = f"➕ Записаться на {date_str}"
        cb = f"register_reg_{event_id}_{next_run_date.isoformat()}"
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "cancelled_auto":
        text = f"❌ Вы отменили запись на {date_str} (Вернуть)"
        cb = f"register_reg_{event_id}_{next_run_date.isoformat()}"
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
        
    builder.row(InlineKeyboardButton(text="⬅️ Назад к активности", callback_data=f"view_activity_{activity_id}"))
    return builder.as_markup()

async def get_activities_keyboard_for_event(activities: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for activity in activities:
        if activity['id'] == 1:
            builder.row(InlineKeyboardButton(text=f"{activity['name']} (для всех)", callback_data=f"select_activity_1"))
        else:
            builder.row(InlineKeyboardButton(text=activity['name'], callback_data=f"select_activity_{activity['id']}"))
    return builder.as_markup()

async def get_events_keyboard(events: list, action: str = "view") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    weekdays_map = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    for event_row in events:
        event = dict(event_row)
        next_run = get_next_run_time(event['event_type'], event.get('event_date'), event.get('weekday'), event.get('event_time'), event.get('last_run'))
        if next_run:
            date_str = next_run.strftime('%d.%m')
            weekday_str = weekdays_map[next_run.weekday()]
            time_str = next_run.strftime('%H:%M')
            schedule_str = f"{date_str} ({weekday_str}) {time_str} ({MSK_LABEL})"
        else:
            schedule_str = f"Дата не определена ({MSK_LABEL})"
        display_name = event.get('name') or event.get('activity_name')
        text = f"{schedule_str} - {display_name}"
        event_id = event['id']
        if action == "view": cb = f"event_{event_id}"
        elif action == "edit": cb = f"edit_event_{event_id}"
        elif action == "delete": cb = f"delete_event_{event_id}"
        else: cb = f"event_{event_id}"
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="main_menu"))
    return builder.as_markup()

async def get_event_details_keyboard(event_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_events"))
    return builder.as_markup()

async def get_event_edit_keyboard(event_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Название", callback_data=f"edit_evt_name_{event_id}"), InlineKeyboardButton(text="Описание", callback_data=f"edit_evt_description_{event_id}"))
    builder.row(InlineKeyboardButton(text="Расписание", callback_data=f"edit_evt_schedule_{event_id}"), InlineKeyboardButton(text="Стоимость", callback_data=f"edit_evt_cost_{event_id}"))
    builder.row(InlineKeyboardButton(text="Ссылку", callback_data=f"edit_evt_link_{event_id}"), InlineKeyboardButton(text="Напоминание", callback_data=f"edit_evt_reminder_{event_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_events"))
    return builder.as_markup()

def get_weekday_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    weekdays = {"Пн": 0, "Вт": 1, "Ср": 2, "Чт": 3, "Пт": 4, "Сб": 5, "Вс": 6}
    buttons = [InlineKeyboardButton(text=day, callback_data=f"select_weekday_{idx}") for day, idx in weekdays.items()]
    builder.row(*buttons)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete"))
    return builder.as_markup()

async def get_settings_keyboard(is_demurrage_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_demurrage_enabled:
        toggle_text = "✅ Демерредж ВКЛЮЧЕН"
        toggle_callback = "settings_demurrage_off"
    else:
        toggle_text = "❌ Демерредж ВЫКЛЮЧЕН"
        toggle_callback = "settings_demurrage_on"
    builder.row(InlineKeyboardButton(text=toggle_text, callback_data=toggle_callback))
    builder.row(InlineKeyboardButton(text="❇️ Welcome-бонус", callback_data="settings_set_welcome_bonus"), InlineKeyboardButton(text="💹 Курс обмена", callback_data="settings_set_exchange_rate"))
    builder.row(InlineKeyboardButton(text="🔣 % Демерреджа", callback_data="settings_set_demurrage_rate"), InlineKeyboardButton(text="✏️ Шаблон напоминания", callback_data="settings_edit_reminder"))
    builder.row(InlineKeyboardButton(text="✏️ Приветствие (бот)", callback_data="settings_edit_welcome_bot"), InlineKeyboardButton(text="✏️ Приветствие (группа)", callback_data="settings_edit_welcome_group"))
    builder.row(InlineKeyboardButton(text="📊 Статус демерреджа", callback_data="settings_demurrage_status"))
    return builder.as_markup()
