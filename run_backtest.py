
import argparse
import logging
from datetime import datetime, timedelta
import pandas as pd
import re
import json

from ib_insync import IB, Stock, util

import config
from algotrade.analysis import AnalysisEngine
from algotrade.logger import setup_logger

logger = setup_logger(__name__, level=config.BACKTEST_LOG_LEVEL)

def _convert_tf_to_ib_format(tf_string: str) -> str:
    """Converts a timeframe string like '1m' or '2h' to the IB format like '1 min' or '2 hours'."""
    match = re.match(r"(\d+)([mh])$", tf_string.lower())
    if not match:
        raise ValueError(f"Invalid timeframe format for backtesting: {tf_string}")
    
    value, unit_short = int(match.group(1)), match.group(2)
    
    if unit_short == 'm':
        unit_full = "min" if value == 1 else "mins"
    elif unit_short == 'h':
        unit_full = "hour" if value == 1 else "hours"
    else:
        raise ValueError(f"Unsupported timeframe unit: {unit_short}")

    return f"{value} {unit_full}"

def run_backtest(start_date_str: str, end_date_str: str):
    """
    Main backtesting function to identify demand zones from historical data
    for all configured zone timeframes and save them to a file.
    """
    # Start with a clean slate for backtest results
    logger.info("Clearing previous backtest zone results...")
    with open("backtest_zones.txt", "w") as f:
        json.dump([], f) # Write an empty JSON array
    logger.info("Previous results cleared. Starting new backtest run.")

    ib = IB()
    all_found_zones = [] # List to store all zones found across all timeframes
    try:
        ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID + 2)
        logger.info("Connected to IB for historical data download.")

        contract = Stock(config.SYMBOL, config.EXCHANGE, config.CURRENCY)
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
        duration_days = (end_dt - start_dt).days
        if duration_days < 1:
            duration_days = 1
        duration_str = f"{duration_days} D"
        end_date_formatted = end_dt.strftime("%Y%m%d %H:%M:%S") + " US/Eastern"

        # Loop through each configured zone timeframe
        for timeframe in config.ZONE_TIMEFRAMES:
            logger.info(f"--- Starting backtest for timeframe: {timeframe} ---")
            
            ib_bar_size = _convert_tf_to_ib_format(timeframe)
            logger.info(f"Downloading historical data for {timeframe} timeframe (IB format: '{ib_bar_size}')...")

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
                logger.error(f"Could not download historical data for {timeframe}. Skipping.")
                continue

            df = util.df(bars)
            if df is None or df.empty:
                logger.error(f"No historical data for {timeframe} or DataFrame is empty. Skipping.")
                continue

            df = df[df['date'] >= pd.to_datetime(start_dt, utc=True)]
            logger.info(f"Downloaded and filtered {len(df)} bars for {timeframe}.")

            # Important: A new AnalysisEngine is created for each timeframe
            # to ensure no state (like previous candles) leaks between tests.
            analysis_engine = AnalysisEngine()

            logger.info(f"Starting demand zone identification for {timeframe}...")
            for index, bar in df.iterrows():
                bar_series = pd.Series(bar, name=bar['date'])
                
                new_zone = analysis_engine.process_new_bar(bar_series, timeframe=timeframe)
                
                if new_zone:
                    # Note: The log from process_new_bar is now the primary source of info.
                    # This additional log can be redundant but is kept for explicit backtest confirmation.
                    logger.info(f"BACKTEST: DEMAND ZONE IDENTIFIED on {timeframe} at {bar['date']}")
                    all_found_zones.append(new_zone)

            logger.info(f"Backtest for {timeframe} finished.")

        # After all timeframes are done, write the collected zones to a file
        if all_found_zones:
            logger.info(f"Found a total of {len(all_found_zones)} zones. Saving to backtest_zones.txt...")
            with open("backtest_zones.txt", "w") as f:
                json.dump(all_found_zones, f, indent=4)
            logger.info("Successfully saved zones to backtest_zones.txt.")
        else:
            logger.warning("No demand zones were identified in this backtest run.")

    except Exception as e:
        logger.error(f"An error occurred during the backtest: {e}", exc_info=True)
    finally:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IB.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a backtest to identify demand zones from historical data.")
    parser.add_argument("--start-date", required=True, help="Start date for backtest (YYYY-MM-DD).")
    parser.add_argument("--end-date", required=True, help="End date for backtest (YYYY-MM-DD).")
    
    args = parser.parse_args()
    
    try:
        start = datetime.strptime(args.start_date, '%Y-%m-%d')
        end = datetime.strptime(args.end_date, '%Y-%m-%d')
    except ValueError:
        print("Error: Dates must be in YYYY-MM-DD format.")
        exit(1)

    run_backtest(start_date_str=args.start_date, end_date_str=args.end_date)
