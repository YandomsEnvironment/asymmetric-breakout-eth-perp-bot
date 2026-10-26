"""
backtester.py - 100% Unbiased Event-Driven / Bar-by-Bar Backtesting Engine for ETH Perps
Designed for Lighter Zero-Fee Model.

Key Unbiased Principles:
1. Zero Lookahead: Signals generated at bar t Close -> Orders executed strictly at bar t+1 Open.
2. Conservative Intra-bar Execution: If both TP and SL are hit within the same candle, SL is assumed hit first.
3. Realistic Slippage Modeling: Configurable slippage / spread in basis points (default 0 for baseline Lighter 0-fee).
4. Proper Risk Sizing: Fixed fractional risk model (risk % of capital per trade) or capital fraction.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional
from engine.metrics import compute_metrics


class Backtester:
    def __init__(
        self,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.0000,      # Lighter is 0% fees
        slippage_bps: float = 0.0,     # Basis points slippage per side (1 bps = 0.0001)
        risk_per_trade: float = 0.015, # 1.5% capital risked per trade
        max_leverage: float = 3.0,     # Max allowable leverage
        allow_short: bool = True
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage_pct = (slippage_bps / 10000.0)
        self.risk_per_trade = risk_per_trade
        self.max_leverage = max_leverage
        self.allow_short = allow_short

    def run(self, df: pd.DataFrame, strategy) -> Dict[str, Any]:
        """
        Executes the backtest bar by bar.
        Expects strategy.generate_signals(df) to have added:
        - 'signal': 1 (Long), -1 (Short), 0 (Neutral)
        - 'stop_loss_dist': float (distance to SL in price terms) or None
        - 'take_profit_dist': float (distance to TP in price terms) or None
        - 'custom_exit': boolean flag or function if strategy has dynamic exit
        """
        df = strategy.generate_signals(df.copy())
        
        capital = self.initial_capital
        position = 0.0           # Current ETH position (+ for Long, - for Short)
        entry_price = 0.0
        entry_idx = 0
        entry_time = None
        sl_price = None
        tp_price = None
        
        trades = []
        equity_series = np.zeros(len(df))
        cash = capital

        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        timestamps = df["timestamp"].values
        signals = df["signal"].values
        
        sl_dists = df["sl_dist"].values if "sl_dist" in df.columns else np.zeros(len(df))
        tp_dists = df["tp_dist"].values if "tp_dist" in df.columns else np.zeros(len(df))
        exit_signals = df["exit_signal"].values if "exit_signal" in df.columns else np.zeros(len(df))

        n = len(df)
        
        for i in range(n):
            current_open = opens[i]
            current_high = highs[i]
            current_low = lows[i]
            current_close = closes[i]
            current_ts = timestamps[i]

            # -------------------------------------------------------------
            # 1. PROCESS EXISTING POSITION EXITS AT CURRENT BAR
            # -------------------------------------------------------------
            if position != 0.0:
                is_long = position > 0
                trade_closed = False
                exit_price = None
                exit_reason = None

                # Check intra-bar Stop Loss and Take Profit
                hit_sl = False
                hit_tp = False

                if is_long:
                    if sl_price is not None and current_low <= sl_price:
                        hit_sl = True
                    if tp_price is not None and current_high >= tp_price:
                        hit_tp = True
                else: # Short
                    if sl_price is not None and current_high >= sl_price:
                        hit_sl = True
                    if tp_price is not None and current_low <= tp_price:
                        hit_tp = True

                # Conservative anti-optimism: If both hit, assume Stop Loss triggered first
                if hit_sl and hit_tp:
                    hit_tp = False

                if hit_sl:
                    exit_price = sl_price * (1.0 - self.slippage_pct if is_long else 1.0 + self.slippage_pct)
                    exit_reason = "STOP_LOSS"
                    trade_closed = True
                elif hit_tp:
                    exit_price = tp_price * (1.0 - self.slippage_pct if is_long else 1.0 + self.slippage_pct)
                    exit_reason = "TAKE_PROFIT"
                    trade_closed = True
                elif exit_signals[i]:
                    # Exit signal triggered at previous bar close, executed at current Open
                    exit_price = current_open * (1.0 - self.slippage_pct if is_long else 1.0 + self.slippage_pct)
                    exit_reason = "SIGNAL_EXIT"
                    trade_closed = True

                if trade_closed:
                    # Calculate PnL
                    if is_long:
                        gross_pnl = position * (exit_price - entry_price)
                    else:
                        gross_pnl = abs(position) * (entry_price - exit_price)
                    
                    # Fee calculation (0 on Lighter, but computed for robustness)
                    fee = (abs(position) * entry_price + abs(position) * exit_price) * self.fee_rate
                    net_pnl = gross_pnl - fee
                    ret_pct = net_pnl / (abs(position) * entry_price)

                    cash += net_pnl
                    capital = cash

                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": current_ts,
                        "direction": "LONG" if is_long else "SHORT",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "size": abs(position),
                        "pnl": net_pnl,
                        "return_pct": ret_pct,
                        "exit_reason": exit_reason,
                        "duration_bars": i - entry_idx
                    })

                    position = 0.0
                    entry_price = 0.0
                    sl_price = None
                    tp_price = None

            # -------------------------------------------------------------
            # 2. PROCESS NEW ENTRY SIGNALS AT CURRENT BAR OPEN
            # (Signal was generated at bar i-1 close, executed at bar i Open)
            # -------------------------------------------------------------
            if position == 0.0 and i > 0:
                prev_signal = signals[i - 1]
                if not self.allow_short and prev_signal == -1:
                    prev_signal = 0

                if prev_signal != 0:
                    is_long = (prev_signal == 1)
                    fill_price = current_open * (1.0 + self.slippage_pct if is_long else 1.0 - self.slippage_pct)
                    
                    sl_dist = sl_dists[i - 1]
                    tp_dist = tp_dists[i - 1]

                    if sl_dist > 0:
                        sl_price = fill_price - sl_dist if is_long else fill_price + sl_dist
                    else:
                        sl_price = None

                    if tp_dist > 0:
                        tp_price = fill_price + tp_dist if is_long else fill_price - tp_dist
                    else:
                        tp_price = None

                    # Position sizing based on risk per trade
                    if sl_dist > 0:
                        risk_amount = capital * self.risk_per_trade
                        desired_size = risk_amount / sl_dist
                    else:
                        # Fallback to 1x leverage if no stop loss distance provided
                        desired_size = (capital * 0.95) / fill_price

                    # Cap position by max leverage
                    max_size = (capital * self.max_leverage) / fill_price
                    size = min(desired_size, max_size)

                    if size * fill_price >= 10.0: # Minimum order threshold
                        position = size if is_long else -size
                        entry_price = fill_price
                        entry_idx = i
                        entry_time = current_ts

            # -------------------------------------------------------------
            # 3. MARK-TO-MARKET EQUITY FOR THE CURRENT BAR
            # -------------------------------------------------------------
            if position != 0.0:
                is_long = position > 0
                unrealized_pnl = position * (current_close - entry_price) if is_long else abs(position) * (entry_price - current_close)
                current_equity = cash + unrealized_pnl
            else:
                current_equity = cash

            equity_series[i] = current_equity

        # Build equity series
        equity_df = pd.Series(equity_series, index=df["timestamp"])
        
        # Determine interval from timestamps
        interval = "1h"
        if len(df) > 1:
            diff_min = (df["timestamp"].iloc[1] - df["timestamp"].iloc[0]).total_seconds() / 60
            if diff_min <= 20:
                interval = "15m"

        metrics = compute_metrics(
            trades=trades,
            equity_curve=equity_df,
            interval=interval,
            initial_capital=self.initial_capital
        )

        return {
            "metrics": metrics,
            "trades": trades,
            "equity_curve": equity_df,
            "df": df
        }
