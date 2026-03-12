# tests/test_handlers.py
"""
Тесты для Telegram-хендлеров, FSM-потоков и callbacks.
Используем unittest.mock.AsyncMock для имитации объектов aiogram.

Запуск: docker compose exec bot python -m pytest tests/test_handlers.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Предварительный импорт модулей в правильном порядке, чтобы избежать circular import
import app.handlers.common  # noqa: F401 — должен быть первым
import app.handlers.user_commands as _uc_mod  # noqa: F401


# --- Mock Helpers ---

def make_user(user_id=382432926, username="testuser", is_bot=False):
    """Создает mock aiogram User."""
    user = MagicMock()
    user.id = user_id
    user.username = username
    user.is_bot = is_bot
    user.full_name = username
    return user


def make_message(text="/start", user_id=382432926, username="testuser", chat_id=382432926):
    """Создает mock aiogram Message."""
    msg = AsyncMock()
    msg.text = text
    msg.from_user = make_user(user_id, username)
    msg.chat = MagicMock()
    msg.chat.id = chat_id
    msg.bot = AsyncMock()
    msg.message_id = 500

    sent = AsyncMock()
    sent.message_id = 999
    msg.answer = AsyncMock(return_value=sent)
    msg.reply = AsyncMock(return_value=sent)
    return msg


def make_callback(data="gen:main_menu", user_id=382432926, username="testuser", chat_id=382432926):
    """Создает mock aiogram CallbackQuery."""
    cb = AsyncMock()
    cb.data = data
    cb.from_user = make_user(user_id, username)
    cb.message = make_message("", user_id, username, chat_id)
    cb.bot = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def make_state(data=None):
    """Создает mock aiogram FSMContext."""
    state = AsyncMock()
    _data = data or {}
    state.get_data = AsyncMock(return_value=_data)
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


# =============================================================================
# Tests: Admin Commands (/users)
# =============================================================================

class TestCmdUsers:

    @pytest.mark.asyncio
    @patch("app.handlers.admin_commands.db")
    async def test_cmd_users_empty(self, mock_db):
        """Если нет пользователей, бот отвечает соответствующим сообщением."""
        from app.handlers.admin_commands import cmd_users
        mock_db.get_all_users = AsyncMock(return_value=[])

        msg = make_message("/users")
        await cmd_users(msg)

        msg.answer.assert_called_once()
        call_text = msg.answer.call_args[0][0]
        assert "пока нет" in call_text.lower()

    @pytest.mark.asyncio
    @patch("app.handlers.admin_commands.db")
    async def test_cmd_users_with_data(self, mock_db):
        """С пользователями — должен показать список с балансами."""
        from app.handlers.admin_commands import cmd_users
        mock_db.get_all_users = AsyncMock(return_value=[
            {'id': 1, 'username': 'alice', 'telegram_id': 1001, 'balance': Decimal('500'), 'is_admin': False},
            {'id': 2, 'username': 'bob', 'telegram_id': 1002, 'balance': Decimal('100'), 'is_admin': True},
        ])

        msg = make_message("/users")
        await cmd_users(msg)

        msg.answer.assert_called_once()
        call_text = msg.answer.call_args[0][0]
        assert "Всего пользователей: 2" in call_text
        assert "@alice" in call_text
        assert "@bob" in call_text
        assert "👮" in call_text  # admin mark for bob


# =============================================================================
# Tests: User Commands (/balance, /send)
# =============================================================================

class TestCmdBalance:

    @pytest.mark.asyncio
    async def test_cmd_balance(self):
        """Команда /balance должна вернуть текущий баланс пользователя."""
        import app.handlers.user_commands as uc_mod
        from app.handlers.user_commands import cmd_balance

        with patch.object(uc_mod, 'ensure_user_exists', new_callable=AsyncMock), \
             patch.object(uc_mod, 'get_user_balance', new_callable=AsyncMock, return_value=Decimal("1000")), \
             patch.object(uc_mod, '_get_history_text', new_callable=AsyncMock, return_value="<i>Нет</i>"), \
             patch.object(uc_mod, 'get_back_to_menu_keyboard', return_value=None):
            msg = make_message("/balance")
            await cmd_balance(msg)

            msg.answer.assert_called_once()
            call_text = msg.answer.call_args[0][0]
            assert "1 000" in call_text or "1000" in call_text


class TestCmdSend:

    @pytest.mark.asyncio
    async def test_cmd_send_no_args(self):
        """Команда /send без аргументов должна запустить FSM."""
        import app.handlers.user_commands as uc_mod
        from app.handlers.user_commands import cmd_send

        with patch.object(uc_mod, 'ensure_user_exists', new_callable=AsyncMock), \
             patch.object(uc_mod, 'get_back_to_menu_keyboard', return_value=None):
            msg = make_message("/send")
            state = make_state()
            await cmd_send(msg, state, msg.bot)

            state.set_state.assert_called_once()
            msg.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_amount_invalid(self):
        """Ввод нечисловой суммы должен показать ошибку."""
        import app.handlers.user_commands as uc_mod
        from app.handlers.user_commands import process_amount_input

        with patch.object(uc_mod, 'get_user_balance', new_callable=AsyncMock, return_value=Decimal("1000")), \
             patch.object(uc_mod, 'get_back_to_menu_keyboard', return_value=None):
            msg = make_message("abc")
            state = make_state({'recipient_id': 1, 'recipient_telegram_id': 1001, 'recipient_username': 'bob', 'message_ids': []})
            await process_amount_input(msg, state)

            msg.reply.assert_called_once()
            call_text = msg.reply.call_args[0][0]
            assert "❌" in call_text

    @pytest.mark.asyncio
    async def test_process_amount_insufficient_funds(self):
        """Ввод суммы больше баланса должен показать ошибку."""
        import app.handlers.user_commands as uc_mod
        from app.handlers.user_commands import process_amount_input

        with patch.object(uc_mod, 'get_user_balance', new_callable=AsyncMock, return_value=Decimal("50")), \
             patch.object(uc_mod, 'get_back_to_menu_keyboard', return_value=None):
            msg = make_message("100")
            state = make_state({'recipient_id': 1, 'recipient_telegram_id': 1001, 'recipient_username': 'bob', 'message_ids': []})
            await process_amount_input(msg, state)

            msg.reply.assert_called_once()
            call_text = msg.reply.call_args[0][0]
            assert "Недостаточно" in call_text



# =============================================================================
# Tests: Event Creation FSM (event_handlers)
# =============================================================================

class TestEventCreationFSM:

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_name(self, mock_db):
        """Ввод имени события должен сохранить его в стейт и перейти к описанию."""
        from app.handlers.event_handlers import process_event_name

        msg = make_message("Тестовое событие")
        state = make_state({
            'activity_id': 1,
            'message_ids': [100],
            'activity_description': 'Описание'
        })
        mock_db.get_activity = AsyncMock(return_value={
            'id': 1, 'name': 'General', 'description': 'Описание активности'
        })

        await process_event_name(msg, state)

        state.update_data.assert_called()
        update_calls = [str(c) for c in state.update_data.call_args_list]
        assert any("Тестовое событие" in c for c in update_calls)
        state.set_state.assert_called()

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_date_valid(self, mock_db):
        """Ввод валидной будущей даты должен перейти к стоимости."""
        from app.handlers.event_handlers import process_event_date

        msg = make_message("01.01.2030 12:00")
        state = make_state({'activity_id': 1, 'message_ids': [100, 101]})

        await process_event_date(msg, state)

        state.update_data.assert_called()
        state.set_state.assert_called()

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_date_invalid_format(self, mock_db):
        """Ввод даты в неверном формате должен показать ошибку."""
        from app.handlers.event_handlers import process_event_date

        msg = make_message("не-дата")
        state = make_state({'activity_id': 1, 'message_ids': [100]})

        await process_event_date(msg, state)

        msg.reply.assert_called_once()
        call_text = msg.reply.call_args[0][0]
        assert "❌" in call_text
        assert "ДД.ММ.ГГГГ" in call_text

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_date_past(self, mock_db):
        """Ввод даты в прошлом должен показать ошибку."""
        from app.handlers.event_handlers import process_event_date

        msg = make_message("01.01.2020 12:00")
        state = make_state({'activity_id': 1, 'message_ids': [100]})

        await process_event_date(msg, state)

        msg.reply.assert_called_once()
        call_text = msg.reply.call_args[0][0]
        assert "прошлом" in call_text.lower()

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_time_valid(self, mock_db):
        """Ввод валидного времени должен перейти к стоимости."""
        from app.handlers.event_handlers import process_event_time

        msg = make_message("14:30")
        state = make_state({'activity_id': 1, 'message_ids': [100, 101]})

        await process_event_time(msg, state)

        state.update_data.assert_called()
        state.set_state.assert_called()

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_time_invalid(self, mock_db):
        """Ввод невалидного времени должен показать ошибку."""
        from app.handlers.event_handlers import process_event_time

        msg = make_message("25:99")
        state = make_state({'message_ids': [100]})

        await process_event_time(msg, state)

        msg.reply.assert_called_once()
        call_text = msg.reply.call_args[0][0]
        assert "❌" in call_text

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_cost_valid(self, mock_db):
        """Ввод валидной стоимости должен перейти к ссылке."""
        from app.handlers.event_handlers import process_event_cost

        msg = make_message("100")
        state = make_state({'message_ids': [100, 101]})

        await process_event_cost(msg, state)

        state.update_data.assert_called()
        state.set_state.assert_called()

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_cost_invalid(self, mock_db):
        """Ввод отрицательной стоимости должен показать ошибку."""
        from app.handlers.event_handlers import process_event_cost

        msg = make_message("-50")
        state = make_state({'message_ids': [100]})

        await process_event_cost(msg, state)

        msg.reply.assert_called_once()
        call_text = msg.reply.call_args[0][0]
        assert "❌" in call_text

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_process_event_cost_non_numeric(self, mock_db):
        """Ввод текста вместо числа должен показать ошибку."""
        from app.handlers.event_handlers import process_event_cost

        msg = make_message("бесплатно")
        state = make_state({'message_ids': [100]})

        await process_event_cost(msg, state)

        msg.reply.assert_called_once()
        call_text = msg.reply.call_args[0][0]
        assert "❌" in call_text


# =============================================================================
# Tests: Activity Subscription (activity_handlers)
# =============================================================================

class TestActivitySubscription:

    @pytest.mark.asyncio
    @patch("app.handlers.activity_handlers._send_activity_details_message", new_callable=AsyncMock)
    @patch("app.handlers.activity_handlers.db")
    async def test_subscribe_to_activity(self, mock_db, mock_send):
        """Нажатие 'subscribe' на активность должно записать подписку."""
        from app.handlers.activity_handlers import process_activity_subscription
        from app.callbacks import ActivityAction

        mock_db.get_activity = AsyncMock(return_value={'id': 2, 'name': 'Йога'})
        mock_db.add_subscription = AsyncMock()

        cb_data = ActivityAction(action="subscribe", activity_id=2)
        cb = make_callback()

        await process_activity_subscription(cb, cb_data)

        mock_db.add_subscription.assert_called_once()
        cb.answer.assert_called()

    @pytest.mark.asyncio
    @patch("app.handlers.activity_handlers._send_activity_details_message", new_callable=AsyncMock)
    @patch("app.handlers.activity_handlers.db")
    async def test_unsubscribe_from_activity(self, mock_db, mock_send):
        """Нажатие 'unsubscribe' на активность должно удалить подписку."""
        from app.handlers.activity_handlers import process_activity_subscription
        from app.callbacks import ActivityAction

        mock_db.get_activity = AsyncMock(return_value={'id': 2, 'name': 'Йога'})
        mock_db.remove_subscription = AsyncMock()

        cb_data = ActivityAction(action="unsubscribe", activity_id=2)
        cb = make_callback()

        await process_activity_subscription(cb, cb_data)

        mock_db.remove_subscription.assert_called_once()
        cb.answer.assert_called()


# =============================================================================
# Tests: Event Edit with TelegramBadRequest resilience
# =============================================================================

class TestEventEditResilience:

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_edit_schedule_fallback_on_bad_request(self, mock_db):
        """При TelegramBadRequest должен отправить ответом вместо редактирования."""
        from app.handlers.event_handlers import process_edit_event_schedule
        from app.callbacks import EventEditAction
        from aiogram.exceptions import TelegramBadRequest

        mock_db.get_event = AsyncMock(return_value={
            'id': 1, 'event_type': 'single', 'name': 'Test'
        })

        cb_data = EventEditAction(action="schedule", event_id=1)
        cb = make_callback()
        state = make_state()

        # edit_text кидает TelegramBadRequest
        cb.message.edit_text = AsyncMock(side_effect=TelegramBadRequest(
            method=MagicMock(), message="message can't be edited"
        ))

        await process_edit_event_schedule(cb, state, cb_data)

        # Должен был вызвать answer как fallback
        cb.message.answer.assert_called_once()
        call_text = cb.message.answer.call_args[0][0]
        assert "ДД.ММ.ГГГГ" in call_text
        cb.answer.assert_called()
