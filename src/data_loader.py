"""Minimal data loading for SIP date brute-force."""

import os

import pandas as pd
import yfinance as yf
import yaml

CACHE_DIR = os.path.join("data", "cache")
CACHE_META_PATH = os.path.join(CACHE_DIR, "nav_meta.yaml")


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
    cache_meta = _read_cache_meta(CACHE_META_PATH, ticker)
    if cache_meta is not None:
        cached_min, cached_max, cached_name = cache_meta
        print(f"[{ticker}] Cache hit: ({cached_min.date()} -> {cached_max.date()})")

        needs_update = False
        frames_pre: list[pd.DataFrame] = []
        frames_post: list[pd.DataFrame] = []

        # Gap before: requested start is earlier than what we have cached.
        if start_date and pd.Timestamp(start_date) < cached_min:
            gap_end = (cached_min - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            print(f"[{ticker}] Fetching earlier gap: {start_date} -> {gap_end}")
            df_before = fetch_mf_data(ticker, start_date=start_date, end_date=gap_end)
            frames_pre.append(df_before)
            needs_update = True

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
                    frames_post.append(df_after)
                    needs_update = True
                except ValueError:
                    print(
                        f"[{ticker}] No new data in gap {gap_start} -> "
                        f"{gap_end_ts.strftime('%Y-%m-%d')}; using cached data."
                    )

        if needs_update:
            # Load CSV only when we actually need to merge new data into it.
            cached = pd.read_csv(cache_path, parse_dates=["Date"])
            cached["Date"] = pd.to_datetime(cached["Date"]).dt.tz_localize(None)
            all_frames = frames_pre + [cached] + frames_post
            merged = (
                pd.concat(all_frames, ignore_index=True)
                .drop_duplicates(subset=["Date"])
                .sort_values("Date")
                .reset_index(drop=True)
            )
            # Persist only cacheable rows (strictly before today).
            cacheable = merged[merged["Date"] < today].copy()
            _save_cache(cacheable, cache_path)
            # Fetch name if not yet stored.
            if cached_name is None:
                cached_name = _fetch_ticker_name(ticker)
                print(f"[{ticker}] Fund name: {cached_name}")
            _write_cache_meta(
                CACHE_META_PATH,
                ticker,
                cacheable["Date"].min(),
                cacheable["Date"].max(),
                name=cached_name,
            )
        else:
            # No gaps — load CSV directly for the return value.
            merged = pd.read_csv(cache_path, parse_dates=["Date"])
            merged["Date"] = pd.to_datetime(merged["Date"]).dt.tz_localize(None)
            # Fetch and store name if missing from metadata.
            if cached_name is None:
                cached_name = _fetch_ticker_name(ticker)
                print(f"[{ticker}] Fund name: {cached_name}")
                _write_cache_meta(
                    CACHE_META_PATH,
                    ticker,
                    cached_min,
                    cached_max,
                    name=cached_name,
                )

    else:
        # No cache meta (treat as cache miss) — fetch everything up to yesterday
        # and seed the cache files.
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
        seed_name = _fetch_ticker_name(ticker)
        print(f"[{ticker}] Fund name: {seed_name}")
        _write_cache_meta(
            CACHE_META_PATH, ticker, merged["Date"].min(), merged["Date"].max(),
            name=seed_name,
        )

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


def _read_cache_meta(
    meta_path: str, ticker: str
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Read a ticker's cached date-range from the shared metadata YAML file.

    Args:
        meta_path: Path to the shared YAML metadata file (``nav_meta.yaml``).
        ticker: Ticker symbol whose entry to look up.

    Returns:
        Tuple of (min_date, max_date) as pd.Timestamp, or None if the file
        does not exist, the ticker has no entry, or the entry cannot be parsed.
    """
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r") as fh:
            all_meta = yaml.safe_load(fh) or {}
        entry = all_meta.get(ticker)
        if not entry:
            return None
        min_date = pd.Timestamp(entry["min_date"])
        max_date = pd.Timestamp(entry["max_date"])
        name: str | None = entry.get("name") or None
        return min_date, max_date, name
    except Exception:
        return None


def _write_cache_meta(
    meta_path: str,
    ticker: str,
    min_date: pd.Timestamp,
    max_date: pd.Timestamp,
    name: str | None = None,
) -> None:
    """Update a ticker's date-range entry in the shared metadata YAML file.

    Reads the existing file (if any), updates only the entry for ``ticker``,
    and writes the file back. If ``name`` is None, any previously stored name
    is preserved.

    Args:
        meta_path: Path to the shared YAML metadata file (``nav_meta.yaml``).
        ticker: Ticker symbol whose entry to create or update.
        min_date: Earliest date present in the ticker's cache CSV.
        max_date: Latest date present in the ticker's cache CSV.
        name: Human-readable fund/ETF name to cache alongside the dates. When
            None, the existing stored name (if any) is kept unchanged.
    """
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    if os.path.exists(meta_path):
        with open(meta_path, "r") as fh:
            all_meta = yaml.safe_load(fh) or {}
    else:
        all_meta = {}
    existing_entry: dict = all_meta.get(ticker) or {}
    new_entry: dict = {
        "min_date": min_date.strftime("%Y-%m-%d"),
        "max_date": max_date.strftime("%Y-%m-%d"),
        "name": name if name is not None else existing_entry.get("name"),
    }
    all_meta[ticker] = new_entry
    with open(meta_path, "w") as fh:
        yaml.dump(all_meta, fh, default_flow_style=False)


def _fetch_ticker_name(ticker: str) -> str:
    """Fetch the human-readable fund/ETF name from Yahoo Finance.

    Args:
        ticker: Yahoo Finance ticker symbol.

    Returns:
        The ``longName`` or ``shortName`` from yfinance info, or the ticker
        symbol itself when the info call fails or the fields are absent.
    """
    try:
        info = yf.Ticker(ticker).info
        return info.get("longName") or info.get("shortName") or ticker
    except Exception:
        return ticker


def get_ticker_name(ticker: str) -> str:
    """Return the cached human-readable name for a ticker from nav_meta.yaml.

    Args:
        ticker: Yahoo Finance ticker symbol.

    Returns:
        The stored fund/ETF name, or the ticker symbol itself if not found.
    """
    result = _read_cache_meta(CACHE_META_PATH, ticker)
    if result is not None:
        _min, _max, name = result
        if name:
            return name
    return ticker


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
    if not isinstance(config, dict):
        raise ValueError("Configuration file must contain a YAML object at the top level")

    config.setdefault("sip", {})
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

    sip_optimization = config.setdefault("sip_optimization", {})
    top_n = int(sip_optimization.get("top_n", 3))
    if top_n < 1:
        raise ValueError("sip_optimization.top_n must be at least 1")
    sip_optimization["top_n"] = top_n

    return config
