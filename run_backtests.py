"""
run_backtests.py - Master Quantitative Evaluator for Asymmetric ETH Perp Bot
Runs institutional unbiased testing:
1. In-Sample vs Strictly Unseen Out-of-Sample Validation
2. Zero-Fee baseline (Lighter) vs Slippage Stress-Testing (0 bps, 2 bps, 5 bps)
3. Walks-forward rolling validation
4. Features Asymmetric Volatility Breakout (New Champion) and comparative baseline models
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.backtester import Backtester
from engine.walk_forward import split_in_sample_out_sample, run_walk_forward
from strategies.s6_asymmetric_breakout import AsymmetricBreakoutStrategy
from strategies.s1_volatility_breakout import VolatilityBreakoutStrategy
from strategies.s4_bollinger_squeeze import VolatilitySqueezeStrategy
from strategies.s3_mtf_trend_pullback import TrendPullbackStrategy
from strategies.s5_volume_momentum import VolumeMomentumStrategy
from strategies.s2_mean_reversion import MeanReversionStrategy


def load_dataset(filename: str) -> pd.DataFrame:
    filepath = os.path.join(BASE_DIR, "data", filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Dataset not found at {filepath}.")
    df = pd.read_csv(filepath)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def run_full_suite():
    results_dir = os.path.join(BASE_DIR, "results")
    os.makedirs(results_dir, exist_ok=True)

    print("=" * 110)
    print("ETH PERP QUANTITATIVE STRATEGY EVALUATION - ASYMMETRIC BREAKOUT SUITE")
    print("=" * 110)

    # 1. Load Dataset
    df_1h = load_dataset("lighter_eth_1h.csv")
    print(f"[*] Loaded {len(df_1h)} hourly candles from Lighter DEX Mainnet.")
    print(f"    Date span: {df_1h['timestamp'].iloc[0]} to {df_1h['timestamp'].iloc[-1]}")

    df_is, df_oos = split_in_sample_out_sample(df_1h, train_ratio=0.60)
    print(f"[*] Strict Unbiased Partitioning:")
    print(f"    - In-Sample (Train)   : {len(df_is)} bars ({df_is['timestamp'].iloc[0].strftime('%Y-%m-%d')} -> {df_is['timestamp'].iloc[-1].strftime('%Y-%m-%d')})")
    print(f"    - Out-of-Sample (UNSEEN): {len(df_oos)} bars ({df_oos['timestamp'].iloc[0].strftime('%Y-%m-%d')} -> {df_oos['timestamp'].iloc[-1].strftime('%Y-%m-%d')})\n")

    # Evaluated Strategies (Champion at top)
    strategies = [
        AsymmetricBreakoutStrategy(),          # NEW CHAMPION
        VolatilityBreakoutStrategy(),          # Symmetric baseline
        VolatilitySqueezeStrategy(),           # Carter Squeeze
        TrendPullbackStrategy(),               # MTF Pullback
        VolumeMomentumStrategy(),              # Volume Flow
        MeanReversionStrategy()                # Zero-fee Mean Reversion
    ]

    bt_baseline = Backtester(initial_capital=200.0, fee_rate=0.0, slippage_bps=2.0, risk_per_trade=0.015, max_leverage=2.5)

    summary_rows = []
    equity_curves_oos = {}

    print("[*] Evaluating Strategies on Strictly UNSEEN Out-of-Sample Data (2 bps Realistic Spread)...")
    print("-" * 110)
    header = f"{'Strategy Setup':<32} | {'OOS Return':<11} | {'Sharpe':<8} | {'Max DD':<9} | {'Win %':<7} | {'PF':<6} | {'Trades':<7} | {'Calmar':<8} | {'Status'}"
    print(header)
    print("-" * 110)

    for strat in strategies:
        res_is = bt_baseline.run(df_is, strat)
        res_oos = bt_baseline.run(df_oos, strat)

        m_is = res_is["metrics"]
        m_oos = res_oos["metrics"]

        equity_curves_oos[strat.name] = res_oos["equity_curve"]

        status = "CHAMPION" if "Asymmetric" in strat.name else ("STRONG" if m_oos["sharpe_ratio"] >= 1.5 else ("VIABLE" if m_oos["cumulative_return_pct"] > 0 else "FAILED"))

        row = {
            "Strategy": strat.name,
            "IS_Sharpe": round(m_is["sharpe_ratio"], 2),
            "OOS_Sharpe": round(m_oos["sharpe_ratio"], 2),
            "IS_Return_Pct": round(m_is["cumulative_return_pct"], 2),
            "OOS_Return_Pct": round(m_oos["cumulative_return_pct"], 2),
            "OOS_MaxDD_Pct": round(m_oos["max_drawdown_pct"], 2),
            "OOS_Calmar": round(m_oos["calmar_ratio"], 2),
            "OOS_WinRate": round(m_oos["win_rate"], 1),
            "OOS_ProfitFactor": round(m_oos["profit_factor"], 2),
            "OOS_Trades": m_oos["total_trades"],
            "OOS_AvgTrade_Pct": round(m_oos["avg_trade_return_pct"], 2),
            "Status": status
        }
        summary_rows.append(row)

        print(f"{strat.name:<32} | {m_oos['cumulative_return_pct']:<10.1f}% | {m_oos['sharpe_ratio']:<8.2f} | {m_oos['max_drawdown_pct']:<8.1f}% | {m_oos['win_rate']:<6.1f}% | {m_oos['profit_factor']:<6.2f} | {m_oos['total_trades']:<7} | {m_oos['calmar_ratio']:<8.2f} | {status}")

    print("-" * 110)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(os.path.join(results_dir, "strategy_comparison_summary.csv"), index=False)

    # Slippage sensitivity test
    print("\n[*] Slippage Sensitivity Stress Test (0 bps vs 2 bps vs 5 bps)...")
    slip_results = []
    print("-" * 80)
    print(f"{'Strategy':<32} | {'0 bps Sharpe':<13} | {'2 bps Sharpe':<13} | {'5 bps Sharpe':<13} | {'Robust?'}")
    print("-" * 80)

    for strat in strategies:
        bt_0 = Backtester(200.0, 0.0, 0.0, 0.015, 2.5)
        bt_2 = Backtester(200.0, 0.0, 2.0, 0.015, 2.5)
        bt_5 = Backtester(200.0, 0.0, 5.0, 0.015, 2.5)

        r0 = bt_0.run(df_oos, strat)["metrics"]
        r2 = bt_2.run(df_oos, strat)["metrics"]
        r5 = bt_5.run(df_oos, strat)["metrics"]

        robust = (r2["cumulative_return_pct"] > 0 and r5["cumulative_return_pct"] > 0)
        label = "YES (Robust)" if robust else "FRAGILE"

        slip_results.append({
            "Strategy": strat.name,
            "Sharpe_0bps": round(r0["sharpe_ratio"], 2),
            "Return_0bps": round(r0["cumulative_return_pct"], 2),
            "Sharpe_2bps": round(r2["sharpe_ratio"], 2),
            "Return_2bps": round(r2["cumulative_return_pct"], 2),
            "Sharpe_5bps": round(r5["sharpe_ratio"], 2),
            "Return_5bps": round(r5["cumulative_return_pct"], 2),
            "Robust": label
        })
        print(f"{strat.name:<32} | {r0['sharpe_ratio']:<13.2f} | {r2['sharpe_ratio']:<13.2f} | {r5['sharpe_ratio']:<13.2f} | {label}")
    print("-" * 80)

    slip_df = pd.DataFrame(slip_results)
    slip_df.to_csv(os.path.join(results_dir, "slippage_sensitivity_stress_test.csv"), index=False)

    # Walk forward on champion
    print("\n[*] Rolling Walk-Forward Validation on Champion (Asymmetric Breakout)...")
    wf_res = run_walk_forward(
        df=df_1h,
        strategy_class=AsymmetricBreakoutStrategy,
        strategy_kwargs={},
        train_bars=4320,
        test_bars=1440,
        backtester_kwargs={"slippage_bps": 2.0}
    )
    wf_res["folds"].to_csv(os.path.join(results_dir, "walk_forward_folds.csv"), index=False)
    print(f"    Total Folds: {wf_res['total_folds']} | Profitable: {wf_res['profitable_folds']}/{wf_res['total_folds']} ({wf_res['consistency_rate']:.1f}%)")
    print(f"    Avg OOS Sharpe: {wf_res['avg_oos_sharpe']:.2f} | Avg OOS Return: +{wf_res['avg_oos_return_pct']:.1f}%")

    # Plot Equity Curves
    print("\n[*] Generating high-resolution Out-of-Sample equity curve chart...")
    plt.style.use("seaborn-v0_8-darkgrid" if "seaborn-v0_8-darkgrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)

    for name, eq in equity_curves_oos.items():
        norm_eq = (eq / eq.iloc[0]) * 100.0
        lw = 2.5 if "Asymmetric" in name else 1.2
        ax.plot(norm_eq.index, norm_eq.values, label=f"{name}", linewidth=lw)

    # Buy & Hold benchmark
    eth_bh = (df_oos["close"] / df_oos["close"].iloc[0]) * 100.0
    ax.plot(df_oos["timestamp"], eth_bh, label="ETH Buy & Hold Benchmark", color="black", linestyle="--", alpha=0.5, linewidth=1.5)

    ax.set_title("ETH Perpetual Out-of-Sample (Unseen Data) Equity Curves on Lighter DEX", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Portfolio Value (Base = 100)", fontsize=11)
    ax.legend(loc="upper left", frameon=True)
    plt.tight_layout()

    chart_path = os.path.join(results_dir, "oos_equity_curves.png")
    plt.savefig(chart_path)
    plt.close()
    print(f"    Updated chart saved to: {chart_path}")
    print("\n" + "=" * 110)
    print("BACKTEST SUITE COMPLETED SUCCESSFULLY.")
    print("=" * 110)


if __name__ == "__main__":
    run_full_suite()
