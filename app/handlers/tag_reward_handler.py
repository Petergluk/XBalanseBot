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

import html
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ReactionTypeEmoji, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from app.callbacks import DonateAction
from app.utils import ensure_user_exists, validate_amount

from redis.asyncio import Redis
from app.config import CURRENCY_SYMBOL, MAIN_GROUP_ID, REDIS_URL, REDIS_HOST
from app.database import db
from app.lexicon import LEXICON_RU
from app.utils import format_amount, safe_format_template
import json

router = Router()
logger = logging.getLogger(__name__)

_redis_client = None

TAG_RULES_CACHE_KEY = "xblns:tag_rules_cache"

def get_redis_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        effective_url = REDIS_URL or f"redis://{REDIS_HOST}:6379/0"
        _redis_client = Redis.from_url(effective_url, decode_responses=True)
    return _redis_client

async def invalidate_tag_rules_cache() -> None:
    try:
        redis = get_redis_client()
        await redis.delete(TAG_RULES_CACHE_KEY)
    except Exception as e:
        logger.warning(f"Failed to invalidate tag rules cache: {e}")

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
                safe_format_template(matched_rule['group_msg'],
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
        bot_msg = safe_format_template(bot_msg,
            mention=message.from_user.mention_html(),
            amount=format_amount(reward),
            currency_symbol=CURRENCY_SYMBOL,
            hashtag=matched_rule['hashtag']
        )
    try:
        await message.bot.send_message(user_id, bot_msg, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Could not send DM to {user_id}: {e}")




def _has_donate_trigger(text: str) -> bool:
    """Проверяет, содержит ли текст поста команду/метку для сбора благодарностей (/donate, /донат, #donate, #донат)."""
    if not text:
        return False
    return bool(re.search(r'(?:^|\s)(?:/donate|/донат|#donate|#донат)(?:@\w+)?(?:\s|$)', text, re.IGNORECASE))


def _get_donate_widget_keyboard(author_id: int, post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💝 Поблагодарить / Поддержать {CURRENCY_SYMBOL}",
                    callback_data=DonateAction(action="start", author_id=author_id, post_id=post_id).pack(),
                )
            ]
        ]
    )


async def _auto_delete_msg(bot: Bot, chat_id: int, msg_id: int, delay: float = 5.0):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except Exception:
        pass


async def _execute_post_donation(
    bot: Bot,
    chat_id: int,
    thread_id: int | None,
    sender_user,
    author_id: int,
    author_username: str,
    post_id: int,
    amount: Decimal,
    comment: str,
    widget_msg_id: int | None = None,
):
    """Выполняет перевод орфов автору поста и обновляет/создаёт карточку благодарностей под постом."""
    await ensure_user_exists(sender_user.id, sender_user.username, sender_user.is_bot)
    author_db = await db.get_user(telegram_id=author_id)
    if not author_db:
        await db.create_user(telegram_id=author_id, username=author_username if not author_username.startswith("user") else None)
        author_db = await db.get_user(telegram_id=author_id)

    result = await db.transfer(sender_user.id, author_db['id'], amount, comment)
    if not result.get('success'):
        err = result.get('error')
        if err == 'insufficient_funds':
            bal_fmt = format_amount(result.get('sender_balance', Decimal('0')))
            err_text = f"❌ @{sender_user.username or sender_user.id}, недостаточно средств (ваш баланс: <b>{bal_fmt} {CURRENCY_SYMBOL}</b>)."
        else:
            err_text = "❌ Не удалось выполнить перевод."
        err_msg = await bot.send_message(chat_id=chat_id, message_thread_id=thread_id, text=err_text, parse_mode="HTML")
        asyncio.create_task(_auto_delete_msg(bot, chat_id, err_msg.message_id, 6.0))
        return False

    await db.handle_debt_repayment(author_db['id'])

    # Ставим реакцию ❤️ на исходный пост
    if post_id:
        try:
            await bot.set_message_reaction(
                chat_id=chat_id,
                message_id=post_id,
                reaction=[ReactionTypeEmoji(emoji="❤️")],
            )
        except Exception:
            pass

    sender_disp = html.escape(sender_user.username or sender_user.full_name or f"user{sender_user.id}")
    author_disp = html.escape(author_db.get('username') or author_username or f"user{author_id}")
    amt_str = format_amount(amount)
    comment_suffix = f" <i>(«{html.escape(comment)}»)</i>" if comment and comment != "Благодарность за пост" else ""
    new_entry = f"• @{sender_disp} — <b>{amt_str} {CURRENCY_SYMBOL}</b>{comment_suffix}"

    redis = get_redis_client()
    kb = _get_donate_widget_keyboard(author_id=author_id, post_id=post_id)

    if widget_msg_id:
        log_key = f"xblns:donate_log:{chat_id}:{widget_msg_id}"
        try:
            await redis.rpush(log_key, new_entry)
            await redis.expire(log_key, 86400 * 30)
            entries = await redis.lrange(log_key, 0, -1)
        except Exception:
            entries = [new_entry]

        lines_str = "\n".join(entries)
        card_text = (
            f"💝 <b>Благодарности автору @{author_disp} за публикацию:</b>\n"
            f"{lines_str}\n\n"
            f"<i>Нажмите кнопку ниже, чтобы тоже поддержать автора:</i>"
        )
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=widget_msg_id,
                text=card_text,
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug(f"Could not edit donate widget {widget_msg_id}: {e}")
    else:
        card_text = (
            f"💝 <b>Благодарности автору @{author_disp} за публикацию:</b>\n"
            f"{new_entry}\n\n"
            f"<i>Нажмите кнопку ниже, чтобы тоже поддержать автора:</i>"
        )
        try:
            sent_widget = await bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id,
                reply_to_message_id=post_id if post_id else None,
                text=card_text,
                reply_markup=kb,
                parse_mode="HTML",
            )
            log_key = f"xblns:donate_log:{chat_id}:{sent_widget.message_id}"
            await redis.rpush(log_key, new_entry)
            await redis.expire(log_key, 86400 * 30)
        except Exception as e:
            logger.debug(f"Could not send new donate widget: {e}")

    # Уведомляем автора в ЛС
    try:
        await bot.send_message(
            author_id,
            LEXICON_RU["msg_transfer_received"].format(
                sender_username=sender_disp,
                amount=amt_str,
                currency_symbol=CURRENCY_SYMBOL,
                comment=html.escape(comment or "Благодарность за пост"),
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    return True


@router.message(Command("donate", "донат", ignore_case=True))
async def cmd_group_donate(message: Message):
    """
    Обрабатывает /donate или /донат в группе:
    1) Если вызвано ответом на чужой пост с суммой (/donate 50 [комментарий]) — сразу переводит орфы автору поста и удаляет команду.
    2) Если вызвано автором в самом посте или ответом на свой пост без суммы — прикрепляет кнопку «💝 Поблагодарить / Поддержать Ӫ».
    """
    if message.chat.type not in ("group", "supergroup"):
        await message.reply(
            "💡 Команда <code>/donate</code> используется в группе:\n"
            "• Добавьте <code>/donate</code> (или <code>#донат</code>) в конец своего поста в группе, чтобы под ним появилась кнопка <b>«💝 Поблагодарить / Поддержать Ӫ»</b>.\n"
            "• Или ответьте (Reply) на чужой пост в группе командой <code>/donate 50</code>, чтобы сразу отправить автору 50 Ӫ.",
            parse_mode="HTML",
        )
        return

    if not message.from_user or message.from_user.is_bot:
        return

    text = (message.text or message.caption or "").strip()
    parts = text.split()

    # Сценарий А: читатель ответил /donate 50 [комментарий] на чужой пост
    if message.reply_to_message and len(parts) >= 2 and parts[0].lower().split('@')[0] in ("/donate", "/донат"):
        target_msg = message.reply_to_message
        author = target_msg.from_user
        if not author or author.is_bot:
            return
        if author.id == message.from_user.id:
            err = await message.reply("❌ Нельзя отправить благодарность самому себе.")
            asyncio.create_task(_auto_delete_msg(message.bot, message.chat.id, err.message_id, 5.0))
            return
        try:
            amount = validate_amount(parts[1])
        except ValueError:
            err = await message.reply("❌ Укажите корректное положительное число, например: <code>/donate 50</code>", parse_mode="HTML")
            asyncio.create_task(_auto_delete_msg(message.bot, message.chat.id, err.message_id, 5.0))
            return

        comment = " ".join(parts[2:]) if len(parts) > 2 else "Благодарность за пост"
        try:
            await message.delete()
        except Exception:
            pass

        await _execute_post_donation(
            bot=message.bot,
            chat_id=message.chat.id,
            thread_id=message.message_thread_id,
            sender_user=message.from_user,
            author_id=author.id,
            author_username=author.username or f"user{author.id}",
            post_id=target_msg.message_id,
            amount=amount,
            comment=comment,
        )
        return

    # Сценарий Б: автор написал /donate в ответ на свой пост (или отдельным постом)
    target_post = message.reply_to_message if (message.reply_to_message and message.reply_to_message.from_user and not message.reply_to_message.from_user.is_bot) else message
    author = target_post.from_user
    await ensure_user_exists(author.id, author.username, author.is_bot)

    # Если команда /donate была отправлена пустой строкой в ответ на пост — удаляем саму команду
    if message.reply_to_message and len(parts) == 1:
        try:
            await message.delete()
        except Exception:
            pass

    author_disp = html.escape(author.username or author.full_name or f"user{author.id}")
    kb = _get_donate_widget_keyboard(author_id=author.id, post_id=target_post.message_id)
    await message.bot.send_message(
        chat_id=message.chat.id,
        message_thread_id=message.message_thread_id,
        reply_to_message_id=target_post.message_id,
        text=(
            f"💝 <b>Поддержать автора @{author_disp} за публикацию:</b>\n"
            f"<i>Нажмите кнопку ниже и введите любую сумму в {CURRENCY_SYMBOL}:</i>"
        ),
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.callback_query(DonateAction.filter(F.action == "start"))
async def handle_donate_button_click(callback: CallbackQuery, callback_data: DonateAction):
    """Запрашивает у нажавшего кнопку участника сумму благодарности в Ӫ."""
    sender = callback.from_user
    if sender.id == callback_data.author_id:
        await callback.answer("❌ Это ваш собственный пост — поблагодарить себя нельзя 😊", show_alert=True)
        return

    await ensure_user_exists(sender.id, sender.username, sender.is_bot)
    author_db = await db.get_user(telegram_id=callback_data.author_id)
    author_username = (author_db.get('username') if author_db else None) or f"user{callback_data.author_id}"

    chat_id = callback.message.chat.id
    thread_id = callback.message.message_thread_id
    sender_disp = html.escape(sender.username or sender.full_name or f"user{sender.id}")
    author_disp = html.escape(author_username)

    cancel_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=DonateAction(action="cancel", author_id=sender.id, post_id=0).pack(),
                )
            ]
        ]
    )

    prompt_msg = await callback.bot.send_message(
        chat_id=chat_id,
        message_thread_id=thread_id,
        text=(
            f"💝 @{sender_disp}, введите в чат сумму в {CURRENCY_SYMBOL} для благодарности @{author_disp}\n"
            f"<i>(просто число или число с комментарием, например: <code>50 Спасибо за практику!</code>)</i>:"
        ),
        reply_markup=cancel_kb,
        parse_mode="HTML",
    )

    redis = get_redis_client()
    wait_key = f"xblns:donate_wait:{chat_id}:{sender.id}"
    payload = {
        "author_id": callback_data.author_id,
        "author_username": author_username,
        "post_id": callback_data.post_id,
        "widget_msg_id": callback.message.message_id,
        "prompt_msg_id": prompt_msg.message_id,
    }
    await redis.setex(wait_key, 180, json.dumps(payload))
    await callback.answer()


@router.callback_query(DonateAction.filter(F.action == "cancel"))
async def handle_donate_cancel(callback: CallbackQuery, callback_data: DonateAction):
    if callback.from_user.id != callback_data.author_id:
        await callback.answer("Эта кнопка для того, кто начал перевод.", show_alert=True)
        return
    chat_id = callback.message.chat.id
    redis = get_redis_client()
    await redis.delete(f"xblns:donate_wait:{chat_id}:{callback.from_user.id}")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Отменено")


@router.message(F.chat.id == MAIN_GROUP_ID, lambda m: not (m.text or '').startswith('/'))
async def on_group_message(message: Message):
    # 1. Проверяем, не вводит ли этот участник сейчас сумму благодарности по кнопке «💝 Поблагодарить»
    if message.from_user and not message.from_user.is_bot:
        text_raw = (message.text or "").strip()
        if text_raw:
            redis = get_redis_client()
            wait_key = f"xblns:donate_wait:{message.chat.id}:{message.from_user.id}"
            pending_raw = await redis.get(wait_key)
            if pending_raw:
                parts = text_raw.split()
                try:
                    amount = validate_amount(parts[0])
                    comment = " ".join(parts[1:]) if len(parts) > 1 else "Благодарность за пост"
                    pending = json.loads(pending_raw)
                    await redis.delete(wait_key)
                    # Удаляем сообщение с цифрой и временную подсказку бота
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    if pending.get("prompt_msg_id"):
                        try:
                            await message.bot.delete_message(chat_id=message.chat.id, message_id=pending["prompt_msg_id"])
                        except Exception:
                            pass
                    await _execute_post_donation(
                        bot=message.bot,
                        chat_id=message.chat.id,
                        thread_id=message.message_thread_id,
                        sender_user=message.from_user,
                        author_id=pending["author_id"],
                        author_username=pending["author_username"],
                        post_id=pending.get("post_id", 0),
                        amount=amount,
                        comment=comment,
                        widget_msg_id=pending.get("widget_msg_id"),
                    )
                    return
                except ValueError:
                    pass

    # 2. Проверяем, не добавил ли автор в текст/подпись своего поста метку /donate, /донат, #donate или #донат
    post_text = message.text or message.caption or ""
    if message.from_user and not message.from_user.is_bot and _has_donate_trigger(post_text):
        await ensure_user_exists(message.from_user.id, message.from_user.username, message.from_user.is_bot)
        author_disp = html.escape(message.from_user.username or message.from_user.full_name or f"user{message.from_user.id}")
        kb = _get_donate_widget_keyboard(author_id=message.from_user.id, post_id=message.message_id)
        try:
            await message.reply(
                f"💝 <b>Поддержать автора @{author_disp} за публикацию:</b>\n"
                f"<i>Нажмите кнопку ниже и введите любую сумму в {CURRENCY_SYMBOL}:</i>",
                reply_markup=kb,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not attach donate widget: {e}")

    # 3. Проверяем обычные правила наград за хэштеги
    await _process_message(message)


@router.edited_message(F.chat.id == MAIN_GROUP_ID)
async def on_group_edited_message(message: Message):
    """Обрабатывает редактирование — начисляет только если пост ещё не получал награду."""
    await _process_message(message)
