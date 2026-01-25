import multiprocessing
import logging
import time
import sys
import argparse
import config

# It's good practice to put service imports in a try-except block
# to provide clearer error messages if dependencies are missing.
try:
    from algotrade.analysis_service import start_analysis_service
    from algotrade.trade_service import start_trade_service
    from algotrade.invalidation_service import start_invalidation_service
    from algotrade.database import clear_demand_zones, create_db_and_tables, sync_config_zones_to_db
except ImportError as e:
    print(f"Error importing services: {e}")
    print("Please ensure all dependencies are installed and the algotrade package is correctly structured.")
    sys.exit(1)


def apply_symbol_config(symbol):
    """
    Apply symbol-specific configuration from SYMBOLS_CONFIG.

    Args:
        symbol: Symbol to configure (e.g., "SPY", "QQQ", "NVDA")
    """
    if not hasattr(config, 'SYMBOLS_CONFIG') or symbol not in config.SYMBOLS_CONFIG:
        logging.warning(f"No configuration found for symbol {symbol} in SYMBOLS_CONFIG. Using defaults.")
        config.SYMBOL = symbol
        return

    symbol_config = config.SYMBOLS_CONFIG[symbol]

    # Set symbol
    config.SYMBOL = symbol

    # Set strike spacing
    if "strike_spacing" in symbol_config:
        config.STRIKE_SPACING = symbol_config["strike_spacing"]

    # Set strike selection mode (ITM/ATM/OTM)
    if "strike_selection_mode" in symbol_config:
        config.STRIKE_SELECTION_MODE = symbol_config["strike_selection_mode"]

    # Set ITM offset
    if "itm_offset" in symbol_config:
        config.ITM_OFFSET = symbol_config["itm_offset"]

    # Set OTM offset
    if "otm_offset" in symbol_config:
        config.OTM_OFFSET = symbol_config["otm_offset"]

    # Set IB client ID offset
    if "client_id_offset" in symbol_config:
        config.IB_CLIENT_ID = config.IB_CLIENT_ID + symbol_config["client_id_offset"]

    # Override timeframes if specified
    if "timeframes" in symbol_config:
        config.TRADING_TIMEFRAMES = symbol_config["timeframes"]

    # Apply any symbol-specific pattern settings
    if "min_drop_pct" in symbol_config:
        config.SMART_REVERSAL_MIN_DROP_PCT = symbol_config["min_drop_pct"]

    # Update log file to include symbol
    if hasattr(config, 'LOG_FILE'):
        base_name = config.LOG_FILE.replace('.log', '')
        config.LOG_FILE = f"{base_name}_{symbol}.log"
    else:
        config.LOG_FILE = f"trading_bot_{symbol}.log"

    logging.info(f"Applied configuration for symbol: {symbol}")
    logging.info(f"  Strike Spacing: {config.STRIKE_SPACING}")
    logging.info(f"  Strike Selection: {config.STRIKE_SELECTION_MODE}")
    logging.info(f"  ITM Offset: ${config.ITM_OFFSET}")
    logging.info(f"  OTM Offset: ${config.OTM_OFFSET}")
    logging.info(f"  IB Client ID: {config.IB_CLIENT_ID}")
    logging.info(f"  Timeframes: {config.TRADING_TIMEFRAMES}")
    logging.info(f"  Log File: {config.LOG_FILE}")

def main():
    """
    Main entry point for the application.
    Launches the Analysis, Trade, and Invalidation Services as separate processes.
    """
    logging.info("Initializing application services...")

    # Create database and tables if they don't exist
    create_db_and_tables()

    # Clear demand zones from the database at the start
    clear_demand_zones()

    # A list to hold the process objects
    processes = []

    try:
        if config.DEMAND_ZONE_TRADING:
            if config.CUSTOM_DEMAND_ZONES:
                logging.info(f"Custom demand zones found in config. Loading {len(config.CUSTOM_DEMAND_ZONES)} zones to database.")
                sync_config_zones_to_db()
            else:
                logging.info("No custom demand zones found.")

            logging.info("Starting all services.")
            # Create and add the Analysis Service process
            analysis_process = multiprocessing.Process(target=start_analysis_service, name="AnalysisService")
            processes.append(analysis_process)

            # Create and add the Invalidation Service process
            invalidation_process = multiprocessing.Process(target=start_invalidation_service, name="InvalidationService")
            processes.append(invalidation_process)
        else:
            logging.warning("DEMAND_ZONE_TRADING is disabled. Only starting TradeService.")

        # Create and add the Trade Service process
        trade_process = multiprocessing.Process(target=start_trade_service, name="TradeService")
        processes.append(trade_process)

        # Start all processes
        for p in processes:
            p.start()
            logging.info(f"Process '{p.name}' started with PID {p.pid}.")

        logging.info("All services are running.")

        # Wait for any process to exit or for a keyboard interrupt
        while all(p.is_alive() for p in processes):
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Shutdown signal received. Terminating all services...")
    
    except Exception as e:
        logging.error(f"An unexpected error occurred in the main orchestrator: {e}")
        logging.error("Terminating all services due to the error.")

    finally:
        # Gracefully terminate all running processes
        for p in processes:
            if p.is_alive():
                logging.info(f"Terminating process '{p.name}'...")
                p.terminate() # Sends SIGTERM
        
        # Wait for processes to terminate
        for p in processes:
            p.join(timeout=10) # Wait up to 10 seconds
            if p.is_alive():
                logging.warning(f"Process '{p.name}' did not terminate gracefully. Forcing shutdown.")
                p.kill() # Sends SIGKILL

        logging.info("Application has shut down.")
        sys.exit(0)


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='AlgoTrade - Algorithmic Trading Bot')
    parser.add_argument('--symbol', type=str, default=None,
                        help='Symbol to trade (e.g., SPY, QQQ, NVDA). Overrides config.SYMBOL.')
    args = parser.parse_args()

    # Apply symbol-specific configuration if provided
    if args.symbol:
        # Need basic logging before apply_symbol_config
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        apply_symbol_config(args.symbol.upper())

    # Configure logging for the main orchestrator process
    # If symbol was specified, logging will go to symbol-specific file
    log_handlers = [logging.StreamHandler(sys.stdout)]

    # Add file handler if LOG_FILE is set
    if hasattr(config, 'LOG_FILE') and config.LOG_FILE:
        try:
            log_handlers.append(logging.FileHandler(config.LOG_FILE))
        except Exception as e:
            print(f"Warning: Could not create log file {config.LOG_FILE}: {e}")

    logging.basicConfig(
        level=logging.INFO,
        format=f'%(asctime)s - [MainOrchestrator-{config.SYMBOL}] - %(levelname)s - %(message)s',
        handlers=log_handlers,
        force=True  # Override any existing config
    )

    # Set start method for multiprocessing for compatibility across platforms (e.g., macOS, Windows)
    # 'fork' is generally fine for Unix-like systems, but 'spawn' is safer and more cross-platform.
    # Consider 'spawn' if you encounter issues on different OSes.
    multiprocessing.set_start_method('fork')

    main()