import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function History() {
    const [profiles, setProfiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const navigate = useNavigate();

    useEffect(() => {
        fetch('/api/analytics/overview')
            .then(res => res.json())
            .then(data => {
                setProfiles(data.customer_profiles || []);
                setLoading(false);
            })
            .catch(e => {
                console.error(e);
                setLoading(false);
            });
    }, []);

    const formatCurrency = (n) => {
        return 'Rs. ' + Math.round(n).toLocaleString('en-IN');
    };

    return (
        <div className="dashboard">
            <div className="page-header">
                <div className="page-title">Flagged Customer History</div>
                <div className="page-subtitle">COMPREHENSIVE ACTIVITY LOG • {profiles.length} RECORDS</div>
            </div>

            <div className="table-card" style={{ background: 'white', borderRadius: '12px', border: '1px solid var(--light-red)', padding: '24px' }}>
                {loading ? (
                    <div>Loading history...</div>
                ) : (
                    <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                        <thead>
                            <tr style={{ borderBottom: '2px solid var(--light-red)', color: 'var(--text-dim)', fontSize: '11px', textTransform: 'uppercase', fontFamily: '"JetBrains Mono", monospace' }}>
                                <th style={{ padding: '12px 8px' }}>Name / ID</th>
                                <th>Bank</th>
                                <th>Location</th>
                                <th>Total Spent</th>
                                <th>Anomalies</th>
                                <th>Risk Score</th>
                                <th>Risk Level</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            {profiles.map(p => (
                                <tr
                                    key={p.customer_uuid}
                                    style={{ borderBottom: '1px solid #f1f1f1', cursor: 'pointer', transition: 'background 0.2s' }}
                                    onClick={() => navigate(`/customer_summary?cust_id=${p.customer_uuid}`)}
                                    onMouseOver={(e) => e.currentTarget.style.background = 'var(--light-red)'}
                                    onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                                >
                                    <td style={{ padding: '16px 8px' }}>
                                        <div style={{ fontWeight: 700, fontSize: '14px', color: 'var(--pri-red)' }}>{p.full_name}</div>
                                        <div style={{ fontSize: '11px', color: '#888', fontFamily: 'monospace' }}>{p.upi_id}</div>
                                    </td>
                                    <td style={{ fontSize: '13px' }}>{p.bank_name}</td>
                                    <td style={{ fontSize: '13px' }}>📍 {p.primary_location}</td>
                                    <td style={{ fontWeight: 600 }}>{formatCurrency(p.total_amount)}</td>
                                    <td style={{ fontWeight: 700, color: p.anomaly_count > 0 ? '#ef4444' : '#22c55e' }}>{p.anomaly_count}</td>
                                    <td>
                                        <div style={{ fontWeight: 700, fontSize: '13px' }}>{p.risk_score} / 10</div>
                                    </td>
                                    <td>
                                        <span style={{
                                            padding: '4px 8px', fontSize: '10px', fontWeight: 700, borderRadius: '4px',
                                            background: p.risk_level === 'CRITICAL' ? '#fef2f2' : p.risk_level === 'HIGH' ? '#fff7ed' : '#f0fdf4',
                                            color: p.risk_level === 'CRITICAL' ? '#ef4444' : p.risk_level === 'HIGH' ? '#f97316' : '#22c55e'
                                        }}>
                                            {p.risk_level}
                                        </span>
                                    </td>
                                    <td style={{ padding: '16px 8px' }}>
                                        <div style={{ display: 'flex', gap: '6px' }}>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); navigate(`/customer_summary?cust_id=${p.customer_uuid}`); }}
                                                style={{
                                                    display: 'inline-flex', alignItems: 'center', gap: '4px', background: 'var(--pri-red)', color: 'white',
                                                    border: 'none', borderRadius: '5px', padding: '6px 12px', fontSize: '11px', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
                                                    boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                                                }}
                                            >
                                                View
                                            </button>
                                            {p.risk_level === 'CRITICAL' && (
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        const confirmAlert = window.confirm(`Initiate critical response for ${p.full_name}?`);
                                                        if (confirmAlert) {
                                                            alert(`🚨 CRITICAL ALERT SENT: Secondary verification required for ${p.full_name}.`);
                                                        }
                                                    }}
                                                    style={{
                                                        display: 'inline-flex', alignItems: 'center', gap: '4px', background: '#000', color: '#fff',
                                                        border: 'none', borderRadius: '5px', padding: '6px 12px', fontSize: '11px', fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
                                                        animation: 'pulse 2s infinite'
                                                    }}
                                                >
                                                    🚨 Alert
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
