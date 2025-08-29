# XBalanseBot/app/keyboards.py
# FULL FILE EMITTED: YES
# v2.5.1
# 2025-08-29 04:15:00
"""
Модуль для создания инлайн-клавиатур.

Версия 2.5.1:
- Полностью переведена логика создания callback_data на использование фабрик
  из `app.callbacks`, что повышает надежность и читаемость кода.
- Удалены устаревшие методы генерации callback_data на основе строк.

Версия 2.5.0:
- НОВАЯ ФУНКЦИЯ: `get_use_default_keyboard` - создает клавиатуру с кнопкой
  для использования значения по умолчанию (например, описания активности).
- НОВАЯ ФУНКЦИЯ: `get_event_creation_confirmation_keyboard` - создает
  клавиатуру для финального подтверждения создания события (`Сохранить`, `Отмена`).
- Исправлена ошибка в `get_activity_view_keyboard`: добавлена проверка на None для `get_next_run_time`.
"""
import random
from datetime import date
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.callbacks import (
    GeneralAction, ActivityAction, ActivityEditAction, EventAction,
    EventEditAction, EventCreationAction, SettingsAction, TransferAction
)
from app.utils import get_next_run_time

MSK_LABEL = "MSK"

WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
MONTHS_RU = [
    "Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
    "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"
]
ACTIVITY_ICONS = ["🧘‍♀️", "☀️", "🌀", "🌐", "☸️", "☯️", "🕉", "🧿", "🏛", "🥁", "🎨", "📚", "💡", "🚀"]

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру главного меню."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Перевести Ӫ другому участнику", callback_data=GeneralAction(action="menu_send").pack()))
    builder.row(
        InlineKeyboardButton(text="💰 Мой Баланс", callback_data=GeneralAction(action="menu_balance").pack()),
        InlineKeyboardButton(text="📜 История транзакций", callback_data=GeneralAction(action="menu_history").pack())
    )
    builder.row(
        InlineKeyboardButton(text="🎨 Активности", callback_data=GeneralAction(action="menu_activity").pack()),
        InlineKeyboardButton(text="📅 Ближайшие события", callback_data=GeneralAction(action="menu_event").pack())
    )
    builder.row(InlineKeyboardButton(text="📖 Справка", callback_data=GeneralAction(action="menu_help").pack()))
    return builder.as_markup()

def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой "Назад в меню"."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=GeneralAction(action="main_menu").pack()))
    return builder.as_markup()

def get_back_to_settings_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой "Назад в меню настроек"."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data=SettingsAction(action="view").pack()))
    return builder.as_markup()
    
def confirm_delete_keyboard(item_type: str, item_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с подтверждением удаления."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=GeneralAction(action=f"confirm_final_delete_{item_type}_{item_id}").pack()),
        InlineKeyboardButton(text="❌ Отмена", callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()
    
def get_transfer_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для подтверждения перевода."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=TransferAction(action="confirm").pack()),
        InlineKeyboardButton(text="❌ Отмена", callback_data=TransferAction(action="cancel").pack())
    )
    return builder.as_markup()

def get_use_default_keyboard(button_text: str, callback_data_action: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с одной кнопкой для использования значения по умолчанию."""
    builder = InlineKeyboardBuilder()
    # Используем GeneralAction для простых действий, где не нужен ID сущности
    builder.row(InlineKeyboardButton(text=button_text, callback_data=GeneralAction(action=callback_data_action).pack()))
    return builder.as_markup()

def get_event_creation_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для финального подтверждения создания события."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Сохранить", callback_data=EventCreationAction(action="confirm_create").pack()),
        InlineKeyboardButton(text="❌ Отмена", callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()

async def get_activities_keyboard(activities: list, user_subscriptions_ids: set, is_admin: bool) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком активностей-категорий."""
    builder = InlineKeyboardBuilder()
    for activity in activities:
        is_subscribed = activity['id'] in user_subscriptions_ids
        icon = "✅" if is_subscribed else ACTIVITY_ICONS[activity['id'] % len(ACTIVITY_ICONS)]
        
        builder.row(InlineKeyboardButton(text=f"{icon} {activity['name']}", callback_data=ActivityAction(action="view", activity_id=activity['id']).pack()))
    
    if is_admin:
        builder.row(InlineKeyboardButton(text="➕ Создать новую активность", callback_data=GeneralAction(action="admin_create_activity").pack()))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=GeneralAction(action="main_menu").pack()))
    return builder.as_markup()

async def get_activity_view_keyboard(activity_name: str, activity_id: int, events: list, is_subscribed: bool, is_admin: bool) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для детального просмотра активности.
    Для администраторов добавляет панель управления.
    """
    builder = InlineKeyboardBuilder()
    
    actual_events = [e for e in events if get_next_run_time(e['event_type'], e.get('event_date'), e.get('weekday'), e.get('event_time'), e.get('last_run')) is not None]
    
    for event in actual_events:
        event_name_display = event['name'] or activity_name
        next_run_dt = get_next_run_time(
            event['event_type'], event.get('event_date'), event.get('weekday'), 
            event.get('event_time'), event.get('last_run')
        )
        date_str = ""
        if next_run_dt:
            weekday_name = WEEKDAYS_RU[next_run_dt.weekday()]
            month_name = MONTHS_RU[next_run_dt.month - 1]
            date_str = f" ({weekday_name}, {next_run_dt.day} {month_name})"
        
        button_text = f"🗓️ {event_name_display}{date_str}"
        builder.row(InlineKeyboardButton(text=button_text, callback_data=EventAction(action="view", event_id=event['id']).pack()))

    if activity_id != 1: # Системную активность нельзя отписывать
        if is_subscribed:
            builder.row(InlineKeyboardButton(text="✅ Вы подписаны (Отписаться)", callback_data=ActivityAction(action="unsubscribe", activity_id=activity_id).pack()))
        else:
            builder.row(InlineKeyboardButton(text="🔔 Подписаться на все события", callback_data=ActivityAction(action="subscribe", activity_id=activity_id).pack()))
            
    if is_admin:
        admin_buttons = [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=ActivityAction(action="edit_menu", activity_id=activity_id).pack()),
            InlineKeyboardButton(text="➕ Создать событие", callback_data=ActivityAction(action="create_event_for", activity_id=activity_id).pack()),
            InlineKeyboardButton(text="👥 Список подписчиков", callback_data=ActivityAction(action="list_subscribers", activity_id=activity_id).pack())
        ]
        builder.row(*admin_buttons)
        
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=GeneralAction(action="back_to_activities").pack()))
    return builder.as_markup()

def get_activity_edit_menu_keyboard(activity_id: int) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с опциями редактирования и удаления для конкретной активности.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📝 Изменить название", callback_data=ActivityEditAction(action="name", activity_id=activity_id).pack()),
        InlineKeyboardButton(text="📄 Изменить описание", callback_data=ActivityEditAction(action="description", activity_id=activity_id).pack())
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Удалить активность", callback_data=ActivityEditAction(action="delete_confirm", activity_id=activity_id).pack())
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад к просмотру", callback_data=ActivityAction(action="view", activity_id=activity_id).pack())
    )
    return builder.as_markup()

async def get_event_view_keyboard(event_id: int, activity_id: int, next_run_date: date, registration_status: str, is_admin: bool) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для просмотра события.
    Для администраторов добавляет панель управления.
    """
    builder = InlineKeyboardBuilder()
    date_str = next_run_date.strftime('%d.%m')
    
    # Блок регистрации для пользователя
    if registration_status == "registered_manual":
        text = f"✅ Вы записаны на {date_str} (Отменить)"
        cb = EventAction(action="cancel", event_id=event_id, target_date=next_run_date).pack()
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "registered_auto":
        text = f"✅ Авто-запись на {date_str} (Отменить)"
        cb = EventAction(action="cancel", event_id=event_id, target_date=next_run_date).pack()
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "unregistered":
        text = f"➕ Записаться на {date_str}"
        cb = EventAction(action="register", event_id=event_id, target_date=next_run_date).pack()
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "cancelled_auto":
        text = f"❌ Вы отменили запись на {date_str} (Вернуть)"
        cb = EventAction(action="register", event_id=event_id, target_date=next_run_date).pack()
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))

    # Блок администратора
    if is_admin:
        admin_buttons = [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=EventAction(action="edit_menu", event_id=event_id).pack()),
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=EventAction(action="delete_confirm", event_id=event_id).pack())
        ]
        builder.row(*admin_buttons)
        
    builder.row(InlineKeyboardButton(text="⬅️ Назад к активности", callback_data=ActivityAction(action="view", activity_id=activity_id).pack()))
    return builder.as_markup()

async def get_activities_keyboard_for_event(activities: list) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком активностей для выбора при создании события."""
    builder = InlineKeyboardBuilder()
    for activity in activities:
        display_name = f"{activity['name']} (для всех)" if activity['id'] == 1 else activity['name']
        builder.row(InlineKeyboardButton(text=display_name, callback_data=EventCreationAction(action="select_activity", activity_id=activity['id']).pack()))
    return builder.as_markup()

async def get_events_keyboard(events: list) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком событий."""
    builder = InlineKeyboardBuilder()
    weekdays_map = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    
    for event_row in events:
        event = dict(event_row)
        next_run = get_next_run_time(event['event_type'], event.get('event_date'), event.get('weekday'), event.get('event_time'), event.get('last_run'))
        
        if not next_run: continue # Пропускаем события без будущих запусков

        date_str = next_run.strftime('%d.%m')
        weekday_str = weekdays_map[next_run.weekday()]
        time_str = next_run.strftime('%H:%M')
        schedule_str = f"{date_str} ({weekday_str}) {time_str} ({MSK_LABEL})"
       
        display_name = event.get('name') or event.get('activity_name')
        text = f"{schedule_str} - {display_name}"
        builder.row(InlineKeyboardButton(text=text, callback_data=EventAction(action="view", event_id=event['id']).pack()))
    builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=GeneralAction(action="main_menu").pack()))
    return builder.as_markup()

async def get_event_details_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для детального просмотра события."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=GeneralAction(action="back_to_events").pack()))
    return builder.as_markup()

async def get_event_edit_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с опциями редактирования для события."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Название", callback_data=EventEditAction(action="name", event_id=event_id).pack()),
        InlineKeyboardButton(text="Описание", callback_data=EventEditAction(action="description", event_id=event_id).pack())
    )
    builder.row(
        InlineKeyboardButton(text="Расписание", callback_data=EventEditAction(action="schedule", event_id=event_id).pack()),
        InlineKeyboardButton(text="Стоимость", callback_data=EventEditAction(action="cost", event_id=event_id).pack())
    )
    builder.row(
        InlineKeyboardButton(text="Ссылку", callback_data=EventEditAction(action="link", event_id=event_id).pack()),
        InlineKeyboardButton(text="Напоминание", callback_data=EventEditAction(action="reminder", event_id=event_id).pack())
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад к просмотру события", callback_data=EventAction(action="view", event_id=event_id).pack()))
    return builder.as_markup()

def get_weekday_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для выбора дня недели."""
    builder = InlineKeyboardBuilder()
    weekdays = {"Пн": 0, "Вт": 1, "Ср": 2, "Чт": 3, "Пт": 4, "Сб": 5, "Вс": 6}
    buttons = [InlineKeyboardButton(text=day, callback_data=EventCreationAction(action="select_weekday", weekday=idx).pack()) for day, idx in weekdays.items()]
    builder.row(*buttons)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=GeneralAction(action="cancel_dialog").pack()))
    return builder.as_markup()

async def get_settings_keyboard(is_demurrage_enabled: bool) -> InlineKeyboardMarkup:
    """Создает клавиатуру меню настроек."""
    builder = InlineKeyboardBuilder()
    if is_demurrage_enabled:
        toggle_text = "✅ Демерредж ВКЛЮЧЕН"
        toggle_callback = SettingsAction(action="toggle_demurrage", enabled=False).pack()
    else:
        toggle_text = "❌ Демерредж ВЫКЛЮЧЕН"
        toggle_callback = SettingsAction(action="toggle_demurrage", enabled=True).pack()
    
    builder.row(InlineKeyboardButton(text=toggle_text, callback_data=toggle_callback))
    builder.row(
        InlineKeyboardButton(text="❇️ Welcome-бонус", callback_data=SettingsAction(action="set_welcome_bonus").pack()),
        InlineKeyboardButton(text="💹 Курс обмена", callback_data=SettingsAction(action="set_exchange_rate").pack())
    )
    builder.row(
        InlineKeyboardButton(text="🔣 % Демерреджа", callback_data=SettingsAction(action="set_demurrage_rate").pack()),
        InlineKeyboardButton(text="✏️ Шаблон напоминания", callback_data=SettingsAction(action="edit_reminder").pack())
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Приветствие (бот)", callback_data=SettingsAction(action="edit_welcome_bot").pack()),
        InlineKeyboardButton(text="✏️ Приветствие (группа)", callback_data=SettingsAction(action="edit_welcome_group").pack())
    )
    builder.row(InlineKeyboardButton(text="📊 Статус демерреджа", callback_data=SettingsAction(action="demurrage_status").pack()))
    return builder.as_markup()
