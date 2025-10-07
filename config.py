# ===================================================================================
# --- Configuration File ---
# ===================================================================================

# Trading settings
TRADE_ORDERS = False # Master switch to enable/disable real order execution

# IB Gateway/TWS connection settings
IB_HOST = '127.0.0.1'
IB_PORT = 4001  # 4001 for TWS, 4002 for Gateway
IB_CLIENT_ID = 1

# Ticker and contract details
SYMBOL = 'SPY'
EXCHANGE = 'SMART'  # Use SMART for aggregated data from all available exchanges
CURRENCY = 'USD'

# Timeframe Configuration
USE_RTH_ONLY = True # Set to True to only fetch data for regular trading hours. False includes pre/post market.
ZONE_TIMEFRAMES = ['5m'] # Timeframes for finding demand zones. E.g., ['2m', '5m', '1h']

# Data collection settings
POLL_INTERVAL_SECONDS = 25  # Collect ticks every 5 seconds
DATA_WINDOW_HOURS = 2      # Keep the last 4 hours of tick data in memory

# Log file configuration
LOG_FILE = "trading_bot.log"

# Demand Zone settings
DEMAND_ZONE_OFFSET_TOP = 0.0
DEMAND_ZONE_OFFSET_BOTTOM = 0.0
BULLISH_WICK_RATIO = 0.5 # Max wick size relative to body for the bullish candle.
BEARISH_WICK_RATIO = 0.5 # Max upper wick size for the bearish candle relative to the bullish body.

# Pattern Detection settings
PATTERN_TIMEFRAME = '5m' # Timeframe for candlestick pattern confirmation

# --- Candlestick Pattern Thresholds (from candlestick.txt) ---
# These values are tunable to adjust pattern sensitivity.
CANDLE_VERY_SMALL_BODY = 0.05  # Threshold for a body to be considered a Doji (<= 5% of range)
CANDLE_SMALL_BODY = 0.15       # Threshold for a body to be considered "small" (e.g., for Hammer, Spinning Top)
CANDLE_NO_WICK = 0.02          # Threshold for a wick to be considered non-existent (<= 2% of range)
CANDLE_LONG_WICK_FACTOR = 2.0  # Factor for a wick to be considered "long" relative to the body (e.g., Hammer)
