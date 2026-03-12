# XBalanseBot/app/callbacks.py
# v1.0.0
# 2025-08-29 04:15:00
"""
Модуль для определения фабрик CallbackData, используемых в боте.
CallbackData обеспечивает типобезопасный и структурированный способ
обработки данных, передаваемых через инлайн-кнопки, заменяя ручной
парсинг строк.

Версия 1.0.0:
- Инициализация модуля с фабриками CallbackData для всех основных сущностей:
  - `GeneralAction`: Для общих навигационных действий (меню, назад).
  - `ActivityAction`: Для действий, связанных с активностями (просмотр, подписка, редактирование).
  - `ActivityEditAction`: Для специфических действий редактирования активности.
  - `EventAction`: Для действий, связанных с событиями (просмотр, регистрация).
  - `EventEditAction`: Для специфических действий редактирования события.
  - `EventCreationAction`: Для шагов FSM создания события.
  - `SettingsAction`: Для действий в меню настроек.
  - `TransferAction`: Для подтверждения переводов.
"""
from aiogram.filters.callback_data import CallbackData
from typing import Optional
from datetime import date

class GeneralAction(CallbackData, prefix="gen"):
    """
    Общий колбэк для навигационных действий или простых универсальных команд.
    Пример: `action="main_menu"`, `action="back_to_activities"`, `action="cancel_dialog"`
    """
    action: str

class ActivityAction(CallbackData, prefix="act"):
    """
    Колбэк для действий, связанных с активностями.
    Пример: `action="view"`, `action="subscribe"`, `action="unsubscribe"`,
    `action="edit_menu"`, `action="create_event_for"`, `action="list_subscribers"`
    """
    action: str
    activity_id: int

class ActivityEditAction(CallbackData, prefix="act_edit"):
    """
    Колбэк для специфических действий редактирования активности.
    Пример: `action="name"`, `action="description"`, `action="delete_confirm"`,
    `action="delete_final"`
    """
    action: str
    activity_id: int
    field: Optional[str] = None # 'name', 'description'

class EventAction(CallbackData, prefix="evt"):
    """
    Колбэк для действий, связанных с событиями.
    Пример: `action="view"`, `action="register"`, `action="cancel"`,
    `action="edit_menu"`, `action="delete_confirm"`, `action="delete_final"`
    `target_date`: Используется для регистрации/отмены на конкретную дату
                   для регулярных событий.
    """
    action: str
    event_id: int
    target_date: Optional[date] = None

class EventEditAction(CallbackData, prefix="evt_edit"):
    """
    Колбэк для специфических действий редактирования события.
    Пример: `action="name"`, `action="description"`, `action="schedule"`,
    `action="cost"`, `action="link"`, `action="reminder"`
    """
    action: str
    event_id: int
    
class EventCreationAction(CallbackData, prefix="evt_create"):
    """
    Колбэк для шагов FSM при создании события.
    Пример: `action="select_activity"`, `action="use_activity_desc"`,
    `action="set_type"`, `action="select_weekday"`, `action="toggle_weekday"`,
    `action="confirm_weekdays"`, `action="use_default_reminder"`, `action="confirm_create"`
    """
    action: str
    activity_id: Optional[int] = None # Используется при выборе активности или создании события для конкретной активности
    event_type: Optional[str] = None # Используется при установке типа события
    weekday: Optional[int] = None # Используется при выборе и переключении дня недели

class SettingsAction(CallbackData, prefix="set"):
    """
    Колбэк для меню настроек и связанных с ними действий.
    Пример: `action="view"`, `action="toggle_demurrage"`, `action="set_welcome_bonus"`,
    `action="demurrage_status"`, `action="back_to_settings"`
    """
    action: str
    enabled: Optional[bool] = None # Для переключения статуса демерреджа

class TransferAction(CallbackData, prefix="tx"):
    """
    Колбэк для подтверждения или отмены перевода средств.
    Пример: `action="confirm"`, `action="cancel"`
    """
    action: str

class ConfirmDeleteAction(CallbackData, prefix="del"):
    """
    Колбэк для подтверждения удаления сущностей.
    `item_type`: 'activity' или 'event'
    `item_id`: ID удаляемого объекта
    """
    item_type: str
    item_id: int
