The project is an automated trading bot for SPY using a three-service architecture: Analysis, Trade, and Invalidation, with Redis for high-performance communication and SQLite for persistence.

**1. Analysis Service (`analysis_service.py`):**
*   **Role:** Identifies demand zones from real-time candlestick data across multiple timeframes (`config.ZONE_TIMEFRAMES`).
*   **Mechanism:** Uses `AnalysisEngine` (`analysis.py`) to apply sophisticated rules for zone detection (candle body ratios, wick sizes, engulfing patterns).
*   **Output:** Publishes new zones to a Redis channel (`demand_zones`) and stores them in a Redis hash (`active_demand_zones`) with an `active` status.

**2. Trade Service (`trade_service.py`):**
*   **Role:** Confirms trade entries based on specific candlestick patterns within active demand zones.
*   **Mechanism:** Polls IB for bar data for configurable pattern timeframes (`config.PATTERN_TIMEFRAMES`). Checks for a 5-candle confirmation pattern (`patterns.py`) within active demand zones (if `config.DEMAND_ZONE_TRADING` is True) or trades any valid pattern (if `config.DEMAND_ZONE_TRADING` is False).
*   **Execution:** Uses `LiveExecutionHandler` or `PaperExecutionHandler` (`execution.py`) to place orders. Paper trades are logged to SQLite and monitored in a separate thread for profit-taking or stop-loss.

**3. Invalidation Service (`invalidation_service.py`):**
*   **Role:** Provides risk management by invalidating demand zones.
*   **Mechanism:** Polls IB for 1-minute bar data. If a bar closes below an active demand zone's `zone_bottom`, the zone is removed from Redis.
*   **Integration:** Triggers a simulated stop-loss for open paper trades associated with invalidated zones.

**Key Components:**

*   **`main.py`**: Orchestrates the launch of the three services as separate processes using `multiprocessing`.
*   **`config.py`**: Centralized configuration for all services, IB connection, pattern thresholds, and trading settings.
*   **`analysis.py`**: Implements the `AnalysisEngine` for demand zone detection.
*   **`patterns.py`**: Library of candlestick pattern detection functions.
*   **`execution.py`**: Handles trade execution (live, paper, backtest).
*   **`orders.py`**: Manages IB order placement and monitoring (bracket orders, stop-loss).
*   **`database.py`**: SQLite database manager for demand zones and trade confirmations.
*   **`logger.py`**: Standardized logging to console and file.
*   **`util.py`**: Utility functions for timeframe conversions.

**Recent Enhancements & Key Features:**

*   **Multi-Service Architecture:** Decoupled Analysis, Trade, and Invalidation into distinct services for better scalability and maintainability.
*   **Redis Communication:** Utilizes Redis Pub/Sub for event-driven communication and a Redis hash for shared state (`active_demand_zones`).
*   **Sophisticated Demand Zone Detection:** `AnalysisEngine` uses refined logic with stricter checks on candle body ratios and wick sizes.
*   **5-Candle Confirmation Pattern:** `TradeService` implements a complex 5-candle pattern for trade entry confirmation, configurable via `config.PATTERN_TIMEFRAMES`.
*   **Paper Trading with Monitoring:** `PaperExecutionHandler` simulates trades, logs them to SQLite, and monitors for profit-taking or stop-loss in a separate thread.
*   **Dynamic Stop-Loss:** `orders.py` implements a dynamic stop-loss based on the demand zone's bottom for live trades.
*   **Invalidation Logic:** `InvalidationService` provides real-time risk management by invalidating zones and triggering paper trade stop-losses.
*   **Configurability:** Extensive use of `config.py` for all critical parameters.
*   **SQLite Persistence:** Demand zones and trade confirmations are logged to an SQLite database.
*   **Backtesting Scripts:** `run_backtest.py` for analysis and `run_pattern_backtest.py` for pattern validation.
