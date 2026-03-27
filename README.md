# MF SIP Date Finder

Find the optimal SIP (Systematic Investment Plan) date for mutual funds by analyzing historical NAV data and calculating XIRR for different investment dates.

## What it does

This tool helps you determine which date of the month (1-28) would give you the best returns for your SIP investments. It:

1. Loads historical NAV (Net Asset Value) data from a CSV file
2. Simulates SIP investments for each possible date (1-28)
3. Calculates XIRR (Extended Internal Rate of Return) for each date
4. Ranks dates by XIRR and absolute returns
5. Shows you the top 3 dates with performance comparisons

## Quick Start

### 1. Choose a data source

**Option A — Local CSV file** (default)

Place your NAV CSV file in the `data/` folder. The CSV must contain at minimum:
- `Date` column (format: YYYY-MM-DD)
- `Close` column (NAV value) or `Price` column

```csv
Date,Close
2013-01-02,10.50
2013-01-03,10.52
...
```

**Option B — Live data via Yahoo Finance**

No local file needed. Supply a valid [Yahoo Finance](https://finance.yahoo.com) ticker symbol.  
For Indian mutual funds traded on BSE/NSE look up the ticker on Yahoo Finance  
(e.g. `0P0001ANWB.BO` for an Indian MF; `NIFTYBEES.NS` for an NSE ETF).

### 2. Configure
Edit `config.yaml`:

**CSV mode (default):**
```yaml
data_source:
  type: csv
  csv_path: data/your_nav_file.csv

sip:
  monthly_amount: 3000  # Your SIP amount

backtest:
  start_date: "2013-01-02"
  end_date: "2026-01-09"

sip_optimization:
  enabled: true
  analyze_dates: []  # Leave empty to test all dates 1-28
```

**Yahoo Finance live-fetch mode:**
```yaml
data_source:
  type: yfinance
  ticker: "0P0001ANWB.BO"  # Yahoo Finance ticker

sip:
  monthly_amount: 3000

backtest:
  start_date: "2013-01-02"
  end_date: "2026-01-09"

sip_optimization:
  enabled: true
  analyze_dates: []
```

### 3. Run
```bash
python main.py
```

Or with uv:
```bash
uv run main.py
```

## Output

The tool will show:
- Average return % and XIRR % across all dates
- Top 3 dates ranked by XIRR
- Performance difference compared to average

Example output:
```
======================================================================
SIP DATE OPTIMIZATION RESULTS
======================================================================

Average across all dates:
  Return: 206.28%
  XIRR:   16.01%

Top 3 SIP dates (ranked by XIRR, then return %):
----------------------------------------------------------------------
Date |  Return% |   XIRR% |  vs Avg Return |  vs Avg XIRR
----------------------------------------------------------------------
  24 |   206.49 |   16.05 |          +0.21 |        +0.04
  25 |   206.28 |   16.05 |          -0.00 |        +0.04
  26 |   206.16 |   16.05 |          -0.12 |        +0.04
======================================================================
```

## Dependencies

- pandas
- scipy
- pyyaml
- yfinance (for live-fetch mode)

Install via:
```bash
pip install pandas scipy pyyaml yfinance
```

Or with uv:
```bash
uv sync
```

## How it works

For each date (1-28):
1. Simulate monthly SIP investments on that date
2. Track all cash flows (investments and final portfolio value)
3. Calculate XIRR using the cash flow dates
4. Calculate absolute returns

The best date is the one that gives the highest annualized return (XIRR).

## Notes

- The tool tests dates 1-28 to avoid month-end complications
- XIRR accounts for the time value of money unlike simple returns
- Past performance doesn't guarantee future results
- Use this as one input among many for your investment decisions
