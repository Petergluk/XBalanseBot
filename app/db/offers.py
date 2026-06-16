# app/db/offers.py
import logging
from typing import Any, Dict, Optional
from psycopg.rows import dict_row
from app.db.base import BaseRepository

logger = logging.getLogger(__name__)

class OfferRepository(BaseRepository):
    """Репозиторий для работы с офферами (маркетплейс)."""

    async def create_offer(
        self,
        seller_telegram_id: int,
        title: str,
        description: Optional[str],
        price,
        photo_id: Optional[str],
        quantity: int = 1,
        duration_days: int = 14
    ) -> int:
        """Создает объявление в БД и возвращает его ID."""
        from decimal import Decimal
        price = Decimal(str(price))
        user = await self.get_user(telegram_id=seller_telegram_id)
        if not user:
            raise ValueError("seller_not_found")
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO offers (seller_id, title, description, price, photo_id, status, quantity, expires_at)
                       VALUES (%s, %s, %s, %s, %s, 'active', %s, CURRENT_TIMESTAMP + %s * interval '1 day') RETURNING id""",
                    (user['id'], title, description, price, photo_id, quantity, duration_days)
                )
                row = await cur.fetchone()
                return row[0]

    async def get_offer(self, offer_id: int) -> Optional[Dict[str, Any]]:
        """Возвращает объявление по ID, включая информацию о продавце и покупателе."""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """SELECT o.*, 
                               s.username as seller_username, s.telegram_id as seller_telegram_id,
                               b.username as buyer_username, b.telegram_id as buyer_telegram_id
                        FROM offers o
                        JOIN users s ON o.seller_id = s.id
                        LEFT JOIN users b ON o.buyer_id = b.id
                        WHERE o.id = %s""",
                    (offer_id,)
                )
                return await cur.fetchone()

    async def update_offer_message(self, offer_id: int, chat_id: int, message_id: int):
        """Сохраняет ID сообщения, опубликованного в группе."""
        async with self.pool.connection() as conn:
            await conn.execute(
                "UPDATE offers SET chat_id = %s, message_id = %s WHERE id = %s",
                (chat_id, message_id, offer_id)
            )

    async def execute_offer_purchase(self, offer_id: int, buyer_telegram_id: int) -> Dict[str, Any]:
        """
        Выполняет транзакцию покупки предложения.
        Проверяет баланс покупателя, осуществляет перевод орфов от покупателя к продавцу,
        записывает транзакцию, уменьшает количество на 1.
        Если количество падает до 0, переводит статус в 'sold'.
        Проверяет, не истек ли срок действия (expires_at).
        Выполняется атомарно с использованием FOR UPDATE с защитой от дедлоков.
        """
        from decimal import Decimal
        from datetime import datetime, timezone
        
        async with self.pool.connection() as conn:
            # Сначала проверяем статус и срок действия без транзакции
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT expires_at, status FROM offers WHERE id = %s", (offer_id,))
                offer_check = await cur.fetchone()
            if not offer_check:
                raise ValueError("offer_not_found")
                
            if offer_check['status'] != 'active':
                raise ValueError(f"offer_already_{offer_check['status']}")
                
            if offer_check['expires_at'] and datetime.now(timezone.utc) > offer_check['expires_at']:
                await conn.execute("UPDATE offers SET status = 'expired' WHERE id = %s", (offer_id,))
                await conn.commit()
                raise ValueError("offer_expired")
                
            async with conn.transaction():
                # 1. Получаем ID покупателя
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT id FROM users WHERE telegram_id = %s", (buyer_telegram_id,))
                    buyer_row = await cur.fetchone()
                if not buyer_row:
                    raise ValueError("buyer_not_found")
                buyer_id = buyer_row['id']
                
                # 2. Получаем ID продавца
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT seller_id FROM offers WHERE id = %s", (offer_id,))
                    offer_row = await cur.fetchone()
                if not offer_row:
                    raise ValueError("offer_not_found")
                seller_id = offer_row['seller_id']
                
                if buyer_id == seller_id:
                    raise ValueError("cannot_buy_own_offer")
                
                # 3. Блокируем покупателя и продавца В СТРОГОМ ПОРЯДКЕ ВОЗРАСТАНИЯ ID (защита от дедлока)
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT id FROM users WHERE id IN (%s, %s) ORDER BY id FOR UPDATE",
                        (buyer_id, seller_id)
                    )
                    await cur.fetchall()
                    
                # 4. Блокируем объявление FOR UPDATE
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM offers WHERE id = %s FOR UPDATE", (offer_id,))
                    offer = await cur.fetchone()
                    
                if offer['status'] != 'active':
                    raise ValueError(f"offer_already_{offer['status']}")
                    
                # Двойная проверка на срок действия под блокировкой
                if offer['expires_at'] and datetime.now(timezone.utc) > offer['expires_at']:
                    await conn.execute("UPDATE offers SET status = 'expired' WHERE id = %s", (offer_id,))
                    raise ValueError("offer_expired")
                    
                # 5. Получаем актуальные данные покупателя и продавца
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM users WHERE id = %s", (buyer_id,))
                    buyer = await cur.fetchone()
                    await cur.execute("SELECT * FROM users WHERE id = %s", (seller_id,))
                    seller = await cur.fetchone()

                price = Decimal(str(offer['price']))
                if buyer['balance'] < price:
                    raise ValueError("insufficient_funds")
                
                # 6. Обновляем балансы
                await conn.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (price, buyer['id']))
                await conn.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (price, seller['id']))
                
                # 7. Записываем транзакцию
                comment = f"Покупка товара: {offer['title']}"
                await conn.execute(
                    "INSERT INTO transactions (from_user_id, to_user_id, amount, type, comment) VALUES (%s, %s, %s, 'purchase', %s)",
                    (buyer['id'], seller['id'], price, comment)
                )
                
                # 8. Увеличиваем счетчик транзакций
                await conn.execute("UPDATE users SET transaction_count = transaction_count + 1 WHERE id IN (%s, %s)", (buyer['id'], seller['id']))
                
                # 9. Уменьшаем количество и обновляем статус
                new_quantity = offer['quantity'] - 1
                new_status = 'sold' if new_quantity <= 0 else 'active'
                
                await conn.execute(
                    "UPDATE offers SET quantity = %s, status = %s, buyer_id = %s WHERE id = %s",
                    (new_quantity, new_status, buyer['id'], offer_id)
                )
                
                # Получаем обновленное объявление
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM offers WHERE id = %s", (offer_id,))
                    updated_offer = await cur.fetchone()
                
                return {
                    "offer": updated_offer,
                    "seller": seller,
                    "buyer": buyer,
                    "price": price,
                    "remaining_quantity": new_quantity
                }

    async def cancel_offer(self, offer_id: int, user_telegram_id: int) -> bool:
        """
        Отменяет объявление. Отменить может либо продавец, либо администратор.
        Возвращает True в случае успеха.
        """
        user = await self.get_user(telegram_id=user_telegram_id)
        if not user:
            return False
        
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute("SELECT * FROM offers WHERE id = %s FOR UPDATE", (offer_id,))
                    offer = await cur.fetchone()
                if not offer:
                    return False
                
                # Проверяем права: либо создатель (seller_id), либо админ
                if offer['seller_id'] != user['id'] and not user['is_admin']:
                    return False
                
                if offer['status'] != 'active':
                    return False
                
                await conn.execute("UPDATE offers SET status = 'cancelled' WHERE id = %s", (offer_id,))
                return True
