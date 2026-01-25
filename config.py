"""Central configuration for algotrade services.

This file keeps runtime toggles and tuning knobs grouped by feature area to
make it easy to audit or override defaults per environment.
"""

# ---------------------------------------------------------------------------
# Trading & execution
# ---------------------------------------------------------------------------
TRADE_ORDERS = True  # Master switch for live order routing
PAPER_TRADE = False  # Enable paper trading mode (no real orders)

# ---------------------------------------------------------------------------
# Order exit targets
# ---------------------------------------------------------------------------
# Profit taking: Fixed percentage target (limit order)
# Stop loss: Dynamic based on SPY swing low break
TAKE_PROFIT_PCT = 0.20     # Take profit percentage (0.20 = +20%)
STOP_LOSS_PCT = 0.10       # [DEPRECATED] Legacy stop loss - not used with SPY monitoring

# ---------------------------------------------------------------------------
# Commission Settings
# ---------------------------------------------------------------------------
COMMISSION_PER_CONTRACT = 0.80  # Commission per contract per transaction ($0.80 buy + $0.80 sell = $1.60 round trip)

# ---------------------------------------------------------------------------
# Order Execution Settings
# ---------------------------------------------------------------------------
ORDER_FILL_POLL_INTERVAL = 0.1   # Seconds between fill status checks (100ms)
ORDER_FILL_TIMEOUT = 10.0        # Max seconds to wait for order fill
USE_ACTUAL_FILL_PRICE = True     # Use actual fill price for OCO (vs estimated ask)

# ---------------------------------------------------------------------------
# Position Sizing (Dynamic Contract Quantity)
# ---------------------------------------------------------------------------
# Testing Mode: Set to False to always use 1 contract (simpler for initial testing)
# Production Mode: Set to True to use dynamic sizing based on target amount
POSITION_SIZE_ENABLED = False    # TESTING: Always 1 contract (switch to True for dynamic sizing)
TRADE_TARGET_AMOUNT = 260        # Target dollar amount per trade (used when ENABLED = True)
TRADE_MIN_AMOUNT = 100           # Minimum acceptable trade amount (used when ENABLED = True)
TRADE_MAX_AMOUNT = 300           # Maximum acceptable trade amount (used when ENABLED = True)

# ---------------------------------------------------------------------------
# Strike Selection (ITM Strategy for Lower Commission Impact)
# ---------------------------------------------------------------------------
# ITM options = higher premium, fewer contracts, lower commission %, tighter spreads
# Trade-off: Lower leverage but more consistent moves
STRIKE_SELECTION_MODE = "ITM"    # "ITM", "ATM", or "OTM"
ITM_OFFSET = 1                   # Dollars in-the-money for calls (SPY @ 590 -> strike 585)
OTM_OFFSET = 2                   # Dollars out-of-the-money for calls (SPY @ 590 -> strike 593)
# Note: For ITM calls, strike < SPY price. For OTM calls, strike > SPY price.

# ---------------------------------------------------------------------------
# Strike Test Mode (Parallel ITM/ATM/OTM Testing)
# ---------------------------------------------------------------------------
# When enabled, places 3 separate trades per signal (1 ITM, 1 ATM, 1 OTM)
# Each trade is tracked independently with pattern_type suffix (-ITM, -ATM, -OTM)
# Disable after testing to return to normal single-strike operation
STRIKE_TEST_MODE = False          # Enable parallel strike testing
STRIKE_TEST_QUANTITY = 1          # Contracts per strike type during test (recommend 1)

# OCO Monitoring Settings
OCO_MONITOR_POLL_INTERVAL = 1.0  # Seconds between OCO status checks
OCO_MONITOR_TIMEOUT = 28800      # Max seconds to monitor (8 hours = market day)

# ---------------------------------------------------------------------------
# Dual Stop Loss Monitoring Settings
# ---------------------------------------------------------------------------
# Two independent stop loss mechanisms (whichever triggers first wins):
# 1. Option Max Loss - protects against theta decay, IV collapse, time erosion
# 2. SPY Support Break - protects against technical breakdown, trend reversal

# Option Price Stop (Max Loss Cap)
OPTION_STOP_ENABLED = True          # Enable option price monitoring for max loss
OPTION_STOP_POLL_INTERVAL = 15      # Seconds between option price checks (15s)
OPTION_MAX_LOSS_PCT = 0.50          # Max loss percentage before stop (0.30 = -30%)

# SPY Price Stop (Support Break)
SPY_STOP_ENABLED = True             # Enable SPY price monitoring for support break
SPY_STOP_POLL_INTERVAL = 30         # Seconds between SPY price checks (30s)
SPY_SWING_LOW_CANDLES = 15          # Number of candles to look back for swing low
SPY_STOP_BUFFER_DOLLARS = 0.10      # Dollars below swing low to trigger stop ($0.10)

# ---------------------------------------------------------------------------
# Execution Broker Selection
# ---------------------------------------------------------------------------
EXECUTION_BROKER = "tradestation"  # "ib" or "tradestation"

# ---------------------------------------------------------------------------
# Interactive Brokers connectivity (used for market data even with TradeStation)
# ---------------------------------------------------------------------------
IB_HOST = "127.0.0.1"
IB_PORT = 4001        # 4001 for TWS, 4002 for Gateway
IB_CLIENT_ID = 1

# ---------------------------------------------------------------------------
# TradeStation API connectivity (Auth0/v3)
# ---------------------------------------------------------------------------
TRADESTATION_CLIENT_ID = "n7HNDAkgFa3dvfzY9CO3DFPfYBY1AYqg"
TRADESTATION_CLIENT_SECRET = "0myfbMgbButqbFHcbUw0eml5_ZX3EbzQwudbu5pFdBZwRA-SbdB3x7YiZDM2ebzK"
TRADESTATION_ACCOUNT_ID = "11955076"
TRADESTATION_REFRESH_TOKEN = "2jX3950fK4moiVoPhRmeuCVM-QK1Dx9lG6COOE7Ir898i"
TRADESTATION_BASE_URL = "https://api.tradestation.com/v3"
TRADESTATION_ENVIRONMENT = "live"  # "live" or "sim" (simulation)

# ---------------------------------------------------------------------------
# Instrument metadata
# ---------------------------------------------------------------------------
SYMBOL = "SPY"  # Default symbol (used when running single symbol)
EXCHANGE = "SMART"    # SMART aggregates across exchanges
CURRENCY = "USD"

# Strike spacing configuration (varies by symbol)
# SPY uses $1 strikes, but other symbols may differ:
# - NVDA: $2.50 or $5.00 strikes depending on price
# - TSLA: $5.00 strikes
# - QQQ: $1.00 strikes
STRIKE_SPACING = 1.0  # Dollar spacing between strikes (default for SPY)

# ---------------------------------------------------------------------------
# Multi-Symbol Configuration (for launcher.py)
# ---------------------------------------------------------------------------
# When running launcher.py, it will spawn one process per enabled symbol
# Each symbol can have custom settings (strike spacing, strike selection, etc.)
SYMBOLS_CONFIG = {
    "SPY": {
        "enabled": True,
        "strike_spacing": 1.0,
        "client_id_offset": 0,  # IB_CLIENT_ID + this offset
        "timeframes": ["2m", "3m"],  # Overrides TRADING_TIMEFRAMES if set
        # Strike selection (0DTE moves fast, ITM is safer)
        "strike_selection_mode": "ITM",  # "ITM", "ATM", or "OTM"
        "itm_offset": 1,   # $1 ITM for SPY
        "otm_offset": 2,   # $2 OTM for SPY
    },
    "TSLA": {
        "enabled": False,  # Set to True to enable
        "strike_spacing": 2.5,
        "client_id_offset": 10,
        "timeframes": ["5m", "10m"],
        # QQQ similar to SPY (both 0DTE, similar liquidity)
        "strike_selection_mode": "OTM",
        "itm_offset": 1,
        "otm_offset": 4,
        "min_drop_pct": 0.0015,
    },
    "NVDA": {
        "enabled": False,  # Set to True to enable
        "strike_spacing": 2.5,  # NVDA uses $2.50 strikes
        "client_id_offset": 20,
        "timeframes": ["5m", "10m"],
        # NVDA is weekly, more volatile - ATM or slight OTM might be better
        "strike_selection_mode": "OTM",  # ATM for weeklies (more time = more directional)
        "itm_offset": 5,   # $5 ITM if switched to ITM
        "otm_offset": 2,   # $5 OTM if switched to OTM
        # Optional: pattern settings (NVDA more volatile, needs bigger drop)
        "min_drop_pct": 0.0015,  # 0.20% might be too tight for NVDA
    }
}

# Note: When launcher spawns a process for a symbol:
# - Sets SYMBOL to the symbol key (e.g., "SPY", "QQQ", "NVDA")
# - Sets STRIKE_SPACING from symbol config
# - Sets STRIKE_SELECTION_MODE from symbol config
# - Sets ITM_OFFSET and OTM_OFFSET from symbol config
# - Sets IB_CLIENT_ID = IB_CLIENT_ID + client_id_offset
# - Sets LOG_FILE to include symbol (e.g., trading_bot_SPY.log)

# ---------------------------------------------------------------------------
# Data acquisition windows
# ---------------------------------------------------------------------------
USE_RTH_ONLY = True    # Limit data requests to regular trading hours
ZONE_TIMEFRAMES = ["30m", "15m", "10m", "5m", "3m", "2m"]
PATTERN_TIMEFRAMES = ["2m","3m"]
SIGNAL_TIMEFRAMES =  ["1m", "2m", "3m"]
POLL_INTERVAL_SECONDS = 15  # AnalysisService polling cadence
CANDLE_BOUNDARY_BUFFER_SECONDS = 2  # Seconds to wait after candle close before fetching

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE = "trading_bot.log"
BACKTEST_LOG_LEVEL = "DEBUG"  # DEBUG, INFO, WARNING, ERROR
PATTERN_LOG_LEVEL = "DEBUG"    # Verbosity for candle ingestion/evaluation logs (changed to DEBUG for troubleshooting)

# Backtest stop loss simulation settings
BACKTEST_STOP_CHECK_TIMEFRAME = "2m"  # Timeframe for stop check bars (1m, 2m, 3m, 5m, 15m)
BACKTEST_STOP_CHECK_BARS = 45         # Number of bars to check after entry
BACKTEST_WIN_BOUNCE_DOLLARS = 0.50    # Price must move this much above entry price to count as WIN

# Backtest demand zone detection mode
# True  = Detect zones dynamically from ZONE_TIMEFRAMES during backtest (matches live behavior)
# False = Load zones from backtest_zones.txt file (legacy behavior)
BACKTEST_DETECT_ZONES = True

# ---------------------------------------------------------------------------
# Demand zone detection
# ---------------------------------------------------------------------------
DEMAND_ZONE_OFFSET_TOP = 0.10
DEMAND_ZONE_OFFSET_BOTTOM = 0.10
BULLISH_WICK_RATIO = 0.5        # Max wick size relative to body for bullish candle
BEARISH_WICK_RATIO = 0.5        # Max upper wick size relative to bullish body
DEMAND_ZONE_TRADING = False    # Toggle demand-zone constrained trading

# Seeded manual zones; non-empty list disables the AnalysisService
CUSTOM_DEMAND_ZONES = []

# ---------------------------------------------------------------------------
# Strategy toggles
# ---------------------------------------------------------------------------
PATTERN_MODE = "6_candle"                  # "6_candle", "3_candle", or "both"
# When "both": runs 3_candle and 6_candle (smart reversal) in parallel
# Each pattern has independent signal tracking and can trigger trades independently

# ---------------------------------------------------------------------------
# 3-Candle Pattern Thresholds
# ---------------------------------------------------------------------------
C3_STRONG_BULLISH_MIN_BODY_PCT = 0.60  # C3: Min body % for strong bullish entry
C3_STRONG_BEARISH_MIN_BODY_PCT = 0.60  # C1: Min body % for strong bearish

# ---------------------------------------------------------------------------
# Candlestick pattern thresholds
# ---------------------------------------------------------------------------
DOJI_PRECISION = 0.30                    # Max body % of range for a standard Doji
DRAGONFLY_DOJI_PRECISION = 0.30          # Max body % for Dragonfly Doji
DRAGONFLY_DOJI_MAX_UPPER_WICK = 0.5      # Max upper wick % of range

STRONG_BULLISH_MIN_BODY_PCT = 0.50       # Body share of range for strong bullish candle
STRONG_BULLISH_MAX_WICK_PCT = 0.60       # Combined wick share of range

C1_MIN_BODY_PCT = 0.30                   # Min body % for indecision candle
C1_MAX_BODY_PCT = 0.50                   # Max body % for indecision candle
C1_MIN_LOWER_WICK_PCT = 0.20             # Min lower wick % relative to body

HAMMER_LOWER_WICK_RATIO = 2.0            # Lower wick relative to body
HAMMER_MAX_UPPER_WICK_RATIO = 0.5        # Upper wick as fraction of body

SPINNING_TOP_MAX_BODY_PCT = 0.30         # Body % threshold for spinning top
SPINNING_TOP_MIN_WICK_BODY_RATIO = 1.5   # Wick-to-body ratio for spinning top

MARUBOZU_MAX_WICK_PCT = 0.05             # Wick share of range for Marubozu

C5_BULLISH_MIN_BODY_PCT = 0.60           # Body share for C5 bullish candle
C6_MAX_BODY_PCT = 0.25                   # Max body % for C6 small bullish (must NOT be strong bullish)
NORMAL_BEARISH_MIN_BODY_PCT = 0.70       # Body share for full bearish candle
NEUTRAL_BEARISH_MIN_BODY_PCT = 0.30      # Body share for neutral bearish candle

# V-Pattern Shape Validation
V_PATTERN_MAX_GAP_PCT = 0.30             # Max gap between candles as % of avg candle range
V_PATTERN_PIVOT_TOLERANCE = 0.10         # Pivot can be within 10% of lowest low

# ---------------------------------------------------------------------------
# Smart Reversal Settings (6-candle pattern)
# ---------------------------------------------------------------------------
# Lookback for drop calculation
SMART_REVERSAL_LOOKBACK_CANDLES = 20  # How many candles to look back for swing high (min 6)

# Drop detection - measures significance of the pullback
SMART_REVERSAL_MIN_DROP_PCT = 0.0015     # Min drop % from swing high (0.20%)
SMART_REVERSAL_MIN_DROP_DOLLARS = 0.25   # OR min drop in dollars (use either)
SMART_REVERSAL_USE_DOLLAR_DROP = False   # True=use dollars, False=use percentage

# Exhaustion detection - identifies the base/accumulation zone
SMART_REVERSAL_REQUIRE_EXHAUSTION = False  # DISABLED: Too restrictive, misses early moves
SMART_REVERSAL_SHRINKING_THRESHOLD = 0.7   # Body shrink ratio for momentum decay (only if enabled)

# Trigger confirmation - the reversal signal
SMART_REVERSAL_MIN_BODY_PCT = 0.50       # Trigger candle min body % of range
SMART_REVERSAL_MIN_RECLAIM_PCT = 0.10    # Trigger must reclaim at least X% of drop
SMART_REVERSAL_MAX_RECLAIM_PCT = 0.40    # Trigger must reclaim at most X% (catch early, not late)
SMART_REVERSAL_REQUIRE_BASE_BREAK = False # DISABLED: Catches earlier entries before base break

# Signal reset - prevent consecutive signals from same reversal
SMART_REVERSAL_REQUIRE_RESET = True      # Require reset before next signal
SMART_REVERSAL_RESET_CANDLES = 2         # Number of bearish candles required before reset

# Continuous Drop Detection - filters out sideways/accumulation zones
# A clean drop should be mostly bearish candles flowing downward, not mixed direction
SMART_REVERSAL_REQUIRE_CONTINUOUS_DROP = True    # Enable continuous drop validation
SMART_REVERSAL_MAX_BULLISH_RATIO = 0.35          # Max % of bullish candles in drop path (0.35 = 35%)
SMART_REVERSAL_MAX_CONSECUTIVE_BULLISH = 2       # Max consecutive bullish candles before it's accumulation

# Drop Recency Check - ensures trigger fires near the bottom, not in consolidation
# V-shaped reversals have trigger close to the drop low, flat zones have stale drop lows
SMART_REVERSAL_REQUIRE_FRESH_DROP = True         # Enable drop recency validation
SMART_REVERSAL_MAX_DROP_AGE = 4                  # Drop low must be within last N candles (4 = V-shape, 6+ = flat)
