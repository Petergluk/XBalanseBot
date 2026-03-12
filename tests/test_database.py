# tests/test_database.py
"""
Тесты для Database: переводы, баланс, welcome-бонус, история, GDP.
Работают с реальной PostgreSQL через docker-compose.
"""
import pytest
from decimal import Decimal


class TestTransfer:
    """Тесты атомарных переводов."""

    async def _create_two_users(self, db, balance_a=Decimal("1000"), balance_b=Decimal("500")):
        """Создает двух тестовых пользователей с заданными балансами."""
        await db.create_user(telegram_id=1001, username="alice")
        await db.create_user(telegram_id=1002, username="bob")
        user_a = await db.get_user(telegram_id=1001)
        user_b = await db.get_user(telegram_id=1002)
        # Устанавливаем начальные балансы
        async with db.pool.connection() as conn:
            await conn.execute("UPDATE users SET balance = %s WHERE id = %s", (balance_a, user_a['id']))
            await conn.execute("UPDATE users SET balance = %s WHERE id = %s", (balance_b, user_b['id']))
        return user_a, user_b

    async def test_successful_transfer(self, db):
        user_a, user_b = await self._create_two_users(db)
        result = await db.transfer(1001, user_b['id'], Decimal("100"), "тест")
        assert result['success'] is True

        updated_a = await db.get_user(telegram_id=1001)
        updated_b = await db.get_user(telegram_id=1002)
        assert updated_a['balance'] == Decimal("900")
        assert updated_b['balance'] == Decimal("600")

    async def test_transfer_insufficient_funds(self, db):
        user_a, user_b = await self._create_two_users(db, balance_a=Decimal("50"))
        result = await db.transfer(1001, user_b['id'], Decimal("100"), "тест")
        assert result['success'] is False
        assert result['error'] == 'insufficient_funds'
        assert result['sender_balance'] == Decimal("50")

        # Балансы не изменились
        updated_a = await db.get_user(telegram_id=1001)
        assert updated_a['balance'] == Decimal("50")

    async def test_transfer_exact_balance(self, db):
        user_a, user_b = await self._create_two_users(db, balance_a=Decimal("100"))
        result = await db.transfer(1001, user_b['id'], Decimal("100"), "весь баланс")
        assert result['success'] is True

        updated_a = await db.get_user(telegram_id=1001)
        assert updated_a['balance'] == Decimal("0")

    async def test_transfer_sender_not_found(self, db):
        await db.create_user(telegram_id=1002, username="bob")
        user_b = await db.get_user(telegram_id=1002)
        result = await db.transfer(99999, user_b['id'], Decimal("100"), "тест")
        assert result['success'] is False
        assert result['error'] == 'sender_not_found'

    async def test_transfer_increments_transaction_count(self, db):
        user_a, user_b = await self._create_two_users(db)
        await db.transfer(1001, user_b['id'], Decimal("10"), "тест")
        
        updated_a = await db.get_user(telegram_id=1001)
        updated_b = await db.get_user(telegram_id=1002)
        assert updated_a['transaction_count'] == 1
        assert updated_b['transaction_count'] == 1

    async def test_transfer_creates_transaction_record(self, db):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        user_a, user_b = await self._create_two_users(db)
        await db.transfer(1001, user_b['id'], Decimal("50"), "подарок")
        
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        _, txs = await db.get_transaction_history(1001, now - timedelta(days=1))
        assert len(txs) == 1
        assert txs[0]['amount'] == Decimal("50")
        assert txs[0]['type'] == 'transfer'
        assert txs[0]['comment'] == 'подарок'


class TestChangeBalance:
    """Тесты admin add/rem."""

    async def test_add_balance(self, db):
        await db.create_user(telegram_id=2001, username="admin_test")
        user = await db.get_user(telegram_id=2001)
        await db.change_balance(user['id'], Decimal("500"), 'manual_add', 'тестовое начисление')
        
        updated = await db.get_user(telegram_id=2001)
        assert updated['balance'] == Decimal("500")
        assert updated['transaction_count'] == 1

    async def test_remove_balance(self, db):
        await db.create_user(telegram_id=2002, username="rem_test")
        user = await db.get_user(telegram_id=2002)
        # Сначала начислим
        async with db.pool.connection() as conn:
            await conn.execute("UPDATE users SET balance = 1000 WHERE id = %s", (user['id'],))
        
        await db.change_balance(user['id'], Decimal("-300"), 'manual_remove', 'штраф')
        updated = await db.get_user(telegram_id=2002)
        assert updated['balance'] == Decimal("700")


class TestWelcomeBonus:
    """Тесты welcome-бонуса."""

    async def test_welcome_bonus_credited(self, db):
        await db.set_setting('welcome_bonus_amount', '100')
        await db.create_user(telegram_id=3001, username="newbie")
        
        bonus = await db.credit_welcome_bonus(3001, "тест бонус")
        assert bonus == Decimal("100")

        user = await db.get_user(telegram_id=3001)
        assert user['balance'] == Decimal("100")
        assert user['transaction_count'] == 1

    async def test_welcome_bonus_zero(self, db):
        await db.set_setting('welcome_bonus_amount', '0')
        await db.create_user(telegram_id=3002, username="newbie2")
        
        bonus = await db.credit_welcome_bonus(3002, "тест")
        assert bonus == Decimal("0")

        user = await db.get_user(telegram_id=3002)
        assert user['balance'] == Decimal("0")

    async def test_welcome_bonus_negative_setting(self, db):
        await db.set_setting('welcome_bonus_amount', '-50')
        await db.create_user(telegram_id=3003, username="newbie3")
        
        bonus = await db.credit_welcome_bonus(3003, "тест")
        assert bonus == Decimal("0")


class TestGDPStats:
    """Тесты GDP-статистики."""

    async def test_gdp_empty(self, db):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        stats = await db.get_gdp_stats(now)
        assert stats['turnover_7d']['turnover'] == Decimal("0")
        assert stats['turnover_30d']['turnover'] == Decimal("0")
        assert stats['turnover_all']['turnover'] == Decimal("0")

    async def test_gdp_with_transfers(self, db):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        # Создаем пользователей и делаем перевод
        await db.create_user(telegram_id=4001, username="alice_gdp")
        await db.create_user(telegram_id=4002, username="bob_gdp")
        user_a = await db.get_user(telegram_id=4001)
        user_b = await db.get_user(telegram_id=4002)
        async with db.pool.connection() as conn:
            await conn.execute("UPDATE users SET balance = 1000 WHERE id = %s", (user_a['id'],))
        
        await db.transfer(4001, user_b['id'], Decimal("200"), "gdp тест")
        
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        stats = await db.get_gdp_stats(now)
        assert stats['turnover_7d']['turnover'] == Decimal("200")
        assert stats['turnover_7d']['tx_count'] == 1


class TestTransactionHistory:
    """Тесты истории транзакций."""

    async def test_history_empty(self, db):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        await db.create_user(telegram_id=5001, username="history_test")
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        user_id, txs = await db.get_transaction_history(5001, now - timedelta(days=30))
        assert user_id is not None
        assert len(txs) == 0

    async def test_history_user_not_found(self, db):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        user_id, txs = await db.get_transaction_history(99999, now - timedelta(days=30))
        assert user_id is None
        assert txs == []
