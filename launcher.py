#!/usr/bin/env python3
"""
Multi-Symbol Trading Bot Launcher

Spawns separate trading bot processes for each enabled symbol in config.SYMBOLS_CONFIG.
Each process runs independently with its own IB client ID and log file.

Usage:
    # Start all enabled symbols:
    python launcher.py

    # Start specific symbol only (for debugging):
    python launcher.py --symbol SPY

    # Show help:
    python launcher.py --help
"""

import subprocess
import sys
import time
import signal
import argparse
from typing import List, Dict
import logging

# Import config to read symbol configuration
import config


class SymbolProcess:
    """Wrapper for a symbol trading process."""

    def __init__(self, symbol: str, symbol_config: Dict):
        self.symbol = symbol
        self.config = symbol_config
        self.process = None
        self.start_time = None

    def start(self):
        """Start the trading process for this symbol."""
        cmd = [sys.executable, "main.py", "--symbol", self.symbol]

        logging.info(f"[{self.symbol}] Starting process with command: {' '.join(cmd)}")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # Line buffered
        )
        self.start_time = time.time()

        logging.info(f"[{self.symbol}] Process started with PID {self.process.pid}")

    def is_alive(self) -> bool:
        """Check if process is still running."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def terminate(self):
        """Gracefully terminate the process."""
        if self.process and self.is_alive():
            logging.info(f"[{self.symbol}] Sending SIGTERM to PID {self.process.pid}")
            self.process.terminate()

    def kill(self):
        """Force kill the process."""
        if self.process and self.is_alive():
            logging.warning(f"[{self.symbol}] Force killing PID {self.process.pid}")
            self.process.kill()

    def wait(self, timeout=None):
        """Wait for process to exit."""
        if self.process:
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                pass


class MultiSymbolLauncher:
    """Manages multiple symbol trading processes."""

    def __init__(self, symbols: List[str] = None):
        """
        Initialize launcher.

        Args:
            symbols: List of symbols to run. If None, runs all enabled symbols from config.
        """
        self.processes: Dict[str, SymbolProcess] = {}
        self.running = False

        # Determine which symbols to run
        if symbols:
            # Specific symbols requested
            self.symbols_to_run = symbols
        else:
            # Get all enabled symbols from config
            if not hasattr(config, 'SYMBOLS_CONFIG'):
                logging.error("No SYMBOLS_CONFIG found in config.py!")
                sys.exit(1)

            self.symbols_to_run = [
                symbol for symbol, cfg in config.SYMBOLS_CONFIG.items()
                if cfg.get('enabled', False)
            ]

        if not self.symbols_to_run:
            logging.error("No symbols to run! Enable at least one symbol in config.SYMBOLS_CONFIG or specify --symbol")
            sys.exit(1)

        logging.info(f"Launcher initialized for symbols: {', '.join(self.symbols_to_run)}")

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logging.info(f"\nReceived signal {signum}. Initiating graceful shutdown...")
        self.running = False

    def start_all(self):
        """Start processes for all configured symbols."""
        logging.info("=" * 80)
        logging.info(f"Starting trading bot for {len(self.symbols_to_run)} symbol(s)")
        logging.info("=" * 80)

        for symbol in self.symbols_to_run:
            # Get symbol config
            symbol_config = config.SYMBOLS_CONFIG.get(symbol, {})

            # Create and start process
            proc = SymbolProcess(symbol, symbol_config)
            proc.start()
            self.processes[symbol] = proc

            # Small delay between starts to avoid IB connection race
            time.sleep(1)

        logging.info("=" * 80)
        logging.info(f"All {len(self.processes)} process(es) started successfully")
        logging.info("=" * 80)
        logging.info("Press Ctrl+C to stop all processes")
        logging.info("")

    def monitor_processes(self):
        """Monitor running processes and restart if needed."""
        self.running = True

        while self.running:
            try:
                # Check if any process has died
                for symbol, proc in list(self.processes.items()):
                    if not proc.is_alive():
                        exit_code = proc.process.returncode
                        runtime = time.time() - proc.start_time

                        logging.warning(
                            f"[{symbol}] Process died after {runtime:.1f}s with exit code {exit_code}"
                        )

                        # Restart if it didn't run long enough (likely a crash)
                        if runtime < 60:  # Less than 1 minute = likely crash
                            logging.info(f"[{symbol}] Attempting restart...")
                            proc.start()
                        else:
                            logging.warning(f"[{symbol}] Not restarting (ran for {runtime:.1f}s)")

                # Sleep between checks
                time.sleep(5)

            except KeyboardInterrupt:
                logging.info("\nKeyboard interrupt received. Shutting down...")
                self.running = False
                break

    def shutdown(self):
        """Gracefully shutdown all processes."""
        logging.info("=" * 80)
        logging.info("Shutting down all processes...")
        logging.info("=" * 80)

        # Send terminate signal to all
        for symbol, proc in self.processes.items():
            proc.terminate()

        # Wait for graceful shutdown (max 10 seconds per process)
        logging.info("Waiting for processes to exit gracefully (10s timeout)...")
        for symbol, proc in self.processes.items():
            proc.wait(timeout=10)

        # Force kill any remaining processes
        for symbol, proc in self.processes.items():
            if proc.is_alive():
                logging.warning(f"[{symbol}] Did not exit gracefully. Force killing...")
                proc.kill()
                proc.wait(timeout=2)

        logging.info("=" * 80)
        logging.info("All processes terminated")
        logging.info("=" * 80)

    def run(self):
        """Main run loop."""
        try:
            self.start_all()
            self.monitor_processes()
        except Exception as e:
            logging.error(f"Fatal error in launcher: {e}", exc_info=True)
        finally:
            self.shutdown()


def main():
    """Entry point for the launcher."""
    parser = argparse.ArgumentParser(
        description='Multi-Symbol Trading Bot Launcher',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start all enabled symbols:
  python launcher.py

  # Start specific symbol only (for debugging):
  python launcher.py --symbol SPY

  # Start multiple specific symbols:
  python launcher.py --symbol SPY --symbol QQQ
        """
    )
    parser.add_argument(
        '--symbol', '-s',
        action='append',
        help='Run specific symbol(s) only. Can be specified multiple times.'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - [Launcher] - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('launcher.log')
        ]
    )

    # Convert symbol list to uppercase
    symbols = [s.upper() for s in args.symbol] if args.symbol else None

    # Create and run launcher
    launcher = MultiSymbolLauncher(symbols=symbols)
    launcher.run()


if __name__ == "__main__":
    main()
