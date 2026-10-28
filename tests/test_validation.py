# tests/test_validation.py
"""
Тесты валидации настроек (admin_commands).
"""
import pytest
from decimal import Decimal
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestSettingsValidation:
    """Тесты функций валидации настроек."""

    def test_validate_rate_valid(self):
        from app.handlers.admin_commands import _validate_rate
        assert _validate_rate(Decimal("0")) is None
        assert _validate_rate(Decimal("0.01")) is None
        assert _validate_rate(Decimal("50")) is None
        assert _validate_rate(Decimal("100")) is None

    def test_validate_rate_invalid(self):
        from app.handlers.admin_commands import _validate_rate
        assert _validate_rate(Decimal("-0.01")) is not None
        assert _validate_rate(Decimal("101")) is not None
        assert _validate_rate(Decimal("105")) is not None

    def test_validate_non_negative_valid(self):
        from app.handlers.admin_commands import _validate_non_negative
        assert _validate_non_negative(Decimal("0")) is None
        assert _validate_non_negative(Decimal("100")) is None
        assert _validate_non_negative(Decimal("0.01")) is None

    def test_validate_non_negative_invalid(self):
        from app.handlers.admin_commands import _validate_non_negative
        assert _validate_non_negative(Decimal("-1")) is not None
        assert _validate_non_negative(Decimal("-0.01")) is not None

    def test_validate_positive_valid(self):
        from app.handlers.admin_commands import _validate_positive
        assert _validate_positive(Decimal("0.01")) is None
        assert _validate_positive(Decimal("1")) is None
        assert _validate_positive(Decimal("100")) is None

    def test_validate_positive_invalid(self):
        from app.handlers.admin_commands import _validate_positive
        assert _validate_positive(Decimal("0")) is not None
        assert _validate_positive(Decimal("-1")) is not None


from datetime import datetime
from app.utils import format_transactions_history, safe_format_template


def test_safe_format_template_handles_braces_and_unknown_keys():
    """Проверяет, что safe_format_template не падает на фигурных скобках и неизвестных плейсхолдерах."""
    tpl = "Привет, {username}! Бонус: {amount} {unknown_placeholder} {"
    res = safe_format_template(tpl, username="Alex {Dev}", amount="100")
    assert "Alex {Dev}" in res
    assert "100" in res
    assert "{unknown_placeholder}" in res


def test_format_transactions_history_includes_purchase_tag_reward_and_fund_payment():
    """Проверяет корректное отображение всех типов транзакций (включая purchase, tag_reward, fund_payment и event_fee)."""
    now = datetime(2025, 10, 27, 12, 0)
    txs = [
        {
            "from_user_id": 0,
            "to_user_id": 42,
            "amount": Decimal("50"),
            "type": "tag_reward",
            "comment": "Бонус за #отчет",
            "sender_username": "fund",
            "recipient_username": "alice",
            "created_at": now,
        },
        {
            "from_user_id": 0,
            "to_user_id": 42,
            "amount": Decimal("200"),
            "type": "fund_payment",
            "comment": "Грант из фонда",
            "sender_username": "fund",
            "recipient_username": "alice",
            "created_at": now,
        },
        {
            "from_user_id": 42,
            "to_user_id": 77,
            "amount": Decimal("120"),
            "type": "purchase",
            "comment": "Покупка товара: <Кабель & Адаптер>",
            "sender_username": "alice",
            "recipient_username": "bob",
            "created_at": now,
        },
        {
            "from_user_id": 42,
            "to_user_id": 0,
            "amount": Decimal("80"),
            "type": "event_fee",
            "comment": "Оплата за событие: Киноклуб",
            "sender_username": "alice",
            "recipient_username": "fund",
            "created_at": now,
        },
    ]

    history_html = format_transactions_history(txs, user_db_id=42)
    assert "Бонус за #отчет" in history_html
    assert "от Фонда (Грант из фонда)" in history_html
    assert "@bob (Покупка товара: &lt;Кабель &amp; Адаптер&gt;)" in history_html
    assert "Мероприятие (Оплата за событие: Киноклуб)" in history_html
