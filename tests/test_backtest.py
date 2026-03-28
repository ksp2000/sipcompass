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
