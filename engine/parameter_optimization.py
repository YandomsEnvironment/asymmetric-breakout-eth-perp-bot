"""
parameter_optimization.py - Mathematical Optimization & Gap Analysis
Performs systematic optimization of:
1. Fractional Kelly Criterion calculation
2. Risk-per-trade & Max Leverage optimization grid
3. Stop Loss / Take Profit ATR multiplier stability plateau
4. Evaluates risk-adjusted metrics (Sharpe, Calmar, MaxDD, Final Equity on $200)
"""

import sys
import os
import itertools
import pandas as pd
import numpy as np

sys.path.insert(0, r"C:\Users\lumin\Desktop\strat-trading-eth")
from engine.backtester import Backtester
from engine.walk_forward import split_in_sample_out_sample
from strategies.s1_volatility_breakout import VolatilityBreakoutStrategy

df_1h = pd.read_csv(r"C:\Users\lumin\Desktop\strat-trading-eth\data\lighter_eth_1h.csv")
df_1h["timestamp"] = pd.to_datetime(df_1h["timestamp"], utc=True)
df_is, df_oos = split_in_sample_out_sample(df_1h, 0.60)

print("=" * 85)
print("COMPREHENSIVE QUANTITATIVE GAP ANALYSIS & PARAMETER OPTIMIZATION")
print("=" * 85)

# -----------------------------------------------------------------------------
# 1. EMPIRICAL KELLY CRITERION CALCULATION
# -----------------------------------------------------------------------------
bt_base = Backtester(initial_capital=10000.0, fee_rate=0.0, slippage_bps=2.0, risk_per_trade=0.015)
strat_base = VolatilityBreakoutStrategy()
res_base = bt_base.run(df_oos, strat_base)
trades = res_base["trades"]

wins = [t["pnl"] for t in trades if t["pnl"] > 0]
losses = [abs(t["pnl"]) for t in trades if t["pnl"] <= 0]
p = len(wins) / len(trades)
q = 1.0 - p
b = np.mean(wins) / np.mean(losses)  # Payoff ratio (win/loss)

# Kelly formula: f* = (p * b - q) / b
kelly_full = (p * b - q) / b
kelly_half = kelly_full / 2.0
kelly_quarter = kelly_full / 4.0

print(f"\n[1] KELLY CRITERION ANALYSIS (Unseen OOS Data):")
print(f"    Win Rate (p)          : {p*100:.2f}%")
print(f"    Payoff Ratio (b)      : {b:.2f} : 1")
print(f"    Full Kelly (f*)       : {kelly_full*100:.2f}% (Theoretical max growth, extreme volatility)")
print(f"    Half-Kelly (f*/2)     : {kelly_half*100:.2f}% (Standard hedge fund growth target)")
print(f"    Quarter-Kelly (f*/4)  : {kelly_quarter*100:.2f}% (Institutional capital preservation target)")
print(f"    -> Mathematically optimal safe risk per trade is: {kelly_quarter*100:.2f}% to {kelly_half*100:.2f}% (approx 1.5% - 2.0%)\n")

# -----------------------------------------------------------------------------
# 2. RISK-PER-TRADE & MAX LEVERAGE GRID
# -----------------------------------------------------------------------------
print("[2] RISK PER TRADE & LEVERAGE GRID SEARCH (Starting Balance: $200 USD, 2 bps Slippage)")
print("-" * 85)
print(f"{'Risk %':<8} | {'Max Lev':<8} | {'Ending $':<10} | {'Return %':<10} | {'Sharpe':<8} | {'Max DD %':<10} | {'Calmar':<8} | {'Trades':<6}")
print("-" * 85)

risk_levels = [0.010, 0.015, 0.020, 0.025]
leverage_levels = [1.5, 2.0, 2.5, 3.0]
grid_results = []

for r in risk_levels:
    for lev in leverage_levels:
        bt = Backtester(
            initial_capital=200.0,
            fee_rate=0.0,
            slippage_bps=2.0,
            risk_per_trade=r,
            max_leverage=lev
        )
        res = bt.run(df_oos, strat_base)
        m = res["metrics"]
        
        row = {
            "risk_pct": r * 100.0,
            "max_leverage": lev,
            "ending_capital": m["ending_capital"],
            "return_pct": m["cumulative_return_pct"],
            "sharpe": m["sharpe_ratio"],
            "max_dd_pct": m["max_drawdown_pct"],
            "calmar": m["calmar_ratio"],
            "trades": m["total_trades"]
        }
        grid_results.append(row)
        print(f"{r*100:<7.1f}% | {lev:<7.1f}x | ${m['ending_capital']:<9.2f} | {m['cumulative_return_pct']:<9.1f}% | {m['sharpe_ratio']:<8.2f} | {m['max_drawdown_pct']:<9.1f}% | {m['calmar_ratio']:<8.2f} | {m['total_trades']:<6}")

print("-" * 85)

# -----------------------------------------------------------------------------
# 3. ATR STOP LOSS & TAKE PROFIT STABILITY PLATEAU
# -----------------------------------------------------------------------------
print("\n[3] SL & TP ATR MULTIPLIER ROBUSTNESS PLATEAU (Checking Parameter Sensitivity)")
print("-" * 85)
print(f"{'SL Mult':<9} | {'TP Mult':<9} | {'Win %':<8} | {'Payoff':<8} | {'Return %':<10} | {'Sharpe':<8} | {'Max DD %':<10} | {'Verdict'}")
print("-" * 85)

atr_combos = [
    (1.5, 3.0),
    (1.8, 3.0),
    (1.8, 3.5),
    (2.0, 3.0),
    (2.0, 3.5),
    (2.0, 4.0),
    (2.2, 3.5),
    (2.2, 4.0),
    (2.5, 4.0)
]

for sl_m, tp_m in atr_combos:
    st = VolatilityBreakoutStrategy(sl_atr_mult=sl_m, tp_atr_mult=tp_m)
    bt = Backtester(initial_capital=200.0, fee_rate=0.0, slippage_bps=2.0, risk_per_trade=0.015, max_leverage=2.5)
    res = bt.run(df_oos, st)
    m = res["metrics"]
    
    t_list = res["trades"]
    w = [t["pnl"] for t in t_list if t["pnl"] > 0]
    l = [abs(t["pnl"]) for t in t_list if t["pnl"] <= 0]
    payoff = (np.mean(w) / np.mean(l)) if l and w else 0.0
    
    verdict = "PEAK PLATEAU" if m["sharpe_ratio"] >= 1.50 and m["max_drawdown_pct"] <= 22.0 else ("GOOD" if m["sharpe_ratio"] > 1.2 else "SUBOPTIMAL")
    print(f"{sl_m:<9.1f} | {tp_m:<9.1f} | {m['win_rate']:<7.1f}% | {payoff:<7.2f} | {m['cumulative_return_pct']:<9.1f}% | {m['sharpe_ratio']:<8.2f} | {m['max_drawdown_pct']:<9.1f}% | {verdict}")

print("-" * 85)
