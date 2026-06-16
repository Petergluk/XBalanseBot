# XBalanseBot/app/config.py
# FULL FILE EMITTED: YES
# v1.6.1
# 2025-08-29 04:15:00
"""
Модуль для хранения конфигурационных переменных и текстов по умолчанию.

Версия 1.6.1:
- Обновлена версия после внедрения CallbackData.

Версия 1.6.0:
- Удалены упоминания команд /edit_*, /delete_* из справки для администратора
  в `DEFAULT_HELP_TEXT_ADMIN_ADDON` в связи с переходом на инлайн-управление.
- Обновлены тексты справки DEFAULT_HELP_TEXT_USER и DEFAULT_HELP_TEXT_GROUP.
- В справку добавлена информация о новой команде /menu.
- Изменена формулировка для поощрения использования меню.
"""
import os

# --- Основные настройки ---
# Секреты и ID считываются из переменных окружения.
BOT_TOKEN = os.environ.get("BOT_TOKEN")
MAIN_GROUP_ID_RAW = os.environ.get("MAIN_GROUP_ID")
SUPER_ADMIN_ID_RAW = os.environ.get("SUPER_ADMIN_ID")

DATABASE_URL = os.environ.get("DATABASE_URL")

# --- Валидация конфигурации при старте ---
if not BOT_TOKEN:
    raise RuntimeError("❌ ERROR: Environment variable 'BOT_TOKEN' is missing or empty.")

if not MAIN_GROUP_ID_RAW:
    raise RuntimeError("❌ ERROR: Environment variable 'MAIN_GROUP_ID' is missing or empty.")
try:
    MAIN_GROUP_ID = int(MAIN_GROUP_ID_RAW)
except ValueError:
    raise RuntimeError(f"❌ ERROR: Environment variable 'MAIN_GROUP_ID' must be an integer, got: {MAIN_GROUP_ID_RAW!r}")

if not SUPER_ADMIN_ID_RAW:
    raise RuntimeError("❌ ERROR: Environment variable 'SUPER_ADMIN_ID' is missing or empty.")
try:
    SUPER_ADMIN_ID = int(SUPER_ADMIN_ID_RAW)
except ValueError:
    raise RuntimeError(f"❌ ERROR: Environment variable 'SUPER_ADMIN_ID' must be an integer, got: {SUPER_ADMIN_ID_RAW!r}")

# --- Настройки базы данных PostgreSQL ---
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT_RAW = os.environ.get("POSTGRES_PORT", "5432")
try:
    POSTGRES_PORT = int(POSTGRES_PORT_RAW)
except ValueError:
    raise RuntimeError(f"❌ ERROR: Environment variable 'POSTGRES_PORT' must be an integer, got: {POSTGRES_PORT_RAW!r}")

if not DATABASE_URL:
    POSTGRES_DB = os.environ.get("POSTGRES_DB")
    POSTGRES_USER = os.environ.get("POSTGRES_USER")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
    if not POSTGRES_DB:
        raise RuntimeError("❌ ERROR: Environment variable 'POSTGRES_DB' is missing (and 'DATABASE_URL' is not set).")
    if not POSTGRES_USER:
        raise RuntimeError("❌ ERROR: Environment variable 'POSTGRES_USER' is missing (and 'DATABASE_URL' is not set).")
    if not POSTGRES_PASSWORD:
        raise RuntimeError("❌ ERROR: Environment variable 'POSTGRES_PASSWORD' is missing (and 'DATABASE_URL' is not set).")
else:
    # Если DATABASE_URL задана, допускаем отсутствие отдельных переменных
    POSTGRES_DB = os.environ.get("POSTGRES_DB")
    POSTGRES_USER = os.environ.get("POSTGRES_USER")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")

# --- Настройки Redis ---
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_URL = os.environ.get("REDIS_URL")

CURRENCY_SYMBOL = "Ӫ"

# --- Настройки вебхуков ---
WEB_SERVER_HOST = os.environ.get("WEB_SERVER_HOST", '0.0.0.0')
PORT_RAW = os.environ.get("PORT", "8080")
try:
    WEBHOOK_PORT = int(PORT_RAW)
except ValueError:
    raise RuntimeError(f"❌ ERROR: Environment variable 'PORT' must be an integer, got: {PORT_RAW!r}")
TRIBUTE_WEBHOOK_SECRET = os.environ.get("TRIBUTE_WEBHOOK_SECRET")
WEBHOOK_SECRET_TOKEN = os.environ.get("WEBHOOK_SECRET_TOKEN")


# Переключатель режимов. По умолчанию - серверный (False).
DEV_MODE = os.environ.get("DEV_MODE", "False").lower() in ('true', '1', 't')

# --- Системные константы ---
GENERAL_ACTIVITY_ID = 1
SYSTEM_FUND_USER_ID = 0

# --- Тексты по умолчанию ---

# Тексты по умолчанию перенесены в app/lexicon.py
# (Оставлены только комментарии)

