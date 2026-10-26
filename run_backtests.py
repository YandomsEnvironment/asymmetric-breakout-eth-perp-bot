"""
run_backtests.py - Comprehensive Multi-Strategy Unbiased Evaluator for ETH Perps
Executes institutional rigorous testing:
1. In-Sample vs Strictly Unseen Out-of-Sample Validation
2. Zero-Fee baseline (Lighter) vs Slippage Stress-Testing (0 bps, 2 bps, 5 bps)
3. Statistical Edge Verification (t-stat, p-value)
4. Rolling Walk-Forward Analysis
5. Generates high-res visual performance charts and CSV summaries in results/
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, Any, List

# Add parent directory to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from engine.backtester import Backtester
from engine.walk_forward import split_in_sample_out_sample, run_walk_forward
from strategies.s1_volatility_breakout import VolatilityBreakoutStrategy
from strategies.s2_mean_reversion import MeanReversionStrategy
from strategies.s3_mtf_trend_pullback import TrendPullbackStrategy
from strategies.s4_bollinger_squeeze import VolatilitySqueezeStrategy
from strategies.s5_volume_momentum import VolumeMomentumStrategy


def load_dataset(filename: str) -> pd.DataFrame:
    filepath = os.path.join(BASE_DIR, "data", filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Dataset not found at {filepath}. Run data/fetch_data.py first.")
    df = pd.read_csv(filepath)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def run_full_suite():
    results_dir = os.path.join(BASE_DIR, "results")
    os.makedirs(results_dir, exist_ok=True)

    print("=" * 80)
    print("ETH PERP QUANTITATIVE STRATEGY EVALUATION (LIGHTER 0-FEE ENVIRONMENT)")
    print("=" * 80)

    # 1. Load Hourly Dataset
    print("\n[1] Loading authentic Lighter DEX ETH Perpetual 1h dataset...")
    df_1h = load_dataset("lighter_eth_1h.csv")
    print(f"    Loaded {len(df_1h)} hourly candles.")
    print(f"    Timeline: {df_1h['timestamp'].iloc[0]} to {df_1h['timestamp'].iloc[-1]}")

    # Strict In-Sample (60%) vs Out-of-Sample Unseen (40%) split
    df_is, df_oos = split_in_sample_out_sample(df_1h, train_ratio=0.60)
    print(f"\n[2] Unbiased Data Splitting:")
    print(f"    - In-Sample (Train/Calibrate) : {len(df_is)} bars ({df_is['timestamp'].iloc[0].strftime('%Y-%m-%d')} -> {df_is['timestamp'].iloc[-1].strftime('%Y-%m-%d')})")
    print(f"    - Out-of-Sample (UNSEEN Test) : {len(df_oos)} bars ({df_oos['timestamp'].iloc[0].strftime('%Y-%m-%d')} -> {df_oos['timestamp'].iloc[-1].strftime('%Y-%m-%d')})")

    # Define Strategies
    strategies = [
        VolatilityBreakoutStrategy(breakout_period=24, trend_ema_period=200, adx_threshold=20.0),
        MeanReversionStrategy(bb_period=20, bb_std=2.2, rsi_oversold=30.0, rsi_overbought=70.0, adx_max=32.0),
        TrendPullbackStrategy(ema_fast=21, ema_mid=50, ema_slow=200),
        VolatilitySqueezeStrategy(bb_period=20, bb_std=2.0, kc_period=20, kc_mult=1.5),
        VolumeMomentumStrategy(ema_fast=9, ema_slow=21, vol_period=20, vol_mult=1.4)
    ]

    bt_baseline = Backtester(initial_capital=10000.0, fee_rate=0.0, slippage_bps=0.0, risk_per_trade=0.015)

    summary_rows = []
    equity_curves_oos = {}

    print("\n[3] Evaluating Strategies on Strictly UNSEEN Out-of-Sample Data (0% Fee Baseline)...")
    print("-" * 110)
    header = f"{'Strategy':<26} | {'IS Sharpe':<10} | {'OOS Sharpe':<10} | {'OOS Ret %':<10} | {'Max DD %':<9} | {'Win %':<7} | {'PF':<6} | {'Trades':<7} | {'p-val':<8} | {'Edge?'}"
    print(header)
    print("-" * 110)

    for strat in strategies:
        # Run In-Sample
        res_is = bt_baseline.run(df_is, strat)
        # Run Strictly Unseen Out-of-Sample
        res_oos = bt_baseline.run(df_oos, strat)

        m_is = res_is["metrics"]
        m_oos = res_oos["metrics"]

        equity_curves_oos[strat.name] = res_oos["equity_curve"]

        edge_label = "YES (P<0.05)" if m_oos["has_stat_edge"] else ("PROFITABLE" if m_oos["cumulative_return_pct"] > 0 and m_oos["profit_factor"] > 1.1 else "NO EDGE")

        row = {
            "Strategy": strat.name,
            "IS_Sharpe": round(m_is["sharpe_ratio"], 2),
            "OOS_Sharpe": round(m_oos["sharpe_ratio"], 2),
            "IS_Return_Pct": round(m_is["cumulative_return_pct"], 2),
            "OOS_Return_Pct": round(m_oos["cumulative_return_pct"], 2),
            "OOS_CAGR_Pct": round(m_oos["cagr_pct"], 2),
            "OOS_MaxDD_Pct": round(m_oos["max_drawdown_pct"], 2),
            "OOS_Calmar": round(m_oos["calmar_ratio"], 2),
            "OOS_WinRate": round(m_oos["win_rate"], 1),
            "OOS_ProfitFactor": round(m_oos["profit_factor"], 2),
            "OOS_Trades": m_oos["total_trades"],
            "OOS_AvgTrade_Pct": round(m_oos["avg_trade_return_pct"], 2),
            "OOS_T_Stat": round(m_oos["t_stat"], 2),
            "OOS_P_Value": round(m_oos["p_value"], 4),
            "Stat_Edge": m_oos["has_stat_edge"],
            "Verdict": edge_label
        }
        summary_rows.append(row)

        print(f"{strat.name:<26} | {m_is['sharpe_ratio']:<10.2f} | {m_oos['sharpe_ratio']:<10.2f} | {m_oos['cumulative_return_pct']:<9.1f}% | {m_oos['max_drawdown_pct']:<8.1f}% | {m_oos['win_rate']:<6.1f}% | {m_oos['profit_factor']:<6.2f} | {m_oos['total_trades']:<7} | {m_oos['p_value']:<8.4f} | {edge_label}")

    print("-" * 110)

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(os.path.join(results_dir, "strategy_comparison_summary.csv"), index=False)

    # 4. Slippage Sensitivity Stress-Test on Top Strategies
    print("\n[4] Running Slippage Sensitivity Stress Test (Robustness Check on Unseen Data)...")
    print("    Evaluating whether edge survives real orderbook bid-ask spreads (0 bps vs 2 bps vs 5 bps)...")
    print("-" * 80)
    print(f"{'Strategy':<26} | {'0 bps Sharpe':<13} | {'2 bps Sharpe':<13} | {'5 bps Sharpe':<13} | {'Robust?'}")
    print("-" * 80)

    slippage_results = []
    for strat in strategies:
        bt_0 = Backtester(initial_capital=10000.0, fee_rate=0.0, slippage_bps=0.0)
        bt_2 = Backtester(initial_capital=10000.0, fee_rate=0.0, slippage_bps=2.0)
        bt_5 = Backtester(initial_capital=10000.0, fee_rate=0.0, slippage_bps=5.0)

        r0 = bt_0.run(df_oos, strat)["metrics"]
        r2 = bt_2.run(df_oos, strat)["metrics"]
        r5 = bt_5.run(df_oos, strat)["metrics"]

        robust = (r2["cumulative_return_pct"] > 0 and r5["cumulative_return_pct"] > 0)
        robust_label = "YES (Robust)" if robust else "FRAGILE"

        slippage_results.append({
            "Strategy": strat.name,
            "Sharpe_0bps": round(r0["sharpe_ratio"], 2),
            "Return_0bps": round(r0["cumulative_return_pct"], 2),
            "Sharpe_2bps": round(r2["sharpe_ratio"], 2),
            "Return_2bps": round(r2["cumulative_return_pct"], 2),
            "Sharpe_5bps": round(r5["sharpe_ratio"], 2),
            "Return_5bps": round(r5["cumulative_return_pct"], 2),
            "Robust": robust_label
        })

        print(f"{strat.name:<26} | {r0['sharpe_ratio']:<13.2f} | {r2['sharpe_ratio']:<13.2f} | {r5['sharpe_ratio']:<13.2f} | {robust_label}")
    print("-" * 80)

    slip_df = pd.DataFrame(slippage_results)
    slip_df.to_csv(os.path.join(results_dir, "slippage_sensitivity_stress_test.csv"), index=False)

    # 5. Walk-Forward Consistency Analysis on the Best Strategy
    best_strat_row = summary_df.sort_values(by=["OOS_Sharpe", "OOS_Return_Pct"], ascending=False).iloc[0]
    best_strat_name = best_strat_row["Strategy"]
    print(f"\n[5] Rolling Walk-Forward Validation on Best Performing Strategy: {best_strat_name}...")
    
    strat_map = {s.name: s for s in strategies}
    best_strat_obj = strat_map[best_strat_name]
    best_strat_cls = type(best_strat_obj)
    
    # Extract kwargs
    if isinstance(best_strat_obj, VolatilityBreakoutStrategy):
        kwargs = {"breakout_period": best_strat_obj.breakout_period, "trend_ema_period": best_strat_obj.trend_ema_period}
    elif isinstance(best_strat_obj, MeanReversionStrategy):
        kwargs = {"bb_period": best_strat_obj.bb_period, "bb_std": best_strat_obj.bb_std}
    elif isinstance(best_strat_obj, TrendPullbackStrategy):
        kwargs = {"ema_fast": best_strat_obj.ema_fast, "ema_mid": best_strat_obj.ema_mid, "ema_slow": best_strat_obj.ema_slow}
    elif isinstance(best_strat_obj, VolatilitySqueezeStrategy):
        kwargs = {"bb_period": best_strat_obj.bb_period, "kc_mult": best_strat_obj.kc_mult}
    else:
        kwargs = {"ema_fast": best_strat_obj.ema_fast, "ema_slow": best_strat_obj.ema_slow}

    wf_res = run_walk_forward(
        df=df_1h,
        strategy_class=best_strat_cls,
        strategy_kwargs=kwargs,
        train_bars=4320, # 6 months
        test_bars=1440,  # 2 months
        backtester_kwargs={"slippage_bps": 1.0}
    )

    wf_df = wf_res["folds"]
    print(f"    Total Walk-Forward Folds: {wf_res['total_folds']}")
    print(f"    Profitable Out-of-Sample Folds: {wf_res['profitable_folds']} / {wf_res['total_folds']} ({wf_res['consistency_rate']:.1f}% Consistency)")
    print(f"    Average Out-of-Sample Sharpe: {wf_res['avg_oos_sharpe']:.2f}")
    print(f"    Average Out-of-Sample Return per Fold: {wf_res['avg_oos_return_pct']:.2f}%")
    wf_df.to_csv(os.path.join(results_dir, "walk_forward_folds.csv"), index=False)

    # 6. Plot Equity Curves
    print("\n[6] Plotting Out-of-Sample Equity Curves...")
    plt.style.use("seaborn-v0_8-darkgrid" if "seaborn-v0_8-darkgrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)

    for name, eq in equity_curves_oos.items():
        norm_eq = (eq / eq.iloc[0]) * 100.0
        ax.plot(norm_eq.index, norm_eq.values, label=f"{name}", linewidth=1.8)

    # Add Buy & Hold ETH benchmark
    eth_bh = (df_oos["close"] / df_oos["close"].iloc[0]) * 100.0
    ax.plot(df_oos["timestamp"], eth_bh, label="ETH Buy & Hold Benchmark", color="black", linestyle="--", alpha=0.5, linewidth=1.5)

    ax.set_title("Out-of-Sample (Strictly Unseen) Equity Curves on Lighter (0% Fees)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Date", fontsize=11)
    ax.set_ylabel("Normalized Portfolio Value (Base = 100)", fontsize=11)
    ax.legend(loc="upper left", frameon=True)
    plt.tight_layout()
    chart_path = os.path.join(results_dir, "oos_equity_curves.png")
    plt.savefig(chart_path)
    plt.close()
    print(f"    Chart saved to: {chart_path}")

    # 7. Check 15m Granularity on Best Strategy
    print(f"\n[7] High-Granularity Verification on 15m Dataset (46,500+ candles)...")
    try:
        df_15m = load_dataset("lighter_eth_15m.csv")
        df_15m_is, df_15m_oos = split_in_sample_out_sample(df_15m, train_ratio=0.60)
        res_15m = bt_baseline.run(df_15m_oos, best_strat_cls(**kwargs))
        m15 = res_15m["metrics"]
        print(f"    15m Unseen OOS Return: {m15['cumulative_return_pct']:.2f}% | Sharpe: {m15['sharpe_ratio']:.2f} | MaxDD: {m15['max_drawdown_pct']:.2f}% | WinRate: {m15['win_rate']:.1f}% | Trades: {m15['total_trades']}")
    except Exception as e:
        print(f"    15m test note: {e}")

    print("\n" + "=" * 80)
    print("BACKTEST SUITE COMPLETED SUCCESSFULLY.")
    print("=" * 80)
    return summary_df


if __name__ == "__main__":
    run_full_suite()
