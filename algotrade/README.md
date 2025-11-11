# Automated Trading Bot for Interactive Brokers

This project implements an automated trading bot designed to trade SPY based on demand zone analysis and candlestick pattern confirmations. The bot is built with a microservice-style architecture, leveraging Redis for high-performance inter-service communication and SQLite for persistent data storage.

## Architecture Overview

The bot operates as a multi-process application, orchestrated by `main.py`, comprising three core services:

1.  **Analysis Service (`analysis_service.py`)**:
    *   **Purpose**: Identifies potential demand zones from real-time candlestick data.
    *   **Data Source**: Connects to Interactive Brokers (IB) to fetch historical and real-time bar data for multiple configurable timeframes (e.g., 2m, 5m, 15m).
    *   **Logic**: Uses the `AnalysisEngine` (`analysis.py`) to apply a sophisticated set of rules (based on candle body ratios, wick sizes, and engulfing patterns) to detect valid demand zones.
    *   **Communication**: Publishes newly identified demand zones to a Redis channel (`demand_zones`) and stores them in a Redis hash (`active_demand_zones`) with an `active` status.

2.  **Trade Service (`trade_service.py`)**:
    *   **Purpose**: Confirms trade entries based on specific candlestick patterns within active demand zones.
    *   **Data Source**: Connects to IB to poll for completed bar data for configurable pattern timeframes (e.g., 1m, 2m).
    *   **Logic**: Monitors active demand zones from Redis. When a price bar (specifically the C4 candle in a 5-candle pattern) falls within an active zone, it then checks for a predefined 5-candle confirmation pattern using the `patterns.py` module.
    *   **Modes**: Can operate in `DEMAND_ZONE_TRADING` mode (patterns only confirmed within zones) or "pattern-only" mode (trades any valid pattern).
    *   **Execution**: Upon confirmation, it triggers an order placement via an `ExecutionHandler` (`execution.py`). Supports both live trading (`LiveExecutionHandler`) and paper trading (`PaperExecutionHandler`). Paper trades are logged to SQLite and monitored in a separate thread for profit-taking or stop-loss.

3.  **Invalidation Service (`invalidation_service.py`)**:
    *   **Purpose**: Provides risk management by invalidating demand zones if price action breaks below them.
    *   **Data Source**: Connects to IB to poll for completed 1-minute bar data.
    *   **Logic**: Continuously monitors all `active` demand zones stored in Redis. If a 1-minute bar closes below the `zone_bottom` of an active demand zone, that zone is marked as invalidated (removed from Redis).
    *   **Paper Trade Integration**: If a paper trade is open for an invalidated zone, it triggers a simulated stop-loss.

## Core Components

*   **`main.py`**: The entry point of the application. It uses Python's `multiprocessing` to launch the Analysis, Trade, and Invalidation services as separate processes.
*   **`config.py`**: Centralized configuration file for all service parameters, IB connection details, pattern thresholds, and trading settings.
*   **`analysis.py`**: Contains the `AnalysisEngine` class, which implements the core demand zone detection algorithm.
*   **`patterns.py`**: A library of candlestick pattern detection functions used by the `TradeService` for trade confirmation.
*   **`execution.py`**: Defines `ExecutionHandler` interfaces and concrete implementations for live, paper, and backtesting trade execution.
*   **`orders.py`**: Handles the specifics of placing and managing orders with Interactive Brokers, including bracket orders with profit targets and dynamic stop-losses.
*   **`database.py`**: Manages SQLite database interactions for logging demand zones, trade confirmations, and placed trades.
*   **`logger.py`**: Configures a standardized logging system for all services, outputting to both console and a file.
*   **`util.py`**: Provides utility functions, such as converting timeframe strings and mapping them to IBKR's format.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd algotrade
    ```
2.  **Create a Python virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt # (Assuming a requirements.txt exists or will be created)
    ```
    *(If `requirements.txt` does not exist, you will need to install `ib_insync`, `pandas`, `redis`, `fastapi`, `uvicorn`, `nest_asyncio`, `pytz`, `sqlite3` (usually built-in), and `python-dateutil` manually.)*
4.  **Redis Server:** Ensure a Redis server is running and accessible at the host and port specified in `config.py`.
5.  **Interactive Brokers TWS/Gateway:** Ensure IB TWS or Gateway is running and configured to accept API connections on the host and port specified in `config.py`. Make sure to enable API connections and specify a trusted IP if necessary.
6.  **Configure `config.py`**: Adjust parameters in `algotrade/config.py` according to your preferences, especially `IB_HOST`, `IB_PORT`, `PAPER_TRADE`, `TRADE_ORDERS`, and pattern thresholds.

## Running the Bot

To start the bot, execute `main.py`. This will launch all three services in separate processes.

```bash
python main.py
```

## Backtesting

*(Note: The current backtesting functionality is limited to `run_backtest.py` for analysis and `run_pattern_backtest.py` for pattern validation. A full trading backtest framework is not yet implemented.)*

*   **`run_backtest.py`**: Used to identify demand zones from historical data.
    ```bash
    python run_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
    ```
*   **`run_pattern_backtest.py`**: Used to test the 5-candle pattern logic on historical data.
    ```bash
    python run_pattern_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
    ```

## Database Management

The bot uses an SQLite database (`trading_data.db`) to store demand zones and trade confirmations. The `database.py` module provides functions for interaction.

*   **Initialization**: The database and tables are automatically created if they don't exist when `database.py` is run or imported.
*   **Manual Zones**: You can pre-define demand zones in `config.CUSTOM_DEMAND_ZONES` which will be synced to the database on service startup.

## Logging

All services log their activities to the console and to a file specified by `LOG_FILE` in `config.py`. This is crucial for monitoring bot operations and debugging.
