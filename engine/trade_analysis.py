"""
trade_analysis.py - Detailed trade frequency and theoretical profit projections
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, r"C:\Users\lumin\Desktop\strat-trading-eth")
from engine.backtester import Backtester
from engine.walk_forward import split_in_sample_out_sample
from strategies.s1_volatility_breakout import VolatilityBreakoutStrategy

df_1h = pd.read_csv(r"C:\Users\lumin\Desktop\strat-trading-eth\data\lighter_eth_1h.csv")
df_1h["timestamp"] = pd.to_datetime(df_1h["timestamp"], utc=True)
df_is, df_oos = split_in_sample_out_sample(df_1h, 0.60)

strat = VolatilityBreakoutStrategy()

# Run across slippage scenarios
scenarios = [
    ("Zero Fee Baseline (0 bps)", 0.0),
    ("Realistic Order Book (2 bps)", 2.0),
    ("Stressed Spread (5 bps)", 5.0)
]

print("=" * 80)
print("TRADE FREQUENCY & PROFIT PROJECTION REPORT")
print("=" * 80)

days = (df_oos["timestamp"].iloc[-1] - df_oos["timestamp"].iloc[0]).total_seconds() / 86400.0
print(f"Out-of-Sample Period: {df_oos['timestamp'].iloc[0].strftime('%Y-%m-%d')} to {df_oos['timestamp'].iloc[-1].strftime('%Y-%m-%d')}")
print(f"Total Duration: {days:.1f} days (~{days/30.5:.1f} months, ~{days/365.25:.2f} years)\n")

for label, slip in scenarios:
    bt = Backtester(initial_capital=10000.0, fee_rate=0.0, slippage_bps=slip, risk_per_trade=0.015)
    res = bt.run(df_oos, strat)
    trades = res["trades"]
    m = res["metrics"]
    
    total_trades = len(trades)
    trades_per_day = total_trades / days
    trades_per_week = trades_per_day * 7
    trades_per_month = trades_per_day * 30.5
    
    durations = [t["duration_bars"] for t in trades]
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    wl_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0
    avg_pnl = np.mean([t["pnl"] for t in trades])
    net_profit = sum([t["pnl"] for t in trades])
    
    # Monthly profit estimate on $10k
    monthly_ret_pct = ((1.0 + m["cumulative_return_pct"]/100.0) ** (1.0 / (days/30.5)) - 1.0) * 100.0
    
    print(f"--- Scenario: {label} ---")
    print(f"  Total Trades        : {total_trades}")
    print(f"  Frequency (Day)     : {trades_per_day:.2f} trades/day (approx 1 trade every {1.0/trades_per_day:.1f} days)")
    print(f"  Frequency (Week)    : {trades_per_week:.1f} trades/week")
    print(f"  Frequency (Month)   : {trades_per_month:.1f} trades/month")
    print(f"  Avg Holding Time    : {np.mean(durations):.1f} hours (~{np.mean(durations)/24:.1f} days)")
    print(f"  Median Holding Time : {np.median(durations):.1f} hours")
    print(f"  Win Rate            : {m['win_rate']:.1f}%")
    print(f"  Avg Win             : +${avg_win:.2f} | Avg Loss: -${avg_loss:.2f} (Payoff Ratio: {wl_ratio:.2f})")
    print(f"  Expectancy / Trade  : +${avg_pnl:.2f}")
    print(f"  Net Profit ($10k cap): +${net_profit:.2f} (+{m['cumulative_return_pct']:.1f}%)")
    print(f"  Monthly Return (CAGR): ~{monthly_ret_pct:.2f}% per month")
    print(f"  Annualized CAGR     : {m['cagr_pct']:.1f}%")
    print(f"  Max Drawdown        : {m['max_drawdown_pct']:.1f}%")
    print(f"  Sharpe Ratio        : {m['sharpe_ratio']:.2f}")
    print()
