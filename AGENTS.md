# AGENTS.md — MF SIP Date Finder

AI coding agents operating in this repo should read this file carefully before making changes.

---

## Build, Run, and Dependency Commands

**Dependency management uses `uv`. Never use `pip` or `python` directly.**

```bash
uv sync                              # Install / refresh all dependencies from uv.lock
uv run main.py                       # Run the app with default config.yaml
uv run main.py --config path/to/config.yaml   # Run with a custom config
```

**There is no test suite.** No pytest, tox, or unittest files exist. If you add tests, place them in a `tests/` directory and register `pytest` as a dev dependency via `uv add --dev pytest`.

**There is no lint/format configuration.** No Ruff, Black, Flake8, or mypy config files exist. Follow the code style conventions described below when editing.

---

## Project Overview

This CLI tool determines the optimal SIP (Systematic Investment Plan) date for a mutual fund or ETF by backtesting all possible monthly investment dates (1–28) over a historical date range and ranking them by XIRR and return %.

**Pipeline:** load config → fetch/load NAV data → run SIP simulation for each date → rank results → print table + write CSV.

---

## Configuration (`config.yaml`)

All runtime settings live here. Key sections:

```yaml
data_source:
  type: yfinance          # "csv" or "yfinance"
  tickers:                # list of Yahoo Finance tickers; required when type=yfinance
    - "0P0000XW8F.BO"
    - "0P0001EXMQ.BO"    # add more as needed
  # Legacy single-ticker form is still accepted and auto-promoted to a list:
  # ticker: "0P0000XW8F.BO"
  # csv_path: data/my_nav.csv  # required when type=csv

sip:
  monthly_amount: 3000
  default_date: 5         # fallback date (1–28), used by validate_config only

backtest:
  start_date: "2025-01-01"
  end_date: "2026-03-27"

sip_optimization:
  enabled: true
  analyze_dates: []        # empty = test all dates 1–28; or provide e.g. [1, 5, 10, 15]

cert_path: "~/.config/cert/cacert.crt"  # declared but currently unused in code
```

---

## Source Module Reference

### `main.py`
CLI entry point. Functions: `parse_args`, `load_config`, `_output_stem`, `save_outputs`, `print_top_dates`, `print_summary_table`, `main`.
- Parses `--config` CLI argument (defaults to `config.yaml`)
- Calls `validate_config`, `load_and_process_data`, `optimize_sip_dates`
- Writes `data/output/<stem>_sip_results.csv` per ticker
- NAV data is **not** written here — managed by the data loader cache
- Exits via `raise SystemExit(...)` when optimization is disabled

### `src/data_loader.py`
Dispatches between CSV and yfinance data sources. Module-level constant: `CACHE_DIR = "data/cache"`.
- `load_and_process_data(config)` — main entry; normalises dates and rounds Close to 2dp
- `_load_yfinance_data(data_source, config)` — incremental persistent cache logic (see below)
- `_save_cache(df, path)` — writes a DataFrame to the cache CSV, creating dirs as needed
- `_load_csv_data(data_source)` — normalises column names (`date`→`Date`, `Price`→`Close`)
- `filter_by_date_range(df, start, end)` — inclusive slice on `Date` column
- `validate_config(config)` — raises `ValueError` for missing/invalid keys; validates `sip_date` range (1–28); normalizes legacy `ticker` string to `tickers` list

**Cache strategy in `_load_yfinance_data`:**
- One CSV per ticker at `data/cache/{ticker}_nav.csv` (e.g. `0P0000XW8F.BO_nav.csv`).
- Only rows with `Date < today` are stored — today's partial data is always fetched live.
- On each call, only the missing date ranges (gap before cached minimum, gap after cached maximum) are fetched from Yahoo Finance. Already-cached rows are never re-downloaded.
- Today's data (if `end_date >= today`) is fetched live, merged into the returned DataFrame, but **not** written to the cache.

### `src/data_fetcher.py`
Thin wrapper around `yfinance.download()`.
- `fetch_mf_data(ticker, start_date, end_date)` — returns DataFrame with `Date`, `Close`, etc.
- Strips timezone from index; shifts end date +1 day (yfinance end is exclusive); flattens MultiIndex columns

### `src/backtest.py`
Core SIP simulation engine.
- `simulate_sip(df, config, sip_date)` — iterates rows; invests once per calendar month on the first trading day >= `sip_date`; accumulates units + cash flows; calls `calculate_xirr`
- Returns dict: `sip_date`, `total_invested`, `final_value`, `return_pct`, `xirr`, `num_investments`, `transactions` (DataFrame)

### `src/finance.py`
XIRR calculation.
- `calculate_xirr(cash_flows, dates)` — converts dates to day-offsets; solves NPV=0 via `scipy.optimize.newton` with `brentq` fallback; returns annualised % or `0.0` on failure

### `src/optimizer.py`
Iterates SIP dates and ranks results.
- `optimize_sip_dates(df, config)` — calls `simulate_sip` for each date in `analyze_dates` (or 1–28)
- Sorts by `(xirr, return_pct)` descending; annotates delta-vs-average fields
- Returns dict with `top_dates` (top 3), `all_results` (full ranked list), `averages`

### `src/data_persistence.py`
Legacy module. Saves/loads DataFrames as Parquet + YAML metadata into `data/processed/`.
**Not called anywhere in the active pipeline.** Do not add new calls to this module; its column assumptions (`buy_signal`, `intensity_level`, `investment_amount`) are stale.

---

## Code Style Guidelines

### Imports
Follow PEP 8 import ordering (no automated sorter is configured):
1. Standard library (`os`, `argparse`, `datetime`, `pathlib`, `statistics`, `typing`)
2. Third-party (`pandas`, `numpy`, `scipy`, `yaml`, `yfinance`)
3. Local (`from src.xxx import yyy`)

Separate each group with a blank line. No wildcard imports.

### Formatting
- 4-space indentation. No tabs.
- Lines should stay under 100 characters where practical.
- No formatter is configured; match the surrounding style when editing existing files.

### Type Hints
- Use type annotations on all new function signatures.
- Prefer Python 3.10+ union syntax (`str | None`) over `Optional[str]` — the project targets `>=3.11`.
- Return types are required on all public functions.
- Existing code is inconsistent (some functions lack parameter types); bring new code up to standard.

```python
# Preferred style
def simulate_sip(df: pd.DataFrame, config: dict, sip_date: int) -> dict:
    ...
```

### Naming Conventions
- Functions and variables: `snake_case`
- Module-level constants: `UPPER_SNAKE_CASE`
- Private/internal helpers: prefix with single underscore (`_load_csv_data`, `_output_stem`)
- Config dict keys mirror their YAML counterparts exactly (`monthly_amount`, `start_date`, etc.)

### Error Handling
- Raise `ValueError` for invalid config values (missing required keys, out-of-range dates, unknown source type).
- Raise `FileNotFoundError` for missing CSV or data files.
- XIRR failures fall through silently (bare `except Exception`) and return `0.0` — this is intentional; do not add logging noise there.
- Avoid `except Exception: pass` for any new code; handle or re-raise with context.
- All user-facing messages use `print()`. No logging framework is in use; do not add one without discussion.

### Docstrings
- Prefer Google-style docstrings with `Args:`, `Returns:`, and `Raises:` sections for public functions.
- One-line docstrings are acceptable for simple private helpers.
- Module-level docstrings are encouraged.

```python
def fetch_mf_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch historical NAV/price data from Yahoo Finance.

    Args:
        ticker: Yahoo Finance ticker symbol.
        start_date: Inclusive start date as ISO string (YYYY-MM-DD).
        end_date: Inclusive end date as ISO string (YYYY-MM-DD).

    Returns:
        DataFrame with columns: Date (index), Close, High, Low, Open, Volume.

    Raises:
        ValueError: If no data is returned for the given ticker/range.
    """
```

---

## Data Flow Summary

```
config.yaml
    └─► validate_config()
    └─► load_and_process_data()  (per ticker)
            ├─ cache hit?  ──► load from data/cache/{ticker}_nav.csv
            │                  fetch only missing gaps (before/after cached range)
            │                  update cache with new rows
            └─ cache miss? ──► fetch_mf_data() ──► seed data/cache/{ticker}_nav.csv
            └─ end_date >= today? ──► fetch today live (not cached)
    └─► filter_by_date_range()
    └─► optimize_sip_dates()
            └─ simulate_sip() × N dates ──► calculate_xirr()
    └─► print_top_dates()  (per ticker)
    └─► print_summary_table()  (when >1 ticker)
    └─► save_outputs()  ──► data/output/{ticker}_{start}_{end}_sip_results.csv
```

---

## Output Files

`data/cache/` — persistent NAV cache (git-ignored):

| File pattern | Description |
|---|---|
| `data/cache/<ticker>_nav.csv` | Incremental NAV cache for a ticker; rows before today only |

`data/output/` — analysis outputs (git-ignored):

| File pattern | Description |
|---|---|
| `<ticker>_<start>_<end>_sip_results.csv` | Full per-date SIP results, ranked by XIRR |
