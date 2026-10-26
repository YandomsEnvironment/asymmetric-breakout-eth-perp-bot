"""
research_trials.py - Advanced Quantitative Strategy Research & Hypothesis Trials
Investigates new institutional setups on Lighter DEX ETH Perpetual data:
1. Hypothesis 1: Dynamic Regime-Adaptive Breakout with Chandelier Trailing Stop
2. Hypothesis 2: Liquidity Sweep & Stop-Hunt Reversal (Turtle Soup setup)
3. Hypothesis 3: Asymmetric Long/Short Volatility Breakout (capturing crash cascades vs grind up)
4. Hypothesis 4: Multi-Timeframe 4H Trend Filter + 1H Value Ribbon Continuation
5. Hypothesis 5: Chandelier Volatility Trend Follower (Letting winners run without fixed TP cap)
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, r"C:\Users\lumin\Desktop\strat-trading-eth")
from engine.backtester import Backtester
from engine.walk_forward import split_in_sample_out_sample, run_walk_forward
from strategies.base import (
    BaseStrategy, compute_atr, compute_ema, compute_donchian, compute_adx, compute_rsi
)
from strategies.s1_volatility_breakout import VolatilityBreakoutStrategy

# Load authoritative datasets
df_1h = pd.read_csv(r"C:\Users\lumin\Desktop\strat-trading-eth\data\lighter_eth_1h.csv")
df_1h["timestamp"] = pd.to_datetime(df_1h["timestamp"], utc=True)
df_is, df_oos = split_in_sample_out_sample(df_1h, 0.60)


# =============================================================================
# STRATEGY 1: Chandelier Volatility Trend Follower (No Cap on Winners)
# =============================================================================
class ChandelierTrendStrategy(BaseStrategy):
    """
    Rides massive crypto trends by replacing fixed take-profit caps with
    a continuous trailing Chandelier exit (Highest High - mult * ATR).
    """
    def __init__(self, breakout_period: int = 24, trend_ema: int = 200, atr_mult: float = 2.2, adx_thresh: float = 20.0):
        super().__init__(name="Chandelier_Trend_Follower")
        self.breakout_period = breakout_period
        self.trend_ema = trend_ema
        self.atr_mult = atr_mult
        self.adx_thresh = adx_thresh

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["atr"] = compute_atr(df, 14)
        df["ema_trend"] = compute_ema(df["close"], self.trend_ema)
        df["upper_ch"], df["lower_ch"], df["mid_ch"] = compute_donchian(df, self.breakout_period)
        df["adx"] = compute_adx(df, 14)

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0  # 0 means no fixed TP; exit via trailing stop
        df["exit_signal"] = False

        close = df["close"]
        upper = df["upper_ch"]
        lower = df["lower_ch"]
        ema = df["ema_trend"]
        adx = df["adx"]
        atr = df["atr"]

        long_cond = (close > upper) & (close > ema) & (adx > self.adx_thresh)
        short_cond = (close < lower) & (close < ema) & (adx > self.adx_thresh)

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * self.atr_mult
        df.loc[short_cond, "sl_dist"] = atr[short_cond] * self.atr_mult
        # Unlimited upside: TP is set very high so trailing exit dictates close
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * 12.0
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * 12.0

        # Trailing Exit: Close crosses opposite Donchian mid-line or EMA 21
        ema_fast = compute_ema(close, 21)
        exit_long = (close < ema_fast) & (df["signal"].shift(1) == 1)
        exit_short = (close > ema_fast) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df


# =============================================================================
# STRATEGY 2: Liquidity Sweep & Stop-Hunt Reversal (Turtle Soup)
# =============================================================================
class LiquiditySweepStrategy(BaseStrategy):
    """
    Fades false breakouts: Price pierces 36-period extreme, then closes back inside,
    triggering a fast mean-reversion counter-move to the opposite side of the range.
    """
    def __init__(self, lookback: int = 36, atr_period: int = 14, sl_atr_mult: float = 1.2, tp_atr_mult: float = 2.8):
        super().__init__(name="Liquidity_Sweep_Reversal")
        self.lookback = lookback
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["atr"] = compute_atr(df, self.atr_period)
        df["high_level"] = df["high"].shift(1).rolling(self.lookback).max()
        df["low_level"] = df["low"].shift(1).rolling(self.lookback).min()
        df["mid_level"] = (df["high_level"] + df["low_level"]) / 2.0
        df["rsi"] = compute_rsi(df["close"], 14)

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0
        df["exit_signal"] = False

        high = df["high"]
        low = df["low"]
        close = df["close"]
        h_lvl = df["high_level"]
        l_lvl = df["low_level"]
        atr = df["atr"]
        rsi = df["rsi"]

        # Bearish Liquidity Sweep (Short): High poked above previous 36-bar high, but Close fell back BELOW it
        bearish_sweep = (high > h_lvl) & (close < h_lvl) & (rsi > 55)

        # Bullish Liquidity Sweep (Long): Low poked below previous 36-bar low, but Close rallied back ABOVE it
        bullish_sweep = (low < l_lvl) & (close > l_lvl) & (rsi < 45)

        df.loc[bullish_sweep, "signal"] = 1
        df.loc[bearish_sweep, "signal"] = -1

        df.loc[bullish_sweep, "sl_dist"] = atr[bullish_sweep] * self.sl_atr_mult
        df.loc[bullish_sweep, "tp_dist"] = atr[bullish_sweep] * self.tp_atr_mult

        df.loc[bearish_sweep, "sl_dist"] = atr[bearish_sweep] * self.sl_atr_mult
        df.loc[bearish_sweep, "tp_dist"] = atr[bearish_sweep] * self.tp_atr_mult

        # Midline exit
        exit_long = (close >= df["mid_level"]) & (df["signal"].shift(1) == 1)
        exit_short = (close <= df["mid_level"]) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df


# =============================================================================
# STRATEGY 3: Asymmetric Long/Short Volatility Breakout
# =============================================================================
class AsymmetricBreakoutStrategy(BaseStrategy):
    """
    Accounts for market asymmetry:
    Longs: Slower breakout (28 periods) with wide runner target (4.0x ATR) for steady grinds up.
    Shorts: Faster breakout (14 periods) with tighter target (2.5x ATR) for rapid flash crashes.
    """
    def __init__(self, long_period: int = 28, short_period: int = 14, trend_ema: int = 200):
        super().__init__(name="Asymmetric_Breakout")
        self.long_period = long_period
        self.short_period = short_period
        self.trend_ema = trend_ema

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["atr"] = compute_atr(df, 14)
        df["ema_trend"] = compute_ema(df["close"], self.trend_ema)
        df["upper_long"] = df["high"].shift(1).rolling(self.long_period).max()
        df["lower_short"] = df["low"].shift(1).rolling(self.short_period).min()
        df["adx"] = compute_adx(df, 14)

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0
        df["exit_signal"] = False

        close = df["close"]
        ema = df["ema_trend"]
        adx = df["adx"]
        atr = df["atr"]

        # Long: 28-period high, Close > EMA 200, ADX > 18
        long_cond = (close > df["upper_long"]) & (close > ema) & (adx > 18)
        # Short: 14-period low, Close < EMA 200, ADX > 22 (violent move)
        short_cond = (close < df["lower_short"]) & (close < ema) & (adx > 22)

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * 2.0
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * 4.2  # Big runner

        df.loc[short_cond, "sl_dist"] = atr[short_cond] * 1.6
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * 2.8  # Fast crash target

        # Exit
        mid_long = (df["upper_long"] + df["lower_short"]) / 2.0
        exit_long = (close < mid_long) & (df["signal"].shift(1) == 1)
        exit_short = (close > mid_long) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df


# =============================================================================
# STRATEGY 4: Volatility Compression & Adaptive Breakout (Bollinger Squeeze + Breakout Hybrid)
# =============================================================================
class AdaptiveCompressionBreakoutStrategy(BaseStrategy):
    """
    Hybrid: Only triggers a breakout if price was PREVIOUSLY in a low volatility compression
    (ATR Percentile < 40th percentile over 100 bars), then enters as volatility explodes.
    Avoids entering breakouts that occur at the tail-end of exhausted trends!
    """
    def __init__(self, breakout_period: int = 24, trend_ema: int = 200, atr_compression_window: int = 72):
        super().__init__(name="Adaptive_Compression_Breakout")
        self.breakout_period = breakout_period
        self.trend_ema = trend_ema
        self.atr_compression_window = atr_compression_window

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["atr"] = compute_atr(df, 14)
        df["ema_trend"] = compute_ema(df["close"], self.trend_ema)
        df["upper_ch"], df["lower_ch"], df["mid_ch"] = compute_donchian(df, self.breakout_period)
        
        # Volatility percentile: ATR rank over past 72 bars
        atr = df["atr"]
        df["atr_rolling_min"] = atr.rolling(self.atr_compression_window).min()
        df["atr_rolling_max"] = atr.rolling(self.atr_compression_window).max()
        df["atr_norm"] = (atr - df["atr_rolling_min"]) / (df["atr_rolling_max"] - df["atr_rolling_min"] + 1e-10)

        # Was compressed in recent bars (ATR norm was < 0.45)
        df["was_compressed"] = df["atr_norm"].shift(1).rolling(12).min() < 0.45

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0
        df["exit_signal"] = False

        close = df["close"]
        upper = df["upper_ch"]
        lower = df["lower_ch"]
        ema = df["ema_trend"]
        comp = df["was_compressed"]

        long_cond = (close > upper) & (close > ema) & comp
        short_cond = (close < lower) & (close < ema) & comp

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * 1.8
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * 3.8

        df.loc[short_cond, "sl_dist"] = atr[short_cond] * 1.8
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * 3.8

        exit_long = (close < df["mid_ch"]) & (df["signal"].shift(1) == 1)
        exit_short = (close > df["mid_ch"]) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df


def run_trials():
    print("=" * 105)
    print("QUANTITATIVE EXPERIMENTATION: ADVANCED HYPOTHESIS TRIALS (LIGHTER 0% FEES, 2 BPS SPREAD)")
    print("=" * 105)

    candidates = [
        VolatilityBreakoutStrategy(), # Current champion benchmark
        ChandelierTrendStrategy(),
        LiquiditySweepStrategy(),
        AsymmetricBreakoutStrategy(),
        AdaptiveCompressionBreakoutStrategy()
    ]

    bt = Backtester(initial_capital=200.0, fee_rate=0.0, slippage_bps=2.0, risk_per_trade=0.015, max_leverage=2.5)

    results = []
    print(f"{'Strategy Hypothesis':<32} | {'OOS Return':<11} | {'Sharpe':<8} | {'Max DD':<9} | {'Win %':<7} | {'PF':<6} | {'Trades':<7} | {'Calmar':<8} | {'Verdict'}")
    print("-" * 105)

    for strat in candidates:
        res = bt.run(df_oos, strat)
        m = res["metrics"]
        
        # Verdict calculation
        is_superior = (m["sharpe_ratio"] > 1.57 and m["max_drawdown_pct"] <= 21.2) or (m["cumulative_return_pct"] > 45.0 and m["sharpe_ratio"] > 1.50)
        verdict = "SUPERIOR EDGE" if is_superior else ("STRONG CONTENDER" if m["sharpe_ratio"] >= 1.3 else ("VIABLE" if m["cumulative_return_pct"] > 0 else "FAILED"))

        row = {
            "Strategy": strat.name,
            "Return_Pct": m["cumulative_return_pct"],
            "Sharpe": m["sharpe_ratio"],
            "MaxDD_Pct": m["max_drawdown_pct"],
            "WinRate": m["win_rate"],
            "ProfitFactor": m["profit_factor"],
            "Trades": m["total_trades"],
            "Calmar": m["calmar_ratio"],
            "EndingCapital": m["ending_capital"],
            "Verdict": verdict
        }
        results.append(row)

        print(f"{strat.name:<32} | {m['cumulative_return_pct']:<10.1f}% | {m['sharpe_ratio']:<8.2f} | {m['max_drawdown_pct']:<8.1f}% | {m['win_rate']:<6.1f}% | {m['profit_factor']:<6.2f} | {m['total_trades']:<7} | {m['calmar_ratio']:<8.2f} | {verdict}")

    print("-" * 105)
    return pd.DataFrame(results)


if __name__ == "__main__":
    df_res = run_trials()
