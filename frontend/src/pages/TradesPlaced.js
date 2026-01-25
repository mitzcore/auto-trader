import React, { useState, useEffect } from 'react';
import { Dropdown, Form } from 'react-bootstrap';
import '../App.css';

const ALL_COLUMNS = [
    { key: 'date', label: 'Date' },
    { key: 'total', label: 'Total Trades' },
    { key: 'wins', label: 'Wins' },
    { key: 'losses', label: 'Losses' },
    { key: 'winrate', label: 'Win Rate' },
    { key: 'pnl', label: 'P&L' },
    { key: 'percentage', label: 'Percentage' },
];

const DEFAULT_VISIBLE = ['date', 'total', 'wins', 'losses', 'winrate', 'pnl', 'percentage'];

const TradesPlaced = () => {
    const [stats, setStats] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [visibleColumns, setVisibleColumns] = useState(() => {
        const saved = localStorage.getItem('statsPageColumns');
        return saved ? JSON.parse(saved) : DEFAULT_VISIBLE;
    });

    const toggleColumn = (key) => {
        setVisibleColumns(prev => {
            const newColumns = prev.includes(key)
                ? prev.filter(k => k !== key)
                : [...prev, key];
            localStorage.setItem('statsPageColumns', JSON.stringify(newColumns));
            return newColumns;
        });
    };

    const isColumnVisible = (key) => visibleColumns.includes(key);

    useEffect(() => {
        const fetchStats = async () => {
            try {
                const response = await fetch('http://localhost:8000/daily-stats/all');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                setStats(data);
            } catch (e) {
                setError(e.message);
            } finally {
                setLoading(false);
            }
        };

        fetchStats();
    }, []);

    if (loading) {
        return (
            <div className="loading-container">
                <div className="modern-spinner"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="table-container" style={{ padding: '40px', textAlign: 'center' }}>
                <div style={{ color: 'var(--color-danger)', marginBottom: '8px', fontWeight: 600 }}>
                    Error loading data
                </div>
                <div style={{ color: 'var(--color-text-muted)', fontSize: '13px' }}>
                    {error}
                </div>
            </div>
        );
    }

    const getRowClass = (profitLoss) => {
        if (profitLoss > 0) return 'row-profit';
        if (profitLoss < 0) return 'row-loss';
        return '';
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return <span className="timestamp">-</span>;
        const date = new Date(dateStr);
        return (
            <span className="timestamp">
                {date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
            </span>
        );
    };

    const formatMoney = (value) => {
        if (value === null || value === undefined) return <span className="numeric">-</span>;
        const num = Number(value);
        const className = num >= 0 ? 'money-positive' : 'money-negative';
        const prefix = num >= 0 ? '+' : '';
        return <span className={`numeric ${className}`}>{prefix}${num.toFixed(2)}</span>;
    };

    const formatPercentage = (value) => {
        if (value === null || value === undefined) return <span className="numeric">-</span>;
        const num = Number(value);
        const className = num >= 0 ? 'money-positive' : 'money-negative';
        const prefix = num >= 0 ? '+' : '';
        return <span className={`numeric ${className}`}>{prefix}{num.toFixed(2)}%</span>;
    };

    const formatWinRate = (wins, losses) => {
        const total = wins + losses;
        if (total === 0) return <span className="numeric">-</span>;
        const rate = (wins / total) * 100;
        const className = rate >= 50 ? 'money-positive' : 'money-negative';
        return <span className={`numeric ${className}`}>{rate.toFixed(0)}%</span>;
    };

    // Calculate summary stats
    const totalTrades = stats.reduce((sum, s) => sum + s.win_count + s.loss_count, 0);
    const totalWins = stats.reduce((sum, s) => sum + s.win_count, 0);
    const totalLosses = stats.reduce((sum, s) => sum + s.loss_count, 0);
    const totalPnL = stats.reduce((sum, s) => sum + Number(s.total_profit_loss), 0);
    const overallWinRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0;

    return (
        <div>
            <div className="page-header">
                <h2 className="page-title">Daily Stats</h2>
                <Dropdown autoClose="outside" className="column-dropdown">
                    <Dropdown.Toggle variant="outline-secondary">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M12 3h7a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7" />
                            <path d="M8 12h8" />
                            <path d="M8 8h8" />
                            <path d="M8 16h8" />
                        </svg>
                        Columns ({visibleColumns.length}/{ALL_COLUMNS.length})
                    </Dropdown.Toggle>
                    <Dropdown.Menu>
                        {ALL_COLUMNS.map(col => (
                            <Dropdown.Item
                                key={col.key}
                                as="div"
                                onClick={(e) => e.stopPropagation()}
                            >
                                <Form.Check
                                    type="checkbox"
                                    id={`col-${col.key}`}
                                    label={col.label}
                                    checked={isColumnVisible(col.key)}
                                    onChange={() => toggleColumn(col.key)}
                                />
                            </Dropdown.Item>
                        ))}
                    </Dropdown.Menu>
                </Dropdown>
            </div>

            {/* Summary Cards */}
            <div className="stats-cards">
                <div className="stat-card">
                    <div className="stat-label">Total Trades</div>
                    <div className="stat-value">{totalTrades}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Wins</div>
                    <div className="stat-value stat-wins">{totalWins}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Losses</div>
                    <div className="stat-value stat-losses">{totalLosses}</div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Win Rate</div>
                    <div className={`stat-value ${overallWinRate >= 50 ? 'stat-wins' : 'stat-losses'}`}>
                        {overallWinRate.toFixed(0)}%
                    </div>
                </div>
                <div className="stat-card">
                    <div className="stat-label">Total P&L</div>
                    <div className={`stat-value ${totalPnL >= 0 ? 'stat-wins' : 'stat-losses'}`}>
                        {totalPnL >= 0 ? '+' : ''}${totalPnL.toFixed(2)}
                    </div>
                </div>
            </div>

            <div className="table-container">
                {stats.length > 0 ? (
                    <table className="modern-table">
                        <thead>
                            <tr>
                                {isColumnVisible('date') && <th>Date</th>}
                                {isColumnVisible('total') && <th>Trades</th>}
                                {isColumnVisible('wins') && <th>Wins</th>}
                                {isColumnVisible('losses') && <th>Losses</th>}
                                {isColumnVisible('winrate') && <th>Win Rate</th>}
                                {isColumnVisible('pnl') && <th>P&L</th>}
                                {isColumnVisible('percentage') && <th>%</th>}
                            </tr>
                        </thead>
                        <tbody>
                            {stats.map(stat => (
                                <tr key={stat.id} className={getRowClass(stat.total_profit_loss)}>
                                    {isColumnVisible('date') && <td>{formatDate(stat.trade_date)}</td>}
                                    {isColumnVisible('total') && <td className="numeric">{stat.win_count + stat.loss_count}</td>}
                                    {isColumnVisible('wins') && <td className="numeric">{stat.win_count}</td>}
                                    {isColumnVisible('losses') && <td className="numeric">{stat.loss_count}</td>}
                                    {isColumnVisible('winrate') && <td>{formatWinRate(stat.win_count, stat.loss_count)}</td>}
                                    {isColumnVisible('pnl') && <td>{formatMoney(stat.total_profit_loss)}</td>}
                                    {isColumnVisible('percentage') && <td>{formatPercentage(stat.total_percentage)}</td>}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className="empty-state">
                        <div className="empty-state-icon">📈</div>
                        <div className="empty-state-text">No stats found</div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default TradesPlaced;
