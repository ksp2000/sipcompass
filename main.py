import argparse
import os
import pandas as pd
import yaml

from src.data_loader import load_and_process_data, filter_by_date_range, validate_config
from src.optimizer import optimize_sip_dates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SIP date optimizer")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    return parser.parse_args()


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _output_stem(ticker: str, config: dict) -> str:
    """Build a filename stem from a ticker symbol and the backtest date range."""
    identifier = ticker.replace("/", "_").replace("\\", "_")
    bt = config.get("backtest", {})
    start = (bt.get("start_date") or "start").replace("-", "")
    end = (bt.get("end_date") or "end").replace("-", "")
    return f"{identifier}_{start}_{end}"


def save_outputs(results: dict, ticker: str, config: dict) -> None:
    """Write all-dates SIP results to a CSV file in data/output/.

    NAV data is no longer written here — it is managed as a persistent cache
    in data/cache/ by src/data_loader._load_yfinance_data.
    """
    out_dir = os.path.join("data", "output")
    os.makedirs(out_dir, exist_ok=True)
    stem = _output_stem(ticker, config)

    results_path = os.path.join(out_dir, f"{stem}_sip_results.csv")
    pd.DataFrame(results["per_date"]).to_csv(results_path, index=False)
    print(f"SIP results written to {results_path}")


def print_top_dates(results: dict, ticker: str = "") -> None:
    """Print per-ticker SIP optimization results with top-3 dates."""
    averages = results["averages"]
    title = (
        f"SIP DATE OPTIMIZATION RESULTS -- {ticker}"
        if ticker
        else "SIP DATE OPTIMIZATION RESULTS"
    )
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print("\nAverage across all dates:")
    print(f"  Return: {averages['return_pct']:.2f}%")
    print(f"  XIRR:   {averages['xirr']:.2f}%")
    print("\nTop 3 SIP dates (ranked by XIRR, then return %):")
    print("-" * 70)
    print(
        f"{'Date':>4} | {'Return%':>8} | {'XIRR%':>7} | {'vs Avg Return':>14} | {'vs Avg XIRR':>12}"
    )
    print("-" * 70)
    for entry in results["top_three"]:
        print(
            "{:>4} | {:>8.2f} | {:>7.2f} | {:>+14.2f} | {:>+12.2f}".format(
                entry["sip_date"],
                entry["return_pct"],
                entry["xirr"],
                entry["delta_vs_avg_return"],
                entry["delta_vs_avg_xirr"],
            )
        )
    print("=" * 70)


def print_summary_table(all_ticker_results: list[dict]) -> None:
    """Print a one-row-per-ticker summary of the best SIP date for each ticker.

    Only printed when more than one ticker was analyzed.

    Args:
        all_ticker_results: List of dicts, each with keys 'ticker' and 'results'
            (the dict returned by optimize_sip_dates).
    """
    if len(all_ticker_results) < 2:
        return

    print("\n" + "=" * 70)
    print("SUMMARY -- BEST SIP DATE PER TICKER")
    print("=" * 70)
    print(
        f"{'Ticker':<22} | {'Best Date':>9} | {'Best Return%':>12} | {'Best XIRR%':>10} | {'Avg XIRR%':>9}"
    )
    print("-" * 70)
    for entry in all_ticker_results:
        best = entry["results"]["top_three"][0]
        avg_xirr = entry["results"]["averages"]["xirr"]
        print(
            "{:<22} | {:>9} | {:>12.2f} | {:>10.2f} | {:>9.2f}".format(
                entry["ticker"],
                best["sip_date"],
                best["return_pct"],
                best["xirr"],
                avg_xirr,
            )
        )
    print("=" * 70)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    config = validate_config(config)

    if not config.get("sip_optimization", {}).get("enabled", False):
        raise SystemExit("sip_optimization.enabled is False; nothing to run.")

    data_source = config.get("data_source", {})
    source_type = data_source.get("type", "csv")
    backtest_cfg = config.get("backtest", {})

    # Build the list of (ticker_label, per-ticker config) pairs to iterate over.
    # For CSV mode there is a single source; for yfinance we iterate over all tickers.
    if source_type == "yfinance":
        tickers = data_source["tickers"]
    else:
        # CSV mode: single source, use the filename stem as the label.
        csv_path = data_source.get("csv_path", "data")
        tickers = [os.path.splitext(os.path.basename(csv_path))[0]]

    all_ticker_results: list[dict] = []

    # --- Stage 1: fetch / cache NAV data for all tickers ---
    print("\n=== Fetching NAV data ===")
    ticker_dfs: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        ticker_config = {**config, "data_source": {**data_source, "ticker": ticker}}
        df = load_and_process_data(ticker_config)
        df = filter_by_date_range(
            df, backtest_cfg.get("start_date"), backtest_cfg.get("end_date")
        )
        ticker_dfs[ticker] = df

    # --- Stage 2: run SIP optimization for each ticker ---
    print("\n=== Running SIP optimization ===")
    for ticker in tickers:
        print(f"\n--- Processing: {ticker} ---")
        ticker_config = {**config, "data_source": {**data_source, "ticker": ticker}}
        df = ticker_dfs[ticker]

        results = optimize_sip_dates(df, ticker_config)
        print_top_dates(results, ticker=ticker)
        save_outputs(results, ticker, config)

        all_ticker_results.append({"ticker": ticker, "results": results})

    print_summary_table(all_ticker_results)


if __name__ == "__main__":
    main()
