import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import DemandZones from './pages/DemandZones';
import TradeConfirmations from './pages/TradeConfirmations';
import TradesPlaced from './pages/TradesPlaced';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app-container">
        <Sidebar />
        <main className="main-content" style={{ marginLeft: '240px' }}>
          <Routes>
            <Route path="/" element={<DemandZones />} />
            <Route path="/confirmations" element={<TradeConfirmations />} />
            <Route path="/trades" element={<TradesPlaced />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
