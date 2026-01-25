import React, { useState, useEffect, useCallback } from 'react';
import { Dropdown, Form } from 'react-bootstrap';
import '../App.css';

const ALL_COLUMNS = [
    { key: 'no', label: 'No' },
    { key: 'symbol', label: 'Symbol' },
    { key: 'triggered', label: 'Triggered @' },
    { key: 'entry', label: 'Entry' },
    { key: 'exit', label: 'Exit' },
    { key: 'timeframe', label: 'Timeframe' },
    { key: 'drop_pct', label: 'Drop %' },
    { key: 'reclaim_pct', label: 'Reclaim %' },
    { key: 'swing_high', label: 'Swing High' },
    { key: 'swing_low', label: 'Swing Low' },
    { key: 'strike', label: 'Strike Price' },
    { key: 'buy', label: 'Buy Price' },
    { key: 'sell', label: 'Sell Price' },
    { key: 'dollar', label: 'Dollar' },
    { key: 'percentage', label: 'Percentage' },
    { key: 'status', label: 'Status' },
];

const DEFAULT_VISIBLE = ['no', 'symbol', 'triggered', 'timeframe', 'drop_pct', 'reclaim_pct', 'swing_high', 'swing_low', 'buy', 'sell', 'dollar', 'percentage', 'status'];

const TradeConfirmations = () => {
    const [confirmations, setConfirmations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [visibleColumns, setVisibleColumns] = useState(() => {
        const saved = localStorage.getItem('tradeConfirmationsColumns');
        return saved ? JSON.parse(saved) : DEFAULT_VISIBLE;
    });

    // Edit state for OPEN trades
    const [editingId, setEditingId] = useState(null);
    const [sellPriceInput, setSellPriceInput] = useState('');
    const [saving, setSaving] = useState(false);

    const toggleColumn = (key) => {
        setVisibleColumns(prev => {
            const newColumns = prev.includes(key)
                ? prev.filter(k => k !== key)
                : [...prev, key];
            localStorage.setItem('tradeConfirmationsColumns', JSON.stringify(newColumns));
            return newColumns;
        });
    };

    const isColumnVisible = (key) => visibleColumns.includes(key);

    const fetchConfirmations = useCallback(async () => {
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
    }, []);

    useEffect(() => {
        fetchConfirmations();
    }, [fetchConfirmations]);

    const handleEditClick = (trade) => {
        setEditingId(trade.id);
        setSellPriceInput(trade.sell_price ? trade.sell_price.toString() : '');
    };

    const handleCancelEdit = () => {
        setEditingId(null);
        setSellPriceInput('');
    };

    const handleSaveSellPrice = async (tradeId) => {
        const sellPrice = parseFloat(sellPriceInput);
        if (isNaN(sellPrice) || sellPrice <= 0) {
            alert('Please enter a valid sell price');
            return;
        }

        setSaving(true);
        try {
            const response = await fetch(`http://localhost:8000/trade-confirmations/${tradeId}/close`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ sell_price: sellPrice }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to close trade');
            }

            // Refresh data after successful update
            await fetchConfirmations();
            setEditingId(null);
            setSellPriceInput('');
        } catch (e) {
            alert(`Error: ${e.message}`);
        } finally {
            setSaving(false);
        }
    };

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

    const getRowClass = (status) => {
        switch (status) {
            case 'Profit':
                return 'row-profit';
            case 'Loss':
                return 'row-loss';
            default:
                return '';
        }
    };

    const getStatusBadge = (status, tradeId, isEditing) => {
        if (status === 'OPEN') {
            if (isEditing) {
                return (
                    <div className="edit-actions">
                        <button
                            className="btn-save"
                            onClick={() => handleSaveSellPrice(tradeId)}
                            disabled={saving}
                        >
                            {saving ? '...' : 'Save'}
                        </button>
                        <button
                            className="btn-cancel"
                            onClick={handleCancelEdit}
                            disabled={saving}
                        >
                            X
                        </button>
                    </div>
                );
            }
            return (
                <span
                    className="status-badge pending editable"
                    onClick={() => handleEditClick(confirmations.find(c => c.id === tradeId))}
                    title="Click to close trade"
                >
                    OPEN
                </span>
            );
        }
        const statusClass = status === 'Profit' ? 'profit' : status === 'Loss' ? 'loss' : 'pending';
        return <span className={`status-badge ${statusClass}`}>{status || 'Pending'}</span>;
    };

    const formatTimestamp = (timestamp) => {
        if (!timestamp) return <span className="timestamp">-</span>;
        const date = new Date(timestamp);
        return (
            <span className="timestamp">
                {date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                {' '}
                {date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
            </span>
        );
    };

    const formatPrice = (price) => {
        if (price === null || price === undefined) return <span className="numeric">-</span>;
        return <span className="numeric">${Number(price).toFixed(2)}</span>;
    };

    const formatMoney = (value) => {
        if (value === null || value === undefined) return <span className="numeric">-</span>;
        const num = Number(value);
        const className = num >= 0 ? 'money-positive' : 'money-negative';
        return <span className={`numeric ${className}`}>${num.toFixed(2)}</span>;
    };

    const formatPercentage = (value) => {
        if (value === null || value === undefined) return <span className="numeric">-</span>;
        const num = Number(value);
        const className = num >= 0 ? 'money-positive' : 'money-negative';
        return <span className={`numeric ${className}`}>{num.toFixed(2)}%</span>;
    };

    const renderSellPrice = (conf) => {
        const isEditing = editingId === conf.id;

        if (conf.status === 'OPEN' && isEditing) {
            return (
                <div className="sell-price-edit">
                    <span className="currency-prefix">$</span>
                    <input
                        type="number"
                        step="0.01"
                        value={sellPriceInput}
                        onChange={(e) => setSellPriceInput(e.target.value)}
                        className="sell-price-input"
                        placeholder="0.00"
                        autoFocus
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') handleSaveSellPrice(conf.id);
                            if (e.key === 'Escape') handleCancelEdit();
                        }}
                    />
                </div>
            );
        }

        if (conf.status === 'OPEN') {
            return (
                <span
                    className="numeric editable-cell"
                    onClick={() => handleEditClick(conf)}
                    title="Click to enter sell price"
                >
                    -
                </span>
            );
        }

        return formatPrice(conf.sell_price);
    };

    return (
        <div>
            <div className="page-header">
                <h2 className="page-title">Trade History</h2>
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

            <div className="table-container">
                {confirmations.length > 0 ? (
                    <table className="modern-table">
                        <thead>
                            <tr>
                                {isColumnVisible('no') && <th>No</th>}
                                {isColumnVisible('symbol') && <th>Symbol</th>}
                                {isColumnVisible('triggered') && <th>Triggered</th>}
                                {isColumnVisible('entry') && <th>Entry</th>}
                                {isColumnVisible('exit') && <th>Exit</th>}
                                {isColumnVisible('timeframe') && <th>TF</th>}
                                {isColumnVisible('drop_pct') && <th>Drop %</th>}
                                {isColumnVisible('reclaim_pct') && <th>Reclaim %</th>}
                                {isColumnVisible('swing_high') && <th>Swing Hi</th>}
                                {isColumnVisible('swing_low') && <th>Swing Lo</th>}
                                {isColumnVisible('strike') && <th>Strike</th>}
                                {isColumnVisible('buy') && <th>Buy</th>}
                                {isColumnVisible('sell') && <th>Sell</th>}
                                {isColumnVisible('dollar') && <th>P/L</th>}
                                {isColumnVisible('percentage') && <th>%</th>}
                                {isColumnVisible('status') && <th>Status</th>}
                            </tr>
                        </thead>
                        <tbody>
                            {confirmations.map((conf, index) => (
                                <tr key={conf.id} className={getRowClass(conf.status)}>
                                    {isColumnVisible('no') && <td className="numeric">{index + 1}</td>}
                                    {isColumnVisible('symbol') && <td><span className="symbol-badge">{conf.symbol || 'SPY'}</span></td>}
                                    {isColumnVisible('triggered') && <td>{formatTimestamp(conf.alert_timestamp)}</td>}
                                    {isColumnVisible('entry') && <td>{formatTimestamp(conf.entry_timestamp)}</td>}
                                    {isColumnVisible('exit') && <td>{formatTimestamp(conf.exit_timestamp)}</td>}
                                    {isColumnVisible('timeframe') && <td><span className="numeric">{conf.timeframe}</span></td>}
                                    {isColumnVisible('drop_pct') && <td><span className="numeric">{conf.drop_pct != null ? `${Number(conf.drop_pct).toFixed(2)}%` : '-'}</span></td>}
                                    {isColumnVisible('reclaim_pct') && <td><span className="numeric">{conf.reclaim_pct != null ? `${Number(conf.reclaim_pct).toFixed(1)}%` : '-'}</span></td>}
                                    {isColumnVisible('swing_high') && <td>{formatPrice(conf.swing_high)}</td>}
                                    {isColumnVisible('swing_low') && <td>{formatPrice(conf.swing_low)}</td>}
                                    {isColumnVisible('strike') && <td>{formatPrice(conf.strike_price)}</td>}
                                    {isColumnVisible('buy') && <td>{formatPrice(conf.buy_price)}</td>}
                                    {isColumnVisible('sell') && <td>{renderSellPrice(conf)}</td>}
                                    {isColumnVisible('dollar') && <td>{formatMoney(conf.profit_loss)}</td>}
                                    {isColumnVisible('percentage') && <td>{formatPercentage(conf.percentage)}</td>}
                                    {isColumnVisible('status') && <td>{getStatusBadge(conf.status, conf.id, editingId === conf.id)}</td>}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <div className="empty-state">
                        <div className="empty-state-icon">📊</div>
                        <div className="empty-state-text">No trades found</div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default TradeConfirmations;
