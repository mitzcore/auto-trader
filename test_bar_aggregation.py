#!/usr/bin/env python3
"""
Test script to verify session-aligned bar aggregation.

This script fetches 30m bars from IBKR and aggregates them into 1h session-aligned bars,
then compares the timestamps to show the difference between clock-aligned and session-aligned.

Usage:
    python test_bar_aggregation.py
"""

from ib_insync import IB, Stock
import pandas as pd
from datetime import datetime
import pytz

from algotrade.util import (
    aggregate_bars_to_session_aligned,
    map_timeframe_to_ibkr,
    needs_session_alignment,
    MARKET_OPEN_TIME,
)


def test_aggregation():
    """Test bar aggregation by comparing IBKR 1h bars vs aggregated 30m->1h bars."""

    ib = IB()
    print("Connecting to IB...")
    ib.connect('127.0.0.1', 7497, clientId=998)

    spy = Stock('SPY', 'SMART', 'USD')
    ib.qualifyContracts(spy)

    # Fetch 1 day of data
    end_date = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y%m%d 16:00:00') + ' US/Eastern'

    print("\n" + "="*80)
    print("COMPARISON: IBKR Clock-Aligned vs Session-Aligned Bars")
    print("="*80)

    # 1. Fetch raw 1h bars from IBKR (clock-aligned)
    print("\n[1] Fetching 1h bars directly from IBKR (clock-aligned)...")
    bars_1h_raw = ib.reqHistoricalData(
        spy,
        endDateTime=end_date,
        durationStr='1 D',
        barSizeSetting='1 hour',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )

    print(f"    Got {len(bars_1h_raw)} bars")
    print("\n    IBKR 1h Bars (Clock-Aligned):")
    print("    " + "-"*70)
    print(f"    {'Time':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10}")
    print("    " + "-"*70)
    for bar in bars_1h_raw[-6:]:  # Show last 6 bars
        time_str = bar.date.strftime('%Y-%m-%d %H:%M') if hasattr(bar.date, 'strftime') else str(bar.date)
        print(f"    {time_str:<20} {bar.open:>10.2f} {bar.high:>10.2f} {bar.low:>10.2f} {bar.close:>10.2f}")

    # 2. Fetch 30m bars and aggregate to session-aligned 1h
    print("\n[2] Fetching 30m bars and aggregating to session-aligned 1h...")
    bars_30m = ib.reqHistoricalData(
        spy,
        endDateTime=end_date,
        durationStr='1 D',
        barSizeSetting='30 mins',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )

    print(f"    Got {len(bars_30m)} x 30m bars")

    # Aggregate to 1h session-aligned
    df_1h_aligned = aggregate_bars_to_session_aligned(bars_30m, "30m", "1h")

    print(f"    Aggregated to {len(df_1h_aligned)} x 1h bars")
    print("\n    Session-Aligned 1h Bars (from 30m aggregation):")
    print("    " + "-"*70)
    print(f"    {'Time':<20} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10}")
    print("    " + "-"*70)
    for _, row in df_1h_aligned.tail(6).iterrows():  # Show last 6 bars
        time_str = row['datetime'].strftime('%Y-%m-%d %H:%M')
        print(f"    {time_str:<20} {row['open']:>10.2f} {row['high']:>10.2f} {row['low']:>10.2f} {row['close']:>10.2f}")

    # 3. Highlight the difference
    print("\n" + "="*80)
    print("KEY DIFFERENCE:")
    print("="*80)
    print("""
    IBKR Clock-Aligned:     10:00, 11:00, 12:00, 13:00, 14:00, 15:00
    Session-Aligned:        09:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30

    Notice how session-aligned bars start at market open (9:30 AM) and
    continue in 1-hour increments from there, matching TradingView.

    The first IBKR bar (9:30-10:00) is only 30 minutes long, while
    session-aligned bars are full 60-minute bars starting from 9:30.
    """)

    # 4. Test other timeframes
    print("\n" + "="*80)
    print("TESTING OTHER TIMEFRAMES:")
    print("="*80)

    for tf in ["30m", "1h", "2h", "4h"]:
        needs_align = needs_session_alignment(tf)
        print(f"    {tf:>4}: needs_session_alignment = {needs_align}")

    ib.disconnect()
    print("\nTest complete. IB disconnected.")


if __name__ == "__main__":
    test_aggregation()
