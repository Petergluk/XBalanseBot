# tests/test_offers.py
import pytest
from decimal import Decimal
from psycopg.rows import dict_row
from app.database import db

class TestOffers:
    """Тесты функционала объявлений и покупок."""

    async def _setup_users(self, db, balance_seller=Decimal("100"), balance_buyer=Decimal("200")):
        """Вспомогательный метод для создания продавца и покупателя."""
        await db.create_user(telegram_id=9001, username="seller")
        await db.create_user(telegram_id=9002, username="buyer")
        seller = await db.get_user(telegram_id=9001)
        buyer = await db.get_user(telegram_id=9002)
        async with db.pool.connection() as conn:
            await conn.execute("UPDATE users SET balance = %s WHERE id = %s", (balance_seller, seller['id']))
            await conn.execute("UPDATE users SET balance = %s WHERE id = %s", (balance_buyer, buyer['id']))
        return seller, buyer

    async def test_create_and_get_offer(self, db):
        seller, _ = await self._setup_users(db)
        offer_id = await db.create_offer(
            seller_telegram_id=9001,
            title="Тестовый товар",
            description="Описание тестового товара",
            price=Decimal("50.5"),
            photo_id="file_id_123"
        )
        assert offer_id > 0

        offer = await db.get_offer(offer_id)
        assert offer is not None
        assert offer['title'] == "Тестовый товар"
        assert offer['description'] == "Описание тестового товара"
        assert offer['price'] == Decimal("50.5000")
        assert offer['photo_id'] == "file_id_123"
        assert offer['status'] == 'active'
        assert offer['seller_username'] == 'seller'
        assert offer['seller_telegram_id'] == 9001

    async def test_update_offer_message(self, db):
        seller, _ = await self._setup_users(db)
        offer_id = await db.create_offer(9001, "Товар", "Описание", Decimal("10"), None)
        await db.update_offer_message(offer_id, chat_id=-1001234, message_id=555)
        
        offer = await db.get_offer(offer_id)
        assert offer['chat_id'] == -1001234
        assert offer['message_id'] == 555

    async def test_cancel_offer_by_seller(self, db):
        seller, _ = await self._setup_users(db)
        offer_id = await db.create_offer(9001, "Товар", "Описание", Decimal("10"), None)
        
        # Отменяет продавец
        res = await db.cancel_offer(offer_id, user_telegram_id=9001)
        assert res is True
        
        offer = await db.get_offer(offer_id)
        assert offer['status'] == 'cancelled'

    async def test_cancel_offer_by_non_owner(self, db):
        seller, buyer = await self._setup_users(db)
        offer_id = await db.create_offer(9001, "Товар", "Описание", Decimal("10"), None)
        
        # Пытается отменить сторонний пользователь
        res = await db.cancel_offer(offer_id, user_telegram_id=9002)
        assert res is False
        
        offer = await db.get_offer(offer_id)
        assert offer['status'] == 'active'

    async def test_successful_purchase(self, db):
        seller, buyer = await self._setup_users(db, balance_seller=Decimal("100"), balance_buyer=Decimal("200"))
        offer_id = await db.create_offer(9001, "Услуга", "Описание услуги", Decimal("70"), None)
        
        res = await db.execute_offer_purchase(offer_id, buyer_telegram_id=9002)
        assert res is not None
        assert res['price'] == Decimal("70")
        assert res['offer']['title'] == "Услуга"
        
        # Проверяем балансы
        updated_seller = await db.get_user(telegram_id=9001)
        updated_buyer = await db.get_user(telegram_id=9002)
        assert updated_seller['balance'] == Decimal("170")
        assert updated_buyer['balance'] == Decimal("130")
        
        # Проверяем статус предложения
        offer = await db.get_offer(offer_id)
        assert offer['status'] == 'sold'
        assert offer['buyer_id'] == buyer['id']
        assert offer['buyer_username'] == 'buyer'
        
        # Проверяем запись в истории транзакций
        async with db.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM transactions WHERE type = 'purchase'")
                tx = await cur.fetchone()
                assert tx is not None
                assert tx['from_user_id'] == buyer['id']
                assert tx['to_user_id'] == seller['id']
                assert tx['amount'] == Decimal("70")

    async def test_purchase_own_offer(self, db):
        seller, _ = await self._setup_users(db)
        offer_id = await db.create_offer(9001, "Товар", "Описание", Decimal("10"), None)
        
        with pytest.raises(ValueError, match="cannot_buy_own_offer"):
            await db.execute_offer_purchase(offer_id, buyer_telegram_id=9001)

    async def test_purchase_insufficient_funds(self, db):
        seller, buyer = await self._setup_users(db, balance_seller=Decimal("0"), balance_buyer=Decimal("10"))
        offer_id = await db.create_offer(9001, "Дорогой товар", "Описание", Decimal("15"), None)
        
        with pytest.raises(ValueError, match="insufficient_funds"):
            await db.execute_offer_purchase(offer_id, buyer_telegram_id=9002)
            
        # Балансы не изменились
        updated_seller = await db.get_user(telegram_id=9001)
        updated_buyer = await db.get_user(telegram_id=9002)
        assert updated_seller['balance'] == Decimal("0")
        assert updated_buyer['balance'] == Decimal("10")

    async def test_purchase_already_sold(self, db):
        seller, buyer = await self._setup_users(db, balance_seller=Decimal("0"), balance_buyer=Decimal("100"))
        offer_id = await db.create_offer(9001, "Товар", "Описание", Decimal("30"), None)
        
        # Первая покупка
        await db.execute_offer_purchase(offer_id, buyer_telegram_id=9002)
        
        # Вторая покупка (уже продано)
        with pytest.raises(ValueError, match="offer_already_sold"):
            await db.execute_offer_purchase(offer_id, buyer_telegram_id=9002)

    async def test_purchase_already_cancelled(self, db):
        seller, buyer = await self._setup_users(db, balance_seller=Decimal("0"), balance_buyer=Decimal("100"))
        offer_id = await db.create_offer(9001, "Товар", "Описание", Decimal("30"), None)
        
        # Отменяем
        await db.cancel_offer(offer_id, user_telegram_id=9001)
        
        # Пытаемся купить
        with pytest.raises(ValueError, match="offer_already_cancelled"):
            await db.execute_offer_purchase(offer_id, buyer_telegram_id=9002)

    async def test_create_with_quantity_and_duration(self, db):
        seller, _ = await self._setup_users(db)
        offer_id = await db.create_offer(
            seller_telegram_id=9001,
            title="Опт",
            description="Оптовый товар",
            price=Decimal("10"),
            photo_id=None,
            quantity=5,
            duration_days=3
        )
        offer = await db.get_offer(offer_id)
        assert offer['quantity'] == 5
        assert offer['expires_at'] is not None

    async def test_multiple_purchases_decrement(self, db):
        seller, buyer = await self._setup_users(db, balance_seller=Decimal("0"), balance_buyer=Decimal("100"))
        offer_id = await db.create_offer(
            seller_telegram_id=9001,
            title="Товар",
            description="Описание",
            price=Decimal("10"),
            photo_id=None,
            quantity=2,
            duration_days=5
        )
        
        # Первая покупка: количество должно стать 1, статус остаться active
        res1 = await db.execute_offer_purchase(offer_id, buyer_telegram_id=9002)
        assert res1['remaining_quantity'] == 1
        assert res1['offer']['status'] == 'active'
        assert res1['offer']['quantity'] == 1
        
        # Вторая покупка: количество должно стать 0, статус sold
        res2 = await db.execute_offer_purchase(offer_id, buyer_telegram_id=9002)
        assert res2['remaining_quantity'] == 0
        assert res2['offer']['status'] == 'sold'
        assert res2['offer']['quantity'] == 0

    async def test_purchase_expired(self, db):
        seller, buyer = await self._setup_users(db, balance_seller=Decimal("0"), balance_buyer=Decimal("100"))
        offer_id = await db.create_offer(
            seller_telegram_id=9001,
            title="Старый товар",
            description="Описание",
            price=Decimal("10"),
            photo_id=None,
            quantity=1,
            duration_days=7
        )
        
        # Искусственно устанавливаем expires_at в прошлое
        async with db.pool.connection() as conn:
            await conn.execute("UPDATE offers SET expires_at = CURRENT_TIMESTAMP - interval '1 hour' WHERE id = %s", (offer_id,))
            
        # Пытаемся купить
        with pytest.raises(ValueError, match="offer_expired"):
            await db.execute_offer_purchase(offer_id, buyer_telegram_id=9002)
            
        # Убеждаемся, что статус предложения обновился на expired в БД
        offer = await db.get_offer(offer_id)
        assert offer['status'] == 'expired'
