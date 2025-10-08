
import argparse
import logging
from datetime import datetime
import pandas as pd
import re
from collections import deque

from ib_insync import IB, Stock, util

import config
from algotrade import patterns

# Configure logging for the backtest
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [PatternBacktest] - %(levelname)s - %(message)s')

def _convert_tf_to_ib_format(tf_string: str) -> str:
    """Converts a timeframe string like '5m' to the IB format like '5 mins'."""
    match = re.match(r"(\d+)([mh])$", tf_string.lower())
    if not match:
        raise ValueError(f"Invalid timeframe format: {tf_string}")
    
    value, unit_short = int(match.group(1)), match.group(2)
    
    if unit_short == 'm':
        unit_full = "min" if value == 1 else "mins"
    elif unit_short == 'h':
        unit_full = "hour" if value == 1 else "hours"
    else:
        raise ValueError(f"Unsupported timeframe unit: {unit_short}")

    return f"{value} {unit_full}"

def run_pattern_backtest(start_date_str: str, end_date_str: str):
    """
    Main backtesting function to identify candlestick patterns from historical data.
    """
    # --- Definitive Test for Config Value ---
    print(f"--- SCRIPT STARTED: Reading DRAGONFLY_DOJI_MAX_UPPER_WICK = {config.DRAGONFLY_DOJI_MAX_UPPER_WICK} ---")
    # --- End of Test ---
    
    ib = IB()
    try:
        # Use a different client ID for the backtest connection
        ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID + 3)
        logging.info("Connected to IB for historical data download.")

        contract = Stock(config.SYMBOL, config.EXCHANGE, config.CURRENCY)
        
        ib_bar_size = _convert_tf_to_ib_format(config.PATTERN_TIMEFRAME)
        logging.info(f"Downloading historical data for {config.PATTERN_TIMEFRAME} timeframe (IB format: '{ib_bar_size}')...")
        
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
        duration_days = (end_dt - start_dt).days
        if duration_days < 1:
            duration_days = 1
        duration_str = f"{duration_days} D"

        end_date_formatted = end_dt.strftime("%Y%m%d %H:%M:%S") + " US/Eastern"

        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_date_formatted,
            durationStr=duration_str,
            barSizeSetting=ib_bar_size,
            whatToShow='TRADES',
            useRTH=config.USE_RTH_ONLY,
            formatDate=1
        )
        
        if not bars:
            logging.error("Could not download historical data. Aborting.")
            return

        df = util.df(bars)
        
        if df is None or df.empty:
            logging.error("No historical data returned or DataFrame is empty. Aborting.")
            return
            
        # CRITICAL: Ensure data is sorted chronologically before processing.
        df = df.sort_values(by='date', ascending=True)
        
        df = df[df['date'] >= pd.to_datetime(start_dt, utc=True)]
        logging.info(f"Downloaded, sorted, and filtered {len(df)} bars.")

        # Use a deque to keep track of the last 2 candles
        candle_history = deque(maxlen=2)
        found_patterns = 0

        logging.info("Starting pattern identification...")
        for index, bar in df.iterrows():
            bar_series = pd.Series(bar, name=bar['date'])
            candle_history.append(bar_series)

            if len(candle_history) < 2:
                continue

            c1, c2 = candle_history[0], candle_history[1]

            # --- Temporary Debug Logging ---
            try:
                c1_range = c1.high - c1.low
                if c1_range > 0:
                    c1_body_pct = abs(c1.close - c1.open) / c1_range
                    c1_upper_wick_pct = (c1.high - max(c1.open, c1.close)) / c1_range
                    logging.info(
                        f"DEBUG C1 at {c1.name}: Body={c1_body_pct:.4f}, "
                        f"UpperWick={c1_upper_wick_pct:.4f}"
                    )
            except Exception:
                pass # Ignore any errors in debug logging
            # --- End of Debug Logging ---

            # --- Re-using the exact same logic as the live TradeService ---
            
            # 1. Identify all matching patterns for c1 (Indecision Candle)
            c1_triggered = []
            if patterns.is_doji(c1): c1_triggered.append("Doji")
            if patterns.is_dragonfly_doji(c1): c1_triggered.append("Dragonfly Doji")
            if patterns.is_hammer(c1): c1_triggered.append("Hammer")
            if patterns.is_spinning_top(c1): c1_triggered.append("Spinning Top")

            if not c1_triggered:
                continue

            # 2. Identify all matching patterns for c2 (Confirmation Candle)
            c2_triggered = []
            if patterns.is_bullish_marubozu(c2): c2_triggered.append("Bullish Marubozu")
            if patterns.is_bullish_engulfing(c1, c2): c2_triggered.append("Bullish Engulfing")
            if patterns.is_strong_bullish_candle(c2): c2_triggered.append("Strong Bullish Candle")

            if not c2_triggered:
                continue

            # 3. Final check on c2's bottom wick as per user rule
            # All c2 patterns are bullish, so open < close
            body_c2 = c2['close'] - c2['open']
            lower_wick_c2 = c2['open'] - c2['low']

            if lower_wick_c2 >= body_c2:
                continue

            # 4. Log the detailed confirmation
            logging.info(
                f"PATTERN CONFIRMED at {c2.name}: "
                f"c1={', '.join(c1_triggered)}, c2={', '.join(c2_triggered)}"
            )
            found_patterns += 1
        
        logging.info(f"Backtest finished. Found {found_patterns} valid patterns.")

    except Exception as e:
        logging.error(f"An error occurred during the backtest: {e}", exc_info=True)
    finally:
        if ib.isConnected():
            ib.disconnect()
            logging.info("Disconnected from IB.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a backtest to identify candlestick confirmation patterns.")
    parser.add_argument("--start-date", required=True, help="Start date for backtest (YYYY-MM-DD).")
    parser.add_argument("--end-date", required=True, help="End date for backtest (YYYY-MM-DD).")
    
    args = parser.parse_args()
    
    try:
        datetime.strptime(args.start_date, '%Y-%m-%d')
        datetime.strptime(args.end_date, '%Y-%m-%d')
    except ValueError:
        print("Error: Dates must be in YYYY-MM-DD format.")
        exit(1)

    run_pattern_backtest(start_date_str=args.start_date, end_date_str=args.end_date)
