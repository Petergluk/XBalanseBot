# app/db/activities.py
import logging
from typing import Any, Dict, List, Optional
from datetime import date
from psycopg.rows import dict_row
from app.config import GENERAL_ACTIVITY_ID
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)

class ActivityRepository(BaseRepository):
    """Репозиторий для работы с активностями (кружками) и подписками."""

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
                if not user:
                    return []
                await cur.execute("SELECT us.activity_id FROM user_subscriptions us WHERE us.user_id = %s", (user['id'],))
                return await cur.fetchall()

    async def is_user_subscribed(self, telegram_id: int, activity_id: int) -> bool:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                user = await self.get_user(telegram_id=telegram_id)
                if not user:
                    return False
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
