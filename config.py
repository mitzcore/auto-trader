# ===================================================================================
# --- Configuration File ---
# ===================================================================================

# Trading settings
TRADE_ORDERS = False # Master switch to enable/disable real order execution
PAPER_TRADE = True # Set to True to enable paper trading mode

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
ZONE_TIMEFRAMES = ['30m','15m','10m','5m','3m','2m'] # Timeframes for finding demand zones. E.g., ['2m', '5m', '30m']

# Data collection settings
POLL_INTERVAL_SECONDS = 60  # Interval in seconds for the AnalysisService to poll for new completed bars.

# Log file configuration
LOG_FILE = "trading_bot.log"
BACKTEST_LOG_LEVEL = "DEBUG"  # Logging level for backtests: DEBUG, INFO, WARNING, ERROR

# Demand Zone settings
DEMAND_ZONE_OFFSET_TOP = 0.10
DEMAND_ZONE_OFFSET_BOTTOM = 0.10
BULLISH_WICK_RATIO = 0.70
BEARISH_WICK_RATIO = 0.60

# Pattern Detection settings
PATTERN_TIMEFRAMES = ['2m','3m','5m'] # Timeframes for candlestick pattern confirmation

# --- Custom Demand Zones ---
# Add custom demand zones here. If this list is not empty, the AnalysisService will be disabled
# and the first zone in this list will be loaded as the active demand zone.
# Example: CUSTOM_DEMAND_ZONES = [{"zone_top": 530.0, "zone_bottom": 529.5}]

CUSTOM_DEMAND_ZONES = [
    {"zone_top": 682.13, "zone_bottom": 681.36},
]

# --- Candlestick Pattern Thresholds ---
# These values are tunable to adjust pattern sensitivity.
DOJI_PRECISION = 0.20           # Max body size (as % of range) for a standard Doji.
DRAGONFLY_DOJI_PRECISION = 0.20  # Max body size (as % of range) for the stricter Dragonfly Doji check.
DRAGONFLY_DOJI_MAX_UPPER_WICK = 0.7 # Max upper wick size (as % of range) for a Dragonfly Doji.

# --- C5 Bullish Candle Definition ---
C5_BULLISH_MIN_BODY_PCT = 0.30 # Min body size (as % of range) for the c5 bullish candle.
C1_MAX_BODY_PCT = 0.40

# --- Hammer Pattern ---
HAMMER_LOWER_WICK_RATIO = 2.0 # Lower wick must be at least this many times the body size.
HAMMER_MAX_UPPER_WICK_RATIO = 1.0 # Upper wick must be less than this many times the body size.

# --- Spinning Top Pattern ---
SPINNING_TOP_MAX_BODY_PCT = 0.3 # Max body size (as % of range) for a Spinning Top.
SPINNING_TOP_MIN_WICK_BODY_RATIO = 1.0 # Wicks must be at least this many times the body size.

# --- Marubozu Pattern ---
MARUBOZU_MAX_WICK_PCT = 0.05 # Max wick size (as % of range) for a Marubozu candle.

