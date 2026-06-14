# XBalanseBot/app/database.py
# v1.9.2
# 2025-08-27 16:33:00
"""
Модуль для асинхронного управления базой данных PostgreSQL.

Версия 1.9.2:
- В `init_db` добавлена команда `ALTER TABLE`, чтобы гарантировать наличие
  колонки `allow_manual_registration` в уже существующей таблице `activities`.
  Это устраняет ошибку `UndefinedColumn`, замеченную в логах.
- Запрос в `get_event` теперь получает `allow_manual_registration` из `activities`,
  чтобы соответствовать логике обработчиков.
"""
import logging
import os
from datetime import datetime, date, time
from typing import Any, Dict, List, Optional
import asyncio

from app.config import GENERAL_ACTIVITY_ID, SYSTEM_FUND_USER_ID

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import (
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
)
from app.lexicon import LEXICON_RU

logger = logging.getLogger(__name__)

# --- НОВЫЙ УНИВЕРСАЛЬНЫЙ БЛОК ДЛЯ ПОДКЛЮЧЕНИЯ К БД ---
if database_url := os.environ.get("DATABASE_URL"):
    CONNINFO = database_url
    logger.info("Using DATABASE_URL for database connection.")
else:
    logger.info("Using individual POSTGRES variables for database connection.")
    CONNINFO = (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} "
        f"user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    )


class Database:
    """Класс для асинхронного управления базой данных PostgreSQL."""

    def __init__(self, conninfo: str):
        self.conninfo = conninfo
        self.pool: Optional[AsyncConnectionPool] = None

    async def initialize(self, max_retries: int = 5):
        """Инициализирует пул соединений и структуру базы данных с повторными попытками."""
        logger.info("Initializing database connection pool...")
        for attempt in range(max_retries):
            try:
                self.pool = AsyncConnectionPool(self.conninfo, open=False, max_size=10)
                await self.pool.open()
                logger.info("Connection pool opened successfully.")
                await self.init_db()
                return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error("Failed to initialize database after several attempts.")
                    raise
                logger.warning(f"Database connection failed, retrying in {2 ** attempt} seconds... ({e})")
                await asyncio.sleep(2 ** attempt)

    async def close(self):
        """Закрывает пул соединений."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed.")

    async def init_db(self):
        """Инициализирует начальные записи (таблицы теперь управляются Alembic)."""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # Системные записи
                await cur.execute("""
                    INSERT INTO users (id, telegram_id, username)
                    VALUES (0, 0, 'fund')
                    ON CONFLICT (id) DO NOTHING
                """)
                await cur.execute("""
                    INSERT INTO activities (id, name, description, is_active)
                    VALUES (1, 'Общие события', 'Это открытые встречи и общесистемные события, на которые автоматически подписаны все участники сообщества.', TRUE)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description, is_active = EXCLUDED.is_active
                """)

                # Синхронизация sequences (Гарантируем, что значение sequence >= 1)
                await cur.execute("SELECT setval('users_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM users), 1), 1))")
                await cur.execute("SELECT setval('activities_id_seq', GREATEST(COALESCE((SELECT MAX(id) FROM activities), 1), 1))")

                default_settings = {
                    'demurrage_rate': '1.0', 'demurrage_enabled': '0', 'exchange_rate': '1.0',
                    'welcome_message_bot': LEXICON_RU["default_welcome_bot"],
                    'welcome_message_group': LEXICON_RU["default_welcome_group"],
                    'welcome_bonus_amount': '1500',
                    'welcome_bonus_message': LEXICON_RU["default_welcome_bonus"],
                    'default_reminder_text': LEXICON_RU["default_reminder"],
                    'activities_description': '<b>🎨 Активности сообщества</b>\n\nВыберите направление:',
                    'demurrage_interval_days': '1',
                    'demurrage_last_run': '1970-01-01'
                }

                for key, value in default_settings.items():
                    await cur.execute(
                        "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                        (key, value)
                    )

    async def get_user(self, telegram_id: int = None, username: str = None) -> Optional[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                if telegram_id is not None:
                    await cur.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
                elif username:
                    await cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                else:
                    return None
                return await cur.fetchone()

    async def create_user(self, telegram_id: int, username: Optional[str], is_admin: bool = False):
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO users (telegram_id, username, is_admin) VALUES (%s, %s, %s) RETURNING id",
                    (telegram_id, username.lower() if username else None, is_admin)
                )
                new_user_id_row = await cur.fetchone()
                if new_user_id_row:
                    await cur.execute(
                        "INSERT INTO user_subscriptions (user_id, activity_id) VALUES (%s, 1) ON CONFLICT DO NOTHING",
                        (new_user_id_row[0],)
                    )

    async def update_user_username(self, telegram_id: int, username: str):
        async with self.pool.connection() as conn:
            await conn.execute("UPDATE users SET username = %s WHERE telegram_id = %s", (username.lower(), telegram_id))

    async def set_admin_status(self, telegram_id: int, is_admin: bool):
        async with self.pool.connection() as conn:
            await conn.execute("UPDATE users SET is_admin = %s WHERE telegram_id = %s", (is_admin, telegram_id))

    async def get_all_admins(self) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM users WHERE is_admin = TRUE")
                return await cur.fetchall()

    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
                result = await cur.fetchone()
                return result[0] if result else default

    async def set_setting(self, key: str, value: str):
        async with self.pool.connection() as conn:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, value)
            )

    async def handle_debt_repayment(self, user_id: int):
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT balance, grace_credit_used FROM users WHERE id = %s", (user_id,))
                user = await cur.fetchone()
                if user and user['grace_credit_used'] and user['balance'] >= 0:
                    await conn.execute("UPDATE users SET grace_credit_used = FALSE WHERE id = %s", (user_id,))
                    logger.info(f"Grace credit flag reset for user_id {user_id} due to positive balance.")

    async def get_returning_user_stats(self, telegram_id: int) -> dict:
        """Получает статистику (переведено, получено, списано) для вернувшегося пользователя"""
        user = await self.get_user(telegram_id=telegram_id)
        if not user:
            return None
        
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # Отправлено (людям)
                await cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE from_user_id = %s AND to_user_id IS NOT NULL", (user['id'],))
                sent = (await cur.fetchone())[0]
                
                # Получено (от людей)
                await cur.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE to_user_id = %s AND from_user_id IS NOT NULL", (user['id'],))
                received = (await cur.fetchone())[0]
                
                # Списано системой (демерредж, оплата событий)
                await cur.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM transactions "
                    "WHERE from_user_id = %s AND (to_user_id IS NULL OR to_user_id = 0)",
                    (user['id'],)
                )
                deducted = (await cur.fetchone())[0]
                
        return {
            'balance': user['balance'],
            'sent': sent,
            'received': received,
            'deducted': deducted
        }

    async def get_all_activities(self) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM activities WHERE is_active = TRUE ORDER BY name")
                return await cur.fetchall()

    async def get_activity(self, activity_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM activities WHERE id = %s", (activity_id,))
                return await cur.fetchone()

    async def get_user_subscriptions(self, telegram_id: int) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                user = await self.get_user(telegram_id=telegram_id)
                if not user: return []
                await cur.execute("SELECT us.activity_id FROM user_subscriptions us WHERE us.user_id = %s", (user['id'],))
                return await cur.fetchall()

    async def is_user_subscribed(self, telegram_id: int, activity_id: int) -> bool:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                user = await self.get_user(telegram_id=telegram_id)
                if not user: return False
                await cur.execute("SELECT 1 FROM user_subscriptions WHERE user_id = %s AND activity_id = %s", (user['id'], activity_id))
                return await cur.fetchone() is not None

    async def add_subscription(self, telegram_id: int, activity_id: int):
        async with self.pool.connection() as conn:
            user = await self.get_user(telegram_id=telegram_id)
            if user:
                await conn.execute("INSERT INTO user_subscriptions (user_id, activity_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user['id'], activity_id))

    async def remove_subscription(self, telegram_id: int, activity_id: int):
        async with self.pool.connection() as conn:
            user = await self.get_user(telegram_id=telegram_id)
            if user:
                if activity_id == GENERAL_ACTIVITY_ID:
                    logger.warning(f"User {telegram_id} tried to unsubscribe from system activity {GENERAL_ACTIVITY_ID}.")
                    return
                await conn.execute("DELETE FROM user_subscriptions WHERE user_id = %s AND activity_id = %s", (user['id'], activity_id))

    async def create_activity(self, name: str, description: str, end_date: Optional[date]) -> int:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO activities (name, description, end_date) VALUES (%s, %s, %s) RETURNING id",
                    (name, description, end_date)
                )
                result = await cur.fetchone()
                return result[0] if result else 0

    async def update_activity(
        self,
        activity_id: int,
        name: str = None,
        description: str = None,
        end_date: Any = ...,
        allow_manual_registration: bool = None
    ):
        async with self.pool.connection() as conn:
            if name is not None:
                await conn.execute("UPDATE activities SET name = %s WHERE id = %s", (name, activity_id))
            if description is not None:
                await conn.execute("UPDATE activities SET description = %s WHERE id = %s", (description, activity_id))
            if end_date is not ...:
                await conn.execute("UPDATE activities SET end_date = %s WHERE id = %s", (end_date, activity_id))
            if allow_manual_registration is not None:
                await conn.execute("UPDATE activities SET allow_manual_registration = %s WHERE id = %s", (allow_manual_registration, activity_id))

    async def delete_activity(self, activity_id: int):
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM activities WHERE id = %s", (activity_id,))

    async def get_all_events(self) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT e.*, a.name as activity_name, a.description as activity_description
                    FROM events e JOIN activities a ON e.activity_id = a.id
                    WHERE e.is_active = TRUE
                """)
                return await cur.fetchall()

    async def get_event(self, event_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("""
                    SELECT e.*, a.name as activity_name, a.description as activity_description, a.allow_manual_registration
                    FROM events e JOIN activities a ON e.activity_id = a.id
                    WHERE e.id = %s
                """, (event_id,))
                return await cur.fetchone()

    async def get_events_for_activity(self, activity_id: int) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM events WHERE activity_id = %s AND is_active = TRUE ORDER BY event_type, event_date, weekday, event_time",
                    (activity_id,)
                )
                return await cur.fetchall()

    async def create_event(self, **kwargs) -> int:
        valid_columns = {
            'activity_id', 'name', 'description', 'event_type', 'cost', 
            'link', 'reminder_time', 'reminder_text', 'created_by', 
            'event_date', 'weekday', 'event_time', 'end_date', 'last_run', 'is_active'
        }
        filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_columns}
        if not filtered_kwargs:
            return 0
            
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                columns = ', '.join(filtered_kwargs.keys())
                placeholders = ', '.join(['%s'] * len(filtered_kwargs))
                query = f"INSERT INTO events ({columns}) VALUES ({placeholders}) RETURNING id"
                await cur.execute(query, tuple(filtered_kwargs.values()))
                result = await cur.fetchone()
                return result[0] if result else 0

    async def update_event(self, event_id: int, **kwargs):
        valid_columns = {
            'activity_id', 'name', 'description', 'event_type', 'cost', 
            'link', 'reminder_time', 'reminder_text', 'created_by', 
            'event_date', 'weekday', 'event_time', 'end_date', 'last_run', 'is_active'
        }
        async with self.pool.connection() as conn:
            fields = []
            params = []
            for key, value in kwargs.items():
                if key in valid_columns:
                    fields.append(f"{key} = %s")
                    params.append(value)
            if not fields: return
            params.append(event_id)
            query = f"UPDATE events SET {', '.join(fields)} WHERE id = %s"
            await conn.execute(query, tuple(params))

    async def delete_event(self, event_id: int):
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM events WHERE id = %s", (event_id,))

    async def get_activity_subscribers(self, activity_id: int) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT u.* FROM users u JOIN user_subscriptions us ON u.id = us.user_id WHERE us.activity_id = %s",
                    (activity_id,)
                )
                return await cur.fetchall()

    async def get_event_overrides_for_date(self, event_id: int, override_date: date) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM event_registration_overrides WHERE event_id = %s AND override_date = %s",
                    (event_id, override_date)
                )
                return await cur.fetchall()

    async def get_user_event_override(self, telegram_id: int, event_id: int, override_date: date) -> Optional[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                user = await self.get_user(telegram_id=telegram_id)
                if not user: return None
                await cur.execute(
                    "SELECT * FROM event_registration_overrides WHERE user_id = %s AND event_id = %s AND override_date = %s",
                    (user['id'], event_id, override_date)
                )
                return await cur.fetchone()

    async def set_event_override(self, telegram_id: int, event_id: int, override_date: date, status: str):
        async with self.pool.connection() as conn:
            user = await self.get_user(telegram_id=telegram_id)
            if not user: return
            await conn.execute(
                """
                INSERT INTO event_registration_overrides (user_id, event_id, override_date, status)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, event_id, override_date) DO UPDATE SET status = EXCLUDED.status
                """,
                (user['id'], event_id, override_date, status)
            )

    async def remove_event_override(self, telegram_id: int, event_id: int, override_date: date):
        async with self.pool.connection() as conn:
            user = await self.get_user(telegram_id=telegram_id)
            if not user: return
            await conn.execute(
                "DELETE FROM event_registration_overrides WHERE user_id = %s AND event_id = %s AND override_date = %s",
                (user['id'], event_id, override_date)
            )

    # --- NEW: Extracted from handlers ---

    async def get_user_balance(self, telegram_id: int) -> Optional[Any]:
        """Возвращает баланс пользователя по telegram_id."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT balance FROM users WHERE telegram_id = %s", (telegram_id,))
                row = await cur.fetchone()
                return row['balance'] if row else None

    async def change_balance(self, target_user_id: int, amount, transaction_type: str, comment: str):
        """Изменение баланса пользователя (admin add/rem). amount может быть отрицательным для списания."""
        from decimal import Decimal
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

    async def get_transaction_history(self, telegram_id: int, date_limit: datetime) -> tuple:
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

    async def get_users_by_ids(self, user_ids: list) -> list:
        """Возвращает полные данные пользователей по списку ID."""
        if not user_ids:
            return []
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM users WHERE id = ANY(%s::int[])", (list(user_ids),))
                return await cur.fetchall()

    async def get_all_users(self) -> List[Dict[str, Any]]:
        """Возвращает всех пользователей (без фонда). ОСТОРОЖНО: может загрузить память."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM users WHERE telegram_id != 0 ORDER BY id")
                return await cur.fetchall()
                
    async def get_total_users_count(self) -> int:
        """Возвращает общее количество пользователей (исключая фонд)."""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM users WHERE telegram_id != 0")
                return (await cur.fetchone())[0]
                
    async def get_users_page(self, limit: int, offset: int) -> List[Dict[str, Any]]:
        """Возвращает список пользователей с лимитом и смещением."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM users WHERE telegram_id != 0 ORDER BY id LIMIT %s OFFSET %s", (limit, offset))
                return await cur.fetchall()

    # --- TAG RULES ---

    async def get_all_tag_rules(self) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM tag_rules ORDER BY id")
                return await cur.fetchall()

    async def get_active_tag_rules(self) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM tag_rules WHERE is_active = TRUE ORDER BY id")
                return await cur.fetchall()

    async def get_tag_rule(self, rule_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM tag_rules WHERE id = %s", (rule_id,))
                return await cur.fetchone()

    async def create_tag_rule(self, hashtag: str, min_chars: int, reward, limit_amount: int, limit_period_days: int,
                              thread_id: Optional[int], group_msg: Optional[str], bot_msg: Optional[str],
                              reaction: str) -> int:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO tag_rules (hashtag, min_chars, reward, limit_amount, limit_period_days, thread_id, group_msg, bot_msg, reaction)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (hashtag.lstrip('#').lower(), min_chars, reward, limit_amount, limit_period_days, thread_id, group_msg, bot_msg, reaction)
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def delete_tag_rule(self, rule_id: int):
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM tag_rules WHERE id = %s", (rule_id,))

    async def get_rewarded_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Проверяет, было ли уже начислено за это сообщение."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM tag_rewards_log WHERE message_id = %s", (message_id,))
                return await cur.fetchone()

    async def log_tag_reward(self, user_telegram_id: int, message_id: int, rule_id: int):
        async with self.pool.connection() as conn:
            await conn.execute(
                """INSERT INTO tag_rewards_log (user_telegram_id, message_id, rule_id)
                   VALUES (%s, %s, %s) ON CONFLICT (message_id) DO NOTHING""",
                (user_telegram_id, message_id, rule_id)
            )

    async def count_today_tag_rewards(self, user_telegram_id: int, rule_id: int) -> int:
        """Считает количество начислений за сегодня для данного пользователя и правила."""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT COUNT(*) FROM tag_rewards_log
                       WHERE user_telegram_id = %s AND rule_id = %s
                         AND rewarded_at >= CURRENT_DATE""",
                    (user_telegram_id, rule_id)
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def award_tag_reward(self, telegram_id: int, reward, comment: str):
        """Начисляет орфы пользователю за хэштег-пост (от фонда, тип manual_add)."""
        from decimal import Decimal
        reward = Decimal(str(reward))
        user = await self.get_user(telegram_id=telegram_id)
        if not user:
            return
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE users SET balance = balance + %s WHERE telegram_id = %s", (reward, telegram_id))
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (0, %s, %s, 'tag_reward', %s)",
                    (user['id'], reward, comment)
                )
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE telegram_id = %s", (telegram_id,))

    async def award_tag_reward_once(
        self,
        user_telegram_id: int,
        message_id: int,
        rule_id: int,
        reward,
        comment: str,
        limit_amount: int = 0,
        limit_period_days: int = 1
    ) -> bool:
        """
        Атомарно логирует сообщение и начисляет награду только один раз.
        Возвращает True, если начисление выполнено; False, если сообщение уже обработано.
        """
        from decimal import Decimal
        reward = Decimal(str(reward))
        user = await self.get_user(telegram_id=user_telegram_id)
        if not user:
            return False

        async with self.pool.connection() as conn:
            async with conn.transaction():
                # Блокируем пользователя, чтобы сериализовать награды и избежать гонки за лимитами
                await conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user['id'],))
                
                if limit_amount > 0:
                    query_params = [user_telegram_id, rule_id]
                    if limit_period_days == 0:
                        # 0 = за все время
                        date_filter = ""
                    else:
                        date_filter = "AND rewarded_at >= (CURRENT_DATE - %s::interval)"
                        query_params.append(f"{limit_period_days - 1} days")

                    query = f"""SELECT COUNT(*) FROM tag_rewards_log
                                WHERE user_telegram_id = %s AND rule_id = %s
                                {date_filter}"""
                    cur = await conn.execute(query, tuple(query_params))
                    row = await cur.fetchone()
                    if row and row[0] >= limit_amount:
                        return False

                log_cursor = await conn.execute(
                    """
                    INSERT INTO tag_rewards_log (user_telegram_id, message_id, rule_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (message_id) DO NOTHING
                    RETURNING id
                    """,
                    (user_telegram_id, message_id, rule_id),
                )
                log_row = await log_cursor.fetchone()
                if not log_row:
                    return False

                await conn.execute(
                    "UPDATE users SET balance = balance + %s, transaction_count = transaction_count + 1 WHERE telegram_id = %s",
                    (reward, user_telegram_id),
                )
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'tag_reward', %s)",
                    (SYSTEM_FUND_USER_ID, user['id'], reward, comment),
                )
                return True

    async def create_offer(
        self,
        seller_telegram_id: int,
        title: str,
        description: Optional[str],
        price,
        photo_id: Optional[str],
        quantity: int = 1,
        duration_days: int = 7
    ) -> int:
        """Создает объявление в БД и возвращает его ID."""
        from decimal import Decimal
        price = Decimal(str(price))
        user = await self.get_user(telegram_id=seller_telegram_id)
        if not user:
            raise ValueError("seller_not_found")
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO offers (seller_id, title, description, price, photo_id, status, quantity, expires_at)
                       VALUES (%s, %s, %s, %s, %s, 'active', %s, CURRENT_TIMESTAMP + %s * interval '1 day') RETURNING id""",
                    (user['id'], title, description, price, photo_id, quantity, duration_days)
                )
                row = await cur.fetchone()
                return row[0]

    async def get_offer(self, offer_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает объявление по ID, включая информацию о продавце и покупателе."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """SELECT o.*, 
                              s.username as seller_username, s.telegram_id as seller_telegram_id,
                              b.username as buyer_username, b.telegram_id as buyer_telegram_id
                       FROM offers o
                       JOIN users s ON o.seller_id = s.id
                       LEFT JOIN users b ON o.buyer_id = b.id
                       WHERE o.id = %s""",
                    (offer_id,)
                )
                return await cur.fetchone()

    async def update_offer_message(self, offer_id: int, chat_id: int, message_id: int):
        """Сохраняет ID сообщения, опубликованного в группе."""
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE offers SET chat_id = %s, message_id = %s WHERE id = %s",
                (chat_id, message_id, offer_id)
            )

    async def execute_offer_purchase(self, offer_id: int, buyer_telegram_id: int) -> Dict[str, Any]:
        """
        Выполняет транзакцию покупки предложения.
        Проверяет баланс покупателя, осуществляет перевод орфов от покупателя к продавцу,
        записывает транзакцию, уменьшает количество на 1.
        Если количество падает до 0, переводит статус в 'sold'.
        Проверяет, не истек ли срок действия (expires_at).
        Выполняется атомарно с использованием FOR UPDATE.
        """
        from decimal import Decimal
        from datetime import datetime, timezone
        is_expired = False
        async with self.pool.connection() as conn:
            # 1. Сначала проверяем срок действия объявления вне транзакции
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM offers WHERE id = %s", (offer_id,))
                offer = await cur.fetchone()
            
            if not offer:
                raise ValueError("offer_not_found")
            if offer['status'] != 'active':
                raise ValueError(f"offer_already_{offer['status']}")
            
            if offer['expires_at'] and datetime.now(timezone.utc) > offer['expires_at']:
                async with conn.transaction():
                    await conn.execute("UPDATE offers SET status = 'expired' WHERE id = %s", (offer_id,))
                is_expired = True
        
        if is_expired:
            raise ValueError("offer_expired")
            
        async with self.pool.connection() as conn:
            async with conn.transaction():
                # 2. Получаем объявление для покупки (с блокировкой FOR UPDATE)
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM offers WHERE id = %s FOR UPDATE", (offer_id,))
                    offer = await cur.fetchone()
                
                if not offer:
                    raise ValueError("offer_not_found")
                if offer['status'] != 'active':
                    raise ValueError(f"offer_already_{offer['status']}")
                
                # Проверяем срок действия
                if offer['expires_at'] and datetime.now(timezone.utc) > offer['expires_at']:
                    await conn.execute("UPDATE offers SET status = 'expired' WHERE id = %s", (offer_id,))
                    raise ValueError("offer_expired")
                
                # 2. Получаем продавца
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM users WHERE id = %s FOR UPDATE", (offer['seller_id'],))
                    seller = await cur.fetchone()
                if not seller:
                    raise ValueError("seller_not_found")
                
                # 3. Получаем покупателя
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM users WHERE telegram_id = %s FOR UPDATE", (buyer_telegram_id,))
                    buyer = await cur.fetchone()
                if not buyer:
                    raise ValueError("buyer_not_found")
                
                if buyer['id'] == seller['id']:
                    raise ValueError("cannot_buy_own_offer")
                
                price = Decimal(str(offer['price']))
                if buyer['balance'] < price:
                    raise ValueError("insufficient_funds")
                
                # 4. Обновляем балансы
                await conn.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (price, buyer['id']))
                await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (price, seller['id']))
                
                # 5. Записываем транзакцию
                comment = f"Покупка товара: {offer['title']}"
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'purchase', %s)",
                    (buyer['id'], seller['id'], price, comment)
                )
                
                # 6. Увеличиваем счетчик транзакций
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id IN (%s, %s)", (buyer['id'], seller['id']))
                
                # 7. Уменьшаем количество и обновляем статус
                new_quantity = offer['quantity'] - 1
                new_status = 'sold' if new_quantity <= 0 else 'active'
                
                await conn.execute(
                    "UPDATE offers SET quantity = %s, status = %s, buyer_id = %s WHERE id = %s",
                    (new_quantity, new_status, buyer['id'], offer_id)
                )
                
                # Получаем обновленное объявление
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM offers WHERE id = %s", (offer_id,))
                    updated_offer = await cur.fetchone()
                
                return {
                    "offer": updated_offer,
                    "seller": seller,
                    "buyer": buyer,
                    "price": price,
                    "remaining_quantity": new_quantity
                }

    async def cancel_offer(self, offer_id: int, user_telegram_id: int) -> bool:
        """
        Отменяет объявление. Отменить может либо продавец, либо администратор.
        Возвращает True в случае успеха.
        """
        user = await self.get_user(telegram_id=user_telegram_id)
        if not user:
            return False
        
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM offers WHERE id = %s FOR UPDATE", (offer_id,))
                    offer = await cur.fetchone()
                if not offer:
                    return False
                
                # Проверяем права: либо создатель (seller_id), либо админ
                if offer['seller_id'] != user['id'] and not user['is_admin']:
                    return False
                
                if offer['status'] != 'active':
                    return False
                
                await conn.execute("UPDATE offers SET status = 'cancelled' WHERE id = %s", (offer_id,))
                return True


db = Database(CONNINFO)
