# app.py
import streamlit as st
import sqlite3
from datetime import datetime, date
import hashlib
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

DB_PATH = "loans_app.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT UNIQUE,
        email TEXT UNIQUE,
        password_hash TEXT,
        is_admin INTEGER DEFAULT 0
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        principal REAL,
        interest_rate REAL,
        days INTEGER,
        total_repayable REAL,
        created_at TEXT,
        due_date TEXT,
        status TEXT DEFAULT 'pending',  -- pending, approved, rejected, paid
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        loan_id INTEGER,
        amount REAL,
        paid_at TEXT,
        FOREIGN KEY(loan_id) REFERENCES loans(id)
    )
    ''')
    c.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('annual_interest_rate', '0.10')")
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def create_user(name, phone, email, password, is_admin=0):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (name, phone, email, password_hash, is_admin) VALUES (?, ?, ?, ?, ?)',
                  (name, phone, email, hash_password(password), is_admin))
        conn.commit()
        return True, "User created"
    except sqlite3.IntegrityError as e:
        return False, str(e)
    finally:
        conn.close()

def authenticate(phone_or_email, password):
    conn = get_conn()
    c = conn.cursor()
    pw_hash = hash_password(password)
    c.execute('SELECT * FROM users WHERE (phone = ? OR email = ?) AND password_hash = ?', (phone_or_email, phone_or_email, pw_hash))
    row = c.fetchone()
    conn.close()
    return row

def get_setting(key):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    r = c.fetchone()
    conn.close()
    return r['value'] if r else None

def set_setting(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def calculate_total_repayable(principal: float, annual_interest_rate: float, days: int) -> float:
    p = Decimal(str(principal))
    r = Decimal(str(annual_interest_rate))
    d = Decimal(str(days))
    interest = (p * r * d / Decimal('365'))
    total = p + interest
    total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return float(total)

def create_loan(user_id, principal, interest_rate, days):
    total = calculate_total_repayable(principal, interest_rate, days)
    created_at = datetime.utcnow().isoformat()
    due_date = (date.today().toordinal() + days)
    due_date_iso = (date.fromordinal(due_date)).isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO loans (user_id, principal, interest_rate, days, total_repayable, created_at, due_date, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
              (user_id, principal, interest_rate, days, total, created_at, due_date_iso, 'pending'))
    conn.commit()
    conn.close()
    return True, total

def update_loan_status(loan_id, status):
    conn = get_conn()
    c = conn.cursor()
    c.execute('UPDATE loans SET status = ? WHERE id = ?', (status, loan_id))
    conn.commit()
    conn.close()

def pay_loan(loan_id, amount):
    paid_at = datetime.utcnow().isoformat()
    conn = get_conn()
    c = conn.cursor()
    c.execute('INSERT INTO payments (loan_id, amount, paid_at) VALUES (?, ?, ?)', (loan_id, amount, paid_at))
    conn.commit()
    c.execute('SELECT total_repayable FROM loans WHERE id = ?', (loan_id,))
    loan = c.fetchone()
    c.execute('SELECT SUM(amount) as total_paid FROM payments WHERE loan_id = ?', (loan_id,))
    paid_sum = c.fetchone()['total_paid'] or 0.0
    if paid_sum >= loan['total_repayable']:
        c.execute('UPDATE loans SET status = ? WHERE id = ?', ('paid', loan_id))
    conn.commit()
    conn.close()

def get_user_loans(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM loans WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_loan_payments(loan_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT * FROM payments WHERE loan_id = ? ORDER BY paid_at', (loan_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_loans():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT loans.*, users.name, users.phone FROM loans JOIN users ON loans.user_id = users.id ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows

# ---------------------------
# Init DB
# ---------------------------
init_db()

st.set_page_config(page_title="Udhar App", layout="centered")
st.title("Udhar App — Loan System")

if 'user' not in st.session_state:
    st.session_state['user'] = None

menu = ["Home", "Register", "Login"]
if st.session_state['user']:
    menu = ["Home", "Dashboard", "Logout"]
    if st.session_state['user']['is_admin'] == 1:
        menu.append("Admin Panel")

choice = st.sidebar.selectbox("Menu", menu)

if choice == "Home":
    st.subheader("Welcome!")
    st.write("Ab loan request pehle **pending approval** me jayegi. Admin approve karega tabhi repayment allow hoga.")

if choice == "Register":
    with st.form("reg_form"):
        name = st.text_input("Name")
        phone = st.text_input("Phone")
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        password2 = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Register")
        if submitted:
            if password != password2:
                st.error("Passwords do not match")
            else:
                ok, msg = create_user(name, phone, email, password)
                st.success(msg) if ok else st.error(msg)

if choice == "Login":
    with st.form("login_form"):
        pe = st.text_input("Phone/Email")
        pw = st.text_input("Password", type="password")
        btn = st.form_submit_button("Login")
        if btn:
            user = authenticate(pe, pw)
            if user:
                st.session_state['user'] = dict(user)
                st.experimental_rerun()
            else:
                st.error("Invalid credentials")

if choice == "Dashboard" and st.session_state['user']:
    user = st.session_state['user']
    st.subheader(f"Dashboard — {user['name']}")
    annual_rate = float(get_setting('annual_interest_rate'))
    with st.expander("Request Loan"):
        with st.form("loan_form"):
            principal = st.number_input("Loan Amount", 100.0, step=100.0)
            days = st.number_input("Duration (days)", 1, value=30)
            submit = st.form_submit_button("Request Loan")
            if submit:
                ok, total = create_loan(user['id'], principal, annual_rate, days)
                st.success(f"Loan requested (Pending Admin Approval). Total repayable: {total:.2f}")

    loans = get_user_loans(user['id'])
    for ln in loans:
        st.write("---")
        st.write(f"Loan ID: {ln['id']} | Status: {ln['status']}")
        st.write(f"Principal: {ln['principal']} | Total repayable: {ln['total_repayable']} | Due: {ln['due_date']}")
        if ln['status'] == "approved":
            with st.expander("Make Payment"):
                st.info("Mock Payment Gateway: Choose EasyPaisa or JazzCash")
                method = st.radio("Payment Method", ["EasyPaisa", "JazzCash"], key=f"method_{ln['id']}")
                if st.button("Pay Now", key=f"pay_{ln['id']}"):
                    pay_loan(ln['id'], ln['total_repayable'])
                    st.success(f"Payment successful via {method} (Simulated)")
                    st.experimental_rerun()
        elif ln['status'] == "pending":
            st.warning("Waiting for Admin approval.")
        elif ln['status'] == "rejected":
            st.error("Loan request rejected by admin.")

if choice == "Admin Panel" and st.session_state['user']['is_admin'] == 1:
    st.subheader("Admin Panel — Loan Approvals")
    all_loans = get_all_loans()
    for ln in all_loans:
        st.write("---")
        st.write(f"Loan ID: {ln['id']} | User: {ln['name']} | Principal: {ln['principal']} | Status: {ln['status']}")
        if ln['status'] == "pending":
            c1, c2 = st.columns(2)
            if c1.button("Approve", key=f"ap_{ln['id']}"):
                update_loan_status(ln['id'], "approved")
                st.success("Loan approved.")
                st.experimental_rerun()
            if c2.button("Reject", key=f"rej_{ln['id']}"):
                update_loan_status(ln['id'], "rejected")
                st.error("Loan rejected.")
                st.experimental_rerun()

if choice == "Logout":
    st.session_state['user'] = None
    st.experimental_rerun()

def ensure_admin_exists():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as cnt FROM users WHERE is_admin = 1')
    if c.fetchone()['cnt'] == 0:
        create_user("Admin", "0000000000", "admin@example.com", "admin123", is_admin=1)
    conn.close()

ensure_admin_exists()
