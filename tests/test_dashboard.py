# tests/test_dashboard.py
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

# Устанавливаем тестовые переменные окружения до импорта app
os.environ.setdefault("BOT_TOKEN", "test:fake_token")
os.environ.setdefault("MAIN_GROUP_ID", "-1001234567890")
os.environ.setdefault("SUPER_ADMIN_ID", "382432926")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("DEV_MODE", "True")
os.environ.setdefault("POSTGRES_DB", "xblns_test")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "postgres")

from app.services.dashboard import (
    format_uptime,
    format_telegram_status,
    render_dashboard_html,
    get_system_status,
    dashboard_page_handler,
    api_status_handler,
)


def test_format_uptime():
    assert format_uptime(45) == "45с"
    assert format_uptime(125) == "2м 5с"
    assert format_uptime(3665) == "1ч 1м 5с"
    assert format_uptime(90061) == "1д 1ч 1м 1с"


def test_render_dashboard_html():
    sample_data = {
        "overall_status": "ok",
        "timestamp": "2026-11-01 02:00:00 UTC",
        "dashboard_url": "https://test.koyeb.app/status",
        "app": {
            "name": "Koyeb App Core",
            "status": "ok",
            "uptime": "1д 2ч 3м 4с",
            "environment": "Production (Koyeb)",
            "python_version": "3.13.0",
            "server_time_utc": "2026-11-01 02:00:00 UTC"
        },
        "database": {
            "name": "Supabase PostgreSQL",
            "status": "ok",
            "latency_ms": 42.5,
            "users_count": 100,
            "transactions_count": 250,
            "error": None
        },
        "redis": {
            "name": "Upstash Redis",
            "status": "ok",
            "latency_ms": 18.2,
            "error": None
        },
        "telegram": {
            "name": "Telegram Bot API",
            "status": "ok",
            "latency_ms": 55.1,
            "bot_username": "@TestBot",
            "pending_updates": 0,
            "last_error_message": None,
            "error": None
        },
        "scheduler": {
            "name": "APScheduler",
            "status": "ok",
            "running": True,
            "jobs_count": 2,
            "jobs": []
        }
    }

    html = render_dashboard_html(sample_data)
    assert "<!DOCTYPE html>" in html
    assert "XBalanseBot Status" in html
    assert "Koyeb App Core" in html
    assert "Supabase Database" in html
    assert "Upstash Redis" in html
    assert "Telegram Bot API" in html
    assert "Планировщик задач" in html
    assert "triggerRefresh" in html


def test_format_telegram_status():
    sample_data = {
        "overall_status": "ok",
        "timestamp": "2026-11-01 02:00:00 UTC",
        "app": {
            "status": "ok",
            "uptime": "1ч 10м",
            "environment": "Production"
        },
        "telegram": {
            "status": "ok",
            "latency_ms": 35.0,
            "bot_username": "@XBalanseBot",
            "pending_updates": 0,
            "last_error_message": None
        },
        "database": {
            "status": "ok",
            "latency_ms": 40.0,
            "users_count": 50,
            "transactions_count": 120,
            "error": None
        },
        "redis": {
            "status": "ok",
            "latency_ms": 20.0,
            "error": None
        },
        "scheduler": {
            "status": "ok",
            "running": True,
            "jobs_count": 3
        }
    }

    text = format_telegram_status(sample_data)
    assert "Диагностика XBalanseBot" in text
    assert "Koyeb (Бот):" in text
    assert "Telegram API:" in text
    assert "Supabase (PostgreSQL):" in text
    assert "Upstash (Redis):" in text
    assert "Планировщик:" in text


@pytest.mark.asyncio
async def test_get_system_status_structure():
    mock_bot = AsyncMock()
    mock_bot.get_me.return_value = MagicMock(username="XBalanseBot", first_name="XBalanse", id=12345)
    mock_bot.get_webhook_info.return_value = MagicMock(
        url="https://test.koyeb.app/webhook/telegram",
        pending_update_count=0,
        last_error_message=None,
        last_error_date=None,
        has_custom_certificate=False
    )

    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    mock_scheduler.get_jobs.return_value = []

    status = await get_system_status(bot=mock_bot, scheduler=mock_scheduler)

    assert "overall_status" in status
    assert "app" in status
    assert "database" in status
    assert "redis" in status
    assert "telegram" in status
    assert "scheduler" in status
    assert status["telegram"]["bot_username"] == "@XBalanseBot"


@pytest.mark.asyncio
async def test_dashboard_handlers():
    mock_bot = AsyncMock()
    mock_bot.get_me.return_value = MagicMock(username="XBalanseBot", first_name="XBalanse", id=12345)
    mock_bot.get_webhook_info.return_value = MagicMock(
        url="https://test.koyeb.app/webhook/telegram",
        pending_update_count=0,
        last_error_message=None,
        last_error_date=None
    )

    app = web.Application()
    app['bot'] = mock_bot
    app['scheduler'] = None

    req_page = make_mocked_request('GET', '/status', app=app)
    resp_page = await dashboard_page_handler(req_page)
    assert resp_page.status == 200
    assert resp_page.content_type == 'text/html'
    assert "XBalanseBot Status" in resp_page.text

    req_api = make_mocked_request('GET', '/api/status', app=app)
    resp_api = await api_status_handler(req_api)
    assert resp_api.status == 200
    assert resp_api.content_type == 'application/json'


if __name__ == "__main__":
    import asyncio
    test_format_uptime()
    test_render_dashboard_html()
    test_format_telegram_status()
    asyncio.run(test_get_system_status_structure())
    asyncio.run(test_dashboard_handlers())
    print("All dashboard tests passed successfully!")

