"""Minimal data loading for SIP date brute-force."""

import os
import pandas as pd

CACHE_DIR = os.path.join("data", "cache")


def load_and_process_data(config: dict) -> pd.DataFrame:
    """Load price history from the configured data source and return sorted DataFrame."""
    data_source = config.get("data_source", {})
    source_type = data_source.get("type", "csv")

    if source_type == "csv":
        df = _load_csv_data(data_source)
    elif source_type == "yfinance":
        df = _load_yfinance_data(data_source, config)
    else:
        raise ValueError(
            f"Unknown data_source.type '{source_type}'. "
            "Supported values: 'csv', 'yfinance'."
        )

    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    if "Close" in df.columns:
        df["Close"] = df["Close"].round(2)
    return df


def _load_yfinance_data(data_source: dict, config: dict) -> pd.DataFrame:
    """Load NAV data for a Yahoo Finance ticker using an incremental persistent cache.

    One CSV file per ticker is maintained at data/cache/{ticker}_nav.csv.
    Only dates strictly before today are stored in the cache — today's row is
    always fetched fresh (market may not have closed yet).

    On each call:
    - If the cache is missing, fetch the full requested range (up to yesterday)
      and seed the cache.
    - If the cache exists, fetch only the gaps: dates before the cached minimum
      and/or dates after the cached maximum (up to yesterday).
    - Today's data (if end_date >= today) is fetched live and merged but never
      written to the cache.

    Args:
        data_source: The 'data_source' section of the config dict. Must contain
            a 'ticker' key.
        config: Full config dict. The 'backtest' section provides start/end dates.

    Returns:
        DataFrame covering [start_date, end_date] with Date and Close columns,
        sorted ascending by Date.
    """
    from src.data_fetcher import fetch_mf_data

    ticker: str = data_source.get("ticker", "")
    backtest_cfg = config.get("backtest", {})
    start_date: str = backtest_cfg.get("start_date") or ""
    end_date: str = backtest_cfg.get("end_date") or ""

    today = pd.Timestamp.today().normalize()
    yesterday = today - pd.Timedelta(days=1)

    # The latest date we are willing to cache (today's data may be partial).
    cacheable_end = yesterday

    identifier = ticker.replace("/", "_").replace("\\", "_")
    cache_path = os.path.join(CACHE_DIR, f"{identifier}_nav.csv")

    # ------------------------------------------------------------------ #
    # 1. Load or seed the cache                                            #
    # ------------------------------------------------------------------ #
    if os.path.exists(cache_path):
        cached = pd.read_csv(cache_path, parse_dates=["Date"])
        cached["Date"] = pd.to_datetime(cached["Date"]).dt.tz_localize(None)
        cached_min: pd.Timestamp = cached["Date"].min()
        cached_max: pd.Timestamp = cached["Date"].max()
        print(
            f"[{ticker}] Cache hit: {len(cached)} rows "
            f"({cached_min.date()} -> {cached_max.date()})"
        )

        frames: list[pd.DataFrame] = [cached]

        # Gap before: requested start is earlier than what we have cached.
        if start_date and pd.Timestamp(start_date) < cached_min:
            gap_end = (cached_min - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            print(f"[{ticker}] Fetching earlier gap: {start_date} -> {gap_end}")
            df_before = fetch_mf_data(ticker, start_date=start_date, end_date=gap_end)
            frames.insert(0, df_before)

        # Gap after: cached data doesn't reach yesterday yet.
        if cached_max < cacheable_end:
            gap_start = (cached_max + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            gap_end_ts = min(
                pd.Timestamp(end_date) if end_date else cacheable_end,
                cacheable_end,
            )
            if pd.Timestamp(gap_start) <= gap_end_ts:
                print(
                    f"[{ticker}] Fetching later gap: "
                    f"{gap_start} -> {gap_end_ts.strftime('%Y-%m-%d')}"
                )
                try:
                    df_after = fetch_mf_data(
                        ticker,
                        start_date=gap_start,
                        end_date=gap_end_ts.strftime("%Y-%m-%d"),
                    )
                    frames.append(df_after)
                except ValueError:
                    print(
                        f"[{ticker}] No new data in gap {gap_start} -> "
                        f"{gap_end_ts.strftime('%Y-%m-%d')}; using cached data."
                    )

        merged = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["Date"])
            .sort_values("Date")
            .reset_index(drop=True)
        )

        # Persist only cacheable rows (strictly before today).
        _save_cache(merged[merged["Date"] < today], cache_path)

    else:
        # No cache yet — fetch everything up to yesterday and seed the file.
        cacheable_end_str = cacheable_end.strftime("%Y-%m-%d")
        fetch_start = start_date or None
        print(
            f"[{ticker}] No cache found. Fetching {fetch_start} -> {cacheable_end_str}"
        )
        merged = fetch_mf_data(
            ticker, start_date=fetch_start, end_date=cacheable_end_str
        )
        os.makedirs(CACHE_DIR, exist_ok=True)
        _save_cache(merged, cache_path)

    # ------------------------------------------------------------------ #
    # 2. Fetch today live if the requested range includes today            #
    # ------------------------------------------------------------------ #
    if end_date and pd.Timestamp(end_date) >= today:
        print(f"[{ticker}] Fetching today's data live (not cached): {today.date()}")
        try:
            df_today = fetch_mf_data(
                ticker,
                start_date=today.strftime("%Y-%m-%d"),
                end_date=end_date,
            )
            merged = (
                pd.concat([merged, df_today], ignore_index=True)
                .drop_duplicates(subset=["Date"])
                .sort_values("Date")
                .reset_index(drop=True)
            )
        except ValueError:
            # Market may not have opened yet for today — proceed without it.
            print(f"[{ticker}] No data available yet for today; skipping.")

    # Slice to exactly the requested window and return.
    return filter_by_date_range(merged, start_date or None, end_date or None)


def _save_cache(df: pd.DataFrame, path: str) -> None:
    """Write a NAV DataFrame to the cache CSV file.

    Args:
        df: DataFrame to persist. Must contain a 'Date' column.
        path: Absolute or relative path to the target CSV file.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Cache updated: {path} ({len(df)} rows)")


def _load_csv_data(data_source: dict) -> pd.DataFrame:
    """Load data from a local CSV file."""
    csv_path = data_source.get("csv_path", "data/EE6KS5J1.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    # Normalise case-variant column names
    if "date" in df.columns and "Date" not in df.columns:
        df = df.rename(columns={"date": "Date"})

    # Allow legacy headers; remap only when Price exists but Close is missing
    if "Price" in df.columns and "Close" not in df.columns:
        df = df.rename(columns={"Price": "Close"})

    required_cols = {"Date", "Close"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    print(f"Loaded {len(df)} records from CSV {csv_path}")
    return df


def filter_by_date_range(
    df: pd.DataFrame, start_date: str | None = None, end_date: str | None = None
) -> pd.DataFrame:
    """Filter by date range (inclusive)."""
    if start_date is None and end_date is None:
        return df

    mask = pd.Series(True, index=df.index)
    if start_date:
        mask &= df["Date"] >= pd.to_datetime(start_date)
    if end_date:
        mask &= df["Date"] <= pd.to_datetime(end_date)

    filtered = df.loc[mask].reset_index(drop=True)
    print(f"Total rows after filtering: {len(filtered)}")
    return filtered


def validate_config(config: dict) -> dict:
    """Validate SIP configuration."""
    sip_date = int(config.get("sip", {}).get("default_date", 1))
    if sip_date < 1 or sip_date > 28:
        raise ValueError("sip.default_date must be between 1 and 28 (inclusive)")
    config["sip"]["default_date"] = sip_date

    if "monthly_amount" not in config.get("sip", {}):
        raise ValueError("sip.monthly_amount is required")

    data_source = config.get("data_source", {})
    source_type = data_source.get("type", "csv")
    if source_type == "csv":
        if not data_source.get("csv_path"):
            raise ValueError(
                "data_source.csv_path is required when data_source.type is 'csv'."
            )
    elif source_type == "yfinance":
        # Normalize legacy single `ticker` key to a `tickers` list.
        if "ticker" in data_source and "tickers" not in data_source:
            data_source["tickers"] = [data_source.pop("ticker")]
        tickers = data_source.get("tickers")
        if not tickers or not isinstance(tickers, list) or not all(tickers):
            raise ValueError(
                "data_source.tickers must be a non-empty list of ticker symbols "
                "when data_source.type is 'yfinance'."
            )
        data_source["tickers"] = [str(t).strip() for t in tickers]
    else:
        raise ValueError(
            f"Unknown data_source.type '{source_type}'. "
            "Supported values: 'csv', 'yfinance'."
        )

    return config
