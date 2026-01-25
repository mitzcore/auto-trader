import logging
import json
import redis
import pandas as pd
from ib_insync import IB, Stock
import time
import datetime
import pytz

import config
from algotrade import patterns
from algotrade.patterns import PATTERN_REGISTRY, evaluate_3_candle_pattern
from algotrade.util import map_timeframe_to_ibkr
from algotrade.logger import setup_logger
from algotrade.database import log_trade_confirmation
from algotrade.execution import LiveExecutionHandler, PaperExecutionHandler, ManualOCOManager

# TradeStation imports (conditional to avoid errors if not using TradeStation)
if config.EXECUTION_BROKER == "tradestation":
    from algotrade.tradestation_execution import TradeStationExecutionHandler, TradeStationPaperHandler

logger = setup_logger(__name__)
_PATTERN_LOG_LEVEL = getattr(logging, config.PATTERN_LOG_LEVEL.upper(), logging.INFO)

# Setup patterns module logger with same handlers as trade_service
patterns_logger = setup_logger('algotrade.patterns', level=_PATTERN_LOG_LEVEL)

class TradeService:
    """
    Monitors for price entry into demand zones and confirms trades by polling
    for completed bars across multiple timeframes and checking for two-candlestick patterns.
    """

    def __init__(self):
        self._ib = IB()
        self._redis_client = redis.Redis(decode_responses=True)
        self._contract = Stock(config.SYMBOL, config.EXCHANGE, config.CURRENCY)

        # Track last processed bar to avoid duplicate processing
        self._confirmed_trade_zones = set()
        self._last_bar_times = {tf: None for tf in config.PATTERN_TIMEFRAMES}

        # Determine which patterns to run
        if config.PATTERN_MODE == "both":
            self._active_patterns = ["6_candle", "3_candle"]
        else:
            self._active_patterns = [config.PATTERN_MODE]

        # Signal reset tracking - per pattern per timeframe (only 6_candle uses this)
        # Format: {("6_candle", "2m"): False, ("6_candle", "3m"): False, ...}
        self._waiting_for_reset = {}
        self._bearish_count = {}
        for pattern in self._active_patterns:
            for tf in config.PATTERN_TIMEFRAMES:
                self._waiting_for_reset[(pattern, tf)] = False
                self._bearish_count[(pattern, tf)] = 0

        # Prevent duplicate trades when multiple patterns pass on same bar
        # Format: {"2m": "2025-12-29 10:30:00", ...} - last traded bar per timeframe
        self._last_trade_bar = {tf: None for tf in config.PATTERN_TIMEFRAMES}

        # OCO Manager for IB live trading (manages stop orders + streaming take profit)
        self._oco_manager = None

        # Select execution handler based on configured broker
        if config.EXECUTION_BROKER == "tradestation":
            self._init_tradestation_handler()
        else:
            self._init_ib_handler()

        patterns_str = " + ".join(self._active_patterns)
        logger.info(f"Trade Service initialized | Patterns: {patterns_str} | Timeframes: {config.PATTERN_TIMEFRAMES}")

    def _init_ib_handler(self):
        """Initialize Interactive Brokers execution handler."""
        if config.PAPER_TRADE:
            self._execution_handler = PaperExecutionHandler(self._ib)
            logger.info("IB Paper trading mode enabled.")
        else:
            self._oco_manager = ManualOCOManager(self._ib)
            self._execution_handler = LiveExecutionHandler(self._ib, self._oco_manager)
            logger.info("IB Live trading mode enabled with ManualOCOManager.")

    def _init_tradestation_handler(self):
        """Initialize TradeStation execution handler."""
        if config.PAPER_TRADE:
            self._execution_handler = TradeStationPaperHandler()
            logger.info("TradeStation Paper trading mode enabled (sim environment).")
        else:
            self._execution_handler = TradeStationExecutionHandler()
            logger.info("TradeStation Live trading mode enabled with native OCO.")

        # Connect TradeStation handler
        if not self._execution_handler.connect():
            logger.error("Failed to connect TradeStation handler!")
            raise ConnectionError("TradeStation authentication failed")

    def _connect_ib(self):
        """Establishes a connection to the IB Gateway/TWS."""
        try:
            if not self._ib.isConnected():
                self._ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID + 1)
                logger.info("Trade Service connected to IB.")
        except Exception as e:
            logger.error(f"Failed to connect to IB: {e}")
            raise

    def _process_6_candle_confirmation(self, candles: list[pd.Series], timeframe: str):
        """
        Checks for the 6-candle confirmation pattern. If DEMAND_ZONE_TRADING is true,
        it only considers patterns within an active demand zone. Otherwise, it triggers
        a trade on any valid pattern.

        Pattern: C1-C4 bearish pullback, C5 indecision, C6 strong bullish entry.
        """
        try:
            pattern_passed, evaluation = patterns.evaluate_6_candle_confirmation_pattern(candles)
            # Candles ordered oldest to newest - use last 6 for key positions
            # With variable lookback, we reference from the end: trigger=[-1], base=[-2,-3]
            c6 = candles[-1]  # Trigger candle (newest)
            c5 = candles[-2]  # Base candle 2 (indecision)
            c5_patterns = evaluation.get('c5_pattern', [])
            c5_pattern_str = ','.join(c5_patterns) if c5_patterns else 'indecision'

            if not config.DEMAND_ZONE_TRADING:
                # --- PATTERN-ONLY TRADING ---
                self._log_6_candle_evaluation(
                    timeframe, candles, evaluation, zone_id="N/A",
                    pattern_passed=pattern_passed, c5_in_zone=True
                )
                if pattern_passed:
                    # Set signal triggered flag (wait for reset before next signal)
                    self._waiting_for_reset[("6_candle", timeframe)] = True
                    self._bearish_count[("6_candle", timeframe)] = 0

                    # Capture alert timestamp when pattern is confirmed
                    alert_timestamp = datetime.datetime.now(pytz.utc)

                    # Smart reversal metrics for confirmation log
                    drop_pct = evaluation.get('drop_pct', 0) * 100
                    reclaim_pct = evaluation.get('reclaim_pct', 0) * 100
                    exhaustion_type = evaluation.get('exhaustion_type', 'base')

                    logger.info(
                        f"\n✨✨✨✨✨✨✨✨ SMART REVERSAL CONFIRMED ✨✨✨✨✨✨✨✨\n"
                        f"TRADE CONFIRMED on {timeframe}. "
                        f"Drop: {drop_pct:.2f}% | Reclaim: {reclaim_pct:.1f}% | Base: {exhaustion_type}"
                        f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                    )

                    # Create a synthetic zone for stop-loss calculation
                    synthetic_zone = {
                        'id': f'pattern-trade-{int(time.time())}',
                        'zone_top': max(c['high'] for c in candles),
                        'zone_bottom': min(c['low'] for c in candles),
                        'zone_timeframe': timeframe
                    }

                    # Get swing high/low from evaluation (Smart Reversal metrics)
                    swing_high = evaluation.get('swing_high', 0)
                    swing_low = evaluation.get('drop_low', 0)  # drop_low is the swing low

                    order = {
                        'price': c6['close'],  # Entry at C6 (newest bullish candle)
                        'zone': synthetic_zone,
                        'quantity': 1,
                        'pattern_type': 'SM',  # Smart Reversal
                        'timeframe': timeframe,  # For swing low calculation
                        # Smart Reversal metrics for trade journaling
                        'drop_pct': drop_pct,      # Already converted to percentage (e.g., 0.25)
                        'reclaim_pct': reclaim_pct,  # Already converted to percentage (e.g., 35.0)
                        'swing_high': swing_high,
                        'swing_low': swing_low,
                    }

                    # Route to test mode or normal execution
                    if getattr(config, 'STRIKE_TEST_MODE', False):
                        self._execution_handler.execute_test_orders(order, alert_timestamp=alert_timestamp)
                    else:
                        self._execution_handler.execute_order(order, alert_timestamp=alert_timestamp)

                    # Mark trade executed on this bar (prevent duplicate from other patterns)
                    self._last_trade_bar[timeframe] = str(candles[-1].name)
                return

            # --- DEMAND ZONE TRADING ---
            active_zones = self._redis_client.hgetall("active_demand_zones")
            if not active_zones:
                self._confirmed_trade_zones.clear()
                self._log_6_candle_evaluation(
                    timeframe, candles, evaluation, zone_id="N/A",
                    pattern_passed=pattern_passed, c5_in_zone=None
                )
                return

            # Check if C5 (indecision candle) touches the zone
            for zone_id, zone_data_str in active_zones.items():
                if zone_id in self._confirmed_trade_zones:
                    continue

                try:
                    zone_data = json.loads(zone_data_str)
                    zone_top = zone_data['zone_top']
                    zone_bottom = zone_data['zone_bottom']

                    # Check if C5 (indecision) touches the zone
                    c5_in_zone = (zone_bottom <= c5['open'] <= zone_top or
                                  zone_bottom <= c5['high'] <= zone_top or
                                  zone_bottom <= c5['low'] <= zone_top or
                                  zone_bottom <= c5['close'] <= zone_top)

                    if not c5_in_zone:
                        self._log_6_candle_evaluation(
                            timeframe, candles, evaluation, zone_id=zone_id,
                            pattern_passed=pattern_passed, c5_in_zone=False
                        )
                        continue

                    self._log_6_candle_evaluation(
                        timeframe, candles, evaluation, zone_id=zone_id,
                        pattern_passed=pattern_passed, c5_in_zone=True
                    )

                    if pattern_passed:
                        # Set signal triggered flag (wait for reset before next signal)
                        self._waiting_for_reset[("6_candle", timeframe)] = True
                        self._bearish_count[("6_candle", timeframe)] = 0

                        # Capture alert timestamp when pattern is confirmed
                        alert_timestamp = datetime.datetime.now(pytz.utc)

                        # Smart reversal metrics for confirmation log
                        drop_pct = evaluation.get('drop_pct', 0) * 100
                        reclaim_pct = evaluation.get('reclaim_pct', 0) * 100
                        exhaustion_type = evaluation.get('exhaustion_type', 'base')

                        logger.info(
                            f"\n✨✨✨✨✨✨✨✨ SMART REVERSAL CONFIRMED (Zone) ✨✨✨✨✨✨✨✨\n"
                            f"TRADE CONFIRMED on {timeframe}: Zone {zone_id}. "
                            f"Drop: {drop_pct:.2f}% | Reclaim: {reclaim_pct:.1f}% | Base: {exhaustion_type}"
                            f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                        )
                        self._confirmed_trade_zones.add(zone_id)

                        # Get swing high/low from evaluation (Smart Reversal metrics)
                        swing_high = evaluation.get('swing_high', 0)
                        swing_low = evaluation.get('drop_low', 0)  # drop_low is the swing low

                        order = {
                            'price': c6['close'],  # Entry at C6 (newest bullish candle)
                            'zone': zone_data,
                            'quantity': 1,
                            'pattern_type': 'SM',  # Smart Reversal
                            'timeframe': timeframe,  # For swing low calculation
                            # Smart Reversal metrics for trade journaling
                            'drop_pct': drop_pct,      # Already converted to percentage (e.g., 0.25)
                            'reclaim_pct': reclaim_pct,  # Already converted to percentage (e.g., 35.0)
                            'swing_high': swing_high,
                            'swing_low': swing_low,
                        }

                        # Route to test mode or normal execution
                        if getattr(config, 'STRIKE_TEST_MODE', False):
                            self._execution_handler.execute_test_orders(order, alert_timestamp=alert_timestamp)
                        else:
                            self._execution_handler.execute_order(order, alert_timestamp=alert_timestamp)

                        # Mark trade executed on this bar (prevent duplicate from other patterns)
                        self._last_trade_bar[timeframe] = str(candles[-1].name)

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode demand zone data for zone {zone_id} from Redis.")

        except (KeyError, redis.RedisError) as e:
            logger.error(f"Error processing 6-candle pattern: {e}")

    def _log_3_candle_evaluation(
        self,
        timeframe: str,
        candles: list[pd.Series],
        evaluation: dict,
        zone_id: str,
        pattern_passed: bool,
        c2_in_zone: bool | None
    ) -> None:
        """Outputs a structured log for 3-candle pattern evaluation."""
        if not candles:
            return

        try:
            latest_timestamp = candles[-1].name
            timestamp_str = self._format_timestamp(latest_timestamp)
        except Exception:
            timestamp_str = str(candles[-1].name)

        c3_status = 'PASS' if evaluation.get('c3') else 'FAIL'
        c2_status = 'PASS' if evaluation.get('c2') else 'FAIL'
        c1_status = 'PASS' if evaluation.get('c1') else 'FAIL'

        c2_patterns = evaluation.get('c2_pattern')
        c2_pattern_str = ','.join(c2_patterns) if c2_patterns else 'None'

        pattern_status = 'PASS' if pattern_passed else 'FAIL'

        if c2_in_zone is None:
            zone_touch_status = 'NO_ZONE'
        else:
            zone_touch_status = 'IN_ZONE' if c2_in_zone else 'OUT'

        logger.info(
            f"[3CandleCheck] tf={timeframe} zone={zone_id} bar={timestamp_str} "
            f"C3={c3_status} C2={c2_status}[{c2_pattern_str}] C1={c1_status} "
            f"result={pattern_status} zone_touch={zone_touch_status}"
        )

    def _log_6_candle_evaluation(
        self,
        timeframe: str,
        candles: list[pd.Series],
        evaluation: dict,
        zone_id: str,
        pattern_passed: bool,
        c5_in_zone: bool | None
    ) -> None:
        """Outputs a structured log for Smart Reversal (6-candle) pattern evaluation."""
        if not candles:
            return

        try:
            latest_timestamp = candles[-1].name
            timestamp_str = self._format_timestamp(latest_timestamp)
        except Exception:
            timestamp_str = str(candles[-1].name)

        # Smart Reversal metrics
        trigger_status = 'PASS' if evaluation.get('trigger_valid') else 'FAIL'
        trigger_body = evaluation.get('trigger_body_pct', 0)

        drop_status = 'PASS' if evaluation.get('drop_sufficient') else 'FAIL'
        drop_pct = evaluation.get('drop_pct', 0) * 100  # Convert to percentage
        drop_dollars = evaluation.get('drop_dollars', 0)

        # Continuous drop check (no sideways/accumulation)
        continuous_ok = evaluation.get('drop_continuous', False)
        continuous_reason = evaluation.get('drop_continuous_reason', 'N/A')
        if continuous_reason == 'disabled':
            continuous_status = 'N/A'
        else:
            continuous_status = f"PASS[{continuous_reason}]" if continuous_ok else f"FAIL[{continuous_reason}]"

        # Fresh drop check (V-shape vs flat zone)
        drop_fresh = evaluation.get('drop_fresh', False)
        drop_low_age = evaluation.get('drop_low_age', 0)
        max_drop_age = getattr(config, 'SMART_REVERSAL_MAX_DROP_AGE', 4)
        if not getattr(config, 'SMART_REVERSAL_REQUIRE_FRESH_DROP', True):
            fresh_status = 'N/A'
        else:
            fresh_status = f"PASS[age={drop_low_age}]" if drop_fresh else f"FAIL[age={drop_low_age}>{max_drop_age}]"

        exhaustion_status = 'PASS' if evaluation.get('exhaustion_detected') else 'FAIL'
        exhaustion_type = evaluation.get('exhaustion_type') or 'none'

        reclaim_status = 'PASS' if evaluation.get('reclaim_valid') else 'FAIL'
        reclaim_pct = evaluation.get('reclaim_pct', 0) * 100  # Convert to percentage

        # Base break: show N/A when not required by config
        if config.SMART_REVERSAL_REQUIRE_BASE_BREAK:
            base_break_status = 'PASS' if evaluation.get('base_break') else 'FAIL'
        else:
            base_break_status = 'N/A'

        pattern_status = 'PASS' if pattern_passed else 'FAIL'

        if c5_in_zone is None:
            zone_touch_status = 'NO_ZONE'
        else:
            zone_touch_status = 'IN_ZONE' if c5_in_zone else 'OUT'

        # DEBUG: Log lookback candle details to diagnose swing high issues
        lookback_debug = evaluation.get('lookback_debug', [])
        if lookback_debug and len(lookback_debug) > 0:
            logger.debug(f"[SmartReversal:DEBUG] Lookback candles: {', '.join(lookback_debug[:5])}...")

        # Smart reversal log format
        logger.info(
            f"[SmartReversal] tf={timeframe} zone={zone_id} bar={timestamp_str} "
            f"TRIGGER={trigger_status}({trigger_body:.0%}) "
            f"DROP={drop_status}({drop_pct:.2f}%/${drop_dollars:.2f}) "
            f"CONTINUOUS={continuous_status} FRESH={fresh_status} "
            f"EXHAUST={exhaustion_status}[{exhaustion_type}] "
            f"RECLAIM={reclaim_status}({reclaim_pct:.1f}%) "
            f"BASE_BREAK={base_break_status} "
            f"result={pattern_status} zone={zone_touch_status}"
        )

        # DEBUG: Log lookback candle details when DROP fails (to diagnose data issues)
        if drop_status == 'FAIL' and trigger_status == 'PASS':
            lookback_debug = evaluation.get('lookback_debug', [])
            swing_high = evaluation.get('swing_high', 0)
            drop_low = evaluation.get('drop_low', 0)
            logger.info(
                f"[SmartReversal LOOKBACK] swing_high={swing_high} drop_low={drop_low}"
            )
            # Log each bar's timestamp and high/low
            for bar_info in lookback_debug:
                logger.info(f"  {bar_info}")

    def _process_3_candle_confirmation(self, candles: list[pd.Series], timeframe: str):
        """
        Checks for the 3-candle confirmation pattern.
        Pattern: C1 (strong bearish) -> C2 (indecision) -> C3 (strong bullish entry)

        If DEMAND_ZONE_TRADING is true, only considers patterns within an active demand zone.
        Otherwise, triggers a trade on any valid pattern.
        """
        try:
            pattern_passed, evaluation = evaluate_3_candle_pattern(candles)
            c1, c2, c3 = candles
            c2_patterns = evaluation.get('c2_pattern', [])
            c2_pattern_str = ','.join(c2_patterns) if c2_patterns else 'indecision'

            if not config.DEMAND_ZONE_TRADING:
                # --- PATTERN-ONLY TRADING ---
                self._log_3_candle_evaluation(
                    timeframe, candles, evaluation, zone_id="N/A",
                    pattern_passed=pattern_passed, c2_in_zone=True
                )
                if pattern_passed:
                    alert_timestamp = datetime.datetime.now(pytz.utc)
                    logger.info(
                        f"\n✨✨✨✨✨✨✨✨ TRADE CONFIRMED (3-Candle Pattern-Only) ✨✨✨✨✨✨✨✨\n"
                        f"TRADE CONFIRMED on {timeframe}. "
                        f"Pattern: C1=strong bearish, C2={c2_pattern_str}, C3=strong bullish entry."
                        f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                    )

                    synthetic_zone = {
                        'id': f'pattern-trade-{int(time.time())}',
                        'zone_top': max(c['high'] for c in candles),
                        'zone_bottom': min(c['low'] for c in candles),
                        'zone_timeframe': timeframe
                    }

                    # Calculate swing high/low from the 3 candles
                    swing_high = max(c['high'] for c in candles)
                    swing_low = min(c['low'] for c in candles)

                    order = {
                        'price': c3['close'],
                        'zone': synthetic_zone,
                        'quantity': 1,
                        'pattern_type': '3C',  # 3-Candle Pattern
                        'timeframe': timeframe,  # For swing low calculation
                        # 3-candle doesn't have drop/reclaim metrics, but include swing levels
                        'drop_pct': None,
                        'reclaim_pct': None,
                        'swing_high': swing_high,
                        'swing_low': swing_low,
                    }

                    # Route to test mode or normal execution
                    if getattr(config, 'STRIKE_TEST_MODE', False):
                        self._execution_handler.execute_test_orders(order, alert_timestamp=alert_timestamp)
                    else:
                        self._execution_handler.execute_order(order, alert_timestamp=alert_timestamp)

                    # Mark trade executed on this bar (prevent duplicate from other patterns)
                    self._last_trade_bar[timeframe] = str(candles[-1].name)
                return

            # --- DEMAND ZONE TRADING ---
            active_zones = self._redis_client.hgetall("active_demand_zones")
            if not active_zones:
                self._confirmed_trade_zones.clear()
                self._log_3_candle_evaluation(
                    timeframe, candles, evaluation, zone_id="N/A",
                    pattern_passed=pattern_passed, c2_in_zone=None
                )
                return

            for zone_id, zone_data_str in active_zones.items():
                if zone_id in self._confirmed_trade_zones:
                    continue

                try:
                    zone_data = json.loads(zone_data_str)
                    zone_top = zone_data['zone_top']
                    zone_bottom = zone_data['zone_bottom']

                    # Check if C2 (indecision) touches the zone
                    c2_in_zone = (zone_bottom <= c2['open'] <= zone_top or
                                  zone_bottom <= c2['high'] <= zone_top or
                                  zone_bottom <= c2['low'] <= zone_top or
                                  zone_bottom <= c2['close'] <= zone_top)

                    if not c2_in_zone:
                        self._log_3_candle_evaluation(
                            timeframe, candles, evaluation, zone_id=zone_id,
                            pattern_passed=pattern_passed, c2_in_zone=False
                        )
                        continue

                    self._log_3_candle_evaluation(
                        timeframe, candles, evaluation, zone_id=zone_id,
                        pattern_passed=pattern_passed, c2_in_zone=True
                    )

                    if pattern_passed:
                        alert_timestamp = datetime.datetime.now(pytz.utc)
                        logger.info(
                            f"\n✨✨✨✨✨✨✨✨ TRADE CONFIRMED (3-Candle in Zone) ✨✨✨✨✨✨✨✨\n"
                            f"TRADE CONFIRMED on {timeframe}: Zone {zone_id}. "
                            f"Pattern: C1=strong bearish, C2={c2_pattern_str}, C3=strong bullish entry."
                            f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                        )
                        self._confirmed_trade_zones.add(zone_id)

                        # Calculate swing high/low from the 3 candles
                        swing_high = max(c['high'] for c in candles)
                        swing_low = min(c['low'] for c in candles)

                        order = {
                            'price': c3['close'],
                            'zone': zone_data,
                            'quantity': 1,
                            'pattern_type': '3C',  # 3-Candle Pattern
                            'timeframe': timeframe,  # For swing low calculation
                            # 3-candle doesn't have drop/reclaim metrics, but include swing levels
                            'drop_pct': None,
                            'reclaim_pct': None,
                            'swing_high': swing_high,
                            'swing_low': swing_low,
                        }

                        # Route to test mode or normal execution
                        if getattr(config, 'STRIKE_TEST_MODE', False):
                            self._execution_handler.execute_test_orders(order, alert_timestamp=alert_timestamp)
                        else:
                            self._execution_handler.execute_order(order, alert_timestamp=alert_timestamp)

                        # Mark trade executed on this bar (prevent duplicate from other patterns)
                        self._last_trade_bar[timeframe] = str(candles[-1].name)

                except json.JSONDecodeError:
                    logger.error(f"Failed to decode demand zone data for zone {zone_id} from Redis.")

        except (KeyError, redis.RedisError) as e:
            logger.error(f"Error processing 3-candle pattern: {e}")

    def _log_pattern_evaluation(
        self,
        timeframe: str,
        candles: list[pd.Series],
        evaluation: dict,
        zone_id: str,
        pattern_passed: bool,
        c4_in_zone: bool | None
    ) -> None:
        """Outputs a structured log detailing each candle's pattern check (5-candle legacy)."""
        if not candles:
            return

        try:
            latest_timestamp = candles[-1].name
            timestamp_str = self._format_timestamp(latest_timestamp)
        except Exception:
            timestamp_str = str(candles[-1].name)

        c5_status = 'PASS' if evaluation.get('c5') else 'FAIL'
        c4_status = 'PASS' if evaluation.get('c4') else 'FAIL'

        # Get which indecision pattern(s) matched for C4
        c4_patterns = evaluation.get('c4_pattern')
        c4_pattern_str = ','.join(c4_patterns) if c4_patterns else 'None'

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

        # Get bearish counts for detailed logging
        bearish_count = evaluation.get('bearish_count', 0)
        strong_bearish_count = evaluation.get('strong_bearish_count', 0)
        qualifying_status = 'PASS' if evaluation.get('qualifying_bearish') else f'FAIL(need 2 bearish w/ 1 strong, got {bearish_count} bearish, {strong_bearish_count} strong)'
        pattern_status = 'PASS' if pattern_passed else 'FAIL'

        if c4_in_zone is None:
            zone_touch_status = 'NO_ACTIVE_ZONE'
        else:
            zone_touch_status = 'IN_ZONE' if c4_in_zone else 'OUT_OF_ZONE'

        # Build OHLC summary for debugging (oldest to newest: c1 -> c5)
        candle_values = evaluation.get('candle_values', {})
        ohlc_parts = []
        for label in ['c1', 'c2', 'c3', 'c4', 'c5']:
            cv = candle_values.get(label, {})
            if cv:
                ohlc_parts.append(f"{label.upper()}(O:{cv.get('open')} H:{cv.get('high')} L:{cv.get('low')} C:{cv.get('close')})")

        ohlc_summary = ' | '.join(ohlc_parts) if ohlc_parts else 'N/A'

        logger.info(
            f"[PatternCheck] timeframe={timeframe} zone={zone_id} end_bar={timestamp_str} "
            f"C5={c5_status} C4={c4_status}[{c4_pattern_str}] Bearish[{bearish_summary}] qualifying={qualifying_status} "
            f"pattern={pattern_status} c4_zone={zone_touch_status}"
        )
        # Log OHLC values on a separate line for readability
        logger.info(f"[PatternOHLC] {ohlc_summary}")

    def _log_pattern_ingest(
        self,
        timeframe: str,
        candle: pd.Series,
        depth: int,
    ) -> None:
        """Logs each OHLC bar as it arrives for pattern processing."""
        timestamp = self._format_timestamp(candle.name)
        logger.log(
            _PATTERN_LOG_LEVEL,
            (
                f"[PatternIngest] timeframe={timeframe} end_bar={timestamp} "
                f"O:{candle['open']:.2f} H:{candle['high']:.2f} "
                f"L:{candle['low']:.2f} C:{candle['close']:.2f} depth={depth}"
            ),
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

    @staticmethod
    def _parse_timeframe_minutes(timeframe: str) -> int:
        """Extract minutes from timeframe string like '2m', '3m', '5m'."""
        value_str = ''.join(filter(str.isdigit, timeframe))
        if not value_str:
            return 1
        return int(value_str)

    def _get_next_candle_boundary(self, timeframe: str) -> datetime.datetime:
        """
        Calculate the exact datetime when the next candle closes for a given timeframe.

        For a 2m candle, boundaries are at :00, :02, :04, :06, etc.
        For a 3m candle, boundaries are at :00, :03, :06, :09, etc.

        Returns the next boundary time plus the configured buffer.
        """
        minutes = self._parse_timeframe_minutes(timeframe)
        now = datetime.datetime.now()

        # Calculate current position within the candle period
        minutes_since_hour = now.minute
        minutes_into_candle = minutes_since_hour % minutes

        # Calculate minutes until next boundary
        if minutes_into_candle == 0 and now.second < config.CANDLE_BOUNDARY_BUFFER_SECONDS:
            # We're right at the boundary, within buffer - this is the one we want
            minutes_until_boundary = 0
        else:
            minutes_until_boundary = minutes - minutes_into_candle

        # Build the next boundary time
        next_boundary = now.replace(second=0, microsecond=0) + datetime.timedelta(minutes=minutes_until_boundary)

        # Add buffer to ensure IB has the data ready
        next_fetch_time = next_boundary + datetime.timedelta(seconds=config.CANDLE_BOUNDARY_BUFFER_SECONDS)

        return next_fetch_time

    def _seconds_until(self, target_time: datetime.datetime) -> float:
        """Calculate seconds from now until target time."""
        now = datetime.datetime.now()
        delta = (target_time - now).total_seconds()
        return max(0, delta)

    def _fetch_and_process_timeframe(self, timeframe: str):
        """
        Fetch historical bars and process for pattern detection.
        Uses FRESH historical data every cycle - same approach as backtest.

        Supports running multiple patterns in parallel (when PATTERN_MODE="both").
        Each pattern runs independently with its own signal reset tracking.
        """
        try:
            # Calculate max candle count needed from all active patterns
            max_candle_count = max(
                PATTERN_REGISTRY[p]["candle_count"] for p in self._active_patterns
            )

            ibkr_tf = map_timeframe_to_ibkr(timeframe)

            # Calculate duration needed for max candle count + buffer
            tf_minutes = int(timeframe.replace('m', ''))
            duration_seconds = (max_candle_count + 5) * tf_minutes * 60

            # Fetch fresh historical bars - EXACTLY like backtest does
            bars = self._ib.reqHistoricalData(
                self._contract,
                endDateTime='',
                durationStr=f'{duration_seconds} S',
                barSizeSetting=ibkr_tf,
                whatToShow='TRADES',
                useRTH=config.USE_RTH_ONLY,
                formatDate=1
            )

            if not bars:
                logger.warning(f"[{timeframe}] No bars returned from IB")
                return

            # Check if we have a new bar to process
            latest_bar = bars[-1]
            new_bar_available = (
                not self._last_bar_times[timeframe]
                or latest_bar.date != self._last_bar_times[timeframe]
            )

            fetch_time = datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
            poll_timestamp = self._format_timestamp(latest_bar.date)

            if not new_bar_available:
                logger.debug(f"[{timeframe}] No new bar - already processed {poll_timestamp}")
                return

            self._last_bar_times[timeframe] = latest_bar.date

            # Convert ALL bars to pd.Series - EXACTLY like backtest
            all_bars_series = []
            for bar in bars:
                bar_series = pd.Series(
                    {'open': bar.open, 'high': bar.high, 'low': bar.low, 'close': bar.close},
                    name=bar.date
                )
                all_bars_series.append(bar_series)

            # DEBUG: Log first and last few bars to verify data integrity
            if len(all_bars_series) >= 3:
                logger.debug(f"[CandleDebug:{timeframe}] First 3 bars: " +
                           f"{all_bars_series[0].name}:H{all_bars_series[0]['high']:.2f}/L{all_bars_series[0]['low']:.2f}, " +
                           f"{all_bars_series[1].name}:H{all_bars_series[1]['high']:.2f}/L{all_bars_series[1]['low']:.2f}, " +
                           f"{all_bars_series[2].name}:H{all_bars_series[2]['high']:.2f}/L{all_bars_series[2]['low']:.2f}")
                logger.debug(f"[CandleDebug:{timeframe}] Last 3 bars: " +
                           f"{all_bars_series[-3].name}:H{all_bars_series[-3]['high']:.2f}/L{all_bars_series[-3]['low']:.2f}, " +
                           f"{all_bars_series[-2].name}:H{all_bars_series[-2]['high']:.2f}/L{all_bars_series[-2]['low']:.2f}, " +
                           f"{all_bars_series[-1].name}:H{all_bars_series[-1]['high']:.2f}/L{all_bars_series[-1]['low']:.2f}")

            # Log the fetch with range info
            first_bar = bars[0] if bars else None
            logger.info(
                f"[CandleFetch] timeframe={timeframe} fetched_at={fetch_time} "
                f"candle_end={poll_timestamp} bars={len(bars)} "
                f"range={self._format_timestamp(first_bar.date) if first_bar else 'N/A'}→{poll_timestamp}"
            )

            # Log latest candle OHLC
            self._log_pattern_ingest(timeframe, all_bars_series[-1], len(all_bars_series))

            # Process each active pattern independently
            for pattern_name in self._active_patterns:
                self._process_pattern(pattern_name, timeframe, all_bars_series, latest_bar)

        except Exception as e:
            logger.error(f"Error fetching/processing {timeframe}: {e}", exc_info=True)

    def _process_pattern(self, pattern_name: str, timeframe: str, all_bars: list, latest_bar):
        """
        Process a single pattern with its own signal reset tracking.
        Called for each active pattern (enables parallel pattern execution).

        Includes duplicate trade prevention - if another pattern already triggered
        a trade on this bar, skip processing.
        """
        # Check if trade already executed on this bar (prevent duplicates)
        current_bar_time = str(latest_bar.date)
        if self._last_trade_bar.get(timeframe) == current_bar_time:
            logger.debug(f"[{pattern_name}:{timeframe}] Skipping - trade already executed on this bar")
            return

        pattern_config = PATTERN_REGISTRY.get(pattern_name)
        if not pattern_config:
            return

        candle_count = pattern_config["candle_count"]
        reset_key = (pattern_name, timeframe)

        # DEBUG: Log candle count being used
        logger.debug(f"[Pattern:{pattern_name}:{timeframe}] candle_count={candle_count}, all_bars={len(all_bars)}")

        # Check for signal reset condition (6_candle / Smart Reversal only)
        if pattern_name == "6_candle" and self._waiting_for_reset.get(reset_key, False):
            if config.SMART_REVERSAL_REQUIRE_RESET:
                if latest_bar.close < latest_bar.open:
                    self._bearish_count[reset_key] = self._bearish_count.get(reset_key, 0) + 1
                    logger.debug(
                        f"[{pattern_name}:{timeframe}] Bearish candle "
                        f"{self._bearish_count[reset_key]}/{config.SMART_REVERSAL_RESET_CANDLES}"
                    )
                    if self._bearish_count[reset_key] >= config.SMART_REVERSAL_RESET_CANDLES:
                        self._waiting_for_reset[reset_key] = False
                        self._bearish_count[reset_key] = 0
                        logger.debug(f"[{pattern_name}:{timeframe}] Signal reset complete")

        # Skip pattern check if waiting for reset (6_candle only)
        if pattern_name == "6_candle" and self._waiting_for_reset.get(reset_key, False):
            if config.SMART_REVERSAL_REQUIRE_RESET:
                logger.debug(f"[{pattern_name}:{timeframe}] Skipping - waiting for reset")
                return

        # Get the candles needed for this pattern
        if len(all_bars) >= candle_count:
            candle_list = all_bars[-candle_count:]

            # Route to appropriate handler
            if pattern_name == "6_candle":
                self._process_6_candle_confirmation(candle_list, timeframe)
            elif pattern_name == "3_candle":
                self._process_3_candle_confirmation(candle_list, timeframe)
        else:
            logger.warning(f"[{pattern_name}:{timeframe}] Not enough bars: {len(all_bars)}/{candle_count}")

    def _has_active_trade(self) -> bool:
        """
        Check if there is an active trade being managed.

        When a trade is active, the program should focus on trade management
        (monitoring SPY price and option price) instead of pattern checking.
        """
        # Check TradeStation handler
        if hasattr(self._execution_handler, 'has_active_trades'):
            return self._execution_handler.has_active_trades()

        # Check IB OCO manager
        if self._oco_manager and hasattr(self._oco_manager, 'has_active_trades'):
            return self._oco_manager.has_active_trades()

        return False

    def _poll_for_bars(self):
        """
        Main polling loop synchronized to candle boundaries.

        Instead of polling at fixed intervals, this calculates when each timeframe's
        candle closes and fetches data right after that moment. This ensures:
        1. OHLC data is complete and accurate
        2. Pattern detection happens immediately after candle close
        3. Minimal latency between candle close and trade signal

        CRITICAL: When a trade is active, this loop pauses pattern checking and
        candle fetching to focus on trade management. This prevents hitting
        IB market data limits.

        Uses ib.sleep() to allow IB events to be processed between fetches.
        """
        # Initialize next fetch times for each timeframe
        next_fetch_times = {tf: self._get_next_candle_boundary(tf) for tf in config.PATTERN_TIMEFRAMES}

        logger.info(f"[CandleSync] Initialized candle boundary tracking:")
        for tf, fetch_time in next_fetch_times.items():
            logger.info(f"  {tf}: next fetch at {fetch_time.strftime('%H:%M:%S')}")

        # Track trade management mode state for logging
        was_in_trade_management = False

        while True:
            # Check if we have an active trade being managed
            in_trade_management = self._has_active_trade()

            # Log state transitions
            if in_trade_management and not was_in_trade_management:
                logger.critical(
                    "[TradeMode] 🔒 ENTERING TRADE MANAGEMENT MODE | "
                    "Pausing pattern detection to focus on active trade"
                )
                was_in_trade_management = True
            elif not in_trade_management and was_in_trade_management:
                logger.critical(
                    "[TradeMode] 🔓 EXITING TRADE MANAGEMENT MODE | "
                    "Resuming pattern detection"
                )
                was_in_trade_management = False
                # Reset next fetch times to start checking immediately
                next_fetch_times = {tf: self._get_next_candle_boundary(tf) for tf in config.PATTERN_TIMEFRAMES}

            # Only do pattern checking when NOT in trade management mode
            if not in_trade_management:
                # Update active zones
                active_zone_ids = self._redis_client.hkeys("active_demand_zones")
                self._confirmed_trade_zones.intersection_update(active_zone_ids)

                # Find the earliest next fetch time across all timeframes
                now = datetime.datetime.now()
                ready_timeframes = [tf for tf, fetch_time in next_fetch_times.items() if fetch_time <= now]

                if ready_timeframes:
                    # Process all timeframes that are ready
                    for timeframe in ready_timeframes:
                        logger.info(
                            f"[CandleSync] {timeframe} candle boundary reached at "
                            f"{now.strftime('%H:%M:%S.%f')[:-3]}"
                        )
                        self._fetch_and_process_timeframe(timeframe)

                        # Schedule next fetch for this timeframe
                        next_fetch_times[timeframe] = self._get_next_candle_boundary(timeframe)
                        logger.debug(
                            f"[CandleSync] {timeframe} next fetch scheduled at "
                            f"{next_fetch_times[timeframe].strftime('%H:%M:%S')}"
                        )

            # ALWAYS check execution handler for exits (even during trade management)
            # For IB: ManualOCOManager checks profit targets and external exits
            # For TradeStation: Check order status and update exits
            if self._oco_manager:
                try:
                    self._oco_manager.check_profit_targets()
                    self._oco_manager.check_external_exits()
                except Exception as e:
                    logger.error(f"OCO manager check error: {e}")
            elif config.EXECUTION_BROKER == "tradestation":
                try:
                    if hasattr(self._execution_handler, 'update_trade_exits'):
                        self._execution_handler.update_trade_exits()
                except Exception as e:
                    logger.error(f"TradeStation exit check error: {e}")

            # Calculate sleep time
            if in_trade_management:
                # During trade management, just check exits frequently (1 second)
                sleep_seconds = 1.0
            else:
                # Calculate sleep time until the next candle boundary
                earliest_fetch = min(next_fetch_times.values())
                sleep_seconds = self._seconds_until(earliest_fetch)
                # Cap sleep to ensure we check OCO manager periodically
                # and don't miss events; minimum 0.5s to avoid busy-loop
                sleep_seconds = max(0.5, min(sleep_seconds, config.POLL_INTERVAL_SECONDS))

            # Use ib.sleep() to process IB events during wait
            self._ib.sleep(sleep_seconds)

    def run(self):
        """
        Starts the main data collection and pattern detection loop.

        Uses synchronous polling with ib.sleep() to ensure IB events are processed,
        which is critical for the ManualOCOManager's event-driven callbacks.
        """
        self._connect_ib()

        try:
            logger.info("Trade Service starting main polling loop (using fresh historical bars each cycle)...")
            self._poll_for_bars()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Trade Service shutting down...")
        except Exception as e:
            logger.error(f"Trade Service error: {e}", exc_info=True)
        finally:
            # Shutdown execution handler
            if config.EXECUTION_BROKER == "tradestation":
                logger.info("Shutting down TradeStation handler...")
                if hasattr(self._execution_handler, 'shutdown'):
                    self._execution_handler.shutdown()
            elif self._oco_manager:
                logger.info("Shutting down OCO Manager...")
                self._oco_manager.shutdown()

            # Always disconnect IB (used for market data even with TradeStation)
            if self._ib.isConnected():
                self._ib.disconnect()
            logger.info("Trade Service disconnected.")

def start_trade_service():
    """Entry point for the trade service process."""
    logger = setup_logger("TradeService", level=logging.DEBUG)
    service = TradeService()
    service.run()
