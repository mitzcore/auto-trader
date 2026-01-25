
import argparse
import logging
from datetime import datetime, timedelta
import pandas as pd
import re
from collections import deque
import json

from ib_insync import IB, Stock, util

import config
from algotrade.patterns import PATTERN_REGISTRY
from algotrade.logger import setup_logger
from algotrade.analysis import AnalysisEngine
from algotrade.util import (
    needs_session_alignment,
    get_session_aligned_timeframe_mapping,
    aggregate_dataframe_to_session_aligned,
    MARKET_OPEN_TIME,
)

logger = setup_logger(__name__, level=config.BACKTEST_LOG_LEVEL)

# Force DEBUG logging for patterns module
patterns_logger = logging.getLogger('algotrade.patterns')
patterns_logger.setLevel(logging.DEBUG)
# Add console handler if it doesn't have one
if not patterns_logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    patterns_logger.addHandler(console_handler)


def _convert_tf_to_ib_format(tf_string: str) -> str:
    """
    Converts a timeframe string like '1m', '2m', '1h' to IB format like '1 min', '2 mins', '1 hour'.

    Supports both minute ('m') and hour ('h') timeframes.
    """
    tf_lower = tf_string.lower()

    # Try minute format first
    match_min = re.match(r"(\d+)m$", tf_lower)
    if match_min:
        value = int(match_min.group(1))
        unit_full = "min" if value == 1 else "mins"
        return f"{value} {unit_full}"

    # Try hour format
    match_hour = re.match(r"(\d+)h$", tf_lower)
    if match_hour:
        value = int(match_hour.group(1))
        unit_full = "hour" if value == 1 else "hours"
        return f"{value} {unit_full}"

    raise ValueError(f"Invalid timeframe format: {tf_string}. Supported: '1m', '2m', '1h', '2h', etc.")


# IB API max duration limits per bar size
IB_MAX_DURATION_DAYS = {
    "1m": 1,    # 1 day max for 1-min bars
    "2m": 2,    # 2 days max for 2-min bars
    "3m": 7,    # 1 week max for 3-min bars
    "5m": 7,    # 1 week max for 5-min bars
    "15m": 14,  # 2 weeks max for 15-min bars
    "30m": 30,  # 1 month max for 30-min bars
    "1h": 30,   # 1 month max for 1-hour bars
    "2h": 30,   # 1 month max for 2-hour bars
    "3h": 30,   # 1 month max for 3-hour bars
    "4h": 30,   # 1 month max for 4-hour bars
}

# Mapping for session-aligned aggregation (target -> source timeframe)
SESSION_ALIGNED_SOURCE_TF = get_session_aligned_timeframe_mapping()


def _format_timestamp(timestamp) -> str:
    """Format timestamp for logging."""
    try:
        if hasattr(timestamp, 'tz_convert'):
            return timestamp.tz_convert('US/Eastern').strftime('%Y-%m-%d %H:%M:%S %Z')
        if hasattr(timestamp, 'tz_localize'):
            return timestamp.tz_localize('UTC').tz_convert('US/Eastern').strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception:
        pass
    return str(timestamp)


def _download_bars_with_session_alignment(
    ib: IB,
    contract,
    start_dt: datetime,
    end_dt: datetime,
    timeframe: str
) -> pd.DataFrame:
    """
    Download historical bars with automatic session alignment for hourly+ timeframes.

    For timeframes >= 1h, fetches 30m bars and aggregates them to create
    session-aligned bars matching TradingView (9:30, 10:30, 11:30...).

    Args:
        ib: Connected IB instance
        contract: IB contract
        start_dt: Start date
        end_dt: End date
        timeframe: Bar size (e.g., "2m", "1h", "2h")

    Returns:
        DataFrame with OHLCV bars sorted by date, session-aligned if applicable
    """
    use_session_alignment = needs_session_alignment(timeframe)

    if use_session_alignment:
        # Fetch smaller bars and aggregate for session alignment
        source_tf = SESSION_ALIGNED_SOURCE_TF.get(timeframe, "30m")
        logger.info(f"[SessionAlign] {timeframe} requires aggregation from {source_tf} bars")
        ib_bar_size = _convert_tf_to_ib_format(source_tf)
        max_days = IB_MAX_DURATION_DAYS.get(source_tf, 30)
    else:
        # Direct fetch for smaller timeframes
        ib_bar_size = _convert_tf_to_ib_format(timeframe)
        max_days = IB_MAX_DURATION_DAYS.get(timeframe, 1)

    # Download data in chunks respecting IB's duration limits
    all_bars = []
    current_end = end_dt

    while current_end >= start_dt:
        chunk_start = current_end - timedelta(days=max_days - 1)
        if chunk_start < start_dt:
            chunk_start = start_dt

        chunk_days = (current_end - chunk_start).days + 1
        duration_str = f"{chunk_days} D"
        end_date_formatted = current_end.strftime("%Y%m%d 23:59:59") + " US/Eastern"

        logger.debug(f"Fetching {duration_str} of {ib_bar_size} ending {current_end.strftime('%Y-%m-%d')}")

        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_date_formatted,
            durationStr=duration_str,
            barSizeSetting=ib_bar_size,
            whatToShow='TRADES',
            useRTH=config.USE_RTH_ONLY,
            formatDate=1
        )

        if bars:
            all_bars.extend(bars)

        current_end = chunk_start - timedelta(days=1)
        ib.sleep(0.5)  # Avoid IB pacing violations

    if not all_bars:
        logger.warning(f"No bars downloaded for {timeframe}")
        return pd.DataFrame()

    # Convert to DataFrame
    df = util.df(all_bars)
    df = df.sort_values(by='date', ascending=True)
    df = df.drop_duplicates(subset=['date'], keep='first')

    # Apply session alignment aggregation if needed
    if use_session_alignment:
        source_tf = SESSION_ALIGNED_SOURCE_TF.get(timeframe, "30m")

        # Prepare DataFrame for aggregation (rename 'date' to 'datetime')
        df_for_agg = df.rename(columns={'date': 'datetime'})

        # Aggregate to session-aligned bars
        df_aligned = aggregate_dataframe_to_session_aligned(
            df_for_agg,
            source_tf=source_tf,
            target_tf=timeframe,
            session_start=MARKET_OPEN_TIME
        )

        if df_aligned.empty:
            logger.warning(f"Session alignment produced no bars for {timeframe}")
            return pd.DataFrame()

        # Rename back to 'date' for consistency with rest of backtest
        df_aligned = df_aligned.rename(columns={'datetime': 'date'})

        logger.info(
            f"[SessionAlign] Aggregated {len(df)} {source_tf} bars → "
            f"{len(df_aligned)} {timeframe} session-aligned bars"
        )
        return df_aligned

    return df


def _detect_demand_zones_from_bars(
    df_bars: pd.DataFrame,
    timeframe: str,
    analysis_engine: AnalysisEngine = None
) -> list:
    """
    Detect demand zones from historical bars using the AnalysisEngine.

    Processes bars sequentially through the analysis engine to detect
    demand zones, mimicking live detection behavior.

    Args:
        df_bars: DataFrame with OHLCV bars (must have 'date' column)
        timeframe: Timeframe string (e.g., "30m", "1h")
        analysis_engine: Optional existing AnalysisEngine instance

    Returns:
        List of detected demand zones with structure:
        [{'id': int, 'zone_top': float, 'zone_bottom': float, 'timestamp': str, 'zone_timeframe': str}, ...]
    """
    if df_bars.empty:
        logger.warning(f"[ZoneDetect] No bars provided for {timeframe}")
        return []

    # Create engine if not provided
    engine = analysis_engine or AnalysisEngine()
    detected_zones = []

    logger.info(f"[ZoneDetect] Processing {len(df_bars)} {timeframe} bars for demand zone detection...")

    for _, row in df_bars.iterrows():
        # Convert row to pandas Series with proper name (timestamp)
        bar_series = pd.Series(
            {'open': row['open'], 'high': row['high'], 'low': row['low'], 'close': row['close']},
            name=row['date']
        )

        # Process bar through analysis engine
        zone = engine.process_new_bar(bar_series, timeframe=timeframe)

        if zone:
            detected_zones.append(zone)
            logger.info(
                f"[ZoneDetect] Zone found on {timeframe} at {zone['timestamp']}: "
                f"Top=${zone['zone_top']:.2f}, Bottom=${zone['zone_bottom']:.2f}"
            )

    logger.info(f"[ZoneDetect] Detected {len(detected_zones)} demand zones on {timeframe}")
    return detected_zones


def _download_zone_detection_bars(
    ib: IB,
    contract,
    start_dt: datetime,
    end_dt: datetime,
    zone_timeframes: list
) -> dict:
    """
    Download bars for all zone detection timeframes.

    Args:
        ib: Connected IB instance
        contract: IB contract
        start_dt: Start date
        end_dt: End date
        zone_timeframes: List of timeframes to download (e.g., ["30m", "1h"])

    Returns:
        Dict mapping timeframe to DataFrame: {"30m": df_30m, "1h": df_1h, ...}
    """
    zone_bars = {}

    for tf in zone_timeframes:
        logger.info(f"[ZoneDownload] Downloading {tf} bars for demand zone detection...")
        df = _download_bars_with_session_alignment(ib, contract, start_dt, end_dt, tf)

        if df.empty:
            logger.warning(f"[ZoneDownload] No {tf} bars downloaded for zone detection")
            continue

        zone_bars[tf] = df
        logger.info(f"[ZoneDownload] Downloaded {len(df)} {tf} bars")

    return zone_bars


def _download_stop_check_bars(ib: IB, contract, start_dt: datetime, end_dt: datetime, timeframe: str = None) -> pd.DataFrame:
    """
    Download bars for stop loss checking with configurable timeframe.

    Args:
        ib: Connected IB instance
        contract: IB contract (SPY)
        start_dt: Start date
        end_dt: End date (+ 1 day for look-ahead)
        timeframe: Bar size (e.g., "1m", "2m", "5m", "15m"). Defaults to config.BACKTEST_STOP_CHECK_TIMEFRAME

    Returns:
        DataFrame with bars sorted by date
    """
    # Use config if not specified
    if timeframe is None:
        timeframe = getattr(config, 'BACKTEST_STOP_CHECK_TIMEFRAME', '1m')

    # Convert to IB format and get max duration
    ib_bar_size = _convert_tf_to_ib_format(timeframe)
    max_days = IB_MAX_DURATION_DAYS.get(timeframe, 1)

    # Add 1 extra day at the end for look-ahead (checking N bars after last pattern per config)
    extended_end_dt = end_dt + timedelta(days=1)

    all_bars = []
    current_end = extended_end_dt

    logger.info(f"Downloading {timeframe} bars for stop loss checking...")

    while current_end >= start_dt:
        chunk_start = current_end - timedelta(days=max_days - 1)
        if chunk_start < start_dt:
            chunk_start = start_dt

        chunk_days = (current_end - chunk_start).days + 1
        duration_str = f"{chunk_days} D"
        end_date_formatted = current_end.strftime("%Y%m%d 23:59:59") + " US/Eastern"

        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_date_formatted,
            durationStr=duration_str,
            barSizeSetting=ib_bar_size,
            whatToShow='TRADES',
            useRTH=config.USE_RTH_ONLY,
            formatDate=1
        )

        if bars:
            all_bars.extend(bars)

        current_end = chunk_start - timedelta(days=1)
        ib.sleep(0.5)

    if not all_bars:
        logger.warning(f"No {timeframe} bars downloaded for stop loss checking.")
        return pd.DataFrame()

    df = util.df(all_bars)
    df = df.sort_values(by='date', ascending=True)
    df = df.drop_duplicates(subset=['date'], keep='first')

    logger.info(f"Downloaded {len(df)} {timeframe} bars for stop loss checking.")
    return df


def _check_stop_loss(entry_timestamp, entry_price: float, swing_low: float, df_stop_bars: pd.DataFrame) -> tuple[str, float, str]:
    """
    Check WIN/LOSS status based on price action.

    Logic (checked in order on each bar):
    1. WIN: bar.high >= entry_price + BACKTEST_WIN_BOUNCE_DOLLARS (price moved up from entry)
    2. LOSS: bar.low < swing_low (support broke)
    3. UNKNOWN: Neither condition met after all bars

    Args:
        entry_timestamp: Trade entry timestamp (pattern trigger time)
        entry_price: Entry price (trigger candle close)
        swing_low: Swing low price (support level for stop loss)
        df_stop_bars: DataFrame of bars for stop checking (timeframe from config)

    Returns:
        Tuple of (status, lowest_price, result_time):
        - status: 'WIN', 'LOSS', or 'UNKNOWN'
        - lowest_price: Lowest low seen in the monitoring period
        - result_time: Timestamp when WIN/LOSS triggered (or empty string if UNKNOWN)
    """
    num_bars = config.BACKTEST_STOP_CHECK_BARS
    win_bounce = config.BACKTEST_WIN_BOUNCE_DOLLARS
    win_target = entry_price + win_bounce
    stop_tf = getattr(config, 'BACKTEST_STOP_CHECK_TIMEFRAME', '1m')

    if df_stop_bars.empty:
        return 'UNKNOWN', 0.0, ''

    # Convert entry timestamp to comparable format
    try:
        if hasattr(entry_timestamp, 'tz_convert'):
            entry_ts = entry_timestamp.tz_convert('UTC')
        elif hasattr(entry_timestamp, 'tz_localize'):
            entry_ts = entry_timestamp.tz_localize('UTC')
        else:
            entry_ts = pd.to_datetime(entry_timestamp, utc=True)
    except Exception:
        entry_ts = pd.to_datetime(entry_timestamp, utc=True)

    # Find bars AFTER entry timestamp
    future_bars = df_stop_bars[df_stop_bars['date'] > entry_ts].head(num_bars)

    if future_bars.empty:
        logger.warning(f"No {stop_tf} bars found after {entry_ts} for stop loss check")
        return 'UNKNOWN', 0.0, ''

    # Track lowest price seen
    lowest_price = float('inf')

    for _, bar in future_bars.iterrows():
        bar_high = bar['high']
        bar_low = bar['low']
        lowest_price = min(lowest_price, bar_low)

        # Check WIN first: price moved up from entry
        if bar_high >= win_target:
            result_time = _format_timestamp(bar['date'])
            logger.debug(f"WIN: bar high {bar_high:.2f} >= win target {win_target:.2f} (entry {entry_price:.2f} + ${win_bounce}) at {result_time}")
            return 'WIN', lowest_price, result_time

        # Check LOSS second: support broke
        if bar_low < swing_low:
            result_time = _format_timestamp(bar['date'])
            logger.debug(f"LOSS: bar low {bar_low:.2f} < swing_low {swing_low:.2f} at {result_time}")
            return 'LOSS', lowest_price, result_time

    # Neither condition met after all bars
    logger.debug(f"UNKNOWN: No WIN/LOSS after {len(future_bars)} {stop_tf} bars. Entry: {entry_price:.2f}, Win target: {win_target:.2f}, Swing low: {swing_low:.2f}")
    return 'UNKNOWN', lowest_price if lowest_price != float('inf') else 0.0, ''


def _write_results_markdown(trade_results: list, start_date: str, end_date: str, pattern_mode: str, symbol: str, output_file: str = "backtest_results.md"):
    """
    Write backtest results to a markdown file with table format.

    Args:
        trade_results: List of trade result dictionaries
        start_date: Backtest start date
        end_date: Backtest end date
        pattern_mode: Pattern mode used (6_candle, 3_candle, or both)
        symbol: Symbol that was backtested
        output_file: Output file path (default: backtest_results.md)
    """
    with open(output_file, 'w') as f:
        # Header
        f.write(f"# Backtest Results\n\n")
        f.write(f"**Date Range:** {start_date} to {end_date}\n\n")
        f.write(f"**Pattern Mode:** {pattern_mode}\n\n")
        f.write(f"**Symbol:** {symbol}\n\n")
        f.write(f"**Total Signals:** {len(trade_results)}\n\n")

        if not trade_results:
            f.write("No patterns found during backtest period.\n")
            return

        # Win/Loss Summary
        wins = sum(1 for tr in trade_results if tr.get('status') == 'WIN')
        losses = sum(1 for tr in trade_results if tr.get('status') == 'LOSS')
        unknown = sum(1 for tr in trade_results if tr.get('status') not in ('WIN', 'LOSS'))
        win_rate = (wins / len(trade_results) * 100) if trade_results else 0

        f.write("## Performance Summary\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Total Trades | {len(trade_results)} |\n")
        f.write(f"| Wins | {wins} |\n")
        f.write(f"| Losses | {losses} |\n")
        if unknown > 0:
            f.write(f"| Unknown | {unknown} |\n")
        f.write(f"| **Win Rate** | **{win_rate:.1f}%** |\n")
        f.write("\n")

        # Summary by pattern type
        pattern_stats = {}
        for tr in trade_results:
            p = tr['pattern']
            if p not in pattern_stats:
                pattern_stats[p] = {'total': 0, 'wins': 0, 'losses': 0}
            pattern_stats[p]['total'] += 1
            if tr.get('status') == 'WIN':
                pattern_stats[p]['wins'] += 1
            elif tr.get('status') == 'LOSS':
                pattern_stats[p]['losses'] += 1

        f.write("## Summary by Pattern\n\n")
        f.write("| Pattern | Total | Wins | Losses | Win Rate |\n")
        f.write("|---------|------:|-----:|-------:|---------:|\n")
        for pattern, stats in sorted(pattern_stats.items()):
            wr = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
            f.write(f"| {pattern} | {stats['total']} | {stats['wins']} | {stats['losses']} | {wr:.1f}% |\n")
        f.write("\n")

        # Summary by timeframe
        tf_stats = {}
        for tr in trade_results:
            tf = tr['timeframe']
            if tf not in tf_stats:
                tf_stats[tf] = {'total': 0, 'wins': 0, 'losses': 0}
            tf_stats[tf]['total'] += 1
            if tr.get('status') == 'WIN':
                tf_stats[tf]['wins'] += 1
            elif tr.get('status') == 'LOSS':
                tf_stats[tf]['losses'] += 1

        f.write("## Summary by Timeframe\n\n")
        f.write("| Timeframe | Total | Wins | Losses | Win Rate |\n")
        f.write("|-----------|------:|-----:|-------:|---------:|\n")
        for tf, stats in sorted(tf_stats.items()):
            wr = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
            f.write(f"| {tf} | {stats['total']} | {stats['wins']} | {stats['losses']} | {wr:.1f}% |\n")
        f.write("\n")

        # Trade confirmations table
        f.write("## Trade Confirmations\n\n")
        f.write("| # | Timestamp | TF | Pattern | Entry | Swing High | Swing Low | Status | Lowest | Details |\n")
        f.write("|--:|-----------|:--:|:-------:|------:|-----------:|----------:|:------:|-------:|--------|\n")

        for i, tr in enumerate(trade_results, 1):
            status = tr.get('status', 'N/A')
            status_emoji = '✅' if status == 'WIN' else ('❌' if status == 'LOSS' else '⚠️')

            f.write(
                f"| {i} "
                f"| {tr['timestamp']} "
                f"| {tr['timeframe']} "
                f"| {tr['pattern_code']} "
                f"| ${tr['entry_price']:.2f} "
                f"| ${tr.get('swing_high', 0):.2f} "
                f"| ${tr.get('swing_low', 0):.2f} "
                f"| {status_emoji} {status} "
                f"| ${tr.get('lowest_price', 0):.2f} "
                f"| {tr.get('details', '')} |\n"
            )

        f.write("\n")

        # Losses detail section
        loss_trades = [tr for tr in trade_results if tr.get('status') == 'LOSS']
        if loss_trades:
            f.write("## Loss Details\n\n")
            f.write("| # | Timestamp | Pattern | Entry | Swing Low | Break Time |\n")
            f.write("|--:|-----------|:-------:|------:|----------:|------------|\n")
            for i, tr in enumerate(loss_trades, 1):
                f.write(
                    f"| {i} "
                    f"| {tr['timestamp']} "
                    f"| {tr['pattern_code']} "
                    f"| ${tr['entry_price']:.2f} "
                    f"| ${tr.get('swing_low', 0):.2f} "
                    f"| {tr.get('break_time', 'N/A')} |\n"
                )
            f.write("\n")

        f.write("---\n")
        f.write(f"*Generated by Pattern Backtest | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")

    logger.info(f"Results written to {output_file}")


def _write_results_html(trade_results: list, start_date: str, end_date: str, pattern_mode: str, symbol: str, output_file: str = "backtest_results.html"):
    """
    Write backtest results to an HTML file with styled tables and charts.

    Args:
        trade_results: List of trade result dictionaries
        start_date: Backtest start date
        end_date: Backtest end date
        pattern_mode: Pattern mode used
        symbol: Symbol that was backtested
        output_file: Output file path
    """
    # Calculate statistics
    total = len(trade_results)
    wins = sum(1 for tr in trade_results if tr.get('status') == 'WIN')
    losses = sum(1 for tr in trade_results if tr.get('status') == 'LOSS')
    unknown = total - wins - losses
    win_rate = (wins / total * 100) if total > 0 else 0

    # Pattern stats
    pattern_stats = {}
    for tr in trade_results:
        p = tr['pattern']
        if p not in pattern_stats:
            pattern_stats[p] = {'total': 0, 'wins': 0, 'losses': 0}
        pattern_stats[p]['total'] += 1
        if tr.get('status') == 'WIN':
            pattern_stats[p]['wins'] += 1
        elif tr.get('status') == 'LOSS':
            pattern_stats[p]['losses'] += 1

    # Timeframe stats
    tf_stats = {}
    for tr in trade_results:
        tf = tr['timeframe']
        if tf not in tf_stats:
            tf_stats[tf] = {'total': 0, 'wins': 0, 'losses': 0}
        tf_stats[tf]['total'] += 1
        if tr.get('status') == 'WIN':
            tf_stats[tf]['wins'] += 1
        elif tr.get('status') == 'LOSS':
            tf_stats[tf]['losses'] += 1

    # Generate pie chart SVG for win/loss
    def generate_pie_chart(wins, losses, size=200):
        total = wins + losses
        if total == 0:
            return '<svg width="200" height="200"><text x="100" y="100" text-anchor="middle">No Data</text></svg>'

        win_pct = wins / total
        win_angle = win_pct * 360

        # Calculate arc paths
        def polar_to_cart(cx, cy, r, angle_deg):
            import math
            angle_rad = (angle_deg - 90) * math.pi / 180
            return cx + r * math.cos(angle_rad), cy + r * math.sin(angle_rad)

        cx, cy, r = size/2, size/2, size/2 - 10

        # Win slice (green)
        if win_pct == 1:
            win_path = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#22c55e"/>'
        elif win_pct == 0:
            win_path = ''
        else:
            x1, y1 = polar_to_cart(cx, cy, r, 0)
            x2, y2 = polar_to_cart(cx, cy, r, win_angle)
            large_arc = 1 if win_angle > 180 else 0
            win_path = f'<path d="M{cx},{cy} L{x1},{y1} A{r},{r} 0 {large_arc},1 {x2},{y2} Z" fill="#22c55e"/>'

        # Loss slice (red)
        if win_pct == 0:
            loss_path = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ef4444"/>'
        elif win_pct == 1:
            loss_path = ''
        else:
            x1, y1 = polar_to_cart(cx, cy, r, win_angle)
            x2, y2 = polar_to_cart(cx, cy, r, 360)
            large_arc = 1 if (360 - win_angle) > 180 else 0
            loss_path = f'<path d="M{cx},{cy} L{x1},{y1} A{r},{r} 0 {large_arc},1 {x2},{y2} Z" fill="#ef4444"/>'

        return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
            {win_path}
            {loss_path}
            <text x="{cx}" y="{cy-10}" text-anchor="middle" fill="white" font-weight="bold" font-size="24">{win_pct*100:.0f}%</text>
            <text x="{cx}" y="{cy+15}" text-anchor="middle" fill="white" font-size="12">Win Rate</text>
        </svg>'''

    pie_chart = generate_pie_chart(wins, losses)

    # Build HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Results - {symbol}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: #f5f5f5;
            color: #333;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #1a1a1a; margin-bottom: 10px; }}
        h2 {{ color: #444; margin: 30px 0 15px; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }}
        .meta {{ color: #666; margin-bottom: 30px; }}
        .meta span {{ margin-right: 20px; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .card-title {{ font-size: 14px; color: #888; text-transform: uppercase; }}
        .card-value {{ font-size: 32px; font-weight: bold; color: #1a1a1a; }}
        .card-value.win {{ color: #22c55e; }}
        .card-value.loss {{ color: #ef4444; }}
        .charts {{ display: flex; gap: 40px; flex-wrap: wrap; justify-content: center; margin: 30px 0; }}
        .chart-container {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .chart-title {{ font-size: 14px; color: #888; margin-bottom: 15px; text-align: center; }}
        .legend {{ display: flex; gap: 20px; justify-content: center; margin-top: 15px; }}
        .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 12px; }}
        .legend-color {{ width: 12px; height: 12px; border-radius: 2px; }}
        .legend-win {{ background: #22c55e; }}
        .legend-loss {{ background: #ef4444; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }}
        th, td {{ padding: 12px 16px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; color: #555; font-size: 13px; text-transform: uppercase; }}
        tr:hover {{ background: #f8f9fa; }}
        .status-win {{ color: #22c55e; font-weight: bold; }}
        .status-loss {{ color: #ef4444; font-weight: bold; }}
        .status-unknown {{ color: #f59e0b; }}
        .number {{ text-align: right; font-family: 'SF Mono', Monaco, monospace; }}
        .timestamp {{ font-size: 12px; color: #666; }}
        .pattern-badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .pattern-sm {{ background: #dbeafe; color: #1d4ed8; }}
        .pattern-3c {{ background: #fef3c7; color: #b45309; }}
        footer {{ text-align: center; color: #888; font-size: 12px; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Backtest Results</h1>
        <div class="meta">
            <span><strong>Symbol:</strong> {symbol}</span>
            <span><strong>Date Range:</strong> {start_date} to {end_date}</span>
            <span><strong>Pattern Mode:</strong> {pattern_mode}</span>
        </div>

        <div class="cards">
            <div class="card">
                <div class="card-title">Total Trades</div>
                <div class="card-value">{total}</div>
            </div>
            <div class="card">
                <div class="card-title">Wins</div>
                <div class="card-value win">{wins}</div>
            </div>
            <div class="card">
                <div class="card-title">Losses</div>
                <div class="card-value loss">{losses}</div>
            </div>
            <div class="card">
                <div class="card-title">Win Rate</div>
                <div class="card-value">{win_rate:.1f}%</div>
            </div>
        </div>

        <div class="charts">
            <div class="chart-container">
                <div class="chart-title">Win/Loss Distribution</div>
                {pie_chart}
                <div class="legend">
                    <div class="legend-item"><div class="legend-color legend-win"></div> Wins ({wins})</div>
                    <div class="legend-item"><div class="legend-color legend-loss"></div> Losses ({losses})</div>
                </div>
            </div>
        </div>

        <h2>Summary by Timeframe</h2>
        <table>
            <thead>
                <tr>
                    <th>Timeframe</th>
                    <th class="number">Total</th>
                    <th class="number">Wins</th>
                    <th class="number">Losses</th>
                    <th class="number">Win Rate</th>
                </tr>
            </thead>
            <tbody>'''

    for tf, stats in sorted(tf_stats.items()):
        wr = (stats['wins'] / stats['total'] * 100) if stats['total'] > 0 else 0
        html += f'''
                <tr>
                    <td>{tf}</td>
                    <td class="number">{stats['total']}</td>
                    <td class="number status-win">{stats['wins']}</td>
                    <td class="number status-loss">{stats['losses']}</td>
                    <td class="number">{wr:.1f}%</td>
                </tr>'''

    html += '''
            </tbody>
        </table>

        <h2>Trade Details</h2>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Timestamp</th>
                    <th>TF</th>
                    <th>Pattern</th>
                    <th class="number">Drop %</th>
                    <th class="number">Reclaim %</th>
                    <th class="number">Entry</th>
                    <th class="number">Swing High</th>
                    <th class="number">Swing Low</th>
                    <th>Status</th>
                    <th class="number">Lowest</th>
                </tr>
            </thead>
            <tbody>'''

    for i, tr in enumerate(trade_results, 1):
        status = tr.get('status', 'N/A')
        status_class = 'status-win' if status == 'WIN' else ('status-loss' if status == 'LOSS' else 'status-unknown')
        status_icon = '✅' if status == 'WIN' else ('❌' if status == 'LOSS' else '⚠️')
        pattern_class = 'pattern-sm' if tr['pattern_code'] == 'SM' else 'pattern-3c'
        drop_pct = tr.get('drop_pct', 0)
        reclaim_pct = tr.get('reclaim_pct', 0)

        html += f'''
                <tr>
                    <td>{i}</td>
                    <td class="timestamp">{tr['timestamp']}</td>
                    <td>{tr['timeframe']}</td>
                    <td><span class="pattern-badge {pattern_class}">{tr['pattern_code']}</span></td>
                    <td class="number">{drop_pct:.2f}%</td>
                    <td class="number">{reclaim_pct:.1f}%</td>
                    <td class="number">${tr['entry_price']:.2f}</td>
                    <td class="number">${tr.get('swing_high', 0):.2f}</td>
                    <td class="number">${tr.get('swing_low', 0):.2f}</td>
                    <td class="{status_class}">{status_icon} {status}</td>
                    <td class="number">${tr.get('lowest_price', 0):.2f}</td>
                </tr>'''

    html += f'''
            </tbody>
        </table>

        <footer>
            Generated by Pattern Backtest | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </footer>
    </div>
</body>
</html>'''

    with open(output_file, 'w') as f:
        f.write(html)

    logger.info(f"HTML results written to {output_file}")


def run_pattern_backtest(start_date_str: str, end_date_str: str, pattern_mode: str = None, symbol: str = None, output_file: str = "backtest_results.md"):
    """
    Main backtesting function. Uses PATTERN_REGISTRY to dynamically run
    pattern detection based on configured PATTERN_MODE.

    Supports "both" mode to run 6_candle and 3_candle patterns in parallel.

    Args:
        start_date_str: Start date (YYYY-MM-DD)
        end_date_str: End date (YYYY-MM-DD)
        pattern_mode: Override config.PATTERN_MODE (optional)
        symbol: Symbol to backtest (default: config.SYMBOL)
        output_file: Output markdown file path (default: backtest_results.md)
    """
    # Determine symbol and pattern mode
    backtest_symbol = symbol or config.SYMBOL
    mode = pattern_mode or config.PATTERN_MODE

    # Handle "both" mode - run multiple patterns
    if mode == "both":
        active_patterns = ["6_candle", "3_candle"]
        # Use max candle count for buffer
        candle_count = max(PATTERN_REGISTRY[p]["candle_count"] for p in active_patterns)
        logger.info(f"=== Pattern Backtest Starting (BOTH PATTERNS) ===")
        logger.info(f"Patterns: 6_candle + 3_candle | Max candles: {candle_count} | Date range: {start_date_str} to {end_date_str}")
    elif mode in PATTERN_REGISTRY:
        active_patterns = [mode]
        candle_count = PATTERN_REGISTRY[mode]["candle_count"]
        logger.info(f"=== Pattern Backtest Starting ===")
        logger.info(f"Mode: {mode} | Candles: {candle_count} | Date range: {start_date_str} to {end_date_str}")
    else:
        logger.error(f"Unknown PATTERN_MODE: {mode}. Available: {list(PATTERN_REGISTRY.keys())} or 'both'")
        return

    # =========================================================================
    # DEMAND ZONE HANDLING
    # =========================================================================
    # Option 1: BACKTEST_DETECT_ZONES=True -> Detect zones dynamically from bars
    # Option 2: BACKTEST_DETECT_ZONES=False -> Load from backtest_zones.txt file
    # Option 3: DEMAND_ZONE_TRADING=False -> No zone filtering at all
    # =========================================================================
    loaded_zones = []
    detect_zones_dynamically = getattr(config, 'BACKTEST_DETECT_ZONES', False)

    if config.DEMAND_ZONE_TRADING and not detect_zones_dynamically:
        # Load zones from file (existing behavior)
        try:
            with open("backtest_zones.txt", "r") as f:
                loaded_zones = json.load(f)
            if not loaded_zones:
                logger.warning("backtest_zones.txt is empty. Running without zone filtering.")
            else:
                logger.info(f"Loaded {len(loaded_zones)} demand zones from backtest_zones.txt.")
        except FileNotFoundError:
            logger.warning("backtest_zones.txt not found. Running without zone filtering.")
        except json.JSONDecodeError:
            logger.error("Could not parse backtest_zones.txt. Running without zone filtering.")
    elif config.DEMAND_ZONE_TRADING and detect_zones_dynamically:
        logger.info("Dynamic zone detection enabled. Zones will be detected during backtest.")

    ib = IB()
    total_patterns_found = 0

    # Collect trade results for markdown output
    trade_results = []

    # Track detected zones (for dynamic detection)
    all_detected_zones = []

    try:
        ib.connect(config.IB_HOST, config.IB_PORT, clientId=config.IB_CLIENT_ID + 3)
        logger.info("Connected to IB for historical data download.")

        contract = Stock(backtest_symbol, config.EXCHANGE, config.CURRENCY)
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')

        logger.info(f"Symbol: {backtest_symbol}")

        # Download bars for stop loss checking (once, used by all patterns)
        # Timeframe is configurable via BACKTEST_STOP_CHECK_TIMEFRAME (default: 1m)
        stop_check_tf = getattr(config, 'BACKTEST_STOP_CHECK_TIMEFRAME', '1m')
        df_stop_bars = _download_stop_check_bars(ib, contract, start_dt, end_dt, stop_check_tf)

        # =====================================================================
        # DYNAMIC DEMAND ZONE DETECTION (if enabled)
        # =====================================================================
        if config.DEMAND_ZONE_TRADING and detect_zones_dynamically:
            zone_timeframes = getattr(config, 'ZONE_TIMEFRAMES', ["30m", "15m"])
            logger.info(f"=== Detecting Demand Zones on {zone_timeframes} ===")

            # Create a single analysis engine instance for zone detection
            zone_analysis_engine = AnalysisEngine()

            # Download and process bars for each zone timeframe
            for zone_tf in zone_timeframes:
                logger.info(f"--- Zone Detection: {zone_tf} ---")

                # Download bars with session alignment support
                df_zone_bars = _download_bars_with_session_alignment(
                    ib, contract, start_dt, end_dt, zone_tf
                )

                if df_zone_bars.empty:
                    logger.warning(f"No {zone_tf} bars for zone detection. Skipping.")
                    continue

                # Detect zones from these bars
                zones = _detect_demand_zones_from_bars(df_zone_bars, zone_tf, zone_analysis_engine)
                all_detected_zones.extend(zones)

            # Use detected zones instead of loaded zones
            loaded_zones = all_detected_zones
            logger.info(f"=== Total Detected Zones: {len(loaded_zones)} ===")

        # =====================================================================
        # PATTERN DETECTION LOOP
        # =====================================================================
        for timeframe in config.PATTERN_TIMEFRAMES:
            logger.info(f"--- Processing timeframe: {timeframe} ---")

            # Calculate buffer period needed for pre-filling candle history
            # Add 1 extra day before start_dt to pre-fill the lookback buffer
            buffer_start_dt = start_dt - timedelta(days=1)

            # Download bars with session alignment support
            # This handles both minute and hourly timeframes automatically
            total_days = (end_dt - start_dt).days + 1
            logger.info(f"Downloading {total_days} days of {timeframe} bars + 1 day buffer...")

            df = _download_bars_with_session_alignment(ib, contract, buffer_start_dt, end_dt, timeframe)

            if df.empty:
                logger.error(f"Could not download historical data for {timeframe}. Skipping.")
                continue

            # Separate buffer bars from pattern detection bars
            # Handle timezone-aware vs naive datetime comparison
            if df['date'].dt.tz is not None:
                start_dt_utc = pd.to_datetime(start_dt).tz_localize('UTC')
                buffer_start_utc = pd.to_datetime(buffer_start_dt).tz_localize('UTC')
            else:
                start_dt_utc = pd.to_datetime(start_dt)
                buffer_start_utc = pd.to_datetime(buffer_start_dt)

            # Filter to buffer period
            df = df[df['date'] >= buffer_start_utc]
            buffer_bars = df[df['date'] < start_dt_utc]
            detection_bars = df[df['date'] >= start_dt_utc]

            logger.info(f"Downloaded {len(df)} bars for {timeframe} (buffer: {len(buffer_bars)}, detection: {len(detection_bars)}).")

            # Dynamic candle buffer based on pattern requirements
            candle_history = deque(maxlen=candle_count)
            found_patterns = {p: 0 for p in active_patterns}

            # Signal reset tracking per pattern (for Smart Reversal)
            waiting_for_reset = {p: False for p in active_patterns}
            bearish_count_since_signal = {p: 0 for p in active_patterns}

            # Track last trade bar to prevent duplicates when running both patterns
            last_trade_bar = None

            # Pre-fill candle history with buffer bars (if available)
            for _, bar in buffer_bars.iterrows():
                bar_series = pd.Series(bar, name=bar['date'])
                candle_history.append(bar_series)

            if len(buffer_bars) > 0:
                logger.info(f"Pre-filled candle history with {len(candle_history)} buffer bars from previous day.")
            else:
                logger.info(f"No buffer data available (market open start). First {candle_count-1} bars will be used for buffer filling.")

            patterns_str = " + ".join(active_patterns)
            logger.info(f"Starting {patterns_str} pattern detection for {timeframe}...")

            # Only iterate over detection bars (patterns already pre-filled from buffer)
            for index, bar in detection_bars.iterrows():
                bar_series = pd.Series(bar, name=bar['date'])
                candle_history.append(bar_series)
                current_bar_time = str(bar['date'])

                # Check for signal reset condition (6_candle only)
                if "6_candle" in active_patterns and waiting_for_reset["6_candle"] and config.SMART_REVERSAL_REQUIRE_RESET:
                    if bar['close'] < bar['open']:
                        bearish_count_since_signal["6_candle"] += 1
                        if bearish_count_since_signal["6_candle"] >= config.SMART_REVERSAL_RESET_CANDLES:
                            waiting_for_reset["6_candle"] = False
                            bearish_count_since_signal["6_candle"] = 0
                            logger.debug(f"6_candle signal reset at {_format_timestamp(bar['date'])}")

                if len(candle_history) < candle_count:
                    continue

                candles = list(candle_history)

                # Zone filtering (if enabled)
                zone_id = "N/A"
                if config.DEMAND_ZONE_TRADING and loaded_zones:
                    in_zone = False
                    for zone in loaded_zones:
                        zone_top = zone['zone_top']
                        zone_bottom = zone['zone_bottom']
                        entry_candle = candles[-1]
                        if (zone_bottom <= entry_candle['low'] <= zone_top or
                            zone_bottom <= entry_candle['high'] <= zone_top or
                            zone_bottom <= entry_candle['open'] <= zone_top or
                            zone_bottom <= entry_candle['close'] <= zone_top):
                            in_zone = True
                            zone_id = zone.get('id', 'unknown')
                            break
                    if not in_zone:
                        continue

                # Process each active pattern
                for pattern_name in active_patterns:
                    # Skip if trade already executed on this bar (duplicate prevention)
                    if last_trade_bar == current_bar_time:
                        continue

                    # Skip if waiting for reset (6_candle only)
                    if pattern_name == "6_candle" and waiting_for_reset["6_candle"] and config.SMART_REVERSAL_REQUIRE_RESET:
                        continue

                    pattern_config = PATTERN_REGISTRY[pattern_name]
                    pattern_candle_count = pattern_config["candle_count"]
                    evaluate_func = pattern_config["evaluate_func"]

                    # Get candles needed for this pattern
                    pattern_candles = candles[-pattern_candle_count:]
                    if len(pattern_candles) < pattern_candle_count:
                        continue

                    pattern_passed, evaluation = evaluate_func(pattern_candles)

                    if pattern_passed:
                        found_patterns[pattern_name] += 1
                        entry_candle = pattern_candles[-1]
                        timestamp_str = _format_timestamp(entry_candle.name)

                        # Mark trade executed on this bar (prevent duplicate)
                        last_trade_bar = current_bar_time

                        # Build trade result for markdown output
                        trade_result = {
                            'timestamp': timestamp_str,
                            'symbol': backtest_symbol,
                            'timeframe': timeframe,
                            'pattern': 'Smart Reversal' if pattern_name == '6_candle' else '3-Candle',
                            'pattern_code': 'SM' if pattern_name == '6_candle' else '3C',
                            'entry_price': round(entry_candle['close'], 2),
                            'open': round(entry_candle['open'], 2),
                            'high': round(entry_candle['high'], 2),
                            'low': round(entry_candle['low'], 2),
                            'close': round(entry_candle['close'], 2),
                        }

                        if pattern_name == "6_candle":
                            waiting_for_reset["6_candle"] = True
                            bearish_count_since_signal["6_candle"] = 0
                            drop_pct = evaluation.get('drop_pct', 0) * 100
                            reclaim_pct = evaluation.get('reclaim_pct', 0) * 100
                            exhaustion_type = evaluation.get('exhaustion_type', 'base')

                            # Add pattern-specific details
                            trade_result['drop_pct'] = round(drop_pct, 2)
                            trade_result['reclaim_pct'] = round(reclaim_pct, 1)
                            trade_result['exhaustion_type'] = exhaustion_type
                            trade_result['details'] = f"Drop: {drop_pct:.2f}% | Reclaim: {reclaim_pct:.1f}% | Base: {exhaustion_type}"

                            logger.info(
                                f"\n✨✨✨✨✨✨✨✨ SMART REVERSAL (Backtest) ✨✨✨✨✨✨✨✨\n"
                                f"TRADE CONFIRMED on {timeframe} at {timestamp_str}. "
                                f"Drop: {drop_pct:.2f}% | Reclaim: {reclaim_pct:.1f}% | Base: {exhaustion_type} | "
                                f"Entry: {entry_candle['close']:.2f}"
                                f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                            )
                        elif pattern_name == "3_candle":
                            c2_patterns = evaluation.get('c2_pattern', [])
                            c2_pattern_str = ','.join(c2_patterns) if c2_patterns else 'indecision'

                            # Add pattern-specific details
                            trade_result['c2_pattern'] = c2_pattern_str
                            trade_result['details'] = f"C1=bearish, C2={c2_pattern_str}, C3=bullish"

                            logger.info(
                                f"\n✨✨✨✨✨✨✨✨ TRADE CONFIRMED (3-Candle Backtest) ✨✨✨✨✨✨✨✨\n"
                                f"TRADE CONFIRMED on {timeframe} at {timestamp_str}. "
                                f"Pattern: C1=strong bearish, C2={c2_pattern_str}, C3=strong bullish entry. "
                                f"Entry price: {entry_candle['close']:.2f}"
                                f"\n✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨✨"
                            )

                        # ==========================================================
                        # STOP LOSS CHECK - Calculate swing low/high and check support
                        # ==========================================================
                        # Calculate swing low and swing high from lookback candles
                        lookback_count = getattr(config, 'SPY_SWING_LOW_CANDLES', 15)
                        lookback_candles = candles[-lookback_count:] if len(candles) >= lookback_count else candles
                        swing_low = min(c['low'] for c in lookback_candles)
                        swing_high = max(c['high'] for c in lookback_candles)

                        # Check WIN/LOSS using stop check bars (config: BACKTEST_STOP_CHECK_TIMEFRAME, BACKTEST_STOP_CHECK_BARS)
                        status, lowest_price, break_time = _check_stop_loss(
                            entry_timestamp=entry_candle.name,
                            entry_price=entry_candle['close'],
                            swing_low=swing_low,
                            df_stop_bars=df_stop_bars
                        )

                        # Add stop loss results to trade_result
                        trade_result['swing_high'] = round(swing_high, 2)
                        trade_result['swing_low'] = round(swing_low, 2)
                        trade_result['status'] = status
                        trade_result['lowest_price'] = round(lowest_price, 2) if lowest_price != float('inf') else 0.0
                        trade_result['break_time'] = break_time

                        # Log the stop loss check result
                        if status == 'LOSS':
                            logger.warning(
                                f"   ❌ STOP LOSS: Support broken! Swing low: ${swing_low:.2f} | "
                                f"Lowest: ${lowest_price:.2f} | Break time: {break_time}"
                            )
                        elif status == 'WIN':
                            logger.info(
                                f"   ✅ SUPPORT HELD: Swing low: ${swing_low:.2f} | "
                                f"Lowest: ${lowest_price:.2f} | Status: WIN"
                            )
                        else:
                            logger.warning(f"   ⚠️ UNKNOWN: Could not determine stop loss result")

                        # Add to results collection
                        trade_results.append(trade_result)

            # Log results per pattern
            for pattern_name in active_patterns:
                logger.info(f"Timeframe {timeframe} - {pattern_name}: Found {found_patterns[pattern_name]} patterns")
            total_patterns_found += sum(found_patterns.values())

        logger.info(f"=== Backtest Complete ===")
        logger.info(f"Total patterns found across all timeframes: {total_patterns_found}")

        # Write results to file (auto-detect format by extension)
        if output_file.endswith('.html'):
            _write_results_html(trade_results, start_date_str, end_date_str, mode, backtest_symbol, output_file)
        else:
            _write_results_markdown(trade_results, start_date_str, end_date_str, mode, backtest_symbol, output_file)

    except Exception as e:
        logger.error(f"An error occurred during the backtest: {e}", exc_info=True)
    finally:
        if ib.isConnected():
            ib.disconnect()
            logger.info("Disconnected from IB.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a backtest for candlestick pattern detection.")
    parser.add_argument("--start-date", required=True, help="Start date for backtest (YYYY-MM-DD).")
    parser.add_argument("--end-date", required=True, help="End date for backtest (YYYY-MM-DD).")
    pattern_choices = list(PATTERN_REGISTRY.keys()) + ["both"]
    parser.add_argument("--pattern", choices=pattern_choices,
                        help=f"Override PATTERN_MODE. Options: {pattern_choices}")
    parser.add_argument("--symbol", default=None,
                        help=f"Symbol to backtest (default: {config.SYMBOL})")
    parser.add_argument("--output", default="backtest_results.md",
                        help="Output markdown file (default: backtest_results.md)")

    args = parser.parse_args()

    try:
        datetime.strptime(args.start_date, '%Y-%m-%d')
        datetime.strptime(args.end_date, '%Y-%m-%d')
    except ValueError:
        print("Error: Dates must be in YYYY-MM-DD format.")
        exit(1)

    run_pattern_backtest(
        start_date_str=args.start_date,
        end_date_str=args.end_date,
        pattern_mode=args.pattern,
        symbol=args.symbol,
        output_file=args.output
    )
