# app.py
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, date
import os, hashlib, random, string, io
from fpdf import FPDF
import matplotlib.pyplot as plt
import base64
import requests  # for payment / webhook (placeholders)
from pathlib import Path

# -----------------------
# Config / Constants
# -----------------------
DB_FILE = "loans_pro.db"
UPLOAD_FOLDER = "uploads"
ADMIN_DEFAULT = {"phone": "0000000000", "email": "admin@example.com", "password": "admin123"}  # change ASAP
EMAIL_NOTIFICATIONS_ENABLED = False  # set True & configure below to send emails
SMS_NOTIFICATIONS_ENABLED = False
EASYPaisa_ENABLED = False
JAZZCASH_ENABLED = False

# Email/SMS / Payment config placeholders
EMAIL_CONFIG = {
    "smtp_server": "smtp.example.com",
    "smtp_port": 587,
    "username": "you@example.com",
    "password": "REPLACE_WITH_PASSWORD"
}
TWILIO_CONFIG = {
    "account_sid": "TWILIO_SID",
    "auth_token": "TWILIO_TOKEN",
    "from_number": "+1..."  # your Twilio number
}
EASYPAY_CONFIG = {"api_key": "EASY_API_KEY", "sandbox": True}
JAZZPAY_CONFIG = {"api_key": "JAZZ_API_KEY", "sandbox": True}

# -----------------------
# Utilities
# -----------------------
def ensure_folder(p):
    os.makedirs(p, exist_ok=True)

ensure_folder(UPLOAD_FOLDER)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def random_txn():
    return "TXN-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

# -----------------------
# Database Setup & Migration
# -----------------------
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Create users table
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT
)
""")

# Base loans table
c.execute("""
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    father_name TEXT,
    phone TEXT,
    cnic TEXT,
    address TEXT,
    user_image_path TEXT,
    cnic_image_path TEXT,
    amount REAL,
    interest_rate REAL,
    total_payable REAL,
    status TEXT,            -- pending/approved/rejected/paid
    due_date TEXT,
    created_at TEXT,
    payment_status TEXT,    -- Unpaid / Partially Paid / Paid
    receipt_no TEXT,
    installment_plan TEXT   -- JSON string or text describing installments
)
""")
conn.commit()

# helper to add columns safely (migration)
def add_column_if_not_exists(table, column, coltype):
    try:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()
    except Exception:
        pass

# add any future columns here using add_column_if_not_exists if needed

# Create default admin if none exists
def ensure_admin():
    c.execute("SELECT COUNT(*) as cnt FROM users WHERE is_admin=1")
    if c.fetchone()[0] == 0:
        pwd_hash = hash_password(ADMIN_DEFAULT["password"])
        c.execute("INSERT OR IGNORE INTO users (name, phone, email, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  ("Admin", ADMIN_DEFAULT["phone"], ADMIN_DEFAULT["email"], pwd_hash, 1, datetime.utcnow().isoformat()))
        conn.commit()

ensure_admin()

# -----------------------
# Helper Functions
# -----------------------
def save_upload(uploaded_file, folder=UPLOAD_FOLDER):
    if uploaded_file is None:
        return None
    ensure_folder(folder)
    safe_name = f"{int(datetime.utcnow().timestamp())}_{uploaded_file.name}"
    path = os.path.join(folder, safe_name)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path

def calculate_total_simple(principal: float, annual_rate: float, days: int) -> float:
    # simple interest
    interest = (principal * annual_rate * days) / 365.0
    total = principal + interest
    return round(total, 2)

def mask_cnic(cnic):
    # show like 42101-XXXXX-2 (keep first 5 and last 1)
    if not cnic or len(cnic) < 5:
        return "****"
    return cnic[:5] + "-" + "X"*7 + "-" + cnic[-1]

def generate_pdf_agreement(loan_record: dict):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "Loan Agreement", ln=True, align="C")
    pdf.ln(5)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 7, f"Loan ID: {loan_record['id']}")
    pdf.multi_cell(0, 7, f"Borrower Name: {loan_record['name']}")
    pdf.multi_cell(0, 7, f"Father Name: {loan_record.get('father_name','')}")
    pdf.multi_cell(0, 7, f"CNIC: {mask_cnic(loan_record.get('cnic',''))}")
    pdf.multi_cell(0, 7, f"Loan Amount: PKR {loan_record['amount']}")
    pdf.multi_cell(0, 7, f"Total Payable: PKR {loan_record['total_payable']}")
    pdf.multi_cell(0, 7, f"Due Date: {loan_record['due_date']}")
    pdf.ln(10)
    pdf.multi_cell(0, 7, "Terms & Conditions:")
    pdf.multi_cell(0, 6, "1. This is a sample agreement for demo purposes only.")
    pdf.multi_cell(0, 6, "2. The borrower agrees to repay by the due date.")
    pdf.ln(20)
    pdf.multi_cell(0, 7, f"Signed: {loan_record['name']}")
    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return output

def send_email_placeholder(to_email, subject, body):
    # placeholder: implement real SMTP send if EMAIL_NOTIFICATIONS_ENABLED
    if not EMAIL_NOTIFICATIONS_ENABLED:
        st.info(f"(Email not sent) would send to {to_email}: {subject}")
        return False
    # Implement actual SMTP here using EMAIL_CONFIG...
    return True

def send_sms_placeholder(to_number, message):
    if not SMS_NOTIFICATIONS_ENABLED:
        st.info(f"(SMS not sent) would send to {to_number}: {message}")
        return False
    # Implement Twilio logic...
    return True

def create_installment_schedule(principal, annual_rate, days, installments):
    # naive equal installments (simple interest)
    total = calculate_total_simple(principal, annual_rate, days)
    per_inst = round(total / installments, 2)
    schedule = []
    start = date.today()
    interval = int(days / installments) if installments>0 else days
    for i in range(installments):
        d = start + timedelta(days=interval*(i+1))
        schedule.append({"inst_no": i+1, "due_date": d.isoformat(), "amount": per_inst, "paid": False})
    return schedule

def df_from_query(query, params=()):
    return pd.read_sql_query(query, conn, params=params)

# -----------------------
# Streamlit UI & Auth
# -----------------------
st.set_page_config(page_title="Udhar - Pro", layout="wide", page_icon="💼")
st.title("💼 Udhar App — Professional Prototype")

# session_state for auth
if "user" not in st.session_state:
    st.session_state["user"] = None

# Top nav
tabs = ["Home", "Signup / Login"]
if st.session_state["user"]:
    tabs = ["Home", "Dashboard", "Apply Loan", "Repay", "History", "Admin"]
page = st.sidebar.selectbox("Navigation", tabs)

# Quick Home
if page == "Home":
    st.header("Welcome to Udhar App (Professional Demo)")
    st.markdown("""
    Features:
    - Signup / Login
    - Apply with CNIC, father name, images
    - Admin approval with image preview
    - EMI / Installments support
    - Mock Easypaisa / JazzCash hooks
    - Export CSV / Excel, generate PDF agreement/receipt
    - Email/SMS notification placeholders
    """)
    st.markdown("**Note:** This is a demo. Configure EMAIL/SMS/PAYMENT settings for production behavior.")


# Signup / Login
if page == "Signup / Login":
    st.header("Create Account or Login")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("New User - Sign Up")
        with st.form("signup"):
            name = st.text_input("Full Name", key="su_name")
            phone = st.text_input("Phone Number", key="su_phone")
            email = st.text_input("Email (optional)", key="su_email")
            password = st.text_input("Password", type="password", key="su_pass")
            password2 = st.text_input("Confirm Password", type="password", key="su_pass2")
            submit = st.form_submit_button("Create Account")
            if submit:
                if not name or not phone or not password:
                    st.error("Name, phone and password are required.")
                elif password != password2:
                    st.error("Passwords don't match.")
                else:
                    try:
                        c.execute("INSERT INTO users (name, phone, email, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                  (name, phone, email, hash_password(password), 0, datetime.utcnow().isoformat()))
                        conn.commit()
                        st.success("Account created. Please login in the right column.")
                    except sqlite3.IntegrityError as e:
                        st.error("Phone or Email already registered.")

    with col2:
        st.subheader("Login")
        with st.form("login"):
            login_phone = st.text_input("Phone or Email", key="li_user")
            login_pass = st.text_input("Password", type="password", key="li_pass")
            login_btn = st.form_submit_button("Login")
            if login_btn:
                # allow login by phone or email
                c.execute("SELECT * FROM users WHERE phone=? OR email=?", (login_phone, login_phone))
                row = c.fetchone()
                if not row:
                    st.error("User not found.")
                else:
                    if verify_password(login_pass, row[4]):
                        st.session_state["user"] = {"id": row[0], "name": row[1], "phone": row[2], "email": row[3], "is_admin": row[5]}
                        st.success(f"Welcome {row[1]}")
                        st.experimental_rerun()
                    else:
                        st.error("Invalid password.")

# Dashboard for logged-in user
if page == "Dashboard" and st.session_state["user"]:
    u = st.session_state["user"]
    st.header(f"Dashboard — {u['name']}")
    st.write(f"Phone: {u['phone']}  |  Email: {u.get('email','-')}")
    # quick stats
    df_total = df_from_query("SELECT COUNT(*) as total, SUM(amount) as total_amount FROM loans WHERE user_id=?", (u["id"],))
    st.write("Your total applications:", int(df_total["total"][0]) if not df_total.empty else 0)
    user_loans = df_from_query("SELECT * FROM loans WHERE user_id=? ORDER BY created_at DESC", (u["id"],))
    if not user_loans.empty:
        st.dataframe(user_loans[["id","amount","total_payable","status","due_date","payment_status"]])
        # download CSV
        csv = user_loans.to_csv(index=False).encode()
        st.download_button("Download My Loan Data (CSV)", csv, file_name=f"my_loans_{u['phone']}.csv")

# Apply Loan page
if page == "Apply Loan" and st.session_state["user"]:
    st.header("Apply for a Loan")
    with st.form("apply"):
        name = st.text_input("Full Name", value=st.session_state["user"]["name"])
        father = st.text_input("Father Name")
        phone = st.text_input("Phone", value=st.session_state["user"]["phone"])
        cnic = st.text_input("CNIC (12345-1234567-1)")
        address = st.text_area("Address")
        profile = st.file_uploader("Upload Profile Image", type=["jpg","jpeg","png"])
        cnic_img = st.file_uploader("Upload CNIC Image (front/back)", type=["jpg","jpeg","png"])
        amount = st.number_input("Loan Amount (PKR)", min_value=1000.0, step=500.0)
        duration = st.number_input("Duration (days)", min_value=7, max_value=365, value=30)
        rate = st.number_input("Annual Interest Rate (%)", value=10.0)/100
        plan_type = st.selectbox("Repayment Type", ["One-Time", "Installments (EMI)"])
        installments = 0
        inst_json = None
        if plan_type == "Installments (EMI)":
            installments = st.number_input("Number of Installments", min_value=1, max_value=12, value=3)
        sub = st.form_submit_button("Submit Loan Application")
        if sub:
            if not name.strip() or not phone.strip() or not cnic.strip():
                st.error("Name, Phone & CNIC required.")
            else:
                user_img_path = save_upload(profile)
                cnic_img_path = save_upload(cnic_img)
                total = calculate_total_simple(amount, rate, int(duration))
                inst_info = None
                if installments > 1:
                    schedule = create_installment_schedule(amount, rate, int(duration), int(installments))
                    inst_info = str(schedule)
                created_at = datetime.utcnow().isoformat()
                c.execute("""INSERT INTO loans (user_id, name, father_name, phone, cnic, address,
                             user_image_path, cnic_image_path, amount, interest_rate, total_payable,
                             status, due_date, created_at, payment_status, receipt_no, installment_plan)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                          (st.session_state["user"]["id"], name, father, phone, cnic, address,
                           user_img_path, cnic_img_path, amount, rate, total,
                           "pending", (date.today()+timedelta(days=duration)).isoformat(), created_at, "Unpaid", None, inst_info))
                conn.commit()
                st.success(f"Application submitted. Total payable PKR {total}. Pending admin approval.")
                # send notification placeholders
                send_email_placeholder(st.session_state["user"].get("email"), "Loan Submitted", f"Your loan for PKR {amount} submitted.")
                send_sms_placeholder(phone, f"Your loan application of PKR {amount} submitted.")

# Repay page (user)
if page == "Repay" and st.session_state["user"]:
    st.header("Repay Loan")
    u = st.session_state["user"]
    df = df_from_query("SELECT * FROM loans WHERE user_id=? AND status='approved' AND payment_status!='Paid'", (u["id"],))
    if df.empty:
        st.info("No approved unpaid loans.")
    else:
        st.dataframe(df[["id","amount","total_payable","due_date","payment_status","installment_plan"]])
        loan_id = st.number_input("Enter Loan ID to pay", min_value=1, step=1)
        payment_mode = st.selectbox("Payment Method", ["Mock - Easypaisa", "Mock - JazzCash"])
        pay_amt = st.number_input("Payment Amount (PKR)", min_value=1.0)
        if st.button("Make Payment"):
            # In production you'd call the gateway and verify webhook.
            receipt = random_txn()
            # handle partial payment logic
            c.execute("SELECT total_payable FROM loans WHERE id=?", (loan_id,))
            row = c.fetchone()
            if not row:
                st.error("Loan not found.")
            else:
                total_pay = float(row[0])
                # simplistic: if pay_amt >= remaining => mark Paid
                c.execute("SELECT SUM(amount) FROM (SELECT amount FROM payments WHERE loan_id=?)", (loan_id,))
                # payments table may not exist yet; ensure it later
                # For simplicity, when payment >= total_pay, mark Paid
                if pay_amt >= total_pay:
                    c.execute("UPDATE loans SET payment_status='Paid', receipt_no=? WHERE id=?", (receipt, loan_id))
                else:
                    c.execute("UPDATE loans SET payment_status='Partially Paid' WHERE id=?", (loan_id,))
                # create payments table if not exists then insert
                c.execute("""CREATE TABLE IF NOT EXISTS payments (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                loan_id INTEGER,
                                amount REAL,
                                payment_method TEXT,
                                paid_at TEXT,
                                receipt TEXT
                            )""")
                c.execute("INSERT INTO payments (loan_id, amount, payment_method, paid_at, receipt) VALUES (?, ?, ?, ?, ?)",
                          (loan_id, pay_amt, payment_mode, datetime.utcnow().isoformat(), receipt))
                conn.commit()
                st.success(f"Payment recorded. Receipt: {receipt}")
                send_email_placeholder(u.get("email"), "Payment Received", f"Payment of PKR {pay_amt} received. Receipt {receipt}")
                send_sms_placeholder(u.get("phone"), f"Payment PKR {pay_amt} received. Receipt {receipt}")

# History page
if page == "History" and st.session_state["user"]:
    st.header("Loan History & Documents")
    u = st.session_state["user"]
    df = df_from_query("SELECT * FROM loans WHERE user_id=? ORDER BY created_at DESC", (u["id"],))
    if df.empty:
        st.info("You have no loan records.")
    else:
        st.dataframe(df[["id","amount","total_payable","status","due_date","payment_status"]])
        sel = st.selectbox("Select loan to view / generate docs", df["id"].tolist())
        loan = df[df["id"]==sel].iloc[0].to_dict()
        st.write("Borrower:", loan["name"])
        st.write("CNIC (masked):", mask_cnic(loan.get("cnic","")))
        st.write("Status:", loan["status"])
        if loan.get("user_image_path"):
            st.image(loan["user_image_path"], width=150, caption="Profile image")
        if loan.get("cnic_image_path"):
            st.image(loan["cnic_image_path"], width=300, caption="CNIC image")
        if st.button("Download Agreement (PDF)"):
            pdf_bytes = generate_pdf_agreement(loan).read()
            st.download_button("Download Agreement", pdf_bytes, file_name=f"agreement_loan_{sel}.pdf", mime="application/pdf")
        if st.button("Export My Data (Excel)"):
            out = io.BytesIO()
            df.to_excel(out, index=False)
            out.seek(0)
            st.download_button("Download Excel", out, file_name=f"loan_history_{u['phone']}.xlsx")

# Admin area
if page == "Admin" and st.session_state["user"] and st.session_state["user"].get("is_admin"):
    st.header("Admin Panel — Manage Loans")
    menu_admin = st.sidebar.selectbox("Admin Actions", ["All Loans", "Pending Approvals", "Analytics", "Reminders & Export", "User Management"])
    if menu_admin == "All Loans":
        df = df_from_query("SELECT loans.*, users.email as user_email, users.name as user_fullname FROM loans LEFT JOIN users ON loans.user_id=users.id ORDER BY created_at DESC")
        st.dataframe(df)
        # show each loan with preview + approve/reject
        st.markdown("### Approve / Reject")
        loan_id = st.number_input("Loan ID", min_value=1, step=1)
        if loan_id:
            r = df[df["id"]==loan_id]
            if r.empty:
                st.info("Loan not found.")
            else:
                rec = r.iloc[0].to_dict()
                st.write("Applicant:", rec.get("name"))
                st.write("Phone:", rec.get("phone"))
                st.write("CNIC (masked):", mask_cnic(rec.get("cnic","")))
                if rec.get("user_image_path"):
                    st.image(rec.get("user_image_path"), width=120)
                if rec.get("cnic_image_path"):
                    st.image(rec.get("cnic_image_path"), width=300)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Approve"):
                        c.execute("UPDATE loans SET status='approved' WHERE id=?", (loan_id,))
                        conn.commit()
                        st.success("Loan approved.")
                        # send notifications
                        send_email_placeholder(rec.get("user_email"), "Loan Approved", f"Your loan ID {loan_id} approved.")
                        send_sms_placeholder(rec.get("phone"), f"Loan {loan_id} approved.")
                with col2:
                    if st.button("Reject"):
                        c.execute("UPDATE loans SET status='rejected' WHERE id=?", (loan_id,))
                        conn.commit()
                        st.error("Loan rejected.")
                        send_email_placeholder(rec.get("user_email"), "Loan Rejected", f"Your loan ID {loan_id} rejected.")
                        send_sms_placeholder(rec.get("phone"), f"Loan {loan_id} rejected.")
    elif menu_admin == "Pending Approvals":
        df = df_from_query("SELECT * FROM loans WHERE status='pending' ORDER BY created_at DESC")
        st.dataframe(df)
    elif menu_admin == "Analytics":
        st.subheader("Portfolio Analytics")
        df_all = df_from_query("SELECT status, COUNT(*) as count, SUM(amount) as sum_amount FROM loans GROUP BY status")
        st.table(df_all)
        # simple chart
        if not df_all.empty:
            fig, ax = plt.subplots()
            ax.pie(df_all["count"], labels=df_all["status"], autopct="%1.1f%%")
            st.pyplot(fig)
    elif menu_admin == "Reminders & Export":
        st.subheader("Loans due in next N days")
        days = st.number_input("Days ahead", min_value=1, value=7)
        target = (date.today()+timedelta(days=days)).isoformat()
        df = df_from_query("SELECT * FROM loans WHERE due_date <= ? AND status='approved' AND payment_status!='Paid'", (target,))
        st.dataframe(df)
        if st.button("Export Reminders CSV"):
            out = df.to_csv(index=False).encode()
            st.download_button("Download Reminders CSV", out, file_name=f"reminders_{target}.csv")
        if st.button("Send Reminders (Email/SMS placeholders)"):
            for _, r in df.iterrows():
                send_email_placeholder(r.get("user_email"), "Loan Due Reminder", f"Loan {r['id']} is due on {r['due_date']}.")
                send_sms_placeholder(r.get("phone"), f"Loan {r['id']} due on {r['due_date']}.")
            st.success("Reminder placeholders executed.")
    elif menu_admin == "User Management":
        st.subheader("Users")
        users = df_from_query("SELECT id,name,phone,email,is_admin,created_at FROM users")
        st.dataframe(users)
        uid = st.number_input("Make admin / remove admin - User ID", min_value=1, step=1)
        if st.button("Toggle Admin"):
            c.execute("SELECT is_admin FROM users WHERE id=?", (uid,))
            r = c.fetchone()
            if r:
                new = 0 if r[0]==1 else 1
                c.execute("UPDATE users SET is_admin=? WHERE id=?", (new, uid))
                conn.commit()
                st.success("Updated user admin status.")
            else:
                st.error("User not found.")

# Logout option
if st.sidebar.button("Logout"):
    st.session_state["user"] = None
    st.experimental_rerun()

# If user not logged in but tries to reach protected pages, ask login
if page in ["Apply Loan","Repay","History","Dashboard","Admin"] and not st.session_state["user"]:
    st.warning("Please login first via Signup / Login tab.")
