import React, { useState, useEffect } from 'react';
import { Table, Spinner, Alert } from 'react-bootstrap';

const TradesPlaced = () => {
    const [trades, setTrades] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchTrades = async () => {
            try {
                const response = await fetch('http://localhost:8000/trades-placed');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                setTrades(data);
            } catch (e) {
                setError(e.message);
            } finally {
                setLoading(false);
            }
        };

        fetchTrades();
    }, []);

    if (loading) {
        return <Spinner animation="border" />;
    }

    if (error) {
        return <Alert variant="danger">Error fetching data: {error}</Alert>;
    }

    return (
        <div>
            <h2>Trades Placed</h2>
            <Table striped bordered hover responsive>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Timestamp</th>
                        <th>Demand Zone ID</th>
                        <th>Order Type</th>
                        <th>Price</th>
                        <th>Quantity</th>
                    </tr>
                </thead>
                <tbody>
                    {trades.length > 0 ? (
                        trades.map(trade => (
                            <tr key={trade.id}>
                                <td>{trade.id}</td>
                                <td>{new Date(trade.timestamp).toLocaleString()}</td>
                                <td>{trade.demand_zone_id}</td>
                                <td>{trade.order_type}</td>
                                <td>{trade.price.toFixed(2)}</td>
                                <td>{trade.quantity}</td>
                            </tr>
                        ))
                    ) : (
                        <tr>
                            <td colSpan="6" className="text-center">No trades placed found.</td>
                        </tr>
                    )}
                </tbody>
            </Table>
        </div>
    );
};

export default TradesPlaced;