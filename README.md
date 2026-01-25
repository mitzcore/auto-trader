
# SPY Demand Zone Trading Bot

This project is an automated, multi-service algorithmic trading bot designed to trade SPY based on the principles of supply and demand.

## Architecture

The system is built on a decoupled three-service architecture using SQLite for persistence.

1.  **Analysis Service (`algotrade/analysis_service.py`)**
    *   **Responsibility:** Identifies potential demand zones by analyzing market data based on the timeframes specified in `config.py`.
    *   **Action:** When a valid zone is found, it stores the zone details in the SQLite database.

2.  **Invalidation Service (`algotrade/invalidation_service.py`)**
    *   **Responsibility:** Provides critical, independent risk management.
    *   **Action:** Subscribes to 1-minute bars. If a bar closes below an active demand zone, it invalidates the zone.

3.  **Trade Service (`algotrade/trade_service.py`)**
    *   **Responsibility:** Manages trade entry and confirmation logic.
    *   **Action:** Monitors active demand zones. When the price enters a zone, it analyzes the chart for candlestick confirmation patterns to find a high-probability entry.

### Candlestick Pattern Confirmation

The `Trade Service` supports multiple pattern modes (configured via `PATTERN_MODE` in `config.py`):

**6-Candle Pattern:**
| Candle | Role | Criteria |
|--------|------|----------|
| C6 | Strong bullish entry | Body >= 60% of range |
| C5 | Indecision | Doji, Hammer, Spinning Top, Dragonfly Doji |
| C4-C1 | Bearish descent | Need 1 strong bearish + 1 small/neutral bearish |

**3-Candle Pattern:**
| Candle | Role | Criteria |
|--------|------|----------|
| C3 | Strong bullish entry | Body >= 50% of range |
| C2 | Indecision | Doji, Hammer, Spinning Top, Dragonfly Doji |
| C1 | Strong bearish | Body >= 50% of range |

## Configuration

All major parameters for the system can be tuned in the `config.py` file. This includes IB connection settings, timeframes, and the sensitivity thresholds for all candlestick patterns (e.g., `DOJI_PRECISION`, `STRONG_BULLISH_MIN_BODY_PCT`).

## Usage

### Live Trading

To run the bot with all three live services, execute the main orchestrator:

```sh
python main.py
```

### Backtesting

```sh
# Use default PATTERN_MODE from config
python run_pattern_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD

# Override pattern mode via CLI
python run_pattern_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --pattern 6_candle
python run_pattern_backtest.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --pattern 3_candle
```
