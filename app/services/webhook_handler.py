# XBalanseBot/app/services/webhook_handler.py
# v1.5.7 - 2025-08-21 (Added health check endpoint)
# 2025-08-21 21:30:00
import logging
import asyncio
import hashlib
import json
from decimal import Decimal, InvalidOperation
from secrets import compare_digest
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from app.database import db
from app.utils import format_amount, ensure_user_exists
from app.config import TRIBUTE_WEBHOOK_SECRET, WEBHOOK_SECRET_TOKEN, WEB_SERVER_HOST, WEBHOOK_PORT, REDIS_HOST, REDIS_URL
import redis.asyncio as redis

_redis_pool = None

async def get_redis():
    global _redis_pool
    if not _redis_pool:
        redis_url = REDIS_URL if REDIS_URL else f"redis://{REDIS_HOST}:6379/0"
        _redis_pool = redis.from_url(redis_url)
    return _redis_pool

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

    if not TRIBUTE_WEBHOOK_SECRET:
        logger.error("TRIBUTE_WEBHOOK_SECRET is not configured. Rejecting Tribute webhook.")
        return web.Response(status=503, text="Webhook secret is not configured")

    received_secret = request.headers.get('X-Tribute-Secret')
    if not received_secret or not compare_digest(received_secret, TRIBUTE_WEBHOOK_SECRET):
        logger.warning("Received webhook with invalid secret.")
        return web.Response(status=403)

    try:
        data = await request.json()
        logger.info(f"Received Tribute webhook: {data}")

        payer_info = data.get('payer') or {}
        telegram_id_raw = payer_info.get('telegram_id')
        username = payer_info.get('username')

        try:
            telegram_id = int(telegram_id_raw)
            amount_rub = Decimal(str(data.get('amount')))
        except (TypeError, ValueError, InvalidOperation):
            logger.error(f"Invalid data in webhook: {data}")
            return web.Response(status=400)

        if telegram_id <= 0 or amount_rub <= 0:
            logger.error(f"Invalid telegram_id/amount in webhook: {data}")
            return web.Response(status=400)

        payment_ref_raw = (
            data.get("payment_id")
            or data.get("id")
            or data.get("transaction_id")
            or data.get("invoice_id")
        )
        if payment_ref_raw:
            payment_ref = f"tribute:{payment_ref_raw}"
        else:
            # Fallback fingerprint to deduplicate provider retries even without explicit payment id.
            payload_canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            payment_ref = f"tribute:hash:{hashlib.sha256(payload_canonical.encode('utf-8')).hexdigest()}"
            logger.warning("Tribute webhook has no payment id. Using payload hash as idempotency key.")

        r = await get_redis()
        # Блокировка дублей на уровне Redis (срок жизни ключа 1 час)
        acquired = await r.set(payment_ref, "processing", ex=3600, nx=True)
        if not acquired:
            logger.info(f"Duplicate Tribute webhook (caught by Redis) for {payment_ref}.")
            return web.Response(status=200, text="OK (duplicate)")

        await ensure_user_exists(telegram_id, username, is_bot=False)

        exchange_rate_str = await db.get_setting('exchange_rate', '1.0')
        try:
            exchange_rate = Decimal(exchange_rate_str)
        except (InvalidOperation, TypeError):
            logger.error(f"Invalid exchange_rate setting: {exchange_rate_str}")
            return web.Response(status=500)

        if exchange_rate <= 0:
            logger.error(f"Non-positive exchange_rate setting: {exchange_rate_str}")
            return web.Response(status=500)

        top_up_amount = (amount_rub * exchange_rate).quantize(Decimal('0.0001'))
        user_id = None
        already_processed = False

        async with db.pool.connection() as conn:
            async with conn.transaction():
                result_cursor = await conn.execute(
                    "SELECT id FROM users WHERE telegram_id = %s FOR UPDATE",
                    (telegram_id,)
                )
                user_row = await result_cursor.fetchone()
                if not user_row:
                    logger.error(f"User {telegram_id} not found in DB after ensure_user_exists call.")
                    raise Exception("User not found during webhook processing")

                user_id = user_row[0]
                tx_cursor = await conn.execute(
                    """
                    INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment, external_id)
                    VALUES (0, %s, %s, 'top_up', %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING id
                    """,
                    (
                        user_id,
                        top_up_amount,
                        f"Пополнение через Tribute на {amount_rub} RUB",
                        payment_ref,
                    ),
                )
                tx_row = await tx_cursor.fetchone()
                if not tx_row:
                    already_processed = True
                else:
                    await conn.execute(
                        "UPDATE users SET balance = balance + %s, transaction_count = transaction_count + 1 WHERE id = %s",
                        (top_up_amount, user_id),
                    )

        if already_processed:
            logger.info(f"Duplicate Tribute webhook ignored for {payment_ref}.")
            return web.Response(status=200, text="OK (duplicate)")

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
    
    if WEBHOOK_SECRET_TOKEN:
        handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET_TOKEN)
    else:
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
