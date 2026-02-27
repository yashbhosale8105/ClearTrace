"""
ClearTrace – Enriched Dataset Generator
Generates realistic Indian banking sample data with full attribute sets for the hackathon.
"""

import csv
import os
import random
import string
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

random.seed(42)

# ── Indian Names ──
FIRST_NAMES_M = ["Rahul","Amit","Vikram","Arjun","Suresh","Rajesh","Karan","Nikhil","Deepak","Anil",
                 "Manish","Sanjay","Ravi","Pradeep","Manoj","Gaurav","Rohit","Vivek","Sachin","Ashish",
                 "Harish","Dinesh","Ramesh","Naresh","Rakesh","Satish","Girish","Kamlesh","Mahesh","Umesh"]
FIRST_NAMES_F = ["Priya","Sneha","Anjali","Pooja","Neha","Kavita","Swati","Megha","Ritika","Sunita",
                 "Divya","Nisha","Shreya","Aarti","Komal","Tanvi","Simran","Pallavi","Jyoti","Ananya",
                 "Rekha","Geeta","Seema","Meena","Usha","Lata","Sita","Radha","Meera","Vandana"]
LAST_NAMES = ["Sharma","Verma","Patel","Singh","Kumar","Gupta","Joshi","Mehta","Shah","Reddy",
              "Nair","Iyer","Bose","Das","Rao","Deshmukh","Pillai","Chauhan","Tiwari","Mishra",
              "Yadav","Sinha","Saxena","Tripathi","Pandey","Shukla","Agarwal","Malhotra","Kapoor","Chandra"]

OCCUPATIONS = ["Software Engineer","Doctor","Teacher","Business Owner","Government Employee","Banker",
               "Lawyer","Accountant","Nurse","Retired","Student","Freelancer","Trader","Farmer",
               "Police Officer","Engineer","Professor","Pharmacist","Architect","Consultant"]

BANK_ACCOUNT_TYPES = ["Savings","Current","Salary","NRI"]
KYC_STATUSES = ["COMPLETE","COMPLETE","COMPLETE","PENDING","FAILED"]
RISK_TIERS = ["LOW","LOW","MEDIUM","MEDIUM","HIGH"]

# ── Banks & IFSC ──
BANKS = [
    ("State Bank of India","SBIN"),("HDFC Bank","HDFC"),("ICICI Bank","ICIC"),
    ("Axis Bank","UTIB"),("Kotak Mahindra Bank","KKBK"),("Punjab National Bank","PUNB"),
    ("Bank of Baroda","BARB"),("Canara Bank","CNRB"),("Union Bank of India","UBIN"),
    ("IndusInd Bank","INDB"),("Yes Bank","YESB"),("Federal Bank","FDRL")
]

UPI_SUFFIXES = ["@okaxis","@oksbi","@okhdfcbank","@okicici","@paytm","@ybl","@upi","@ibl","@kotak","@axl"]

CITIES = ["Mumbai","Delhi","Bangalore","Chennai","Hyderabad","Pune","Kolkata","Ahmedabad","Jaipur","Lucknow",
          "Surat","Nagpur","Indore","Bhopal","Patna","Vadodara","Coimbatore","Kochi","Chandigarh","Goa"]

STATES = {
    "Mumbai":"Maharashtra","Delhi":"Delhi","Bangalore":"Karnataka","Chennai":"Tamil Nadu",
    "Hyderabad":"Telangana","Pune":"Maharashtra","Kolkata":"West Bengal","Ahmedabad":"Gujarat",
    "Jaipur":"Rajasthan","Lucknow":"Uttar Pradesh","Surat":"Gujarat","Nagpur":"Maharashtra",
    "Indore":"Madhya Pradesh","Bhopal":"Madhya Pradesh","Patna":"Bihar","Vadodara":"Gujarat",
    "Coimbatore":"Tamil Nadu","Kochi":"Kerala","Chandigarh":"Punjab","Goa":"Goa"
}

BRANCHES = ["{city} Main Branch","{city} MG Road Branch","{city} Station Road Branch",
            "{city} Civil Lines Branch","{city} Cantonment Branch"]

MERCHANT_NAMES = [
    "Amazon Seller Services","Flipkart Internet","Swiggy Delivery","Zomato Online",
    "BigBasket Daily","PhonePe Merchant","Myntra Fashion","Reliance Digital",
    "DMart Ready","Uber India","Ola Cabs","BookMyShow","MakeMyTrip","IRCTC",
    "Jio Recharge","Paytm Mall","Meesho Seller","Nykaa Beauty","1mg Pharmacy",
    "BigDeal Electronics","FreshKart Grocery","FastBus Travels","RailYatri","HotelEasy India"
]

MERCHANT_CATEGORIES = {
    "Amazon Seller Services":"E-Commerce","Flipkart Internet":"E-Commerce","Swiggy Delivery":"Food & Dining",
    "Zomato Online":"Food & Dining","BigBasket Daily":"Grocery","PhonePe Merchant":"Digital Wallet",
    "Myntra Fashion":"Fashion","Reliance Digital":"Electronics","DMart Ready":"Grocery",
    "Uber India":"Transport","Ola Cabs":"Transport","BookMyShow":"Entertainment",
    "MakeMyTrip":"Travel","IRCTC":"Travel","Jio Recharge":"Telecom","Paytm Mall":"E-Commerce",
    "Meesho Seller":"E-Commerce","Nykaa Beauty":"Beauty & Health","1mg Pharmacy":"Healthcare",
    "BigDeal Electronics":"Electronics","FreshKart Grocery":"Grocery","FastBus Travels":"Travel",
    "RailYatri":"Travel","HotelEasy India":"Travel"
}

TRANSACTION_TYPES = ["DEBIT","DEBIT","DEBIT","CREDIT","REFUND"]
TRANSACTION_MODES = ["UPI","UPI","UPI","NEFT","IMPS"]
TRANSACTION_STATUSES = ["SUCCESS","SUCCESS","SUCCESS","SUCCESS","FAILED","PENDING"]
FAILURE_REASONS = ["INSUFFICIENT_FUNDS","BANK_DECLINED","NETWORK_TIMEOUT","INVALID_UPI_PIN","DAILY_LIMIT_EXCEEDED",""]

EMAIL_DOMAINS = ["gmail.com","yahoo.co.in","outlook.com","hotmail.com","rediffmail.com","protonmail.com"]

DEVICE_BRANDS = ["Samsung","OnePlus","Xiaomi Redmi","Apple iPhone","Vivo","Oppo","Realme","Nokia","Motorola"]
OS_TYPES = ["Android 13","Android 12","Android 11","iOS 16","iOS 17","Android 14"]

# ───────────────────────────────────────────────
# Utility functions
# ───────────────────────────────────────────────
def gen_phone():
    return f"9{random.randint(100000000,999999999)}"

def gen_device_id():
    return f"DEV{random.randint(10000,99999)}"

def gen_device_model():
    return f"{random.choice(DEVICE_BRANDS)} ({random.choice(OS_TYPES)})"

def gen_ip():
    return f"{random.choice(['192.168','10.0','172.16'])}.{random.randint(1,254)}.{random.randint(1,254)}"

def gen_account_number():
    return ''.join([str(random.randint(0,9)) for _ in range(11)])

def gen_ifsc(bank_code):
    return f"{bank_code}0{random.randint(100,999):03d}"

def gen_upi_id(name):
    first = name.split()[0].lower()
    num = random.randint(1,99)
    suffix = random.choice(UPI_SUFFIXES)
    return f"{first}{num}{suffix}"

def gen_email(name):
    first = name.split()[0].lower()
    last = name.split()[-1].lower()
    num = random.randint(1,99)
    domain = random.choice(EMAIL_DOMAINS)
    style = random.choice([
        f"{first}.{last}{num}",
        f"{first}{last}{num}",
        f"{first}{num}",
        f"{last}.{first}",
    ])
    return f"{style}@{domain}"

def gen_pan():
    letters = ''.join(random.choices(string.ascii_uppercase, k=5))
    digits  = ''.join(random.choices(string.digits, k=4))
    last    = random.choice(string.ascii_uppercase)
    return f"{letters}{digits}{last}"

def gen_aadhaar():
    return f"{random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)}"

def gen_gstin(bank_code, state_code="27"):
    return f"{state_code}{bank_code}{random.randint(1000,9999)}Z{random.choice(string.ascii_uppercase)}"

def gen_upi_ref():
    return f"UPI{random.randint(100000000000,999999999999)}"

def random_date(start_year=2018, end_year=2024):
    start = datetime(start_year,1,1)
    end = datetime(end_year,12,31)
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0,delta))).strftime("%Y-%m-%d")

def random_timestamp(base_date=None):
    if base_date is None:
        start = datetime(2025,1,1)
        end = datetime(2026,2,27)
    else:
        start = base_date
        end = base_date + timedelta(hours=24)
    delta = int((end - start).total_seconds())
    ts = start + timedelta(seconds=random.randint(0, delta))
    return ts.strftime("%Y-%m-%d %H:%M:%S")


# ───────────────────────────────────────────────
# Generate Customers (enriched)
# ───────────────────────────────────────────────
def generate_customers(n=40):
    customers = []
    used_phones = set()
    used_accounts = set()

    for i in range(1, n+1):
        gender = random.choice(["Male","Male","Female","Female","Female"])
        if gender == "Male":
            first = random.choice(FIRST_NAMES_M)
        else:
            first = random.choice(FIRST_NAMES_F)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"

        bank_name, bank_code = random.choice(BANKS)
        city = random.choice(CITIES)
        state = STATES[city]
        branch = random.choice(BRANCHES).format(city=city)
        balance = round(random.uniform(5000, 500000), 2)
        total_txn_count = random.randint(10, 500)
        total_txn_amt = round(random.uniform(10000, 2000000), 2)
        last_txn_amt = round(random.uniform(100, 50000), 2)
        age = random.randint(18, 68)

        # Unique phone
        phone = gen_phone()
        while phone in used_phones:
            phone = gen_phone()
        used_phones.add(phone)

        # Unique account number
        acct = gen_account_number()
        while acct in used_accounts:
            acct = gen_account_number()
        used_accounts.add(acct)

        monthly_avg_txn = round(total_txn_amt / max(total_txn_count, 1), 2)
        daily_txn_limit = random.choice([10000, 25000, 50000, 100000, 200000])
        is_blocked = random.random() < 0.05  # 5% chance blocked

        customer = {
            # ── Identity ──
            "customer_uuid":            f"CUST{i:03d}",
            "full_name":                name,
            "gender":                   gender,
            "age":                      age,
            "date_of_birth":            f"{2026-age}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "occupation":               random.choice(OCCUPATIONS),
            "email":                    gen_email(name),
            "registered_phone_number":  phone,
            "pan_number":               gen_pan(),
            "aadhaar_last4":            str(random.randint(1000,9999)),
            "kyc_status":               random.choice(KYC_STATUSES),
            "risk_tier":                random.choice(RISK_TIERS),
            # ── UPI / Bank ──
            "upi_id":                   gen_upi_id(name),
            "bank_name":                bank_name,
            "account_number":           acct,
            "account_type":             random.choice(BANK_ACCOUNT_TYPES),
            "ifsc_code":                gen_ifsc(bank_code),
            "home_branch":              branch,
            "city":                     city,
            "state":                    state,
            # ── Device / Network ──
            "registered_device_id":     gen_device_id(),
            "registered_device_model":  gen_device_model(),
            "registered_ip_address":    gen_ip(),
            # ── Financials ──
            "account_balance":          balance,
            "last_transaction_amount":  last_txn_amt,
            "total_transactions_count": total_txn_count,
            "total_transactions_amount":total_txn_amt,
            "monthly_avg_transaction":  monthly_avg_txn,
            "daily_transaction_limit":  daily_txn_limit,
            "account_open_date":        random_date(2013, 2023),
            "is_account_blocked":       str(is_blocked),
            "last_login_timestamp":     random_timestamp(),
        }
        customers.append(customer)
    return customers


# ───────────────────────────────────────────────
# Generate Merchants (enriched)
# ───────────────────────────────────────────────
def generate_merchants(n=20):
    merchants = []
    names = MERCHANT_NAMES[:n] if n <= len(MERCHANT_NAMES) else MERCHANT_NAMES + [f"Merchant_{j}" for j in range(len(MERCHANT_NAMES)+1, n+1)]

    for i, name in enumerate(names[:n], 1):
        bank_name, bank_code = random.choice(BANKS)
        city = random.choice(CITIES)
        state = STATES[city]
        category = MERCHANT_CATEGORIES.get(name, "General")
        open_date = random_date(2013, 2022)
        avg_monthly_vol = round(random.uniform(50000, 5000000), 2)

        merchant = {
            # ── Identity ──
            "merchant_uuid":                f"MER{i:03d}",
            "merchant_name":                name,
            "merchant_category":            category,
            "merchant_gstin":               gen_gstin(bank_code),
            "merchant_rating":              round(random.uniform(3.0, 5.0), 1),
            "is_verified":                  str(random.random() > 0.1),  # 90% verified
            # ── UPI / Bank ──
            "merchant_upi_id":              name.split()[0].lower() + random.choice(UPI_SUFFIXES),
            "merchant_bank_name":           bank_name,
            "merchant_account_number":      gen_account_number(),
            "merchant_ifsc_code":           gen_ifsc(bank_code),
            "merchant_bank_branch":         random.choice(BRANCHES).format(city=city),
            "merchant_bank_address":        f"{city}, {state}, India",
            "merchant_account_open_date":   open_date,
            # ── Operations ──
            "merchant_city":                city,
            "merchant_state":               state,
            "avg_monthly_volume":           avg_monthly_vol,
            "total_transactions_count":     random.randint(500, 50000),
            "refund_rate_percent":          round(random.uniform(0.5, 8.0), 2),
            "chargeback_count":             random.randint(0, 25),
        }
        merchants.append(merchant)
    return merchants


# ───────────────────────────────────────────────
# Generate Transactions (enriched, with anomalies)
# ───────────────────────────────────────────────
def generate_transactions(customers, merchants, n=80):
    transactions = []
    anomaly_count = int(n * 0.20)  # 20% anomalous
    anomaly_indices = set(random.sample(range(n), anomaly_count))

    for i in range(1, n+1):
        cust = random.choice(customers)
        merch = random.choice(merchants)
        is_anomaly = (i-1) in anomaly_indices

        # Base values
        device_id = cust["registered_device_id"]
        device_model = cust["registered_device_model"]
        ip_addr = cust["registered_ip_address"]
        location = cust["city"]
        amount = round(random.uniform(50, 25000), 2)
        txn_type = random.choice(["DEBIT","DEBIT","DEBIT","CREDIT"])
        status = "SUCCESS"
        failure_reason = ""
        anomaly_flag = "NONE"

        if is_anomaly:
            anomaly_type = random.choice([
                "device_mismatch","ip_mismatch","high_amount",
                "unusual_location","rapid_fire","exceeds_balance",
                "multiple_anomaly"
            ])
            anomaly_flag = anomaly_type.upper()

            if anomaly_type == "device_mismatch":
                device_id = gen_device_id()
                device_model = f"{random.choice(DEVICE_BRANDS)} (Unknown OS)"

            elif anomaly_type == "ip_mismatch":
                ip_addr = gen_ip()

            elif anomaly_type == "high_amount":
                amount = round(random.uniform(80000, 300000), 2)

            elif anomaly_type == "unusual_location":
                home_city = cust["city"]
                other_cities = [c for c in CITIES if c != home_city]
                location = random.choice(other_cities)

            elif anomaly_type == "exceeds_balance":
                amount = round(float(cust["account_balance"]) * random.uniform(1.1, 3.0), 2)
                status = random.choice(["SUCCESS","FAILED"])
                if status == "FAILED":
                    failure_reason = "INSUFFICIENT_FUNDS"

            elif anomaly_type == "rapid_fire":
                amount = round(random.uniform(500, 10000), 2)

            elif anomaly_type == "multiple_anomaly":
                device_id = gen_device_id()
                ip_addr = gen_ip()
                home_city = cust["city"]
                other_cities = [c for c in CITIES if c != home_city]
                location = random.choice(other_cities)
                amount = round(random.uniform(60000, 200000), 2)

        # Random failure for normal txns too (2% rate)
        if status == "SUCCESS" and random.random() < 0.02:
            status = random.choice(["FAILED","PENDING"])
            if status == "FAILED":
                failure_reason = random.choice(FAILURE_REASONS[:-1])

        latency_ms = random.randint(80, 4000) if status == "SUCCESS" else random.randint(200, 8000)

        txn = {
            # ── Keys ──
            "transaction_uuid":         f"TXN{i:03d}",
            "customer_uuid":            cust["customer_uuid"],
            "merchant_uuid":            merch["merchant_uuid"],
            "upi_reference_id":         gen_upi_ref(),
            # ── Transaction ──
            "transaction_type":         txn_type,
            "transaction_mode":         random.choice(TRANSACTION_MODES),
            "transaction_amount":       amount,
            "currency":                 "INR",
            "transaction_timestamp":    random_timestamp(),
            "transaction_location":     location,
            "transaction_status":       status,
            "failure_reason":           failure_reason,
            "response_latency_ms":      latency_ms,
            # ── Device / Network at time of txn ──
            "customer_device_id":       device_id,
            "customer_device_model":    device_model,
            "customer_ip_address":      ip_addr,
            "customer_upi_app":         random.choice(["PhonePe","GPay","Paytm","BHIM","Amazon Pay","WhatsApp Pay"]),
            # ── Risk ──
            "anomaly_flag":             anomaly_flag,
            "is_international":         str(random.random() < 0.02),
            "merchant_vpa":             merch["merchant_upi_id"],
        }
        transactions.append(txn)
    return transactions


# ───────────────────────────────────────────────
# Generate Cheque Images (enriched)
# ───────────────────────────────────────────────
def generate_cheque_images(customers, n=15, output_dir="dataset/cheques/cheque_images"):
    os.makedirs(output_dir, exist_ok=True)
    cheque_data = []

    all_names = FIRST_NAMES_M + FIRST_NAMES_F
    for i in range(1, n+1):
        cust = random.choice(customers)
        beneficiary_first = random.choice(all_names)
        beneficiary_last  = random.choice(LAST_NAMES)
        beneficiary = f"{beneficiary_first} {beneficiary_last}"
        amount = round(random.uniform(5000, 200000), 2)
        date = random_date(2025, 2026)
        cheque_no = f"CHQ{i:06d}"

        # Introduce ~20% tampered cheques
        is_tampered = random.random() < 0.20
        tamper_type = ""
        if is_tampered:
            tamper_type = random.choice(["ACCOUNT_MISMATCH","IFSC_MISMATCH","AMOUNT_ALTERED","SIGNATURE_MISSING"])

        display_acct  = cust["account_number"]
        display_ifsc  = cust["ifsc_code"]
        display_name  = cust["full_name"]
        display_amount= amount

        if tamper_type == "ACCOUNT_MISMATCH":
            display_acct = gen_account_number()
        elif tamper_type == "IFSC_MISMATCH":
            _, fake_code = random.choice(BANKS)
            display_ifsc = gen_ifsc(fake_code)
        elif tamper_type == "AMOUNT_ALTERED":
            display_amount = round(amount * random.uniform(1.5, 5.0), 2)
        elif tamper_type == "SIGNATURE_MISSING":
            display_name = "NO SIGNATURE"

        # ── Draw cheque ──
        img = Image.new('RGB', (960, 420), '#FFFEF5')
        draw = ImageDraw.Draw(img)

        # Outer border
        draw.rectangle([6, 6, 953, 413], outline='#8B7355', width=3)
        draw.rectangle([10, 10, 949, 409], outline='#C4A882', width=1)

        # Header band
        draw.rectangle([10, 10, 949, 72], fill='#1C3557')
        # Watermark-style lines in header
        for x in range(10, 950, 30):
            draw.line([(x, 10), (x+15, 72)], fill='#234573', width=1)

        try:
            font_xl   = ImageFont.truetype("arial.ttf", 24)
            font_lg   = ImageFont.truetype("arial.ttf", 18)
            font_md   = ImageFont.truetype("arial.ttf", 14)
            font_sm   = ImageFont.truetype("arial.ttf", 11)
        except:
            font_xl = font_lg = font_md = font_sm = ImageFont.load_default()

        # Bank name + logo area
        draw.text((28, 22), cust["bank_name"].upper(), fill='#FFFFFF', font=font_xl)
        draw.text((28, 52), f"Branch: {cust['home_branch']}", fill='#A8C4E0', font=font_sm)
        draw.text((740, 30), "ACCOUNT PAYEE ONLY", fill='#FFD700', font=font_sm)
        draw.text((780, 48), "NON-NEGOTIABLE",      fill='#FFD700', font=font_sm)

        # Cheque number & date
        draw.text((28, 85),  f"Cheque No: {cheque_no}", fill='#444', font=font_sm)
        draw.text((700, 85), f"Date:", fill='#666', font=font_sm)
        draw.rectangle([740, 82, 940, 102], outline='#999', width=1)
        draw.text((745, 85), date, fill='#1C3557', font=font_md)

        # Pay to line
        draw.text((28, 118), "Pay to:", fill='#888', font=font_sm)
        draw.text((95, 115), beneficiary, fill='#111', font=font_lg)
        draw.line([(95, 136), (650, 136)], fill='#CCC', width=1)
        draw.text((660, 118), "or Bearer", fill='#888', font=font_sm)

        # Amount in words
        draw.text((28, 155), "Rupees:", fill='#888', font=font_sm)
        draw.text((95, 152), f"{int(display_amount):,} Rupees Only", fill='#111', font=font_lg)
        draw.line([(95, 172), (700, 172)], fill='#CCC', width=1)

        # Amount box
        draw.rectangle([720, 148, 940, 178], outline='#1C3557', width=2)
        draw.text((728, 153), f"Rs. {display_amount:,.2f}", fill='#1C3557', font=font_lg)

        # Account details
        draw.rectangle([28, 195, 440, 265], outline='#DDD', width=1)
        draw.text((35, 200), f"Account No : {display_acct}", fill='#222', font=font_md)
        draw.text((35, 220), f"IFSC Code  : {display_ifsc}", fill='#222', font=font_md)
        draw.text((35, 240), f"Bank       : {cust['bank_name']}", fill='#555', font=font_sm)

        # MICR band
        draw.rectangle([10, 330, 949, 375], fill='#F5F0E8')
        micr_text = f"  ⑆{display_ifsc}⑆  ⑆{display_acct}⑆  {cheque_no}  "
        draw.text((28, 340), micr_text, fill='#333', font=font_md)

        # Signature area
        draw.line([(600, 305), (930, 305)], fill='#BBB', width=1)
        if tamper_type != "SIGNATURE_MISSING":
            # Simple squiggly signature
            sig_x = 650
            for j in range(15):
                y_off = 285 + (5 if j % 2 == 0 else -5)
                draw.ellipse([(sig_x+j*15-4, y_off-4), (sig_x+j*15+4, y_off+4)], outline='#224', width=1)
        draw.text((650, 308), "Authorised Signatory", fill='#888', font=font_sm)
        draw.text((650, 290), display_name, fill='#1C3557', font=font_sm)

        # Tamper watermark
        if is_tampered:
            draw.text((300, 190), "⚠ FLAGGED", fill=(220, 60, 60, 120), font=font_xl)

        filepath = os.path.join(output_dir, f"cheque_{i:03d}.png")
        img.save(filepath)

        cheque_data.append({
            "filename":           f"cheque_{i:03d}.png",
            "cheque_number":      cheque_no,
            "issuer_name":        cust["full_name"],
            "beneficiary_name":   beneficiary,
            "account_number":     cust["account_number"],
            "ifsc_code":          cust["ifsc_code"],
            "bank_name":          cust["bank_name"],
            "amount":             amount,
            "date":               date,
            "customer_uuid":      cust["customer_uuid"],
            # Displayed (may differ if tampered)
            "displayed_account":  display_acct,
            "displayed_ifsc":     display_ifsc,
            "displayed_amount":   display_amount,
            "is_tampered":        str(is_tampered),
            "tamper_type":        tamper_type if is_tampered else "NONE",
        })
        print(f"  {'⚠' if is_tampered else '✓'} Generated cheque_{i:03d}.png  {'[TAMPERED: '+tamper_type+']' if is_tampered else ''}")

    return cheque_data


# ───────────────────────────────────────────────
# CSV writer
# ───────────────────────────────────────────────
def save_csv(data, filepath, fieldnames):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    print(f"  ✓ Saved {filepath}  ({len(data)} records)")


# ───────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────
def main():
    print("=" * 60)
    print("ClearTrace – Enriched Dataset Generator")
    print("Dataweb Hackathon 2026 – GenAI Track")
    print("=" * 60)

    print("\n[1/4] Generating customers (40)...")
    customers = generate_customers(40)
    save_csv(customers, "dataset/upi/upi_customers.csv", list(customers[0].keys()))

    print("\n[2/4] Generating merchants (20)...")
    merchants = generate_merchants(20)
    save_csv(merchants, "dataset/upi/upi_merchants.csv", list(merchants[0].keys()))

    print("\n[3/4] Generating transactions (80)...")
    transactions = generate_transactions(customers, merchants, 80)
    save_csv(transactions, "dataset/upi/upi_transactions.csv", list(transactions[0].keys()))

    print("\n[4/4] Generating cheque images (15)...")
    cheque_data = generate_cheque_images(customers, 15)
    save_csv(cheque_data, "dataset/cheques/cheque_metadata.csv", list(cheque_data[0].keys()))

    print("\n" + "=" * 60)
    print("✅ Dataset generation complete!")
    print(f"   Customers    : {len(customers)}  records")
    print(f"   Merchants    : {len(merchants)}  records")
    print(f"   Transactions : {len(transactions)} records  (~{int(len(transactions)*0.20)} anomalous)")
    print(f"   Cheques      : {len(cheque_data)}  images   (~{sum(1 for c in cheque_data if c['is_tampered']=='True')} tampered)")
    print("\nNew attributes added:")
    print("  Customers    → gender, occupation, email, PAN, Aadhaar last4, KYC status,")
    print("                 risk tier, account type, city/state, device model, DOB,")
    print("                 daily limit, monthly avg txn, blocked status, last login")
    print("  Merchants    → category, GSTIN, rating, verified flag, city/state,")
    print("                 avg monthly volume, refund rate, chargeback count")
    print("  Transactions → type, mode, UPI ref ID, status, failure reason,")
    print("                 latency ms, device model, UPI app, anomaly flag,")
    print("                 international flag, merchant VPA")
    print("  Cheques      → cheque number, tamper type, displayed vs actual fields")
    print("=" * 60)


if __name__ == "__main__":
    main()
