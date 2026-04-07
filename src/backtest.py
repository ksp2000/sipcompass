import pandas as pd
from src.finance import calculate_xirr


def simulate_sip(df: pd.DataFrame, config: dict, sip_date: int) -> dict:
    """Simulate SIP investments on a specific date of each month."""
    monthly_amount = config['sip']['monthly_amount']
    
    total_units = 0.0
    total_invested = 0.0
    cash_flows = []
    cash_dates = []
    transactions = []
    
    df = df.copy()
    df['_date'] = pd.to_datetime(df['Date'])
    df['_month_key'] = df['_date'].dt.to_period('M')

    for month_period, group in df.groupby('_month_key', sort=True):
        # First trading day on or after sip_date within this month
        on_or_after = group[group['_date'].dt.day >= sip_date]
        if not on_or_after.empty:
            row = on_or_after.iloc[0]
        else:
            # sip_date falls after the last trading day of this month —
            # use the last available trading day (backward roll)
            row = group.iloc[-1]

        date_obj = row['_date']
        price = row['Close']
        units = monthly_amount / price

        total_units += units
        total_invested += monthly_amount
        cash_flows.append(-monthly_amount)
        cash_dates.append(date_obj)

        transactions.append({
            'Date': date_obj.date().isoformat(),
            'Price': round(price, 2),
            'Amount': monthly_amount,
            'Units': round(units, 4),
            'Cumulative_Units': round(total_units, 4),
            'Cumulative_Invested': round(total_invested, 2)
        })
    
    final_price = df['Close'].iloc[-1]
    final_date = pd.to_datetime(df['Date'].iloc[-1])
    
    portfolio_value = total_units * final_price
    absolute_return = portfolio_value - total_invested
    return_pct = (absolute_return / total_invested * 100) if total_invested > 0 else 0.0
    
    # Calculate XIRR
    cash_flows.append(portfolio_value)
    cash_dates.append(final_date)
    xirr = calculate_xirr(cash_flows, cash_dates)
    
    return {
        'sip_date': sip_date,
        'total_invested': round(total_invested, 2),
        'total_units': round(total_units, 4),
        'portfolio_value': round(portfolio_value, 2),
        'absolute_return': round(absolute_return, 2),
        'return_pct': round(return_pct, 2),
        'xirr': round(xirr, 2),
        'num_transactions': len(transactions),
        'transactions': pd.DataFrame(transactions)
    }
