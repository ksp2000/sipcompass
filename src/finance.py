import pandas as pd
from scipy import optimize


def calculate_xirr(cash_flows, dates):
    """
    Calculate XIRR (Extended Internal Rate of Return) for irregular cash flows.
    Returns percentage (annualized).
    """
    if len(cash_flows) != len(dates) or len(cash_flows) == 0:
        return 0.0
    
    dates = pd.to_datetime(dates)
    days = (dates - dates[0]).days.values
    
    def npv(rate):
        return sum(cf / ((1 + rate) ** (d / 365.0)) for cf, d in zip(cash_flows, days))

    try:
        result = optimize.newton(npv, 0.1)
        return result * 100
    except Exception:
        try:
            result = optimize.brentq(npv, -0.99, 10)
            return result * 100
        except Exception:
            return 0.0
