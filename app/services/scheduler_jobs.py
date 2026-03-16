# XBalanseBot/app/services/scheduler_jobs.py
# v1.6.0
# 2025-08-26 20:15:00
"""
Модуль для управления фоновыми задачами через APScheduler.

Версия 1.6.0:
- ИЗМЕНЕНИЕ: Полностью переписана логика определения участников в `handle_payment_for_event` и `handle_reminders_for_event`.
- Теперь используется гибридная модель: базовые подписчики + разовые регистрации/отмены из таблицы `event_registration_overrides`.
"""
import logging
from datetime import datetime, date
from decimal import Decimal
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError
from psycopg.rows import dict_row
from zoneinfo import ZoneInfo

from app.database import db
from app.utils import format_amount, get_next_run_time
from app.config import CURRENCY_SYMBOL
from app.lexicon import LEXICON_RU

logger = logging.getLogger(__name__)
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
MSK_LABEL = "MSK"

async def schedule_event_jobs(event: dict, bot: Bot, scheduler: AsyncIOScheduler):
    """Планирует или перепланирует задачи для одного события (оплата и напоминание)."""
    event_id = event['id']
    remove_event_jobs(event_id, scheduler)

    next_run = get_next_run_time(
        event_type=event['event_type'],
        event_date=event.get('event_date'),
        weekday_val=event.get('weekday'),
        event_time=event.get('event_time'),
        last_run=event.get('last_run'),
        end_date=event.get('end_date')
    )

    if not next_run or next_run < datetime.now(next_run.tzinfo):
        logger.info(f"Event {event_id} has no valid next run time in the future. Not scheduling.")
        return

    scheduler.add_job(
        run_event_payment, 'date', run_date=next_run,
        args=[event_id, bot, scheduler, next_run], id=f"event_payment_{event_id}"
    )
    logger.info(f"Scheduled payment for event {event_id} at {next_run}")

    if event['reminder_time'] and event['reminder_time'] > 0:
        from datetime import timedelta
        reminder_datetime = next_run - timedelta(minutes=event['reminder_time'])
        if reminder_datetime > datetime.now(reminder_datetime.tzinfo):
            scheduler.add_job(
                run_event_reminder, 'date', run_date=reminder_datetime,
                args=[event_id, bot, next_run], id=f"event_reminder_{event_id}"
            )
            logger.info(f"Scheduled reminder for event {event_id} at {reminder_datetime}")

def remove_event_jobs(event_id: int, scheduler: AsyncIOScheduler):
    """Удаляет задачи для события из планировщика."""
    for job_id in [f"event_payment_{event_id}", f"event_reminder_{event_id}"]:
        try:
            scheduler.remove_job(job_id)
            logger.info(f"Removed job {job_id} from scheduler.")
        except JobLookupError:
            pass

async def _get_final_participants(event: dict, event_date: date) -> list:
    """Определяет финальный список участников события на конкретную дату."""
    activity_id = event['activity_id']
    event_id = event['id']

    # 1. Базовый список подписчиков
    if activity_id == 1:  # Общие события
        base_subscribers = await db.get_all_users()
    else:
        base_subscribers = await db.get_activity_subscribers(activity_id)
    
    base_subscriber_ids = {user['id'] for user in base_subscribers}
    
    # 2. Получаем исключения на дату
    overrides = await db.get_event_overrides_for_date(event_id, event_date)
    
    manually_registered_ids = {ov['user_id'] for ov in overrides if ov['status'] == 'registered'}
    manually_unregistered_ids = {ov['user_id'] for ov in overrides if ov['status'] == 'unregistered'}
    
    # 3. Формируем финальный список ID
    final_participant_ids = (base_subscriber_ids - manually_unregistered_ids) | manually_registered_ids
    
    if not final_participant_ids:
        return []

    return await db.get_users_by_ids(list(final_participant_ids))


async def run_event_payment(event_id: int, bot: Bot, scheduler: AsyncIOScheduler, scheduled_start_dt: datetime):
    """Выполняется по расписанию. Обрабатывает списания и перепланирует событие."""
    event = await db.get_event(event_id)
    if not event or not event['is_active']:
        logger.warning(f"Job run_event_payment for event {event_id} skipped: event not found or inactive.")
        return
    
    logger.info(f"Running payment job for event {event_id} ('{event['name'] or event['activity_name']}')")
    
    await handle_payment_for_event(bot, event, scheduled_start_dt)

    await db.update_event(event_id, last_run=datetime.now(MOSCOW_TZ))

    if event['event_type'] == 'recurring':
        updated_event = await db.get_event(event_id)
        if updated_event:
            await schedule_event_jobs(updated_event, bot, scheduler)

async def run_event_reminder(event_id: int, bot: Bot, scheduled_start_dt: datetime):
    """Выполняется по расписанию. Отправляет напоминания."""
    event = await db.get_event(event_id)
    if not event or not event['is_active']:
        logger.warning(f"Job run_event_reminder for event {event_id} skipped: event not found or inactive.")
        return
        
    logger.info(f"Running reminder job for event {event_id} ('{event['name'] or event['activity_name']}')")
    
    await handle_reminders_for_event(bot, event, scheduled_start_dt)

async def handle_payment_for_event(bot: Bot, event: dict, event_start_dt: datetime | None = None):
    """Обрабатывает списания для конкретного наступившего события."""
    event_name = event['name'] or event['activity_name']
    fee = event['cost']
    
    next_run_dt = event_start_dt or get_next_run_time(
        event['event_type'],
        event.get('event_date'),
        event.get('weekday'),
        event.get('event_time'),
        event.get('last_run'),
        event.get('end_date'),
    )
    if not next_run_dt:
        logger.warning(f"Could not determine next run time for payment of event {event['id']}. Skipping.")
        return
    
    participants = await _get_final_participants(event, next_run_dt.date())

    if not participants:
        logger.info(f"No participants found for event {event['id']}, skipping payments.")
        return

    logger.info(f"Processing payments for {len(participants)} users for event '{event_name}'.")
    
    if fee <= 0:
        logger.info(f"Event {event['id']} has zero cost, skipping payments.")
        return
        
    fund_user_id = 0
    
    async with db.pool.connection() as conn:
        async with conn.transaction():
            for user in participants:
                await conn.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (fee, user['id']))
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'event_fee', %s)",
                    (user['id'], fund_user_id, fee, f"Оплата за событие: {event_name}")
                )
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id = %s", (user['id'],))
                
                start_time_str = f"\n🕒 Начало: {next_run_dt.strftime('%d.%m.%Y в %H:%M')} ({MSK_LABEL})"
                notification_text = (
                    f"▶️ <b>Начинается событие: «{event_name}»</b>\n"
                    f"🔗 Ссылка для подключения: {event.get('link') or '—'}{start_time_str}\n\n"
                    f"С вашего счета списано {format_amount(fee)} {CURRENCY_SYMBOL} за участие."
                )
                try:
                    await bot.send_message(user['telegram_id'], notification_text, parse_mode="HTML")
                except Exception as e:
                    logger.warning(f"Failed to send payment notification to user {user['telegram_id']}: {e}")
    
    logger.info(f"Successfully processed payments for event {event['id']}.")

async def handle_reminders_for_event(bot: Bot, event: dict, event_start_dt: datetime | None = None):
    """Отправляет напоминания подписчикам события."""
    if not event['reminder_text']:
        return

    next_run_dt = event_start_dt or get_next_run_time(
        event['event_type'],
        event.get('event_date'),
        event.get('weekday'),
        event.get('event_time'),
        event.get('last_run'),
        event.get('end_date'),
    )
    if not next_run_dt:
        logger.warning(f"Could not determine next run time for reminder of event {event['id']}. Skipping.")
        return

    participants = await _get_final_participants(event, next_run_dt.date())

    if not participants:
        return

    logger.info(f"Sending reminders to {len(participants)} users for event '{event['name'] or event['activity_name']}'.")
    
    event_name = event['name'] or event['activity_name']
    event_description = event['description'] or event['activity_description']
    
    reminder_text = event['reminder_text']
    if reminder_text == ".":
        reminder_text = await db.get_setting('default_reminder_text', LEXICON_RU["default_reminder"])

    try:
        formatted_text = reminder_text.format(
            event_name=event_name,
            event_description=event_description,
            start_date=next_run_dt.strftime('%d.%m.%Y'),
            start_time=next_run_dt.strftime('%H:%M') + f" ({MSK_LABEL})",
            cost=format_amount(event['cost']),
            currency_symbol=CURRENCY_SYMBOL,
            reminder_minutes=event['reminder_time'],
            link=event['link'] or ''
        )
    except KeyError as e:
        logger.error(f"Invalid placeholder in reminder text for event {event['id']}: {e}")
        formatted_text = f"Скоро начнется событие {event_name}"

    for user in participants:
        try:
            await bot.send_message(user['telegram_id'], formatted_text, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Failed to send reminder to {user['telegram_id']} for event {event['id']}: {e}")

async def process_demurrage(bot: Bot):
    """Ежедневный процесс демерреджа."""
    logger.info("Checking daily demurrage process...")
    
    is_enabled = await db.get_setting('demurrage_enabled', '0') == '1'
    if not is_enabled:
        logger.info("Demurrage is disabled. Skipping.")
        return

    try:
        interval_str = await db.get_setting('demurrage_interval_days', '1')
        interval = int(interval_str)
        last_run_str = await db.get_setting('demurrage_last_run', '1970-01-01')
        last_run_date = datetime.strptime(last_run_str, '%Y-%m-%d').date()
        
        days_since_last_run = (date.today() - last_run_date).days
        
        if days_since_last_run < interval:
            logger.info(f"Demurrage check: {days_since_last_run}/{interval} days passed. Skipping.")
            return
            
        logger.info("Demurrage interval passed. Starting process...")
        
        rate_str = await db.get_setting('demurrage_rate', '1.0')
        rate = Decimal(rate_str) / 100
        if rate <= 0:
            logger.info(f"Demurrage rate is zero or negative ({rate_str}%). Skipping.")
            return
    except (ValueError, TypeError) as e:
        logger.error(f"Could not get or parse demurrage settings: {e}")
        return

    try:
        users_processed = 0
        total_demurrage = Decimal('0')
        
        async with db.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT id, balance FROM users WHERE balance > 0 AND telegram_id != 0")
                    users_to_tax = await cur.fetchall()

                if not users_to_tax:
                    logger.info("No users with positive balance found. Demurrage process finished.")
                    # return out of transaction safely, then save last_run
                else:
                    fund_user_id = 0
                    for user in users_to_tax:
                        demurrage_amount = (user['balance'] * rate).quantize(Decimal('0.0001'))
                        if demurrage_amount <= 0: 
                            continue
                        
                        await conn.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (demurrage_amount, user['id']))
                        await conn.execute(
                            "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'demurrage', %s)",
                            (user['id'], fund_user_id, demurrage_amount, f"Демерредж {rate*100}%")
                        )
                        total_demurrage += demurrage_amount
                        users_processed += 1
                    
                    if total_demurrage > 0:
                        await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (total_demurrage, fund_user_id))
        
        # Если транзакция не выбросила исключение, смело ставим дату последнего запуска
        await db.set_setting('demurrage_last_run', date.today().isoformat())
        
        if users_processed > 0:
            logger.info(f"Demurrage successfully processed for {users_processed} users. Total amount: {format_amount(total_demurrage)} {CURRENCY_SYMBOL}.")
            
    except Exception as e:
        logger.error(f"An error occurred during demurrage process. Transaction rolled back. Error: {e}", exc_info=True)
