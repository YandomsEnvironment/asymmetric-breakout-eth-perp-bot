"""
s3_mtf_trend_pullback.py - Multi-Timeframe Trend Continuation Pullback Setup
Institutional trend-pullback system:
- Macro trend: Price above EMA 200 and EMA 50 > EMA 200
- Micro pullback: Price dips toward EMA 21 / EMA 50 with RSI resetting to 38-50
- Entry confirmation: Price re-claims short-term momentum (Close > EMA 21 and Close > Open)
- Risk/Reward: 1.5 ATR Stop Loss vs 3.0 ATR Take Profit (2.0 R:R)
"""

import pandas as pd
import numpy as np
from strategies.base import (
    BaseStrategy, compute_atr, compute_ema, compute_rsi
)


class TrendPullbackStrategy(BaseStrategy):
    def __init__(
        self,
        ema_fast: int = 21,
        ema_mid: int = 50,
        ema_slow: int = 200,
        rsi_period: int = 14,
        rsi_pullback_min: float = 38.0,
        rsi_pullback_max: float = 52.0,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 3.0
    ):
        super().__init__(name="MTF_Trend_Pullback")
        self.ema_fast = ema_fast
        self.ema_mid = ema_mid
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_pullback_min = rsi_pullback_min
        self.rsi_pullback_max = rsi_pullback_max
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["ema_fast"] = compute_ema(df["close"], self.ema_fast)
        df["ema_mid"] = compute_ema(df["close"], self.ema_mid)
        df["ema_slow"] = compute_ema(df["close"], self.ema_slow)
        df["rsi"] = compute_rsi(df["close"], self.rsi_period)
        df["atr"] = compute_atr(df, self.atr_period)

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0
        df["exit_signal"] = False

        close = df["close"]
        open_p = df["open"]
        low = df["low"]
        high = df["high"]
        e_fast = df["ema_fast"]
        e_mid = df["ema_mid"]
        e_slow = df["ema_slow"]
        rsi = df["rsi"]
        atr = df["atr"]

        # Long Trend Pullback:
        # 1. Macro Bullish: EMA 50 > EMA 200 & Close > EMA 200
        # 2. Pullback occurred: Low touched near EMA 21 or EMA 50, RSI cooled to 38-52
        # 3. Resumption: Close > Open and Close > EMA 21
        bullish_macro = (e_mid > e_slow) & (close > e_slow)
        pullback_long = (low <= e_fast * 1.005) & (rsi >= self.rsi_pullback_min) & (rsi <= self.rsi_pullback_max)
        resumption_long = (close > open_p) & (close > e_fast)
        long_cond = bullish_macro & pullback_long & resumption_long

        # Short Trend Pullback:
        # 1. Macro Bearish: EMA 50 < EMA 200 & Close < EMA 200
        # 2. Pullback occurred: High touched near EMA 21 or EMA 50, RSI rallied to 48-62
        # 3. Resumption: Close < Open and Close < EMA 21
        bearish_macro = (e_mid < e_slow) & (close < e_slow)
        pullback_short = (high >= e_fast * 0.995) & (rsi >= (100 - self.rsi_pullback_max)) & (rsi <= (100 - self.rsi_pullback_min))
        resumption_short = (close < open_p) & (close < e_fast)
        short_cond = bearish_macro & pullback_short & resumption_short

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * self.sl_atr_mult
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * self.tp_atr_mult

        df.loc[short_cond, "sl_dist"] = atr[short_cond] * self.sl_atr_mult
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * self.tp_atr_mult

        # Invalidation exit: Close crosses back below EMA 50
        exit_long = (close < e_mid) & (df["signal"].shift(1) == 1)
        exit_short = (close > e_mid) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df
