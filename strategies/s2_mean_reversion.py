"""
s2_mean_reversion.py - Bollinger Band & RSI Mean Reversion Strategy
Capitalizes directly on Lighter's 0-fee environment where high-frequency mean reversion
is not eroded by taker/maker exchange fees.

Setup:
- Bollinger Bands (20, 2.2 std dev)
- RSI(14) oversold (< 30) / overbought (> 70)
- Chop / Low Volatility Regime Filter: ADX < 32 (avoids fading runaway trends)
- Exit Target: Mean (SMA 20) or Take Profit ATR
- Invalidation / Stop Loss: 1.5 * ATR
"""

import pandas as pd
import numpy as np
from strategies.base import (
    BaseStrategy, compute_atr, compute_rsi, compute_bollinger_bands, compute_adx
)


class MeanReversionStrategy(BaseStrategy):
    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.2,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        adx_max: float = 32.0,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.0
    ):
        super().__init__(name="ZeroFee_Mean_Reversion")
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.adx_max = adx_max
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        mid, upper, lower, bandwidth, pct_b = compute_bollinger_bands(df["close"], self.bb_period, self.bb_std)
        df["bb_mid"] = mid
        df["bb_upper"] = upper
        df["bb_lower"] = lower
        df["pct_b"] = pct_b
        df["rsi"] = compute_rsi(df["close"], self.rsi_period)
        df["adx"] = compute_adx(df, 14)
        df["atr"] = compute_atr(df, self.atr_period)

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0
        df["exit_signal"] = False

        close = df["close"]
        low = df["low"]
        high = df["high"]
        rsi = df["rsi"]
        adx = df["adx"]
        atr = df["atr"]

        # Long: Price pierces lower band, RSI oversold, regime is non-runaway (ADX < adx_max)
        long_cond = (low < lower) & (rsi < self.rsi_oversold) & (adx < self.adx_max)

        # Short: Price pierces upper band, RSI overbought, regime is non-runaway
        short_cond = (high > upper) & (rsi > self.rsi_overbought) & (adx < self.adx_max)

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * self.sl_atr_mult
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * self.tp_atr_mult

        df.loc[short_cond, "sl_dist"] = atr[short_cond] * self.sl_atr_mult
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * self.tp_atr_mult

        # Target exit: Return to mean (SMA 20)
        exit_long = (close >= mid) & (df["signal"].shift(1) == 1)
        exit_short = (close <= mid) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df
