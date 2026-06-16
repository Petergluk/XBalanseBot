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
        mock_db.get_total_users_count = AsyncMock(return_value=0)
        mock_db.get_users_page = AsyncMock(return_value=[])

        msg = make_message("/users")
        loading_msg = AsyncMock()
        msg.answer.return_value = loading_msg
        await cmd_users(msg)

        msg.answer.assert_called_once()
        loading_msg.edit_text.assert_called_once()
        call_text = loading_msg.edit_text.call_args[0][0]
        assert "пока нет" in call_text.lower()

    @pytest.mark.asyncio
    @patch("app.handlers.admin_commands.db")
    async def test_cmd_users_with_data(self, mock_db):
        """С пользователями — должен показать список с балансами."""
        from app.handlers.admin_commands import cmd_users
        mock_db.get_total_users_count = AsyncMock(return_value=2)
        mock_db.get_users_page = AsyncMock(return_value=[
            {'id': 1, 'username': 'alice', 'telegram_id': 1001, 'balance': Decimal('500'), 'is_admin': False},
            {'id': 2, 'username': 'bob', 'telegram_id': 1002, 'balance': Decimal('100'), 'is_admin': True},
        ])

        msg = make_message("/users")
        loading_msg = AsyncMock()
        msg.answer.return_value = loading_msg
        await cmd_users(msg)

        msg.answer.assert_called_once()
        loading_msg.edit_text.assert_called_once()
        call_text = loading_msg.edit_text.call_args[0][0]
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


class TestTopicsSettings:

    @pytest.mark.asyncio
    @patch("app.handlers.admin_commands.db")
    async def test_menu_topics(self, mock_db):
        from app.handlers.admin_commands import process_settings_callbacks
        from app.callbacks import SettingsAction
        
        mock_db.get_setting = AsyncMock(return_value="12345")
        
        cb_data = SettingsAction(action="menu_topics")
        cb = make_callback()
        state = make_state()
        
        await process_settings_callbacks(cb, state, cb_data)
        
        mock_db.get_setting.assert_called_once_with("market_thread_id", "0")
        cb.message.edit_text.assert_called_once()
        call_text = cb.message.edit_text.call_args[0][0]
        assert "ID 12345" in call_text
        cb.answer.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.handlers.admin_commands.db")
    async def test_reset_market_thread(self, mock_db):
        from app.handlers.admin_commands import process_settings_callbacks
        from app.callbacks import SettingsAction
        
        mock_db.set_setting = AsyncMock()
        
        cb_data = SettingsAction(action="reset_market_thread")
        cb = make_callback()
        state = make_state()
        
        await process_settings_callbacks(cb, state, cb_data)
        
        mock_db.set_setting.assert_called_once_with("market_thread_id", "0")
        cb.answer.assert_called_once()
        cb.message.edit_text.assert_called_once()
        call_text = cb.message.edit_text.call_args[0][0]
        assert "Общий чат" in call_text


class TestGroupRestrictions:

    @pytest.mark.asyncio
    async def test_middleware_blocks_private_command_in_group(self):
        from main import private_chat_restriction_middleware
        
        # message in group
        msg = make_message(text="/menu", chat_id=-100123)
        msg.chat.type = "supergroup"
        
        # handler mock
        handler = AsyncMock()
        
        await private_chat_restriction_middleware(handler, msg, {})
        
        handler.assert_not_called()
        msg.reply.assert_called_once()
        assert "личных сообщениях" in msg.reply.call_args[0][0]

    @pytest.mark.asyncio
    async def test_middleware_allows_private_command_in_private(self):
        from main import private_chat_restriction_middleware
        
        msg = make_message(text="/menu", chat_id=123)
        msg.chat.type = "private"
        
        handler = AsyncMock(return_value="OK")
        
        res = await private_chat_restriction_middleware(handler, msg, {})
        
        handler.assert_called_once()
        assert res == "OK"

    @pytest.mark.asyncio
    async def test_middleware_blocks_send_without_args_in_group(self):
        from main import private_chat_restriction_middleware
        
        msg = make_message(text="/send", chat_id=-100123)
        msg.chat.type = "supergroup"
        
        handler = AsyncMock()
        
        await private_chat_restriction_middleware(handler, msg, {})
        
        handler.assert_not_called()
        msg.reply.assert_called_once()
        assert "быстрый перевод" in msg.reply.call_args[0][0]

    @pytest.mark.asyncio
    async def test_middleware_blocks_navigation_callback_in_group(self):
        from main import private_chat_restriction_middleware
        
        cb = make_callback(data="gen:main_menu", chat_id=-100123)
        cb.message.chat.type = "supergroup"
        
        handler = AsyncMock()
        
        await private_chat_restriction_middleware(handler, cb, {})
        
        handler.assert_not_called()
        cb.answer.assert_called_once_with(
            "❌ Это действие доступно только в личных сообщениях с ботом.",
            show_alert=True
        )

    @pytest.mark.asyncio
    async def test_middleware_allows_offer_callback_in_group(self):
        from main import private_chat_restriction_middleware
        
        cb = make_callback(data="off:buy:42", chat_id=-100123)
        cb.message.chat.type = "supergroup"
        
        handler = AsyncMock(return_value="OK")
        
        res = await private_chat_restriction_middleware(handler, cb, {})
        
        handler.assert_called_once()
        assert res == "OK"


# =============================================================================
# Tests: Grace Credit Callback
# =============================================================================

class TestGraceCreditCallback:

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_grace_credit_success(self, mock_db):
        """Успешное получение кредита доверия при недостаточном балансе."""
        from app.handlers.event_handlers import process_grace_credit_click
        from app.callbacks import GraceCreditAction
        from contextlib import asynccontextmanager

        # Mock user and event in main db queries
        mock_db.get_user = AsyncMock(return_value={'id': 42, 'telegram_id': 12345, 'balance': Decimal('5'), 'grace_credit_used': False})
        mock_db.get_event = AsyncMock(return_value={'id': 100, 'cost': Decimal('10'), 'name': 'Yoga', 'activity_name': None, 'event_date': None, 'link': 'http://yoga'})

        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_tx = MagicMock()
        
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(return_value={'balance': Decimal('5'), 'grace_credit_used': False})

        @asynccontextmanager
        async def mock_cur_ctx(*args, **kwargs):
            yield mock_cur
            
        @asynccontextmanager
        async def mock_tx_ctx(*args, **kwargs):
            yield mock_tx
            
        @asynccontextmanager
        async def mock_conn_ctx(*args, **kwargs):
            yield mock_conn

        mock_conn.transaction = MagicMock(side_effect=mock_tx_ctx)
        mock_conn.cursor = MagicMock(side_effect=mock_cur_ctx)
        mock_db.pool.connection = MagicMock(side_effect=mock_conn_ctx)

        # Create mock callback query
        cb = make_callback(data="grace_credit:100", user_id=12345)
        cb.message.edit_text = AsyncMock()
        
        cb_data = GraceCreditAction(event_id=100)
        bot_mock = AsyncMock()

        # Run handler
        await process_grace_credit_click(cb, cb_data, bot_mock)

        # Verify balance updated in db (with grace_credit_used = TRUE)
        # UPDATE users SET balance = balance - %s, grace_credit_used = TRUE WHERE id = %s
        update_call = mock_conn.execute.call_args_list[0][0]
        assert "grace_credit_used = TRUE" in update_call[0]
        assert update_call[1] == (Decimal('10'), 42)

        # Verify message edited
        cb.message.edit_text.assert_called_once()
        assert "Вы получили кредит" in cb.message.edit_text.call_args[0][0]
        cb.answer.assert_called_once_with("✅ Кредит получен, участие подтверждено!")

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_grace_credit_balance_already_sufficient(self, mock_db):
        """Если у пользователя внезапно хватает баланса, списываем без активации кредита."""
        from app.handlers.event_handlers import process_grace_credit_click
        from app.callbacks import GraceCreditAction
        from contextlib import asynccontextmanager

        mock_db.get_user = AsyncMock(return_value={'id': 42, 'telegram_id': 12345, 'balance': Decimal('20'), 'grace_credit_used': False})
        mock_db.get_event = AsyncMock(return_value={'id': 100, 'cost': Decimal('10'), 'name': 'Yoga', 'activity_name': None, 'event_date': None, 'link': 'http://yoga'})

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_tx = MagicMock()
        
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(return_value={'balance': Decimal('20'), 'grace_credit_used': False})

        @asynccontextmanager
        async def mock_cur_ctx(*args, **kwargs):
            yield mock_cur
            
        @asynccontextmanager
        async def mock_tx_ctx(*args, **kwargs):
            yield mock_tx
            
        @asynccontextmanager
        async def mock_conn_ctx(*args, **kwargs):
            yield mock_conn

        mock_conn.transaction = MagicMock(side_effect=mock_tx_ctx)
        mock_conn.cursor = MagicMock(side_effect=mock_cur_ctx)
        mock_db.pool.connection = MagicMock(side_effect=mock_conn_ctx)

        cb = make_callback(data="grace_credit:100", user_id=12345)
        cb.message.edit_text = AsyncMock()
        
        cb_data = GraceCreditAction(event_id=100)
        bot_mock = AsyncMock()

        await process_grace_credit_click(cb, cb_data, bot_mock)

        # UPDATE users SET balance = balance - %s WHERE id = %s (без grace_credit_used = TRUE)
        update_call = mock_conn.execute.call_args_list[0][0]
        assert "grace_credit_used = TRUE" not in update_call[0]
        assert update_call[1] == (Decimal('10'), 42)

        cb.message.edit_text.assert_called_once()
        assert "кредит не использован" in cb.message.edit_text.call_args[0][0]
        cb.answer.assert_called_once_with("✅ Участие подтверждено!")

    @pytest.mark.asyncio
    @patch("app.handlers.event_handlers.db")
    async def test_grace_credit_already_used(self, mock_db):
        """Если кредит уже использован, отклоняем запрос."""
        from app.handlers.event_handlers import process_grace_credit_click
        from app.callbacks import GraceCreditAction
        from contextlib import asynccontextmanager

        mock_db.get_user = AsyncMock(return_value={'id': 42, 'telegram_id': 12345, 'balance': Decimal('5'), 'grace_credit_used': True})
        mock_db.get_event = AsyncMock(return_value={'id': 100, 'cost': Decimal('10'), 'name': 'Yoga', 'activity_name': None, 'event_date': None, 'link': 'http://yoga'})

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_tx = MagicMock()
        
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(return_value={'balance': Decimal('5'), 'grace_credit_used': True})

        @asynccontextmanager
        async def mock_cur_ctx(*args, **kwargs):
            yield mock_cur
            
        @asynccontextmanager
        async def mock_tx_ctx(*args, **kwargs):
            yield mock_tx
            
        @asynccontextmanager
        async def mock_conn_ctx(*args, **kwargs):
            yield mock_conn

        mock_conn.transaction = MagicMock(side_effect=mock_tx_ctx)
        mock_conn.cursor = MagicMock(side_effect=mock_cur_ctx)
        mock_db.pool.connection = MagicMock(side_effect=mock_conn_ctx)

        cb = make_callback(data="grace_credit:100", user_id=12345)
        cb.message.edit_reply_markup = AsyncMock()
        
        cb_data = GraceCreditAction(event_id=100)
        bot_mock = AsyncMock()

        await process_grace_credit_click(cb, cb_data, bot_mock)

        # Никаких списаний в БД быть не должно
        assert mock_conn.execute.call_count == 0

        # Кнопки должны быть удалены
        cb.message.edit_reply_markup.assert_called_once_with(reply_markup=None)
        cb.answer.assert_called_once_with("❌ Вы уже использовали свой кредит доверия. Пожалуйста, пополните баланс.", show_alert=True)
