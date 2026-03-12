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
MAIN_GROUP_ID = int(os.environ.get("MAIN_GROUP_ID"))
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID"))

# --- Настройки базы данных PostgreSQL ---
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", 5432))
POSTGRES_DB = os.environ.get("POSTGRES_DB")
POSTGRES_USER = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")

# --- Настройки Redis ---
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")

CURRENCY_SYMBOL = "Ӫ"

# --- Настройки вебхуков ---
WEB_SERVER_HOST = os.environ.get("WEB_SERVER_HOST", '0.0.0.0')
WEBHOOK_PORT = int(os.environ.get("PORT", 8080))
TRIBUTE_WEBHOOK_SECRET = os.environ.get("TRIBUTE_WEBHOOK_SECRET")


# Переключатель режимов. По умолчанию - серверный (False).
DEV_MODE = os.environ.get("DEV_MODE", "False").lower() in ('true', '1', 't')

# --- Тексты по умолчанию ---

# Тексты по умолчанию перенесены в app/lexicon.py
# (Оставлены только комментарии)

