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
BULLISH_WICK_RATIO = 0.5 # Max wick size relative to body for the bullish candle.
BEARISH_WICK_RATIO = 0.5 # Max upper wick size for the bearish candle relative to the bullish body.

# Pattern Detection settings
PATTERN_TIMEFRAMES = ['2m','3m','5m'] # Timeframes for candlestick pattern confirmation

# --- Custom Demand Zones ---
# Add custom demand zones here. If this list is not empty, the AnalysisService will be disabled
# and the first zone in this list will be loaded as the active demand zone.
# Example: CUSTOM_DEMAND_ZONES = [{"zone_top": 530.0, "zone_bottom": 529.5}]

CUSTOM_DEMAND_ZONES = [
    {"zone_top": 667.90, "zone_bottom": 663.48},
]

# --- Candlestick Pattern Thresholds ---
# These values are tunable to adjust pattern sensitivity.

# Add a flag to enable/disable demand zone analysis
DEMAND_ZONE_TRADING = True

DOJI_PRECISION = 0.30           # Max body size (as % of range) for a standard Doji.
DRAGONFLY_DOJI_PRECISION = 0.30  # Max body size (as % of range) for the stricter Dragonfly Doji check.
DRAGONFLY_DOJI_MAX_UPPER_WICK = 0.5 # Max upper wick size (as % of range) for a Dragonfly Doji.

# Thresholds for a "Strong Bullish Candle"
STRONG_BULLISH_MIN_BODY_PCT = 0.50  # Body must be at least 70% of the total candle range.
STRONG_BULLISH_MAX_WICK_PCT = 0.60 # Wicks must be less than 25% of the total candle range.

# Thresholds for C1 (indecision candle) in a two-candle confirmation pattern
C1_MIN_BODY_PCT = 0.30 # Minimum body size (as % of range) for C1 to be considered a valid indecision candle.
C1_MIN_LOWER_WICK_PCT = 0.20 # Minimum lower wick size (as % of range) for C1, relative to its body.
C1_MAX_BODY_PCT = 0.50  # Maximum body size (as % of range) for a C1 indecision candle.

HAMMER_LOWER_WICK_RATIO = 2.0  # Lower wick must be at least twice the body size.
HAMMER_MAX_UPPER_WICK_RATIO = 0.5  # Upper wick should be small compared to the body.

SPINNING_TOP_MAX_BODY_PCT = 0.3  # Body must be less than 30% of the total range.
SPINNING_TOP_MIN_WICK_BODY_RATIO = 1.5  # Wicks should be at least 1.5x the body.

MARUBOZU_MAX_WICK_PCT = 0.05  # Maximum wick size (as % of range) for a Marubozu.

C5_BULLISH_MIN_BODY_PCT = 0.6  # Body must be at least 70% of the total range for a C5 bullish candle.

NORMAL_BEARISH_MIN_BODY_PCT = 0.7  # Body must be at least 70% of the total range for a normal bearish candle.
NEUTRAL_BEARISH_MIN_BODY_PCT = 0.3 # Body must be at least 30% of the total range for a neutral bearish candle.

SIGNAL_TIMEFRAMES = ['2m', '3m', '5m'] # Timeframes for trade signal generation.
