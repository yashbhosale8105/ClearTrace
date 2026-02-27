import React, { useState, useRef, useEffect } from 'react';
import { Shield, Search, Flag, Users, FileText, Volume2, Send, User, Sparkles } from 'lucide-react';

export default function Chatbot() {
    const [messages, setMessages] = useState([
        {
            sender: 'bot',
            text: "Hi, I'm the ClearTrace AI Investigator. Whether it's verifying suspicious UPI patterns, mapping anomaly velocity, or analyzing fraudulent cheques, I'm here to curate your investigation workspace. What case are we looking into today?"
        }
    ]);
    const [input, setInput] = useState('');
    const [isTyping, setIsTyping] = useState(false);
    const chatEndRef = useRef(null);

    const scrollToBottom = () => {
        chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, isTyping]);

    const handleSend = async () => {
        const text = input.trim();
        if (!text) return;

        setMessages(prev => [...prev, { sender: 'user', text }]);
        setInput('');
        setIsTyping(true);

        try {
            const response = await fetch('/api/chatbot/query', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text })
            });

            const data = await response.json();
            setIsTyping(false);

            if (data.success && data.reply) {
                let botReply = data.reply;
                let formattedReply = botReply
                    .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
                    .replace(/^##\s+(.*$)/gm, '<h3 style="font-size: 16px; margin-top: 10px; color: #000;">$1</h3>')
                    .replace(/^###\s+(.*$)/gm, '<h3 style="font-size: 14px; margin-top: 10px; color: #000;">$1</h3>')
                    .replace(/^\*\s+(.*$)/gm, '<li style="margin-left: 20px;">$1</li>')
                    .replace(/^- \s+(.*$)/gm, '<li style="margin-left: 20px;">$1</li>')
                    .replace(/\n/g, '<br>');

                setMessages(prev => [...prev, { sender: 'bot', text: formattedReply, isHtml: true }]);
            } else {
                setMessages(prev => [...prev, { sender: 'bot', text: data.error || "No matching forensic data found." }]);
            }
        } catch (error) {
            console.error(error);
            setIsTyping(false);
            setMessages(prev => [...prev, { sender: 'bot', text: "Connection issue. Please check your backend server." }]);
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="dashboard" style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100%',
            padding: '24px',
            background: "url('https://images.unsplash.com/photo-1490481651871-ab68de25d43d?q=80&w=2070&auto=format&fit=crop') no-repeat center center/cover",
            position: 'relative',
            zIndex: 0
        }}>
            {/* Overlay */}
            <div style={{
                position: 'absolute',
                inset: 0,
                background: 'rgba(0, 0, 0, 0.4)',
                backdropFilter: 'blur(5px)',
                zIndex: -1
            }} />

            {/* Google Fonts Preload */}
            <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500&family=Playfair+Display:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet" />

            <div style={{
                width: '100%',
                maxWidth: '1000px',
                height: '85vh',
                background: 'rgba(255, 255, 255, 0.95)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '20px',
                boxShadow: '0 20px 50px rgba(0, 0, 0, 0.3)',
                display: 'flex',
                flexDirection: 'column',
                position: 'relative',
                backdropFilter: 'blur(10px)',
                overflow: 'hidden',
                fontFamily: "'Outfit', sans-serif"
            }}>
                {/* Header */}
                <div style={{
                    padding: '25px 20px',
                    textAlign: 'center',
                    borderBottom: '2px solid #000',
                    background: '#fff'
                }}>
                    <h1 style={{
                        fontFamily: "'Playfair Display', serif",
                        fontSize: '32px',
                        fontWeight: '400',
                        letterSpacing: '1px',
                        marginBottom: '5px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '10px'
                    }}>
                        <span style={{ fontSize: '36px' }}>✦</span> ClearTrace
                    </h1>
                    <p style={{
                        fontSize: '11px',
                        textTransform: 'uppercase',
                        letterSpacing: '2px',
                        fontWeight: '600',
                        opacity: 0.6
                    }}>AI Forensic Investigator</p>
                </div>

                {/* Quick Chips (Retained but styled for Lookify) */}
                <div style={{ display: 'flex', gap: '8px', padding: '12px 20px', backgroundColor: '#fff', flexWrap: 'wrap', borderBottom: '1px solid #eee' }}>
                    {['Investigate UPI', 'Flagged', 'Customers', 'PDF Report'].map((label, idx) => (
                        <button key={idx} onClick={() => setInput(`Analyze ${label}`)} style={{
                            padding: '4px 12px',
                            borderRadius: '4px',
                            border: '1px solid #000',
                            background: 'white',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            fontSize: '11px',
                            cursor: 'pointer',
                            textTransform: 'uppercase',
                            letterSpacing: '1px',
                            fontWeight: '500'
                        }}>
                            {idx === 0 && <Search size={12} />}
                            {idx === 1 && <Flag size={12} />}
                            {idx === 2 && <Users size={12} />}
                            {idx === 3 && <FileText size={12} />}
                            {label}
                        </button>
                    ))}
                </div>

                {/* Chat Area */}
                <div style={{
                    flex: 1,
                    padding: '25px',
                    overflowY: 'auto',
                    background: '#fff',
                    backgroundImage: 'linear-gradient(#e5e5e5 1px, transparent 1px), linear-gradient(90deg, #e5e5e5 1px, transparent 1px)',
                    backgroundSize: '40px 40px'
                }}>
                    {messages.map((msg, index) => (
                        <div key={index} style={{
                            display: 'flex',
                            alignItems: 'flex-end',
                            marginBottom: '20px',
                            justifyContent: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                            animation: 'slideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1)'
                        }}>
                            {msg.sender === 'bot' && (
                                <div style={{
                                    width: '32px',
                                    height: '32px',
                                    background: '#000',
                                    color: '#fff',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    borderRadius: '50%',
                                    marginRight: '12px',
                                    flexShrink: 0
                                }}>
                                    <Shield size={16} />
                                </div>
                            )}

                            <div style={{
                                maxWidth: '80%',
                                padding: '14px 18px',
                                fontSize: '14px',
                                lineHeight: '1.6',
                                position: 'relative',
                                background: msg.sender === 'user' ? '#000' : '#fff',
                                color: msg.sender === 'user' ? '#fff' : '#000',
                                border: msg.sender === 'bot' ? '1px solid #000' : 'none',
                                borderRadius: msg.sender === 'bot' ? '0 12px 12px 12px' : '12px 12px 0 12px',
                                boxShadow: msg.sender === 'bot' ? '4px 4px 0px rgba(0, 0, 0, 0.1)' : 'none'
                            }}>
                                {msg.isHtml ? (
                                    <div dangerouslySetInnerHTML={{ __html: msg.text }} />
                                ) : (
                                    <div>{msg.text}</div>
                                )}
                            </div>

                            {msg.sender === 'user' && (
                                <div style={{
                                    width: '32px',
                                    height: '32px',
                                    background: '#eee',
                                    color: '#666',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    borderRadius: '50%',
                                    marginLeft: '12px',
                                    flexShrink: 0
                                }}>
                                    <User size={16} />
                                </div>
                            )}
                        </div>
                    ))}

                    {/* Typing Indicator */}
                    {isTyping && (
                        <div style={{
                            padding: '10px 14px',
                            background: '#fff',
                            border: '1px solid #e0e0e0',
                            borderRadius: '0 12px 12px 12px',
                            marginLeft: '44px',
                            marginBottom: '20px',
                            width: 'fit-content',
                            display: 'flex',
                            gap: '4px'
                        }}>
                            <span style={{ width: '6px', height: '6px', background: '#000', borderRadius: '50%', animation: 'blink 1.4s infinite both' }}></span>
                            <span style={{ width: '6px', height: '6px', background: '#000', borderRadius: '50%', animation: 'blink 1.4s infinite both', animationDelay: '0.2s' }}></span>
                            <span style={{ width: '6px', height: '6px', background: '#000', borderRadius: '50%', animation: 'blink 1.4s infinite both', animationDelay: '0.4s' }}></span>
                        </div>
                    )}
                    <div ref={chatEndRef} />
                </div>

                {/* Input Area */}
                <div style={{
                    padding: '20px',
                    background: '#fff',
                    borderTop: '2px solid #000',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px'
                }}>
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyPress={handleKeyPress}
                        placeholder="Type a case query or forensic command..."
                        style={{
                            flex: 1,
                            padding: '15px',
                            border: 'none',
                            borderBottom: '2px solid #ccc',
                            fontFamily: 'inherit',
                            fontSize: '15px',
                            outline: 'none',
                            background: 'transparent',
                            transition: 'border-color 0.3s'
                        }}
                        onFocus={(e) => e.target.style.borderColor = '#000'}
                        onBlur={(e) => e.target.style.borderColor = '#ccc'}
                        disabled={isTyping}
                    />
                    <button
                        onClick={handleSend}
                        disabled={isTyping || !input.trim()}
                        className="send-btn"
                        style={{
                            background: '#000',
                            border: '1px solid #000',
                            width: '50px',
                            height: '50px',
                            borderRadius: '50%',
                            color: '#fff',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            transition: 'all 0.3s ease'
                        }}
                    >
                        <Send size={20} />
                    </button>
                </div>
            </div>

            <style>
                {`
                @keyframes slideIn {
                    from { opacity: 0; transform: translateY(20px); }
                    to { opacity: 1; transform: translateY(0); }
                }
                @keyframes blink {
                    0% { opacity: 0.2; }
                    20% { opacity: 1; }
                    100% { opacity: 0.2; }
                }
                .send-btn:hover {
                    background: #fff !important;
                    color: #000 !important;
                    transform: rotate(-45deg);
                }
                /* Custom Scrollbar */
                ::-webkit-scrollbar {
                    width: 6px;
                }
                ::-webkit-scrollbar-track {
                    background: transparent;
                }
                ::-webkit-scrollbar-thumb {
                    background: #ccc;
                    border-radius: 3px;
                }
                ::-webkit-scrollbar-thumb:hover {
                    background: #000;
                }
                `}
            </style>
        </div>
    );
}
