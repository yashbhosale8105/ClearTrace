import React, { useState, useEffect } from 'react';
import { UploadCloud, ShieldCheck, FolderOpen, ScanLine, CheckCircle, FileCheck, AlertTriangle } from 'lucide-react';

export default function Cheques() {
    const [chequesList, setChequesList] = useState([]);
    const [analyzing, setAnalyzing] = useState(false);
    const [result, setResult] = useState(null);
    const [errorMsg, setErrorMsg] = useState(null);
    const [dragActive, setDragActive] = useState(false);

    useEffect(() => {
        fetch('/api/cheque/list')
            .then(r => r.json())
            .then(d => {
                if (d.cheques) setChequesList(d.cheques);
            })
            .catch(e => console.error("Error fetching cheques:", e));
    }, []);

    const handleUpload = async (file) => {
        if (!file) return;
        setAnalyzing(true);
        setErrorMsg(null);
        setResult(null);

        const fd = new FormData();
        fd.append('file', file);

        try {
            const res = await fetch('/api/cheque/analyze', { method: 'POST', body: fd });
            const data = await res.json();

            if (data.error) {
                setErrorMsg(data.error);
            } else {
                setResult(data);
            }
        } catch (e) {
            setErrorMsg('Upload failed. Connection error.');
        } finally {
            setAnalyzing(false);
        }
    };

    const analyzeFromList = async (filename) => {
        setAnalyzing(true);
        try {
            const r = await fetch(`/api/cheque/image/${filename}`);
            const b = await r.blob();
            handleUpload(new File([b], filename, { type: 'image/png' }));
        } catch (e) {
            setErrorMsg("Failed to load cheque image.");
            setAnalyzing(false);
        }
    };

    const onDragOver = (e) => { e.preventDefault(); setDragActive(true); };
    const onDragLeave = () => setDragActive(false);
    const onDrop = (e) => {
        e.preventDefault();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleUpload(e.dataTransfer.files[0]);
        }
    };

    const handleFileInput = (e) => {
        if (e.target.files && e.target.files[0]) {
            handleUpload(e.target.files[0]);
        }
    };

    return (
        <div className="dashboard">
            <div className="page-header" style={{ marginBottom: '24px' }}>
                <div className="page-title">Cheque Verification</div>
                <div className="page-subtitle">OCR FRAUD DETECTION DEPLOYMENT</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '24px' }}>

                {/* Upload Card */}
                <div style={{ background: 'white', border: '1px solid var(--light-red)', borderRadius: '12px', padding: '24px', display: 'flex', flexDirection: 'column' }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-dark)', marginBottom: '8px', fontSize: '16px', fontWeight: 600 }}>
                        <UploadCloud size={20} color="var(--pri-red)" /> Upload Cheque for Analysis
                    </h3>
                    <p style={{ fontSize: '12px', color: 'var(--text-dim)', marginBottom: '16px' }}>
                        Upload a cheque image to extract details via AI and validate against customer records.
                    </p>

                    <label
                        onDragOver={onDragOver}
                        onDragLeave={onDragLeave}
                        onDrop={onDrop}
                        style={{
                            flex: 1, border: `2px dashed ${dragActive ? 'var(--pri-red)' : '#ddd'}`,
                            borderRadius: '12px', display: 'flex', flexDirection: 'column',
                            alignItems: 'center', justifyContent: 'center', padding: '40px 20px',
                            cursor: 'pointer', backgroundColor: dragActive ? 'var(--light-red)' : '#faf9f9',
                            transition: 'all 0.2s', textAlign: 'center'
                        }}
                    >
                        <FileCheck size={40} color={dragActive ? "var(--pri-red)" : "#bbb"} style={{ marginBottom: '16px' }} />
                        <div style={{ fontWeight: 'bold', fontSize: '14px', marginBottom: '8px', color: 'var(--pri-red)' }}>
                            {analyzing ? 'Analyzing Image...' : 'Drop cheque image here or click'}
                        </div>
                        <div style={{ fontSize: '12px', color: '#888' }}>PNG, JPG supported</div>
                        <input type="file" accept="image/*" onChange={handleFileInput} style={{ display: 'none' }} disabled={analyzing} />
                    </label>
                </div>

                {/* Info Card */}
                <div style={{ background: 'white', border: '1px solid var(--light-red)', borderRadius: '12px', padding: '24px' }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-dark)', marginBottom: '12px', fontSize: '16px', fontWeight: 600 }}>
                        <ShieldCheck size={20} color="var(--pri-red)" /> System Capabilities
                    </h3>
                    <ul style={{ fontSize: '13px', color: 'var(--text-sec)', paddingLeft: '20px', lineHeight: '1.8', margin: 0 }}>
                        <li>Extract account number, IFSC, amount, date from cheque images</li>
                        <li>Cross-validate cheque data against customer records</li>
                        <li>Verify issuer name and account ownership</li>
                        <li>Check sufficiency of account balance</li>
                        <li>Correlate UPI transaction data across datasets</li>
                        <li>Identify inconsistencies between payment data and records</li>
                    </ul>

                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-dark)', marginTop: '24px', marginBottom: '12px', fontSize: '16px', fontWeight: 600 }}>
                        <FolderOpen size={20} color="var(--pri-red)" /> Available Records
                    </h3>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        {chequesList.length === 0 ? (
                            <div style={{ fontSize: '13px', color: 'var(--text-dim)' }}>No cheque validation queues pending at the moment.</div>
                        ) : (
                            chequesList.map((filename, i) => (
                                <img
                                    key={i}
                                    src={`/api/cheque/image/${filename}`}
                                    alt={filename}
                                    title={`Analyze: ${filename}`}
                                    onClick={() => !analyzing && analyzeFromList(filename)}
                                    style={{ height: '60px', borderRadius: '4px', border: '1px solid #eee', cursor: 'pointer', objectFit: 'cover', opacity: analyzing ? 0.5 : 1 }}
                                />
                            ))
                        )}
                    </div>
                </div>

                {/* Results Panels */}
                <div style={{ background: 'white', border: '1px solid var(--light-red)', borderRadius: '12px', padding: '24px', opacity: (result || errorMsg) ? 1 : 0.5 }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-dark)', marginBottom: '16px', fontSize: '16px', fontWeight: 600 }}>
                        <ScanLine size={20} color="var(--pri-red)" /> Extracted Data
                    </h3>

                    {errorMsg && (
                        <div>
                            <p style={{ color: 'var(--pri-red)', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', fontWeight: 600 }}><AlertTriangle size={16} /> {errorMsg}</p>
                            {errorMsg.includes('API key') && <p style={{ color: 'var(--text-dim)', fontSize: '12px', marginTop: '6px' }}>Set Gemini API key for cheque OCR.</p>}
                        </div>
                    )}

                    {!result && !errorMsg && <div style={{ fontSize: '13px', color: 'var(--text-dim)' }}>Waiting for active upload...</div>}

                    {result && result.extracted_data && (
                        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: '12px' }}>
                            {Object.entries(result.extracted_data).map(([k, v]) => (
                                <div key={k} style={{ padding: '8px 12px', background: '#faf9f9', borderRadius: '6px', fontSize: '13px' }}>
                                    <div style={{ color: 'var(--text-dim)', textTransform: 'uppercase', fontSize: '10px', fontWeight: 700, letterSpacing: '0.05em', marginBottom: '2px' }}>{k.replace(/_/g, ' ')}</div>
                                    <div style={{ fontWeight: 600 }}>{v}</div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                <div style={{ background: 'white', border: '1px solid var(--light-red)', borderRadius: '12px', padding: '24px', opacity: result ? 1 : 0.5 }}>
                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-dark)', marginBottom: '16px', fontSize: '16px', fontWeight: 600 }}>
                        <CheckCircle size={20} color="var(--pri-red)" /> Validation Results
                    </h3>
                    {!result && <div style={{ fontSize: '13px', color: 'var(--text-dim)' }}>Waiting for OCR extraction queue...</div>}

                    {result && result.validations && (
                        <div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
                                {result.validations.map((v, i) => {
                                    const isPass = v.status === 'PASS';
                                    const isFail = v.status === 'FAIL';
                                    return (
                                        <div key={i} style={{ display: 'flex', gap: '8px', padding: '10px 12px', border: '1px solid #eee', borderRadius: '6px', fontSize: '13px', background: isFail ? '#fef2f2' : 'transparent' }}>
                                            <div style={{ fontSize: '14px' }}>{isPass ? '✅' : isFail ? '❌' : '⚠️'}</div>
                                            <div>
                                                <span style={{ fontWeight: 600 }}>{v.check}:</span> {v.detail}
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>

                            {result.overall_status && (
                                <div style={{
                                    padding: '12px 16px', borderRadius: '8px', fontWeight: 600, fontSize: '14px', display: 'inline-flex', alignItems: 'center', gap: '8px',
                                    background: result.overall_status === 'PASS' ? '#f0fdf4' : '#fef2f2',
                                    color: result.overall_status === 'PASS' ? '#16a34a' : '#ef4444'
                                }}>
                                    {result.overall_status === 'PASS' ? '✅' : '❌'}
                                    OVERALL: {result.overall_status}
                                </div>
                            )}
                        </div>
                    )}
                </div>

            </div>
        </div>
    );
}
