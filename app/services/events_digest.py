# app/services/events_digest.py
import html
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import CURRENCY_SYMBOL, GENERAL_ACTIVITY_ID, MAIN_GROUP_ID
from app.database import db
from app.utils import format_amount, parse_weekdays

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
WEEKDAYS_FULL_RU = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]
WEEKDAYS_SHORT_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def collect_weekly_occurrences(
    events: list[dict],
    now: datetime | None = None,
    days: int = 7,
) -> list[tuple[datetime, dict]]:
    """
    Собирает все предстоящие запуски активных событий на ближайшие `days` дней,
    включая несколько повторений регулярных событий за неделю.
    """
    if now is None:
        now = datetime.now(MOSCOW_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=MOSCOW_TZ)

    week_ahead = now + timedelta(days=days)
    occurrences: list[tuple[datetime, dict]] = []

    for event in events:
        event_type = event.get("event_type")
        if event_type == "single":
            ev_dt = event.get("event_date")
            if isinstance(ev_dt, datetime):
                ev_dt = ev_dt.replace(tzinfo=MOSCOW_TZ) if ev_dt.tzinfo is None else ev_dt.astimezone(MOSCOW_TZ)
                if now <= ev_dt <= week_ahead:
                    occurrences.append((ev_dt, event))
        elif event_type == "recurring":
            weekdays = parse_weekdays(event.get("weekday"))
            event_time = event.get("event_time")
            end_date = event.get("end_date")
            last_run = event.get("last_run")
            last_run_date = last_run.date() if isinstance(last_run, datetime) else last_run
            if not weekdays or not event_time:
                continue
            for offset in range(days + 1):
                candidate_date = now.date() + timedelta(days=offset)
                if candidate_date.weekday() not in weekdays:
                    continue
                if end_date and candidate_date > end_date:
                    continue
                if last_run_date and candidate_date == last_run_date:
                    continue
                candidate_dt = datetime.combine(candidate_date, event_time, tzinfo=MOSCOW_TZ)
                if now <= candidate_dt <= week_ahead:
                    occurrences.append((candidate_dt, event))

    occurrences.sort(key=lambda item: (item[0], int(item[1].get("id") or 0)))
    return occurrences


def _format_price_label(raw_val, currency_symbol: str) -> str:
    try:
        dec = Decimal(str(raw_val if raw_val is not None else 0))
    except Exception:
        return "Бесплатно"
    if dec <= 0:
        return "Бесплатно"
    return f"{format_amount(dec)} {currency_symbol}"


def format_weekly_digest_html(
    occurrences: list[tuple[datetime, dict]],
    bot_username: str,
    currency_symbol: str = CURRENCY_SYMBOL,
    now: datetime | None = None,
) -> str:
    """Форматирует HTML-пост еженедельного расписания событий для группы."""
    if now is None:
        now = datetime.now(MOSCOW_TZ)

    end_date = (now + timedelta(days=7)).date()
    period_str = f"{now.strftime('%d.%m')} – {end_date.strftime('%d.%m')}"

    header = (
        f"📅 <b>Афиша событий на неделю ({period_str})</b>\n\n"
        "Ниже — все запланированные встречи и практики на ближайшие 7 дней."
    )
    footer = (
        "\n\n👇 <b>Нажмите кнопку ниже</b>, чтобы перейти в бот и записаться на выбранное событие "
        "(или подписаться на направление целиком):"
    )

    lines: list[str] = [header]
    current_day = None
    truncated_count = 0
    max_body_len = 3850 - len(footer)

    for idx, (dt, event) in enumerate(occurrences):
        day = dt.date()
        day_header = ""
        if day != current_day:
            current_day = day
            day_name = WEEKDAYS_FULL_RU[day.weekday()]
            day_header = f"\n\n📌 <b>{day_name}, {day.strftime('%d.%m')}</b>"

        time_str = dt.strftime("%H:%M")
        raw_title = event.get("name") or event.get("activity_name") or "Событие"
        title = html.escape(str(raw_title))
        raw_act = event.get("activity_name") or ""
        act_name = html.escape(str(raw_act))
        activity_id = event.get("activity_id")

        act_suffix = ""
        if act_name and act_name != title and activity_id != GENERAL_ACTIVITY_ID:
            act_suffix = f" <i>({act_name})</i>"

        sub_label = _format_price_label(event.get("cost"), currency_symbol)
        allow_single = bool(event.get("allow_manual_registration"))
        single_val = event.get("single_cost")
        if single_val is None:
            single_val = event.get("cost")
        single_label = _format_price_label(single_val, currency_symbol)

        event_id = event.get("id")
        link_url = f"https://t.me/{bot_username}?start=event_{event_id}"

        if activity_id == GENERAL_ACTIVITY_ID:
            meta = f"📢 Общее событие ({sub_label}) · участвуют все"
        elif allow_single:
            meta = (
                f"по подписке: {sub_label} · разово: {single_label} · "
                f'<a href="{link_url}">Записаться →</a>'
            )
        else:
            meta = f'по подписке: {sub_label} · <a href="{link_url}">Записаться →</a>'

        entry = f"{day_header}\n• <b>{time_str} МСК</b> — <b>{title}</b>{act_suffix}\n  {meta}"
        candidate_len = sum(len(part) for part in lines) + len(entry)
        if candidate_len > max_body_len:
            truncated_count = len(occurrences) - idx
            break
        lines.append(entry)

    if truncated_count > 0:
        lines.append(f"\n<i>… и ещё {truncated_count} событий в расписании бота</i>")

    lines.append(footer)
    return "".join(lines)


def build_weekly_digest_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    """Создаёт кнопки под постом афиши для быстрого перехода в бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Выбрать событие и записаться",
                    url=f"https://t.me/{bot_username}?start=events",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Все активности и подписки",
                    url=f"https://t.me/{bot_username}?start=activities",
                )
            ],
        ]
    )


def should_run_weekly_digest(
    now: datetime,
    enabled: str,
    target_weekday: int,
    target_hour: int,
    target_minute: int,
    last_sent_date: str,
) -> bool:
    """Проверяет, пора ли публиковать еженедельную афишу событий."""
    if str(enabled) != "1":
        return False
    if now.tzinfo is None:
        now = now.replace(tzinfo=MOSCOW_TZ)
    today_iso = now.date().isoformat()
    if last_sent_date == today_iso:
        return False
    if now.weekday() != target_weekday:
        return False
    now_total_min = now.hour * 60 + now.minute
    target_total_min = target_hour * 60 + target_minute
    delta_min = now_total_min - target_total_min
    return 0 <= delta_min <= 15


async def publish_weekly_events_digest(bot: Bot, *, force: bool = False) -> dict:
    """Публикует еженедельную сводку событий в настроенный топик группы и закрепляет её."""
    if not MAIN_GROUP_ID:
        return {"ok": False, "reason": "no_main_group"}

    all_events = await db.get_all_events()
    now = datetime.now(MOSCOW_TZ)
    occurrences = collect_weekly_occurrences(all_events, now=now, days=7)
    if not occurrences:
        return {"ok": False, "reason": "no_events"}

    bot_info = await bot.get_me()
    bot_username = bot_info.username or ""
    if not bot_username:
        return {"ok": False, "reason": "no_bot_username"}

    text = format_weekly_digest_html(occurrences, bot_username=bot_username, now=now)
    keyboard = build_weekly_digest_keyboard(bot_username)

    thread_id_str = await db.get_setting("events_digest_thread_id", "0")
    try:
        thread_id = int(thread_id_str) if thread_id_str and str(thread_id_str) != "0" else None
    except ValueError:
        thread_id = None

    old_pinned_id = await db.get_setting("events_digest_last_pinned_msg_id", "")
    if old_pinned_id and str(old_pinned_id).isdigit():
        try:
            await bot.unpin_chat_message(
                chat_id=MAIN_GROUP_ID,
                message_id=int(old_pinned_id),
            )
        except Exception as unpin_err:
            logger.debug(f"Could not unpin previous digest message {old_pinned_id}: {unpin_err}")

    sent_msg = await bot.send_message(
        chat_id=MAIN_GROUP_ID,
        message_thread_id=thread_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    pinned = False
    try:
        await bot.pin_chat_message(
            chat_id=MAIN_GROUP_ID,
            message_id=sent_msg.message_id,
            disable_notification=True,
        )
        pinned = True
        await db.set_setting("events_digest_last_pinned_msg_id", str(sent_msg.message_id))
    except Exception as pin_err:
        logger.warning(f"Could not pin weekly digest message {sent_msg.message_id}: {pin_err}")

    if not force:
        await db.set_setting("events_digest_last_sent_date", now.date().isoformat())

    return {
        "ok": True,
        "message_id": sent_msg.message_id,
        "pinned": pinned,
        "events_count": len(occurrences),
        "thread_id": thread_id,
    }


async def check_and_send_weekly_digest(bot: Bot):
    """Периодическая задача планировщика (раз в минуту проверяет день/время публикации афиши)."""
    try:
        enabled = await db.get_setting("events_digest_enabled", "0")
        if str(enabled) != "1":
            return

        weekday_raw = await db.get_setting("events_digest_weekday", "0")
        hour_raw = await db.get_setting("events_digest_hour", "9")
        minute_raw = await db.get_setting("events_digest_minute", "0")
        last_sent_date = await db.get_setting("events_digest_last_sent_date", "")

        target_weekday = int(weekday_raw) if str(weekday_raw).isdigit() else 0
        target_hour = int(hour_raw) if str(hour_raw).isdigit() else 9
        target_minute = int(minute_raw) if str(minute_raw).isdigit() else 0

        now = datetime.now(MOSCOW_TZ)
        if not should_run_weekly_digest(
            now=now,
            enabled=enabled,
            target_weekday=target_weekday,
            target_hour=target_hour,
            target_minute=target_minute,
            last_sent_date=last_sent_date,
        ):
            return

        await db.set_setting("events_digest_last_sent_date", now.date().isoformat())
        res = await publish_weekly_events_digest(bot, force=False)
        if res.get("ok"):
            logger.info(
                f"Weekly events digest published: msg={res['message_id']}, "
                f"pinned={res['pinned']}, events={res['events_count']}, thread={res['thread_id']}"
            )
        else:
            logger.info(f"Weekly events digest skipped: reason={res.get('reason')}")
    except Exception as e:
        logger.error(f"Error in check_and_send_weekly_digest: {e}", exc_info=True)
