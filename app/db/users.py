# app/db/users.py
import logging
from typing import Any, Dict, List, Optional
from psycopg.rows import dict_row
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)

class UserRepository(BaseRepository):
    """Репозиторий для работы с пользователями."""

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

    async def handle_debt_repayment(self, user_id: int):
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT balance, grace_credit_used FROM users WHERE id = %s", (user_id,))
                user = await cur.fetchone()
                if user and user['grace_credit_used'] and user['balance'] >= 0:
                    await conn.execute("UPDATE users SET grace_credit_used = FALSE WHERE id = %s", (user_id,))
                    logger.info(f"Grace credit flag reset for user_id {user_id} due to positive balance.")

    async def get_returning_user_stats(self, telegram_id: int) -> Optional[dict]:
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
