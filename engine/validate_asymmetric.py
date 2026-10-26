"""
validate_asymmetric.py - Rigorous out-of-sample and walk-forward verification of Asymmetric Breakout
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, r"C:\Users\lumin\Desktop\strat-trading-eth")
from engine.backtester import Backtester
from engine.walk_forward import split_in_sample_out_sample, run_walk_forward
from engine.research_trials import AsymmetricBreakoutStrategy

df = pd.read_csv(r"C:\Users\lumin\Desktop\strat-trading-eth\data\lighter_eth_1h.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df_is, df_oos = split_in_sample_out_sample(df, 0.60)
strat = AsymmetricBreakoutStrategy()

bt_is = Backtester(200.0, 0.0, 2.0, 0.015, 2.5)
m_is = bt_is.run(df_is, strat)["metrics"]

bt_0 = Backtester(200.0, 0.0, 0.0, 0.015, 2.5)
m_0 = bt_0.run(df_oos, strat)["metrics"]

bt_2 = Backtester(200.0, 0.0, 2.0, 0.015, 2.5)
m_2 = bt_2.run(df_oos, strat)["metrics"]

bt_5 = Backtester(200.0, 0.0, 5.0, 0.015, 2.5)
m_5 = bt_5.run(df_oos, strat)["metrics"]

print("=" * 80)
print("ASYMMETRIC LONG/SHORT BREAKOUT: RIGOROUS MULTI-PERIOD VERIFICATION")
print("=" * 80)
print(f"In-Sample Return (Train)   : +{m_is['cumulative_return_pct']:.1f}% | Sharpe: {m_is['sharpe_ratio']:.2f} | MaxDD: {m_is['max_drawdown_pct']:.1f}%")
print(f"OOS 0 bps (Lighter baseline): +{m_0['cumulative_return_pct']:.1f}% | Sharpe: {m_0['sharpe_ratio']:.2f} | MaxDD: {m_0['max_drawdown_pct']:.1f}% | Final: ${m_0['ending_capital']:.2f}")
print(f"OOS 2 bps (Realistic spread): +{m_2['cumulative_return_pct']:.1f}% | Sharpe: {m_2['sharpe_ratio']:.2f} | MaxDD: {m_2['max_drawdown_pct']:.1f}% | Final: ${m_2['ending_capital']:.2f}")
print(f"OOS 5 bps (Stressed spread) : +{m_5['cumulative_return_pct']:.1f}% | Sharpe: {m_5['sharpe_ratio']:.2f} | MaxDD: {m_5['max_drawdown_pct']:.1f}% | Final: ${m_5['ending_capital']:.2f}")

wf = run_walk_forward(df, AsymmetricBreakoutStrategy, {}, 4320, 1440, {"slippage_bps": 2.0})
print(f"Walk-Forward Consistency   : {wf['profitable_folds']}/{wf['total_folds']} ({wf['consistency_rate']:.1f}%) | Avg OOS Sharpe: {wf['avg_oos_sharpe']:.2f} | Avg OOS Return: +{wf['avg_oos_return_pct']:.1f}%")

print("\nWalk-Forward Folds Breakdown:")
for idx, row in wf["folds"].iterrows():
    print(f"  Fold {row['fold_idx']}: {row['test_start'].strftime('%Y-%m')} to {row['test_end'].strftime('%Y-%m')} | OOS Return: {row['oos_return_pct']:>6.1f}% | Sharpe: {row['oos_sharpe']:>5.2f} | WinRate: {row['oos_win_rate']:>4.1f}% | MaxDD: {row['oos_max_dd_pct']:>5.1f}%")
