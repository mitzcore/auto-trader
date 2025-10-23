import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Container, Row, Col } from 'react-bootstrap';
import Sidebar from './components/Sidebar';
import DemandZones from './pages/DemandZones';
import TradeConfirmations from './pages/TradeConfirmations';
import TradesPlaced from './pages/TradesPlaced';

function App() {
  return (
    <Router>
      <Container fluid>
        <Row>
          <Col md={2} className="p-0">
            <Sidebar />
          </Col>
          <Col md={10} style={{ padding: '20px' }}>
            <Routes>
              <Route path="/" element={<DemandZones />} />
              <Route path="/confirmations" element={<TradeConfirmations />} />
              <Route path="/trades" element={<TradesPlaced />} />
            </Routes>
          </Col>
        </Row>
      </Container>
    </Router>
  );
}

export default App;