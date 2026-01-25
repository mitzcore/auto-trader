
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from algotrade.database import (
    get_demand_zones,
    get_trade_confirmations,
    get_trades_placed,
    get_daily_stats,
    get_all_daily_stats,
    create_db_and_tables,
    manual_close_trade
)


class CloseTradeRequest(BaseModel):
    sell_price: float

# Create database and tables if they don't exist
create_db_and_tables()

app = FastAPI(
    title="AlgoTrade API",
    description="API for fetching trading bot data.",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"]  # Allows all methods
)

@app.get("/demand-zones", tags=["Data"], summary="Get all demand zones")
def read_demand_zones():
    """Endpoint to retrieve all logged demand zones."""
    return get_demand_zones()

@app.get("/trade-confirmations", tags=["Data"], summary="Get all trade confirmations")
def read_trade_confirmations():
    """Endpoint to retrieve all logged trade confirmations."""
    return get_trade_confirmations()

@app.get("/trades-placed", tags=["Data"], summary="Get all trades placed")
def read_trades_placed():
    """Endpoint to retrieve all logged placed trades."""
    return get_trades_placed()

@app.get("/daily-stats", tags=["Data"], summary="Get daily trade statistics")
def read_daily_stats(date: str = None):
    """
    Endpoint to retrieve daily trade statistics.

    Args:
        date: Optional date in YYYY-MM-DD format (default: today)

    Returns:
        Daily stats including win_count, loss_count, total_percentage, total_profit_loss
    """
    stats = get_daily_stats(date)
    if stats:
        return stats
    return {"message": "No trades recorded for this date", "trade_date": date}

@app.get("/daily-stats/all", tags=["Data"], summary="Get all daily trade statistics")
def read_all_daily_stats():
    """Endpoint to retrieve all daily trade statistics."""
    return get_all_daily_stats()


@app.put("/trade-confirmations/{trade_id}/close", tags=["Data"], summary="Manually close an OPEN trade")
def close_trade(trade_id: int, request: CloseTradeRequest):
    """
    Manually close an OPEN trade with a sell price.

    - Calculates P/L based on buy_price and sell_price
    - Updates trade status to Profit or Loss
    - Updates daily statistics

    Args:
        trade_id: The trade ID to close
        request: CloseTradeRequest with sell_price

    Returns:
        Updated trade details with calculated P/L
    """
    result = manual_close_trade(trade_id, request.sell_price)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


if __name__ == "__main__":
    uvicorn.run("api_service:app", host="0.0.0.0", port=8000, reload=True)
