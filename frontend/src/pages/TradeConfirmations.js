import React, { useState, useEffect } from 'react';
import { Table, Spinner, Alert } from 'react-bootstrap';
import { formatInTimeZone } from 'date-fns-tz';

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

    const getRowClass = (status) => {
        switch (status) {
            case 'Profit':
                return 'table-success';
            case 'Loss':
                return 'table-danger';
            default:
                return '';
        }
    };

    const formatTimestamp = (isoString) => {
        if (!isoString) return '';
        try {
            // The backend provides a UTC string. We parse it and format it into the 'America/New_York' timezone.
            return formatInTimeZone(isoString, 'America/New_York', 'yyyy-MM-dd HH:mm:ss zzz');
        } catch (error) {
            console.error("Error formatting date:", error);
            return isoString; // Fallback to the original string
        }
    };

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
                        <th>Strike Price</th>
                        <th>Buy Price</th>
                        <th>Sell Price</th>
                        <th>Percentage</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {confirmations.length > 0 ? (
                        confirmations.map(conf => (
                            <tr key={conf.id} className={getRowClass(conf.status)}>
                                <td>{conf.id}</td>
                                <td>{formatTimestamp(conf.timestamp)}</td>
                                <td>{conf.demand_zone_id}</td>
                                <td>{conf.timeframe}</td>
                                <td>{conf.strike_price}</td>
                                <td>{conf.buy_price}</td>
                                <td>{conf.sell_price}</td>
                                <td>{conf.percentage !== null ? `${Math.floor(conf.percentage)}%` : ''}</td>
                                <td>{conf.status}</td>
                            </tr>
                        ))
                    ) : (
                        <tr>
                            <td colSpan="9" className="text-center">No trade confirmations found.</td>
                        </tr>
                    )}
                </tbody>
            </Table>
        </div>
    );
};

export default TradeConfirmations;