# app/db/__init__.py
import os
import logging

from app.db.connection import ConnectionManager
from app.db.users import UserRepository
from app.db.activities import ActivityRepository
from app.db.events import EventRepository
from app.db.transactions import TransactionRepository
from app.db.offers import OfferRepository
from app.db.tags import TagRewardRepository
from app.db.settings import SettingRepository

logger = logging.getLogger(__name__)

# --- Определение CONNINFO ---
if database_url := os.environ.get("DATABASE_URL"):
    CONNINFO = database_url
    logger.info("Using DATABASE_URL for database connection.")
else:
    logger.info("Using individual POSTGRES variables for database connection.")
    from app.config import (
        POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    )
    CONNINFO = (
        f"host={POSTGRES_HOST} port={POSTGRES_PORT} dbname={POSTGRES_DB} "
        f"user={POSTGRES_USER} password={POSTGRES_PASSWORD}"
    )


class Database(
    ConnectionManager,
    UserRepository,
    ActivityRepository,
    EventRepository,
    TransactionRepository,
    OfferRepository,
    TagRewardRepository,
    SettingRepository
):
    """Единый фасад для всех репозиториев базы данных (паттерн Facade)."""
    def __init__(self, conninfo: str):
        super().__init__(conninfo)


# Экспортируем глобальный экземпляр БД для обратной совместимости
db = Database(CONNINFO)
