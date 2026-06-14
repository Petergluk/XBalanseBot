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
    waiting_for_activities_description = State()
    waiting_for_welcome_bonus_text = State()

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
    waiting_for_end_date = State()  # Дата окончания для регулярных событий
    waiting_for_cost = State()
    waiting_for_link = State()
    waiting_for_reminder_time = State()
    waiting_for_reminder_text = State()
    waiting_for_confirmation = State()

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

class BroadcastStates(StatesGroup):
    """
    Состояния для рассылки сообщений подписчикам активности.
    data: `activity_id`, `activity_name`, `chat_id`, `message_id`
    """
    waiting_for_message = State()
    waiting_for_schedule = State()
    waiting_for_datetime = State()
    waiting_for_confirmation = State()

class TagRuleCreationStates(StatesGroup):
    """
    Состояния для FSM создания правила начисления по хэштегу.
    data: `hashtag`, `min_chars`, `reward`, `limit_amount`, `limit_period_days`,
          `thread_id`, `group_msg`, `bot_msg`, `reaction`
    """
    waiting_for_hashtag = State()
    waiting_for_min_chars = State()
    waiting_for_reward = State()
    waiting_for_limit_amount = State()
    waiting_for_limit_period = State()
    waiting_for_thread_id = State()
    waiting_for_group_msg = State()
    waiting_for_bot_msg = State()
    waiting_for_reaction = State()


class OfferCreationStates(StatesGroup):
    """
    Состояния для FSM создания нового объявления о продаже/обмене.
    data: `message_ids`, `title`, `description`, `price`, `quantity`, `duration_days`, `photo_id`, `confirm_msg_id`
    """
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_price = State()
    waiting_for_quantity = State()
    waiting_for_duration = State()
    waiting_for_photo = State()
    waiting_for_confirmation = State()


