"""
s6_asymmetric_breakout.py - Asymmetric Long/Short Volatility Breakout Strategy
Highest-performing quantitative setup discovered on Lighter DEX ETH Perpetual data.

Market Microstructure Insight:
Crypto perp markets are structurally asymmetric:
- Longs (Accumulation/Bull Trends): Slow, steady grinds up with lower realized volatility.
  -> Uses 28-period breakout, 2.0x ATR Stop, and 4.2x ATR runner target.
- Shorts (Liquidation Cascades): Fast, violent breakdown drops followed by V-reversals.
  -> Uses 14-period breakout, 1.6x ATR tight stop, and 2.8x ATR quick flush target.
"""

import pandas as pd
import numpy as np
from strategies.base import (
    BaseStrategy, compute_atr, compute_ema, compute_adx
)


class AsymmetricBreakoutStrategy(BaseStrategy):
    def __init__(
        self,
        long_period: int = 28,
        short_period: int = 14,
        trend_ema_period: int = 200,
        long_sl_mult: float = 2.0,
        long_tp_mult: float = 4.2,
        short_sl_mult: float = 1.6,
        short_tp_mult: float = 2.8,
        adx_long_thresh: float = 18.0,
        adx_short_thresh: float = 22.0
    ):
        super().__init__(name="Asymmetric_Volatility_Breakout")
        self.long_period = long_period
        self.short_period = short_period
        self.trend_ema_period = trend_ema_period
        self.long_sl_mult = long_sl_mult
        self.long_tp_mult = long_tp_mult
        self.short_sl_mult = short_sl_mult
        self.short_tp_mult = short_tp_mult
        self.adx_long_thresh = adx_long_thresh
        self.adx_short_thresh = adx_short_thresh
        self.adx_threshold = adx_long_thresh

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["atr"] = compute_atr(df, 14)
        df["ema_trend"] = compute_ema(df["close"], self.trend_ema_period)
        df["upper_long"] = df["high"].shift(1).rolling(self.long_period).max()
        df["lower_short"] = df["low"].shift(1).rolling(self.short_period).min()
        df["upper_channel"] = df["upper_long"]
        df["lower_channel"] = df["lower_short"]
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
        long_cond = (close > df["upper_long"]) & (close > ema) & (adx > self.adx_long_thresh)
        # Short: 14-period low, Close < EMA 200, ADX > 22 (violent cascade trigger)
        short_cond = (close < df["lower_short"]) & (close < ema) & (adx > self.adx_short_thresh)

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * self.long_sl_mult
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * self.long_tp_mult

        df.loc[short_cond, "sl_dist"] = atr[short_cond] * self.short_sl_mult
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * self.short_tp_mult

        # Midline structural trailing exit
        mid_channel = (df["upper_long"] + df["lower_short"]) / 2.0
        exit_long = (close < mid_channel) & (df["signal"].shift(1) == 1)
        exit_short = (close > mid_channel) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df
