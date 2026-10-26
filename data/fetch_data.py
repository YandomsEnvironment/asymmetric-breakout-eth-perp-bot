"""
fetch_data.py - Real-world historic price downloader for ETH Perpetual on Lighter DEX
Downloads authoritative historical klines from Lighter Mainnet API (market_id: 0).
"""

import os
import time
import datetime
import httpx
import pandas as pd


def fetch_lighter_candles(
    market_id: int = 0,
    resolution: str = "1h",
    min_timestamp: int = 1735689600,  # 2025-01-01
    save_dir: str = None
) -> pd.DataFrame:
    """
    Paginates backward from current timestamp to retrieve the entire historical candle set
    from Lighter Mainnet API for ETH Perp.
    """
    if save_dir is None:
        save_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(save_dir, exist_ok=True)
    filename = os.path.join(save_dir, f"lighter_eth_{resolution}.csv")

    base_url = "https://mainnet.zklighter.elliot.ai/api/v1/candles"
    client = httpx.Client(timeout=15.0)

    all_candles = []
    seen_timestamps = set()
    current_end_ts = int(time.time())

    print(f"[*] Starting download for Lighter ETH Perp (market {market_id}, {resolution})...")
    batch_num = 0

    while current_end_ts > min_timestamp:
        batch_num += 1
        params = {
            "market_id": market_id,
            "resolution": resolution,
            "start_timestamp": min_timestamp,
            "end_timestamp": current_end_ts,
            "count_back": 500
        }
        
        success = False
        batch = []
        for attempt in range(4):
            try:
                resp = client.get(base_url, params=params)
                if resp.status_code == 200:
                    batch = resp.json().get("c", [])
                    success = True
                    break
                else:
                    time.sleep(1.0 * (attempt + 1))
            except Exception as e:
                time.sleep(1.0 * (attempt + 1))

        if not success or not batch:
            print(f"[*] Reached beginning of data or no further records.")
            break

        # Filter out duplicates
        new_records = [c for c in batch if c["t"] not in seen_timestamps]
        if not new_records:
            break

        for c in new_records:
            seen_timestamps.add(c["t"])

        all_candles.extend(new_records)
        
        # Next batch moves back in time
        earliest_in_batch = min(c["t"] for c in batch)
        current_end_ts = int(earliest_in_batch / 1000) - 1

        if batch_num % 10 == 0:
            earliest_dt = datetime.datetime.fromtimestamp(earliest_in_batch / 1000, tz=datetime.timezone.utc)
            print(f"    Batch {batch_num}: retrieved {len(all_candles)} candles (reached {earliest_dt})...")

        time.sleep(0.05)

    client.close()

    if not all_candles:
        raise ValueError(f"No candles retrieved for resolution {resolution}")

    # Build clean DataFrame
    df = pd.DataFrame(all_candles)
    # Rename columns to standard financial names
    # t: open time (ms), o: open, h: high, l: low, c: close, v: volume (ETH), V: quote volume (USD)
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
    df = df.drop_duplicates(subset=["timestamp"])

    # Keep essential columns
    cols = ["timestamp", "open", "high", "low", "close", "volume_eth", "volume_usd"]
    df = df[[c for c in cols if c in df.columns]]

    df.to_csv(filename, index=False)
    print(f"[+] Download complete! Saved {len(df)} candles to: {filename}")
    print(f"    Span: {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}")
    return df


if __name__ == "__main__":
    # Fetch 1h candles across full Lighter lifetime
    fetch_lighter_candles(market_id=0, resolution="1h", min_timestamp=1735689600)

    # Fetch 15m candles across recent months
    # 1751328000 = approx mid-2025
    fetch_lighter_candles(market_id=0, resolution="15m", min_timestamp=1751328000)
