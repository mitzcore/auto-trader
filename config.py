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
SIGNAL_TIMEFRAMES = ['2m'] # Lower timeframes for finding entry signals

# Data collection settings
POLL_INTERVAL_SECONDS = 25  # Collect ticks every 5 seconds
DATA_WINDOW_HOURS = 4      # Keep the last 4 hours of tick data in memory

# Log file configuration
LOG_FILE = "trading_bot.log"

# Demand Zone settings
DEMAND_ZONE_OFFSET_TOP = 0.0
DEMAND_ZONE_OFFSET_BOTTOM = 0.0