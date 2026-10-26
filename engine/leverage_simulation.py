"""
leverage_simulation.py - Mathematical & Empirical Simulation of 50x Leverage on $100
Evaluates liquidation risk, survival time, best-case, worst-case, and most likely scenarios
on real Lighter ETH Perpetual candles.
"""

import sys
import os
import pandas as pd
import numpy as np

sys.path.insert(0, r"C:\Users\lumin\Desktop\strat-trading-eth")
from strategies.s1_volatility_breakout import VolatilityBreakoutStrategy
from engine.walk_forward import split_in_sample_out_sample

df_1h = pd.read_csv(r"C:\Users\lumin\Desktop\strat-trading-eth\data\lighter_eth_1h.csv")
df_1h["timestamp"] = pd.to_datetime(df_1h["timestamp"], utc=True)
df_is, df_oos = split_in_sample_out_sample(df_1h, 0.60)

strat = VolatilityBreakoutStrategy()
df_sig = strat.generate_signals(df_oos.copy())

def simulate_leverage(leverage: float, initial_capital: float = 100.0, maint_margin_pct: float = 0.01):
    """
    Simulates trading with fixed leverage.
    Liquidation distance = (1 / leverage) - maint_margin_pct.
    If bar adverse price wick touches liquidation price, position is liquidated (capital becomes 0).
    """
    capital = initial_capital
    position = 0.0
    entry_price = 0.0
    is_liquidated = False
    liq_bar_idx = -1
    liq_time = None
    trades_executed = 0
    trade_history = []
    
    liq_dist_pct = (1.0 / leverage) - maint_margin_pct
    
    opens = df_sig["open"].values
    highs = df_sig["high"].values
    lows = df_sig["low"].values
    closes = df_sig["close"].values
    signals = df_sig["signal"].values
    timestamps = df_sig["timestamp"].values
    sl_dists = df_sig["sl_dist"].values
    tp_dists = df_sig["tp_dist"].values
    exit_signals = df_sig["exit_signal"].values
    
    sl_price = None
    tp_price = None
    liq_price = None
    
    for i in range(1, len(df_sig)):
        if is_liquidated:
            break
            
        cur_open = opens[i]
        cur_high = highs[i]
        cur_low = lows[i]
        cur_ts = timestamps[i]
        
        # 1. Manage open position
        if position != 0.0:
            is_long = position > 0
            # Check liquidation FIRST
            hit_liq = False
            if is_long and cur_low <= liq_price:
                hit_liq = True
            elif not is_long and cur_high >= liq_price:
                hit_liq = True
                
            if hit_liq:
                is_liquidated = True
                liq_bar_idx = i
                liq_time = cur_ts
                capital = 0.0
                trade_history.append({"pnl": -initial_capital, "reason": "LIQUIDATION", "bars": i})
                break
                
            # Check normal SL / TP
            hit_sl = (cur_low <= sl_price) if is_long else (cur_high >= sl_price)
            hit_tp = (cur_high >= tp_price) if is_long else (cur_low <= tp_price)
            
            closed = False
            exit_p = 0.0
            reason = ""
            
            if hit_sl:
                exit_p = sl_price
                reason = "SL"
                closed = True
            elif hit_tp:
                exit_p = tp_price
                reason = "TP"
                closed = True
            elif exit_signals[i]:
                exit_p = cur_open
                reason = "SIGNAL"
                closed = True
                
            if closed:
                pnl = position * (exit_p - entry_price) if is_long else abs(position) * (entry_price - exit_p)
                capital += pnl
                trade_history.append({"pnl": pnl, "reason": reason, "capital": capital})
                position = 0.0
                if capital <= 5.0: # Account bust
                    is_liquidated = True
                    liq_bar_idx = i
                    liq_time = cur_ts
                    break
                    
        # 2. Enter new position at bar open
        if position == 0.0 and not is_liquidated:
            sig = signals[i - 1]
            if sig != 0:
                is_long = (sig == 1)
                entry_price = cur_open
                pos_value = capital * leverage
                position = (pos_value / entry_price) if is_long else -(pos_value / entry_price)
                
                # Liquidation price
                if is_long:
                    liq_price = entry_price * (1.0 - liq_dist_pct)
                    sl_price = entry_price - sl_dists[i - 1]
                    tp_price = entry_price + tp_dists[i - 1]
                else:
                    liq_price = entry_price * (1.0 + liq_dist_pct)
                    sl_price = entry_price + sl_dists[i - 1]
                    tp_price = entry_price - tp_dists[i - 1]
                    
                trades_executed += 1
                
    return {
        "leverage": leverage,
        "is_liquidated": is_liquidated,
        "liq_bar_idx": liq_bar_idx,
        "liq_time": liq_time,
        "trades_executed": trades_executed,
        "ending_capital": max(capital, 0.0),
        "total_trades": len(trade_history)
    }

print("=" * 75)
print("LEVERAGE SIMULATION ON $100 STARTING BALANCE (ETH PERP UNSEEN DATA)")
print("=" * 75)
for lev in [50.0, 20.0, 10.0, 5.0, 3.0, 2.0, 1.0]:
    res = simulate_leverage(lev)
    liq_str = f"LIQUIDATED on Trade #{res['trades_executed']} at {res['liq_time']}" if res['is_liquidated'] else f"SURVIVED! Final: ${res['ending_capital']:.2f}"
    print(f"Leverage {lev:>4.0f}x | {liq_str}")

# Trade #1 Excursion Analysis
first_idx = (df_sig["signal"] != 0).idxmax()
entry = df_sig["open"].iloc[first_idx]
sl_dist = df_sig["sl_dist"].iloc[first_idx - 1]
sig_type = "LONG" if df_sig["signal"].iloc[first_idx - 1] == 1 else "SHORT"

print("\n" + "=" * 75)
print("ANATOMY OF TRADE #1: WHY 50X LEVERAGE GUARANTEES LIQUIDATION")
print("=" * 75)
print(f"Signal: {sig_type} at {df_sig['timestamp'].iloc[first_idx]}")
print(f"Entry Price: ${entry:.2f}")
print(f"Proper Strategy Stop Loss Distance (2.0 ATR): ${sl_dist:.2f} ({sl_dist/entry*100:.2f}%)")
print(f"50x Liquidation Margin: Exactly 1.00% to 1.50% adverse movement")

for k in range(first_idx, first_idx + 8):
    bar_low = df_sig["low"].iloc[k]
    adverse = (entry - bar_low) / entry * 100.0
    bar_ts = df_sig["timestamp"].iloc[k]
    status = "LIQUIDATION HIT!" if adverse >= 1.0 else "In position"
    print(f"  Bar +{k-first_idx} ({bar_ts}): Low ${bar_low:.2f} | Adverse dip: {adverse:.2f}% -> {status}")
    if adverse >= 1.0:
        break

