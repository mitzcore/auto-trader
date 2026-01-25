#!/usr/bin/env python3
"""
Risk/Reward Ratio Optimization Analysis
Analyzes historical trade data to find optimal stop loss and take profit levels.
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime

def analyze_trade_performance():
    """Analyze historical trade performance and R:R ratios."""

    conn = sqlite3.connect('trading_data.db')

    # Get all closed trades
    df = pd.read_sql_query("""
        SELECT
            profit_loss,
            buy_price,
            sell_price,
            quantity,
            percentage,
            pattern_type,
            entry_timestamp,
            exit_timestamp,
            timeframe
        FROM trade_confirmations
        WHERE exit_timestamp IS NOT NULL
        ORDER BY exit_timestamp DESC
    """, conn)

    conn.close()

    if len(df) == 0:
        print("No closed trades found in database.")
        return

    # Calculate metrics
    df['is_win'] = df['profit_loss'] > 0
    total_trades = len(df)
    wins = df['is_win'].sum()
    losses = total_trades - wins
    win_rate = (wins / total_trades) * 100

    avg_win = df[df['is_win']]['profit_loss'].mean()
    avg_loss = df[~df['is_win']]['profit_loss'].mean()
    avg_win_pct = df[df['is_win']]['percentage'].mean()
    avg_loss_pct = df[~df['is_win']]['percentage'].mean()

    total_pl = df['profit_loss'].sum()

    # Calculate actual R:R ratio
    rr_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else 0

    # Calculate expectancy
    expectancy = (win_rate/100 * avg_win) + ((100-win_rate)/100 * avg_loss)

    print("=" * 80)
    print("CURRENT PERFORMANCE ANALYSIS")
    print("=" * 80)
    print(f"Total Trades:      {total_trades}")
    print(f"Wins:              {wins} ({win_rate:.1f}%)")
    print(f"Losses:            {losses} ({100-win_rate:.1f}%)")
    print(f"Total P/L:         ${total_pl:.2f}")
    print()
    print(f"Average Win:       ${avg_win:.2f} ({avg_win_pct:.2f}%)")
    print(f"Average Loss:      ${avg_loss:.2f} ({avg_loss_pct:.2f}%)")
    print(f"Actual R:R Ratio:  1:{rr_ratio:.2f}")
    print(f"Expectancy/Trade:  ${expectancy:.2f}")
    print()

    # Percentage distribution analysis
    print("=" * 80)
    print("PROFIT/LOSS PERCENTAGE DISTRIBUTION")
    print("=" * 80)

    # What % of trades hit various profit levels?
    profit_levels = [2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20]
    print("\nProfit Target Analysis (% of wins that reached each level):")
    print("-" * 60)
    winning_trades = df[df['is_win']]['percentage']
    for level in profit_levels:
        pct_reached = (winning_trades >= level).sum() / len(winning_trades) * 100 if len(winning_trades) > 0 else 0
        print(f"  +{level:2d}%: {pct_reached:5.1f}% of wins reached this level")

    # What % of trades hit various loss levels?
    loss_levels = [2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20]
    print("\nStop Loss Analysis (% of losses that hit each level):")
    print("-" * 60)
    losing_trades = df[~df['is_win']]['percentage'].abs()
    for level in loss_levels:
        pct_hit = (losing_trades >= level).sum() / len(losing_trades) * 100 if len(losing_trades) > 0 else 0
        print(f"  -{level:2d}%: {pct_hit:5.1f}% of losses hit this level")

    # Pattern breakdown
    print()
    print("=" * 80)
    print("PERFORMANCE BY PATTERN TYPE")
    print("=" * 80)
    pattern_stats = df.groupby('pattern_type').agg({
        'profit_loss': ['count', 'sum', 'mean'],
        'is_win': 'sum'
    }).round(2)

    for pattern in df['pattern_type'].unique():
        pattern_df = df[df['pattern_type'] == pattern]
        if len(pattern_df) == 0:
            continue

        p_total = len(pattern_df)
        p_wins = pattern_df['is_win'].sum()
        p_win_rate = (p_wins / p_total) * 100
        p_total_pl = pattern_df['profit_loss'].sum()
        p_avg_win = pattern_df[pattern_df['is_win']]['profit_loss'].mean() if p_wins > 0 else 0
        p_avg_loss = pattern_df[~pattern_df['is_win']]['profit_loss'].mean() if p_total > p_wins else 0
        p_rr = p_avg_win / abs(p_avg_loss) if p_avg_loss != 0 else 0

        print(f"\n{pattern}:")
        print(f"  Trades: {p_total} | Wins: {p_wins} ({p_win_rate:.1f}%) | Total P/L: ${p_total_pl:.2f}")
        print(f"  Avg Win: ${p_avg_win:.2f} | Avg Loss: ${p_avg_loss:.2f} | R:R: 1:{p_rr:.2f}")

    return df


def simulate_rr_scenarios(df):
    """Simulate different R:R scenarios to find optimal settings."""

    print()
    print("=" * 80)
    print("R:R RATIO OPTIMIZATION SIMULATION")
    print("=" * 80)
    print("Testing different stop loss and take profit combinations...")
    print()

    # Define scenarios to test
    scenarios = [
        # (stop_loss_pct, take_profit_pct, name)
        (8, 8, "1:1 (8%/8%)"),
        (10, 10, "1:1 (10%/10%)"),
        (10, 15, "1:1.5 (10%/15%)"),
        (10, 20, "1:2 (10%/20%)"),
        (8, 12, "1:1.5 (8%/12%)"),
        (8, 16, "1:2 (8%/16%)"),
        (12, 18, "1:1.5 (12%/18%)"),
        (12, 24, "1:2 (12%/24%)"),
        (6, 12, "1:2 (6%/12%)"),
        (5, 10, "1:2 (5%/10%)"),
    ]

    results = []

    for stop_pct, target_pct, name in scenarios:
        # Simulate outcomes for each historical trade
        simulated_pl = []
        wins = 0

        for _, trade in df.iterrows():
            actual_pct = trade['percentage']
            actual_pl = trade['profit_loss']

            # Determine what would have happened with these levels
            if actual_pct >= target_pct:
                # Would have hit target
                simulated_result = target_pct
                wins += 1
            elif actual_pct <= -stop_pct:
                # Would have hit stop
                simulated_result = -stop_pct
            else:
                # Would have closed at actual level (0DTE expires)
                simulated_result = actual_pct
                if actual_pct > 0:
                    wins += 1

            # Convert percentage to dollar P/L
            # Approximate: use avg contract cost of $1000
            simulated_pl.append(simulated_result * 10)

        total_trades = len(simulated_pl)
        win_rate = (wins / total_trades) * 100
        total_pl = sum(simulated_pl)
        avg_pl = total_pl / total_trades

        # Subtract commission ($1.30 per trade)
        total_pl_net = total_pl - (total_trades * 1.30)
        avg_pl_net = total_pl_net / total_trades

        results.append({
            'name': name,
            'stop': stop_pct,
            'target': target_pct,
            'win_rate': win_rate,
            'total_pl': total_pl,
            'total_pl_net': total_pl_net,
            'avg_pl_net': avg_pl_net
        })

    # Sort by net P/L
    results = sorted(results, key=lambda x: x['total_pl_net'], reverse=True)

    print(f"{'Scenario':<20} {'Win Rate':<10} {'Total P/L':<12} {'Net P/L':<12} {'Avg/Trade':<10}")
    print("-" * 75)

    for r in results:
        print(f"{r['name']:<20} {r['win_rate']:>6.1f}%   ${r['total_pl']:>8.2f}   ${r['total_pl_net']:>8.2f}   ${r['avg_pl_net']:>6.2f}")

    print()
    print("Note: Net P/L includes $1.30 commission per trade")
    print()

    return results


def advanced_recommendations():
    """Provide advanced optimization recommendations."""

    print("=" * 80)
    print("ADVANCED OPTIMIZATION STRATEGIES")
    print("=" * 80)
    print()

    strategies = [
        ("1. Volatility-Adjusted Stops",
         "Use ATR (Average True Range) instead of fixed %. Wider stops in volatile markets, tighter in calm markets."),

        ("2. Time-Based Exits",
         "Close positions after 2-3 hours if not hit (manage theta decay on 0DTE). Prevents small losses from becoming big losses."),

        ("3. Partial Profit Taking",
         "Take 50% off at 1:1 (lock in win), let rest run to 1:2. Increases win rate while capturing big moves."),

        ("4. Break-Even Stops",
         "Move stop to entry +$0.50 once trade is up 4-5%. Converts potential losses into break-evens."),

        ("5. Pattern-Specific R:R",
         "Smart Reversal might need wider stops (stronger signal), 3-candle might need tighter (weaker signal)."),

        ("6. VIX-Based Adjustments",
         "VIX > 20: Use 1:1.5 ratio (choppy). VIX < 15: Use 1:2 ratio (trending). Adapt to market regime."),

        ("7. Price-Based Stops",
         "Stop below recent swing low instead of % (respects market structure). Prevents premature stops."),

        ("8. Trailing Stops",
         "Once up 5%, trail stop at 50% of gains. Locks in profits while letting winners run."),
    ]

    for title, description in strategies:
        print(f"{title}")
        print(f"  → {description}")
        print()


if __name__ == "__main__":
    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "RISK/REWARD OPTIMIZATION ANALYSIS" + " " * 25 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    # Analyze current performance
    df = analyze_trade_performance()

    if df is not None and len(df) > 0:
        # Simulate different scenarios
        results = simulate_rr_scenarios(df)

        # Show advanced strategies
        advanced_recommendations()

        # Final recommendation
        print("=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)
        best = results[0]
        print(f"\nBased on your historical data, the optimal settings appear to be:")
        print(f"  → {best['name']}")
        print(f"  → Expected win rate: {best['win_rate']:.1f}%")
        print(f"  → Expected profit: ${best['avg_pl_net']:.2f} per trade")
        print()
        print("However, consider implementing:")
        print("  1. Start with 1:1.5 ratio (10% SL / 15% TP) - good balance")
        print("  2. Add time-based exit after 2-3 hours to manage theta")
        print("  3. Test partial profit taking (50% at 1:1, rest at 1:1.5)")
        print("  4. Track performance weekly and adjust")
        print()
