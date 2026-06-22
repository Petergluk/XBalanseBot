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
from datetime import date
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.callbacks import (
    GeneralAction, ActivityAction, ActivityEditAction, EventAction,
    EventEditAction, EventCreationAction, SettingsAction, TransferAction,
    ConfirmDeleteAction, OfferAction
)
from app.utils import get_next_run_time, format_weekdays, parse_weekdays
from app.lexicon import LEXICON_RU

MSK_LABEL = "MSK"

WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
MONTHS_RU = [
    "Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
    "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря"
]
ACTIVITY_ICONS = ["🧘‍♀️", "☀️", "🌀", "🌐", "☸️", "☯️", "🕉", "🧿", "🏛", "🥁", "🎨", "📚", "💡", "🚀"]

def get_main_menu_keyboard(is_member: bool = False) -> InlineKeyboardMarkup:
    """Создает клавиатуру главного меню."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_menu_send"], callback_data=GeneralAction(action="menu_send").pack()))
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_menu_create_offer"], callback_data=GeneralAction(action="menu_create_offer").pack()))
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_menu_activity"], callback_data=GeneralAction(action="menu_activity").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_menu_event"], callback_data=GeneralAction(action="menu_event").pack())
    )
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_menu_balance"], callback_data=GeneralAction(action="menu_balance_history").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_menu_help"], callback_data=GeneralAction(action="menu_help").pack())
    )
    if not is_member:
        builder.row(
            InlineKeyboardButton(text="👥 Войти в группу", callback_data=GeneralAction(action="get_invite_link").pack())
        )
    return builder.as_markup()

def get_onboarding_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для согласия с правилами сообщества."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_onboarding_agree"], callback_data=GeneralAction(action="onboarding_agree").pack()))
    return builder.as_markup()

def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопкой "Назад в меню"."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_back_to_menu"], callback_data=GeneralAction(action="main_menu").pack()))
    return builder.as_markup()

def get_back_to_settings_keyboard(setting_action: str = None) -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой Назад для возврата в меню настроек из FSM."""
    builder = InlineKeyboardBuilder()
    if setting_action:
        builder.row(InlineKeyboardButton(text="🔄 Восстановить по умолчанию", callback_data=SettingsAction(action=f"reset_{setting_action}").pack()))
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=SettingsAction(action="back_to_settings").pack()))
    return builder.as_markup()

async def get_welcome_bonus_setting_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для меню настройки Welcome-бонуса с кнопкой редактирования приветствия."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_edit_message"], callback_data=SettingsAction(action="edit_bonus_message").pack()))
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=SettingsAction(action="back_to_settings").pack()))
    return builder.as_markup()
    
def confirm_delete_keyboard(item_type: str, item_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с подтверждением удаления."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_yes_delete"], callback_data=ConfirmDeleteAction(item_type=item_type, item_id=item_id).pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()
    
def get_transfer_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для подтверждения перевода."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_confirm"], callback_data=TransferAction(action="confirm").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=TransferAction(action="cancel").pack())
    )
    return builder.as_markup()

def get_use_default_keyboard(button_text: str, callback_data: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с одной кнопкой для использования значения по умолчанию."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=button_text, callback_data=callback_data))
    return builder.as_markup()

def get_event_creation_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для финального подтверждения создания события."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_save"], callback_data=EventCreationAction(action="confirm_create").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()

async def get_activities_keyboard(activities: list, user_subscriptions_ids: set, is_admin: bool) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком активностей-категорий."""
    builder = InlineKeyboardBuilder()
    for activity in activities:
        is_subscribed = activity['id'] in user_subscriptions_ids
        display_name = activity['name']
        if activity['id'] == 1:
            display_name = LEXICON_RU["text_general_events"]
            icon = "✅" if is_subscribed else "📢"
            button_text = f"{icon} {display_name}"
        else:
            base_icon = ACTIVITY_ICONS[activity['id'] % len(ACTIVITY_ICONS)]
            icon = "✅" if is_subscribed else base_icon
            button_text = f"{icon} {display_name}"
            
        builder.row(InlineKeyboardButton(text=button_text, callback_data=ActivityAction(action="view", activity_id=activity['id']).pack()))
    
    if is_admin:
        builder.row(
            InlineKeyboardButton(text=LEXICON_RU["btn_create_activity"], callback_data=GeneralAction(action="admin_create_activity").pack()),
            InlineKeyboardButton(text=LEXICON_RU["btn_edit_activities_desc"], callback_data=SettingsAction(action="edit_activities_desc").pack())
        )
    
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_back_to_menu"], callback_data=GeneralAction(action="main_menu").pack()))
    return builder.as_markup()

async def get_activity_view_keyboard(activity_name: str, activity_id: int, events: list, is_subscribed: bool, is_admin: bool) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для детального просмотра активности.
    Для администраторов добавляет панель управления.
    """
    builder = InlineKeyboardBuilder()
    
    actual_events = [
        e for e in events
        if get_next_run_time(
            e['event_type'],
            e.get('event_date'),
            e.get('weekday'),
            e.get('event_time'),
            e.get('last_run'),
            e.get('end_date'),
        ) is not None
    ]
    
    for event in actual_events:
        event_name_display = event['name'] or activity_name
        next_run_dt = get_next_run_time(
            event['event_type'], event.get('event_date'), event.get('weekday'), 
            event.get('event_time'), event.get('last_run'), event.get('end_date')
        )
        date_str = ""
        if next_run_dt:
            weekday_name = WEEKDAYS_RU[next_run_dt.weekday()]
            month_name = MONTHS_RU[next_run_dt.month - 1]
            date_str = f" ({weekday_name}, {next_run_dt.day} {month_name})"
        
        button_text = f"🗓️ {event_name_display}{date_str}"
        builder.row(InlineKeyboardButton(text=button_text, callback_data=EventAction(action="view_in_activity", event_id=event['id']).pack()))

    if activity_id != 1: # Системную активность нельзя отписывать
        if is_subscribed:
            builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_unsubscribe_activity"], callback_data=ActivityAction(action="unsubscribe_confirm", activity_id=activity_id).pack()))
        else:
            builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_subscribe_all_events"], callback_data=ActivityAction(action="subscribe", activity_id=activity_id).pack()))
            
    if is_admin:
        builder.row(
            InlineKeyboardButton(text=LEXICON_RU["btn_edit"], callback_data=ActivityAction(action="edit_menu", activity_id=activity_id).pack()),
            InlineKeyboardButton(text=LEXICON_RU["btn_create_event"], callback_data=EventCreationAction(action="select_activity", activity_id=activity_id).pack()),
        )
        builder.row(
            InlineKeyboardButton(text=LEXICON_RU["btn_list_subscribers"], callback_data=ActivityAction(action="list_subscribers", activity_id=activity_id).pack()),
            InlineKeyboardButton(text=LEXICON_RU["btn_broadcast"], callback_data=ActivityAction(action="broadcast", activity_id=activity_id).pack()),
        )
        
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_back_to_activities"], callback_data=GeneralAction(action="back_to_activities").pack()))
    return builder.as_markup()


def get_broadcast_confirm_keyboard(activity_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения/отмены рассылки."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=LEXICON_RU["btn_broadcast_confirm"],
            callback_data=ActivityAction(action="broadcast_confirm", activity_id=activity_id).pack()
        ),
        InlineKeyboardButton(
            text=LEXICON_RU["btn_cancel"],
            callback_data=ActivityAction(action="broadcast_cancel", activity_id=activity_id).pack()
        )
    )
    return builder.as_markup()


def get_broadcast_schedule_keyboard(activity_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для выбора: отправить сейчас или запланировать."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=LEXICON_RU["btn_broadcast_now"],
        callback_data=ActivityAction(action="broadcast_now", activity_id=activity_id).pack()
    ))
    builder.row(InlineKeyboardButton(
        text=LEXICON_RU["btn_cancel"],
        callback_data=ActivityAction(action="broadcast_cancel", activity_id=activity_id).pack()
    ))
    return builder.as_markup()

def get_activity_edit_menu_keyboard(activity_id: int) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с опциями редактирования и удаления для конкретной активности.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_edit_name"], callback_data=ActivityEditAction(action="name", activity_id=activity_id).pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_edit_desc"], callback_data=ActivityEditAction(action="description", activity_id=activity_id).pack())
    )
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_delete_activity"], callback_data=ActivityEditAction(action="delete_confirm", activity_id=activity_id).pack())
    )
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_back_to_activity_view"], callback_data=ActivityAction(action="view", activity_id=activity_id).pack())
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
        text = LEXICON_RU["btn_registered_manual"].format(date_str=date_str)
        cb = EventAction(action="cancel", event_id=event_id, target_date=next_run_date).pack()
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "registered_auto":
        text = LEXICON_RU["btn_registered_auto"].format(date_str=date_str)
        cb = EventAction(action="cancel", event_id=event_id, target_date=next_run_date).pack()
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "unregistered":
        text = LEXICON_RU["btn_register_event"].format(date_str=date_str)
        cb = EventAction(action="register", event_id=event_id, target_date=next_run_date).pack()
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    elif registration_status == "cancelled_auto":
        text = LEXICON_RU["btn_cancelled_auto"].format(date_str=date_str)
        cb = EventAction(action="register", event_id=event_id, target_date=next_run_date).pack()
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))

    # Блок администратора
    if is_admin:
        admin_buttons = [
            InlineKeyboardButton(text=LEXICON_RU["btn_edit"], callback_data=EventAction(action="edit_menu", event_id=event_id).pack()),
            InlineKeyboardButton(text=LEXICON_RU["btn_delete"], callback_data=EventAction(action="delete_confirm", event_id=event_id).pack())
        ]
        builder.row(*admin_buttons)
        
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_back_to_activity"], callback_data=ActivityAction(action="view", activity_id=activity_id).pack()))
    return builder.as_markup()

async def get_activities_keyboard_for_event(activities: list) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком активностей для выбора при создании события."""
    builder = InlineKeyboardBuilder()
    for activity in activities:
        display_name = LEXICON_RU["text_general_events_for_all"] if activity['id'] == 1 else activity['name']
        builder.row(InlineKeyboardButton(text=display_name, callback_data=EventCreationAction(action="select_activity", activity_id=activity['id']).pack()))
    return builder.as_markup()

async def get_events_keyboard(events: list) -> InlineKeyboardMarkup:
    """Создает клавиатуру со списком событий."""
    builder = InlineKeyboardBuilder()
    weekdays_map = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    
    for event_row in events:
        event = dict(event_row)
        next_run = get_next_run_time(
            event['event_type'],
            event.get('event_date'),
            event.get('weekday'),
            event.get('event_time'),
            event.get('last_run'),
            event.get('end_date'),
        )
        
        if not next_run: continue # Пропускаем события без будущих запусков

        date_str = next_run.strftime('%-d.%m')  # без ведущего нуля
        weekday_name = weekdays_map[next_run.weekday()]
        time_str = next_run.strftime('%H:%M')
       
        display_name = event.get('name') or event.get('activity_name')
        text = f"– {weekday_name} ({date_str}) – {display_name} | {time_str} {MSK_LABEL}"
        builder.row(InlineKeyboardButton(text=text, callback_data=EventAction(action="view", event_id=event['id']).pack()))
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_back_to_menu"], callback_data=GeneralAction(action="main_menu").pack()))
    return builder.as_markup()

async def get_event_details_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для детального просмотра события."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_back_to_events"], callback_data=GeneralAction(action="back_to_events").pack()))
    return builder.as_markup()

async def get_event_edit_keyboard(event_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с опциями редактирования для события."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_event_name"], callback_data=EventEditAction(action="name", event_id=event_id).pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_event_desc"], callback_data=EventEditAction(action="description", event_id=event_id).pack())
    )
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_event_schedule"], callback_data=EventEditAction(action="schedule", event_id=event_id).pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_event_cost"], callback_data=EventEditAction(action="cost", event_id=event_id).pack())
    )
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_event_link"], callback_data=EventEditAction(action="link", event_id=event_id).pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_event_reminder"], callback_data=EventEditAction(action="reminder", event_id=event_id).pack())
    )
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=SettingsAction(action="back_to_settings").pack()))
    return builder.as_markup()

def get_weekday_keyboard(selected_weekdays: list[int] = None) -> InlineKeyboardMarkup:
    """Создает клавиатуру для множественного выбора дней недели."""
    if selected_weekdays is None:
        selected_weekdays = []
        
    builder = InlineKeyboardBuilder()
    weekdays = {"Пн": 0, "Вт": 1, "Ср": 2, "Чт": 3, "Пт": 4, "Сб": 5, "Вс": 6}
    
    buttons = []
    for day_label, idx in weekdays.items():
        text = f"✅ {day_label}" if idx in selected_weekdays else day_label
        buttons.append(InlineKeyboardButton(text=text, callback_data=EventCreationAction(action="toggle_weekday", weekday=idx).pack()))
        
    builder.row(*buttons)
    
    if selected_weekdays:
        builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_done_confirm"], callback_data=EventCreationAction(action="confirm_weekdays").pack()))
        
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack()))
    return builder.as_markup()

async def get_settings_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру главного меню настроек."""
    builder = InlineKeyboardBuilder()
    # 1. Широкая кнопка на 2 колонки
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_menu_demurrage"], callback_data=SettingsAction(action="menu_demurrage").pack()))
    
    # Тексты (левая колонка) | Деньги и поощрения (правая колонка)
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_edit_welcome_bot"], callback_data=SettingsAction(action="edit_welcome_bot").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_welcome_bonus"], callback_data=SettingsAction(action="set_welcome_bonus").pack())
    )
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_menu_welcome_group"], callback_data=SettingsAction(action="edit_welcome_group").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_exchange_rate"], callback_data=SettingsAction(action="set_exchange_rate").pack())
    )
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_edit_reminder"], callback_data=SettingsAction(action="edit_reminder").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_tag_rules"], callback_data=SettingsAction(action="menu_tag_rules").pack())
    )
    
    # Кнопка настройки топиков
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_menu_topics"], callback_data=SettingsAction(action="menu_topics").pack()))
    return builder.as_markup()


def get_topics_settings_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру настроек топиков."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Сбросить топик (в общий чат)", callback_data=SettingsAction(action="reset_market_thread").pack()))
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_back"], callback_data=SettingsAction(action="back_to_settings").pack()))
    return builder.as_markup()

async def get_demurrage_settings_keyboard(is_enabled: bool) -> InlineKeyboardMarkup:
    """Создает клавиатуру подменю демерреджа."""
    builder = InlineKeyboardBuilder()
    if is_enabled:
        toggle_text = LEXICON_RU["btn_demurrage_on"]
        toggle_callback = SettingsAction(action="toggle_demurrage", enabled=False).pack()
    else:
        toggle_text = LEXICON_RU["btn_demurrage_off"]
        toggle_callback = SettingsAction(action="toggle_demurrage", enabled=True).pack()
    
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=toggle_callback),
        InlineKeyboardButton(text=LEXICON_RU["btn_demurrage_rate"], callback_data=SettingsAction(action="set_demurrage_rate").pack())
    )
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_back"], callback_data=SettingsAction(action="back_to_settings").pack()))
    return builder.as_markup()



def get_welcome_group_prompt_keyboard(is_enabled: bool, setting_action: str = None) -> InlineKeyboardMarkup:
    """Клавиатура для вложенного промпта редактирования текста группы."""
    builder = InlineKeyboardBuilder()
    if is_enabled:
        toggle_text = LEXICON_RU["btn_welcome_group_on"]
        toggle_callback = SettingsAction(action="toggle_welcome_group", enabled=False).pack()
    else:
        toggle_text = LEXICON_RU["btn_welcome_group_off"]
        toggle_callback = SettingsAction(action="toggle_welcome_group", enabled=True).pack()
    
    builder.row(InlineKeyboardButton(text=toggle_text, callback_data=toggle_callback))
    if setting_action:
        builder.row(InlineKeyboardButton(text="🔄 Восстановить по умолчанию", callback_data=SettingsAction(action=f"reset_{setting_action}").pack()))
    builder.row(InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=SettingsAction(action="back_to_settings").pack()))
    return builder.as_markup()


def get_offer_group_keyboard(offer_id: int, price) -> InlineKeyboardMarkup:
    """Создает клавиатуру для объявления в группе с кнопкой Купить."""
    from app.config import CURRENCY_SYMBOL
    builder = InlineKeyboardBuilder()
    btn_text = LEXICON_RU["btn_buy_offer"].format(price=price, currency_symbol=CURRENCY_SYMBOL)
    builder.row(InlineKeyboardButton(text=btn_text, callback_data=OfferAction(action="buy", offer_id=offer_id).pack()))
    return builder.as_markup()


def get_offer_confirm_keyboard(offer_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру для подтверждения публикации объявления."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_publish"], callback_data=OfferAction(action="publish", offer_id=offer_id).pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()


def get_offer_photo_skip_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для пропуска шага отправки фото."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_skip_photo"], callback_data=GeneralAction(action="skip_photo").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()


def get_offer_desc_skip_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для пропуска шага описания."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_skip_desc"], callback_data=GeneralAction(action="skip_desc").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()


def get_offer_quantity_skip_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для пропуска шага количества."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_skip_quantity"], callback_data=GeneralAction(action="skip_quantity").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()


def get_offer_duration_skip_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру для пропуска шага срока актуальности."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=LEXICON_RU["btn_skip_duration"], callback_data=GeneralAction(action="skip_duration").pack()),
        InlineKeyboardButton(text=LEXICON_RU["btn_cancel"], callback_data=GeneralAction(action="cancel_dialog").pack())
    )
    return builder.as_markup()
