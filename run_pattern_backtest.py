
import argparse
import logging
from datetime import datetime, timedelta
import pandas as pd
import re
from collections import deque
import json

from ib_insync import IB, Stock, util

import config
from algotrade import patterns
from algotrade.logger import setup_logger

logger = setup_logger(__name__, level=config.BACKTEST_LOG_LEVEL)

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
    for the 5-candle confirmation pattern within those zones.
    """
    # 1. Load demand zones
    try:
        with open("backtest_zones.txt", "r") as f:
            loaded_zones = json.load(f)
        if not loaded_zones:
            logger.error("backtest_zones.txt is empty. Run the zone backtest first.")
            return
        logger.info(f"Successfully loaded {len(loaded_zones)} demand zones from backtest_zones.txt.")
    except FileNotFoundError:
        logger.error("backtest_zones.txt not found. Please run the demand zone backtest first.")
        return
    except json.JSONDecodeError:
        logger.error("Could not parse backtest_zones.txt. The file may be corrupt.")
        return

    ib = IB()
    try:
        ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID + 3)
        logger.info("Connected to IB for historical data download.")

        contract = Stock(config.SYMBOL, config.EXCHANGE, config.CURRENCY)
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')

        # Loop through each configured pattern timeframe
        for timeframe in config.PATTERN_TIMEFRAMES:
            logger.info(f"--- Starting backtest for timeframe: {timeframe} ---")
            
            ib_bar_size = _convert_tf_to_ib_format(timeframe)

            logger.info(f"Downloading historical data with bar size: '{{ib_bar_size}}'...")

            all_bars = []
            current_dt = start_dt
            while current_dt <= end_dt:
                end_date_formatted = current_dt.strftime("%Y%m%d 23:59:59") + " US/Eastern"
                logger.debug(f"Fetching data for {{current_dt.strftime('%Y-%m-%d')}}")
                
                bars_for_day = ib.reqHistoricalData(
                    contract,
                    endDateTime=end_date_formatted,
                    durationStr='1 D',
                    barSizeSetting=ib_bar_size,
                    whatToShow='TRADES',
                    useRTH=config.USE_RTH_ONLY,
                    formatDate=1
                )
                if bars_for_day:
                    all_bars.extend(bars_for_day)
                
                current_dt += timedelta(days=1)

            bars = all_bars
            
            if not bars:
                logger.error(f"Could not download historical data for {{timeframe}}. Skipping.")
                continue

            df = util.df(bars)
            if df is None or df.empty:
                logger.error(f"No historical data for {{timeframe}} or DataFrame is empty. Skipping.")
                continue
            
            df = df.sort_values(by='date', ascending=True)
            df = df[df['date'] >= pd.to_datetime(start_dt, utc=True)]
            logger.info(f"Downloaded, sorted, and filtered {{len(df)}} bars for {{timeframe}}.")

            candle_history = deque(maxlen=5)
            found_patterns = 0

            logger.info(f"Starting 5-candle pattern identification for {timeframe} within loaded zones...")
            for index, bar in df.iterrows():
                bar_series = pd.Series(bar, name=bar['date'])
                candle_history.append(bar_series)

                if len(candle_history) < 5:
                    continue

                candles = list(candle_history)
                c5, c4, c3, c2, c1 = candles

                # Check if the indecision candle (c4) is inside any demand zone
                active_zone = None
                for zone in loaded_zones:
                    zone_top = zone['zone_top']
                    zone_bottom = zone['zone_bottom']
                    
                    c4_in_zone = (zone_bottom <= c4['open'] <= zone_top or
                                  zone_bottom <= c4['high'] <= zone_top or
                                  zone_bottom <= c4['low'] <= zone_top or
                                  zone_bottom <= c4['close'] <= zone_top)
                    
                    if c4_in_zone:
                        active_zone = zone
                        break
                
                if not active_zone:
                    continue # c4 not in any zone, move to the next bar

                # If c4 is in a zone, check the full 5-candle pattern
                if patterns.check_5_candle_confirmation_pattern(candles):
                    logger.info(
                        f"\n✨✨✨✨✨✨✨✨ 5-CANDLE PATTERN CONFIRMED (Backtest) ✨✨✨✨✨✨✨✨\n"
                        f"CONFIRMED on {timeframe} at {c1.name}: Zone {{active_zone['id']}}. "
                        f"Pattern: c5 bullish, c4 indecision, c3-c1 bearish mix."
                        f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                    )
                    found_patterns += 1
            
            logger.info(f"Backtest for {timeframe} finished. Found {found_patterns} valid trade confirmations.")

    except Exception as e:
        logger.error(f"An error occurred during the backtest: {e}", exc_info=True)
    finally:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IB.")


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
