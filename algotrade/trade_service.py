import logging
import json
import redis
from collections import deque
import pandas as pd
from ib_insync import IB, Stock
import asyncio
import time

import config
from algotrade import patterns
from algotrade import v_pattern # Import the new v_pattern module
from algotrade.util import map_timeframe_to_ibkr
from algotrade.logger import setup_logger
from algotrade.database import log_trade_confirmation
from algotrade.execution import LiveExecutionHandler, PaperExecutionHandler

logger = setup_logger(__name__)

class TradeService:
    """
    Monitors for price entry into demand zones and confirms trades by polling
    for completed bars across multiple timeframes and checking for two-candlestick patterns.
    """

    def __init__(self):
        self._ib = IB()
        self._redis_client = redis.Redis(decode_responses=True)
        self._contract = Stock(config.SYMBOL, config.EXCHANGE, config.CURRENCY)
        
        self._candles = {tf: deque(maxlen=6) for tf in config.PATTERN_TIMEFRAMES} # Changed maxlen to 6
        self._confirmed_trade_zones = set()
        self._last_bar_times = {tf: None for tf in config.PATTERN_TIMEFRAMES}

        if config.PAPER_TRADE:
            self._execution_handler = PaperExecutionHandler(self._ib)
            logger.info("Paper trading mode enabled.")
        else:
            self._execution_handler = LiveExecutionHandler(self._ib)
            logger.info("Live trading mode enabled.")
        
        logger.info(f"Trade Service initialized for polling on timeframes: {config.PATTERN_TIMEFRAMES}")

    def _connect_ib(self):
        """Establishes a connection to the IB Gateway/TWS."""
        try:
            if not self._ib.isConnected():
                self._ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID + 1)
                logger.info("Trade Service connected to IB.")
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            raise

    def _process_5_candle_confirmation(self, candles: list[pd.Series], timeframe: str):
        """
        Checks for the 5-candle confirmation pattern. If DEMAND_ZONE_TRADING is true,
        it only considers patterns within an active demand zone. Otherwise, it triggers
        a trade on any valid pattern.
        """
        try:
            pattern_passed, evaluation = patterns.evaluate_5_candle_confirmation_pattern(candles)
            c5, c4, c3, c2, c1 = candles

            if not config.DEMAND_ZONE_TRADING:
                # --- PATTERN-ONLY TRADING ---
                self._log_pattern_evaluation(
                    timeframe, candles, evaluation, zone_id="N/A",
                    pattern_passed=pattern_passed, c4_in_zone=True
                )
                if pattern_passed:
                    logger.info(
                        f"\n✨✨✨✨✨✨✨✨ TRADE CONFIRMED (Pattern-Only Mode) ✨✨✨✨✨✨✨✨\n"
                        f"TRADE CONFIRMED on {timeframe}. "
                        f"Pattern: c5 bullish, c4 indecision, c3-c1 bearish mix."
                        f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                    )
                    
                    # Create a synthetic zone for stop-loss calculation
                    synthetic_zone = {
                        'id': f'pattern-trade-{int(time.time())}',
                        'zone_top': max(c['high'] for c in candles),
                        'zone_bottom': min(c['low'] for c in candles),
                        'zone_timeframe': timeframe
                    }

                    order = {
                        'price': c1['close'],
                        'zone': synthetic_zone,
                        'quantity': 1
                    }
                    self._execution_handler.execute_order(order)
                return

            # --- DEMAND ZONE TRADING (Original Logic) ---
            active_zones = self._redis_client.hgetall("active_demand_zones")
            if not active_zones:
                self._confirmed_trade_zones.clear()
                self._log_pattern_evaluation(
                    timeframe, candles, evaluation, zone_id="N/A",
                    pattern_passed=pattern_passed, c4_in_zone=None
                )
                return

            for zone_id, zone_data_str in active_zones.items():
                if zone_id in self._confirmed_trade_zones:
                    continue

                try:
                    zone_data = json.loads(zone_data_str)
                    zone_top = zone_data['zone_top']
                    zone_bottom = zone_data['zone_bottom']

                    c4_in_zone = (zone_bottom <= c4['open'] <= zone_top or
                                  zone_bottom <= c4['high'] <= zone_top or
                                  zone_bottom <= c4['low'] <= zone_top or
                                  zone_bottom <= c4['close'] <= zone_top)

                    if not c4_in_zone:
                        self._log_pattern_evaluation(
                            timeframe, candles, evaluation, zone_id=zone_id,
                            pattern_passed=pattern_passed, c4_in_zone=False
                        )
                        continue

                    self._log_pattern_evaluation(
                        timeframe, candles, evaluation, zone_id=zone_id,
                        pattern_passed=pattern_passed, c4_in_zone=True
                    )

                    if pattern_passed:
                        logger.info(
                            f"\n✨✨✨✨✨✨✨✨ TRADE CONFIRMED (5-Candle Pattern in Zone) ✨✨✨✨✨✨✨✨\n"
                            f"TRADE CONFIRMED on {timeframe}: Zone {zone_id}. "
                            f"Pattern: c5 bullish, c4 indecision, c3-c1 bearish mix."
                            f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                        )
                        self._confirmed_trade_zones.add(zone_id)

                        order = {
                            'price': c1['close'],
                            'zone': zone_data,
                            'quantity': 1
                        }
                        self._execution_handler.execute_order(order)

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode demand zone data for zone {zone_id} from Redis.")

        except (KeyError, redis.RedisError) as e:
            logger.error(f"Error processing bars in TradeService: {e}")

    def _process_v_pattern_confirmation(self, candles: list[pd.Series], timeframe: str):
        """
        Checks for the V-shaped pattern and triggers a trade if detected.
        """
        try:
            pattern_passed, evaluation = v_pattern.evaluate_v_pattern(candles)
            c6 = candles[-1] # The last candle in the 6-candle sequence

            if not config.DEMAND_ZONE_TRADING:
                # --- PATTERN-ONLY TRADING ---
                # For V-pattern, we don't have a direct zone_id or c4_in_zone concept
                # in the same way as the 5-candle pattern.
                # We'll log a simplified evaluation.
                logger.info(
                    f"[V-PatternCheck] timeframe={timeframe} end_bar={self._format_timestamp(c6.name)} "
                    f"pattern={pattern_passed} (Pattern-Only Mode)"
                )
                if pattern_passed:
                    logger.info(
                        f"\n✨✨✨✨✨✨✨✨ TRADE CONFIRMED (V-Pattern-Only Mode) ✨✨✨✨✨✨✨✨\n"
                        f"TRADE CONFIRMED on {timeframe}. "
                        f"Pattern: V-shaped bearish drop -> base -> bullish reversal."
                        f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                    )
                    
                    # Create a synthetic zone for stop-loss calculation
                    # For V-pattern, the stop loss could be below the low of the base (e.g., Low(C3) or Low(C4))
                    # For simplicity, let's use the lowest low of the 6 candles as the zone bottom for now.
                    synthetic_zone = {
                        'id': f'v-pattern-trade-{int(time.time())}',
                        'zone_top': max(c['high'] for c in candles),
                        'zone_bottom': min(c['low'] for c in candles),
                        'zone_timeframe': timeframe
                    }

                    order = {
                        'price': c6['close'], # Entry price at the close of C6
                        'zone': synthetic_zone,
                        'quantity': 1
                    }
                    self._execution_handler.execute_order(order)
                return

            # --- DEMAND ZONE TRADING (V-Pattern Logic) ---
            # This part would involve checking if the V-pattern's base or reversal candle
            # is within an active demand zone. For now, given the prompt's focus on
            # adding the new feature and the toggle switch for later, I'll keep this
            # part simple and assume V-pattern is primarily a standalone signal
            # unless explicitly configured to interact with demand zones.
            # If DEMAND_ZONE_TRADING is True, and ENABLE_V_PATTERN_STRATEGY is True,
            # we could potentially check if the base of the V-pattern is within an active zone.
            # For now, I'll treat V-pattern as a standalone signal even if DEMAND_ZONE_TRADING is True,
            # as the prompt implies a toggle for strategy selection later.
            
            # For now, if DEMAND_ZONE_TRADING is True, we will not execute V-pattern trades
            # unless it's explicitly integrated with demand zones.
            # This aligns with the "toggle switch to select strategy between two but i dont want to do it now"
            # and "integrate trade confirmation and execution logic from the pattern.py into the new function"
            # which implies the execution logic, not necessarily the demand zone interaction.
            
            logger.info(
                f"[V-PatternCheck] timeframe={timeframe} end_bar={self._format_timestamp(c6.name)} "
                f"pattern={pattern_passed} (Demand Zone Trading Mode - V-Pattern not integrated with zones yet)"
            )
            
            if pattern_passed:
                logger.info(
                    f"\n✨✨✨✨✨✨✨✨ V-PATTERN DETECTED (Demand Zone Trading Mode) ✨✨✨✨✨✨✨✨\n"
                    f"V-Pattern detected on {timeframe}, but not executing trade as it's not yet integrated with demand zones in this mode."
                    f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                )


        except Exception as e:
            logger.error(f"Error processing V-pattern in TradeService: {e}")

    def _log_pattern_evaluation(
        self,
        timeframe: str,
        candles: list[pd.Series],
        evaluation: dict,
        zone_id: str,
        pattern_passed: bool,
        c4_in_zone: bool | None
    ) -> None:
        """Outputs a structured log detailing each candle's pattern check."""
        if not candles:
            return

        try:
            latest_timestamp = candles[-1].name
            timestamp_str = self._format_timestamp(latest_timestamp)
        except Exception:
            timestamp_str = str(candles[-1].name)

        c5_status = 'PASS' if evaluation.get('c5') else 'FAIL'
        c4_status = 'PASS' if evaluation.get('c4') else 'FAIL'

        bearish_parts = []
        for item in evaluation.get('bearish', []):
            label = item.get('label', '').upper()
            if not label:
                continue
            if item.get('pass'):
                classification = item.get('classification') or 'bearish'
                bearish_parts.append(f"{label}=PASS ({classification})")
            else:
                bearish_parts.append(f"{label}=FAIL")

        bearish_summary = ', '.join(bearish_parts) if bearish_parts else 'No bearish candles evaluated'
        qualifying_status = 'PASS' if evaluation.get('qualifying_bearish') else 'FAIL'
        pattern_status = 'PASS' if pattern_passed else 'FAIL'

        if c4_in_zone is None:
            zone_touch_status = 'NO_ACTIVE_ZONE'
        else:
            zone_touch_status = 'IN_ZONE' if c4_in_zone else 'OUT_OF_ZONE'

        logger.info(
            f"[PatternCheck] timeframe={timeframe} zone={zone_id} end_bar={timestamp_str} "
            f"C5={c5_status} C4={c4_status} Bearish[{bearish_summary}] qualifying={qualifying_status} "
            f"pattern={pattern_status} c4_zone={zone_touch_status}"
        )

    @staticmethod
    def _format_timestamp(timestamp) -> str:
        """Attempts to present pandas/IB timestamps in Eastern Time."""
        try:
            if hasattr(timestamp, 'tz_convert'):
                return timestamp.tz_convert('US/Eastern').strftime('%Y-%m-%d %H:%M:%S %Z')
            if hasattr(timestamp, 'tz_localize'):
                return timestamp.tz_localize('UTC').tz_convert('US/Eastern').strftime('%Y-%m-%d %H:%M:%S %Z')
        except Exception:
            pass
        return str(timestamp)

    async def _poll_for_bars(self):
        """The main polling loop for all configured pattern timeframes."""
        while True:
            active_zone_ids = self._redis_client.hkeys("active_demand_zones")
            self._confirmed_trade_zones.intersection_update(active_zone_ids)

            for timeframe in config.PATTERN_TIMEFRAMES:
                try:
                    ibkr_tf = map_timeframe_to_ibkr(timeframe)
                    # Request more bars to ensure we have enough data for a 5-candle pattern
                    bars = self._ib.reqHistoricalData(
                        self._contract, endDateTime='', durationStr='3600 S', # Increased duration
                        barSizeSetting=ibkr_tf, whatToShow='TRADES',
                        useRTH=config.USE_RTH_ONLY, formatDate=1
                    )

                    if not bars or len(bars) < 2:
                        continue

                    latest_bar = bars[-2] # Get the last completed bar

                    if self._last_bar_times[timeframe] and latest_bar.date == self._last_bar_times[timeframe]:
                        continue

                    self._last_bar_times[timeframe] = latest_bar.date
                    bar_series = pd.Series(
                        {'open': latest_bar.open, 'high': latest_bar.high, 'low': latest_bar.low, 'close': latest_bar.close},
                        name=latest_bar.date
                    )
                    self._candles[timeframe].append(bar_series)
                    
                    # Check for 5-candle confirmation pattern
                    if len(self._candles[timeframe]) >= 5: # Use >= 5 to allow for 6 candles for V-pattern
                        candle_list_5 = list(self._candles[timeframe])[-5:] # Get last 5 candles
                        self._process_5_candle_confirmation(candle_list_5, timeframe)

                    # Check for V-pattern confirmation if enabled
                    if config.ENABLE_V_PATTERN_STRATEGY and len(self._candles[timeframe]) == 6:
                        candle_list_6 = list(self._candles[timeframe])
                        self._process_v_pattern_confirmation(candle_list_6, timeframe)

                except Exception as e:
                    logger.error(f"An error occurred in the trade service polling loop for {timeframe}: {e}", exc_info=True)
            
            await asyncio.sleep(config.POLL_INTERVAL_SECONDS)

    def run(self):
        """Starts the main data collection and pattern detection loop."""
        self._connect_ib()
        
        try:
            import nest_asyncio
            nest_asyncio.apply()
            self._ib.run(self._poll_for_bars())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Trade Service shutting down.")
        finally:
            if self._ib.isConnected():
                self._ib.disconnect()
            logger.info("Trade Service disconnected from IB.")

def start_trade_service():
    """Entry point for the trade service process."""
    logger = setup_logger("TradeService", level=logging.DEBUG)
    service = TradeService()
    service.run()
