import multiprocessing
import logging
import time
import sys

# It's good practice to put service imports in a try-except block 
# to provide clearer error messages if dependencies are missing.
try:
    from algotrade.analysis_service import start_analysis_service
    from algotrade.trade_service import start_trade_service
except ImportError as e:
    print(f"Error importing services: {e}")
    print("Please ensure all dependencies are installed and the algotrade package is correctly structured.")
    sys.exit(1)

def main():
    """
    Main entry point for the application.
    Launches the Analysis Service and Trade Service as separate processes.
    """
    # Configure basic logging for the main orchestrator process
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - [Main] - %(levelname)s - %(message)s')

    logging.info("Initializing application services...")

    # A list to hold the process objects
    processes = []

    try:
        # Create and add the Analysis Service process
        analysis_process = multiprocessing.Process(target=start_analysis_service, name="AnalysisService")
        processes.append(analysis_process)

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
    # Set start method for multiprocessing for compatibility across platforms (e.g., macOS, Windows)
    multiprocessing.set_start_method('fork')
    main()