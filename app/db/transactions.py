# app/db/transactions.py
import logging
from typing import Any, Optional, Tuple
from datetime import datetime
from psycopg.rows import dict_row
from app.config import SYSTEM_FUND_USER_ID
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)

class TransactionRepository(BaseRepository):
    """Репозиторий для работы с транзакциями, переводами и балансами."""

    async def get_user_balance(self, telegram_id: int) -> Optional[Any]:
        """Возвращает баланс пользователя по telegram_id."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT balance FROM users WHERE telegram_id = %s", (telegram_id,))
                row = await cur.fetchone()
                return row['balance'] if row else None

    async def change_balance(self, target_user_id: int, amount, transaction_type: str, comment: str):
        """Изменение баланса пользователя (admin add/rem). amount может быть отрицательным для списания."""
        async with self.pool.connection() as conn:
            async with conn.transaction():
                from_user_id = 0 if transaction_type == 'manual_add' else target_user_id
                to_user_id = target_user_id if transaction_type == 'manual_add' else 0
                await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount, target_user_id))
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, %s, %s)",
                    (from_user_id, to_user_id, abs(amount), transaction_type, comment)
                )
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id = %s", (target_user_id,))

    async def transfer(self, sender_telegram_id: int, recipient_user_id: int, amount, comment: str) -> dict:
        """
        Атомарный перевод средств с проверкой баланса внутри транзакции.
        Возвращает dict с ключами: success, sender_db_id, sender_balance, error.
        """
        from decimal import Decimal
        async with self.pool.connection() as conn:
            async with conn.transaction():
                result_cursor = await conn.execute(
                    "SELECT id FROM users WHERE telegram_id = %s",
                    (sender_telegram_id,)
                )
                sender_row = await result_cursor.fetchone()
                if not sender_row:
                    return {'success': False, 'error': 'sender_not_found'}
                sender_db_id = sender_row[0]

                # Lock both in order to prevent deadlocks
                if sender_db_id != recipient_user_id:
                    await conn.execute("SELECT id FROM users WHERE id IN (%s, %s) ORDER BY id FOR UPDATE", (sender_db_id, recipient_user_id))
                else:
                    await conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (sender_db_id,))

                # Fetch balances after locking
                result_cursor = await conn.execute("SELECT balance FROM users WHERE id = %s", (sender_db_id,))
                sender_balance = Decimal(str((await result_cursor.fetchone())[0]))

                if sender_balance < amount:
                    return {'success': False, 'error': 'insufficient_funds', 'sender_balance': sender_balance}
                
                await conn.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (amount, sender_db_id))
                await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (amount, recipient_user_id))
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'transfer', %s)",
                    (sender_db_id, recipient_user_id, amount, comment)
                )
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id = %s", (sender_db_id,))
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id = %s", (recipient_user_id,))
                return {'success': True, 'sender_db_id': sender_db_id}

    async def get_transaction_history(self, telegram_id: int, date_limit: datetime) -> Tuple[Optional[int], list]:
        """Возвращает (user_db_id, transactions_list) для истории."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
                user_db_id_row = await cur.fetchone()
                if not user_db_id_row:
                    return None, []
                user_db_id = user_db_id_row['id']
                await cur.execute(
                    "SELECT t.*, sender.username as sender_username, recipient.username as recipient_username "
                    "FROM transactions t "
                    "LEFT JOIN users sender ON t.from_user_id = sender.id "
                    "LEFT JOIN users recipient ON t.to_user_id = recipient.id "
                    "WHERE (t.to_user_id = %s OR t.from_user_id = %s) AND t.created_at > %s "
                    "ORDER BY t.created_at DESC",
                    (user_db_id, user_db_id, date_limit)
                )
                return user_db_id, await cur.fetchall()

    async def get_gdp_stats(self, now: datetime) -> dict:
        """Возвращает статистику экономики сообщества."""
        from datetime import timedelta
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                async def get_turnover_and_count(days=None):
                    query = "SELECT COALESCE(SUM(amount), 0) as turnover, COUNT(id) as tx_count FROM transactions WHERE type = 'transfer'"
                    params = []
                    if days:
                        query += " AND created_at > %s"
                        params.append(now - timedelta(days=days))
                    await cur.execute(query, params)
                    return await cur.fetchone()
                turnover_7d = await get_turnover_and_count(7)
                turnover_30d = await get_turnover_and_count(30)
                turnover_all = await get_turnover_and_count()
                await cur.execute("SELECT COALESCE(SUM(balance), 0) as total FROM users")
                total_supply = (await cur.fetchone())['total']
                await cur.execute("SELECT balance FROM users WHERE id = 0")
                fund_balance = (await cur.fetchone())['balance']
                return {
                    'turnover_7d': turnover_7d,
                    'turnover_30d': turnover_30d,
                    'turnover_all': turnover_all,
                    'total_supply': total_supply,
                    'fund_balance': fund_balance,
                }

    async def credit_welcome_bonus(self, telegram_id: int, comment: str) -> Any:
        """Начисляет welcome-бонус. Возвращает сумму бонуса (0 если не начислен)."""
        from decimal import Decimal
        # Ожидаем, что SettingRepository примешан к результирующему классу Database
        bonus_amount_str = await self.get_setting('welcome_bonus_amount', '0')
        try:
            welcome_bonus = Decimal(bonus_amount_str)
            if welcome_bonus <= 0:
                return Decimal('0')
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    result_cursor = await conn.execute("SELECT id FROM users WHERE telegram_id = %s FOR UPDATE", (telegram_id,))
                    user_row = await result_cursor.fetchone()
                    if user_row:
                        user_id = user_row[0]
                        
                        # Проверяем, начислен ли уже бонус, чтобы избежать race condition
                        tx_cursor = await conn.execute(
                            "SELECT 1 FROM transactions WHERE to_user_id = %s AND type = 'welcome_bonus'",
                            (user_id,)
                        )
                        if await tx_cursor.fetchone():
                            return Decimal('0')

                        await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (welcome_bonus, user_id))
                        await conn.execute(
                            "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'welcome_bonus', %s)",
                            (SYSTEM_FUND_USER_ID, user_id, welcome_bonus, comment)
                        )
                        await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id = %s", (user_id,))
                        logger.info(f"Welcome bonus {welcome_bonus} credited to user {telegram_id}")
            return welcome_bonus
        except (ValueError, TypeError) as e:
            logger.error(f"Could not parse welcome_bonus_amount '{bonus_amount_str}': {e}")
            return Decimal('0')
