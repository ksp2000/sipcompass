# SIPCompass

SIPCompass is a Python CLI that backtests monthly SIP dates for mutual funds and ETFs, ranks them by XIRR, and helps you compare how different dates of the month would have performed historically.

## Why use it?

If you invest monthly, SIPCompass helps answer questions like:

- Does the 5th of the month perform better than the 15th?
- Which date historically produced the best XIRR?
- How far is the best date from the average across all possible SIP dates?

It is meant to be a practical backtesting tool — not a crystal ball in a blazer.

## Features

- Backtests SIP dates from `1` to `28`
- Supports both local CSV data and live Yahoo Finance tickers
- Ranks results by XIRR, then by absolute return %
- Rich terminal output with readable tables
- Incremental cache for Yahoo Finance data
- CSV export of ranked results
- Configurable `top_n` results display
- CLI overrides for quick experimentation

## Quick start

### Prerequisites

- Python `3.11+`
- [`uv`](https://github.com/astral-sh/uv)

### Install

```bash
uv sync
```

### Create your config

Copy the example config:

```bash
cp config.example.yaml config.yaml
```

On Windows PowerShell:

```powershell
Copy-Item config.example.yaml config.yaml
```

Then edit `config.yaml`.

### Run

```bash
uv run sipcompass --config config.yaml
```

## Example config

### Yahoo Finance mode

```yaml
data_source:
  type: yfinance
  tickers:
    - "0P0001ANWB.BO"
    - "NIFTYBEES.NS"

sip:
  monthly_amount: 5000
  default_date: 5

backtest:
  start_date: "2021-01-01"
  end_date: "2026-03-28"

sip_optimization:
  enabled: true
  analyze_dates: []
  top_n: 5
```

### CSV mode

```yaml
data_source:
  type: csv
  csv_path: data/sample_nav.csv

sip:
  monthly_amount: 5000
  default_date: 5

backtest:
  start_date: "2021-01-01"
  end_date: "2026-03-28"

sip_optimization:
  enabled: true
  analyze_dates: []
  top_n: 5
```

Your CSV must include:

- `Date` in `YYYY-MM-DD` format
- `Close` or `Price`

Example:

```csv
Date,Close
2024-01-02,10.50
2024-01-03,10.52
2024-01-04,10.61
```

## Common CLI overrides

You can override config values without editing the YAML file each time:

```bash
uv run sipcompass --config config.yaml --top-n 7
uv run sipcompass --config config.yaml --start-date 2022-01-01 --end-date 2026-03-28
uv run sipcompass --config config.yaml --ticker NIFTYBEES.NS --ticker GOLDBEES.NS
uv run sipcompass --config config.yaml --amount 10000
```

## Output

SIPCompass prints:

- average return % and XIRR % across all analyzed dates
- the top `N` SIP dates ranked by XIRR and return %
- one-row-per-ticker summary when multiple tickers are analyzed
- a CSV file in `data/output/` with all ranked results

## How ranking works

For each SIP date from `1` to `28`, SIPCompass:

1. simulates investing once per month on the first trading day on or after that date
2. tracks cash outflows and final portfolio value
3. calculates XIRR for the resulting cash flows
4. ranks dates by:
   - highest XIRR first
   - highest return % second

The tool avoids dates `29`–`31` to keep the comparison consistent across months.

## Finding ticker symbols

For live mode, use Yahoo Finance ticker symbols.

Examples:

- Indian mutual fund on BSE: `0P0001ANWB.BO`
- NSE ETF: `NIFTYBEES.NS`

Search on [Yahoo Finance](https://finance.yahoo.com/) and copy the symbol exactly.

## Project structure

- `main.py` — CLI entry point
- `src/data_loader.py` — CSV/Yahoo data loading and cache handling
- `src/backtest.py` — SIP simulation logic
- `src/finance.py` — XIRR calculation
- `src/optimizer.py` — ranking and summary generation

## Notes and caveats

- This tool is for historical analysis only.
- Past performance does **not** guarantee future returns.
- Yahoo Finance data availability can vary by symbol and market.
- XIRR failures currently fall back to `0.0%`.
- Use this as a research aid, not as investment advice.

## Development

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

## License

MIT
