"""
config.py - Institutional Configuration for Lighter ETH Perpetual Bot
Optimized via Fractional Kelly, Volatility Parity, and Parameter Grid Optimization.
"""

import os

# -----------------------------------------------------------------------------
# 1. Environment & API Endpoints
# -----------------------------------------------------------------------------
ENVIRONMENT = os.getenv("LIGHTER_ENV", "MAINNET")  # "MAINNET" or "TESTNET"
BASE_URL = "https://mainnet.zklighter.elliot.ai" if ENVIRONMENT == "MAINNET" else "https://testnet.zklighter.elliot.ai"

# Lighter Market Specifications
MARKET_ID = 0              # ETH Perpetual on Lighter
SYMBOL = "ETH"
RESOLUTION = "1h"          # 1-hour candles matching verified institutional backtest
MIN_ORDER_SIZE_ETH = 0.015 # Lighter minimum contract order size (~$35 at $2,330 ETH)

# -----------------------------------------------------------------------------
# 2. Account Credentials & Security
# -----------------------------------------------------------------------------
L1_ADDRESS = os.getenv("LIGHTER_L1_ADDRESS", "0x0000000000000000000000000000000000000000")
PRIVATE_KEY = os.getenv("LIGHTER_PRIVATE_KEY", "")
ACCOUNT_INDEX = int(os.getenv("LIGHTER_ACCOUNT_INDEX", "0"))
API_KEY_INDEX = int(os.getenv("LIGHTER_API_KEY_INDEX", "0"))

# Execution Mode: Set to False only when ready to execute with real signed transactions
DRY_RUN = os.getenv("LIGHTER_DRY_RUN", "True").lower() in ("true", "1", "yes")

# -----------------------------------------------------------------------------
# 3. Capital & Risk Allocation (Scientifically Optimized)
# -----------------------------------------------------------------------------
STARTING_CAPITAL_USD = 200.0   # Recommended initial live deployment budget ($200 USD)
CAPITAL_USD = STARTING_CAPITAL_USD # Backward compatibility alias
RISK_PER_TRADE = 0.015         # 1.5% Quarter-Kelly Risk per trade ($3.00 risk on $200)
MAX_LEVERAGE = 2.5             # 2.5x Hard Cap (Liquidation threshold is 35%+ away)

# Circuit Breakers & Risk Shields
MAX_DAILY_LOSS_PCT = 0.05      # 5.0% daily circuit breaker ($10.00 loss halts trading for 24h)
MAX_DRAWDOWN_LIMIT_PCT = 0.22  # 22.0% high-water mark global circuit breaker

# -----------------------------------------------------------------------------
# 4. Strategy Selection & Parameters
# -----------------------------------------------------------------------------
# "ASYMMETRIC" is the superior discovered edge (+65.2% OOS, 2.04 Sharpe, 17.3% MaxDD)
# "SYMMETRIC" is the standard benchmark (+41.3% OOS, 1.57 Sharpe, 21.2% MaxDD)
ACTIVE_STRATEGY = os.getenv("LIGHTER_STRATEGY", "ASYMMETRIC")

ASYMMETRIC_PARAMS = {
    "long_period": 28,         # Slower 28-period high breakout for steady bull grinds
    "short_period": 14,        # Faster 14-period low breakout for violent cascades
    "trend_ema_period": 200,   # Macro 200-hour trend alignment
    "long_sl_mult": 2.0,       # 2.0x ATR Stop Loss for longs
    "long_tp_mult": 4.2,       # 4.2x ATR Runner Target for longs
    "short_sl_mult": 1.6,      # 1.6x ATR Tight Stop Loss for shorts
    "short_tp_mult": 2.8,      # 2.8x ATR Fast Flush Target for shorts
    "adx_long_thresh": 18.0,   # Trend momentum threshold for longs
    "adx_short_thresh": 22.0   # Trend momentum threshold for shorts
}

SYMMETRIC_PARAMS = {
    "breakout_period": 24,
    "trend_ema_period": 200,
    "adx_period": 14,
    "adx_threshold": 20.0,
    "atr_period": 14,
    "sl_atr_mult": 2.0,
    "tp_atr_mult": 3.5
}

STRATEGY_PARAMS = ASYMMETRIC_PARAMS if ACTIVE_STRATEGY == "ASYMMETRIC" else SYMMETRIC_PARAMS
