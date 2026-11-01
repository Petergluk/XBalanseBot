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



def test_validate_amount_indivisible_integer_orf():
    """Проверяет, что validate_amount принимает целые орфы и отклоняет дробные значения (STEP-11)."""
    from app.utils import validate_amount
    assert validate_amount("1") == Decimal("1")
    assert validate_amount("250") == Decimal("250")
    with pytest.raises(ValueError):
        validate_amount("10.5")
    with pytest.raises(ValueError):
        validate_amount("0.1")


def test_format_transactions_history_collapses_daily_demurrage():
    """Проверяет схлопывание ежедневных списаний демерреджа в одну итоговую строку (STEP-9)."""
    now = datetime(2026, 11, 1, 12, 0)
    txs = [
        {
            "from_user_id": 42,
            "to_user_id": 0,
            "amount": Decimal("5"),
            "type": "demurrage",
            "comment": "Демерредж 1%",
            "sender_username": "alice",
            "recipient_username": "fund",
            "created_at": now,
        },
        {
            "from_user_id": 42,
            "to_user_id": 0,
            "amount": Decimal("4"),
            "type": "demurrage",
            "comment": "Демерредж 1%",
            "sender_username": "alice",
            "recipient_username": "fund",
            "created_at": now,
        },
        {
            "from_user_id": 42,
            "to_user_id": 0,
            "amount": Decimal("6"),
            "type": "demurrage",
            "comment": "Демерредж 1%",
            "sender_username": "alice",
            "recipient_username": "fund",
            "created_at": now,
        },
    ]
    history_html = format_transactions_history(txs, user_db_id=42)
    assert "📉 Демерредж за 3 дн.: -15" in history_html


def test_clean_template_html():
    """Проверяет снятие случайного внешнего обрамления <pre> или <code> с сохранением ссылок."""
    from app.handlers.admin_commands import _clean_template_html

    # Снятие внешних <pre>...</pre>
    assert _clean_template_html("<pre>Привет, мир!</pre>") == "Привет, мир!"
    # Снятие внешних <code>...</code>
    assert _clean_template_html("<code>Привет, мир!</code>") == "Привет, мир!"
    # Сохранение внутренних ссылок при снятии внешней <pre>
    html_with_link = '<pre>1️⃣ Используем <a href="https://t.me/danzasemantica/1420">«Я-сообщения»</a>.</pre>'
    cleaned = _clean_template_html(html_with_link)
    assert cleaned == '1️⃣ Используем <a href="https://t.me/danzasemantica/1420">«Я-сообщения»</a>.'
    # Не трогает обычный текст без тегов кода
    normal = 'Привет, {username}! <a href="https://example.com">клик</a>'
    assert _clean_template_html(normal) == normal
