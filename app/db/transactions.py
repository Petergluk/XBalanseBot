# app/db/transactions.py
import logging
from typing import Any, Optional, Tuple
from datetime import datetime
from decimal import Decimal
from psycopg.rows import dict_row
from app.config import SYSTEM_FUND_USER_ID, SUPER_ADMIN_ID
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)


class TransactionRepository(BaseRepository):
    """Репозиторий для работы с транзакциями, переводами и балансами."""

    async def _get_or_create_treasury_id(self, conn) -> int:
        """Возвращает внутренний ID счёта «Игровая казна» (SUPER_ADMIN_ID), создавая его при необходимости."""
        if not SUPER_ADMIN_ID:
            return SYSTEM_FUND_USER_ID
        cur = await conn.execute("SELECT id FROM users WHERE telegram_id = %s", (SUPER_ADMIN_ID,))
        row = await cur.fetchone()
        if row:
            return row[0] if not isinstance(row, dict) else row['id']
        cur = await conn.execute(
            """INSERT INTO users (telegram_id, username, is_admin)
               VALUES (%s, 'treasury', TRUE)
               ON CONFLICT (telegram_id) DO UPDATE SET is_admin = TRUE
               RETURNING id""",
            (SUPER_ADMIN_ID,)
        )
        created = await cur.fetchone()
        return created[0] if not isinstance(created, dict) else created['id']

    async def _allocate_bonus_from_source(
        self,
        conn,
        recipient_user_id: int,
        amount: Decimal,
        tx_type: str,
        comment: str,
        bonus_mode: str = 'stepwise',
    ) -> Decimal:
        """
        Списывает бонус (welcome_bonus или tag_reward) согласно 3-позиционному переключателю:
        - 'treasury' ('monarch'): сразу в минус со счёта «Игровая казна» (SUPER_ADMIN_ID)
        - 'fund': только из накопленного демерреджа в Общем фонде (id = 0)
        - 'stepwise': сначала из Общего фонда (id = 0), а недостающий остаток — из «Игровой казны» (SUPER_ADMIN_ID)
        Возвращает фактически начисленную сумму (или 0, если в режиме 'fund' недостаточно средств).
        """
        amount = Decimal(str(amount))
        if amount <= 0:
            return Decimal('0')

        treasury_id = await self._get_or_create_treasury_id(conn)
        lock_ids = sorted(set([SYSTEM_FUND_USER_ID, treasury_id, recipient_user_id]))
        await conn.execute(
            "SELECT id FROM users WHERE id = ANY(%s::int[]) ORDER BY id FOR UPDATE",
            (lock_ids,)
        )

        cur = await conn.execute("SELECT balance FROM users WHERE id = %s", (SYSTEM_FUND_USER_ID,))
        fund_row = await cur.fetchone()
        fund_balance = Decimal(str(fund_row[0] if not isinstance(fund_row, dict) else fund_row['balance'])) if fund_row else Decimal('0')

        mode = (bonus_mode or 'stepwise').strip().lower()
        if mode in ('treasury', 'monarch'):
            from_fund = Decimal('0')
            from_treasury = amount
        elif mode == 'fund':
            if fund_balance < amount:
                return Decimal('0')
            from_fund = amount
            from_treasury = Decimal('0')
        else:
            available_fund = max(Decimal('0'), fund_balance)
            from_fund = min(available_fund, amount)
            from_treasury = amount - from_fund

        if from_fund > 0:
            await conn.execute(
                "UPDATE users SET balance = balance - %s WHERE id = %s",
                (from_fund, SYSTEM_FUND_USER_ID)
            )
        if from_treasury > 0:
            await conn.execute(
                "UPDATE users SET balance = balance - %s WHERE id = %s",
                (from_treasury, treasury_id)
            )

        await conn.execute(
            """UPDATE users
               SET balance = balance + %s,
                   transaction_count = transaction_count + 1,
                   grace_credit_used = CASE WHEN balance + %s >= 0 THEN FALSE ELSE grace_credit_used END
               WHERE id = %s""",
            (amount, amount, recipient_user_id)
        )

        if from_fund > 0 and from_treasury > 0:
            await conn.execute(
                "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, %s, %s)",
                (SYSTEM_FUND_USER_ID, recipient_user_id, from_fund, tx_type, comment)
            )
            await conn.execute(
                "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, %s, %s)",
                (treasury_id, recipient_user_id, from_treasury, tx_type, comment)
            )
        else:
            source_user_id = SYSTEM_FUND_USER_ID if from_treasury == 0 else treasury_id
            await conn.execute(
                "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, %s, %s)",
                (source_user_id, recipient_user_id, amount, tx_type, comment)
            )
        return amount

    async def get_user_balance(self, telegram_id: int) -> Optional[Any]:
        """Возвращает баланс пользователя по telegram_id."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT balance FROM users WHERE telegram_id = %s", (telegram_id,))
                row = await cur.fetchone()
                return row['balance'] if row else None

    async def change_balance(self, target_user_id: int, amount, transaction_type: str, comment: str):
        """
        Изменение баланса пользователя (admin add/rem) через счёт «Игровая казна» (SUPER_ADMIN_ID).
        Поддерживает закон сохранения суммы балансов (Σ = 0).
        """
        amount = Decimal(str(amount))
        abs_amount = abs(amount)
        async with self.pool.connection() as conn:
            async with conn.transaction():
                treasury_id = await self._get_or_create_treasury_id(conn)
                lock_ids = sorted(set([treasury_id, target_user_id]))
                await conn.execute(
                    "SELECT id FROM users WHERE id = ANY(%s::int[]) ORDER BY id FOR UPDATE",
                    (lock_ids,)
                )

                if transaction_type == 'manual_add' or amount > 0:
                    from_user_id = treasury_id
                    to_user_id = target_user_id
                    if treasury_id != target_user_id:
                        await conn.execute(
                            "UPDATE users SET balance = balance - %s, transaction_count = transaction_count + 1 WHERE id = %s",
                            (abs_amount, treasury_id)
                        )
                    await conn.execute(
                        """UPDATE users
                           SET balance = balance + %s,
                               transaction_count = transaction_count + 1,
                               grace_credit_used = CASE WHEN balance + %s >= 0 THEN FALSE ELSE grace_credit_used END
                           WHERE id = %s""",
                        (abs_amount, abs_amount, target_user_id)
                    )
                else:
                    from_user_id = target_user_id
                    to_user_id = treasury_id
                    await conn.execute(
                        "UPDATE users SET balance = balance - %s, transaction_count = transaction_count + 1 WHERE id = %s",
                        (abs_amount, target_user_id)
                    )
                    if treasury_id != target_user_id:
                        await conn.execute(
                            "UPDATE users SET balance = balance + %s, transaction_count = transaction_count + 1 WHERE id = %s",
                            (abs_amount, treasury_id)
                        )

                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, %s, %s)",
                    (from_user_id, to_user_id, abs_amount, transaction_type, comment)
                )

    async def transfer(self, sender_telegram_id: int, recipient_user_id: int, amount, comment: str) -> dict:
        """
        Атомарный перевод средств с проверкой баланса внутри транзакции.
        Для Супер-админа (SUPER_ADMIN_ID — «Игровая казна») разрешён уход в минус без лимита.
        Возвращает dict с ключами: success, sender_db_id, sender_balance, error, is_treasury.
        """
        amount = Decimal(str(amount))
        is_treasury_sender = bool(SUPER_ADMIN_ID and sender_telegram_id == SUPER_ADMIN_ID)

        async with self.pool.connection() as conn:
            async with conn.transaction():
                if is_treasury_sender:
                    sender_db_id = await self._get_or_create_treasury_id(conn)
                else:
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
                    await conn.execute(
                        "SELECT id FROM users WHERE id IN (%s, %s) ORDER BY id FOR UPDATE",
                        (sender_db_id, recipient_user_id)
                    )
                else:
                    await conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (sender_db_id,))

                # Fetch balances after locking
                result_cursor = await conn.execute("SELECT balance FROM users WHERE id = %s", (sender_db_id,))
                sender_balance = Decimal(str((await result_cursor.fetchone())[0]))

                if not is_treasury_sender and sender_balance < amount:
                    return {'success': False, 'error': 'insufficient_funds', 'sender_balance': sender_balance}

                await conn.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (amount, sender_db_id))
                await conn.execute(
                    """UPDATE users
                       SET balance = balance + %s,
                           grace_credit_used = CASE WHEN balance + %s >= 0 THEN FALSE ELSE grace_credit_used END
                       WHERE id = %s""",
                    (amount, amount, recipient_user_id)
                )
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'transfer', %s)",
                    (sender_db_id, recipient_user_id, amount, comment)
                )
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id = %s", (sender_db_id,))
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id = %s", (recipient_user_id,))
                return {
                    'success': True,
                    'sender_db_id': sender_db_id,
                    'sender_balance': sender_balance - amount,
                    'is_treasury': is_treasury_sender,
                }

    async def transfer_from_fund(self, recipient_user_id: int, amount, comment: str) -> dict:
        """
        Атомарный перевод средств из Фонда (id = 0) пользователю.
        Проверяет достаточность средств в Фонде и сбрасывает grace_credit_used при выходе из минуса.
        """
        amount = Decimal(str(amount))
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT id FROM users WHERE id IN (0, %s) ORDER BY id FOR UPDATE",
                    (recipient_user_id,)
                )
                cur = await conn.execute("SELECT balance FROM users WHERE id = 0")
                fund_row = await cur.fetchone()
                fund_balance = Decimal(str(fund_row[0])) if fund_row else Decimal('0')

                if fund_balance < amount:
                    return {
                        'success': False,
                        'error': 'insufficient_fund_balance',
                        'fund_balance': fund_balance,
                    }

                await conn.execute("UPDATE users SET balance = balance - %s WHERE id = 0", (amount,))
                await conn.execute(
                    """UPDATE users
                       SET balance = balance + %s,
                           transaction_count = transaction_count + 1,
                           grace_credit_used = CASE WHEN balance + %s >= 0 THEN FALSE ELSE grace_credit_used END
                       WHERE id = %s""",
                    (amount, amount, recipient_user_id)
                )
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (0, %s, %s, 'fund_payment', %s)",
                    (recipient_user_id, amount, comment)
                )
                return {
                    'success': True,
                    'new_fund_balance': fund_balance - amount,
                }

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
                    "SELECT t.*, sender.username as sender_username, sender.telegram_id as sender_telegram_id, "
                    "recipient.username as recipient_username, recipient.telegram_id as recipient_telegram_id "
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
                    query = "SELECT COALESCE(SUM(amount), 0) as turnover, COUNT(id) as tx_count FROM transactions WHERE type IN ('transfer', 'purchase')"
                    params = []
                    if days:
                        query += " AND created_at > %s"
                        params.append(now - timedelta(days=days))
                    await cur.execute(query, params)
                    return await cur.fetchone()
                turnover_7d = await get_turnover_and_count(7)
                turnover_30d = await get_turnover_and_count(30)
                turnover_all = await get_turnover_and_count()

                # Деньги в обращении: сумма положительных балансов участников (без Фонда и Игровой казны)
                await cur.execute(
                    """SELECT COALESCE(SUM(balance), 0) as total
                       FROM users
                       WHERE id != 0 AND (telegram_id != %s OR %s IS NULL) AND balance > 0""",
                    (SUPER_ADMIN_ID, SUPER_ADMIN_ID)
                )
                total_supply = (await cur.fetchone())['total']

                await cur.execute("SELECT balance FROM users WHERE id = 0")
                fund_row = await cur.fetchone()
                fund_balance = fund_row['balance'] if fund_row else Decimal('0')

                await cur.execute("SELECT balance FROM users WHERE telegram_id = %s", (SUPER_ADMIN_ID,))
                treasury_row = await cur.fetchone()
                treasury_balance = treasury_row['balance'] if treasury_row else Decimal('0')

                # Вся денежная масса системы (в замкнутой экономике строго равна 0)
                await cur.execute("SELECT COALESCE(SUM(balance), 0) as total_mass FROM users")
                mass_row = await cur.fetchone()
                total_mass = mass_row['total_mass'] if mass_row else Decimal('0')

                return {
                    'turnover_7d': turnover_7d,
                    'turnover_30d': turnover_30d,
                    'turnover_all': turnover_all,
                    'total_supply': total_supply,
                    'fund_balance': fund_balance,
                    'treasury_balance': treasury_balance,
                    'total_mass': total_mass,
                }

    async def credit_welcome_bonus(self, telegram_id: int, comment: str) -> Any:
        """Начисляет welcome-бонус с учётом 3-позиционного переключателя источника бонусов."""
        bonus_amount_str = await self.get_setting('welcome_bonus_amount', '0')
        bonus_mode = await self.get_setting('bonus_source_mode', 'stepwise')
        try:
            welcome_bonus = Decimal(bonus_amount_str)
            if welcome_bonus <= 0:
                return Decimal('0')
            async with self.pool.connection() as conn:
                async with conn.transaction():
                    result_cursor = await conn.execute(
                        "SELECT id FROM users WHERE telegram_id = %s FOR UPDATE",
                        (telegram_id,)
                    )
                    user_row = await result_cursor.fetchone()
                    if not user_row:
                        return Decimal('0')
                    user_id = user_row[0]

                    # Проверяем, начислен ли уже бонус, чтобы избежать race condition
                    tx_cursor = await conn.execute(
                        "SELECT 1 FROM transactions WHERE to_user_id = %s AND type = 'welcome_bonus'",
                        (user_id,)
                    )
                    if await tx_cursor.fetchone():
                        return Decimal('0')

                    credited = await self._allocate_bonus_from_source(
                        conn,
                        recipient_user_id=user_id,
                        amount=welcome_bonus,
                        tx_type='welcome_bonus',
                        comment=comment,
                        bonus_mode=bonus_mode,
                    )
                    if credited > 0:
                        logger.info(f"Welcome bonus {credited} credited to user {telegram_id} (mode={bonus_mode})")
                    return credited
        except (ValueError, TypeError) as e:
            logger.error(f"Could not parse welcome_bonus_amount '{bonus_amount_str}': {e}")
            return Decimal('0')
