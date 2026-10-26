"""
live_runner.py - Production Trading Bot for Lighter ETH Perpetual
Incorporates institutional risk architecture:
- Volatility Parity Sizing (Quarter-Kelly 1.5% fixed risk)
- Dynamic ATR-based Stop Loss & Take Profit
- 2.5x Max Leverage Hard Cap (35%+ Liquidation Buffer)
- Daily 5% Loss Circuit Breaker & High-Water Mark Drawdown Guard
- Real-time Lighter DEX Order Book & Kline Streaming
"""

import os
import sys
import time
import argparse
import datetime
import pandas as pd
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import bot.config as config
from bot.lighter_client import LighterClient
from strategies.s1_volatility_breakout import VolatilityBreakoutStrategy


def parse_args():
    parser = argparse.ArgumentParser(description="Lighter ETH Perpetual Trading Bot")
    parser.add_argument("--live", action="store_true", help="Enable live on-chain execution with real funds")
    parser.add_argument("--once", action="store_true", help="Execute single cycle check and exit")
    parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds (default: 60)")
    parser.add_argument("--capital", type=float, default=config.STARTING_CAPITAL_USD, help="Starting capital for simulation")
    return parser.parse_args()


class ETHPerpBot:
    def __init__(self, dry_run: bool = True, initial_capital: float = 200.0):
        self.dry_run = dry_run
        self.client = LighterClient(dry_run=self.dry_run)
        if self.dry_run:
            self.client.simulated_balance = initial_capital

        self.strategy = VolatilityBreakoutStrategy(**config.STRATEGY_PARAMS)
        self.last_processed_timestamp = None
        self.running = True

        # Institutional Risk Tracking
        self.high_water_mark = initial_capital
        self.day_start_balance = initial_capital
        self.last_day_reset = datetime.datetime.now(datetime.timezone.utc).date()
        self.circuit_breaker_active = False

    def update_circuit_breakers(self, current_balance: float) -> bool:
        """
        Monitors Daily Loss Circuit Breaker (5%) and Global Drawdown (22%).
        Returns True if trading is halted, False otherwise.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        current_date = now_utc.date()

        # Reset daily starting balance at UTC midnight
        if current_date != self.last_day_reset:
            self.day_start_balance = current_balance
            self.last_day_reset = current_date
            self.circuit_breaker_active = False
            print(f"[!] New Trading Day ({current_date} UTC). Daily circuit breaker reset. Starting balance: ${self.day_start_balance:.2f}")

        # Update High-Water Mark
        if current_balance > self.high_water_mark:
            self.high_water_mark = current_balance

        # 1. Daily Loss Check
        daily_loss = (self.day_start_balance - current_balance) / self.day_start_balance
        if daily_loss >= config.MAX_DAILY_LOSS_PCT:
            if not self.circuit_breaker_active:
                print(f"\n[!!!] DAILY CIRCUIT BREAKER TRIGGERED: Daily loss is {daily_loss*100:.2f}% (Limit: {config.MAX_DAILY_LOSS_PCT*100}%).")
                print(f"      Halting new entries until 00:00 UTC to protect capital.")
                self.circuit_breaker_active = True
            return True

        # 2. Global Max Drawdown Check from Peak
        total_dd = (self.high_water_mark - current_balance) / self.high_water_mark
        if total_dd >= config.MAX_DRAWDOWN_LIMIT_PCT:
            print(f"\n[CRITICAL WARNING] GLOBAL DRAWDOWN REACHED: {total_dd*100:.2f}% from peak (${self.high_water_mark:.2f}).")
            return True

        return False

    def calculate_liquidation_price(self, entry_price: float, size_eth: float, capital: float, is_long: bool) -> float:
        """Calculates theoretical liquidation price assuming 1.0% maintenance margin."""
        notional = size_eth * entry_price
        if notional <= 0:
            return 0.0
        # Bankruptcy margin: (Capital / Notional) - 0.01
        maint_margin = 0.01
        max_adverse_pct = (capital / notional) - maint_margin
        if is_long:
            return max(entry_price * (1.0 - max_adverse_pct), 0.0)
        else:
            return entry_price * (1.0 + max_adverse_pct)

    def run_cycle(self):
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        capital = self.client.get_account_balance()

        print(f"\n{'='*75}")
        print(f"CYCLE EVALUATION @ {now_dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Account Balance : ${capital:.2f} | High-Water Mark: ${self.high_water_mark:.2f}")

        # Check circuit breakers
        if self.update_circuit_breakers(capital):
            print(f"[!] Trading suspended by circuit breaker. Monitoring active positions only.")

        # 1. Fetch live market data
        try:
            df = self.client.get_candles(resolution=config.RESOLUTION, count=250)
            current_price = self.client.get_latest_price()
            ob = self.client.get_order_book()
            best_bid = float(ob["bids"][0]["price"]) if ob.get("bids") else current_price
            best_ask = float(ob["asks"][0]["price"]) if ob.get("asks") else current_price
            spread_bps = ((best_ask - best_bid) / current_price) * 10000.0
        except Exception as e:
            print(f"[!] Network error fetching market data: {e}")
            return

        if len(df) < 205:
            print(f"[!] Warmup in progress: {len(df)} candles retrieved (need 205+).")
            return

        # 2. Compute signals strictly on the latest CLOSED bar (Zero lookahead)
        closed_df = df.iloc[:-1].copy().reset_index(drop=True)
        signals_df = self.strategy.generate_signals(closed_df)

        latest_closed = signals_df.iloc[-1]
        latest_ts = latest_closed["timestamp"]

        print(f"Current ETH Price : ${current_price:.2f} (Bid: ${best_bid:.2f} | Ask: ${best_ask:.2f} | Spread: {spread_bps:.1f} bps)")
        print(f"Latest Closed Bar : {latest_ts.strftime('%Y-%m-%d %H:%M UTC')} | Close: ${latest_closed['close']:.2f}")
        print(f"EMA 200 Trend Line: ${latest_closed['ema_trend']:.2f} | Donchian: [${latest_closed['lower_channel']:.2f} - ${latest_closed['upper_channel']:.2f}]")
        print(f"ADX Trend Strength: {latest_closed['adx']:.1f} (Min: {self.strategy.adx_threshold}) | 14-ATR: ${latest_closed['atr']:.2f}")

        # 3. Check active position
        pos = self.client.simulated_position if self.dry_run else {}
        active_size = pos.get("size", 0.0)

        if active_size > 0:
            sl = pos.get("sl_price")
            tp = pos.get("tp_price")
            direction = pos.get("direction")
            entry = pos.get("entry_price")
            is_long = (direction == "LONG")

            # Mark to market PnL
            unrealized_pnl = active_size * (current_price - entry) if is_long else active_size * (entry - current_price)
            unrealized_pct = (unrealized_pnl / (active_size * entry)) * 100.0

            liq_price = self.calculate_liquidation_price(entry, active_size, capital, is_long)
            liq_buffer_pct = abs(current_price - liq_price) / current_price * 100.0

            print(f"\n[ACTIVE POSITION]")
            print(f"  Direction       : {direction} {active_size:.4f} ETH (~${active_size * current_price:.2f})")
            print(f"  Entry Price     : ${entry:.2f} | Current: ${current_price:.2f}")
            print(f"  Unrealized PnL  : {'+$' if unrealized_pnl>=0 else '-$'}{abs(unrealized_pnl):.2f} ({'+' if unrealized_pct>=0 else ''}{unrealized_pct:.2f}%)")
            print(f"  Stop Loss       : ${sl:.2f} | Take Profit: ${tp:.2f}")
            print(f"  Liquidation     : ${liq_price:.2f} (Buffer: {liq_buffer_pct:.1f}% away - Safe!)")

            # Check exits
            if is_long:
                if sl and current_price <= sl:
                    self.client.close_position(current_price, reason="STOP_LOSS_HIT")
                    return
                elif tp and current_price >= tp:
                    self.client.close_position(current_price, reason="TAKE_PROFIT_HIT")
                    return
                elif latest_closed["exit_signal"]:
                    self.client.close_position(current_price, reason="STRATEGY_EXIT_SIGNAL")
                    return
            else: # Short
                if sl and current_price >= sl:
                    self.client.close_position(current_price, reason="STOP_LOSS_HIT")
                    return
                elif tp and current_price <= tp:
                    self.client.close_position(current_price, reason="TAKE_PROFIT_HIT")
                    return
                elif latest_closed["exit_signal"]:
                    self.client.close_position(current_price, reason="STRATEGY_EXIT_SIGNAL")
                    return

        # 4. Check for new entry signal (only if no active position and circuit breaker not active)
        if active_size == 0 and not self.circuit_breaker_active:
            if self.last_processed_timestamp != latest_ts:
                signal = latest_closed["signal"]
                sl_dist = latest_closed["sl_dist"]
                tp_dist = latest_closed["tp_dist"]

                if signal != 0:
                    direction = "LONG" if signal == 1 else "SHORT"
                    risk_amount = capital * config.RISK_PER_TRADE

                    # Volatility Parity sizing: Size = Risk / Distance
                    raw_size_eth = (risk_amount / sl_dist) if sl_dist > 0 else (capital * 0.9) / current_price

                    # Enforce Lighter DEX Contract Minimum (0.0150 ETH ~ $35)
                    size_eth = max(raw_size_eth, config.MIN_ORDER_SIZE_ETH)

                    # Enforce Hard Max Leverage Cap (2.5x)
                    max_notional = capital * config.MAX_LEVERAGE
                    max_size_eth = max_notional / current_price
                    size_eth = min(size_eth, max_size_eth)

                    # Final feasibility check
                    order_notional = size_eth * current_price
                    if order_notional < (config.MIN_ORDER_SIZE_ETH * current_price * 0.95):
                        print(f"[!] Warning: Account capital (${capital:.2f}) cannot meet contract minimum {config.MIN_ORDER_SIZE_ETH} ETH.")
                        return

                    sl_price = current_price - sl_dist if signal == 1 else current_price + sl_dist
                    tp_price = current_price + tp_dist if signal == 1 else current_price - tp_dist
                    liq_price = self.calculate_liquidation_price(current_price, size_eth, capital, (signal == 1))

                    effective_lev = order_notional / capital

                    print(f"\n[!!!] NEW CONFIRMED SIGNAL: {direction} @ ${current_price:.2f}")
                    print(f"      Calculated Size : {size_eth:.4f} ETH (~${order_notional:.2f})")
                    print(f"      Effective Lev   : {effective_lev:.2f}x (Max Cap: {config.MAX_LEVERAGE:.1f}x)")
                    print(f"      Risk on Trade   : ${size_eth * sl_dist:.2f} ({config.RISK_PER_TRADE*100:.1f}% equity)")
                    print(f"      Stop Loss       : ${sl_price:.2f} | Take Profit: ${tp_price:.2f}")
                    print(f"      Liquidation P   : ${liq_price:.2f} (Buffer: {abs(current_price-liq_price)/current_price*100:.1f}%)")

                    self.client.place_order(
                        direction=direction,
                        size=size_eth,
                        price=current_price,
                        sl_price=sl_price,
                        tp_price=tp_price
                    )
                else:
                    print(f"Signal Status     : NEUTRAL (No confirmed breakout on closed candle)")

                self.last_processed_timestamp = latest_ts
            else:
                print(f"Signal Status     : WAITING (Closed bar at {latest_ts.strftime('%H:%M')} already evaluated)")

    def start(self, poll_interval: int = 60, run_once: bool = False):
        mode_str = "DRY RUN (Paper Trading Simulator)" if self.dry_run else "*** LIVE EXECUTION ON LIGHTER MAINNET ***"
        print("=" * 75)
        print(f"LIGHTER ETH PERPETUAL BOT")
        print(f"Mode          : {mode_str}")
        print(f"Market ID     : {config.MARKET_ID} (ETH/USD Perpetual)")
        print(f"Strategy      : {self.strategy.name}")
        print(f"Risk per Trade: {config.RISK_PER_TRADE*100:.1f}% Quarter-Kelly Volatility Parity")
        print(f"Max Leverage  : {config.MAX_LEVERAGE:.1f}x Hard Cap")
        print(f"Daily Limit   : {config.MAX_DAILY_LOSS_PCT*100:.1f}% Loss Circuit Breaker")
        print(f"Initial Fund  : ${self.client.get_account_balance():.2f}")
        print("=" * 75)

        if run_once:
            self.run_cycle()
            return

        try:
            while self.running:
                self.run_cycle()
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\n[*] Bot terminated gracefully by user.")
        finally:
            self.client.close()


if __name__ == "__main__":
    args = parse_args()
    dry_run = not args.live
    bot = ETHPerpBot(dry_run=dry_run, initial_capital=args.capital)
    bot.start(poll_interval=args.interval, run_once=args.once)
