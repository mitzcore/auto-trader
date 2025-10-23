import React from 'react';
import { Nav } from 'react-bootstrap';
import { Link } from 'react-router-dom';

const Sidebar = () => {
    return (
        <Nav className="d-none d-md-block bg-light sidebar" style={{ height: '100vh', padding: '20px' }}>
            <Nav.Item>
                <Nav.Link as={Link} to="/">Demand Zones</Nav.Link>
            </Nav.Item>
            <Nav.Item>
                <Nav.Link as={Link} to="/confirmations">Trade Confirmations</Nav.Link>
            </Nav.Item>
            <Nav.Item>
                <Nav.Link as={Link} to="/trades">Trades Placed</Nav.Link>
            </Nav.Item>
        </Nav>
    );
};

export default Sidebar;
