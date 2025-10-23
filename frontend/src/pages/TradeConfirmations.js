import React, { useState, useEffect } from 'react';
import { Table, Spinner, Alert } from 'react-bootstrap';

const TradeConfirmations = () => {
    const [confirmations, setConfirmations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchConfirmations = async () => {
            try {
                const response = await fetch('http://localhost:8000/trade-confirmations');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                setConfirmations(data);
            } catch (e) {
                setError(e.message);
            } finally {
                setLoading(false);
            }
        };

        fetchConfirmations();
    }, []);

    if (loading) {
        return <Spinner animation="border" />;
    }

    if (error) {
        return <Alert variant="danger">Error fetching data: {error}</Alert>;
    }

    return (
        <div>
            <h2>Trade Confirmations</h2>
            <Table striped bordered hover responsive>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Timestamp</th>
                        <th>Demand Zone ID</th>
                        <th>Timeframe</th>
                    </tr>
                </thead>
                <tbody>
                    {confirmations.length > 0 ? (
                        confirmations.map(conf => (
                            <tr key={conf.id}>
                                <td>{conf.id}</td>
                                <td>{new Date(conf.timestamp).toLocaleString()}</td>
                                <td>{conf.demand_zone_id}</td>
                                <td>{conf.timeframe}</td>
                            </tr>
                        ))
                    ) : (
                        <tr>
                            <td colSpan="4" className="text-center">No trade confirmations found.</td>
                        </tr>
                    )}
                </tbody>
            </Table>
        </div>
    );
};

export default TradeConfirmations;