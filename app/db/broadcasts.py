# app/db/broadcasts.py
import logging
from datetime import datetime
from typing import Any, Dict, List
from psycopg.rows import dict_row
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)


class BroadcastRepository(BaseRepository):
    """Репозиторий для хранения и выборки отложенных рассылок (/broadcast) в PostgreSQL."""

    async def create_scheduled_broadcast(
        self,
        activity_id: int,
        source_chat_id: int,
        source_message_id: int,
        admin_chat_id: int,
        scheduled_at: datetime,
    ) -> int:
        """Сохраняет запланированную рассылку в БД и возвращает её ID."""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO scheduled_broadcasts
                       (activity_id, source_chat_id, source_message_id, admin_chat_id, scheduled_at, status)
                       VALUES (%s, %s, %s, %s, %s, 'pending')
                       RETURNING id""",
                    (activity_id, source_chat_id, source_message_id, admin_chat_id, scheduled_at),
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def claim_due_scheduled_broadcasts(self, now: datetime) -> List[Dict[str, Any]]:
        """
        Атомарно переводит наступившие рассылки из статуса 'pending' в 'processing'
        (с защитой FOR UPDATE SKIP LOCKED) и возвращает их список.
        """
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """UPDATE scheduled_broadcasts
                           SET status = 'processing'
                           WHERE id IN (
                               SELECT id FROM scheduled_broadcasts
                               WHERE status = 'pending' AND scheduled_at <= %s
                               ORDER BY scheduled_at ASC
                               FOR UPDATE SKIP LOCKED
                           )
                           RETURNING *""",
                        (now,),
                    )
                    return await cur.fetchall()

    async def mark_scheduled_broadcast_status(self, broadcast_id: int, status: str) -> None:
        """Обновляет статус рассылки ('sent' или 'failed')."""
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE scheduled_broadcasts SET status = %s WHERE id = %s",
                (status, broadcast_id),
            )

    async def cancel_scheduled_broadcast(self, broadcast_id: int) -> bool:
        """Отменяет ожидающую рассылку (status='pending') по её ID."""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE scheduled_broadcasts SET status = 'cancelled' WHERE id = %s AND status = 'pending' RETURNING id",
                    (broadcast_id,),
                )
                row = await cur.fetchone()
                return bool(row)
