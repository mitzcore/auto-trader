#!/usr/bin/env python3
"""Debug script to fetch and display candles around the missed reversal"""

from ib_insync import IB, Stock
import pandas as pd
from datetime import datetime

def fetch_candles():
    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=999)

    spy = Stock('SPY', 'SMART', 'USD')
    ib.qualifyContracts(spy)

    # Fetch 2m bars for Jan 7, 2026 around 10:00-10:30 AM
    bars = ib.reqHistoricalData(
        spy,
        endDateTime='20260107 10:30:00 US/Eastern',
        durationStr='1 D',
        barSizeSetting='2 mins',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1
    )

    # Convert to DataFrame
    data = []
    for bar in bars:
        data.append({
            'datetime': bar.date,
            'open': bar.open,
            'high': bar.high,
            'low': bar.low,
            'close': bar.close,
            'volume': bar.volume
        })

    df = pd.DataFrame(data)

    # Filter for 9:30 AM - 10:30 AM
    df['datetime'] = pd.to_datetime(df['datetime'])
    mask = (df['datetime'].dt.time >= pd.Timestamp('09:30').time()) & \
           (df['datetime'].dt.time <= pd.Timestamp('10:30').time())
    df_filtered = df[mask].copy()

    # Calculate body percentage
    df_filtered['body_pct'] = abs(df_filtered['close'] - df_filtered['open']) / \
                              (df_filtered['high'] - df_filtered['low'])
    df_filtered['body_pct'] = (df_filtered['body_pct'] * 100).round(1)

    # Mark bullish/bearish
    df_filtered['type'] = df_filtered.apply(
        lambda x: 'BULL' if x['close'] > x['open'] else 'BEAR',
        axis=1
    )

    print("\n" + "="*100)
    print("SPY 2m Candles - Jan 7, 2026 (9:30 AM - 10:30 AM)")
    print("="*100)
    print("Time         Open     High     Low      Close    Type   Body%   Drop from High  ")
    print("-"*100)

    # Track swing high
    swing_high = None
    swing_high_idx = None

    for idx, row in df_filtered.iterrows():
        time_str = row['datetime'].strftime('%H:%M')

        # Update swing high (look back 15 candles)
        lookback_start = max(0, len(df_filtered[:idx]) - 15)
        lookback_data = df_filtered.iloc[lookback_start:len(df_filtered[:idx])]

        if len(lookback_data) > 0:
            swing_high = lookback_data['high'].max()
            drop_from_high = ((swing_high - row['low']) / swing_high * 100)
            drop_str = "-{:.2f}%".format(drop_from_high)
        else:
            drop_str = "N/A"

        print("{:<12} {:<8.2f} {:<8.2f} {:<8.2f} {:<8.2f} {:<6} {:<7.1f}% {:<15}".format(
            time_str, row['open'], row['high'], row['low'], row['close'],
            row['type'], row['body_pct'], drop_str))

    print("="*100)

    ib.disconnect()

if __name__ == "__main__":
    fetch_candles()
