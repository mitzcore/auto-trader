import multiprocessing
import logging
import time
import sys
import redis
import json
import config

# It's good practice to put service imports in a try-except block 
# to provide clearer error messages if dependencies are missing.
try:
    from algotrade.analysis_service import start_analysis_service
    from algotrade.trade_service import start_trade_service
    from algotrade.invalidation_service import start_invalidation_service
    from algotrade.database import clear_demand_zones, create_db_and_tables
except ImportError as e:
    print(f"Error importing services: {e}")
    print("Please ensure all dependencies are installed and the algotrade package is correctly structured.")
    sys.exit(1)

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

    # Connect to Redis for initial setup
    redis_client = redis.Redis(decode_responses=True)

    # Clear all existing demand zones from Redis on startup
    logging.info("Clearing all existing demand zones from Redis...")
    redis_client.delete("active_demand_zones")
    logging.info("Existing demand zones cleared from Redis.")

    # A list to hold the process objects
    processes = []

    try:
        if config.DEMAND_ZONE_TRADING:
            if config.CUSTOM_DEMAND_ZONES:
                logging.info(f"Custom demand zones found in config. Loading {len(config.CUSTOM_DEMAND_ZONES)} zones.")
                
                # Publish each custom zone to the updates channel
                for custom_zone_config in config.CUSTOM_DEMAND_ZONES:
                    zone = {
                        "zone_top": custom_zone_config["zone_top"],
                        "zone_bottom": custom_zone_config["zone_bottom"],
                        "zone_timeframe": "custom",
                        "status": "active",
                        "entry_confirmation": None,
                        "invalidation_confirmation": None,
                    }
                    # Use hset to store the zone in the hash, with zone_id as the field
                    zone_id = f"custom_zone_{custom_zone_config['zone_top']}_{custom_zone_config['zone_bottom']}"
                    redis_client.hset("active_demand_zones", zone_id, json.dumps(zone))
                    logging.info(f"Loaded custom demand zone into Redis: {zone}")
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
    # Configure logging for the main orchestrator process
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [MainOrchestrator] - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)  # Ensure logs go to standard output
        ]
    )
    
    # Set start method for multiprocessing for compatibility across platforms (e.g., macOS, Windows)
    # 'fork' is generally fine for Unix-like systems, but 'spawn' is safer and more cross-platform.
    # Consider 'spawn' if you encounter issues on different OSes.
    multiprocessing.set_start_method('fork')
    
    main()