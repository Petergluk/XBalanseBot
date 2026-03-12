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
