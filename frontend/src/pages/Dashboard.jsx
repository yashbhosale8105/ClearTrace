import React, { useState, useEffect } from 'react';
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement } from 'chart.js';
import { Bar, Doughnut } from 'react-chartjs-2';
import { AlertCircle, TrendingUp, CheckCircle, Wallet } from 'lucide-react';

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend, ArcElement);

export default function Dashboard() {
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState({
        flagged_count: 0,
        critical_count: 0,
        fraud_confirmed: 0,
        total_at_risk_amount: 0,
        risk_distribution: { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
        anomaly_type_distribution: {}
    });

    useEffect(() => {
        fetch('/api/analytics/overview')
            .then(r => r.json())
            .then(data => {
                setStats({
                    flagged_count: data.kpis?.flagged_count || 0,
                    critical_count: data.kpis?.critical_count || 0,
                    fraud_confirmed: data.kpis?.fraud_confirmed || 0,
                    total_at_risk_amount: data.kpis?.total_at_risk_amount || 0,
                    risk_distribution: data.risk_distribution || { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 },
                    anomaly_type_distribution: data.anomaly_type_distribution || {}
                });
                setLoading(false);
            })
            .catch(e => {
                console.error('Failed to load stats:', e);
                setLoading(false);
            });
    }, []);

    if (loading) return <div style={{ padding: '40px' }}>Loading real-time data...</div>;

    // Formatting amount to India format
    const formatCurrency = (val) => {
        return new Intl.NumberFormat('en-IN', {
            style: 'currency',
            currency: 'INR',
            maximumFractionDigits: 0
        }).format(val);
    };

    return (
        <div className="dashboard" style={{ padding: '32px 40px', backgroundColor: '#fdfdfd' }}>
            <div className="kpi-row" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '24px', marginBottom: '32px' }}>

                {/* KPI 1: Flagged */}
                <div className="kpi-card" style={{ background: 'white', borderRadius: '16px', border: '1px solid #eee', padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px', boxShadow: '0 4px 20px rgba(0,0,0,0.03)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ padding: '8px', background: '#3b82f6', borderRadius: '10px', color: 'white', display: 'flex' }}><AlertCircle size={20} /></div>
                        <span style={{ fontSize: '13px', color: '#555', fontWeight: '500', letterSpacing: '0.3px' }}>Flagged Transactions</span>
                    </div>
                    <div style={{ fontSize: '42px', fontWeight: '700', color: '#111', fontFamily: "'Space Grotesk', sans-serif" }}>{stats.flagged_count}</div>
                </div>

                {/* KPI 2: Critical */}
                <div className="kpi-card" style={{ background: 'white', borderRadius: '16px', border: '1px solid #eee', padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px', boxShadow: '0 4px 20px rgba(0,0,0,0.03)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ padding: '8px', background: '#ef4444', borderRadius: '10px', color: 'white', display: 'flex' }}><TrendingUp size={20} /></div>
                        <span style={{ fontSize: '13px', color: '#555', fontWeight: '500', letterSpacing: '0.3px' }}>Critical Risk Cases</span>
                    </div>
                    <div style={{ fontSize: '42px', fontWeight: '700', color: '#111', fontFamily: "'Space Grotesk', sans-serif" }}>{stats.critical_count}</div>
                </div>

                {/* KPI 3: Confirmed */}
                <div className="kpi-card" style={{ background: 'white', borderRadius: '16px', border: '1px solid #eee', padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px', boxShadow: '0 4px 20px rgba(0,0,0,0.03)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ padding: '8px', background: '#f97316', borderRadius: '10px', color: 'white', display: 'flex' }}><CheckCircle size={20} /></div>
                        <span style={{ fontSize: '13px', color: '#555', fontWeight: '500', letterSpacing: '0.3px' }}>Fraud Confirmed</span>
                    </div>
                    <div style={{ fontSize: '42px', fontWeight: '700', color: '#111', fontFamily: "'Space Grotesk', sans-serif" }}>{stats.fraud_confirmed}</div>
                </div>

                {/* KPI 4: Amount */}
                <div className="kpi-card" style={{ background: 'white', borderRadius: '16px', border: '1px solid #eee', padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px', boxShadow: '0 4px 20px rgba(0,0,0,0.03)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ padding: '8px', background: '#f59e0b', borderRadius: '10px', color: 'white', display: 'flex' }}><Wallet size={20} /></div>
                        <span style={{ fontSize: '13px', color: '#555', fontWeight: '500', letterSpacing: '0.3px' }}>Total Amount at Risk</span>
                    </div>
                    <div style={{ fontSize: '42px', fontWeight: '700', color: '#111', fontFamily: "'Space Grotesk', sans-serif" }}>{formatCurrency(stats.total_at_risk_amount)}</div>
                </div>
            </div>

            <div className="chart-row" style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '24px' }}>

                {/* Chart 1: Anomaly Distribution */}
                <div className="chart-card" style={{ background: 'white', border: '1px solid #eee', borderRadius: '20px', padding: '32px', boxShadow: '0 4px 20px rgba(0,0,0,0.02)' }}>
                    <div style={{ marginBottom: '24px' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111', marginBottom: '8px' }}>Anomaly Type Distribution</h3>
                        <p style={{ fontSize: '13px', color: '#888' }}>Breakdown of detected fraud patterns</p>
                    </div>
                    <div style={{ height: '300px' }}>
                        <Bar
                            data={{
                                labels: Object.keys(stats.anomaly_type_distribution || {}).map(l => l.replace(/_/g, ' ')),
                                datasets: [{
                                    data: Object.values(stats.anomaly_type_distribution || {}),
                                    backgroundColor: '#2563eb',
                                    borderRadius: 4,
                                    barThickness: 30
                                }]
                            }}
                            options={{
                                responsive: true,
                                maintainAspectRatio: false,
                                plugins: { legend: { display: false } },
                                scales: {
                                    x: { grid: { display: false }, ticks: { font: { size: 10 }, color: '#666' } },
                                    y: { grid: { borderDash: [2, 2], color: '#eee' }, beginAtZero: true }
                                }
                            }}
                        />
                    </div>
                </div>

                {/* Chart 2: Risk Levels */}
                <div className="chart-card" style={{ background: 'white', border: '1px solid #eee', borderRadius: '20px', padding: '32px', boxShadow: '0 4px 20px rgba(0,0,0,0.02)' }}>
                    <div style={{ marginBottom: '24px' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#111', marginBottom: '8px' }}>Risk Level Distribution</h3>
                        <p style={{ fontSize: '13px', color: '#888' }}>Cases by severity classification</p>
                    </div>
                    <div style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Doughnut
                            data={{
                                labels: ['Critical', 'High', 'Medium', 'Low'],
                                datasets: [{
                                    data: [
                                        stats.risk_distribution.CRITICAL || 0,
                                        stats.risk_distribution.HIGH || 0,
                                        stats.risk_distribution.MEDIUM || 0,
                                        stats.risk_distribution.LOW || 0
                                    ],
                                    backgroundColor: ['#d01c1c', '#e67e22', '#f1c40f', '#2ecc71'],
                                    borderWidth: 0,
                                    hoverOffset: 4
                                }]
                            }}
                            options={{
                                responsive: true,
                                maintainAspectRatio: false,
                                cutout: '70%',
                                plugins: {
                                    legend: {
                                        position: 'right',
                                        labels: {
                                            usePointStyle: true,
                                            padding: 20,
                                            font: { size: 12, family: "'Space Grotesk', sans-serif" },
                                            generateLabels: (chart) => {
                                                const data = chart.data;
                                                return data.labels.map((label, i) => ({
                                                    text: `${label}: ${data.datasets[0].data[i]}`,
                                                    fillStyle: data.datasets[0].backgroundColor[i],
                                                    hidden: false,
                                                    index: i
                                                }));
                                            }
                                        }
                                    }
                                }
                            }}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}
