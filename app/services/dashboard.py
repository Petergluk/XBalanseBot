# XBalanseBot/app/services/dashboard.py
"""
Модуль системного мониторинга и веб-дашборда для XBalanseBot.
Позволяет в одном окне (в браузере и Telegram) проверить работоспособность:
- Сервера бота на Koyeb
- Базы данных Supabase (PostgreSQL)
- Хранилища Upstash (Redis)
- Telegram Bot API и Webhook
- Фонового планировщика задач (APScheduler)
"""
import os
import sys
import time
import json
import logging
from datetime import datetime, timezone
from aiohttp import web
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import (
    DEV_MODE, REDIS_URL, REDIS_HOST, WEBHOOK_HOST
)
from app.database import db

logger = logging.getLogger(__name__)

# Фиксируем время запуска процесса
START_TIME = datetime.now(timezone.utc)


def format_uptime(seconds: float) -> str:
    """Форматирует количество секунд в читаемую строку аптайма."""
    secs = int(seconds)
    days, secs = divmod(secs, 86400)
    hours, secs = divmod(secs, 3600)
    minutes, secs = divmod(secs, 60)

    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0 or days > 0:
        parts.append(f"{hours}ч")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}м")
    parts.append(f"{secs}с")
    return " ".join(parts)


def get_dashboard_url() -> str:
    """Возвращает публичный URL дашборда."""
    host = WEBHOOK_HOST or "xbalansebot-xbalance-1fe9cf64.koyeb.app"
    return f"https://{host}/status"


async def get_system_status(bot: Bot = None, scheduler: AsyncIOScheduler = None) -> dict:
    """Выполняет реальные тесты доступности всех компонентов системы."""
    now_utc = datetime.now(timezone.utc)
    uptime_sec = (now_utc - START_TIME).total_seconds()

    # 1. Koyeb Core
    app_status = {
        "name": "Koyeb App Core",
        "status": "ok",
        "uptime": format_uptime(uptime_sec),
        "uptime_seconds": int(uptime_sec),
        "environment": "Development (Polling)" if DEV_MODE else "Production (Koyeb)",
        "python_version": sys.version.split()[0],
        "server_time_utc": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    # 2. Supabase PostgreSQL
    db_status = {
        "name": "Supabase PostgreSQL",
        "status": "unknown",
        "latency_ms": None,
        "users_count": None,
        "transactions_count": None,
        "error": None
    }
    try:
        t0 = time.perf_counter()
        if db.pool and not db.pool.closed:
            async with db.pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1;")
                    await cur.execute("SELECT count(*) FROM users;")
                    users_row = await cur.fetchone()
                    users_count = users_row[0] if users_row else 0

                    await cur.execute("SELECT count(*) FROM transactions;")
                    tx_row = await cur.fetchone()
                    tx_count = tx_row[0] if tx_row else 0

            db_status["status"] = "ok"
            db_status["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            db_status["users_count"] = users_count
            db_status["transactions_count"] = tx_count
        else:
            db_status["status"] = "error"
            db_status["error"] = "Пул соединений не открыт"
    except Exception as e:
        db_status["status"] = "error"
        db_status["error"] = str(e)
        logger.warning(f"Dashboard DB check failed: {e}")

    # 3. Upstash Redis
    redis_status = {
        "name": "Upstash Redis",
        "status": "unknown",
        "latency_ms": None,
        "error": None
    }
    try:
        import redis.asyncio as aioredis
        r_url = REDIS_URL if REDIS_URL else f"redis://{REDIS_HOST}:6379/0"
        t0 = time.perf_counter()
        client = aioredis.from_url(r_url, socket_timeout=3.0)
        pong = await client.ping()
        await client.aclose()
        if pong:
            redis_status["status"] = "ok"
            redis_status["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        else:
            redis_status["status"] = "error"
            redis_status["error"] = "Нет ответа PONG от Redis"
    except Exception as e:
        redis_status["status"] = "error"
        redis_status["error"] = str(e)
        logger.warning(f"Dashboard Redis check failed: {e}")

    # 4. Telegram Bot API & Webhook
    tg_status = {
        "name": "Telegram Bot API",
        "status": "unknown",
        "latency_ms": None,
        "bot_username": None,
        "bot_id": None,
        "webhook_url": None,
        "pending_updates": 0,
        "last_error_message": None,
        "last_error_date": None,
        "error": None
    }
    if bot:
        try:
            t0 = time.perf_counter()
            me = await bot.get_me()
            wh_info = await bot.get_webhook_info()
            tg_status["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            tg_status["bot_username"] = f"@{me.username}" if me.username else me.first_name
            tg_status["bot_id"] = me.id
            tg_status["webhook_url"] = wh_info.url or ("(polling mode)" if DEV_MODE else "(нет)")
            tg_status["pending_updates"] = wh_info.pending_update_count
            tg_status["last_error_message"] = wh_info.last_error_message
            if wh_info.last_error_date:
                tg_status["last_error_date"] = datetime.fromtimestamp(
                    wh_info.last_error_date, timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S UTC")

            if wh_info.last_error_message or (wh_info.pending_update_count and wh_info.pending_update_count > 25):
                tg_status["status"] = "degraded"
            else:
                tg_status["status"] = "ok"
        except Exception as e:
            tg_status["status"] = "error"
            tg_status["error"] = str(e)
            logger.warning(f"Dashboard Telegram check failed: {e}")
    else:
        tg_status["status"] = "warning"
        tg_status["error"] = "Экземпляр бота не передан"

    # 5. APScheduler
    sched_status = {
        "name": "APScheduler",
        "status": "unknown",
        "running": False,
        "jobs_count": 0,
        "jobs": []
    }
    if scheduler:
        try:
            sched_status["running"] = scheduler.running
            sched_status["status"] = "ok" if scheduler.running else "warning"
            jobs = scheduler.get_jobs()
            sched_status["jobs_count"] = len(jobs)
            for j in jobs:
                next_run = j.next_run_time.strftime("%d.%m %H:%M MSK") if j.next_run_time else "не запланировано"
                sched_status["jobs"].append({
                    "id": j.id,
                    "name": j.name or j.id,
                    "next_run": next_run
                })
        except Exception as e:
            sched_status["status"] = "error"
            sched_status["error"] = str(e)
    else:
        sched_status["status"] = "warning"
        sched_status["error"] = "Планировщик не подключен"

    # Расчет общего статуса
    critical = [db_status["status"], redis_status["status"], tg_status["status"]]
    if any(s == "error" for s in critical):
        overall = "error"
    elif any(s in ("degraded", "warning") for s in critical) or (sched_status["status"] != "ok"):
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "overall_status": overall,
        "timestamp": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "dashboard_url": get_dashboard_url(),
        "app": app_status,
        "database": db_status,
        "redis": redis_status,
        "telegram": tg_status,
        "scheduler": sched_status,
    }


def format_telegram_status(data: dict) -> str:
    """Форматирует результаты диагностики в сообщение Telegram с HTML-разметкой."""
    status_icons = {
        "ok": "🟢",
        "degraded": "🟡",
        "warning": "🟡",
        "error": "🔴",
        "unknown": "⚪"
    }

    overall_status = data.get("overall_status", "unknown")
    overall_icon = status_icons.get(overall_status, "⚪")
    app = data.get("app", {})
    db_info = data.get("database", {})
    r = data.get("redis", {})
    tg = data.get("telegram", {})
    sched = data.get("scheduler", {})

    status_titles = {
        "ok": "Все системы работают штатно",
        "degraded": "Работает с предупреждениями",
        "error": "Внимание! Есть ошибки в сервисах",
        "unknown": "Статус неизвестен"
    }
    overall_title = status_titles.get(overall_status, "Статус")

    lines = [
        f"🩺 <b>Диагностика XBalanseBot</b> {overall_icon}",
        f"<b>Статус:</b> {overall_title}\n",
        f"🤖 <b>Koyeb (Бот):</b> {status_icons.get(app.get('status'), '⚪')} Онлайн",
        f"   • Аптайм: <code>{app.get('uptime', '–')}</code>",
        f"   • Среда: <code>{app.get('environment', '–')}</code>\n",
        f"📱 <b>Telegram API:</b> {status_icons.get(tg.get('status'), '⚪')} {tg.get('latency_ms', '–')} ms",
        f"   • Бот: {tg.get('bot_username', '–')}",
        f"   • В очереди (pending): <b>{tg.get('pending_updates', 0)}</b>",
    ]

    if tg.get("last_error_message"):
        lines.append(f"   • ⚠️ Ошибка: <code>{tg.get('last_error_message')}</code>")

    lines.append("")
    lines.append(f"🗄️ <b>Supabase (PostgreSQL):</b> {status_icons.get(db_info.get('status'), '⚪')} {db_info.get('latency_ms', '–')} ms")
    if db_info.get("status") == "ok":
        lines.append(f"   • Пользователей: <code>{db_info.get('users_count', 0)}</code>")
        lines.append(f"   • Транзакций: <code>{db_info.get('transactions_count', 0)}</code>")
    elif db_info.get("error"):
        lines.append(f"   • ⚠️ Ошибка: <code>{db_info.get('error')}</code>")

    lines.append("")
    lines.append(f"⚡ <b>Upstash (Redis):</b> {status_icons.get(r.get('status'), '⚪')} {r.get('latency_ms', '–')} ms")
    if r.get("error"):
        lines.append(f"   • ⚠️ Ошибка: <code>{r.get('error')}</code>")

    lines.append("")
    lines.append(f"⏱️ <b>Планировщик:</b> {status_icons.get(sched.get('status'), '⚪')} {'Активен' if sched.get('running') else 'Остановлен'}")
    lines.append(f"   • Задач в очереди: <code>{sched.get('jobs_count', 0)}</code>")

    lines.append(f"\n🕒 <i>Проверено: {data.get('timestamp')}</i>")
    return "\n".join(lines)


def render_dashboard_html(data: dict) -> str:
    """Генерирует автономную современную HTML-страницу дашборда (темная тема)."""
    data_json = json.dumps(data)

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XBalanseBot — System Dashboard</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>⚖️</text></svg>">
    <style>
        :root {{
            --bg-body: #0a0d14;
            --bg-card: #121722;
            --bg-card-hover: #161d2b;
            --border-color: #232b3e;
            --border-subtle: #1a2130;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --green: #10b981;
            --green-glow: rgba(16, 185, 129, 0.2);
            --yellow: #f59e0b;
            --yellow-glow: rgba(245, 158, 11, 0.2);
            --red: #ef4444;
            --red-glow: rgba(239, 68, 68, 0.2);
            --blue: #3b82f6;
            --accent: #6366f1;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: var(--bg-body);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 24px 16px;
            display: flex;
            justify-content: center;
        }}

        .container {{
            width: 100%;
            max-width: 1080px;
        }}

        /* Header */
        header {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 24px;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .brand-icon {{
            font-size: 32px;
            background: #1e2638;
            width: 52px;
            height: 52px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 14px;
            border: 1px solid var(--border-color);
        }}

        .brand-text h1 {{
            font-size: 22px;
            font-weight: 700;
            letter-spacing: -0.02em;
        }}

        .brand-text p {{
            font-size: 13px;
            color: var(--text-secondary);
            margin-top: 2px;
        }}

        .controls {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }}

        .refresh-btn {{
            background: #1e2638;
            color: var(--text-primary);
            border: 1px solid var(--border-color);
            padding: 9px 18px;
            font-size: 14px;
            font-weight: 600;
            border-radius: 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
        }}

        .refresh-btn:hover {{
            background: #28334b;
            border-color: var(--blue);
        }}

        .refresh-btn.loading svg {{
            animation: spin 0.8s linear infinite;
        }}

        @keyframes spin {{
            100% {{ transform: rotate(360deg); }}
        }}

        .auto-refresh-toggle {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            color: var(--text-secondary);
            cursor: pointer;
            user-select: none;
        }}

        .auto-refresh-toggle input {{
            accent-color: var(--green);
            cursor: pointer;
        }}

        /* Banner */
        .status-banner {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            border-radius: 14px;
            margin-bottom: 24px;
            border: 1px solid;
            transition: all 0.3s ease;
        }}

        .status-banner.ok {{
            background: rgba(16, 185, 129, 0.08);
            border-color: rgba(16, 185, 129, 0.3);
            color: var(--green);
        }}

        .status-banner.degraded {{
            background: rgba(245, 158, 11, 0.08);
            border-color: rgba(245, 158, 11, 0.3);
            color: var(--yellow);
        }}

        .status-banner.error {{
            background: rgba(239, 68, 68, 0.08);
            border-color: rgba(239, 68, 68, 0.3);
            color: var(--red);
        }}

        .banner-left {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 16px;
            font-weight: 600;
        }}

        .banner-time {{
            font-size: 12px;
            color: var(--text-secondary);
            font-weight: normal;
        }}

        /* Pulse indicator */
        .pulse-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
            position: relative;
        }}

        .pulse-dot.ok {{
            background: var(--green);
            box-shadow: 0 0 10px var(--green);
        }}

        .pulse-dot.degraded {{
            background: var(--yellow);
            box-shadow: 0 0 10px var(--yellow);
        }}

        .pulse-dot.error {{
            background: var(--red);
            box-shadow: 0 0 10px var(--red);
        }}

        /* Grid */
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }}

        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
            transition: all 0.2s ease;
        }}

        .card:hover {{
            background: var(--bg-card-hover);
            border-color: #333f5c;
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .card-title {{
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 16px;
            font-weight: 700;
        }}

        .badge {{
            font-size: 12px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 20px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border: 1px solid;
        }}

        .badge.ok {{
            background: rgba(16, 185, 129, 0.12);
            border-color: rgba(16, 185, 129, 0.3);
            color: var(--green);
        }}

        .badge.degraded {{
            background: rgba(245, 158, 11, 0.12);
            border-color: rgba(245, 158, 11, 0.3);
            color: var(--yellow);
        }}

        .badge.error {{
            background: rgba(239, 68, 68, 0.12);
            border-color: rgba(239, 68, 68, 0.3);
            color: var(--red);
        }}

        .badge.neutral {{
            background: rgba(148, 163, 184, 0.12);
            border-color: rgba(148, 163, 184, 0.3);
            color: var(--text-secondary);
        }}

        .card-stats {{
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}

        .stat-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 13px;
        }}

        .stat-label {{
            color: var(--text-secondary);
        }}

        .stat-value {{
            font-weight: 600;
            color: var(--text-primary);
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }}

        .latency {{
            color: var(--green);
            font-weight: 600;
        }}

        .latency.slow {{
            color: var(--yellow);
        }}

        .latency.bad {{
            color: var(--red);
        }}

        .card-footer {{
            border-top: 1px solid var(--border-subtle);
            padding-top: 12px;
            margin-top: auto;
            font-size: 12px;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .card-link {{
            color: var(--blue);
            text-decoration: none;
            font-weight: 500;
        }}

        .card-link:hover {{
            text-decoration: underline;
        }}

        /* Tips section */
        .info-box {{
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 14px;
            padding: 18px 20px;
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.6;
        }}

        .info-box strong {{
            color: var(--text-primary);
        }}

        .info-box code {{
            background: #1f2937;
            color: #e2e8f0;
            padding: 2px 6px;
            border-radius: 6px;
            font-size: 12px;
        }}

        /* Responsive */
        @media (max-width: 640px) {{
            body {{
                padding: 16px 12px;
            }}
            header {{
                flex-direction: column;
                align-items: flex-start;
            }}
            .controls {{
                width: 100%;
                justify-content: space-between;
            }}
            .status-banner {{
                flex-direction: column;
                align-items: flex-start;
                gap: 8px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="brand">
                <div class="brand-icon">⚖️</div>
                <div class="brand-text">
                    <h1>XBalanseBot Status</h1>
                    <p>Панель мониторинга и доступности компонентов</p>
                </div>
            </div>
            <div class="controls">
                <label class="auto-refresh-toggle">
                    <input type="checkbox" id="autoRefreshCheck" checked>
                    Автообновление (30с)
                </label>
                <button class="refresh-btn" id="refreshBtn" onclick="triggerRefresh()">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                    </svg>
                    <span>Обновить</span>
                </button>
            </div>
        </header>

        <!-- Status Banner -->
        <div class="status-banner" id="banner">
            <div class="banner-left">
                <span class="pulse-dot" id="bannerDot"></span>
                <span id="bannerText">Проверка состояния...</span>
            </div>
            <div class="banner-time" id="lastUpdated">
                Обновлено: только что
            </div>
        </div>

        <!-- Grid of Services -->
        <div class="grid">
            <!-- 1. Koyeb App Core -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>🤖</span> Koyeb App Core
                    </div>
                    <span class="badge" id="appBadge">...</span>
                </div>
                <div class="card-stats">
                    <div class="stat-row">
                        <span class="stat-label">Аптайм (без сна):</span>
                        <span class="stat-value" id="appUptime">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Среда выполнения:</span>
                        <span class="stat-value" id="appEnv">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Python:</span>
                        <span class="stat-value" id="appPython">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Серверное время:</span>
                        <span class="stat-value" id="appTime">–</span>
                    </div>
                </div>
                <div class="card-footer">
                    <span>Контейнер Koyeb</span>
                    <span class="badge neutral" id="appStatusText">В сети</span>
                </div>
            </div>

            <!-- 2. Telegram Bot API & Webhook -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>📱</span> Telegram Bot API
                    </div>
                    <span class="badge" id="tgBadge">...</span>
                </div>
                <div class="card-stats">
                    <div class="stat-row">
                        <span class="stat-label">Пинг к API:</span>
                        <span class="stat-value latency" id="tgLatency">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Имя бота:</span>
                        <span class="stat-value" id="tgUsername">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Очередь (pending):</span>
                        <span class="stat-value" id="tgPending">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Ошибки вебхука:</span>
                        <span class="stat-value" id="tgError">Нет</span>
                    </div>
                </div>
                <div class="card-footer">
                    <span id="tgWebhookShort">Webhook</span>
                    <a href="https://t.me/XBalanseBot" target="_blank" class="card-link" id="tgBotLink">Открыть в Telegram ↗</a>
                </div>
            </div>

            <!-- 3. Supabase PostgreSQL -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>🗄️</span> Supabase Database
                    </div>
                    <span class="badge" id="dbBadge">...</span>
                </div>
                <div class="card-stats">
                    <div class="stat-row">
                        <span class="stat-label">Отклик (SELECT 1):</span>
                        <span class="stat-value latency" id="dbLatency">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Пользователей в базе:</span>
                        <span class="stat-value" id="dbUsers">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Всего транзакций:</span>
                        <span class="stat-value" id="dbTx">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Пул соединений:</span>
                        <span class="stat-value" id="dbPool">Активен</span>
                    </div>
                </div>
                <div class="card-footer">
                    <span>PostgreSQL 15</span>
                    <span class="badge neutral" id="dbStatusText">OK</span>
                </div>
            </div>

            <!-- 4. Upstash Redis -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>⚡</span> Upstash Redis
                    </div>
                    <span class="badge" id="redisBadge">...</span>
                </div>
                <div class="card-stats">
                    <div class="stat-row">
                        <span class="stat-label">Отклик (PING/PONG):</span>
                        <span class="stat-value latency" id="redisLatency">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Назначение:</span>
                        <span class="stat-value">FSM + Троттлинг</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Защита от флуда:</span>
                        <span class="stat-value" style="color: var(--green);">Включена</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Статус соединения:</span>
                        <span class="stat-value" id="redisConn">PONG</span>
                    </div>
                </div>
                <div class="card-footer">
                    <span>Serverless Redis</span>
                    <span class="badge neutral" id="redisStatusText">OK</span>
                </div>
            </div>

            <!-- 5. APScheduler Background Jobs -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>⏱️</span> Планировщик задач
                    </div>
                    <span class="badge" id="schedBadge">...</span>
                </div>
                <div class="card-stats">
                    <div class="stat-row">
                        <span class="stat-label">Состояние:</span>
                        <span class="stat-value" id="schedRunning">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Активных задач:</span>
                        <span class="stat-value" id="schedJobsCount">–</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Демередж (00:01 МСК):</span>
                        <span class="stat-value" style="color: var(--green);">Запланирован</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Часовой пояс:</span>
                        <span class="stat-value">Europe/Moscow</span>
                    </div>
                </div>
                <div class="card-footer">
                    <span>APScheduler 3.x</span>
                    <span class="badge neutral" id="schedStatusText">OK</span>
                </div>
            </div>

            <!-- 6. UptimeRobot & Wakeup -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>🔔</span> Wakeup & Keep-Alive
                    </div>
                    <span class="badge ok">Активно</span>
                </div>
                <div class="card-stats">
                    <div class="stat-row">
                        <span class="stat-label">Эндпоинт вейкапа:</span>
                        <span class="stat-value"><code>GET /</code></span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Ответ health-check:</span>
                        <span class="stat-value">"I'm awake!"</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Рекомендация:</span>
                        <span class="stat-value">Пинг раз в 5 мин</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Предотвращение сна:</span>
                        <span class="stat-value" style="color: var(--green);">Koyeb Scale-to-0</span>
                    </div>
                </div>
                <div class="card-footer">
                    <span>UptimeRobot / Cron</span>
                    <a href="https://uptimerobot.com" target="_blank" class="card-link">UptimeRobot ↗</a>
                </div>
            </div>
        </div>

        <!-- Info Footer -->
        <div class="info-box">
            💡 <strong>Подсказка:</strong> Для того чтобы Koyeb не усыплял бота на бесплатном тарифе, настройте в 
            <a href="https://uptimerobot.com" target="_blank" style="color: var(--blue);">UptimeRobot</a> монитор типа 
            <code>HTTP(s)</code> на адрес <code>https://xbalansebot-xbalance-1fe9cf64.koyeb.app/</code> с интервалом 5 минут.
            Также вы можете проверить статус прямо в Telegram, отправив команду <code>/status</code> боту.
        </div>
    </div>

    <!-- Client Logic -->
    <script>
        let initialData = {data_json};

        function updateUI(d) {{
            // 1. Overall Banner
            const banner = document.getElementById('banner');
            const bannerDot = document.getElementById('bannerDot');
            const bannerText = document.getElementById('bannerText');
            const lastUpdated = document.getElementById('lastUpdated');

            banner.className = 'status-banner ' + d.overall_status;
            bannerDot.className = 'pulse-dot ' + d.overall_status;
            if (d.overall_status === 'ok') {{
                bannerText.textContent = 'Все системы работают штатно';
            }} else if (d.overall_status === 'degraded') {{
                bannerText.textContent = 'Система работает с предупреждениями';
            }} else {{
                bannerText.textContent = 'Обнаружены сбои в компонентах системы';
            }}
            lastUpdated.textContent = 'Обновлено: ' + d.timestamp;

            // 2. App Core
            document.getElementById('appBadge').className = 'badge ' + d.app.status;
            document.getElementById('appBadge').textContent = d.app.status === 'ok' ? 'Online' : 'Warning';
            document.getElementById('appUptime').textContent = d.app.uptime;
            document.getElementById('appEnv').textContent = d.app.environment;
            document.getElementById('appPython').textContent = d.app.python_version;
            document.getElementById('appTime').textContent = d.app.server_time_utc;

            // 3. Telegram API
            const tg = d.telegram;
            document.getElementById('tgBadge').className = 'badge ' + tg.status;
            document.getElementById('tgBadge').textContent = tg.status.toUpperCase();
            document.getElementById('tgLatency').textContent = tg.latency_ms ? (tg.latency_ms + ' ms') : '–';
            document.getElementById('tgLatency').className = 'stat-value latency ' + (tg.latency_ms > 200 ? 'slow' : '');
            document.getElementById('tgUsername').textContent = tg.bot_username || '–';
            document.getElementById('tgPending').textContent = tg.pending_updates !== null ? tg.pending_updates : '–';
            if (tg.pending_updates > 0) {{
                document.getElementById('tgPending').style.color = 'var(--yellow)';
            }} else {{
                document.getElementById('tgPending').style.color = 'var(--green)';
            }}
            document.getElementById('tgError').textContent = tg.last_error_message || (tg.error ? tg.error : 'Нет ошибок');
            if (tg.last_error_message || tg.error) {{
                document.getElementById('tgError').style.color = 'var(--red)';
            }} else {{
                document.getElementById('tgError').style.color = 'var(--text-primary)';
            }}
            if (tg.bot_username && tg.bot_username.startsWith('@')) {{
                document.getElementById('tgBotLink').href = 'https://t.me/' + tg.bot_username.substring(1);
            }}

            // 4. Supabase DB
            const db = d.database;
            document.getElementById('dbBadge').className = 'badge ' + db.status;
            document.getElementById('dbBadge').textContent = db.status === 'ok' ? 'CONNECTED' : 'ERROR';
            document.getElementById('dbLatency').textContent = db.latency_ms ? (db.latency_ms + ' ms') : '–';
            document.getElementById('dbLatency').className = 'stat-value latency ' + (db.latency_ms > 150 ? 'slow' : '');
            document.getElementById('dbUsers').textContent = db.users_count !== null ? db.users_count : '–';
            document.getElementById('dbTx').textContent = db.transactions_count !== null ? db.transactions_count : '–';
            document.getElementById('dbStatusText').textContent = db.error ? 'Ошибка' : 'Подключено';
            if (db.error) {{
                document.getElementById('dbPool').textContent = db.error;
                document.getElementById('dbPool').style.color = 'var(--red)';
            }}

            // 5. Upstash Redis
            const r = d.redis;
            document.getElementById('redisBadge').className = 'badge ' + r.status;
            document.getElementById('redisBadge').textContent = r.status === 'ok' ? 'CONNECTED' : 'ERROR';
            document.getElementById('redisLatency').textContent = r.latency_ms ? (r.latency_ms + ' ms') : '–';
            document.getElementById('redisLatency').className = 'stat-value latency ' + (r.latency_ms > 100 ? 'slow' : '');
            document.getElementById('redisConn').textContent = r.error ? 'Ошибка' : 'PONG';
            if (r.error) {{
                document.getElementById('redisConn').style.color = 'var(--red)';
            }}

            // 6. APScheduler
            const sched = d.scheduler;
            document.getElementById('schedBadge').className = 'badge ' + sched.status;
            document.getElementById('schedBadge').textContent = sched.running ? 'RUNNING' : 'STOPPED';
            document.getElementById('schedRunning').textContent = sched.running ? 'Работает' : 'Остановлен';
            document.getElementById('schedRunning').style.color = sched.running ? 'var(--green)' : 'var(--red)';
            document.getElementById('schedJobsCount').textContent = sched.jobs_count;
        }}

        async function triggerRefresh() {{
            const btn = document.getElementById('refreshBtn');
            btn.classList.add('loading');
            try {{
                const res = await fetch('/api/status');
                if (res.ok) {{
                    const freshData = await res.json();
                    updateUI(freshData);
                }}
            }} catch (err) {{
                console.error('Failed to fetch status:', err);
            }} finally {{
                btn.classList.remove('loading');
            }}
        }}

        // Initial render
        updateUI(initialData);

        // Auto-refresh interval (30 seconds)
        setInterval(() => {{
            const autoCheck = document.getElementById('autoRefreshCheck');
            if (autoCheck && autoCheck.checked) {{
                triggerRefresh();
            }}
        }}, 30000);
    </script>
</body>
</html>"""


async def dashboard_page_handler(request: web.Request) -> web.Response:
    """Обработчик маршрута GET /status - отдает веб-интерфейс дашборда."""
    bot = request.app.get('bot')
    scheduler = request.app.get('scheduler')
    status_data = await get_system_status(bot=bot, scheduler=scheduler)
    html_content = render_dashboard_html(status_data)
    return web.Response(text=html_content, content_type='text/html', status=200)


async def api_status_handler(request: web.Request) -> web.Response:
    """Обработчик маршрута GET /api/status - отдает JSON со статусом системы."""
    bot = request.app.get('bot')
    scheduler = request.app.get('scheduler')
    status_data = await get_system_status(bot=bot, scheduler=scheduler)
    return web.json_response(status_data)
