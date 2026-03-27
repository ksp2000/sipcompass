from statistics import mean
from typing import Iterable

from src.backtest import simulate_sip


def optimize_sip_dates(df, config) -> dict:
    """Test different SIP dates (1-28) and rank by XIRR."""
    sip_cfg = config.get('sip_optimization', {})
    analyze_dates: Iterable[int] = sip_cfg.get('analyze_dates') or range(1, 29)
    analyze_dates = [int(d) for d in analyze_dates if 1 <= int(d) <= 28]
    if not analyze_dates:
        raise ValueError("No valid SIP dates to analyze. Provide values between 1 and 28.")

    per_date_results = []
    for sip_date in analyze_dates:
        result = simulate_sip(df, config, sip_date)
        per_date_results.append(result)

    avg_return = mean(r['return_pct'] for r in per_date_results)
    avg_xirr = mean(r['xirr'] for r in per_date_results)

    # Rank by XIRR (primary) and return_pct (secondary)
    ranked = sorted(per_date_results, key=lambda r: (r['xirr'], r['return_pct']), reverse=True)
    for r in ranked:
        r['delta_vs_avg_return'] = round(r['return_pct'] - avg_return, 2)
        r['delta_vs_avg_xirr'] = round(r['xirr'] - avg_xirr, 2)

    top_three = ranked[:3]

    return {
        'averages': {
            'return_pct': round(avg_return, 2),
            'xirr': round(avg_xirr, 2),
        },
        'per_date': ranked,
        'top_three': top_three,
    }
