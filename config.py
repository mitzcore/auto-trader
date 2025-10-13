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
ZONE_TIMEFRAMES = ['5m','15m'] # Timeframes for finding demand zones. E.g., ['2m', '5m', '1h']

# Data collection settings
POLL_INTERVAL_SECONDS = 60  # Interval in seconds for the AnalysisService to poll for new completed bars.

# Log file configuration
LOG_FILE = "trading_bot.log"

# Demand Zone settings
DEMAND_ZONE_OFFSET_TOP = 0.20
DEMAND_ZONE_OFFSET_BOTTOM = 0.20
BULLISH_WICK_RATIO = 0.5 # Max wick size relative to body for the bullish candle.
BEARISH_WICK_RATIO = 0.7 # Max upper wick size for the bearish candle relative to the bullish body.

# Pattern Detection settings
PATTERN_TIMEFRAMES = ['2m','3m'] # Timeframes for candlestick pattern confirmation

# --- Custom Demand Zones ---
# Add custom demand zones here. If this list is not empty, the AnalysisService will be disabled
# and the first zone in this list will be loaded as the active demand zone.
# Example: CUSTOM_DEMAND_ZONES = [{"zone_top": 530.0, "zone_bottom": 529.5}]
CUSTOM_DEMAND_ZONES = []
#    {"zone_top": 530.0, "zone_bottom": 529.5},
#    {"zone_top": 525.0, "zone_bottom": 524.5},
#    {"zone_top": 520.0, "zone_bottom": 519.5}
#]
# [{"zone_top": 530.0, "zone_bottom": 529.5}]

# --- Candlestick Pattern Thresholds ---
# These values are tunable to adjust pattern sensitivity.
DOJI_PRECISION = 0.15           # Max body size (as % of range) for a standard Doji.
DRAGONFLY_DOJI_PRECISION = 0.10  # Max body size (as % of range) for the stricter Dragonfly Doji check.
DRAGONFLY_DOJI_MAX_UPPER_WICK = 0.4 # Max upper wick size (as % of range) for a Dragonfly Doji.

# Thresholds for a "Strong Bullish Candle"
STRONG_BULLISH_MIN_BODY_PCT = 0.5  # Body must be at least 70% of the total candle range.
STRONG_BULLISH_MAX_WICK_PCT = 0.30 # Wicks must be less than 25% of the total candle range.
