
import argparse
import logging
from datetime import datetime
import pandas as pd
import re
from collections import deque
import json

from ib_insync import IB, Stock, util

import config
from algotrade import patterns

# Configure logging for the backtest
logging.basicConfig(level=config.BACKTEST_LOG_LEVEL, format='%(asctime)s - [PatternBacktest] - %(levelname)s - %(message)s')

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
    Main backtesting function. Loads demand zones from a file, then checks
    for candlestick confirmation patterns within those zones.
    """
    # 1. Load demand zones from the file
    try:
        with open("backtest_zones.txt", "r") as f:
            loaded_zones = json.load(f)
        if not loaded_zones:
            logging.error("backtest_zones.txt is empty. Run the zone backtest first.")
            return
        logging.info(f"Successfully loaded {len(loaded_zones)} demand zones from backtest_zones.txt.")
    except FileNotFoundError:
        logging.error("backtest_zones.txt not found. Please run the demand zone backtest first.")
        return
    except json.JSONDecodeError:
        logging.error("Could not parse backtest_zones.txt. The file may be corrupt.")
        return

    ib = IB()
    try:
        ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID + 3)
        logging.info("Connected to IB for historical data download.")

        contract = Stock(config.SYMBOL, config.EXCHANGE, config.CURRENCY)
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
        duration_days = (end_dt - start_dt).days
        if duration_days < 1:
            duration_days = 1
        duration_str = f"{duration_days} D"
        end_date_formatted = end_dt.strftime("%Y%m%d %H:%M:%S") + " US/Eastern"

        # Loop through each configured pattern timeframe
        for timeframe in config.PATTERN_TIMEFRAMES:
            logging.info(f"--- Starting backtest for timeframe: {timeframe} ---")
            
            ib_bar_size = _convert_tf_to_ib_format(timeframe)
            logging.info(f"Downloading historical data for {timeframe} (IB format: '{ib_bar_size}')...")

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
                logging.error(f"Could not download historical data for {timeframe}. Skipping.")
                continue

            df = util.df(bars)
            
            if df is None or df.empty:
                logging.error(f"No historical data for {timeframe} or DataFrame is empty. Skipping.")
                continue
                
            df = df.sort_values(by='date', ascending=True)
            df = df[df['date'] >= pd.to_datetime(start_dt, utc=True)]
            logging.info(f"Downloaded, sorted, and filtered {len(df)} bars for {timeframe}.")

            candle_history = deque(maxlen=2)
            found_patterns = 0

            logging.info(f"Starting pattern identification for {timeframe} within loaded zones...")
            for index, bar in df.iterrows():
                bar_series = pd.Series(bar, name=bar['date'])
                candle_history.append(bar_series)

                if len(candle_history) < 2:
                    continue

                c1, c2 = candle_history[0], candle_history[1]

                logging.debug(f"Analyzing candles:\nC1: {c1.to_dict()}\nC2: {c2.to_dict()}")

                # Check if the candle's range overlaps with any loaded demand zone
                active_zone = None
                for zone in loaded_zones:
                    if c2['low'] <= zone['zone_top'] and c2['high'] >= zone['zone_bottom']:
                        active_zone = zone
                        break # Found a zone, no need to check others for this bar
                
                if not active_zone:
                    continue # Not in any zone, move to the next bar

                # If in a zone, proceed with pattern matching
                logging.debug(f"Bar at {c2.name} is inside zone {active_zone['id']}. Checking for patterns.")

                c1_triggered = [p_name for p_name, p_func in patterns.INDECISION_PATTERNS.items() if p_func(c1)]
                if not c1_triggered:
                    continue

                c2_triggered = [p_name for p_name, p_func in patterns.CONFIRMATION_PATTERNS.items() if p_func(c2)]
                if not c2_triggered:
                    continue

                body_c2 = c2['close'] - c2['open']
                if body_c2 <= 0: # Ensure c2 is bullish before checking wick
                    continue
                lower_wick_c2 = c2['open'] - c2['low']

                if lower_wick_c2 >= body_c2:
                    continue

                # Log the confirmation
                logging.info(f"Trade confirmed with bar timestamp: {c2.name}")
                found_patterns += 1
            
            logging.info(f"Backtest for {timeframe} finished. Found {found_patterns} valid trade confirmations.")

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
