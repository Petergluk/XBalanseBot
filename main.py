# XBalanseBot/main.py
# v1.8.9
# 2025-08-29 04:15:00
"""
Main entry point of XBalanseBot.

Версия 1.8.9:
- Добавлен импорт нового модуля `app.callbacks`.

Версия 1.8.8:
- ИСПРАВЛЕНИЕ: Исправлена ошибка `AttributeError` при завершении работы бота.
  Вызов `db.pool.is_closed()` заменен на свойство `db.pool.closed`.
- ИСПРАВЛЕНИЕ: Исправлена опечатка `db.pool.is_closed()` на `db.pool.closed` для
  корректного завершения работы.
"""

import asyncio
import logging
import os
import sys
import time
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# --- IMPORTANT: Make sure the project's root directory is on sys.path ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

load_dotenv()

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Windows compatibility for psycopg3 event loop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.config import BOT_TOKEN, SUPER_ADMIN_ID, DEV_MODE, LOG_LEVEL, REDIS_HOST, REDIS_URL, WEBHOOK_SECRET_TOKEN
from app.database import db
from app.handlers import common, user_commands, admin_commands, activity_handlers, event_handlers, tag_reward_handler, offer_handlers
from app.services import scheduler_jobs
from app.services.webhook_handler import run_webhook_server
from app import callbacks # Импорт нового модуля callbacks

# --- Logging setup ---
def cleanup_old_logs(log_dir: str = "data/logs", retention_days: int = 7) -> int:
    """Автоматически удаляет накопленные файлы логов старше retention_days дней при запуске."""
    if not os.path.exists(log_dir):
        return 0
    cutoff = time.time() - (retention_days * 86400)
    removed = 0
    try:
        for fname in os.listdir(log_dir):
            if fname.startswith("bot_") and fname.endswith(".log"):
                fpath = os.path.join(log_dir, fname)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    removed += 1
    except Exception:
        pass
    return removed

_removed_logs_count = cleanup_old_logs("data/logs", retention_days=7)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
from app.services.dashboard import install_dashboard_log_handler
install_dashboard_log_handler()
logger = logging.getLogger(__name__)
if _removed_logs_count > 0:
    logger.info(f"Cleaned up {_removed_logs_count} old log file(s) (>7 days) from data/logs.")


async def logging_middleware(handler, event, data: dict):
    """Outer middleware for unified update logging (redacted for privacy)."""
    user = data.get('event_from_user')
    if user:
        if isinstance(event, Message):
            is_command = event.text and event.text.startswith('/')
            msg_type = f"command '{event.text.split()[0]}'" if is_command else "message"
            logger.info(f"User {user.id} sent {msg_type}")
        elif isinstance(event, CallbackQuery):
            logger.info(f"User {user.id} sent callback: '{event.data}'")
        elif isinstance(event, ChatMemberUpdated):
            logger.info(
                f"User {user.id} caused chat member update: {event.new_chat_member.status}"
            )
    return await handler(event, data)


def make_throttling_middleware(storage):
    async def throttling_middleware(handler, event, data: dict):
        user = data.get('event_from_user')
        if not user:
            return await handler(event, data)

        redis = storage.redis
        user_id = user.id

        is_command = False
        if isinstance(event, Message):
            is_command = event.text and event.text.startswith('/')

        if is_command or isinstance(event, CallbackQuery):
            key = f"throttle:{user_id}"
            is_allowed = await redis.set(key, 1, px=500, nx=True)
            if not is_allowed:
                if isinstance(event, Message):
                    await event.reply("⚠️ Слишком быстро! Пожалуйста, подождите немного.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Слишком быстро! Подождите...", show_alert=True)
                return

        return await handler(event, data)
    return throttling_middleware


async def private_chat_restriction_middleware(handler, event, data: dict):
    """Prevents private-only commands and navigation callbacks from running in groups."""
    is_message = isinstance(event, Message) or (hasattr(event, "text") and isinstance(event.text, str))
    is_callback = isinstance(event, CallbackQuery) or (hasattr(event, "data") and isinstance(event.data, str))

    if is_message:
        if event.chat and event.chat.type in ('group', 'supergroup'):
            if event.text and event.text.startswith('/'):
                parts = event.text.split()
                command = parts[0].lower().split('@')[0]

                private_commands = {
                    "/menu", "/balance", "/баланс", "/history", "/settings",
                    "/users", "/check", "/rem", "/make_admin", "/remove_admin",
                    "/list_tag_rules", "/add_tag_rule", "/create_act", "/create_event",
                    "/gide", "/гид", "/test", "/activity", "/activities", "/afisha", "/event", "/start",
                    "/join", "/link", "/offer", "/create_offer", "/reset", "/rebalance",
                    "/pay_from_fund", "/fund", "/fund_pay", "/cancel_broadcast", "/status", "/cancel"
                }

                if command in private_commands:
                    bot_info = await event.bot.get_me()
                    await event.reply(
                        f"❌ Эта команда доступна только в личных сообщениях со мной: @{bot_info.username}"
                    )
                    return

                if command in ("/send", "/add") and len(parts) < 3:
                    await event.reply(
                        "❌ В группе поддерживается только быстрый перевод:\n"
                        "<code>/send @username сумма [комментарий]</code>",
                        parse_mode="HTML"
                    )
                    return

        elif event.chat and event.chat.type == 'private':
            from_user = getattr(event, 'from_user', None)
            text_str = (event.text or "").strip()
            cmd_token = text_str.split()[0].lower().split('@')[0] if text_str.startswith('/') else ""
            if (
                from_user
                and not getattr(from_user, 'is_bot', False)
                and from_user.id != SUPER_ADMIN_ID
                and cmd_token != "/start"
                and getattr(db, 'pool', None) is not None
            ):
                user_row = await db.get_user(telegram_id=from_user.id)
                if not user_row:
                    from app.utils import check_is_group_member
                    if not await check_is_group_member(event.bot, from_user.id):
                        await common.send_onboarding_prompt(event)
                        return

    elif is_callback:
        if event.message and event.message.chat and event.message.chat.type in ('group', 'supergroup'):
            data_str = event.data or ""
            blocked_prefixes = ("gen:", "act:", "act_edit:", "evt:", "evt_edit:", "evt_create:", "set:", "tx:", "del:")
            if data_str.startswith(blocked_prefixes):
                await event.answer(
                    "❌ Это действие доступно только в личных сообщениях с ботом.",
                    show_alert=True
                )
                return
        elif event.message and event.message.chat and event.message.chat.type == 'private':
            from_user = getattr(event, 'from_user', None)
            data_str = event.data or ""
            if (
                from_user
                and not getattr(from_user, 'is_bot', False)
                and from_user.id != SUPER_ADMIN_ID
                and "onboarding_agree" not in data_str
                and getattr(db, 'pool', None) is not None
            ):
                user_row = await db.get_user(telegram_id=from_user.id)
                if not user_row:
                    from app.utils import check_is_group_member
                    if not await check_is_group_member(event.bot, from_user.id):
                        await common.send_onboarding_prompt(event)
                        return

    return await handler(event, data)


async def setup_super_admin():
    """Ensure the super admin exists and has is_admin flag."""
    logger.info("Checking for super admin setup...")
    if not SUPER_ADMIN_ID:
        return
    user = await db.get_user(telegram_id=SUPER_ADMIN_ID)
    if not user:
        await db.create_user(telegram_id=SUPER_ADMIN_ID, username=None, is_admin=True)
        logger.info(f"Super admin with ID {SUPER_ADMIN_ID} created.")
    elif not user['is_admin']:
        await db.set_admin_status(telegram_id=SUPER_ADMIN_ID, is_admin=True)
        logger.info(f"Existing user {SUPER_ADMIN_ID} has been promoted to super admin.")


async def setup_bot_commands(bot: Bot):
    """Регистрирует команды бота отдельно для личных чатов и для групп."""
    from aiogram.types import (
        BotCommand,
        BotCommandScopeDefault,
        BotCommandScopeAllPrivateChats,
        BotCommandScopeAllGroupChats,
        BotCommandScopeChat,
    )

    # Команды для личных сообщений с ботом (минималистичное меню без терминальной перегрузки)
    user_commands = [
        BotCommand(command="menu", description="🤖 Главное меню"),
    ]
    # Команды, которые реально работают внутри группового чата
    group_commands = [
        BotCommand(command="donate", description="💝 Поблагодарить автора поста орфами"),
        BotCommand(command="send", description="💸 Быстрый перевод (@user сумма)"),
        BotCommand(command="gdp", description="📊 Экономика сообщества"),
        BotCommand(command="help", description="📖 Справка по командам в группе"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    try:
        await bot.set_my_commands(user_commands, scope=BotCommandScopeAllPrivateChats())
        await bot.set_my_commands(group_commands, scope=BotCommandScopeAllGroupChats())
    except Exception as e:
        logger.warning(f"Could not set scoped commands: {e}")
    logger.info(f"Bot commands set: {len(user_commands)} private commands, {len(group_commands)} group commands.")

    # Расширенные команды для всех администраторов и супер-админа
    admin_commands = [
        BotCommand(command="menu", description="🤖 Главное меню"),
        BotCommand(command="settings", description="⚙️ Настройки бота"),
        BotCommand(command="status", description="🩺 Статус системы"),
        BotCommand(command="gide", description="🔐 Гид администратора"),
        BotCommand(command="help", description="📖 Справка"),
    ]
    admin_ids = set()
    if SUPER_ADMIN_ID:
        admin_ids.add(int(SUPER_ADMIN_ID))
    try:
        all_users = await db.get_all_users()
        for u in all_users:
            if u.get("is_admin") and u.get("telegram_id"):
                admin_ids.add(int(u["telegram_id"]))
    except Exception:
        pass
    for adm_id in admin_ids:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=adm_id))
        except Exception as e:
            logger.warning(f"Could not set admin commands for {adm_id}: {e}")


async def setup_scheduler(bot: Bot, scheduler: AsyncIOScheduler):
    """Configure the background scheduler."""
    scheduler.add_job(scheduler_jobs.process_demurrage, CronTrigger(hour=0, minute=1), args=(bot,))
    scheduler.add_job(
        scheduler_jobs.process_scheduled_broadcasts,
        'interval',
        minutes=1,
        args=(bot,),
        id='process_scheduled_broadcasts',
        replace_existing=True,
    )

    all_events = await db.get_all_events()
    for event in all_events:
        await scheduler_jobs.schedule_event_jobs(event, bot, scheduler)

    scheduler.start()
    logger.info(f"Scheduler started with {len(scheduler.get_jobs())} jobs.")


async def main():
    """Bot bootstrap."""
    logger.info("Starting bot initialization...")

    if not BOT_TOKEN:
        logger.critical("FATAL: BOT_TOKEN is not found! Bot cannot start.")
        return

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

    redis_url = REDIS_URL if REDIS_URL else f"redis://{REDIS_HOST}:6379/0"
    storage = RedisStorage.from_url(redis_url, key_builder=DefaultKeyBuilder(with_destiny=True))
    dp = Dispatcher(storage=storage, scheduler=scheduler)

    throttling_middleware = make_throttling_middleware(storage)
    dp.message.outer_middleware(throttling_middleware)
    dp.callback_query.outer_middleware(throttling_middleware)

    dp.message.outer_middleware(logging_middleware)
    dp.callback_query.outer_middleware(logging_middleware)
    dp.chat_member.outer_middleware(logging_middleware)

    dp.message.outer_middleware(private_chat_restriction_middleware)
    dp.callback_query.outer_middleware(private_chat_restriction_middleware)

    dp.include_router(common.router)
    dp.include_router(tag_reward_handler.router)  # Must be before admin router (no middleware)
    dp.include_router(admin_commands.router)
    dp.include_router(user_commands.router)
    dp.include_router(offer_handlers.router)
    dp.include_router(activity_handlers.router)
    dp.include_router(event_handlers.router)

    try:
        await db.initialize()
        await setup_super_admin()
        await setup_bot_commands(bot)
        await setup_scheduler(bot, scheduler)
        # В продакшене не сбрасываем апдейты пользователей при штатном перезапуске:
        await bot.delete_webhook(drop_pending_updates=DEV_MODE)

        # Resolve all update types that the bot handles (includes chat_member)
        allowed_updates = dp.resolve_used_update_types()
        logger.info(f"Resolved allowed updates: {allowed_updates}")

        if DEV_MODE:
            logger.info("Bot is running in DEVELOPMENT mode (polling).")
            await dp.start_polling(bot, allowed_updates=allowed_updates)
        else:
            WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
            if not WEBHOOK_HOST:
                logger.critical("FATAL: WEBHOOK_HOST is not set for production mode!")
                return

            logger.info("Bot is running in PRODUCTION mode (webhook).")
            webhook_url = f"https://{WEBHOOK_HOST}/webhook/telegram"
            if WEBHOOK_SECRET_TOKEN:
                await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET_TOKEN, allowed_updates=allowed_updates)
            else:
                await bot.set_webhook(webhook_url, allowed_updates=allowed_updates)
            logger.info(f"Webhook set to: {webhook_url}")
            await run_webhook_server(bot, dp, scheduler=scheduler)

    finally:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler stopped.")

        if db.pool and not db.pool.closed:
            await db.close()

        await bot.session.close()
        await storage.close()
        logger.info("Bot session, storage, and database pool closed.")




if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot application stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error during bot execution: {e}", exc_info=True)
