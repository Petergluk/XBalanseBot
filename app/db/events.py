# app/db/events.py
import logging
from typing import Any, Dict, List, Optional
from datetime import date
from psycopg.rows import dict_row
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)

class EventRepository(BaseRepository):
    """Репозиторий для работы с событиями и оверрайдами регистраций."""

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
            if not fields:
                return
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
                if not user:
                    return None
                await cur.execute(
                    "SELECT * FROM event_registration_overrides WHERE user_id = %s AND event_id = %s AND override_date = %s",
                    (user['id'], event_id, override_date)
                )
                return await cur.fetchone()

    async def set_event_override(self, telegram_id: int, event_id: int, override_date: date, status: str):
        async with self.pool.connection() as conn:
            user = await self.get_user(telegram_id=telegram_id)
            if not user:
                return
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
            if not user:
                return
            await conn.execute(
                "DELETE FROM event_registration_overrides WHERE user_id = %s AND event_id = %s AND override_date = %s",
                (user['id'], event_id, override_date)
            )
