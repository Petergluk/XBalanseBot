import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Убираем asyncPG/connect
import app.services.scheduler_jobs as sched_mod
from app.services.scheduler_jobs import handle_payment_for_event, handle_reminders_for_event, process_demurrage

# =============================================================================
# Тесты: handle_payment_for_event (Еженедельные / ежедневные списания событий)
# =============================================================================

class TestProcessEventPayments:
    @pytest.mark.asyncio
    @patch.object(sched_mod, '_get_final_participants', new_callable=AsyncMock)
    @patch.object(sched_mod, 'get_next_run_time')
    async def test_payment_zero_cost(self, mock_next_run, mock_get_participants):
        """События с нулевой стоимостью не должны инициировать списания."""
        mock_next_run.return_value = datetime.now(ZoneInfo("Europe/Moscow"))
        mock_get_participants.return_value = [{'id': 10, 'telegram_id': 1001, 'balance': Decimal('100')}]
        
        event = {
            'id': 1, 'name': 'Free Yoga', 'activity_name': None,
            'cost': 0, 'event_type': 'single', 'link': 'http'
        }
        bot_mock = AsyncMock()

        with patch("app.services.scheduler_jobs.db") as mock_db:
            await handle_payment_for_event(bot_mock, event)
            # Транзакции не должны были вызываться для нулевой стоимости
            assert mock_db.pool.connection.call_count == 0

    @pytest.mark.asyncio
    @patch.object(sched_mod, '_get_final_participants', new_callable=AsyncMock)
    @patch.object(sched_mod, 'get_next_run_time')
    async def test_payment_processed_correctly(self, mock_next_run, mock_get_participants):
        """Корректное списание со всех участников."""
        mock_next_run.return_value = datetime.now(ZoneInfo("Europe/Moscow"))
        mock_get_participants.return_value = [
            {'id': 10, 'telegram_id': 1001, 'balance': Decimal('100')},
            {'id': 11, 'telegram_id': 1002, 'balance': Decimal('50')}
        ]
        
        event = {
            'id': 1, 'name': 'Paid Yoga', 'activity_name': None,
            'cost': Decimal('10'), 'event_type': 'single', 'link': 'http'
        }
        bot_mock = AsyncMock()

        from contextlib import asynccontextmanager
        
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        mock_tx = MagicMock()
        
        mock_cur = MagicMock()
        mock_cur.execute = AsyncMock()
        mock_cur.fetchone = AsyncMock(side_effect=[
            {'balance': Decimal('100'), 'grace_credit_used': False},
            {'balance': Decimal('50'), 'grace_credit_used': False}
        ])
        
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
        
        mock_db = MagicMock()
        mock_db.pool.connection = MagicMock(side_effect=mock_conn_ctx)

        with patch("app.services.scheduler_jobs.db", mock_db):
            await handle_payment_for_event(bot_mock, event)
            
            # 3 запроса (списать с юзера, добавить транзакцию, обновить кол-во транз) * 2 юзера = 6 вызовов
            assert mock_conn.execute.call_count == 6
            # Бот должен был отправить два сообщения
            assert bot_mock.send_message.call_count == 2
            
            # Проверки первого execute (списание 10 монет)
            call_args = mock_conn.execute.call_args_list[0][0]
            assert "UPDATE users SET balance = balance - %s" in call_args[0]
            assert call_args[1] == (Decimal('10'), 10)

    @pytest.mark.asyncio
    @patch.object(sched_mod, '_get_final_participants', new_callable=AsyncMock)
    @patch.object(sched_mod, 'get_next_run_time')
    async def test_payment_grace_credit_offered(self, mock_next_run, mock_get_participants):
        """Пользователю предлагается кредит доверия, если баланса не хватает и он еще не использован."""
        mock_next_run.return_value = datetime.now(ZoneInfo("Europe/Moscow"))
        mock_get_participants.return_value = [
            {'id': 12, 'telegram_id': 1003, 'balance': Decimal('5')}
        ]
        
        event = {
            'id': 1, 'name': 'Paid Yoga', 'activity_name': None,
            'cost': Decimal('10'), 'event_type': 'single', 'link': 'http'
        }
        bot_mock = AsyncMock()

        from contextlib import asynccontextmanager
        
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
        
        mock_db = MagicMock()
        mock_db.pool.connection = MagicMock(side_effect=mock_conn_ctx)

        with patch("app.services.scheduler_jobs.db", mock_db):
            await handle_payment_for_event(bot_mock, event)
            
            # В бд списание не делается
            assert mock_conn.execute.call_count == 0
            
            # Бот должен отправить сообщение с кнопкой кредита
            assert bot_mock.send_message.call_count == 1
            call_args, call_kwargs = bot_mock.send_message.call_args
            assert call_args[0] == 1003
            assert "Недостаточно средств" in call_args[1]
            assert "reply_markup" in call_kwargs
            assert call_kwargs["reply_markup"] is not None

    @pytest.mark.asyncio
    @patch.object(sched_mod, '_get_final_participants', new_callable=AsyncMock)
    @patch.object(sched_mod, 'get_next_run_time')
    async def test_payment_suspended_credit_already_used(self, mock_next_run, mock_get_participants):
        """Участие приостановлено, если баланса не хватает и кредит уже использован."""
        mock_next_run.return_value = datetime.now(ZoneInfo("Europe/Moscow"))
        mock_get_participants.return_value = [
            {'id': 13, 'telegram_id': 1004, 'balance': Decimal('5')}
        ]
        
        event = {
            'id': 1, 'name': 'Paid Yoga', 'activity_name': None,
            'cost': Decimal('10'), 'event_type': 'single', 'link': 'http'
        }
        bot_mock = AsyncMock()

        from contextlib import asynccontextmanager
        
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
        
        mock_db = MagicMock()
        mock_db.pool.connection = MagicMock(side_effect=mock_conn_ctx)

        with patch("app.services.scheduler_jobs.db", mock_db):
            await handle_payment_for_event(bot_mock, event)
            
            # В бд списание не делается
            assert mock_conn.execute.call_count == 0
            
            # Бот должен отправить сообщение о приостановке
            assert bot_mock.send_message.call_count == 1
            call_args, call_kwargs = bot_mock.send_message.call_args
            assert call_args[0] == 1004
            assert "Участие приостановлено" in call_args[1]
            assert "reply_markup" not in call_kwargs or call_kwargs["reply_markup"] is None


# =============================================================================
# Тесты: process_demurrage (Ежедневный налог)
# =============================================================================

class TestProcessDemurrage:
    @pytest.mark.asyncio
    async def test_demurrage_disabled(self):
        """Демерредж не выполняется, если настройка выключена."""
        bot_mock = AsyncMock()
        mock_db = MagicMock()
        mock_db.get_setting = AsyncMock(return_value='0') # demurrage_enabled = 0
        
        with patch("app.services.scheduler_jobs.db", mock_db):
            await process_demurrage(bot_mock)
            
            assert mock_db.get_setting.call_count == 1 # Только запрос demurrage_enabled
            assert mock_db.pool.connection.call_count == 0

    @pytest.mark.asyncio
    async def test_demurrage_interval_not_passed(self):
        """Демерредж пропускается, если не прошел интервал дней."""
        bot_mock = AsyncMock()
        mock_db = MagicMock()
        
        def mock_get_setting(key, default):
            if key == 'demurrage_enabled': return '1'
            if key == 'demurrage_interval_days': return '7'
            if key == 'demurrage_last_run': return date.today().isoformat() # Сегодня уже запускался
            return default
            
        mock_db.get_setting = AsyncMock(side_effect=mock_get_setting)
        
        with patch("app.services.scheduler_jobs.db", mock_db):
            await process_demurrage(bot_mock)
            
            # Соединение к БД с транзакциями открываться не должно
            assert mock_db.pool.connection.call_count == 0

    @pytest.mark.asyncio
    async def test_demurrage_zero_rate(self):
        """Демерредж пропускается, если ставка 0%."""
        bot_mock = AsyncMock()
        mock_db = MagicMock()
        
        def mock_get_setting(key, default):
            if key == 'demurrage_enabled': return '1'
            if key == 'demurrage_interval_days': return '1'
            if key == 'demurrage_last_run': return "2020-01-01" # Запускался давно
            if key == 'demurrage_rate': return "0.0"
            return default
            
        mock_db.get_setting = AsyncMock(side_effect=mock_get_setting)
        
        with patch("app.services.scheduler_jobs.db", mock_db):
            await process_demurrage(bot_mock)
            assert mock_db.pool.connection.call_count == 0

    @pytest.mark.asyncio
    async def test_demurrage_processed_correctly(self):
        """Корректное начисление демерреджа и обновление даты."""
        bot_mock = AsyncMock()
        mock_db = MagicMock()
        
        def mock_get_setting(key, default):
            if key == 'demurrage_enabled': return '1'
            if key == 'demurrage_interval_days': return '1'
            if key == 'demurrage_last_run': return "2020-01-01" # Прошло много дней
            if key == 'demurrage_rate': return "1.0" # 1%
            return default

        users_to_tax = [
            {'id': 10, 'balance': Decimal('100')}, # 1% = 1
            {'id': 11, 'balance': Decimal('50')}   # 1% = 0.5
        ]

        from contextlib import asynccontextmanager
        
        mock_cur = MagicMock()
        mock_cur.fetchall = AsyncMock(side_effect=[users_to_tax, []])
        mock_cur.execute = AsyncMock()
        mock_cur.executemany = AsyncMock()
        
        mock_tx = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        
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
        
        mock_db = MagicMock()
        mock_db.pool.connection = MagicMock(side_effect=mock_conn_ctx)
        mock_db.get_setting = AsyncMock(side_effect=mock_get_setting)
        mock_db.set_setting = AsyncMock()

        with patch("app.services.scheduler_jobs.db", mock_db):
            await process_demurrage(bot_mock)
            
            # Проверяем, что дата обновлена
            mock_db.set_setting.assert_called_once_with('demurrage_last_run', date.today().isoformat())
            
            # 2 batch execute calls + 1 update fund call
            assert mock_cur.executemany.call_count == 2
            assert mock_conn.execute.call_count == 1
            
            # Проверим, что фонд получил 1.5
            last_execute_args = mock_conn.execute.call_args_list[-1][0]
            assert "UPDATE users SET balance = balance + %s" in last_execute_args[0]
            assert last_execute_args[1] == (Decimal('1.5'), 0) # Fund ID is 0
