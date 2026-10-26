"""
s5_volume_momentum.py - Volume-Weighted Momentum Flow Setup
Combines volume expansion with moving average momentum:
- Volume Surge: Current volume > 1.4x 20-period Volume SMA
- Momentum Alignment: Fast EMA(9) crosses/leads Slow EMA(21)
- RSI Confirmation: RSI in directional acceleration zone (52-68 for Long, 32-48 for Short)
- Target: 2.0 Risk-to-Reward (1.5 ATR SL, 3.0 ATR TP)
"""

import pandas as pd
import numpy as np
from strategies.base import (
    BaseStrategy, compute_atr, compute_ema, compute_rsi
)


class VolumeMomentumStrategy(BaseStrategy):
    def __init__(
        self,
        ema_fast: int = 9,
        ema_slow: int = 21,
        vol_period: int = 20,
        vol_mult: float = 1.4,
        rsi_period: int = 14,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 3.0
    ):
        super().__init__(name="Volume_Momentum_Flow")
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.vol_period = vol_period
        self.vol_mult = vol_mult
        self.rsi_period = rsi_period
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df["ema_f"] = compute_ema(df["close"], self.ema_fast)
        df["ema_s"] = compute_ema(df["close"], self.ema_slow)
        vol_col = "volume_eth" if "volume_eth" in df.columns else "volume"
        df["vol_sma"] = df[vol_col].rolling(window=self.vol_period).mean()
        df["rsi"] = compute_rsi(df["close"], self.rsi_period)
        df["atr"] = compute_atr(df, self.atr_period)

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0
        df["exit_signal"] = False

        close = df["close"]
        open_p = df["open"]
        ema_f = df["ema_f"]
        ema_s = df["ema_s"]
        vol = df[vol_col]
        vol_sma = df["vol_sma"]
        rsi = df["rsi"]
        atr = df["atr"]

        vol_surge = vol > (vol_sma * self.vol_mult)

        # Bullish volume thrust: Fast > Slow, Close > Open, Volume Surge, RSI 52-68
        long_cond = (ema_f > ema_s) & (close > open_p) & vol_surge & (rsi >= 52) & (rsi <= 68)

        # Bearish volume thrust: Fast < Slow, Close < Open, Volume Surge, RSI 32-48
        short_cond = (ema_f < ema_s) & (close < open_p) & vol_surge & (rsi >= 32) & (rsi <= 48)

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * self.sl_atr_mult
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * self.tp_atr_mult

        df.loc[short_cond, "sl_dist"] = atr[short_cond] * self.sl_atr_mult
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * self.tp_atr_mult

        # Exit when fast EMA crosses back over slow EMA
        exit_long = (ema_f < ema_s) & (df["signal"].shift(1) == 1)
        exit_short = (ema_f > ema_s) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df
