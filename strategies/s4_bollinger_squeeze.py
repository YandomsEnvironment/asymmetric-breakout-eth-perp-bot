"""
s4_bollinger_squeeze.py - Volatility Squeeze Strategy (Bollinger Bands vs Keltner Channels)
A classic institutional volatility breakout setup:
- Compression (Squeeze): Bollinger Bands contract entirely INSIDE Keltner Channels.
- Momentum: Momentum oscillator (Close - SMA(20)) indicates directional bias.
- Firing: When BB expands OUTSIDE Keltner Channels, trade in the direction of the momentum expansion.
"""

import pandas as pd
import numpy as np
from strategies.base import (
    BaseStrategy, compute_atr, compute_bollinger_bands, compute_keltner_channels, compute_ema
)


class VolatilitySqueezeStrategy(BaseStrategy):
    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        kc_period: int = 20,
        kc_mult: float = 1.5,
        atr_period: int = 14,
        sl_atr_mult: float = 1.8,
        tp_atr_mult: float = 3.2
    ):
        super().__init__(name="Bollinger_Keltner_Squeeze")
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.kc_period = kc_period
        self.kc_mult = kc_mult
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        bb_mid, bb_upper, bb_lower, _, _ = compute_bollinger_bands(df["close"], self.bb_period, self.bb_std)
        kc_mid, kc_upper, kc_lower = compute_keltner_channels(df, self.kc_period, self.atr_period, self.kc_mult)
        df["atr"] = compute_atr(df, self.atr_period)

        # Squeeze condition: BB inside KC
        squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)
        # Squeeze release (firing): was in squeeze, now breaking out
        squeeze_fired = (squeeze_on.shift(1) == True) & (squeeze_on == False)

        # Momentum calculation: difference of close from average of donchian mid and sma
        sma20 = df["close"].rolling(window=self.bb_period).mean()
        momentum = df["close"] - sma20
        mom_slope = momentum.diff(1)

        df["signal"] = 0
        df["sl_dist"] = 0.0
        df["tp_dist"] = 0.0
        df["exit_signal"] = False

        atr = df["atr"]

        # Long: Squeeze fired with positive momentum & positive slope
        long_cond = squeeze_fired & (momentum > 0) & (mom_slope > 0)
        # Short: Squeeze fired with negative momentum & negative slope
        short_cond = squeeze_fired & (momentum < 0) & (mom_slope < 0)

        df.loc[long_cond, "signal"] = 1
        df.loc[short_cond, "signal"] = -1

        df.loc[long_cond, "sl_dist"] = atr[long_cond] * self.sl_atr_mult
        df.loc[long_cond, "tp_dist"] = atr[long_cond] * self.tp_atr_mult

        df.loc[short_cond, "sl_dist"] = atr[short_cond] * self.sl_atr_mult
        df.loc[short_cond, "tp_dist"] = atr[short_cond] * self.tp_atr_mult

        # Momentum deceleration exit
        exit_long = (momentum < 0) & (df["signal"].shift(1) == 1)
        exit_short = (momentum > 0) & (df["signal"].shift(1) == -1)
        df.loc[exit_long | exit_short, "exit_signal"] = True

        return df
