# app/db/tags.py
import logging
from typing import Any, Dict, List, Optional
from psycopg.rows import dict_row
from app.config import SYSTEM_FUND_USER_ID
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)

class TagRewardRepository(BaseRepository):
    """Репозиторий для работы с правилами начисления наград по хэштегам."""

    async def get_all_tag_rules(self) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM tag_rules ORDER BY id")
                return await cur.fetchall()

    async def get_active_tag_rules(self) -> List[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM tag_rules WHERE is_active = TRUE ORDER BY id")
                return await cur.fetchall()

    async def get_tag_rule(self, rule_id: int) -> Optional[Dict[str, Any]]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM tag_rules WHERE id = %s", (rule_id,))
                return await cur.fetchone()

    async def create_tag_rule(self, hashtag: str, min_chars: int, reward, limit_amount: int, limit_period_days: int,
                              thread_id: Optional[int], group_msg: Optional[str], bot_msg: Optional[str],
                              reaction: str) -> int:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO tag_rules (hashtag, min_chars, reward, limit_amount, limit_period_days, thread_id, group_msg, bot_msg, reaction)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    (hashtag.lstrip('#').lower(), min_chars, reward, limit_amount, limit_period_days, thread_id, group_msg, bot_msg, reaction)
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def delete_tag_rule(self, rule_id: int):
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM tag_rules WHERE id = %s", (rule_id,))

    async def get_rewarded_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Проверяет, было ли уже начислено за это сообщение."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM tag_rewards_log WHERE message_id = %s", (message_id,))
                return await cur.fetchone()

    async def log_tag_reward(self, user_telegram_id: int, message_id: int, rule_id: int):
        async with self.pool.connection() as conn:
            await conn.execute(
                """INSERT INTO tag_rewards_log (user_telegram_id, message_id, rule_id)
                   VALUES (%s, %s, %s) ON CONFLICT (message_id) DO NOTHING""",
                (user_telegram_id, message_id, rule_id)
            )

    async def count_today_tag_rewards(self, user_telegram_id: int, rule_id: int) -> int:
        """Считает количество начислений за сегодня для данного пользователя и правила."""
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """SELECT COUNT(*) FROM tag_rewards_log
                       WHERE user_telegram_id = %s AND rule_id = %s
                         AND rewarded_at >= CURRENT_DATE""",
                    (user_telegram_id, rule_id)
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def award_tag_reward(self, telegram_id: int, reward, comment: str):
        """Начисляет орфы пользователю за хэштег-пост (от фонда, тип manual_add)."""
        from decimal import Decimal
        reward = Decimal(str(reward))
        user = await self.get_user(telegram_id=telegram_id)
        if not user:
            return
        async with self.pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE users SET balance = balance + %s WHERE telegram_id = %s", (reward, telegram_id))
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (0, %s, %s, 'tag_reward', %s)",
                    (user['id'], reward, comment)
                )
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE telegram_id = %s", (telegram_id,))

    async def award_tag_reward_once(
        self,
        user_telegram_id: int,
        message_id: int,
        rule_id: int,
        reward,
        comment: str,
        limit_amount: int = 0,
        limit_period_days: int = 1
    ) -> bool:
        """
        Атомарно логирует сообщение и начисляет награду только один раз.
        Возвращает True, если начисление выполнено; False, если сообщение уже обработано.
        """
        from decimal import Decimal
        reward = Decimal(str(reward))
        user = await self.get_user(telegram_id=user_telegram_id)
        if not user:
            return False

        async with self.pool.connection() as conn:
            async with conn.transaction():
                # Блокируем пользователя, чтобы сериализовать награды и избежать гонки за лимитами
                await conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user['id'],))
                
                if limit_amount > 0:
                    query_params = [user_telegram_id, rule_id]
                    if limit_period_days == 0:
                        # 0 = за все время
                        date_filter = ""
                    else:
                        date_filter = "AND rewarded_at >= (CURRENT_DATE - %s::interval)"
                        query_params.append(f"{limit_period_days - 1} days")

                    query = f"""SELECT COUNT(*) FROM tag_rewards_log
                                WHERE user_telegram_id = %s AND rule_id = %s
                                {date_filter}"""
                    cur = await conn.execute(query, tuple(query_params))
                    row = await cur.fetchone()
                    if row and row[0] >= limit_amount:
                        return False

                log_cursor = await conn.execute(
                    """
                    INSERT INTO tag_rewards_log (user_telegram_id, message_id, rule_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (message_id) DO NOTHING
                    RETURNING id
                    """,
                    (user_telegram_id, message_id, rule_id),
                )
                log_row = await log_cursor.fetchone()
                if not log_row:
                    return False

                await conn.execute(
                    "UPDATE users SET balance = balance + %s, transaction_count = transaction_count + 1 WHERE telegram_id = %s",
                    (reward, user_telegram_id),
                )
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'tag_reward', %s)",
                    (SYSTEM_FUND_USER_ID, user['id'], reward, comment),
                )
                return True
