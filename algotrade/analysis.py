import logging
import pandas as pd
from collections import deque
import redis
import json
import time

import config
from .util import timeframe_to_timedelta

class AnalysisEngine:
    """
    Analyzes incoming candlestick data from multiple timeframes to find demand zones
    and publishes them to Redis.
    """
    def __init__(self):
        """
        Initializes the AnalysisEngine, creating separate data stores for each timeframe.
        """
        # Create a dictionary of deques, one for each timeframe, to store candles separately.
        self._candles = {tf: deque(maxlen=2) for tf in config.ZONE_TIMEFRAMES}
        self._last_demand_zone = None
        self._redis_client = redis.Redis(decode_responses=True)
        logging.info(f"Analysis Engine initialized for timeframes: {config.ZONE_TIMEFRAMES}")

    def process_new_bar(self, bar: pd.Series, timeframe: str) -> dict or None:
        """
        Processes a new candlestick bar for a specific timeframe.
        """
        if timeframe not in self._candles:
            logging.warning(f"Received bar for unconfigured timeframe: {timeframe}")
            return None

        # Append the new bar to the correct timeframe's deque.
        self._candles[timeframe].append(bar)
        
        candle_history = self._candles[timeframe]
        if len(candle_history) < 2:
            logging.debug(f"Not enough data for {timeframe}, have {len(candle_history)} bars.")
            return None

        # c1 is the previous bar, c2 is the most recent (current) bar.
        c1, c2 = candle_history[0], candle_history[1]
        # Pass the timeframe to the detection method
        demand_zone = self._detect_and_publish_demand_zone(c1, c2, timeframe)

        if demand_zone:
            self._last_demand_zone = demand_zone

            # Convert UTC timestamp from the demand zone to a specific timezone for logging
            utc_time = pd.to_datetime(demand_zone['timestamp'])
            try:
                # Convert to US/Eastern timezone for user-friendly logs
                local_time = utc_time.tz_convert('US/Eastern')
                log_timestamp = local_time.strftime('%Y-%m-%d %H:%M:%S %Z') # Include timezone abbreviation
            except Exception as e:
                logging.warning(f"Could not convert timestamp to local time for logging: {e}")
                log_timestamp = demand_zone['timestamp'] # Fallback to UTC

            logging.info(
                f"\n-------------------- DEMAND ZONE PUBLISHED --------------------\n"
                f"Demand Zone Published from {timeframe} at {log_timestamp}: "
                f"Top={demand_zone['zone_top']:.2f}, Bottom={demand_zone['zone_bottom']:.2f}, "
                f"ID={demand_zone['id']}"
                f"\n-----------------------------------------------------------------"
            )
            return demand_zone

        return None

    def _detect_and_publish_demand_zone(self, c1: pd.Series, c2: pd.Series, zone_timeframe: str) -> dict or None:
        """
        Detects a demand zone using the refined logic and publishes it to Redis if found.
        """
        logging.info(f"[{zone_timeframe}] Analyzing candles for demand zone:\nC1 [{c1.name} {zone_timeframe}]: {c1.to_dict()}\nC2 [{c2.name} {zone_timeframe}]: {c2.to_dict()}")
        try:
            # Core Condition 1: Second candle must be Bullish
            if not c2['close'] > c2['open']:
                return None

            # Core Condition 2: Bullish candle must engulf the bearish one
            if not c2['close'] > c1['open']:
                return None

            body_c1 = abs(c1['open'] - c1['close'])
            body_c2 = c2['close'] - c2['open']

            # Core Condition 3: c1 open must be inside c2 body OR close to c2 open.
            is_inside = (c1['open'] >= c2['open']) and (c1['open'] <= c2['close'])
            is_close = abs(c1['open'] - c2['open']) <= body_c1
            
            if not (is_inside or is_close):
                return None

            # Core Condition 4: Base candle body (c1) must be less than 50% of the explosive candle body (c2)
            if not body_c1 < (0.5 * body_c2):
                return None

            # Refined Condition 5: Wicks on the bullish candle (c2) must be small
            upper_wick_c2 = c2['high'] - c2['close']
            lower_wick_c2 = c2['open'] - c2['low']
            if upper_wick_c2 >= (config.BULLISH_WICK_RATIO * body_c2) or lower_wick_c2 >= (config.BULLISH_WICK_RATIO * body_c2):
                return None

            # Refined Condition 6: Upper wick of base candle (c1) must be relatively small
            upper_wick_c1 = c1['high'] - c1['open']
            if upper_wick_c1 >= (config.BEARISH_WICK_RATIO * body_c2):
                return None

            # All conditions passed, a valid demand zone is detected
            timeframe_delta = timeframe_to_timedelta(zone_timeframe)
            if not timeframe_delta:
                logging.warning(f"Invalid timeframe string '{zone_timeframe}', cannot calculate zone end time.")
                return None

            confirmation_time = c2.name + timeframe_delta
            
            # Generate a unique ID for the zone using the timestamp
            zone_id = str(confirmation_time.timestamp())

            demand_zone = {
                'id': zone_id,
                'status': 'active',
                'zone_top': c1['open'] + config.DEMAND_ZONE_OFFSET_TOP,
                'zone_bottom': c1['low'] - config.DEMAND_ZONE_OFFSET_BOTTOM,
                'timestamp': str(confirmation_time)
            }
            
            payload = json.dumps(demand_zone)
            
            # Set the current state in the hash and publish the event
            self._redis_client.hset("active_demand_zones", zone_id, payload)
            self._redis_client.publish("demand_zones", payload)
            
            return demand_zone

        except (KeyError, AttributeError) as e:
            logging.error(f"Error processing candles: {e}")
            return None
        except redis.RedisError as e:
            logging.error(f"Redis error: {e}")
            return None

    def get_last_demand_zone(self) -> dict or None:
        """
        Returns the most recently detected demand zone.
        """
        return self._last_demand_zone