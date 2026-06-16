# app/db/settings.py
import logging
from typing import Optional
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)

class SettingRepository(BaseRepository):
    """Репозиторий для управления системными настройками."""

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
