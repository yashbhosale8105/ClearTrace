"""
ClearTrace – Intelligent Investigation Assistant
Flask backend with GenAI, SQLite DB, email alerts, PDF reports, voice output, cheque OCR.
"""

import os
import io
import json
import base64
import hashlib
import sqlite3
import smtplib
from datetime import datetime, timedelta
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ── Email credentials ──
SENDER_EMAIL   = "cleartrace27@gmail.com"
APP_PASSWORD   = "ymyobapfzvugnpjo"

import pandas as pd
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS

# ── PDF ──
from fpdf import FPDF

# ── Voice ──
from gtts import gTTS

# ── GenAI ──
import google.generativeai as genai
from PIL import Image

# ══════════════════════════════════════════════════════════════
# App Setup
# ══════════════════════════════════════════════════════════════
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

REPORTS_DIR = Path("generated_reports")
REPORTS_DIR.mkdir(exist_ok=True)
VOICE_DIR = Path("generated_voice")
VOICE_DIR.mkdir(exist_ok=True)
DB_PATH = "cleartrace.db"

# ── Gemini Setup ──
GEMINI_API_KEY = None  # Set via environment or setkey command
gemini_model = None

def init_gemini(api_key=None):
    global GEMINI_API_KEY, gemini_model
    key = api_key or GEMINI_API_KEY
    if key:
        GEMINI_API_KEY = key
        genai.configure(api_key=key)
        
        print(f"  GenAI:               Auto-detecting available models...")
        try:
            # Get models that support content generation
            models = genai.list_models()
            available_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
            print(f"  GenAI:               Detected: {len(available_models)} models")
            
            # Prefer stable versions of Flash (good for OCR/Vision and fast)
            # Then Pro versions
            target_order = ["1.5-flash", "2.0-flash", "1.5-pro", "flash", "pro"]
            
            for target in target_order:
                for m_name in available_models:
                    if target in m_name.lower():
                        try:
                            test_model = genai.GenerativeModel(m_name)
                            # Basic check to see if we can at least initialize (doesn't trigger quota usually)
                            # We don't want to ping every model and waste limited quota
                            gemini_model = test_model
                            print(f"  GenAI:               ✓ Successfully bound to {m_name}")
                            return True
                        except Exception as e:
                            print(f"  GenAI:               ⚠️ Failed to bind to {m_name}: {str(e)[:50]}")
                            continue
            
            # Fallback to the first available if no target matches
            if available_models:
                gemini_model = genai.GenerativeModel(available_models[0])
                print(f"  GenAI:               ! Fallback bound to {available_models[0]}")
                return True
                
        except Exception as e:
            print(f"  GenAI:               ✗ Model discovery failed: {str(e)[:50]}")
            
        return False
    return False

init_gemini()

# ══════════════════════════════════════════════════════════════
# SQLite Database
# ══════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS investigations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            officer_name  TEXT    DEFAULT "Officer",
            customer_uuid TEXT,
            customer_name TEXT,
            customer_email TEXT,
            txn_id        TEXT,
            risk_level    TEXT,
            anomaly_count INTEGER,
            report_text   TEXT,
            pdf_path      TEXT,
            created_at    TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS email_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            investigation_id INTEGER,
            recipient_email TEXT,
            customer_name   TEXT,
            txn_id          TEXT,
            subject         TEXT,
            status          TEXT,
            error_message   TEXT,
            sent_at         TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def log_investigation(customer_uuid, customer_name, customer_email, txn_id,
                     risk_level, anomaly_count, report_text, pdf_path=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO investigations (customer_uuid,customer_name,customer_email,txn_id,risk_level,"
        "anomaly_count,report_text,pdf_path,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (customer_uuid, customer_name, customer_email, txn_id, risk_level,
         anomaly_count, report_text, pdf_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    inv_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return inv_id

def log_email(investigation_id, recipient, customer_name, txn_id, subject, status, error=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO email_logs (investigation_id,recipient_email,customer_name,txn_id,subject,status,error_message,sent_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (investigation_id, recipient, customer_name, txn_id, subject, status, error,
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

# ══════════════════════════════════════════════════════════════
# Data Loading
# ══════════════════════════════════════════════════════════════
import math

BASE = Path("dataset")

def sanitize_nan(obj):
    """Recursively replace float NaN / Inf with None so jsonify doesn't break."""
    if isinstance(obj, dict):
        return {k: sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_nan(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

def load_data():
    customers = pd.read_csv(BASE / "upi" / "upi_customers.csv")
    merchants = pd.read_csv(BASE / "upi" / "upi_merchants.csv")
    transactions = pd.read_csv(BASE / "upi" / "upi_transactions.csv")
    cheque_meta = None
    cheque_path = BASE / "cheques" / "cheque_metadata.csv"
    if cheque_path.exists():
        cheque_meta = pd.read_csv(cheque_path)
    return customers, merchants, transactions, cheque_meta

customers_df, merchants_df, transactions_df, cheques_df = load_data()


# ══════════════════════════════════════════════════════════════
# Anomaly Detection Engine
# ══════════════════════════════════════════════════════════════

def detect_anomalies(customer_uuid=None, upi_id=None):
    """Detect anomalies in transactions for a given customer."""
    global customers_df, transactions_df, merchants_df

    if upi_id:
        cust_row = customers_df[customers_df["upi_id"] == upi_id]
    elif customer_uuid:
        cust_row = customers_df[customers_df["customer_uuid"] == customer_uuid]
    else:
        return None, None, []

    if cust_row.empty:
        return None, None, []

    cust = cust_row.iloc[0].to_dict()
    cust_id = cust["customer_uuid"]

    # Get customer's transactions
    txns = transactions_df[transactions_df["customer_uuid"] == cust_id].copy()
    if txns.empty:
        return cust, [], []

    txn_list = txns.to_dict("records")
    anomalies = []

    for txn in txn_list:
        txn_anomalies = []

        # 1. Device mismatch
        if str(txn.get("customer_device_id","")) != str(cust.get("registered_device_id","")):
            txn_anomalies.append({
                "type": "DEVICE_MISMATCH",
                "severity": "HIGH",
                "detail": f"Transaction device '{txn['customer_device_id']}' differs from registered device '{cust['registered_device_id']}'"
            })

        # 2. IP mismatch
        if str(txn.get("customer_ip_address","")) != str(cust.get("registered_ip_address","")):
            txn_anomalies.append({
                "type": "IP_MISMATCH",
                "severity": "MEDIUM",
                "detail": f"Transaction IP '{txn['customer_ip_address']}' differs from registered IP '{cust['registered_ip_address']}'"
            })

        # 3. High amount (>₹50,000)
        amt = float(txn.get("transaction_amount", 0))
        if amt > 50000:
            txn_anomalies.append({
                "type": "HIGH_AMOUNT",
                "severity": "HIGH",
                "detail": f"Transaction amount ₹{amt:,.2f} exceeds ₹50,000 threshold"
            })

        # 4. Amount exceeds balance
        bal = float(cust.get("account_balance", 0))
        if amt > bal:
            txn_anomalies.append({
                "type": "EXCEEDS_BALANCE",
                "severity": "CRITICAL",
                "detail": f"Transaction ₹{amt:,.2f} exceeds account balance ₹{bal:,.2f}"
            })

        # 5. Location mismatch
        home_city = str(cust.get("home_branch", "")).split()[0] if cust.get("home_branch") else ""
        txn_loc = str(txn.get("transaction_location", ""))
        if home_city and txn_loc and home_city.lower() != txn_loc.lower():
            txn_anomalies.append({
                "type": "LOCATION_MISMATCH",
                "severity": "MEDIUM",
                "detail": f"Transaction in '{txn_loc}' but customer branch is in '{home_city}'"
            })

        if txn_anomalies:
            # Enrich with merchant info
            merch_row = merchants_df[merchants_df["merchant_uuid"] == txn.get("merchant_uuid")]
            merchant_name = merch_row.iloc[0]["merchant_name"] if not merch_row.empty else "Unknown"

            anomalies.append({
                "transaction": txn,
                "merchant_name": merchant_name,
                "anomalies": txn_anomalies,
                "risk_score": sum({"LOW":1,"MEDIUM":2,"HIGH":3,"CRITICAL":4}.get(a["severity"],1) for a in txn_anomalies)
            })

    # Check rapid-fire transactions
    if len(txn_list) >= 2:
        try:
            txns_sorted = sorted(txn_list, key=lambda x: x["transaction_timestamp"])
            for i in range(1, len(txns_sorted)):
                t1 = datetime.strptime(txns_sorted[i-1]["transaction_timestamp"], "%Y-%m-%d %H:%M:%S")
                t2 = datetime.strptime(txns_sorted[i]["transaction_timestamp"], "%Y-%m-%d %H:%M:%S")
                diff = (t2 - t1).total_seconds()
                if 0 < diff < 300:  # Within 5 minutes
                    # Check if this transaction already has anomalies
                    existing = [a for a in anomalies if a["transaction"]["transaction_uuid"] == txns_sorted[i]["transaction_uuid"]]
                    rapid_anomaly = {
                        "type": "RAPID_TRANSACTION",
                        "severity": "HIGH",
                        "detail": f"Transaction occurred {int(diff)}s after previous transaction (threshold: 300s)"
                    }
                    if existing:
                        existing[0]["anomalies"].append(rapid_anomaly)
                        existing[0]["risk_score"] += 3
                    else:
                        merch_row = merchants_df[merchants_df["merchant_uuid"] == txns_sorted[i].get("merchant_uuid")]
                        merchant_name = merch_row.iloc[0]["merchant_name"] if not merch_row.empty else "Unknown"
                        anomalies.append({
                            "transaction": txns_sorted[i],
                            "merchant_name": merchant_name,
                            "anomalies": [rapid_anomaly],
                            "risk_score": 3
                        })
        except Exception:
            pass

    # Sort by risk score descending
    anomalies.sort(key=lambda x: x["risk_score"], reverse=True)

    return cust, txn_list, anomalies


def get_risk_level(anomalies):
    if not anomalies:
        return "LOW"
    max_score = max(a["risk_score"] for a in anomalies)
    if max_score >= 6:
        return "CRITICAL"
    elif max_score >= 4:
        return "HIGH"
    elif max_score >= 2:
        return "MEDIUM"
    return "LOW"


# ══════════════════════════════════════════════════════════════
# GenAI – Investigation Reasoning
# ══════════════════════════════════════════════════════════════

def generate_investigation_report(cust, transactions, anomalies):
    """Use Gemini to generate an investigation report."""
    
    # Build context
    context = f"""
You are a Senior Banking Investigation Officer at a major Indian bank. Analyze the following flagged UPI transaction case and generate a detailed investigation report.

## Customer Profile
- Name: {cust['full_name']}
- Age: {cust['age']}
- UPI ID: {cust['upi_id']}
- Bank: {cust['bank_name']}
- Account: {cust['account_number']}
- IFSC: {cust['ifsc_code']}
- Branch: {cust['home_branch']}
- Phone: {cust['registered_phone_number']}
- Registered Device: {cust['registered_device_id']}
- Registered IP: {cust['registered_ip_address']}
- Account Balance: ₹{float(cust['account_balance']):,.2f}
- Total Transactions: {cust['total_transactions_count']}
- Account Opened: {cust['account_open_date']}

## Transaction Summary
Total transactions analyzed: {len(transactions)}

## Flagged Anomalies ({len(anomalies)} detected)
"""
    for i, anom in enumerate(anomalies, 1):
        txn = anom["transaction"]
        context += f"""
### Flagged Transaction #{i} – {txn['transaction_uuid']}
- Amount: ₹{float(txn['transaction_amount']):,.2f}
- Merchant: {anom['merchant_name']}
- Time: {txn['transaction_timestamp']}
- Location: {txn['transaction_location']}
- Device: {txn['customer_device_id']}
- IP: {txn['customer_ip_address']}
- Risk Score: {anom['risk_score']}/10
- Anomalies Detected:
"""
        for a in anom["anomalies"]:
            context += f"  - [{a['severity']}] {a['type']}: {a['detail']}\n"

    context += """

## Generate Investigation Report
Provide a structured investigation report with:
1. **Case Summary** – Brief overview of the flagged case
2. **Data Analyzed** – What data points were examined
3. **Detected Inconsistencies** – List all anomalies found with explanations
4. **Risk Assessment** – Overall risk level and justification
5. **Investigation Outcome** – SUSPICIOUS / LEGITIMATE / REQUIRES_FURTHER_REVIEW
6. **Recommended Actions** – What steps should the bank take
7. **Reasoning** – Detailed explanation of your decision

Be specific, reference actual data values, and explain your reasoning clearly. Use a professional, formal tone.
"""

    if gemini_model:
        try:
            response = gemini_model.generate_content(context)
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "quota" in err_msg.lower():
                print(f"  GenAI:               ! Quota exceeded (429). Falling back to rule-based report.")
                return generate_fallback_report(cust, transactions, anomalies) + "\n\n_Note: AI detailed analysis currently unavailable due to API rate limits._"
            return generate_fallback_report(cust, transactions, anomalies)
    else:
        return generate_fallback_report(cust, transactions, anomalies)


def generate_fallback_report(cust, transactions, anomalies):
    """Generate a rule-based report when GenAI is unavailable."""
    risk = get_risk_level(anomalies)
    
    report = f"""# Investigation Report
## Case ID: INV-{hashlib.md5(cust['customer_uuid'].encode()).hexdigest()[:8].upper()}
## Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 1. Case Summary
Investigation initiated for customer **{cust['full_name']}** (UPI: {cust['upi_id']}). 
{len(anomalies)} anomalous transaction(s) detected out of {len(transactions)} total transactions analyzed.
Overall Risk Level: **{risk}**

## 2. Data Analyzed
- Customer profile and account information
- {len(transactions)} UPI transaction records
- Device and IP address correlation
- Transaction locations vs registered branch
- Transaction amounts vs account balance

## 3. Detected Inconsistencies
"""
    if not anomalies:
        report += "No anomalies detected. All transactions appear consistent with customer profile.\n"
    else:
        for i, anom in enumerate(anomalies, 1):
            txn = anom["transaction"]
            report += f"""
### Transaction {txn['transaction_uuid']}
- **Amount:** ₹{float(txn['transaction_amount']):,.2f}
- **Merchant:** {anom['merchant_name']}
- **Time:** {txn['transaction_timestamp']}
- **Risk Score:** {anom['risk_score']}/10
"""
            for a in anom["anomalies"]:
                report += f"- **[{a['severity']}] {a['type']}:** {a['detail']}\n"

    outcome = "SUSPICIOUS" if risk in ("HIGH","CRITICAL") else "REQUIRES_FURTHER_REVIEW" if risk == "MEDIUM" else "LEGITIMATE"
    report += f"""
## 4. Risk Assessment
Overall risk: **{risk}**
Flagged transactions: {len(anomalies)}
Maximum risk score: {max((a['risk_score'] for a in anomalies), default=0)}/10

## 5. Investigation Outcome
**{outcome}**

## 6. Recommended Actions
"""
    if outcome == "SUSPICIOUS":
        report += """- Temporarily freeze account pending manual review
- Contact customer for transaction verification
- Escalate to fraud investigation team
- File STR (Suspicious Transaction Report) if confirmed
"""
    elif outcome == "REQUIRES_FURTHER_REVIEW":
        report += """- Flag account for enhanced monitoring
- Request customer verification for flagged transactions
- Review again after 48 hours
"""
    else:
        report += """- No immediate action required
- Continue standard monitoring
"""

    report += f"""
## 7. Reasoning
Based on analysis of {len(transactions)} transactions for customer {cust['full_name']}, """
    
    if anomalies:
        types = set()
        for a in anomalies:
            for an in a["anomalies"]:
                types.add(an["type"])
        report += f"the following anomaly types were detected: {', '.join(types)}. "
        report += f"The highest risk score observed was {max(a['risk_score'] for a in anomalies)}/10, "
        report += f"which places this case in the {risk} risk category. "
    else:
        report += "no anomalies were detected. All transaction parameters are consistent with the registered customer profile."

    report += f"""

---
*Report generated by ClearTrace Investigation System*
*Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    return report


# ══════════════════════════════════════════════════════════════
# Cheque Analysis
# ══════════════════════════════════════════════════════════════

def analyze_cheque_image(image_path_or_bytes):
    """Use Gemini Vision to extract info from cheque image."""
    prompt = """Analyze this cheque image and extract the following information in JSON format:
{
  "account_number": "",
  "ifsc_code": "",
  "amount": 0,
  "date": "",
  "issuer_name": "",
  "beneficiary_name": "",
  "bank_name": "",
  "cheque_number": ""
}
Return ONLY the JSON object, no additional text."""

    if not gemini_model:
        return {"error": "Gemini model not initialized. Please check API key."}

    try:
        if isinstance(image_path_or_bytes, (str, Path)):
            img = Image.open(image_path_or_bytes)
        else:
            img = Image.open(io.BytesIO(image_path_or_bytes))

        # Check if model supports multimodal - if it crashes here, we might need a model switch
        response = gemini_model.generate_content([prompt, img])
        text = response.text.strip()
        
        # Clean markdown code blocks
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        
        return json.loads(text)
    except Exception as e:
        err_msg = str(e)
        if "429" in err_msg or "quota" in err_msg.lower():
            return {"error": "AI Quota Exceeded (429). Please wait about 15-20 seconds and try again. The free tier has very strict request limits."}
        if "404" in err_msg or "not found" in err_msg.lower():
            return {"error": "The AI model selected does not support image analysis in this version. Falling back..."}
        return {"error": f"AI Extraction Failed: {err_msg}"}


def validate_cheque(cheque_info):
    """Validate extracted cheque data against customer records."""
    acct = str(cheque_info.get("account_number", ""))
    ifsc = str(cheque_info.get("ifsc_code", ""))

    validations = []
    match = customers_df[customers_df["account_number"].astype(str) == acct]

    if match.empty:
        validations.append({"check": "Account Lookup", "status": "FAIL", "detail": f"Account {acct} not found in records"})
        return validations, None

    cust = match.iloc[0].to_dict()
    validations.append({"check": "Account Lookup", "status": "PASS", "detail": f"Account belongs to {cust['full_name']}"})

    # IFSC check
    if ifsc and str(cust.get("ifsc_code","")) != ifsc:
        validations.append({"check": "IFSC Verification", "status": "FAIL",
                           "detail": f"Cheque IFSC '{ifsc}' differs from registered '{cust['ifsc_code']}'"})
    else:
        validations.append({"check": "IFSC Verification", "status": "PASS", "detail": "IFSC code matches"})

    # Amount vs balance
    amt = float(cheque_info.get("amount", 0))
    bal = float(cust.get("account_balance", 0))
    if amt > bal:
        validations.append({"check": "Balance Check", "status": "FAIL",
                           "detail": f"Cheque ₹{amt:,.2f} exceeds balance ₹{bal:,.2f}"})
    else:
        validations.append({"check": "Balance Check", "status": "PASS",
                           "detail": f"Sufficient balance (₹{bal:,.2f}) for cheque ₹{amt:,.2f}"})

    # Name match
    issuer = str(cheque_info.get("issuer_name", "")).lower().strip()
    cust_name = str(cust.get("full_name", "")).lower().strip()
    if issuer and issuer != cust_name:
        validations.append({"check": "Name Verification", "status": "WARNING",
                           "detail": f"Issuer '{cheque_info.get('issuer_name')}' vs registered '{cust['full_name']}'"})
    elif issuer:
        validations.append({"check": "Name Verification", "status": "PASS", "detail": "Issuer name matches"})

    return validations, cust


# ══════════════════════════════════════════════════════════════
# PDF Report Generation
# ══════════════════════════════════════════════════════════════

class InvestigationPDF(FPDF):
    def header(self):
        self.set_fill_color(15, 23, 42)
        self.rect(0, 0, 210, 30, 'F')
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(255, 255, 255)
        self.cell(0, 15, "ClearTrace Investigation Report", ln=True, align="C")
        self.set_font("Helvetica", "", 9)
        self.set_text_color(148, 163, 184)
        self.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"ClearTrace | Page {self.page_no()}/{{nb}}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(30, 64, 175)
        self.cell(0, 10, title, ln=True)
        self.set_draw_color(30, 64, 175)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def body_text(self, text):
        text = str(text).replace('₹', 'Rs. ')
        self.set_font("Helvetica", "", 10)
        self.set_text_color(51, 51, 51)
        # FPDF handles latin-1 only typically for standard fonts
        text = text.encode('latin-1', 'replace').decode('latin-1')
        self.multi_cell(0, 6, text)
        self.ln(2)

    def key_value(self, key, value):
        key = str(key).replace('₹', 'Rs. ')
        value = str(value).replace('₹', 'Rs. ')
        key = key.encode('latin-1', 'replace').decode('latin-1')
        value = value.encode('latin-1', 'replace').decode('latin-1')
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(71, 85, 105)
        self.cell(55, 7, key + ":")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 41, 59)
        self.cell(0, 7, str(value), ln=True)

    def risk_badge(self, level):
        colors = {
            "CRITICAL": (220, 38, 38),
            "HIGH": (234, 88, 12),
            "MEDIUM": (234, 179, 8),
            "LOW": (34, 197, 94)
        }
        r, g, b = colors.get(level, (128,128,128))
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        w = self.get_string_width(f" {level} ") + 10
        self.cell(w, 8, f" {level} ", fill=True)
        self.ln(5)


def generate_pdf(cust, transactions, anomalies, report_text):
    """Generate PDF investigation report."""
    pdf = InvestigationPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=20)

    case_id = f"INV-{hashlib.md5(cust['customer_uuid'].encode()).hexdigest()[:8].upper()}"

    # Case Info
    pdf.section_title("Case Information")
    pdf.key_value("Case ID", case_id)
    pdf.key_value("Investigation Date", datetime.now().strftime("%Y-%m-%d"))
    risk = get_risk_level(anomalies)
    pdf.key_value("Risk Level", "")
    pdf.risk_badge(risk)
    pdf.ln(5)

    # Customer Profile
    pdf.section_title("Customer Profile")
    pdf.key_value("Name", cust["full_name"])
    pdf.key_value("Age", str(cust["age"]))
    pdf.key_value("UPI ID", cust["upi_id"])
    pdf.key_value("Bank", cust["bank_name"])
    pdf.key_value("Account Number", str(cust["account_number"]))
    pdf.key_value("IFSC Code", cust["ifsc_code"])
    pdf.key_value("Branch", cust["home_branch"])
    pdf.key_value("Phone", str(cust["registered_phone_number"]))
    pdf.key_value("Account Balance", f"Rs. {float(cust['account_balance']):,.2f}")
    pdf.key_value("Account Opened", str(cust["account_open_date"]))
    pdf.ln(5)

    # Transaction Summary
    pdf.section_title("Transaction Analysis")
    pdf.body_text(f"Total transactions analyzed: {len(transactions)}")
    pdf.body_text(f"Anomalous transactions flagged: {len(anomalies)}")
    pdf.ln(3)

    # Anomalies
    if anomalies:
        pdf.section_title("Detected Anomalies")
        for i, anom in enumerate(anomalies, 1):
            txn = anom["transaction"]
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(30, 41, 59)
            pdf.cell(0, 7, f"Transaction #{i}: {txn['transaction_uuid']}", ln=True)
            pdf.key_value("  Amount", f"Rs. {float(txn['transaction_amount']):,.2f}")
            pdf.key_value("  Merchant", anom["merchant_name"])
            pdf.key_value("  Time", str(txn["transaction_timestamp"]))
            pdf.key_value("  Location", str(txn["transaction_location"]))
            pdf.key_value("  Risk Score", f"{anom['risk_score']}/10")
            for a in anom["anomalies"]:
                pdf.set_font("Helvetica", "", 9)
                sev_colors = {"CRITICAL":(220,38,38),"HIGH":(234,88,12),"MEDIUM":(234,179,8),"LOW":(34,197,94)}
                r,g,b = sev_colors.get(a["severity"],(128,128,128))
                pdf.set_text_color(r, g, b)
                detail_text = str(a['detail']).replace("₹", "Rs. ")
                pdf.cell(0, 6, f"    [{a['severity']}] {a['type']}: {detail_text}", ln=True)
            pdf.ln(3)

    # GenAI Report
    pdf.add_page()
    pdf.section_title("AI Investigation Analysis")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(51, 51, 51)
    # Clean markdown formatting for PDF, and replace unsupported unicode char
    clean_text = report_text.replace("₹", "Rs. ").replace("**", "").replace("##", "").replace("###", "").replace("#", "").replace("*", "").replace("---","")
    for line in clean_text.split("\n"):
        line = line.strip()
        if line:
            try:
                pdf.multi_cell(0, 5, line)
            except Exception:
                # Handle encoding issues
                pdf.multi_cell(0, 5, line.encode('latin-1', 'replace').decode('latin-1'))
            pdf.ln(1)

    filename = f"report_{case_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = REPORTS_DIR / filename
    pdf.output(str(filepath))
    return str(filepath), filename


# ══════════════════════════════════════════════════════════════
# Chatbot Logic
# ══════════════════════════════════════════════════════════════

# Simple conversation state per session
chat_sessions = {}

def get_session(session_id):
    if session_id not in chat_sessions:
        chat_sessions[session_id] = {"state": "idle", "context": {}}
    return chat_sessions[session_id]


def process_chat(session_id, message):
    """Process a chat message and return a response."""
    session = get_session(session_id)
    msg = message.strip().lower()
    
    # ── API Key setup ──
    if msg.startswith("setkey:") or msg.startswith("set key:"):
        key = message.split(":", 1)[1].strip()
        if init_gemini(key):
            return {"reply": "✅ **Gemini API key configured successfully!** AI-powered investigation is now enabled.\n\nHow can I help you? Try:\n- 🔍 **Investigate UPI** – Enter a UPI ID to investigate\n- 📋 **View Flagged** – See all flagged transactions\n- 🏦 **Analyze Cheque** – Upload a cheque image", "type": "text"}
        return {"reply": "❌ Failed to configure API key. Please check and try again.", "type": "text"}

    # ── Greeting ──
    if msg in ("hi","hello","hey","help","start","menu"):
        session["state"] = "idle"
        return {
            "reply": "👋 **Welcome to ClearTrace!**\n\nI'm your AI-powered banking investigation assistant. Here's what I can do:\n\n🔍 **Investigate UPI** – Analyze a customer's UPI transactions\n📋 **View Flagged** – See all flagged/anomalous transactions\n🏦 **Analyze Cheque** – Upload & validate a cheque image\n📊 **Customer List** – View all customers in the system\n📄 **Generate Report** – Create a PDF investigation report\n🔊 **Voice Summary** – Listen to investigation results\n\nType a command or ask me anything!",
            "type": "text"
        }

    # ── View flagged transactions ──
    if any(kw in msg for kw in ["flagged","anomal","suspicious","flag"]):
        all_anomalies = []
        for _, cust in customers_df.iterrows():
            _, _, anoms = detect_anomalies(customer_uuid=cust["customer_uuid"])
            for a in anoms:
                a["customer_name"] = cust["full_name"]
                a["customer_upi"] = cust["upi_id"]
                all_anomalies.append(a)
        
        all_anomalies.sort(key=lambda x: x["risk_score"], reverse=True)
        
        if not all_anomalies:
            return {"reply": "✅ No anomalous transactions found!", "type": "text"}
        
        reply = f"🚨 **Flagged Transactions ({len(all_anomalies)} found)**\n\n"
        for i, a in enumerate(all_anomalies[:15], 1):
            txn = a["transaction"]
            risk_emoji = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢"}
            max_sev = max(an["severity"] for an in a["anomalies"])
            emoji = risk_emoji.get(max_sev, "⚪")
            reply += f"{emoji} **{txn['transaction_uuid']}** | {a['customer_name']} ({a['customer_upi']})\n"
            reply += f"   ₹{float(txn['transaction_amount']):,.2f} → {a['merchant_name']} | Risk: {a['risk_score']}/10\n"
            for an in a["anomalies"]:
                reply += f"   ⚠️ {an['type']}: {an['detail']}\n"
            reply += "\n"
        
        if len(all_anomalies) > 15:
            reply += f"\n_...and {len(all_anomalies) - 15} more. Investigate a specific UPI ID for details._"
        
        return {"reply": reply, "type": "flagged", "count": len(all_anomalies)}

    # ── Customer list ──
    if any(kw in msg for kw in ["customer list","all customers","list customer","customers"]):
        reply = "👥 **Customer Directory**\n\n"
        reply += "| # | Name | UPI ID | Bank | Balance |\n"
        reply += "|---|------|--------|------|--------|\n"
        for i, (_, c) in enumerate(customers_df.iterrows(), 1):
            reply += f"| {i} | {c['full_name']} | `{c['upi_id']}` | {c['bank_name']} | ₹{float(c['account_balance']):,.0f} |\n"
        reply += "\n_Enter a UPI ID to investigate a customer._"
        return {"reply": reply, "type": "text"}

    # ── Investigate UPI ──
    if any(kw in msg for kw in ["investigate","upi","analyze upi","check upi"]):
        # Check if UPI ID is in the message
        parts = message.strip().split()
        upi_id = None
        for p in parts:
            if "@" in p:
                upi_id = p
                break
        
        if upi_id:
            return investigate_upi(session, upi_id)
        else:
            session["state"] = "awaiting_upi"
            return {"reply": "🔍 **UPI Investigation Mode**\n\nPlease enter the customer's **UPI ID** (e.g., `rahul42@okaxis`):", "type": "text"}

    # ── Awaiting UPI ID ──
    if session["state"] == "awaiting_upi":
        upi_id = message.strip()
        if "@" not in upi_id:
            # Try to match by name or customer UUID
            match = customers_df[
                (customers_df["full_name"].str.lower().str.contains(msg)) |
                (customers_df["customer_uuid"].str.lower() == msg)
            ]
            if not match.empty:
                upi_id = match.iloc[0]["upi_id"]
            else:
                return {"reply": "⚠️ That doesn't look like a valid UPI ID. Please enter a UPI ID with @ symbol (e.g., `rahul42@okaxis`).\n\nOr type **customer list** to see available customers.", "type": "text"}
        return investigate_upi(session, upi_id)

    # ── Generate report (after investigation) ──
    if any(kw in msg for kw in ["report","pdf","download","generate report"]):
        if "last_investigation" in session.get("context", {}):
            ctx = session["context"]["last_investigation"]
            filepath, filename = generate_pdf(ctx["customer"], ctx["transactions"], ctx["anomalies"], ctx["report_text"])
            return {
                "reply": f"📄 **Investigation Report Generated!**\n\nFile: `{filename}`\n\nClick the download button below to save the PDF.",
                "type": "pdf",
                "pdf_path": filepath,
                "pdf_name": filename
            }
        else:
            return {"reply": "⚠️ No investigation data available. Please investigate a UPI ID first, then request a report.", "type": "text"}

    # ── Voice summary ──
    if any(kw in msg for kw in ["voice","speak","audio","listen","read aloud"]):
        if "last_investigation" in session.get("context", {}):
            ctx = session["context"]["last_investigation"]
            summary = ctx["report_text"][:1500]  # Limit for TTS
            # Clean markdown
            clean = summary.replace("**","").replace("##","").replace("#","").replace("*","").replace("---","").replace("_","")
            try:
                tts = gTTS(text=clean, lang='en', slow=False)
                voice_file = VOICE_DIR / f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                tts.save(str(voice_file))
                return {
                    "reply": "🔊 **Voice summary generated!** Click play to listen.",
                    "type": "voice",
                    "voice_path": str(voice_file)
                }
            except Exception as e:
                return {"reply": f"⚠️ Voice generation failed: {str(e)}", "type": "text"}
        else:
            return {"reply": "⚠️ No investigation data. Please investigate a UPI ID first.", "type": "text"}

    # ── Cheque analysis ──
    if any(kw in msg for kw in ["cheque","check image","analyze cheque"]):
        session["state"] = "awaiting_cheque"
        return {"reply": "🏦 **Cheque Analysis Mode**\n\nPlease upload a cheque image using the upload button below. I'll extract the details and validate against customer records.", "type": "text"}

    # ── If message contains @, try as UPI ID ──
    if "@" in msg:
        return investigate_upi(session, message.strip())

    # ── Free-form query via GenAI ──
    if gemini_model:
        try:
            # Build a data-aware context
            data_context = f"""You are ClearTrace, an AI banking investigation assistant. 
You have access to {len(customers_df)} customers, {len(merchants_df)} merchants, and {len(transactions_df)} transactions.

Customer UPI IDs available: {', '.join(customers_df['upi_id'].tolist()[:10])}...

The user asks: {message}

If they seem to be asking about a specific customer or transaction, suggest they use the "investigate" command with a UPI ID.
Otherwise, answer their banking/investigation question helpfully.
Keep responses concise and professional."""
            
            response = gemini_model.generate_content(data_context)
            return {"reply": response.text, "type": "text"}
        except Exception:
            pass
    
    return {
        "reply": "🤔 I'm not sure what you mean. Try one of these:\n\n🔍 **investigate** – Investigate a UPI ID\n📋 **flagged** – View flagged transactions\n👥 **customer list** – View all customers\n🏦 **cheque** – Analyze a cheque image\n\nOr type **help** for the full menu!",
        "type": "text"
    }


def investigate_upi(session, upi_id):
    """Run full investigation on a UPI ID."""
    cust, txns, anomalies = detect_anomalies(upi_id=upi_id)

    if cust is None:
        return {"reply": f"❌ **Customer not found** for UPI ID: `{upi_id}`\n\nPlease check the ID and try again. Type **customer list** to see available customers.", "type": "text"}

    risk = get_risk_level(anomalies)
    risk_emoji = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢"}.get(risk,"⚪")

    # Generate AI report
    report_text = generate_investigation_report(cust, txns, anomalies)

    # Store in session for follow-up
    session["state"] = "investigated"
    session["context"]["last_investigation"] = {
        "customer": cust,
        "transactions": txns,
        "anomalies": anomalies,
        "report_text": report_text
    }

    reply = f"""## 🔍 Investigation Results

### Customer Profile
| Field | Value |
|-------|-------|
| **Name** | {cust['full_name']} |
| **UPI ID** | `{cust['upi_id']}` |
| **Bank** | {cust['bank_name']} |
| **Account** | {cust['account_number']} |
| **Branch** | {cust['home_branch']} |
| **Balance** | ₹{float(cust['account_balance']):,.2f} |
| **Total Transactions** | {cust['total_transactions_count']} |
| **Account Since** | {cust['account_open_date']} |

### Risk Assessment
{risk_emoji} **Overall Risk: {risk}**
- Transactions analyzed: **{len(txns)}**
- Anomalies detected: **{len(anomalies)}**

"""
    if anomalies:
        reply += "### 🚨 Flagged Transactions\n\n"
        for i, a in enumerate(anomalies, 1):
            txn = a["transaction"]
            reply += f"**{i}. {txn['transaction_uuid']}** – ₹{float(txn['transaction_amount']):,.2f} → {a['merchant_name']}\n"
            reply += f"   📍 {txn['transaction_location']} | 🕐 {txn['transaction_timestamp']} | Risk: {a['risk_score']}/10\n"
            for an in a["anomalies"]:
                severity_icon = {"CRITICAL":"🔴","HIGH":"🟠","MEDIUM":"🟡","LOW":"🟢"}.get(an["severity"],"⚪")
                reply += f"   {severity_icon} **{an['type']}**: {an['detail']}\n"
            reply += "\n"
    else:
        reply += "### ✅ No Anomalies Detected\nAll transactions are consistent with the customer profile.\n\n"

    reply += "---\n### 🤖 AI Analysis\n\n"
    # Truncate for display, full version in PDF
    display_report = report_text[:2000]
    if len(report_text) > 2000:
        display_report += "\n\n_...Report truncated. Download the full PDF for complete analysis._"
    reply += display_report

    reply += "\n\n---\n💡 **Quick Actions:** Type **report** for PDF | **voice** for audio summary"

    return {
        "reply": reply,
        "type": "investigation",
        "risk": risk,
        "anomaly_count": len(anomalies),
        "customer_name": cust["full_name"]
    }


# ══════════════════════════════════════════════════════════════
# API Routes
# ══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(".", "chatbot.html")

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    message = data.get("message", "")
    session_id = data.get("session_id", "default")
    result = process_chat(session_id, message)
    return jsonify(result)

@app.route("/api/set_key", methods=["POST"])
def api_set_key():
    data = request.json
    key = data.get("api_key", "")
    if init_gemini(key):
        return jsonify({"success": True, "message": "API key configured"})
    return jsonify({"success": False, "message": "Invalid key"})

@app.route("/api/investigate/upi", methods=["POST"])
def api_investigate_upi():
    data = request.json
    upi_id = data.get("upi_id", "")
    cust, txns, anomalies = detect_anomalies(upi_id=upi_id)
    if cust is None:
        return jsonify({"error": "Customer not found"}), 404
    
    report = generate_investigation_report(cust, txns, anomalies)
    return jsonify({
        "customer": cust,
        "transactions": txns,
        "anomalies": [{
            "transaction": a["transaction"],
            "merchant_name": a["merchant_name"],
            "anomalies": a["anomalies"],
            "risk_score": a["risk_score"]
        } for a in anomalies],
        "risk_level": get_risk_level(anomalies),
        "report": report
    })

@app.route("/api/report/pdf", methods=["POST"])
def api_report_pdf():
    data = request.json
    session_id = data.get("session_id", "default")
    session = get_session(session_id)
    
    if "last_investigation" not in session.get("context", {}):
        return jsonify({"error": "No investigation data"}), 400
    
    ctx = session["context"]["last_investigation"]
    filepath, filename = generate_pdf(ctx["customer"], ctx["transactions"], ctx["anomalies"], ctx["report_text"])
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route("/api/voice", methods=["POST"])
def api_voice():
    data = request.json
    text = data.get("text", "")
    session_id = data.get("session_id", "default")
    
    if not text:
        session = get_session(session_id)
        if "last_investigation" in session.get("context", {}):
            text = session["context"]["last_investigation"]["report_text"][:1500]
    
    if not text:
        return jsonify({"error": "No text to convert"}), 400
    
    clean = text.replace("**","").replace("##","").replace("#","").replace("*","").replace("---","").replace("_","")
    try:
        tts = gTTS(text=clean, lang='en', slow=False)
        voice_file = VOICE_DIR / f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        tts.save(str(voice_file))
        return send_file(str(voice_file), mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/cheque/analyze", methods=["POST"])
def api_cheque_analyze():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["file"]
    img_bytes = file.read()
    
    cheque_info = analyze_cheque_image(img_bytes)
    if "error" in cheque_info:
        return jsonify(cheque_info), 400
    
    validations, cust = validate_cheque(cheque_info)
    
    response = {
        "extracted_data": cheque_info,
        "validations": validations,
        "customer": cust if cust else None,
        "overall_status": "PASS" if all(v["status"] in ("PASS",) for v in validations) else "FAIL"
    }
    return jsonify(response)

@app.route("/api/customers", methods=["GET"])
def api_customers():
    return jsonify(customers_df.to_dict("records"))

@app.route("/api/transactions", methods=["GET"])
def api_transactions():
    flagged = request.args.get("flagged", "false").lower() == "true"
    if flagged:
        all_anomalies = []
        for _, cust in customers_df.iterrows():
            _, _, anoms = detect_anomalies(customer_uuid=cust["customer_uuid"])
            for a in anoms:
                a["customer_name"] = cust["full_name"]
                all_anomalies.append(a)
        return jsonify(all_anomalies)
    return jsonify(transactions_df.to_dict("records"))

@app.route("/api/cheque/list", methods=["GET"])
def api_cheque_list():
    cheque_dir = BASE / "cheques" / "cheque_images"
    if cheque_dir.exists():
        files = [f.name for f in cheque_dir.iterdir() if f.suffix == ".png"]
        return jsonify({"cheques": sorted(files)})
    return jsonify({"cheques": []})

@app.route("/api/cheque/image/<filename>", methods=["GET"])
def api_cheque_image(filename):
    return send_from_directory(str(BASE / "cheques" / "cheque_images"), filename)


@app.route("/analytics")
def analytics_page():
    return send_from_directory(".", "analytics.html")


@app.route("/api/analytics/overview", methods=["GET"])
def api_analytics_overview():
    """Deep per-customer analytics with transaction behaviour, locations, UPI IDs."""
    global customers_df, transactions_df, merchants_df

    all_customer_profiles = []
    anomaly_type_counts   = {}
    risk_counts           = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    total_at_risk_amount  = 0.0
    fraud_confirmed_count = 0

    for _, cust_row in customers_df.iterrows():
        cust_uuid = cust_row["customer_uuid"]
        cust_txns = transactions_df[transactions_df["customer_uuid"] == cust_uuid].copy()
        if cust_txns.empty:
            continue

        # ── Anomaly detection for this customer ──
        _, txns, anomalies = detect_anomalies(customer_uuid=cust_uuid)
        risk_level = get_risk_level(anomalies)
        max_risk   = max((a["risk_score"] for a in anomalies), default=0)

        # Locations
        locations = cust_txns["transaction_location"].dropna().value_counts().head(3).to_dict()
        primary_location = list(locations.keys())[0] if locations else "Unknown"

        # Transaction modes
        modes = cust_txns["transaction_mode"].dropna().value_counts().to_dict() if "transaction_mode" in cust_txns.columns else {}

        # UPI apps
        apps = cust_txns["customer_upi_app"].dropna().value_counts().to_dict() if "customer_upi_app" in cust_txns.columns else {}

        # Amounts
        total_amt = float(cust_txns["transaction_amount"].sum())
        avg_amt   = float(cust_txns["transaction_amount"].mean())
        max_amt   = float(cust_txns["transaction_amount"].max())

        # Status breakdown
        statuses = cust_txns["transaction_status"].dropna().value_counts().to_dict() if "transaction_status" in cust_txns.columns else {}
        failed_count  = statuses.get("FAILED", 0) + statuses.get("DECLINED", 0)
        success_count = statuses.get("SUCCESS", 0)

        # Behaviour tags
        behaviour = []
        if max_risk >= 6:
            behaviour.append("CRITICAL_RISK")
        elif max_risk >= 4:
            behaviour.append("HIGH_RISK")
        if any(a["type"] == "DEVICE_MISMATCH" for anom in anomalies for a in anom["anomalies"]):
            behaviour.append("DEVICE_ANOMALY")
        if any(a["type"] == "IP_MISMATCH" for anom in anomalies for a in anom["anomalies"]):
            behaviour.append("IP_ANOMALY")
        if any(a["type"] == "LOCATION_MISMATCH" for anom in anomalies for a in anom["anomalies"]):
            behaviour.append("LOCATION_ANOMALY")
        if any(a["type"] == "HIGH_AMOUNT" for anom in anomalies for a in anom["anomalies"]):
            behaviour.append("LARGE_TXNS")
        if any(a["type"] == "RAPID_TRANSACTION" for anom in anomalies for a in anom["anomalies"]):
            behaviour.append("RAPID_TXNS")
        if any(a["type"] == "EXCEEDS_BALANCE" for anom in anomalies for a in anom["anomalies"]):
            behaviour.append("BALANCE_EXCEEDED")
        if failed_count > 2:
            behaviour.append("MULTIPLE_FAILURES")
        if not behaviour:
            behaviour.append("NORMAL")

        # Collect anomaly type counts globally
        for anom in anomalies:
            for a in anom["anomalies"]:
                anomaly_type_counts[a["type"]] = anomaly_type_counts.get(a["type"], 0) + 1

        # Global counters
        risk_counts[risk_level] = risk_counts.get(risk_level, 0) + 1
        if risk_level in ("CRITICAL", "HIGH") and anomalies:
            total_at_risk_amount += sum(float(a["transaction"]["transaction_amount"]) for a in anomalies)
        if risk_level == "CRITICAL":
            fraud_confirmed_count += 1

        # Merchant diversity
        merch_ids = cust_txns["merchant_uuid"].dropna().unique().tolist()
        top_merchant_ids = merch_ids[:3]
        top_merchant_names = []
        for mid in top_merchant_ids:
            m = merchants_df[merchants_df["merchant_uuid"] == mid]
            top_merchant_names.append(m.iloc[0]["merchant_name"] if not m.empty else mid)

        all_customer_profiles.append({
            "customer_uuid":   cust_uuid,
            "full_name":       str(cust_row.get("full_name", "")),
            "upi_id":          str(cust_row.get("upi_id", "")),
            "bank_name":       str(cust_row.get("bank_name", "")),
            "account_number":  str(cust_row.get("account_number", "")),
            "email":           str(cust_row.get("email", "")),
            "phone":           str(cust_row.get("registered_phone_number", "")),
            "occupation":      str(cust_row.get("occupation", "")),
            "risk_tier":       str(cust_row.get("risk_tier", "")),
            "kyc_status":      str(cust_row.get("kyc_status", "")),
            "account_balance": float(cust_row.get("account_balance", 0) or 0),
            "risk_level":      risk_level,
            "risk_score":      max_risk,
            "anomaly_count":   len(anomalies),
            "txn_count":       len(cust_txns),
            "total_amount":    round(total_amt, 2),
            "avg_amount":      round(avg_amt, 2),
            "max_amount":      round(max_amt, 2),
            "success_count":   int(success_count),
            "failed_count":    int(failed_count),
            "primary_location":primary_location,
            "all_locations":   locations,
            "transaction_modes": modes,
            "upi_apps":        apps,
            "behaviour_tags":  behaviour,
            "top_merchants":   top_merchant_names,
        })

    # Sort by risk_score descending
    all_customer_profiles.sort(key=lambda x: x["risk_score"], reverse=True)

    return jsonify(sanitize_nan({
        "kpis": {
            "flagged_count":      sum(1 for p in all_customer_profiles if p["anomaly_count"] > 0),
            "critical_count":     risk_counts["CRITICAL"],
            "high_count":         risk_counts["HIGH"],
            "fraud_confirmed":    fraud_confirmed_count,
            "total_at_risk_amount": round(total_at_risk_amount, 2),
            "total_customers":    len(all_customer_profiles),
        },
        "anomaly_type_distribution": anomaly_type_counts,
        "risk_distribution":         risk_counts,
        "customer_profiles":         all_customer_profiles,
    }))


@app.route("/dashboard")
def dashboard():
    return send_from_directory(".", "dashboard.html")

@app.route("/investigation")
def investigation_page():
    return send_from_directory(".", "investigation.html")

@app.route("/api/investigate/txn/<txn_id>", methods=["GET"])
def api_investigate_txn(txn_id):
    """Full investigation data for a specific transaction."""
    txn_row = transactions_df[transactions_df["transaction_uuid"] == txn_id]
    if txn_row.empty:
        return jsonify({"error": "Transaction not found"}), 404
    txn = txn_row.iloc[0].to_dict()

    cust, txns, anomalies = detect_anomalies(customer_uuid=txn["customer_uuid"])
    if cust is None:
        return jsonify({"error": "Customer not found"}), 404

    # Find anomalies for this specific txn
    txn_anomalies = []
    txn_risk_score = 0
    for a in anomalies:
        if a["transaction"]["transaction_uuid"] == txn_id:
            txn_anomalies = a["anomalies"]
            txn_risk_score = a["risk_score"]
            break

    risk_level = get_risk_level(anomalies)
    overall_risk_score = max((a["risk_score"] for a in anomalies), default=0)

    # Sanitize NaN before using in JSON/PDF
    cust = {k: (v if not (isinstance(v, float) and math.isnan(v)) else None) for k, v in cust.items()}
    txn  = {k: (v if not (isinstance(v, float) and math.isnan(v)) else None) for k, v in txn.items()}

    # Merchant info
    merch_row = merchants_df[merchants_df["merchant_uuid"] == txn.get("merchant_uuid", "")]
    merchant  = {k: (v if not (isinstance(v, float) and math.isnan(v)) else None)
                 for k, v in (merch_row.iloc[0].to_dict() if not merch_row.empty else {}).items()}

    # Generate AI report (graceful fallback if no Gemini key)
    try:
        report_text = generate_investigation_report(cust, txns, anomalies)
    except Exception:
        report_text = (
            f"AI analysis unavailable — set a Gemini API key for full reports.\n\n"
            f"Customer: {cust.get('full_name','N/A')} | "
            f"Risk Level: {risk_level} | Anomalies: {len(txn_anomalies)}"
        )

    # All txns for this customer (last 10)
    cust_txns = transactions_df[transactions_df["customer_uuid"] == cust["customer_uuid"]].copy()
    cust_txn_list = cust_txns.sort_values("transaction_timestamp", ascending=False).head(10).to_dict("records")
    # Enrich with merchant names
    for t in cust_txn_list:
        m = merchants_df[merchants_df["merchant_uuid"] == t.get("merchant_uuid","")]
        t["merchant_name"] = m.iloc[0]["merchant_name"] if not m.empty else "Unknown"

    # Outcome
    if risk_level in ("CRITICAL", "HIGH"):
        outcome = "FRAUD CONFIRMED" if risk_level == "CRITICAL" else "SUSPICIOUS – NEEDS REVIEW"
        recommended_action = "Block transaction immediately. Freeze account pending manual review. File STR (Suspicious Transaction Report). Contact customer for verification."
    elif risk_level == "MEDIUM":
        outcome = "SUSPICIOUS – NEEDS REVIEW"
        recommended_action = "Flag account for enhanced monitoring. Contact customer for verification. Re-review in 48 hours."
    else:
        outcome = "LEGITIMATE"
        recommended_action = "No immediate action required. Continue standard monitoring."

    return jsonify(sanitize_nan({
        "txn_id": txn_id,
        "customer": cust,
        "transaction": txn,
        "merchant": merchant,
        "all_customer_txns": cust_txn_list,
        "anomalies": txn_anomalies,
        "all_anomalies_count": len(anomalies),
        "risk_score": txn_risk_score,
        "overall_risk_score": overall_risk_score,
        "risk_level": risk_level,
        "outcome": outcome,
        "recommended_action": recommended_action,
        "ai_report": report_text,
        "total_txns_analyzed": len(txns),
    }))


@app.route("/api/dashboard/stats", methods=["GET"])
def api_dashboard_stats():
    """Compute all analytics for the dashboard."""
    global customers_df, transactions_df, merchants_df

    # ── Summary KPIs ──
    total_customers = len(customers_df)
    total_transactions = len(transactions_df)
    total_merchants = len(merchants_df)
    total_volume = float(transactions_df["transaction_amount"].sum())
    avg_txn = float(transactions_df["transaction_amount"].mean())

    # ── Flagged analysis ──
    all_anomalies = []
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    anomaly_type_counts = {}
    customers_at_risk = set()

    for _, cust in customers_df.iterrows():
        _, _, anoms = detect_anomalies(customer_uuid=cust["customer_uuid"])
        for a in anoms:
            a["customer_name"] = cust["full_name"]
            a["customer_upi"] = cust["upi_id"]
            a["customer_bank"] = cust["bank_name"]
            all_anomalies.append(a)
            customers_at_risk.add(cust["customer_uuid"])
            for an in a["anomalies"]:
                t = an["type"]
                anomaly_type_counts[t] = anomaly_type_counts.get(t, 0) + 1

    all_anomalies.sort(key=lambda x: x["risk_score"], reverse=True)

    for a in all_anomalies:
        score = a["risk_score"]
        if score >= 6:
            risk_counts["CRITICAL"] += 1
        elif score >= 4:
            risk_counts["HIGH"] += 1
        elif score >= 2:
            risk_counts["MEDIUM"] += 1
        else:
            risk_counts["LOW"] += 1

    # ── Transaction amount distribution ──
    amount_ranges = {"0-1K": 0, "1K-5K": 0, "5K-10K": 0, "10K-25K": 0, "25K-50K": 0, "50K-100K": 0, "100K+": 0}
    for _, t in transactions_df.iterrows():
        amt = float(t["transaction_amount"])
        if amt < 1000: amount_ranges["0-1K"] += 1
        elif amt < 5000: amount_ranges["1K-5K"] += 1
        elif amt < 10000: amount_ranges["5K-10K"] += 1
        elif amt < 25000: amount_ranges["10K-25K"] += 1
        elif amt < 50000: amount_ranges["25K-50K"] += 1
        elif amt < 100000: amount_ranges["50K-100K"] += 1
        else: amount_ranges["100K+"] += 1

    # ── Bank distribution ──
    bank_counts = customers_df["bank_name"].value_counts().to_dict()

    # ── Transaction by location ──
    location_counts = transactions_df["transaction_location"].value_counts().head(10).to_dict()

    # ── Merchant volume ──
    merchant_volumes = {}
    for _, t in transactions_df.iterrows():
        mid = t["merchant_uuid"]
        m_row = merchants_df[merchants_df["merchant_uuid"] == mid]
        name = m_row.iloc[0]["merchant_name"] if not m_row.empty else mid
        merchant_volumes[name] = merchant_volumes.get(name, 0) + float(t["transaction_amount"])
    top_merchants = dict(sorted(merchant_volumes.items(), key=lambda x: x[1], reverse=True)[:10])

    # ── Age distribution ──
    age_groups = {"18-25": 0, "26-35": 0, "36-45": 0, "46-55": 0, "56-65": 0}
    for _, c in customers_df.iterrows():
        age = int(c["age"])
        if age <= 25: age_groups["18-25"] += 1
        elif age <= 35: age_groups["26-35"] += 1
        elif age <= 45: age_groups["36-45"] += 1
        elif age <= 55: age_groups["46-55"] += 1
        else: age_groups["56-65"] += 1

    # ── Balance distribution ──
    balance_ranges = {"<10K": 0, "10K-50K": 0, "50K-100K": 0, "100K-250K": 0, "250K-500K": 0, "500K+": 0}
    for _, c in customers_df.iterrows():
        bal = float(c["account_balance"])
        if bal < 10000: balance_ranges["<10K"] += 1
        elif bal < 50000: balance_ranges["10K-50K"] += 1
        elif bal < 100000: balance_ranges["50K-100K"] += 1
        elif bal < 250000: balance_ranges["100K-250K"] += 1
        elif bal < 500000: balance_ranges["250K-500K"] += 1
        else: balance_ranges["500K+"] += 1

    # ── Flagged table (enriched with customer email & uuid) ──
    flagged_table = []
    for a in all_anomalies[:50]:
        txn = a["transaction"]
        # Look up customer email from customers_df
        cust_row = customers_df[customers_df["customer_uuid"] == txn.get("customer_uuid", "")]
        cust_email = cust_row.iloc[0]["email"] if not cust_row.empty and "email" in cust_row.columns else ""
        cust_uuid  = cust_row.iloc[0]["customer_uuid"] if not cust_row.empty else ""
        cust_phone = str(cust_row.iloc[0]["registered_phone_number"]) if not cust_row.empty else ""
        cust_occupation = cust_row.iloc[0]["occupation"] if not cust_row.empty and "occupation" in cust_row.columns else ""
        cust_risk_tier  = cust_row.iloc[0]["risk_tier"] if not cust_row.empty and "risk_tier" in cust_row.columns else ""
        flagged_table.append({
            "txn_id":       txn["transaction_uuid"],
            "customer_uuid": cust_uuid,
            "customer":     a.get("customer_name", ""),
            "customer_email": cust_email,
            "customer_phone": cust_phone,
            "customer_occupation": cust_occupation,
            "customer_risk_tier":  cust_risk_tier,
            "upi":         a.get("customer_upi", ""),
            "bank":        a.get("customer_bank", ""),
            "amount":      float(txn["transaction_amount"]),
            "merchant":    a["merchant_name"],
            "location":    txn["transaction_location"],
            "timestamp":   txn["transaction_timestamp"],
            "device":      txn["customer_device_id"],
            "ip":          txn["customer_ip_address"],
            "txn_mode":    txn.get("transaction_mode", "UPI"),
            "txn_status":  txn.get("transaction_status", "SUCCESS"),
            "upi_app":     txn.get("customer_upi_app", ""),
            "risk_score":  a["risk_score"],
            "anomalies":   [{"type": an["type"], "severity": an["severity"], "detail": an["detail"]} for an in a["anomalies"]]
        })

    return jsonify({
        "kpis": {
            "total_customers": total_customers,
            "total_transactions": total_transactions,
            "total_merchants": total_merchants,
            "total_volume": total_volume,
            "avg_transaction": avg_txn,
            "flagged_count": len(all_anomalies),
            "customers_at_risk": len(customers_at_risk),
            "flag_rate": round(len(all_anomalies) / total_transactions * 100, 1) if total_transactions else 0
        },
        "risk_distribution": risk_counts,
        "anomaly_types": anomaly_type_counts,
        "amount_distribution": amount_ranges,
        "bank_distribution": bank_counts,
        "location_distribution": location_counts,
        "top_merchants": top_merchants,
        "age_distribution": age_groups,
        "balance_distribution": balance_ranges,
        "flagged_transactions": flagged_table
    })

@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "online",
        "gemini_active": gemini_model is not None,
        "model_name": gemini_model.model_name if gemini_model else "none",
        "dataset": {
            "customers": len(customers_df),
            "transactions": len(transactions_df),
            "cheques": len(cheques_df) if cheques_df is not None else 0
        }
    })


# ══════════════════════════════════════════════════════════════
# Email API
# ══════════════════════════════════════════════════════════════

def send_alert_email(recipient, customer_name, txn_id, risk_level, anomaly_details,
                     amount, merchant, timestamp, location, pdf_path=None):
    """Send fraud alert email to customer with optional PDF attachment."""
    subject = f"[ClearTrace Alert] Suspicious Transaction Detected – {txn_id}"

    risk_color = {"CRITICAL": "#c96666", "HIGH": "#d4845a",
                  "MEDIUM": "#c9a84c", "LOW": "#7fba8a"}.get(risk_level, "#a09f9b")

    anomaly_rows = "".join(
        f"<tr><td style='padding:6px 10px;border-bottom:1px solid #eee;color:#555'>{an['type']}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{an['severity']}</td>"
        f"<td style='padding:6px 10px;border-bottom:1px solid #eee;color:#333'>{an['detail']}</td></tr>"
        for an in anomaly_details
    )

    html_body = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:620px;margin:0 auto;background:#f9f9f7;border-radius:10px;overflow:hidden;border:1px solid #ddd">
      <div style="background:#1C1B19;padding:28px 32px">
        <div style="color:#c8b89a;font-size:22px;font-weight:700;letter-spacing:-0.5px">ClearTrace</div>
        <div style="color:#6b6966;font-size:12px;margin-top:4px">Banking Investigation System</div>
      </div>
      <div style="padding:28px 32px">
        <div style="background:{risk_color}18;border:1px solid {risk_color}44;border-radius:8px;padding:16px 20px;margin-bottom:24px">
          <div style="font-size:13px;color:{risk_color};font-weight:600;margin-bottom:4px">⚠ {risk_level} RISK ALERT</div>
          <div style="font-size:14px;color:#222;font-weight:500">Suspicious transaction detected on your account</div>
        </div>
        <p style="color:#444;font-size:14px;line-height:1.6">Dear <strong>{customer_name}</strong>,</p>
        <p style="color:#555;font-size:13px;line-height:1.7">
          Our fraud detection system has flagged a transaction on your account. Please review the details below.
          If you did not authorize this transaction, contact your bank immediately.
        </p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:13px">
          <tr style="background:#f0ede8"><td style="padding:8px 12px;font-weight:600;color:#666">Transaction ID</td><td style="padding:8px 12px;color:#222;font-family:monospace">{txn_id}</td></tr>
          <tr><td style="padding:8px 12px;font-weight:600;color:#666">Amount</td><td style="padding:8px 12px;color:#c96666;font-weight:700">₹{amount:,.2f}</td></tr>
          <tr style="background:#f0ede8"><td style="padding:8px 12px;font-weight:600;color:#666">Merchant</td><td style="padding:8px 12px;color:#222">{merchant}</td></tr>
          <tr><td style="padding:8px 12px;font-weight:600;color:#666">Date & Time</td><td style="padding:8px 12px;color:#222">{timestamp}</td></tr>
          <tr style="background:#f0ede8"><td style="padding:8px 12px;font-weight:600;color:#666">Location</td><td style="padding:8px 12px;color:#222">{location}</td></tr>
          <tr><td style="padding:8px 12px;font-weight:600;color:#666">Risk Level</td><td style="padding:8px 12px"><span style="background:{risk_color}22;color:{risk_color};padding:3px 10px;border-radius:4px;font-weight:600;font-size:12px">{risk_level}</span></td></tr>
        </table>
        {'<div style="margin:20px 0"><div style="font-size:13px;font-weight:600;color:#444;margin-bottom:8px">Anomalies Detected:</div><table style="width:100%;font-size:12px;border-collapse:collapse"><thead><tr style="background:#f0ede8"><th style="padding:6px 10px;text-align:left;color:#666">Type</th><th style="padding:6px 10px;text-align:left;color:#666">Severity</th><th style="padding:6px 10px;text-align:left;color:#666">Detail</th></tr></thead><tbody>' + anomaly_rows + '</tbody></table></div>' if anomaly_rows else ''}
        <div style="background:#1C1B19;border-radius:8px;padding:18px 24px;margin-top:24px">
          <p style="color:#c8b89a;font-size:13px;margin:0"><strong>What to do:</strong></p>
          <ul style="color:#a09f9b;font-size:12px;line-height:1.8;margin:8px 0 0">
            <li>If you made this transaction — no action needed.</li>
            <li>If you <strong>did NOT</strong> make this — call your bank immediately and freeze your account.</li>
            <li>Change your UPI PIN and update your registered device.</li>
          </ul>
        </div>
        <p style="color:#aaa;font-size:11px;margin-top:24px">This is an automated alert from ClearTrace Investigation System. Case investigated by a banking fraud officer.</p>
      </div>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    # Attach PDF if provided
    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{Path(pdf_path).name}"')
        msg.attach(part)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SENDER_EMAIL, APP_PASSWORD)
    server.sendmail(SENDER_EMAIL, recipient, msg.as_string())
    server.quit()


@app.route("/api/send_alert", methods=["POST"])
def api_send_alert():
    """Officer sends alert email for a flagged transaction."""
    data = request.json
    txn_id        = data.get("txn_id", "")
    customer_uuid = data.get("customer_uuid", "")
    recipient     = data.get("recipient_email", "")
    generate_pdf_flag = data.get("generate_pdf", True)

    if not txn_id or not recipient:
        return jsonify({"error": "txn_id and recipient_email are required"}), 400

    # Fetch customer & anomalies
    cust, txns, anomalies = detect_anomalies(customer_uuid=customer_uuid)
    if cust is None:
        return jsonify({"error": "Customer not found"}), 404

    # Find the specific transaction
    txn_row = transactions_df[transactions_df["transaction_uuid"] == txn_id]
    if txn_row.empty:
        return jsonify({"error": "Transaction not found"}), 404
    txn = txn_row.iloc[0].to_dict()

    # Find anomalies for this transaction
    txn_anomalies = []
    for a in anomalies:
        if a["transaction"]["transaction_uuid"] == txn_id:
            txn_anomalies = a["anomalies"]
            risk_score    = a["risk_score"]
            break

    risk_level = "HIGH" if risk_score >= 4 else "MEDIUM" if risk_score >= 2 else "LOW"
    merch_row  = merchants_df[merchants_df["merchant_uuid"] == txn.get("merchant_uuid", "")]
    merchant_name = merch_row.iloc[0]["merchant_name"] if not merch_row.empty else "Unknown"

    # Generate PDF report
    pdf_path = ""
    try:
        if generate_pdf_flag:
            report_text = generate_investigation_report(cust, txns, anomalies)
            pdf_filepath, _ = generate_pdf(cust, txns, anomalies, report_text)
            pdf_path = pdf_filepath
    except Exception as e:
        pdf_path = ""

    # Log investigation
    inv_id = log_investigation(
        customer_uuid=cust["customer_uuid"],
        customer_name=cust["full_name"],
        customer_email=recipient,
        txn_id=txn_id,
        risk_level=risk_level,
        anomaly_count=len(txn_anomalies),
        report_text="",
        pdf_path=pdf_path
    )

    # Send email
    try:
        send_alert_email(
            recipient=recipient,
            customer_name=cust["full_name"],
            txn_id=txn_id,
            risk_level=risk_level,
            anomaly_details=txn_anomalies,
            amount=float(txn["transaction_amount"]),
            merchant=merchant_name,
            timestamp=txn["transaction_timestamp"],
            location=txn["transaction_location"],
            pdf_path=pdf_path if pdf_path else None
        )
        log_email(inv_id, recipient, cust["full_name"], txn_id,
                  f"Alert: Suspicious Transaction {txn_id}", "SENT")
        return jsonify({"success": True, "message": f"Alert email sent to {recipient}",
                        "investigation_id": inv_id})
    except Exception as e:
        log_email(inv_id, recipient, cust["full_name"], txn_id,
                  f"Alert: {txn_id}", "FAILED", str(e))
        return jsonify({"error": f"Email failed: {str(e)}"}), 500


@app.route("/api/investigation_history", methods=["GET"])
def api_investigation_history():
    conn = get_db()
    rows = conn.execute(
        "SELECT i.*, e.status as email_status, e.sent_at as email_sent_at "
        "FROM investigations i LEFT JOIN email_logs e ON e.investigation_id = i.id "
        "ORDER BY i.created_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/email_logs", methods=["GET"])
def api_email_logs():
    conn = get_db()
    rows = conn.execute("SELECT * FROM email_logs ORDER BY sent_at DESC LIMIT 100").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/generate_report/<txn_id>", methods=["GET"])
def api_generate_report_for_txn(txn_id):
    """Generate & stream PDF for a specific transaction."""
    try:
        txn_row = transactions_df[transactions_df["transaction_uuid"] == txn_id]
        if txn_row.empty:
            return jsonify({"error": "Transaction not found"}), 404
        txn = txn_row.iloc[0].to_dict()
        # Replace NaN with empty string in raw dicts passed to PDF functions
        txn = {k: (v if not (isinstance(v, float) and math.isnan(v)) else "") for k, v in txn.items()}

        cust, txns, anomalies = detect_anomalies(customer_uuid=txn["customer_uuid"])
        if cust is None:
            return jsonify({"error": "Customer not found"}), 404

        # Sanitize customer dict
        cust = {k: (v if not (isinstance(v, float) and math.isnan(v)) else "") for k, v in cust.items()}

        # Generate or fallback report text
        try:
            report_text = generate_investigation_report(cust, txns, anomalies)
        except Exception:
            risk_level = get_risk_level(anomalies)
            report_text = (
                f"ClearTrace Investigation Report\n"
                f"Customer: {cust.get('full_name','N/A')}\n"
                f"Transaction: {txn_id}\n"
                f"Risk Level: {risk_level}\n"
                f"Anomalies Detected: {len(anomalies)}\n\n"
                f"Note: AI report generation requires a Gemini API key. "
                f"This is a system-generated summary.\n\n"
                f"Recommended Action: " + (
                    "Block transaction immediately and freeze account." if risk_level in ("CRITICAL","HIGH")
                    else "Flag for enhanced monitoring and contact customer."
                )
            )

        filepath, filename = generate_pdf(cust, txns, anomalies, report_text)
        return send_file(filepath, as_attachment=True, download_name=filename,
                         mimetype="application/pdf")
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500


@app.route("/customer_summary")
def customer_summary_page():
    return send_from_directory(".", "customer_summary.html")

@app.route("/api/investigate/customer/<cust_id>", methods=["GET"])
def api_investigate_customer(cust_id):
    cust, txns, anomalies = detect_anomalies(customer_uuid=cust_id)
    if not cust:
        return jsonify({"error": "Customer not found"}), 404
        
    risk_level = get_risk_level(anomalies)
    overall_risk_score = max((a["risk_score"] for a in anomalies), default=0)

    # Sanitize inputs
    cust = {k: (v if not (isinstance(v, float) and math.isnan(v)) else None) for k, v in cust.items()}
    
    # Generate AI report
    try:
        report_text = generate_investigation_report(cust, txns, anomalies)
    except Exception:
        report_text = (
            f"AI analysis unavailable — set a Gemini API key for full reports.\n\n"
            f"Customer: {cust.get('full_name','N/A')} | "
            f"Risk Level: {risk_level} | Anomalies: {len(anomalies)}"
        )

    # Get recent transactions for the customer
    cust_txns = transactions_df[transactions_df["customer_uuid"] == cust["customer_uuid"]].copy()
    cust_txn_list = cust_txns.sort_values("transaction_timestamp", ascending=False).head(20).to_dict("records")
    
    # Enrich with merchant names
    for t in cust_txn_list:
        m = merchants_df[merchants_df["merchant_uuid"] == t.get("merchant_uuid","")]
        t["merchant_name"] = m.iloc[0]["merchant_name"] if not m.empty else "Unknown"
        
    return jsonify(sanitize_nan({
        "customer": cust,
        "all_customer_txns": cust_txn_list,
        "anomalies": anomalies,
        "all_anomalies_count": len(anomalies),
        "overall_risk_score": overall_risk_score,
        "risk_level": risk_level,
        "ai_report": report_text,
        "total_txns_analyzed": len(txns)
    }))

@app.route("/api/generate_customer_report/<cust_id>", methods=["GET"])
def api_generate_customer_report(cust_id):
    try:
        cust, txns, anomalies = detect_anomalies(customer_uuid=cust_id)
        if not cust:
            return jsonify({"error": "Customer not found"}), 404

        cust = {k: (v if not (isinstance(v, float) and math.isnan(v)) else "") for k, v in cust.items()}

        try:
            report_text = generate_investigation_report(cust, txns, anomalies)
        except Exception:
            risk_level = get_risk_level(anomalies)
            report_text = (
                f"ClearTrace Customer Investigation Report\n"
                f"Customer: {cust.get('full_name','N/A')}\n"
                f"Risk Level: {risk_level}\n"
                f"Anomalies Detected: {len(anomalies)}\n\n"
                f"System-generated summary."
            )

        filepath, filename = generate_pdf(cust, txns, anomalies, report_text)
        return send_file(filepath, as_attachment=True, download_name=filename, mimetype="application/pdf")
    except Exception as e:
        return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500

def send_email(receiver_email, subject, message, attachment_path=None):
    if not receiver_email or not subject or not message:
        raise ValueError("Missing required email fields")
        
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = receiver_email
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(attachment_path)}")
            msg.attach(part)

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Email failed: {e}")
        raise e

@app.route("/api/send_customer_alert", methods=["POST"])
def api_send_customer_alert():
    data = request.json
    cust_id = data.get("customer_uuid")
    recipient = data.get("recipient_email")
    if not cust_id or not recipient:
        return jsonify({"error": "Missing parameters"}), 400
        
    try:
        cust, txns, anomalies = detect_anomalies(customer_uuid=cust_id)
        cust = {k: (v if not (isinstance(v, float) and math.isnan(v)) else "") for k, v in cust.items()}
        try:
            report_text = generate_investigation_report(cust, txns, anomalies)
        except:
            report_text = "See attached PDF for details."
            
        filepath, _ = generate_pdf(cust, txns, anomalies, report_text)
        
        subject = f"ClearTrace Security Alert: Account Activity Review for {cust.get('full_name')}"
        body = f"Dear {cust.get('full_name')},\n\nWe have detected anomalous behaviour on your account. Please review the attached security report.\n\nClearTrace Fraud Prevention"
        send_email(recipient, subject, body, attachment_path=filepath)
        return jsonify({"success": True, "message": "Email sent"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chatbot/query", methods=["POST"])
def api_chatbot_query():
    global gemini_model
    data = request.json
    message = data.get("message", "").strip()
    
    if not message:
        return jsonify({"error": "Empty message"}), 400

    # ── Handle API Key Setup ──
    if message.lower().startswith("setkey:"):
        key = message.split(":", 1)[1].strip()
        if init_gemini(key):
            return jsonify({
                "success": True,
                "reply": "✅ **Gemini API key configured successfully!** Start asking me any investigation questions!",
                "entities_found": []
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to configure API key. Please check and try again."
            }), 400

    context = ""
    found_entities = []

    # 1. Search for customer by name, upi, or email
    search_term = message.lower()
    match_cust = customers_df[
        (customers_df["full_name"].str.lower().str.contains(search_term, na=False)) |
        (customers_df["upi_id"].str.lower().str.contains(search_term, na=False)) |
        (customers_df["email"].str.lower().str.contains(search_term, na=False))
    ]

    if not match_cust.empty:
        for _, row in match_cust.head(3).iterrows():
            cust_uuid = row["customer_uuid"]
            cust, txns, anomalies = detect_anomalies(customer_uuid=cust_uuid)
            risk_level = get_risk_level(anomalies)
            found_entities.append(f"Customer: {row['full_name']} (UPI: {row['upi_id']}, Risk: {risk_level})")
            context += f"\nData for Customer {row['full_name']}:\n"
            context += f"- UUID: {cust_uuid}\n- Risk Level: {risk_level}\n- Anomalies Detected: {len(anomalies)}\n"
            recent = transactions_df[transactions_df["customer_uuid"] == cust_uuid].head(5)
            for idx, (_, txn) in enumerate(recent.iterrows(), 1):
                context += f"  {idx}. {txn['transaction_uuid']}: ₹{txn['transaction_amount']} ({txn['transaction_status']})\n"

    import re
    
    # 2. Search for specific transaction ID (TXNxxxxxx)
    txn_ids = re.findall(r'TXN\d+', message.upper())
    for tid in txn_ids:
        t_row = transactions_df[transactions_df["transaction_uuid"] == tid]
        if not t_row.empty:
            t_data = t_row.iloc[0]
            found_entities.append(f"Transaction: {tid}")
            context += f"\nTransaction {tid} Details:\n"
            context += f"- Amount: ₹{t_data['transaction_amount']}\n"
            context += f"- Status: {t_data['transaction_status']}\n"
            context += f"- Type: {t_data['transaction_type']}\n"
            context += f"- Timestamp: {t_data['transaction_timestamp']}\n"

    # 3. Search for specific Cheque ID (CHQxxxxxx)
    chq_ids = re.findall(r'CHQ\d+', message.upper())
    for cid in chq_ids:
        if cheques_df is not None:
            c_row = cheques_df[cheques_df["cheque_number"] == cid]
            if not c_row.empty:
                c_data = c_row.iloc[0]
                found_entities.append(f"Cheque: {cid}")
                context += f"\nCheque {cid} Details:\n"
                context += f"- Issuer: {c_data['issuer_name']}\n"
                context += f"- Beneficiary: {c_data['beneficiary_name']}\n"
                context += f"- Amount: ₹{c_data['cheque_amount']}\n"
                context += f"- Tampered: {c_data.get('is_tampered', False)}\n"
                if c_data.get('is_tampered'):
                    context += f"- Tamper Type: {c_data.get('tamper_type', 'Unknown')}\n"
    
    # 4. Search for cheques by Issuer/Beneficiary name
    if cheques_df is not None:
        match_chq = cheques_df[
            (cheques_df["issuer_name"].str.lower().str.contains(search_term, na=False)) |
            (cheques_df["beneficiary_name"].str.lower().str.contains(search_term, na=False))
        ]
        if not match_chq.empty:
            for _, row in match_chq.head(3).iterrows():
                found_entities.append(f"Cheque: {row['cheque_number']}")
                context += f"\nCheque {row['cheque_number']} (Issuer: {row['issuer_name']})\n"
                context += f"- Beneficiary: {row['beneficiary_name']}\n"
                context += f"- Amount: ₹{row['cheque_amount']}\n"

    # Generate response
    try:
        if gemini_model:
            # Use Gemini AI if configured
            full_prompt = (
                "You are ClearTrace AI, a forensic fraud assistant. You analyze UPI anomalies and Cheque tampering cases.\n"
                "Here is the context data I found in the system:\n"
                f"{context if context else 'No matching records found in database.'}\n\n"
                f"User Query: {message}\n\n"
                "Provide a professional, clear response based on the data above. If no data was found, answer generally but professionally. "
                "If a cheque has 'Tampered: True', highlight the 'Tamper Type' and explain the risk."
            )
            response = gemini_model.generate_content(full_prompt)
            return jsonify({
                "success": True, 
                "reply": response.text,
                "entities_found": found_entities
            })
        else:
            # Fallback response without Gemini
            if context:
                reply = f"📋 **Investigation Results** ({len(found_entities)} entities found):\n\n{context}\n\n"
                reply += "_To enable AI-powered insights, run: **setkey:YOUR_GEMINI_API_KEY**_"
            else:
                reply = "No matching records found for your query. Try:\n- Enter a customer name or UPI ID\n- Search for a transaction (TXN12345)\n- Search for a cheque (CHQ12345)\n\nTo enhance responses with AI insights, configure your Gemini API key: **setkey:YOUR_API_KEY**"
            
            return jsonify({
                "success": True,
                "reply": reply,
                "entities_found": found_entities
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  ClearTrace – Investigation System")
    print("="*60)
    print(f"  Customers loaded:    {len(customers_df)}")
    print(f"  Merchants loaded:    {len(merchants_df)}")
    print(f"  Transactions loaded: {len(transactions_df)}")
    if GEMINI_API_KEY:
        print("  GenAI:               ✓ Gemini configured")
    else:
        print("  GenAI:               ✗ Set GEMINI_API_KEY or use 'setkey:YOUR_KEY' in chat")
    print("="*60)
    print("  Open http://localhost:5000 in your browser")
    print("="*60 + "\n")
    app.run(debug=True, port=5000)
