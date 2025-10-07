import pandas as pd
from .util import timeframe_to_timedelta

def detect_demand_zone(c1: pd.Series, c2: pd.Series, bullish_wick_ratio: float, bearish_wick_ratio: float, zone_top_offset: float, zone_bottom_offset: float, zone_timeframe: str) -> dict or None:
    """
    Detects a demand zone based on a refined two-candlestick pattern.

    Args:
        c1 (pd.Series): The first candle (bearish candidate).
        c2 (pd.Series): The second candle (bullish candidate).
        bullish_wick_ratio (float): Max wick size relative to body for the bullish candle.
        bearish_wick_ratio (float): Max upper wick size for the bearish candle relative to the bullish body.
        zone_top_offset (float): A buffer to add to the top of the detected zone.
        zone_bottom_offset (float): A buffer to add to the bottom of the detected zone.
        zone_timeframe (str): The timeframe of the candles (e.g., '15m', '1h').

    Returns:
        dict or None: A dictionary for the demand zone if detected, otherwise None.
    """
    try:
        # Core Condition 1: Second candle must be Bullish
        if not c2['close'] > c2['open']:
            return None

        # Core Condition 2: Bullish candle must engulf the bearish one
        if not c2['close'] > c1['open']:
            return None

        body_c1 = abs(c1['open'] - c1['close'])
        body_c2 = c2['close'] - c2['open']

        # New Core Condition 3: Bearish body must be less than 50% of the bullish body
        if not body_c1 < (0.5 * body_c2):
            return None

        # Refined Condition 4: Wicks on the bullish candle (c2) must be small
        upper_wick_c2 = c2['high'] - c2['close']
        lower_wick_c2 = c2['open'] - c2['low']
        if upper_wick_c2 >= (bullish_wick_ratio * body_c2) or lower_wick_c2 >= (bullish_wick_ratio * body_c2):
            return None

        # Refined Condition 5: Upper wick of bearish candle (c1) must be relatively small
        upper_wick_c1 = c1['high'] - c1['open']
        if upper_wick_c1 >= (bearish_wick_ratio * body_c2):
            return None

        # All conditions passed, a valid demand zone is detected
        timeframe_delta = timeframe_to_timedelta(zone_timeframe)
        if not timeframe_delta:
            return None # Timeframe string is invalid, can't calculate end time

        confirmation_time = c2.name + timeframe_delta
        demand_zone = {
            'top': c1['open'] + zone_top_offset,
            'bottom': c1['low'] - zone_bottom_offset,
            'timestamp': confirmation_time
        }
        return demand_zone

    except (KeyError, AttributeError):
        return None