
import argparse
import logging
from datetime import datetime, timedelta
import pandas as pd

from ib_insync import IB, Stock, util

import config
from algotrade.analysis import AnalysisEngine

# Configure logging for the backtest
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Backtest] - %(levelname)s - %(message)s')

def run_backtest(start_date_str: str, end_date_str: str):
    """
    Main backtesting function to identify demand zones from historical data.
    """
    ib = IB()
    try:
        ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID + 2)
        logging.info("Connected to IB for historical data download.")

        contract = Stock(config.SYMBOL, config.EXCHANGE, config.CURRENCY)
        
        analysis_tf = config.ZONE_TIMEFRAMES[0]
        logging.info(f"Downloading historical data for {analysis_tf} timeframe...")
        
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
        duration_days = (end_dt - start_dt).days
        if duration_days < 1:
            duration_days = 1
        duration_str = f"{duration_days} D"

        end_date_formatted = end_dt.strftime("%Y%m%d %H:%M:%S")

        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_date_formatted,
            durationStr=duration_str,
            barSizeSetting=analysis_tf,
            whatToShow='TRADES',
            useRTH=config.USE_RTH_ONLY,
            formatDate=1
        )
        
        if not bars:
            logging.error("Could not download historical data. Aborting.")
            return

        df = util.df(bars)
        df = df[df['date'] >= pd.to_datetime(start_dt, utc=True)]
        logging.info(f"Downloaded and filtered {len(df)} bars.")

        analysis_engine = AnalysisEngine()

        logging.info("Starting demand zone identification...")
        for index, bar in df.iterrows():
            bar_series = pd.Series(bar, name=bar['date'])
            
            # Analyze the bar to find a new demand zone.
            new_zone = analysis_engine.process_new_bar(bar_series, timeframe=analysis_tf)
            
            # If a zone is found, log its details.
            if new_zone:
                logging.info(f"DEMAND ZONE IDENTIFIED at {bar['date']}: Top={new_zone['zone_top']:.2f}, Bottom={new_zone['zone_bottom']:.2f}")

        logging.info("Backtest finished.")

    except Exception as e:
        logging.error(f"An error occurred during the backtest: {e}", exc_info=True)
    finally:
        if ib.isConnected():
            ib.disconnect()
            logging.info("Disconnected from IB.")


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
