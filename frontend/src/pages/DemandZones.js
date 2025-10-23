import React, { useState, useEffect } from 'react';
import { Table, Spinner, Alert } from 'react-bootstrap';

const DemandZones = () => {
    const [zones, setZones] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchZones = async () => {
            try {
                const response = await fetch('http://localhost:8000/demand-zones');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                setZones(data);
            } catch (e) {
                setError(e.message);
            } finally {
                setLoading(false);
            }
        };

        fetchZones();
    }, []);

    if (loading) {
        return <Spinner animation="border" />;
    }

    if (error) {
        return <Alert variant="danger">Error fetching data: {error}</Alert>;
    }

    return (
        <div>
            <h2>Demand Zones</h2>
            <Table striped bordered hover responsive>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Timestamp</th>
                        <th>Timeframe</th>
                        <th>Top Price</th>
                        <th>Bottom Price</th>
                    </tr>
                </thead>
                <tbody>
                    {zones.length > 0 ? (
                        zones.map(zone => (
                            <tr key={zone.id}>
                                <td>{zone.id}</td>
                                <td>{new Date(zone.timestamp).toLocaleString()}</td>
                                <td>{zone.timeframe}</td>
                                <td>{zone.top_price.toFixed(2)}</td>
                                <td>{zone.bottom_price.toFixed(2)}</td>
                            </tr>
                        ))
                    ) : (
                        <tr>
                            <td colSpan="5" className="text-center">No demand zones found.</td>
                        </tr>
                    )}
                </tbody>
            </Table>
        </div>
    );
};

export default DemandZones;