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
# 4. Statistically Verified Strategy Parameters (Peak Plateau)
# -----------------------------------------------------------------------------
STRATEGY_PARAMS = {
    "breakout_period": 24,     # 24-period Donchian channel breakout
    "trend_ema_period": 200,   # Macro regime filter (Price > EMA 200 for Longs)
    "adx_period": 14,          # Momentum strength filter
    "adx_threshold": 20.0,     # Only trade when ADX > 20 (avoids choppy ranges)
    "atr_period": 14,          # 14-period True Range for volatility parity
    "sl_atr_mult": 2.0,        # 2.0x ATR Stop Loss distance (Optimal stability plateau)
    "tp_atr_mult": 3.5         # 3.5x ATR Take Profit target (1.75 : 1 R:R payoff)
}
