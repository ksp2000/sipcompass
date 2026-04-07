import pandas as pd

from src.backtest import simulate_sip


def test_simulate_sip_invests_once_per_month_after_target_date() -> None:
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                [
                    "2024-01-02",
                    "2024-01-05",
                    "2024-01-20",
                    "2024-02-03",
                    "2024-02-06",
                    "2024-02-20",
                    "2024-03-07",
                ]
            ),
            "Close": [10.0, 10.5, 10.8, 11.0, 11.2, 11.3, 11.5],
        }
    )
    config = {"sip": {"monthly_amount": 1000}}

    result = simulate_sip(df, config, sip_date=5)

    assert result["num_transactions"] == 3
    assert result["total_invested"] == 3000
    assert result["transactions"]["Date"].tolist() == [
        "2024-01-05",
        "2024-02-06",
        "2024-03-07",
    ]


def test_simulate_sip_backward_rolls_when_no_trading_day_on_or_after_sip_date() -> None:
    """When sip_date=28 and the last trading day of Feb is the 26th,
    the investment must happen on Feb 26 (backward roll), not skip to March 28."""
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                [
                    "2024-01-28",  # Jan: day >= 28, invest here
                    "2024-02-20",  # Feb: no day >= 28 in this month
                    "2024-02-26",  # Feb: last trading day — backward roll target
                    "2024-03-28",  # Mar: day >= 28, invest here
                ]
            ),
            "Close": [10.0, 11.0, 11.5, 12.0],
        }
    )
    config = {"sip": {"monthly_amount": 1000}}

    result = simulate_sip(df, config, sip_date=28)

    # All 3 months must have exactly one investment (no skipped months)
    assert result["num_transactions"] == 3
    assert result["total_invested"] == 3000
    assert result["transactions"]["Date"].tolist() == [
        "2024-01-28",
        "2024-02-26",  # backward-rolled to last trading day of Feb
        "2024-03-28",
    ]
