"""
base.py - Abstract Strategy Class & Common Technical Indicators
All indicators strictly use historical information without forward-peeking.
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class BaseStrategy(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Takes raw OHLCV DataFrame, calculates indicators, and populates:
        - df['signal']: 1 for Long, -1 for Short, 0 for None
        - df['sl_dist']: float (distance from entry to stop loss)
        - df['tp_dist']: float (distance from entry to take profit)
        - df['exit_signal']: bool (True if position should close at open of next bar)
        """
        pass


# -----------------------------------------------------------------------------
# Unbiased Vectorized Indicators (No Lookahead)
# -----------------------------------------------------------------------------

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (ATR)"""
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average"""
    return series.rolling(window=period).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (RSI)"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0.0)).ewm(alpha=1.0/period, adjust=False).mean()
    loss = ((-delta.where(delta < 0, 0.0))).ewm(alpha=1.0/period, adjust=False).mean()
    rs = gain / (loss + 1e-10)
    return 100.0 - (100.0 / (1.0 + rs))


def compute_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
    """Bollinger Bands (Middle, Upper, Lower, Bandwidth, %B)"""
    mid = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    bandwidth = (upper - lower) / (mid + 1e-10)
    pct_b = (series - lower) / (upper - lower + 1e-10)
    return mid, upper, lower, bandwidth, pct_b


def compute_keltner_channels(df: pd.DataFrame, ema_period: int = 20, atr_period: int = 14, multiplier: float = 1.5):
    """Keltner Channels"""
    mid = compute_ema(df["close"], ema_period)
    atr = compute_atr(df, atr_period)
    upper = mid + multiplier * atr
    lower = mid - multiplier * atr
    return mid, upper, lower


def compute_donchian(df: pd.DataFrame, period: int = 20):
    """Donchian Channels (shifted by 1 to prevent lookahead)"""
    upper = df["high"].shift(1).rolling(window=period).max()
    lower = df["low"].shift(1).rolling(window=period).min()
    mid = (upper + lower) / 2.0
    return upper, lower, mid


def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index (ADX)"""
    high = df["high"]
    low = df["low"]
    close_prev = df["close"].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    up_move = high - df["high"].shift(1)
    down_move = df["low"].shift(1) - low
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    tr_smooth = pd.Series(tr).ewm(span=period, adjust=False).mean()
    plus_di = 100.0 * (pd.Series(plus_dm).ewm(span=period, adjust=False).mean() / (tr_smooth + 1e-10))
    minus_di = 100.0 * (pd.Series(minus_dm).ewm(span=period, adjust=False).mean() / (tr_smooth + 1e-10))
    
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(span=period, adjust=False).mean()
    return adx
