# tests/conftest.py
"""
Фикстуры для тестирования.

ВАЖНО: Переменные окружения для БД ПРИНУДИТЕЛЬНО перезаписываются,
чтобы тесты НИКОГДА не затронули основную базу данных.
Тесты используют отдельную базу `xblns_test`.
"""
import asyncio
import os
import pytest

# === ПРИНУДИТЕЛЬНАЯ перезапись переменных БД ===
# НЕ setdefault! Именно os.environ[...] = ..., чтобы перебить Docker env.
os.environ["POSTGRES_DB"] = "xblns_test"
os.environ["POSTGRES_HOST"] = os.environ.get("POSTGRES_HOST", "localhost")
os.environ["POSTGRES_PORT"] = os.environ.get("POSTGRES_PORT", "5432")
os.environ["POSTGRES_USER"] = os.environ.get("POSTGRES_USER", "postgres")
os.environ["POSTGRES_PASSWORD"] = os.environ.get("POSTGRES_PASSWORD", "postgres")

os.environ.setdefault("BOT_TOKEN", "test:fake_token")
os.environ.setdefault("MAIN_GROUP_ID", "-1001234567890")
os.environ.setdefault("SUPER_ADMIN_ID", "382432926")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("DEV_MODE", "True")


async def _ensure_test_database_exists():
    """
    Создаёт тестовую БД `xblns_test`, если она ещё не существует,
    и прогоняет Alembic-миграции для создания всех таблиц.
    """
    import psycopg

    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_PORT"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    test_db = os.environ["POSTGRES_DB"]  # xblns_test

    # Подключаемся к системной БД `postgres` для создания тестовой
    sys_conninfo = f"host={host} port={port} dbname=postgres user={user} password={password}"

    conn = await psycopg.AsyncConnection.connect(sys_conninfo, autocommit=True)
    try:
        cur = await conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (test_db,)
        )
        exists = await cur.fetchone()
        if not exists:
            await conn.execute(f'CREATE DATABASE "{test_db}"')
            print(f"✅ Created test database: {test_db}")
    finally:
        await conn.close()

    # Прогоняем Alembic-миграции на тестовой БД
    import sys
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True,
        cwd=os.path.dirname(os.path.dirname(__file__))
    )
    if result.returncode != 0:
        print(f"⚠️ Alembic migration stderr: {result.stderr}")
    else:
        print(f"✅ Alembic migrations applied to {test_db}")





@pytest.fixture(scope="session", autouse=True)
async def _setup_test_db():
    """Автоматически создаёт тестовую БД перед первым тестом в сессии."""
    await _ensure_test_database_exists()


@pytest.fixture
async def db():
    """Создает свежий экземпляр Database для каждого теста с откатом данных."""
    from app.database import Database, CONNINFO
    test_db = Database(CONNINFO)
    await test_db.initialize()
    yield test_db
    # Очистка: удаляем тестовые данные (только в xblns_test!)
    async with test_db.pool.connection() as conn:
        await conn.execute("DELETE FROM offers")
        await conn.execute("DELETE FROM event_registration_overrides")
        await conn.execute("DELETE FROM transactions WHERE id > 0")
        await conn.execute("DELETE FROM events")
        await conn.execute("DELETE FROM user_subscriptions WHERE user_id > 0")
        await conn.execute("DELETE FROM users WHERE id > 0")
        # Не удаляем fund (id=0), activities (id=1), и settings
    await test_db.close()
