# CLAUDE.md - Project Context for AI Sessions

## Project Overview
SPY algorithmic trading bot using supply/demand zone analysis with candlestick confirmation patterns to trade 0DTE options. Supports dual broker execution: Interactive Brokers (market data) and TradeStation (order execution).

## Architecture
```
algotrade/
├── main.py                    # Orchestrator - launches all services
├── config.py                  # Central configuration hub
├── trading_data.db            # SQLite database
├── run_pattern_backtest.py    # Pattern backtesting script
├── algotrade/
│   ├── analysis_service.py    # Service 1: Identifies demand zones
│   ├── trade_service.py       # Service 2: Pattern confirmation & execution
│   ├── invalidation_service.py# Service 3: Risk management
│   ├── patterns.py            # Candlestick pattern library + PATTERN_REGISTRY
│   │
│   │  # IB Execution (EXECUTION_BROKER = "ib")
│   ├── execution.py           # IB handlers (Live/Paper/ManualOCOManager)
│   ├── orders.py              # IB order placement
│   │
│   │  # TradeStation Execution (EXECUTION_BROKER = "tradestation")
│   ├── tradestation_client.py # TradeStation REST API client
│   ├── tradestation_orders.py # TradeStation bracket order logic
│   ├── tradestation_execution.py # TradeStation execution handlers
│   │
│   ├── database.py            # SQLite persistence
│   ├── analysis.py            # Demand zone detection
│   └── util.py                # Utilities
└── frontend/                  # React dashboard (not integrated)
```

## 3-Service Architecture
1. **Analysis Service** - Scans timeframes (30m→2m) for demand zones, stores in SQLite
2. **Trade Service** - Monitors candle patterns (6-candle or 3-candle), executes trades
3. **Invalidation Service** - Risk management, invalidates broken zones

## Candle Confirmation Patterns

### 6-Candle Pattern (Smart Reversal)
Uses intelligent reversal detection instead of mechanical candle counting.

**SIMPLIFIED MODE (Default - SMART_REVERSAL_REQUIRE_EXHAUSTION = False):**
```
1. Strong bullish candle appears (trigger with 50%+ body)
2. Look back 15 candles → find swing high
3. Calculate drop % from swing high to lowest point
4. Verify drop is CONTINUOUS (no sideways/accumulation zones)
5. Calculate reclaim % - how much trigger close recovers from drop
6. If drop >= min AND continuous AND reclaim in range → TRADE!
```

**ADVANCED MODE (SMART_REVERSAL_REQUIRE_EXHAUSTION = True):**
```
1. SIGNIFICANT DROP  → Measure actual price drop (not candle count)
2. EXHAUSTION BASE   → Detect momentum decay / accumulation (OPTIONAL)
3. TRIGGER CONFIRM   → Strong bullish that reclaims the drop
```

**The Secret Sauce: RECLAIM RATIO**
How much of the drop the trigger candle "takes back". A trigger that reclaims 15-80% shows buying conviction while catching early entries.

| Check | What it Measures | Config |
|-------|------------------|--------|
| Drop | Price drop from swing high | `SMART_REVERSAL_MIN_DROP_PCT` (0.20%) |
| Continuous | Drop must flow downward (no sideways) | `SMART_REVERSAL_REQUIRE_CONTINUOUS_DROP` (True) |
| Exhaustion | Base formation (DISABLED by default) | `SMART_REVERSAL_REQUIRE_EXHAUSTION` (False) |
| Trigger | Strong bullish body | `SMART_REVERSAL_MIN_BODY_PCT` (50%) |
| Reclaim | % of drop recovered by trigger close | `SMART_REVERSAL_MIN_RECLAIM_PCT` (10%) |
| Max Reclaim | Catch early, not late | `SMART_REVERSAL_MAX_RECLAIM_PCT` (30%) |
| Base Break | Trigger closes above base high (DISABLED by default) | `SMART_REVERSAL_REQUIRE_BASE_BREAK` (False) |

**Continuous Drop Detection (filters out sideways zones):**
- `clean_drop` - Mostly bearish candles with consistent lower lows
- `mixed_direction` - FAIL: Too many bullish candles (>35%) in drop path
- `accumulation` - FAIL: 3+ consecutive bullish candles (sideways zone)

**Drop Recency Check (V-shape vs flat zone):**
- Ensures trigger fires near the bottom of the drop, not in consolidation
- `age=1-4` - PASS: Drop low is recent (V-shaped reversal)
- `age>4` - FAIL: Drop low is stale (flat zone/consolidation)

**Exhaustion Types (only when enabled):**
- `indecision` - Doji, Hammer, Spinning Top in base
- `shrinking` - Candle bodies getting smaller (momentum decay)
- `spring` - Wick below prior low that recovers (traps shorts)
- `tight_range` - Consolidation pattern
- `disabled` - When SMART_REVERSAL_REQUIRE_EXHAUSTION = False

Candle order: `c1`→`c6` = oldest→newest

### 3-Candle Pattern
| Candle | Role | Criteria |
|--------|------|----------|
| C3 | Strong bullish entry | Body >= 50% of range (`C3_STRONG_BULLISH_MIN_BODY_PCT`) |
| C2 | Indecision | Doji, Hammer, Spinning Top, Dragonfly Doji |
| C1 | Strong bearish | Body >= 50% of range (`C3_STRONG_BEARISH_MIN_BODY_PCT`) |

Candle order: `c1`→`c3` = oldest→newest

**Efficiency**: Fast-fail ordering (C3 checked first, then C2, then C1). OHLC values stored only on pattern pass.

## Key Config Flags
```python
PATTERN_MODE        # "6_candle", "3_candle", or "both" (run both in parallel)
EXECUTION_BROKER    # "ib" or "tradestation"
TRADE_ORDERS        # Enable/disable order placement
PAPER_TRADE         # Paper vs live trading
DEMAND_ZONE_TRADING # Zone-based vs pattern-only mode
TAKE_PROFIT_PCT     # Profit target percentage (default 0.20 = 20%)

# Position Sizing (Dynamic Contract Quantity)
POSITION_SIZE_ENABLED = True     # False = always 1 contract
TRADE_TARGET_AMOUNT = 160        # Target $ per trade (higher for ITM)
TRADE_MIN_AMOUNT = 100           # Min acceptable
TRADE_MAX_AMOUNT = 180           # Max acceptable

# Strike Selection (ITM Strategy for Lower Commission)
STRIKE_SELECTION_MODE = "ITM"    # "ITM", "ATM", or "OTM"
ITM_OFFSET = 1                   # Dollars ITM for calls (SPY @ 590 -> strike 589)
OTM_OFFSET = 3                   # Dollars OTM for calls (SPY @ 590 -> strike 593)

# Dual Stop Loss Monitoring (whichever triggers first wins)
# 1. Option Max Loss - protects against theta decay, IV collapse
OPTION_STOP_ENABLED = True          # Enable option price monitoring
OPTION_STOP_POLL_INTERVAL = 15      # Seconds between option price checks (15s)
OPTION_MAX_LOSS_PCT = 0.30          # Max loss percentage (-30%)

# 2. SPY Support Break - protects against technical breakdown
SPY_STOP_ENABLED = True             # Enable SPY price monitoring
SPY_STOP_POLL_INTERVAL = 30         # Seconds between SPY checks (30s)
SPY_SWING_LOW_CANDLES = 15          # Candles to look back for swing low
SPY_STOP_BUFFER_DOLLARS = 0.10      # Dollars below swing low ($0.10)

# 3-Candle Pattern Thresholds
C3_STRONG_BULLISH_MIN_BODY_PCT = 0.50  # C3: Min body % for strong bullish entry
C3_STRONG_BEARISH_MIN_BODY_PCT = 0.50  # C1: Min body % for strong bearish

# Smart Reversal Settings (6-candle pattern)
SMART_REVERSAL_LOOKBACK_CANDLES = 15        # Candles to look back for swing high (15 recommended)
SMART_REVERSAL_MIN_DROP_PCT = 0.0012        # Min drop % from swing high (0.12%)
SMART_REVERSAL_MIN_BODY_PCT = 0.50          # Trigger candle min body %
SMART_REVERSAL_MIN_RECLAIM_PCT = 0.15       # Min reclaim % (signal strength)
SMART_REVERSAL_MAX_RECLAIM_PCT = 0.80       # Max reclaim % (catch early, not late)

# SIMPLIFIED MODE (Recommended - catches early momentum)
SMART_REVERSAL_REQUIRE_EXHAUSTION = False   # Skip indecision checks (faster signals)
SMART_REVERSAL_REQUIRE_BASE_BREAK = False   # Skip base break check (earlier entries)

# ADVANCED MODE (Stricter filtering)
# SMART_REVERSAL_REQUIRE_EXHAUSTION = True  # Requires indecision/accumulation in base
# SMART_REVERSAL_REQUIRE_BASE_BREAK = True  # Requires breakout above base

# Continuous Drop Detection (filters out sideways/accumulation zones)
SMART_REVERSAL_REQUIRE_CONTINUOUS_DROP = True    # Require clean drop (no sideways)
SMART_REVERSAL_MAX_BULLISH_RATIO = 0.35          # Max 35% bullish candles in drop path
SMART_REVERSAL_MAX_CONSECUTIVE_BULLISH = 2       # Max consecutive bullish before fail

# Drop Recency Check (V-shape vs flat zone)
SMART_REVERSAL_REQUIRE_FRESH_DROP = True         # Require drop_low to be recent
SMART_REVERSAL_MAX_DROP_AGE = 4                  # Drop low must be within last N candles

SMART_REVERSAL_REQUIRE_RESET = True         # Require reset before next signal
SMART_REVERSAL_RESET_CANDLES = 2            # Bearish candles needed before next signal
```

## Parallel Pattern Execution (PATTERN_MODE = "both")

When `PATTERN_MODE = "both"`, both 6_candle (Smart Reversal) and 3_candle patterns run simultaneously on each candle close.

**How it works:**
```
Every candle close:
├── Fetch fresh historical bars (enough for largest pattern)
├── Process 6_candle (Smart Reversal)
│   └── Independent signal reset tracking
└── Process 3_candle
    └── Independent (no reset needed)
```

**Duplicate Trade Prevention:**
- First pattern to trigger on a bar wins
- Second pattern is skipped for that bar
- Each timeframe tracked independently (2m trade doesn't block 3m)

**Example log output:**
```
Trade Service initialized | Patterns: 6_candle + 3_candle | Timeframes: ['2m', '3m']
[CandleFetch] timeframe=2m ... bars=20 range=13:20:00→14:00:00
[SmartReversal] tf=2m ... result=PASS
✨✨✨ SMART REVERSAL CONFIRMED ✨✨✨
[3_candle:2m] Skipping - trade already executed on this bar  ← Duplicate prevented
```

**Signal Reset Tracking (per-pattern):**
- Format: `{("6_candle", "2m"): False, ("3_candle", "2m"): False, ...}`
- Each pattern has its own reset state per timeframe
- 6_candle uses reset logic, 3_candle does not

## Pattern Registry (Single Source of Truth)

All patterns are registered in `patterns.py`:

```python
PATTERN_REGISTRY = {
    "6_candle": {
        "candle_count": 6,
        "evaluate_func": evaluate_6_candle_confirmation_pattern,
        "log_prefix": "6CandleCheck"
    },
    "3_candle": {
        "candle_count": 3,
        "evaluate_func": evaluate_3_candle_pattern,
        "log_prefix": "3CandleCheck"
    }
}
```

Both live trading and backtest import from the same registry:
- `trade_service.py` → imports `PATTERN_REGISTRY`
- `run_pattern_backtest.py` → imports `PATTERN_REGISTRY`

### Adding a New Pattern
1. Add `evaluate_X_candle_pattern()` function to `patterns.py`
2. Add entry to `PATTERN_REGISTRY`
3. Add `_process_X_candle_confirmation()` handler to `trade_service.py`
4. Backtest automatically works (no changes needed)

## Backtesting

### CLI Usage

```bash
# Basic usage (defaults to config.SYMBOL and config.PATTERN_MODE)
python run_pattern_backtest.py --start-date 2024-12-01 --end-date 2024-12-20

# Override pattern mode
python run_pattern_backtest.py --start-date 2024-12-01 --end-date 2024-12-20 --pattern 6_candle
python run_pattern_backtest.py --start-date 2024-12-01 --end-date 2024-12-20 --pattern 3_candle
python run_pattern_backtest.py --start-date 2024-12-01 --end-date 2024-12-20 --pattern both

# Custom symbol
python run_pattern_backtest.py --start-date 2024-12-01 --end-date 2024-12-20 --symbol TSLA
python run_pattern_backtest.py --start-date 2024-12-01 --end-date 2024-12-20 --symbol QQQ

# Output formats (auto-detected by file extension)
python run_pattern_backtest.py --start-date 2024-12-01 --end-date 2024-12-20 --output results.md   # Markdown
python run_pattern_backtest.py --start-date 2024-12-01 --end-date 2024-12-20 --output results.html # HTML with charts

# Full example
python run_pattern_backtest.py \
  --start-date 2024-12-01 \
  --end-date 2024-12-20 \
  --symbol SPY \
  --pattern both \
  --output backtest_results.html
```

### CLI Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--start-date` | Required | Start date (YYYY-MM-DD) |
| `--end-date` | Required | End date (YYYY-MM-DD) |
| `--symbol` | `config.SYMBOL` | Symbol to backtest (SPY, TSLA, QQQ, etc.) |
| `--pattern` | `config.PATTERN_MODE` | Pattern mode: `6_candle`, `3_candle`, or `both` |
| `--output` | `backtest_results.md` | Output file (.md for Markdown, .html for HTML) |

### Session-Aligned Bars (TradingView Compatible)

Backtest now supports **session-aligned bars** for hourly timeframes (1h, 2h, 3h, 4h), matching TradingView's bar alignment.

**The Problem:**
IBKR returns clock-aligned bars (10:00, 11:00, 12:00...) instead of session-aligned bars (9:30, 10:30, 11:30...).

**The Solution:**
For timeframes >= 1h, the backtest automatically:
1. Fetches 30m bars from IBKR
2. Aggregates them into session-aligned bars starting from market open (9:30 AM)

```python
# Automatic behavior based on timeframe
"2m"  → Direct fetch (already aligned)
"30m" → Direct fetch (naturally aligned)
"1h"  → Fetch 30m → Aggregate to session-aligned 1h
"2h"  → Fetch 30m → Aggregate to session-aligned 2h
```

**Example:**
```
IBKR 1h bars:    9:30-10:00 (30min), 10:00-11:00, 11:00-12:00...
Session-aligned: 9:30-10:30 (full), 10:30-11:30, 11:30-12:30...
```

### Dynamic Demand Zone Detection

Backtest can now detect demand zones dynamically (like live trading) instead of loading from a file.

**Config:**
```python
BACKTEST_DETECT_ZONES = True   # Detect zones during backtest (recommended)
BACKTEST_DETECT_ZONES = False  # Load from backtest_zones.txt (legacy)
```

**How it works:**
1. Downloads bars for all `ZONE_TIMEFRAMES` (e.g., 30m, 15m, 1h)
2. Runs `AnalysisEngine` to detect demand zones from those bars
3. Uses detected zones for pattern filtering (if `DEMAND_ZONE_TRADING=True`)

**Flow:**
```
Backtest Start
    ↓
Download Zone Timeframe Bars (with session alignment)
    ↓
Run AnalysisEngine on each bar → Detect zones
    ↓
Store detected zones
    ↓
Pattern Detection Loop (uses detected zones for filtering)
```

### Stop Loss Simulation

Backtest includes stop loss simulation to calculate WIN/LOSS status for each trade:

```
Pattern Detected
    ↓
Calculate Swing High/Low (last 15-20 candles from config.SPY_SWING_LOW_CANDLES)
    ↓
Check Next 8 × 15-minute Bars (always 15m, regardless of pattern timeframe)
    ↓
If ANY bar.low < swing_low → LOSS
If ALL 8 bars hold above swing_low → WIN
```

**Key Points:**
- Swing high/low calculated from pattern's timeframe candles
- Stop check uses 15-minute bars (2 hours monitoring period)
- Results include: entry price, swing high, swing low, lowest price during monitoring

### Output Formats

**Markdown (.md):**
- Summary tables (win rate, pattern stats, timeframe stats)
- Trade confirmations table with status
- Loss details section

**HTML (.html):**
- Dashboard cards (Total, Wins, Losses, Win Rate)
- Pie chart for win/loss distribution (SVG)
- Bar chart for pattern performance (SVG)
- Styled tables with color-coded status (✅ WIN / ❌ LOSS)
- No external dependencies (pure HTML/CSS/SVG)

### Sample Output Table

| # | Timestamp | TF | Pattern | Entry | Swing High | Swing Low | Status | Lowest |
|--:|-----------|:--:|:-------:|------:|-----------:|----------:|:------:|-------:|
| 1 | 2024-12-02 10:04:00 | 2m | SM | $589.45 | $590.20 | $588.20 | ✅ WIN | $588.50 |
| 2 | 2024-12-02 11:32:00 | 2m | 3C | $590.12 | $591.00 | $589.30 | ❌ LOSS | $588.90 |

### Pre-Fill Buffer

Backtest downloads 1 extra day of data before `start_date` to pre-fill the candle history buffer:

| Scenario | Buffer Behavior |
|----------|-----------------|
| Multi-day backtest | Previous day's bars pre-fill buffer → Pattern check ready on first bar |
| Single day at 9:30 AM | No buffer data → First 14 bars used for buffer filling |
| Mid-day start (11:00 AM) | Same-day earlier bars pre-fill buffer → Ready immediately |

### IB API Duration Limits (handled automatically)

| Bar Size | Max per Request |
|----------|-----------------|
| 1 min | 1 day |
| 2 min | 2 days |
| 3 min | 1 week |
| 15 min | 1 week |

## Execution Broker Selection

### Interactive Brokers (EXECUTION_BROKER = "ib")
- **Live**: `ManualOCOManager` - Event-driven via IB's `pendingTickersEvent`
- **Paper**: `PaperExecutionHandler` - Simulates trades with monitoring thread
- Requires IB account with options approval

### TradeStation (EXECUTION_BROKER = "tradestation")
- **Live**: `TradeStationExecutionHandler` - Limit-only orders with SPY monitoring
- **Paper**: `TradeStationPaperHandler` - Uses sim environment
- REST API with OAuth2 authentication

## TradeStation Order Execution Flow

### Entry Order Sequence (Synchronized)
```
1. Trade signal detected
2. TradeStationClient.authenticate() (OAuth2)
3. Build SPY option symbol: "SPY YYMMDD[C/P]STRIKE"
4. Get option quote (ask price)
5. Calculate position size based on target amount
6. Place Market BUY order
7. Poll for fill confirmation (100ms intervals, 10s timeout)
   ✅ WAIT for BUY FILLED before proceeding
8. Get actual fill price from API
9. Calculate profit target = actual_fill_price × 1.20
10. Place LIMIT SELL order @ profit target (+20%)
11. Calculate swing low from last 15 candles on pattern timeframe
12. Start SPY monitoring thread for dynamic stop loss
```

### Dual Stop Loss Monitoring (Threading-Based)
Each trade gets an independent monitoring thread with **TWO parallel stops** (whichever triggers first wins):

**Option Stop (15s polling):**
```
1. Get option BID price from TradeStation
2. If bid ≤ entry_price × 0.70 (-30%):
   → OPTION_MAX_LOSS triggered
   → Protects against: theta decay, IV collapse, time erosion
```

**SPY Stop (30s polling):**
```
1. Calculate swing low = lowest low from last 15 candles
   Example: Pattern on 2m → use last 15 x 2m candles
2. Monitor SPY price using IB connection
3. If SPY ≤ swing_low - $0.10:
   → SPY_SUPPORT_BREAK triggered
   → Protects against: technical breakdown, trend reversal
```

**When EITHER stop triggers:**
```
a. Cancel profit LIMIT order
b. Poll for cancel confirmation (200ms intervals, 3s timeout)
   ✅ WAIT for CANCELLED status before proceeding
c. Place Market SELL order
d. Update database with P/L and stop_type
e. Stop monitoring
```

**Also stops when:**
- Profit target fills (limit order fills at +20%)

### Exit Sequence (Profit Target)
```
1. Main loop polls limit order status every 1 second
2. Limit order FILLED at +20%
3. Signal monitoring thread to stop
4. Update database with profit
5. Cleanup trade from active trades
```

### Exit Sequence (Stop Loss Trigger - Dual)
```
EITHER:
  Option BID ≤ -30% (OPTION_MAX_LOSS)
OR:
  SPY ≤ swing_low - $0.10 (SPY_SUPPORT_BREAK)

Then:
1. Cancel profit limit order → Wait for confirmation
2. Place market sell order
3. Poll for market fill (200ms intervals)
4. Update database with loss + stop_type
5. Monitoring thread exits
6. Main loop detects exit and cleans up
```

**Key Safety Features:**
- BUY confirmation required before placing limit sell
- Cancel confirmation required before placing market sell
- Prevents rejected orders due to double-selling same position
- Thread-safe with stop events for clean shutdown

## Position Sizing (Dynamic Contract Quantity)

Automatically calculates number of contracts based on target dollar amount.

```python
# Config settings
POSITION_SIZE_ENABLED = True     # False = always 1 contract
TRADE_TARGET_AMOUNT = 160        # Target $ per trade (higher for ITM)
TRADE_MIN_AMOUNT = 100           # Min acceptable
TRADE_MAX_AMOUNT = 180           # Max acceptable
```

**How it works:**
1. Get option ask price (e.g., $10.50 for $1 ITM)
2. Calculate: `$160 / ($10.50 × 100) = 0.15` → rounds to 1 contract
3. Verify cost is within range: `1 × $1050 = $1050` (exceeds max but uses 1 minimum)

## Strike Selection (ITM Strategy)

Uses ITM (In-The-Money) options to reduce commission impact and improve consistency.

```python
# Config settings
STRIKE_SELECTION_MODE = "ITM"    # "ITM", "ATM", or "OTM"
ITM_OFFSET = 1                   # Dollars ITM (SPY @ 590 -> strike 589)
OTM_OFFSET = 3                   # Dollars OTM (SPY @ 590 -> strike 593)
```

**Why ITM?**

| Factor | ITM ($1 ITM) | ATM | OTM ($3 OTM) |
|--------|-------------|-----|--------------|
| Premium | ~$10-12 | ~$2-3 | ~$0.50-1.00 |
| Delta | ~0.60-0.65 | ~0.50 | ~0.30-0.40 |
| Contracts for $160 | 1 | 1-2 | 2-3 |
| Commission (RT) | ~$1.60 | ~$3.20 | ~$4.80 |
| Commission % | **1.0%** | 2.0% | **3.0%** |
| Bid-ask spread | Tight | Medium | Wide |
| Theta decay | Low | High | Highest |

**Commission Impact Example:**
- OTM: 3 contracts × $0.80 × 2 = $4.80 commission on $160 position = **3.0%**
- ITM: 1 contract × $0.80 × 2 = $1.60 commission on $160 position = **1.0%**

For 20% profit target, commission eats 15% of OTM profits vs 5% of ITM profits.

**Log Output:**
```
[StrikeSelect] ITM | SPY: $590.25 | Strike: 589 | ITM by $1 | ~Delta: 0.62
[PositionSize] Qty: 1 | Premium: $10.50 | Cost: $1050.00 | Target: $160 (range: $100-$180)
```

**Trade-offs:**
- ITM = More capital per position, lower leverage, but more consistent
- ATM = Balanced risk/reward
- OTM = Less capital, more leverage, but higher commission impact and theta decay

## Strike Test Mode (Parallel ITM/ATM/OTM Testing)

Enables parallel testing of all 3 strike types on the same signal for direct comparison.

```python
# Config settings
STRIKE_TEST_MODE = False          # Enable parallel strike testing
STRIKE_TEST_QUANTITY = 1          # Contracts per strike type (recommend 1)
```

**How it works:**
When a pattern triggers with test mode enabled:
1. Places 3 separate orders (ITM, ATM, OTM)
2. Each gets its own profit limit order and SPY monitoring thread
3. Each tracked independently in database with pattern_type suffix

**Database tracking:**
```
| ID | Pattern  | Strike | Entry  | P/L   |
|----|----------|--------|--------|-------|
| 1  | SM-ITM   | 585    | $10.50 | +$84  |
| 2  | SM-ATM   | 590    | $2.80  | +$28  |
| 3  | SM-OTM   | 593    | $0.85  | -$42  |
```

**Log output:**
```
[TestMode] 🧪 PARALLEL STRIKE TEST | SPY: $590.25 | ITM: 585 | ATM: 590 | OTM: 593
[TestMode] ✅ ITM FILLED @ $10.50
[TestMode] ✅ ATM FILLED @ $2.80
[TestMode] ✅ OTM FILLED @ $0.85
[TestMode] 🧪 TEST COMPLETE | Success: 3/3 | Total time: 2450ms
```

**To enable:** Set `STRIKE_TEST_MODE = True` in config.py
**To disable:** Set `STRIKE_TEST_MODE = False` (returns to normal single-strike mode)

## Signal Reset Logic (Smart Reversal)

Prevents multiple signals from the same reversal move.

```python
SMART_REVERSAL_REQUIRE_RESET = True   # Enable reset requirement
SMART_REVERSAL_RESET_CANDLES = 2      # Bearish candles needed
```

**How it works:**
1. Signal triggers → set `waiting_for_reset = True`
2. Count bearish candles (close < open)
3. After N bearish candles → reset, allow new signals
4. Prevents rapid-fire entries on same move

## TradeStation Config (Auth0/v3)
```python
TRADESTATION_CLIENT_ID = ""        # API Key from Developer Portal
TRADESTATION_CLIENT_SECRET = ""    # API Secret from Developer Portal
TRADESTATION_REFRESH_TOKEN = ""    # OAuth refresh token (from initial auth flow)
TRADESTATION_ACCOUNT_ID = ""       # Account ID (get from /brokerage/accounts)
TRADESTATION_BASE_URL = "https://api.tradestation.com/v3"
TRADESTATION_ENVIRONMENT = "live"  # "live" or "sim"
```

**Auth Notes:**
- Uses Auth0 authentication (v3 endpoints)
- Access tokens expire in 20 minutes (auto-refreshed)
- Refresh tokens are non-expiring by default
- Token endpoint: `https://signin.tradestation.com/oauth/token`

## Dependencies
- `ib_insync` - Interactive Brokers API (market data)
- `requests` - TradeStation REST API
- `pandas`, `numpy` - Data analysis
- SQLite - Persistence (demand zones, trades, daily stats)

## Common Tasks
- Pattern detection: `algotrade/patterns.py`
- IB execution: `algotrade/execution.py`, `algotrade/orders.py`
- TradeStation execution: `algotrade/tradestation_*.py`
- Zone detection: `algotrade/analysis.py`
- Config changes: `config.py`
- Backtesting: `run_pattern_backtest.py`

## Candle Timing
- Polling synchronized to candle boundaries
- 2m candle closes at :00, :02, :04... → fetch at :02, :04, :06...
- `CANDLE_BOUNDARY_BUFFER_SECONDS = 2` delay ensures data completeness

## Recent Changes (Jan 5, 2026)

### Dual Stop Loss System (Option + SPY)
Replaced single SPY stop with **dual independent stops** - whichever triggers first wins.

**Two Parallel Protections:**

1. **Option Max Loss Stop (-30%)**
   - Polls option BID price every 15 seconds
   - Triggers if bid ≤ entry × 0.70
   - Protects against: theta decay, IV collapse, time erosion
   - Caps max loss in dollars

2. **SPY Support Break Stop**
   - Polls SPY price every 30 seconds
   - Calculates swing low from last 15 candles (once at entry)
   - Triggers if SPY ≤ swing_low - $0.10
   - Protects against: technical breakdown, trend reversal
   - Respects price action structure

**Why Dual Stops?**
- **0DTE options decay** regardless of SPY movement
- SPY could consolidate while option bleeds from theta
- Need protection from BOTH time decay AND price breakdown
- Example: SPY holds $589.60 (above trigger) but option drops from $10 → $7 (-30%) → STOPPED
- Example: SPY breaks $589.30 (below trigger) while option at -18% → STOPPED

**Implementation:**
- `_monitor_dual_stop_loss()` in `tradestation_execution.py`
- Independent polling intervals (15s option, 30s SPY)
- Uses TradeStation API for option quotes (BID price)
- Uses IB connection for SPY real-time data
- Logs which stop triggered for performance tracking

### Profit Target Increased to 20%
Changed from 15% to **20%** profit target with limit-only orders.

**Order Structure:**
- **Before**: OCO bracket (LIMIT +15% | STOP -10%)
- **After**: LIMIT +20% only (stop loss via SPY monitoring)

**Entry Sequence (Synchronized):**
1. Place BUY market order
2. **Wait for fill confirmation** ✅
3. Get actual fill price from API
4. Place LIMIT sell at actual_fill_price × 1.20
5. Start SPY monitoring

**Exit Sequence (Stop Loss - Synchronized):**
1. SPY breaks trigger level
2. Cancel profit limit order
3. **Wait for cancel confirmation** ✅
4. Place market sell order
5. Update database

**Safety Features:**
- No double-selling: waits for confirmations before next order
- Prevents rejected orders from duplicate positions
- Polling with timeouts (not blind delays)

### Config Changes
```python
# Updated values
TAKE_PROFIT_PCT = 0.20              # Increased from 0.15
TRADE_TARGET_AMOUNT = 160           # Adjusted from 300
TRADE_MIN_AMOUNT = 100              # Adjusted from 250
TRADE_MAX_AMOUNT = 180              # Adjusted from 350
ITM_OFFSET = 1                      # Reduced from 5 ($1 ITM vs $5)

# Dual stop monitoring settings
OPTION_STOP_ENABLED = True          # Option max loss monitoring
OPTION_STOP_POLL_INTERVAL = 15      # Poll every 15s
OPTION_MAX_LOSS_PCT = 0.30          # -30% max loss trigger

SPY_STOP_ENABLED = True             # SPY support break monitoring
SPY_STOP_POLL_INTERVAL = 30         # Poll every 30s
SPY_SWING_LOW_CANDLES = 15          # Lookback period
SPY_STOP_BUFFER_DOLLARS = 0.10      # $0.10 below swing low
```

## Recent Changes (Dec 29, 2024)

### Fresh Historical Data Fetch (Critical Fix)
Live trading now fetches **fresh historical bars every cycle**, identical to how backtest works. This eliminates buffer management issues.

**Before (problematic):**
```
Every 2 min → Fetch bars → Use only LAST bar → Append to rolling buffer → Pattern uses buffer
Problem: Buffer builds slowly, can have stale/wrong data after restart
```

**After (like backtest):**
```
Every 2 min → Fetch N historical bars → Convert ALL to pd.Series → Pattern uses fresh data
Result: Always accurate, same code path as backtest, works immediately after restart
```

**Key changes in `trade_service.py`:**
- Removed `_candles` rolling buffer (no longer needed)
- `_fetch_and_process_timeframe()` now fetches fresh historical bars each cycle
- Log shows full range: `[CandleFetch] bars=15 range=13:52:00→14:20:00`

### Parallel Pattern Execution
- New `PATTERN_MODE = "both"` runs 6_candle + 3_candle simultaneously
- Each pattern has independent signal reset tracking
- Duplicate trade prevention: first pattern to trigger wins on each bar
- See "Parallel Pattern Execution" section above for details

### Lookback Candles Increased
- Changed `SMART_REVERSAL_LOOKBACK_CANDLES` from 6 to **15** (recommended)
- 6 was too short to capture swing highs in longer downtrends
- 15 candles = 30 min lookback on 2m timeframe (captures most reversals)

### Backtest Support for "both" Mode
- `run_pattern_backtest.py` now supports `--pattern both`
- Runs both patterns on each bar with duplicate prevention
- Output shows pattern counts separately per pattern type

## Earlier Changes (Dec 2024)
- **Position Sizing**: Dynamic contract quantity based on $200 target amount
  - `calculate_position_size()` in `tradestation_orders.py`
  - Configurable target/min/max amounts
  - Auto-adjusts quantity to fit within range
- **Signal Reset**: Prevents consecutive signals from same reversal
  - Requires N bearish candles before next signal allowed
  - Configurable via `SMART_REVERSAL_RESET_CANDLES`
- **Smart Reversal (6-candle)**: Replaced mechanical pattern counting with intelligent detection:
  - Measures actual price drop magnitude (not candle count)
  - Detects exhaustion via indecision, shrinking bodies, spring patterns, tight ranges
  - **Reclaim Ratio**: The secret sauce - measures how much of the drop the trigger reclaims
  - Configurable thresholds for drop %, reclaim %, trigger body %
  - Variable lookback for swing high (`SMART_REVERSAL_LOOKBACK_CANDLES`)
  - Max reclaim % to catch reversals early (`SMART_REVERSAL_MAX_RECLAIM_PCT`)
- **3-candle pattern**: Replaced 2-candle with 3-candle (C1=strong bearish, C2=indecision, C3=strong bullish entry)
- **Pattern Registry**: Single source of truth in `patterns.py` for all pattern configurations
- **Backtest improvements**: Dynamic pattern support, IB duration limits handling, chunked requests, signal reset tracking
- **Efficiency optimizations**: Fast-fail checks, OHLC stored only on pass
- Added TradeStation API integration for order execution
- Candle polling synchronized to boundaries (not fixed 15s intervals)
- V-pattern detection removed
- Trade service converted from async to sync with `ib.sleep()`
- Candle ordering fixed to oldest→newest

## Database Schema

### trade_confirmations table
- `symbol` - Trading symbol (SPY, TSLA, NVDA, etc.) - **NEW: Multi-symbol support**
- `alert_timestamp` - When pattern/signal detected
- `entry_timestamp` - When BUY order filled (from broker API)
- `exit_timestamp` - When exit order filled (from broker API)
- `quantity` - Number of contracts
- `profit_loss` - Dollar P/L (calculated: `(sell - buy) * qty * 100`)
- `pattern_type` - Pattern that triggered the trade: `'SM'` (Smart Reversal) or `'3C'` (3-Candle)

### daily_trade_stats table
Tracks daily win/loss statistics, updated on each trade exit:
- `trade_date` - Date (unique)
- `win_count` - Number of winning trades
- `loss_count` - Number of losing trades
- `total_percentage` - Sum of all trade percentages
- `total_profit_loss` - Sum of all dollar P/L

## API Endpoints
- `GET /daily-stats` - Today's stats (or `?date=YYYY-MM-DD`)
- `GET /daily-stats/all` - All daily stats (descending)

## Frontend Pages
- **Trades** (`/confirmations`) - Individual trade details with timestamps
  - Now includes **Symbol** column for multi-symbol trading (SPY, TSLA, NVDA)
  - Columns: No, Symbol, Triggered @, Entry, Exit, Timeframe, Strike Price, Buy Price, Sell Price, Dollar, Percentage, Status
- **Stats** (`/trades`) - Daily aggregated win/loss/P&L statistics

## Log Formats

### Smart Reversal Check (6-Candle)
```
# SIMPLIFIED MODE (default - SMART_REVERSAL_REQUIRE_EXHAUSTION = False, REQUIRE_BASE_BREAK = False)
[SmartReversal] tf=2m zone=N/A bar=2024-12-20 10:04:00 TRIGGER=PASS(62%) DROP=PASS(0.25%/$1.47) EXHAUST=PASS[disabled] RECLAIM=PASS(35.2%) BASE_BREAK=N/A result=PASS zone=IN_ZONE

# ADVANCED MODE (when exhaustion and base break are enabled)
[SmartReversal] tf=2m zone=N/A bar=2024-12-20 10:04:00 TRIGGER=PASS(62%) DROP=PASS(0.25%/$1.47) EXHAUST=PASS[indecision] RECLAIM=PASS(35.2%) BASE_BREAK=PASS result=PASS zone=IN_ZONE
```

### 3-Candle Trade Confirmed
```
✨✨✨✨✨✨✨✨ TRADE CONFIRMED (3-Candle Pattern-Only) ✨✨✨✨✨✨✨✨
TRADE CONFIRMED on 2m. Pattern: C1=strong bearish, C2=Hammer, C3=strong bullish entry.
✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨
```

### Smart Reversal Trade Confirmed
```
✨✨✨✨✨✨✨✨ SMART REVERSAL CONFIRMED ✨✨✨✨✨✨✨✨
TRADE CONFIRMED on 2m. Drop: 0.28% | Reclaim: 42.5% | Base: indecision
✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨
```
