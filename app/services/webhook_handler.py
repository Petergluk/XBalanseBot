# XBalanseBot/app/services/webhook_handler.py
# v1.5.7 - 2025-08-21 (Added health check endpoint)
# 2025-08-21 21:30:00
import logging
import asyncio
from decimal import Decimal
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from app.database import db
from app.utils import format_amount, ensure_user_exists, is_user_in_group
from app.config import WEB_SERVER_HOST, WEBHOOK_PORT, TRIBUTE_WEBHOOK_SECRET

logger = logging.getLogger(__name__)


async def health_check(request: web.Request):
    """
    Простой обработчик для корневого URL /.
    Используется внешними сервисами (UptimeRobot) для проверки работоспособности
    и предотвращения "засыпания" сервиса.
    """
    logger.info("Health check endpoint '/' was requested.")
    return web.Response(status=200, text="I'm awake!")


async def handle_tribute_webhook(request: web.Request):
    """Обработка вебхука от Tribute для пополнения баланса."""
    bot = request.app['bot']
    
    if request.headers.get('X-Tribute-Secret') != TRIBUTE_WEBHOOK_SECRET:
        logger.warning("Received webhook with invalid secret.")
        return web.Response(status=403)

    try:
        data = await request.json()
        logger.info(f"Received Tribute webhook: {data}")

        payer_info = data.get('payer', {})
        telegram_id = payer_info.get('telegram_id')
        username = payer_info.get('username')
        amount_rub = Decimal(str(data.get('amount')))
        
        if not telegram_id or not amount_rub:
            logger.error(f"Invalid data in webhook: {data}")
            return web.Response(status=400)

        if not await is_user_in_group(bot, telegram_id):
            logger.warning(f"User {telegram_id} from webhook is not in the main group.")
            return web.Response(status=200, text="OK (user not in group)")

        await ensure_user_exists(telegram_id, username, is_bot=False)
        
        exchange_rate_str = await db.get_setting('exchange_rate', '1.0')
        exchange_rate = Decimal(exchange_rate_str)
        top_up_amount = (amount_rub * exchange_rate).quantize(Decimal('0.0001'))
        user_id = None

        async with db.pool.connection() as conn:
            async with conn.transaction():
                user_row = await conn.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,)).fetchone()
                if not user_row:
                    logger.error(f"User {telegram_id} not found in DB after ensure_user_exists call.")
                    raise Exception("User not found during webhook processing")

                user_id = user_row[0]
                await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (top_up_amount, user_id))
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (0, %s, %s, 'top_up', %s)",
                    (user_id, top_up_amount, f"Пополнение через Tribute на {amount_rub} RUB")
                )
        
        if user_id:
            await db.handle_debt_repayment(user_id)

        try:
            await bot.send_message(
                telegram_id,
                f"✅ Ваш баланс пополнен на <b>{format_amount(top_up_amount)} Ӫ</b> "
                f"после оплаты {amount_rub} RUB через Tribute."
            )
        except Exception as e:
            logger.error(f"Failed to notify user {telegram_id} about top-up: {e}")

        return web.Response(status=200, text="OK")

    except Exception as e:
        logger.exception(f"Error processing Tribute webhook: {e}")
        return web.Response(status=500)

async def run_webhook_server(bot: Bot, dp: Dispatcher):
    """Запускает веб-сервер для приема вебхуков от Telegram и Tribute."""
    app = web.Application()
    app['bot'] = bot
    
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path="/webhook/telegram")
    
    app.router.add_post('/webhook/tribute', handle_tribute_webhook)
    
    # Регистрация обработчика для корневого URL
    app.router.add_get('/', health_check)

    setup_application(app, dp, bot=bot)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEBHOOK_PORT)
    
    logger.info(f"Starting aiohttp server on {WEB_SERVER_HOST}:{WEBHOOK_PORT}...")
    await site.start()
    
    await asyncio.Event().wait()