# XBalanseBot/main.py
# v1.8.1 - 2025-08-20 (Render.com import fix for config)
# 2025-08-20 12:50:00
"""
Main entry point of XBalanseBot.

Functions and responsibilities:
- Loads environment variables for local development.
- Ensures stable module import paths in heterogeneous runtimes (Render.com).
- Initializes logging, database connection pool, routers, and scheduler.
- Runs the bot in polling mode (DEV) or webhook mode (PROD).

External dependencies:
- aiogram (Telegram Bot framework)
- apscheduler (task scheduler)
- python-dotenv (environment variables)
- aiohttp (used by webhook server)
- psycopg/psycopg_pool (via app.database)
- Local modules: config, app.database, app.handlers.*, app.services.*

Recent changes (changelog):
- v1.8.1: FIX — Added explicit sys.path injection for the current directory before importing `config`
           to prevent ModuleNotFoundError on Render.com.
- v1.8.0: FEAT — Production-ready webhook server launch for Render.com; improved logging and lifecycle.
"""

import asyncio
import logging
import os
import sys
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# --- IMPORTANT: Make sure the directory of this file is on sys.path ---
# Some hosting environments (e.g., Render.com) may execute the script with a
# different working directory; explicitly ensuring the script directory is in

# Load .env early for local development (in production, env vars are provided by the platform)
load_dotenv()

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Windows compatibility for psycopg3 event loop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Local configuration and modules
from app.config import BOT_TOKEN, SUPER_ADMIN_ID, DEV_MODE, WEBHOOK_HOST
from app.database import db
from app.handlers import common, user_commands, admin_commands, activity_handlers, event_handlers
from app.services import scheduler_jobs
from app.services.webhook_handler import run_webhook_server

# --- Logging setup ---
log_dir = "data/logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filename = os.path.join(log_dir, f"bot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def logging_middleware(handler, event, data: dict):
    """
    Outer middleware for unified update logging.

    Args:
        handler: Next handler in the aiogram chain.
        event: Incoming event instance (Message/CallbackQuery/ChatMemberUpdated).
        data (dict): Aiogram context data.

    Returns:
        Any: Result from the next handler.
    """
    user = data.get('event_from_user')
    if user:
        if isinstance(event, Message):
            logger.info(f"User {user.id} (@{user.username}) sent message: '{event.text}'")
        elif isinstance(event, CallbackQuery):
            logger.info(f"User {user.id} (@{user.username}) sent callback: '{event.data}'")
        elif isinstance(event, ChatMemberUpdated):
            logger.info(
                f"User {user.id} (@{user.username}) caused chat member update: {event.new_chat_member.status}"
            )
    return await handler(event, data)


async def setup_super_admin():
    """
    Ensure the super admin exists and has is_admin flag.
    Uses SUPER_ADMIN_ID from config.
    """
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


async def setup_scheduler(bot: Bot, scheduler: AsyncIOScheduler):
    """
    Configure the background scheduler:
    - Daily demurrage
    - Jobs for all active events

    Args:
        bot (Bot): Aiogram bot instance (required by jobs).
        scheduler (AsyncIOScheduler): The asyncio scheduler.
    """
    # Schedule daily demurrage at 00:01 MSK
    scheduler.add_job(scheduler_jobs.process_demurrage, CronTrigger(hour=0, minute=1), args=(bot,))

    # Schedule event jobs (payments + reminders)
    all_events = await db.get_all_events()
    for event in all_events:
        await scheduler_jobs.schedule_event_jobs(event, bot, scheduler)

    scheduler.start()
    logger.info(f"Scheduler started with {len(scheduler.get_jobs())} jobs.")


async def main():
    """
    Bot bootstrap:
    - Validate configuration
    - Initialize DB pool
    - Ensure super admin
    - Start scheduler
    - Register routers
    - Start bot in polling (DEV) or webhook (PROD) mode
    """
    logger.info("Starting bot initialization...")

    # Validate token presence
    if not BOT_TOKEN:
        logger.critical("FATAL: BOT_TOKEN is not found! Bot cannot start.")
        return

    # Create scheduler with MSK timezone
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

    # Initialize bot instance
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    # Attach scheduler to bot for convenient access in handlers/services
    bot.scheduler = scheduler

    # Dispatcher with in-memory FSM storage
    dp = Dispatcher(storage=MemoryStorage())

    # Global logging middleware
    dp.message.outer_middleware(logging_middleware)
    dp.callback_query.outer_middleware(logging_middleware)
    dp.chat_member.outer_middleware(logging_middleware)

    # Register routers
    dp.include_router(common.router)
    dp.include_router(admin_commands.router)
    dp.include_router(user_commands.router)
    dp.include_router(activity_handlers.router)
    dp.include_router(event_handlers.router)

    try:
        # Initialize database connection pool and schema
        await db.initialize()

        # Ensure super admin exists
        await setup_super_admin()

        # Prepare scheduler jobs
        await setup_scheduler(bot, scheduler)

        # Remove previous webhook (prevents conflicts when switching modes)
        await bot.delete_webhook(drop_pending_updates=True)

        if DEV_MODE:
            # Development: long polling
            logger.info("Bot is running in DEVELOPMENT mode (polling).")
            await dp.start_polling(bot)
        else:
            # Production: webhook mode (Render.com)
            if not WEBHOOK_HOST:
                logger.critical("FATAL: WEBHOOK_HOST is not set for production mode!")
                return

            logger.info("Bot is running in PRODUCTION mode (webhook).")
            webhook_url = f"https://{WEBHOOK_HOST}/webhook/telegram"
            await bot.set_webhook(webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")

            # Launch aiohttp server to accept Telegram and Tribute webhooks
            await run_webhook_server(bot, dp)

    finally:
        # Graceful shutdown
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler stopped.")

        await db.close()
        await bot.session.close()
        logger.info("Bot session and database pool closed.")

        # Stop docker-compose only in development mode
        if DEV_MODE:
            logger.info("Stopping docker-compose services...")
            try:
                subprocess.run(["docker-compose", "down"], check=True, capture_output=True)
                logger.info("Docker services stopped successfully.")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.error(f"Failed to run 'docker-compose down': {e}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot application stopped by user.")
    except Exception as e:
        logger.error(f"Fatal error during bot execution: {e}", exc_info=True)