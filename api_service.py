
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from algotrade.database import (
    get_demand_zones,
    get_trade_confirmations,
    get_trades_placed,
    create_db_and_tables
)

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

if __name__ == "__main__":
    uvicorn.run("api_service:app", host="0.0.0.0", port=8000, reload=True)
