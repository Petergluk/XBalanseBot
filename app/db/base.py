# app/db/base.py
import logging
from typing import Optional
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

class BaseRepository:
    """Базовый репозиторий, предоставляющий доступ к пулу соединений."""
    def __init__(self, conninfo: str, *args, **kwargs):
        self.conninfo = conninfo
        self.pool: Optional[AsyncConnectionPool] = None
        super().__init__(*args, **kwargs)
