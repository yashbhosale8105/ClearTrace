import React from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Clock, Landmark, Shield } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import History from './pages/History';
import Investigate from './pages/Investigate';
import Chatbot from './pages/Chatbot';
import Cheques from './pages/Cheques';

function Sidebar() {
  const location = useLocation();
  const path = location.pathname;

  return (
    <div className="sidebar">
      <div className="nav-logo">
        <Shield size={24} />
      </div>

      <Link to="/chatbot" className={`nav-item ${path === '/chatbot' ? 'active' : ''}`} title="Chatbot">
        <MessageSquare size={20} />
      </Link>

      <Link to="/history" className={`nav-item ${path === '/history' ? 'active' : ''}`} title="History">
        <Clock size={20} />
      </Link>

      <Link to="/cheques" className={`nav-item ${path === '/cheques' ? 'active' : ''}`} title="Cheques">
        <Landmark size={20} />
      </Link>

      <Link to="/" className={`nav-item ${path === '/' ? 'active' : ''}`} title="Insights">
        <LayoutDashboard size={20} />
      </Link>
    </div>
  );
}

function Topbar() {
  return (
    <div className="topbar">
      <div className="topbar-brand">
        <div className="brand-title">CLEARTRACE</div>
        <div className="brand-sub">AI INVESTIGATION<br />SYSTEM</div>
      </div>
      <div className="topbar-right">
        <div className="status-indicator">
          <div className="status-dot"></div>
          SYSTEM<br />ONLINE
        </div>
        <div style={{ height: '30px', width: '1px', backgroundColor: '#eee', margin: '0 10px' }}></div>
        <div className="officer-info">
          Officer: <span className="officer-name">R. MEHTA</span>
          <div className="officer-avatar">R</div>
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div id="root">
        <Sidebar />
        <div className="main-content">
          <Topbar />
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chatbot" element={<Chatbot />} />
            <Route path="/history" element={<History />} />
            <Route path="/cheques" element={<Cheques />} />
            <Route path="/customer_summary" element={<Investigate />} />
            <Route path="*" element={<div style={{ padding: '40px' }}>Under Construction</div>} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
