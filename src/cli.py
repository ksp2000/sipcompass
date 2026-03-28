import argparse
import os
from pathlib import Path

import pandas as pd
import yaml
from rich.console import Console
from rich.table import Table

from src.data_loader import filter_by_date_range, load_and_process_data, validate_config
from src.optimizer import optimize_sip_dates

console = Console()
DEFAULT_CONFIG_PATH = "config.yaml"
EXAMPLE_CONFIG_PATH = "config.example.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SIPCompass - backtest the best monthly SIP dates."
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to configuration YAML")
    parser.add_argument(
        "--start-date",
        help="Override backtest.start_date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        help="Override backtest.end_date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        dest="tickers",
        help="Yahoo Finance ticker to analyze. Repeat for multiple tickers.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        help="Number of top-ranked SIP dates to display.",
    )
    parser.add_argument(
        "--amount",
        type=float,
        help="Override sip.monthly_amount.",
    )
    return parser.parse_args()


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        example_hint = ""
        if path == DEFAULT_CONFIG_PATH and os.path.exists(EXAMPLE_CONFIG_PATH):
            example_hint = (
                f" Copy '{EXAMPLE_CONFIG_PATH}' to '{DEFAULT_CONFIG_PATH}' and edit it to your needs."
            )
        raise FileNotFoundError(f"Config file not found: {path}.{example_hint}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def apply_cli_overrides(config: dict, args: argparse.Namespace) -> dict:
    """Apply CLI-provided config overrides on top of the loaded YAML config."""
    config.setdefault("backtest", {})
    config.setdefault("sip", {})
    config.setdefault("sip_optimization", {})
    config.setdefault("data_source", {})

    if args.start_date:
        config["backtest"]["start_date"] = args.start_date
    if args.end_date:
        config["backtest"]["end_date"] = args.end_date
    if args.amount is not None:
        config["sip"]["monthly_amount"] = args.amount
    if args.top_n is not None:
        config["sip_optimization"]["top_n"] = args.top_n
    if args.tickers:
        config["data_source"]["type"] = "yfinance"
        config["data_source"]["tickers"] = args.tickers

    return config


def _output_stem(ticker: str, config: dict) -> str:
    """Build a filename stem from a ticker symbol and the backtest date range."""
    identifier = ticker.replace("/", "_").replace("\\", "_")
    bt = config.get("backtest", {})
    start = (bt.get("start_date") or "start").replace("-", "")
    end = (bt.get("end_date") or "end").replace("-", "")
    return f"{identifier}_{start}_{end}"


def save_outputs(results: dict, ticker: str, config: dict) -> None:
    """Write all-dates SIP results to a CSV file in data/output/."""
    out_dir = os.path.join("data", "output")
    os.makedirs(out_dir, exist_ok=True)
    stem = _output_stem(ticker, config)

    results_path = os.path.join(out_dir, f"{stem}_sip_results.csv")
    pd.DataFrame(results["per_date"]).to_csv(results_path, index=False)
    console.print(f"[green]✓[/green] SIP results written to [dim]{results_path}[/dim]")


def print_top_dates(results: dict, ticker: str = "") -> None:
    """Print per-ticker SIP optimization results with the configured top dates."""
    averages = results["averages"]
    title = (
        f"SIP DATE OPTIMIZATION RESULTS — {ticker}"
        if ticker
        else "SIP DATE OPTIMIZATION RESULTS"
    )
    console.rule(f"[bold cyan]{title}[/bold cyan]")

    console.print("[bold]Averages across all dates:[/bold]")
    console.print(f"  Return: [yellow]{averages['return_pct']:.2f}%[/yellow]")
    console.print(f"  XIRR:   [yellow]{averages['xirr']:.2f}%[/yellow]")

    top_n = results.get("top_n", len(results["top_three"]))
    console.print(f"\n[bold]Top {top_n} SIP dates[/bold] [dim](ranked by XIRR, then return %)[/dim]")
    table = Table(show_header=True, header_style="bold magenta", show_lines=False)
    table.add_column("SIP Date", justify="right", style="bold")
    table.add_column("Return %", justify="right")
    table.add_column("XIRR %", justify="right")
    table.add_column("vs Avg Return", justify="right")
    table.add_column("vs Avg XIRR", justify="right")

    for entry in results["top_three"]:
        delta_return = entry["delta_vs_avg_return"]
        delta_xirr = entry["delta_vs_avg_xirr"]
        dr_style = "green" if delta_return >= 0 else "red"
        dx_style = "green" if delta_xirr >= 0 else "red"
        table.add_row(
            str(entry["sip_date"]),
            f"{entry['return_pct']:.2f}%",
            f"[bold]{entry['xirr']:.2f}%[/bold]",
            f"[{dr_style}]{delta_return:+.2f}%[/{dr_style}]",
            f"[{dx_style}]{delta_xirr:+.2f}%[/{dx_style}]",
        )
    console.print(table)


def print_summary_table(all_ticker_results: list[dict]) -> None:
    """Print a one-row-per-ticker summary of the best SIP date for each ticker."""
    if len(all_ticker_results) < 2:
        return

    console.rule("[bold cyan]SUMMARY — BEST SIP DATE PER TICKER[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta", show_lines=False)
    table.add_column("Ticker", style="bold")
    table.add_column("Best Date", justify="right")
    table.add_column("Best Return %", justify="right")
    table.add_column("Best XIRR %", justify="right")
    table.add_column("Avg XIRR %", justify="right")

    for entry in all_ticker_results:
        best = entry["results"]["top_three"][0]
        avg_xirr = entry["results"]["averages"]["xirr"]
        table.add_row(
            entry["ticker"],
            str(best["sip_date"]),
            f"{best['return_pct']:.2f}%",
            f"[bold]{best['xirr']:.2f}%[/bold]",
            f"{avg_xirr:.2f}%",
        )
    console.print(table)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    config = apply_cli_overrides(config, args)
    config = validate_config(config)

    console.print("[bold green]SIPCompass[/bold green] [dim]- SIP date backtesting for funds and ETFs[/dim]")
    console.print(f"[dim]Using config:[/dim] {Path(args.config)}")

    if not config.get("sip_optimization", {}).get("enabled", False):
        raise SystemExit("sip_optimization.enabled is False; nothing to run.")

    data_source = config.get("data_source", {})
    source_type = data_source.get("type", "csv")
    backtest_cfg = config.get("backtest", {})

    if source_type == "yfinance":
        tickers = data_source["tickers"]
    else:
        csv_path = data_source.get("csv_path", "data")
        tickers = [os.path.splitext(os.path.basename(csv_path))[0]]

    all_ticker_results: list[dict] = []

    console.rule("[bold blue]Fetching NAV data[/bold blue]")
    ticker_dfs: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        ticker_config = {**config, "data_source": {**data_source, "ticker": ticker}}
        df = load_and_process_data(ticker_config)
        df = filter_by_date_range(
            df, backtest_cfg.get("start_date"), backtest_cfg.get("end_date")
        )
        ticker_dfs[ticker] = df

    console.rule("[bold blue]Running SIP optimization[/bold blue]")
    for ticker in tickers:
        console.print(f"\n[bold cyan]Processing:[/bold cyan] {ticker}")
        ticker_config = {**config, "data_source": {**data_source, "ticker": ticker}}
        df = ticker_dfs[ticker]

        results = optimize_sip_dates(df, ticker_config)
        print_top_dates(results, ticker=ticker)
        save_outputs(results, ticker, config)

        all_ticker_results.append({"ticker": ticker, "results": results})

    print_summary_table(all_ticker_results)
