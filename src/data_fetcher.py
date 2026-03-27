import pandas as pd
import yfinance as yf


def fetch_mf_data(ticker: str, start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """Fetch historical price/NAV data from Yahoo Finance.

    Args:
        ticker: Yahoo Finance ticker symbol (e.g., '0P0001ANWB.BO' for an Indian MF,
                or 'NIFTYBEES.NS' for an ETF).
        start_date: Optional start date as 'YYYY-MM-DD'. Fetches all available history
                    when omitted.
        end_date:   Optional end date as 'YYYY-MM-DD' (inclusive). Uses today when omitted.

    Returns:
        DataFrame with columns: Date (datetime64, tz-naive), Close, plus any extra
        OHLCV columns present in the Yahoo response.  Sorted ascending by Date.

    Raises:
        ValueError: If no data is returned for the given ticker / date range.
    """
    print(f"Fetching data for ticker '{ticker}' from Yahoo Finance...")

    kwargs: dict = {"auto_adjust": True, "progress": False}
    if start_date:
        kwargs["start"] = start_date
    if end_date:
        # yfinance end is exclusive; shift by one day so end_date is included
        kwargs["end"] = (pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    raw = yf.download(ticker, **kwargs)

    if raw is None or raw.empty:
        raise ValueError(f"No data returned by Yahoo Finance for ticker '{ticker}'.")

    # Flatten MultiIndex columns that yfinance sometimes produces
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    # Normalise index → Date column, strip timezone
    df = raw.reset_index().rename(columns={"index": "Date", "Datetime": "Date"})
    if "Date" not in df.columns:
        df = df.rename(columns={df.columns[0]: "Date"})

    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)

    if "Close" not in df.columns:
        raise ValueError(
            f"Yahoo Finance response for '{ticker}' does not contain a 'Close' column. "
            f"Available columns: {list(df.columns)}"
        )

    df = df.sort_values("Date").reset_index(drop=True)

    print(f"Successfully fetched {len(df)} records for '{ticker}'.")
    return df