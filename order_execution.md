# Future Live Trading: OCO (Bracket) Order Implementation

This document outlines how to implement OCO (One-Cancels-Other) bracket orders with Interactive Brokers API for live trading.

## Overview

A bracket order consists of three orders:
1. **Parent Order** - The initial BUY order (market or limit)
2. **Take Profit Order** - SELL LIMIT at +15% from entry
3. **Stop Loss Order** - SELL STOP at -10% from entry

When one child order fills, the other is automatically cancelled.

## Current Paper Trading Logic

```
Buy Price: $1.00
├── Profit Target: $1.15 (+15%)
└── Stop Loss: $0.90 (-10%)

Monitor OPTIONS BID price every 5 seconds:
- If bid >= $1.15 → Log PROFIT, exit
- If bid <= $0.90 → Log LOSS, exit
```

## Live Trading Implementation

### Prerequisites

```python
from ib_insync import IB, Contract, MarketOrder, LimitOrder, StopOrder
```

### Code Implementation

```python
def place_bracket_order(ib: IB, option_contract: Contract, quantity: int, buy_price: float):
    """
    Places a bracket order with take profit (+15%) and stop loss (-10%).

    Args:
        ib: Connected IB instance
        option_contract: Qualified options contract
        quantity: Number of contracts
        buy_price: Expected entry price (for limit orders) or estimated price (for market orders)

    Returns:
        tuple: (parent_trade, take_profit_trade, stop_loss_trade)
    """

    # Calculate target prices
    profit_target = round(buy_price * 1.15, 2)  # +15%
    stop_loss_target = round(buy_price * 0.90, 2)  # -10%

    # Generate unique order IDs
    parent_id = ib.client.getReqId()

    # 1. Parent Order (BUY)
    parent_order = MarketOrder(
        action='BUY',
        totalQuantity=quantity,
        transmit=False  # Don't send yet, wait for children
    )
    parent_order.orderId = parent_id

    # 2. Take Profit Order (SELL LIMIT at +15%)
    take_profit_order = LimitOrder(
        action='SELL',
        totalQuantity=quantity,
        lmtPrice=profit_target,
        transmit=False  # Don't send yet
    )
    take_profit_order.orderId = ib.client.getReqId()
    take_profit_order.parentId = parent_id

    # 3. Stop Loss Order (SELL STOP at -10%)
    stop_loss_order = StopOrder(
        action='SELL',
        totalQuantity=quantity,
        stopPrice=stop_loss_target,
        transmit=True  # Transmit all orders now
    )
    stop_loss_order.orderId = ib.client.getReqId()
    stop_loss_order.parentId = parent_id

    # Place all orders
    parent_trade = ib.placeOrder(option_contract, parent_order)
    take_profit_trade = ib.placeOrder(option_contract, take_profit_order)
    stop_loss_trade = ib.placeOrder(option_contract, stop_loss_order)

    logging.info(
        f"Bracket order placed | "
        f"Parent ID: {parent_id} | "
        f"Take Profit: ${profit_target} (+15%) | "
        f"Stop Loss: ${stop_loss_target} (-10%)"
    )

    return parent_trade, take_profit_trade, stop_loss_trade
```

### Alternative: Limit Entry with Bracket

```python
def place_limit_bracket_order(ib: IB, option_contract: Contract, quantity: int, limit_price: float):
    """
    Places a LIMIT BUY with bracket orders.
    Use this when you want to enter at a specific price.
    """

    profit_target = round(limit_price * 1.15, 2)
    stop_loss_target = round(limit_price * 0.90, 2)

    parent_id = ib.client.getReqId()

    # Parent: LIMIT BUY
    parent_order = LimitOrder(
        action='BUY',
        totalQuantity=quantity,
        lmtPrice=limit_price,
        transmit=False
    )
    parent_order.orderId = parent_id

    # Take Profit: SELL LIMIT
    take_profit_order = LimitOrder(
        action='SELL',
        totalQuantity=quantity,
        lmtPrice=profit_target,
        transmit=False
    )
    take_profit_order.orderId = ib.client.getReqId()
    take_profit_order.parentId = parent_id

    # Stop Loss: SELL STOP
    stop_loss_order = StopOrder(
        action='SELL',
        totalQuantity=quantity,
        stopPrice=stop_loss_target,
        transmit=True
    )
    stop_loss_order.orderId = ib.client.getReqId()
    stop_loss_order.parentId = parent_id

    # Place orders
    ib.placeOrder(option_contract, parent_order)
    ib.placeOrder(option_contract, take_profit_order)
    ib.placeOrder(option_contract, stop_loss_order)

    return parent_id
```

## Integration with Existing Code

### Modify `LiveExecutionHandler` in `execution.py`

```python
class LiveExecutionHandler(ExecutionHandler):
    def __init__(self, ib):
        self.ib = ib

    def execute_order(self, order, bar=None):
        from .orders import place_bracket_order, get_option_contract

        if not config.TRADE_ORDERS:
            logging.warning("Order execution is DISABLED. Skipping trade.")
            return

        spy_price = order.get('price')
        quantity = order.get('quantity', 1)

        # Get qualified option contract
        option_contract, ask_price = get_option_contract(self.ib, spy_price)

        if option_contract and ask_price:
            # Place bracket order
            parent, tp, sl = place_bracket_order(
                self.ib,
                option_contract,
                quantity,
                ask_price
            )

            # Log to database
            log_trade_confirmation(
                demand_zone_id=order['zone']['id'],
                timeframe=order['zone']['zone_timeframe'],
                strike_price=option_contract.strike,
                buy_price=ask_price,
                status='OPEN'
            )

            logging.info(f"Live bracket order placed: {option_contract.localSymbol}")
        else:
            logging.error("Failed to get option contract. Order not placed.")
```

## Order States & Monitoring

### Order Status Values

| Status | Description |
|--------|-------------|
| `PendingSubmit` | Order sent, awaiting confirmation |
| `Submitted` | Order accepted by exchange |
| `Filled` | Order completely filled |
| `Cancelled` | Order cancelled |
| `Inactive` | Parent not yet filled, children waiting |

### Monitoring Fill Status

```python
def monitor_bracket_order(ib: IB, parent_trade, take_profit_trade, stop_loss_trade):
    """
    Monitors bracket order until one child fills.
    """
    while True:
        ib.sleep(1)

        # Check if take profit filled
        if take_profit_trade.orderStatus.status == 'Filled':
            fill_price = take_profit_trade.orderStatus.avgFillPrice
            logging.info(f"✅ PROFIT TARGET FILLED at ${fill_price}")
            return 'Profit', fill_price

        # Check if stop loss filled
        if stop_loss_trade.orderStatus.status == 'Filled':
            fill_price = stop_loss_trade.orderStatus.avgFillPrice
            logging.warning(f"❌ STOP LOSS FILLED at ${fill_price}")
            return 'Loss', fill_price

        # Check if parent was cancelled/rejected
        if parent_trade.orderStatus.status in ['Cancelled', 'Inactive']:
            logging.error("Parent order cancelled or inactive")
            return 'Cancelled', None
```

## Configuration Changes

Add to `config.py`:

```python
# Live Trading Settings
TRADE_ORDERS = True  # Enable live order placement
PROFIT_TARGET_PCT = 0.15  # +15%
STOP_LOSS_PCT = 0.10  # -10%

# Order Type
USE_MARKET_ORDER = True  # False for limit orders
LIMIT_OFFSET = 0.05  # Offset from ask for limit orders
```

## Risk Management Notes

1. **Slippage**: Market orders may fill at different prices than expected
2. **Partial Fills**: Options may have low liquidity, causing partial fills
3. **Gap Risk**: Price may gap through stop loss in fast markets
4. **0DTE Risk**: Same-day expiry options can move very fast

## Testing Checklist

Before enabling live trading:

- [ ] Test with paper trading account first
- [ ] Verify bracket orders work in TWS manually
- [ ] Test order cancellation handling
- [ ] Test partial fill scenarios
- [ ] Verify database logging works correctly
- [ ] Test during market hours with live data
- [ ] Start with minimum quantity (1 contract)

## References

- [IBKR TWS API: Bracket Orders](https://interactivebrokers.github.io/tws-api/bracket_order.html)
- [IBKR TWS API: Order Types](https://interactivebrokers.github.io/tws-api/available_orders.html)
- [ib_insync Documentation](https://ib-insync.readthedocs.io/)
