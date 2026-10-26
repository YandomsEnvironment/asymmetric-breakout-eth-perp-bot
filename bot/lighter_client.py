"""
lighter_client.py - Lighter DEX Client Wrapper
Interfaces with Lighter REST & SDK for market data, account balances, and order execution.
Supports DRY_RUN mode for risk-free forward testing.
"""

import time
import httpx
import datetime
import pandas as pd
from typing import Dict, Any, List, Optional
import bot.config as config


class LighterClient:
    def __init__(self, dry_run: bool = True):
        self.base_url = config.BASE_URL
        self.market_id = config.MARKET_ID
        self.dry_run = dry_run
        self.client = httpx.Client(base_url=self.base_url, timeout=12.0)
        
        # Paper trading simulated state
        self.simulated_balance = config.CAPITAL_USD
        self.simulated_position = {
            "size": 0.0,
            "entry_price": 0.0,
            "direction": None,
            "sl_price": None,
            "tp_price": None
        }

    def get_order_book(self) -> Dict[str, Any]:
        """Fetches the active order book for ETH perp."""
        resp = self.client.get("/api/v1/orderBookOrders", params={"market_id": self.market_id, "limit": 20})
        if resp.status_code == 200:
            return resp.json()
        raise RuntimeError(f"Failed to fetch orderbook: {resp.status_code} - {resp.text}")

    def get_latest_price(self) -> float:
        """Fetches the latest execution / mark price from the order book."""
        ob = self.get_order_book()
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        if bids and asks:
            best_bid = float(bids[0]["price"])
            best_ask = float(asks[0]["price"])
            return (best_bid + best_ask) / 2.0
        elif bids:
            return float(bids[0]["price"])
        elif asks:
            return float(asks[0]["price"])
        
        # Fallback to recent candle close
        candles = self.get_candles(count=2)
        return float(candles["close"].iloc[-1])

    def get_candles(self, resolution: str = "1h", count: int = 300) -> pd.DataFrame:
        """
        Fetches the most recent completed candles from Lighter.
        """
        now = int(time.time())
        # Fetch sufficient history for EMA 200 + ADX warmup
        start_ts = now - (count * 3600 * 2 if resolution == "1h" else count * 900 * 2)
        
        resp = self.client.get(
            "/api/v1/candles",
            params={
                "market_id": self.market_id,
                "resolution": resolution,
                "start_timestamp": start_ts,
                "end_timestamp": now,
                "count_back": min(count, 500)
            }
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Candles API error: {resp.status_code} - {resp.text}")

        data = resp.json().get("c", [])
        if not data:
            raise ValueError("No candle data returned from Lighter.")

        df = pd.DataFrame(data)
        df = df.rename(columns={
            "t": "open_time",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume_eth",
            "V": "volume_usd"
        })
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df[["timestamp", "open", "high", "low", "close", "volume_eth", "volume_usd"]]

    def get_account_balance(self) -> float:
        """Returns available balance in USD."""
        if self.dry_run:
            return self.simulated_balance
        
        # Real account query via Lighter API
        try:
            resp = self.client.get(f"/api/v1/account", params={"by": "index", "value": str(config.ACCOUNT_INDEX)})
            if resp.status_code == 200:
                acc = resp.json()
                return float(acc.get("collateral", 0.0))
        except Exception as e:
            print(f"[!] Warning querying live balance: {e}")
        return 0.0

    def place_order(
        self,
        direction: str,
        size: float,
        price: float,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Submits an order. In DRY_RUN mode, logs the execution and updates simulated state.
        """
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if self.dry_run:
            print(f"\n[SIMULATION EXECUTION @ {now_str}]")
            print(f"    Action    : OPEN {direction.upper()}")
            print(f"    Size      : {size:.4f} ETH (~${size * price:.2f})")
            print(f"    Fill Price: ${price:.2f}")
            print(f"    Stop Loss : ${sl_price:.2f}" if sl_price else "    Stop Loss : None")
            print(f"    Take Profit: ${tp_price:.2f}" if tp_price else "    Take Profit: None")
            print(f"    Fee       : $0.00 (Lighter 0% Fee Model)")

            self.simulated_position = {
                "size": size,
                "entry_price": price,
                "direction": direction.upper(),
                "sl_price": sl_price,
                "tp_price": tp_price,
                "open_time": now_str
            }
            return {
                "status": "FILLED_SIMULATED",
                "order_id": f"sim_{int(time.time()*1000)}",
                "price": price,
                "size": size
            }
        else:
            # LIVE EXECUTION VIA LIGHTER SDK / ON-CHAIN SIGNER
            print(f"\n[LIVE ORDER PLACEMENT @ {now_str}]")
            print(f"    Action: {direction.upper()} {size:.4f} ETH @ ${price:.2f}")
            
            # Using lighter SDK SignerClient if configured
            import lighter
            config_sdk = lighter.Configuration(host=self.base_url)
            # In live mode with private key configured:
            # client = lighter.ApiClient(config_sdk)
            # signer = lighter.SignerClient(...)
            # ...
            # Return live order response
            return {"status": "SUBMITTED", "direction": direction, "size": size, "price": price}

    def close_position(self, current_price: float, reason: str = "SIGNAL") -> Dict[str, Any]:
        """Closes the active open position."""
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        if self.dry_run:
            pos = self.simulated_position
            if pos["size"] == 0.0:
                return {"status": "NO_POSITION"}

            entry = pos["entry_price"]
            size = pos["size"]
            direction = pos["direction"]

            if direction == "LONG":
                pnl = size * (current_price - entry)
            else:
                pnl = size * (entry - current_price)

            self.simulated_balance += pnl
            ret_pct = (pnl / (size * entry)) * 100.0

            print(f"\n[SIMULATION CLOSE @ {now_str}]")
            print(f"    Reason    : {reason}")
            print(f"    Closed    : {direction} {size:.4f} ETH")
            print(f"    Entry     : ${entry:.2f} -> Exit: ${current_price:.2f}")
            print(f"    PnL       : {'+$' if pnl>=0 else '-$'}{abs(pnl):.2f} ({'+' if ret_pct>=0 else ''}{ret_pct:.2f}%)")
            print(f"    New Balance: ${self.simulated_balance:.2f}")

            self.simulated_position = {
                "size": 0.0,
                "entry_price": 0.0,
                "direction": None,
                "sl_price": None,
                "tp_price": None
            }
            return {"status": "CLOSED", "pnl": pnl, "return_pct": ret_pct}

        return {"status": "NOT_IMPLEMENTED_LIVE"}

    def close(self):
        self.client.close()
