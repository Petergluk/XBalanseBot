# XBalanseBot/app/states.py
# FULL FILE EMITTED: YES
# v1.4.0
# 2025-08-29 00:49:00
"""
Модуль для определения состояний (FSM) бота.

Версия 1.4.0:
- **НОВОЕ**: В `EventCreationStates` добавлено состояние `waiting_for_confirmation`
  для реализации предпросмотра события перед его сохранением.
- В Docstrings добавлено упоминание поля `message_ids`, которое теперь
  хранится в data для очистки диалогов.
"""

from aiogram.fsm.state import State, StatesGroup

class TransferStates(StatesGroup):
    """
    Состояния для процесса перевода средств.
    data: `message_ids`, `recipient_id`, `amount`, `comment`, etc.
    """
    waiting_for_recipient = State()
    waiting_for_amount = State()
    waiting_for_comment = State()
    waiting_for_confirmation = State()

class AdminEditStates(StatesGroup):
    """Состояния для редактирования административных настроек."""
    waiting_for_welcome_text = State()
    waiting_for_welcome_text_group = State()
    waiting_for_demurrage_rate = State()
    waiting_for_demurrage_interval = State()
    waiting_for_exchange_rate = State()
    waiting_for_welcome_bonus = State()
    waiting_for_reminder_text = State()

class FundPaymentStates(StatesGroup):
    """Состояния для процесса выплаты из фонда."""
    waiting_for_amount_and_comment = State()

class ActivityCreationStates(StatesGroup):
    """
    Состояния для процесса создания новой активности.
    data: `message_ids`, `name`, `description`, `end_date`
    """
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_end_date = State()

class ActivityEditStates(StatesGroup):
    """
    Состояния для процесса редактирования существующей активности.
    data: `message_ids`, `activity_id`
    """
    waiting_for_new_name = State()
    waiting_for_new_description = State()
    waiting_for_new_end_date = State()

class EventCreationStates(StatesGroup):
    """
    Состояния для процесса создания нового события.
    data: `message_ids`, `activity_id`, `name`, `description`, etc.
    """
    waiting_for_activity = State()
    waiting_for_event_name = State()
    waiting_for_event_description = State()
    waiting_for_type = State()
    waiting_for_date = State()
    waiting_for_weekday = State()
    waiting_for_time = State()
    waiting_for_cost = State()
    waiting_for_link = State()
    waiting_for_reminder_time = State()
    waiting_for_reminder_text = State()
    waiting_for_confirmation = State() # Новое состояние для предпросмотра

class EventEditStates(StatesGroup):
    """
    Состояния для процесса редактирования существующего события.
    data: `message_ids`, `event_id`, `activity_id`
    """
    waiting_for_field_choice = State()
    waiting_for_new_name = State()
    waiting_for_new_description = State()
    waiting_for_new_date = State()
    waiting_for_new_weekday = State()
    waiting_for_new_time = State()
    waiting_for_new_cost = State()
    waiting_for_new_link = State()
    waiting_for_new_reminder_time = State()
    waiting_for_new_reminder_text = State()
