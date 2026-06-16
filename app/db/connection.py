# app/db/connection.py
import asyncio
import logging
from psycopg_pool import AsyncConnectionPool
from app.lexicon import LEXICON_RU
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)

class ConnectionManager(BaseRepository):
    """Класс для управления подключением и инициализации структуры базы данных."""
    
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
