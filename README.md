
# SPY Demand Zone Trading Bot

This project is an automated, multi-service algorithmic trading bot designed to trade SPY based on the principles of supply and demand.

## Architecture

The system is built on a robust, decoupled three-service architecture that uses Redis for high-performance communication and state management.

![Architecture Diagram](https://i.imgur.com/3y3uY3A.png) *A simplified representation of the service interaction.*

1.  **Analysis Service (`algotrade/analysis_service.py`)**
    *   **Responsibility:** Identifies potential demand zones by analyzing market data based on the timeframes specified in `config.py`.
    *   **Action:** When a valid zone is found, it publishes the zone details to a Redis channel and sets the `current_demand_zone` key with an `active` status.

2.  **Invalidation Service (`algotrade/invalidation_service.py`)**
    *   **Responsibility:** Provides critical, independent risk management.
    *   **Action:** Subscribes to 1-minute bars. If a bar closes below an active demand zone, it invalidates the zone by deleting it from Redis. It also cleans up the zone if the price has clearly respected it and moved on, preventing stale data.

3.  **Trade Service (`algotrade/trade_service.py`)**
    *   **Responsibility:** Manages trade entry and confirmation logic.
    *   **Action:** Monitors the active demand zone from Redis. When the price enters a zone, it begins analyzing the chart for a specific two-candle confirmation pattern to find a high-probability entry.

### Core Logic: Two-Candle Pattern Confirmation

The `Trade Service` confirms a trade by identifying the following sequence on the `PATTERN_TIMEFRAME` defined in `config.py`:

1.  **C1 - The Indecision Candle:** The first candle must be a Doji, Dragonfly Doji, Hammer, or Spinning Top.
2.  **C2 - The Confirmation Candle:** The second candle must be a Bullish Marubozu or a Strong Bullish Candle.
3.  **Final Filter:** The `c2` candle's lower wick must be smaller than its body.

## Configuration

All major parameters for the system can be tuned in the `config.py` file. This includes IB connection settings, timeframes, and the sensitivity thresholds for all candlestick patterns (e.g., `DOJI_PRECISION`).

## Usage

### Live Trading

To run the bot with all three live services, execute the main orchestrator:

```sh
python main.py
```

### Backtesting

The project includes two separate backtesting scripts for validating different parts of the logic.

**1. Demand Zone Analysis Backtest**

To test the demand zone identification algorithm on historical data:

```sh
python run_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

**2. Candlestick Pattern Backtest**

To test the two-candle confirmation pattern logic on historical data (independent of demand zones):

```sh
python run_pattern_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```
