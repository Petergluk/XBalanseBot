# XBalanseBot/app/utils.py
# FULL FILE EMITTED: YES
# v1.5.7
# 2025-08-28 13:24:00
"""
Модуль с утилитами и вспомогательными функциями.

Версия 1.5.7:
- ИСПРАВЛЕНИЕ: В `get_next_run_time` изменена логика сравнения времени.
  - Для разовых событий `>` заменено на `>=` для корректной обработки событий, наступающих в текущую минуту.
  - Для повторяющихся событий `now.time() >= event_time` заменено на `now.time() > event_time`, чтобы событие, назначенное на текущее время, считалось сегодняшним, а не переносилось на неделю.
  - Это исправляет баг, из-за которого планировщик не мог обработать наступившее событие и оно считалось прошедшим.
"""
import logging
from datetime import datetime, timedelta, time, date
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from aiogram import Bot
from app.config import MAIN_GROUP_ID, CURRENCY_SYMBOL, DEV_MODE
from app.database import db

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

WEEKDAYS_RU = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
WEEKDAYS_SHORT_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

def parse_weekdays(weekday_val: str | int | None) -> list[int]:
    """Парсит значение из БД (строка '0,2', число 0 или None) в отсортированный список int."""
    if weekday_val is None:
        return []
    if isinstance(weekday_val, int):
        return [weekday_val]
    # Если строка (например '0, 2')
    try:
        parts = [int(x.strip()) for x in str(weekday_val).split(',') if x.strip().isdigit()]
        return sorted(list(set(parts)))
    except ValueError:
        return []

def format_weekdays(weekday_val: str | int | None) -> str:
    """Форматирует значение БД в короткую строку, например 'Пн, Ср, Пт'."""
    days = parse_weekdays(weekday_val)
    if not days:
        return "Не задано"
    if len(days) == 7:
        return "Ежедневно"
    return ", ".join([WEEKDAYS_SHORT_RU[d] for d in days])

def format_amount(amount: Decimal) -> str:
    """
    Форматирует сумму для вывода, убирая лишние нули и избегая научной нотации.

    Args:
        amount (Decimal): Сумма для форматирования.

    Returns:
        str: Отформатированная строка.
    """
    if amount is None:
        return "0"
    
    s = f'{amount:f}'
    
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
        
    return s

def validate_amount(text: str, max_value: Decimal = Decimal('1000000')) -> Decimal:
    """
    Парсит и валидирует денежную сумму с защитой от переполнений.
    """
    try:
        amount = Decimal(text.replace(',', '.'))
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount > max_value:
            raise ValueError(f"Amount exceeds maximum {max_value}")
        return amount
    except (InvalidOperation, ValueError):
        raise ValueError("Invalid amount format")

def format_transactions_history(transactions: list, user_db_id: int) -> str:
    """
    Форматирует список транзакций в текстовый отчет по категориям.

    Args:
        transactions (list): Список транзакций (объекты sqlite3.Row).
        user_db_id (int): ID пользователя в БД, для которого строится отчет.

    Returns:
        str: Отформатированный HTML-текст истории.
    """
    response_parts = []
    top_ups, incoming, outgoing, system_debits = [], [], [], []

    for tx in transactions:
        if tx['to_user_id'] == user_db_id:
            if tx['type'] in ('manual_add', 'welcome_bonus', 'top_up'):
                top_ups.append(tx)
            elif tx['type'] in ('transfer', 'fund_payment'):
                incoming.append(tx)
        elif tx['from_user_id'] == user_db_id:
            if tx['type'] in ('transfer', 'event_fee'):
                outgoing.append(tx)
            elif tx['type'] in ('demurrage', 'manual_rem'):
                system_debits.append(tx)

    import html
    def format_tx_line(tx, sign, prefix="", peer_name=""):
        date_str = tx['created_at'].strftime('%d.%m %H:%M')
        amount_str = format_amount(Decimal(str(tx['amount'])))
        safe_comment = html.escape(tx['comment']) if tx['comment'] else ""
        safe_peer = html.escape(peer_name) if peer_name else ""
        comment = f" ({safe_comment})" if safe_comment else ""
        return f"  {sign} {amount_str} {prefix}{safe_peer}{comment} - {date_str}\n"

    if top_ups:
        response_parts.append("\n\n💰 <b>Пополнения:</b>\n")
        for tx in top_ups:
            response_parts.append(format_tx_line(tx, "✅ +"))
    
    if incoming:
        response_parts.append("\n📥 <b>Входящие переводы:</b>\n")
        for tx in incoming:
            peer = f"@{tx['sender_username']}" if tx['sender_username'] else "Пользователь"
            response_parts.append(format_tx_line(tx, "➕", prefix="от ", peer_name=peer))

    if outgoing:
        response_parts.append("\n📤 <b>Исходящие переводы и платежи:</b>\n")
        for tx in outgoing:
            peer = f"@{tx['recipient_username']}" if tx['recipient_username'] != 'fund' else "Фонд"
            response_parts.append(format_tx_line(tx, "➖ -", peer_name=peer))

    if system_debits:
        response_parts.append("\n💸 <b>Системные списания:</b>\n")
        for tx in system_debits:
            peer = "Техническое списание" if tx['type'] == 'manual_rem' else "Демерредж"
            response_parts.append(format_tx_line(tx, "➖ -", peer_name=peer))
            
    return "".join(response_parts)

async def get_user_balance(telegram_id: int) -> Decimal:
    """Получает баланс пользователя."""
    user = await db.get_user(telegram_id=telegram_id)
    return Decimal(str(user['balance'])) if user else Decimal('0')

async def get_transaction_count(telegram_id: int) -> int:
    """Получает количество транзакций пользователя."""
    user = await db.get_user(telegram_id=telegram_id)
    return user['transaction_count'] if user else 0

async def is_admin(telegram_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    user = await db.get_user(telegram_id=telegram_id)
    return bool(user['is_admin']) if user else False



async def ensure_user_exists(telegram_id: int, username: str | None, is_bot: bool = False) -> bool:
    """
    Проверяет существование пользователя и создает его, если он отсутствует.
    Также обновляет username, если он появился или изменился.
    Игнорирует ботов.
    """
    if is_bot:
        logger.info(f"Ignored attempt to register a bot with id {telegram_id}")
        return False

    user = await db.get_user(telegram_id=telegram_id)
    
    if not user:
        await db.create_user(telegram_id, username)
        logger.info(f"New user created: {username or telegram_id}")
        return True
    
    if username and (not user['username'] or user['username'] != username.lower()):
        await db.update_user_username(telegram_id, username)
        logger.info(f"Username for user {telegram_id} updated to {username.lower()}")

    return False

def get_next_run_time(
    event_type: str, 
    event_date: datetime | None, 
    weekday_val: str | int | None, 
    event_time: time | None,
    last_run: datetime | None = None,
    end_date: date | None = None,
) -> datetime | None:
    """
    Вычисляет следующую дату и время для события на основе его типа и расписания.
    Всегда возвращает aware datetime в Europe/Moscow.
    Поддерживает мульти-дни недели для recurring (например '0,2,4').
    """
    now = datetime.now(MOSCOW_TZ)

    if event_type == 'single':
        if event_date and event_date >= now:
            return event_date
        return None

    if event_type == 'recurring' and weekday_val is not None and event_time is not None:
        weekdays = parse_weekdays(weekday_val)
        if not weekdays:
            return None
            
        today_weekday = now.weekday()
        
        best_target_dt = None
        min_days_ahead = -1

        for wd in weekdays:
            days_ahead = wd - today_weekday
            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0:
                # Если время уже наступило или прошло, переносим этот день на следующую неделю.
                event_dt_today = datetime.combine(now.date(), event_time, tzinfo=MOSCOW_TZ)
                if now > event_dt_today:
                    days_ahead = 7
            
            # Находим минимальное положительное окно ожидания
            if min_days_ahead == -1 or days_ahead < min_days_ahead:
                min_days_ahead = days_ahead

        if min_days_ahead != -1:
            target_date = now.date() + timedelta(days=min_days_ahead)
            if end_date and target_date > end_date:
                return None
            best_target_dt = datetime.combine(target_date, event_time).replace(tzinfo=MOSCOW_TZ)
            return best_target_dt

    return None
