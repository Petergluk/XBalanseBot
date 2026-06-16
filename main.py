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

from app.config import BOT_TOKEN, SUPER_ADMIN_ID, DEV_MODE, REDIS_HOST, REDIS_URL, WEBHOOK_SECRET_TOKEN
from app.database import db
from app.handlers import common, user_commands, admin_commands, activity_handlers, event_handlers, tag_reward_handler, offer_handlers
from app.services import scheduler_jobs
from app.services.webhook_handler import run_webhook_server
from app import callbacks # Импорт нового модуля callbacks

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
                    "/users", "/check", "/add", "/rem", "/make_admin", "/remove_admin",
                    "/list_tag_rules", "/add_tag_rule", "/create_act", "/create_event",
                    "/gide", "/гид", "/test", "/activity", "/activities", "/afisha", "/event", "/start"
                }
                
                if command in private_commands:
                    bot_info = await event.bot.get_me()
                    await event.reply(
                        f"❌ Эта команда доступна только в личных сообщениях со мной: @{bot_info.username}"
                    )
                    return
                
                if command == "/send" and len(parts) < 3:
                    await event.reply(
                        "❌ В группе поддерживается только быстрый перевод:\n"
                        "<code>/send @username сумма [комментарий]</code>",
                        parse_mode="HTML"
                    )
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
    """Регистрирует команды бота в меню Telegram."""
    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

    # Команды для всех пользователей
    user_commands = [
        BotCommand(command="menu", description="🤖 Главное меню"),
        BotCommand(command="start", description="👋 Начать работу с ботом"),
        BotCommand(command="help", description="📖 Справка"),
        BotCommand(command="history", description="📜 История транзакций"),
        BotCommand(command="gdp", description="📊 Экономика сообщества"),
        BotCommand(command="cancel", description="❌ Отменить текущее действие"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
    logger.info(f"Bot commands set: {len(user_commands)} user commands.")

    # Расширенные команды для супер-админа
    if SUPER_ADMIN_ID:
        admin_commands = user_commands + [
            BotCommand(command="settings", description="⚙️ Настройки бота"),
            BotCommand(command="users", description="👥 Список пользователей"),
            BotCommand(command="gide", description="📘 Гид по валюте"),
            BotCommand(command="test", description="🧪 Тестовые команды"),
        ]
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=SUPER_ADMIN_ID))
            logger.info(f"Admin commands set for super admin {SUPER_ADMIN_ID}: {len(admin_commands)} commands.")
        except Exception as e:
            logger.warning(f"Could not set admin commands for {SUPER_ADMIN_ID}: {e}")


async def setup_scheduler(bot: Bot, scheduler: AsyncIOScheduler):
    """Configure the background scheduler."""
    scheduler.add_job(scheduler_jobs.process_demurrage, CronTrigger(hour=0, minute=1), args=(bot,))

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
        await bot.delete_webhook(drop_pending_updates=True)

        if DEV_MODE:
            logger.info("Bot is running in DEVELOPMENT mode (polling).")
            await dp.start_polling(bot)
        else:
            WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
            if not WEBHOOK_HOST:
                logger.critical("FATAL: WEBHOOK_HOST is not set for production mode!")
                return

            logger.info("Bot is running in PRODUCTION mode (webhook).")
            webhook_url = f"https://{WEBHOOK_HOST}/webhook/telegram"
            if WEBHOOK_SECRET_TOKEN:
                await bot.set_webhook(webhook_url, secret_token=WEBHOOK_SECRET_TOKEN)
            else:
                await bot.set_webhook(webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
            await run_webhook_server(bot, dp)

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
