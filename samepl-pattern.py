def is_doji(bar, precision=0.1):
    """Checks if a bar is a Doji pattern."""
    body = abs(bar.close - bar.open)
    price_range = bar.high - bar.low
    if price_range == 0:
        return False
    return body / price_range < precision

def is_hammer(bar):
    """Checks if a bar is a Hammer pattern (bullish reversal)."""
    body = abs(bar.close - bar.open)
    price_range = bar.high - bar.low
    if price_range == 0 or body == 0:
        return False
    
    lower_wick = min(bar.open, bar.close) - bar.low
    upper_wick = bar.high - max(bar.open, bar.close)
    
    # 1. Body is at the upper end of the range.
    # 2. Long lower wick (at least 2x body size).
    # 3. Very small or no upper wick.
    return lower_wick >= 2 * body and upper_wick < body

def is_dragonfly_doji(bar):
    """Checks if a bar is a Dragonfly Doji (bullish reversal)."""
    price_range = bar.high - bar.low
    if price_range == 0:
        return False

    # Check if it's a Doji with a very small body
    if not is_doji(bar, precision=0.05):
        return False

    # Check if the open/close is near the high (very small upper wick)
    return (bar.high - max(bar.open, bar.close)) / price_range < 0.1

def is_normal_bullish_candle(bar):
    """
    Checks if a bar is a 'Normal Bullish Candle', defined as a candle
    with a strong body and relatively small wicks.
    """
    # Must be a bullish candle
    if bar.open >= bar.close:
        return False

    body = bar.close - bar.open
    price_range = bar.high - bar.low

    if price_range == 0:
        return False

    # Body must be the dominant part of the candle (e.g., > 60% of the range)
    body_is_dominant = (body / price_range) > 0.6

    # Wicks should not be excessively long compared to the body
    upper_wick = bar.high - bar.close
    lower_wick = bar.open - bar.low
    wicks_are_controlled = upper_wick < body and lower_wick < body

    return body_is_dominant and wicks_are_controlled

def is_bullish_marubozu(bar):
    """Checks if a bar is a Bullish Marubozu pattern."""
    # The body should be bullish (green)
    if bar.open >= bar.close:
        return False

    price_range = bar.high - bar.low
    if price_range == 0:
        return False

    # Wicks should be a very small percentage of the total range
    lower_wick = (bar.open - bar.low) / price_range
    upper_wick = (bar.high - bar.close) / price_range

    return lower_wick < 0.05 and upper_wick < 0.05

def is_spinning_top(bar):
    """Checks if a bar is a Spinning Top pattern."""
    body = abs(bar.close - bar.open)
    price_range = bar.high - bar.low

    if price_range == 0 or body == 0:
        return False

    upper_wick = bar.high - max(bar.open, bar.close)
    lower_wick = min(bar.open, bar.close) - bar.low

    # Body must be small relative to the range
    is_small_body = body / price_range < 0.3

    # Both wicks must be longer than the body
    wicks_longer_than_body = upper_wick > body and lower_wick > body

    return is_small_body and wicks_longer_than_body

def is_near_marubozu(bar):
    """Checks if a bar is a Near-Marubozu or Strong Bullish Candle."""
    # Must be a bullish candle
    if bar.open >= bar.close:
        return False

    body = bar.close - bar.open
    price_range = bar.high - bar.low

    if price_range == 0:
        return False

    # Body should be a significant portion of the candle's range (e.g., > 70%)
    body_is_strong = (body / price_range) > 0.7

    # Wicks should be small relative to the range (e.g., < 25%)
    upper_wick = (bar.high - bar.close) / price_range
    lower_wick = (bar.open - bar.low) / price_range
    wicks_are_small = upper_wick < 0.25 and lower_wick < 0.25

    return body_is_strong and wicks_are_small

