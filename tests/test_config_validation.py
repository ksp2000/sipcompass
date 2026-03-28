import pytest

from src.data_loader import validate_config


def test_validate_config_normalizes_single_yfinance_ticker() -> None:
    config = {
        "data_source": {"type": "yfinance", "ticker": "NIFTYBEES.NS"},
        "sip": {"monthly_amount": 5000, "default_date": 5},
        "sip_optimization": {"enabled": True, "top_n": 3},
    }

    validated = validate_config(config)

    assert validated["data_source"]["tickers"] == ["NIFTYBEES.NS"]
    assert validated["sip_optimization"]["top_n"] == 3


def test_validate_config_rejects_invalid_top_n() -> None:
    config = {
        "data_source": {"type": "csv", "csv_path": "data/sample.csv"},
        "sip": {"monthly_amount": 5000, "default_date": 5},
        "sip_optimization": {"enabled": True, "top_n": 0},
    }

    with pytest.raises(ValueError, match="top_n"):
        validate_config(config)
