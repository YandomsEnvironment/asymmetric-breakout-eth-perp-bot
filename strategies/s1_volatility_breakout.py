"""
s1_volatility_breakout.py - Volatility Breakout with Trend & ADX Filter
Setup:
- Donchian channel breakout (24h/24-bar high/low)
- Trend filter: Close above/below EMA 200
- Momentum strength: ADX > 20
- Dynamic ATR-based Stop Loss & Take Profit (1 : 1.75+ R:R)
"""

import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, compute_atr, compute_ema, compute_donchian, compute_adx


class VolatilityBreakoutStrategy(BaseStrategy):
    def __init__(
        self,
        breakout_period: int = 24,
        trend_ema_period: int = 200,
        adx_period: int = 14,
        adx_threshold: float = 20.0,
        atr_period: int = 14,
        sl_atr_mult: float = 2.0,
        tp_atr_mult: float = 3.5
    ):
        super().__init__(name="ATR_Volatility_Breakout")
        self.breakout_period = breakout_period
        self.trend_ema_period = trend_ema_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["atr"] = compute_atr(df, self.atr_period)
        df["ema_trend"] = compute_ema(df["close"], self.trend_ema_period)
        df["upper_channel"], df["lower_channel"], df["mid_channel"] = compute_donchian(df, self.breakout_period)
        df["adx"] = compute_adx(df, self.adx_period)

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0
        df["exit_signal"] = False

        close = df["close"]
        upper = df["upper_channel"]
        lower = df["lower_channel"]
        mid = df["mid_channel"]
        ema = df["ema_trend"]
        adx = df["adx"]
        atr = df["atr"]

        # Long Entry: Close breaks above Upper Donchian Channel, above EMA 200, ADX > threshold
        long_cond = (close > upper) & (close > ema) & (adx > self.adx_threshold)
        
        # Short Entry: Close breaks below Lower Donchian Channel, below EMA 200, ADX > threshold
        short_cond = (close < lower) & (close < ema) & (adx > self.adx_threshold)

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * self.sl_atr_mult
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * self.tp_atr_mult

        df.loc[short_cond, "sl_dist"] = atr[short_cond] * self.sl_atr_mult
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * self.tp_atr_mult

        # Structural Exit: Close re-crosses mid channel
        exit_long = (close < mid) & (df["signal"].shift(1) == 1)
        exit_short = (close > mid) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df
