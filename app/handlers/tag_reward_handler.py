# XBalanseBot/app/handlers/tag_reward_handler.py
"""
Мониторинг сообщений в группе и начисление орфов за хэштег-посты.

Бот слушает ВСЕ сообщения в основной группе. Когда сообщение содержит
хэштег из активных правил, а длина текста ≥ min_chars — начисляет орфы.
Редактирование поста учитывается только если пост ещё не был награждён.
"""
import logging
import re
import asyncio
from datetime import datetime
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.types import Message, ReactionTypeEmoji

from app.config import CURRENCY_SYMBOL, MAIN_GROUP_ID
from app.database import db
from app.lexicon import LEXICON_RU
from app.utils import format_amount

router = Router()
logger = logging.getLogger(__name__)

# Простой кеш правил: (rules, loaded_at)
_rules_cache: tuple = ([], None)
_CACHE_TTL_SECONDS = 60


async def _get_rules():
    global _rules_cache
    rules, loaded_at = _rules_cache
    now = datetime.now()
    if loaded_at is None or (now - loaded_at).total_seconds() > _CACHE_TTL_SECONDS:
        rules = await db.get_active_tag_rules()
        _rules_cache = (rules, now)
    return rules


def _extract_hashtags(text: str) -> set[str]:
    """Извлекает хэштеги из текста в нижнем регистре без #."""
    return {tag.lstrip('#').lower() for tag in re.findall(r'#[\wа-яёА-ЯЁ]+', text)}


async def _process_message(message: Message):
    """Основная логика проверки и начисления."""
    # Только из основной группы
    if message.chat.id != MAIN_GROUP_ID:
        return

    # Нет автора (системное, анонимное) — пропускаем
    if not message.from_user or message.from_user.is_bot:
        return

    text = message.text or message.caption or ''
    if not text:
        return

    hashtags_in_msg = _extract_hashtags(text)
    if not hashtags_in_msg:
        return

    rules = await _get_rules()

    # Ищем первое совпавшее правило
    matched_rule = None
    for rule in rules:
        if rule['hashtag'].lower() not in hashtags_in_msg:
            continue
        # Проверяем топик, если задан
        if rule['thread_id'] is not None and message.message_thread_id != rule['thread_id']:
            continue
        matched_rule = rule
        break

    if not matched_rule:
        return

    # Проверяем длину текста
    if len(text) < matched_rule['min_chars']:
        logger.debug(f"Tag {matched_rule['hashtag']}: text too short ({len(text)} < {matched_rule['min_chars']})")
        return

    user_id = message.from_user.id
    message_id = message.message_id

    # Пост уже был награждён?
    existing = await db.get_rewarded_message(message_id)
    if existing:
        logger.debug(f"Message {message_id} already rewarded, skipping")
        return

    # Суточный лимит
    daily_limit = matched_rule['daily_limit']
    if daily_limit > 0:
        today_count = await db.count_today_tag_rewards(user_id, matched_rule['id'])
        if today_count >= daily_limit:
            logger.debug(f"User {user_id} hit daily limit ({daily_limit}) for rule {matched_rule['id']}")
            return

    # Начисляем!
    reward = Decimal(str(matched_rule['reward']))
    comment = f"Бонус за #{matched_rule['hashtag']}"
    await db.award_tag_reward(user_id, reward, comment)
    await db.log_tag_reward(user_id, message_id, matched_rule['id'])
    logger.info(f"Tag reward: user {user_id} got {reward} for #{matched_rule['hashtag']} (msg {message_id})")

    # Реакция на пост
    emoji = matched_rule.get('reaction') or '🏅'
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except Exception as e:
        logger.warning(f"Could not set reaction: {e}")

    # Сообщение в группу (reply на пост)
    if matched_rule.get('group_msg'):
        try:
            await message.reply(
                matched_rule['group_msg'].format(
                    mention=message.from_user.mention_html(),
                    amount=format_amount(reward),
                    currency_symbol=CURRENCY_SYMBOL,
                    hashtag=matched_rule['hashtag']
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not send group_msg: {e}")

    # DM пользователю
    bot_msg = matched_rule.get('bot_msg')
    if not bot_msg:
        user = await db.get_user(telegram_id=user_id)
        balance = user['balance'] if user else '?'
        bot_msg = LEXICON_RU['msg_tag_reward_default_dm'].format(
            hashtag=matched_rule['hashtag'],
            amount=format_amount(reward),
            currency_symbol=CURRENCY_SYMBOL,
            balance=format_amount(Decimal(str(balance)))
        )
    else:
        bot_msg = bot_msg.format(
            mention=message.from_user.mention_html(),
            amount=format_amount(reward),
            currency_symbol=CURRENCY_SYMBOL,
            hashtag=matched_rule['hashtag']
        )
    try:
        await message.bot.send_message(user_id, bot_msg, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Could not send DM to {user_id}: {e}")


@router.message(F.chat.id == MAIN_GROUP_ID, ~F.text.startswith('/'))
async def on_group_message(message: Message):
    await _process_message(message)


@router.edited_message(F.chat.id == MAIN_GROUP_ID)
async def on_group_edited_message(message: Message):
    """Обрабатывает редактирование — начисляет только если пост ещё не получал награду."""
    await _process_message(message)
