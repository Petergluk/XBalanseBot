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
from aiogram.exceptions import TelegramBadRequest

from redis.asyncio import Redis
from app.config import CURRENCY_SYMBOL, MAIN_GROUP_ID, REDIS_URL
from app.database import db
from app.lexicon import LEXICON_RU
from app.utils import format_amount
import json

router = Router()
logger = logging.getLogger(__name__)

_redis_client = None

def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)

async def _get_rules():
    try:
        redis = get_redis_client()
        cache_key = "xblns:tag_rules_cache"
        cached = await redis.get(cache_key)
        
        if cached:
            return json.loads(cached)
            
        rules = await db.get_active_tag_rules()
        await redis.setex(cache_key, 60, json.dumps(rules, cls=CustomJSONEncoder))
        return rules
    except Exception as e:
        logger.warning(f"Redis cache error {e}. Falling back to DB for tag rules.")
        return await db.get_active_tag_rules()


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

    # Лимит за период
    limit_amount = matched_rule.get('limit_amount', 0)
    limit_period_days = matched_rule.get('limit_period_days', 1)

    # Начисляем!
    reward = Decimal(str(matched_rule['reward']))
    comment = f"Бонус за #{matched_rule['hashtag']}"
    awarded = await db.award_tag_reward_once(user_id, message_id, matched_rule['id'], reward, comment, limit_amount, limit_period_days)
    if not awarded:
        logger.debug(f"Message {message_id} already rewarded or daily limit hit, skipping")
        return
    logger.info(f"Tag reward: user {user_id} got {reward} for #{matched_rule['hashtag']} (msg {message_id})")

    # Реакция на пост
    emoji = matched_rule.get('reaction') or '🏅'
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except TelegramBadRequest as e:
        logger.debug(f"Could not set reaction (possibly unsupported or no rights): {e}")
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
