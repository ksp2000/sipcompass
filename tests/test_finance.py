import pytest

from src.finance import calculate_xirr


def test_calculate_xirr_returns_positive_value_for_profitable_cash_flows() -> None:
    cash_flows = [-1000, -1000, 2300]
    dates = ["2024-01-01", "2025-01-01", "2026-01-01"]

    result = calculate_xirr(cash_flows, dates)

    assert result > 0


def test_calculate_xirr_returns_zero_for_invalid_input_lengths() -> None:
    result = calculate_xirr([-1000, 1500], ["2024-01-01"])

    assert result == 0.0
