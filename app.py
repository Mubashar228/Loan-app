import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import random, string, os

# --------------------------
# Database Setup & Migration
# --------------------------
conn = sqlite3.connect("loans.db", check_same_thread=False)
c = conn.cursor()

# Base table create
c.execute("""
CREATE TABLE IF NOT EXISTS loans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT,
    amount REAL,
    interest REAL,
    total_payable REAL,
    status TEXT,
    due_date TEXT,
    payment_status TEXT,
    receipt_no TEXT
)
""")
conn.commit()

# Auto schema migration
def add_column_if_not_exists(column_name, column_type):
    try:
        c.execute(f"ALTER TABLE loans ADD COLUMN {column_name} {column_type}")
        conn.commit()
    except sqlite3.OperationalError:
        pass

# Adding new columns if missing
add_column_if_not_exists("father_name", "TEXT")
add_column_if_not_exists("cnic", "TEXT")
add_column_if_not_exists("address", "TEXT")
add_column_if_not_exists("user_image_path", "TEXT")
add_column_if_not_exists("cnic_image_path", "TEXT")

# --------------------------
# Helper Functions
# --------------------------
def calculate_total(amount, interest_rate, days):
    interest = (amount * interest_rate * days) / 365
    total = amount + interest
    return round(total, 2)

def generate_receipt():
    return "TXN-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def save_uploaded_file(uploaded_file, folder="uploads"):
    if uploaded_file is not None:
        if not os.path.exists(folder):
            os.makedirs(folder)
        file_path = os.path.join(folder, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

# --------------------------
# Streamlit UI
# --------------------------
st.set_page_config(page_title="Udhar Loan App", page_icon="💰", layout="wide")
st.title("💰 Udhar (Loan) Management System")

menu = st.sidebar.radio("📌 Select Option", ["Apply for Loan", "Admin - Approve Loans", "Repay Loan", "Loan History"])

# --------------------------
# Apply for Loan
# --------------------------
if menu == "Apply for Loan":
    st.header("📝 Apply for a New Loan")
    with st.form("loan_form"):
        name = st.text_input("Enter Your Name")
        father_name = st.text_input("Enter Your Father's Name")
        phone = st.text_input("Enter Your Phone Number")
        cnic = st.text_input("Enter Your CNIC Number (XXXXX-XXXXXXX-X)")
        address = st.text_area("Enter Your Address")
        user_image = st.file_uploader("Upload Your Profile Image", type=["jpg", "jpeg", "png"])
        cnic_image = st.file_uploader("Upload CNIC Image", type=["jpg", "jpeg", "png"])
        
        amount = st.number_input("Loan Amount", min_value=1000.0, step=500.0)
        duration_days = st.slider("Loan Duration (Days)", 7, 180, 30)
        interest_rate = st.number_input("Annual Interest Rate (%)", value=10.0) / 100
        
        submit = st.form_submit_button("📨 Submit Loan Request")
        
        if submit:
            if not name.strip() or not phone.strip() or not cnic.strip():
                st.error("❌ Name, Phone, and CNIC are required!")
            else:
                user_img_path = save_uploaded_file(user_image)
                cnic_img_path = save_uploaded_file(cnic_image)
                total_payable = calculate_total(amount, interest_rate, duration_days)
                due_date = (datetime.today() + timedelta(days=duration_days)).strftime("%Y-%m-%d")
                
                c.execute("""
                    INSERT INTO loans (name, father_name, phone, cnic, address, user_image_path, cnic_image_path,
                    amount, interest, total_payable, status, due_date, payment_status, receipt_no)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, father_name, phone, cnic, address, user_img_path, cnic_img_path,
                      amount, interest_rate, total_payable, "Pending", due_date, "Unpaid", None))
                conn.commit()
                st.success(f"✅ Loan Request Submitted! Total Payable: {total_payable} | Due Date: {due_date}")

# --------------------------
# Admin - Approve Loans
# --------------------------
elif menu == "Admin - Approve Loans":
    st.header("👨‍💻 Admin Panel - Loan Approval")
    df = pd.read_sql_query("SELECT * FROM loans", conn)
    if not df.empty:
        st.dataframe(df)
        loan_id = st.number_input("Enter Loan ID to Approve/Reject", min_value=1, step=1)
        action = st.radio("Action", ["Approve", "Reject"])
        if st.button("✅ Confirm Action"):
            new_status = "Approved" if action == "Approve" else "Rejected"
            c.execute("UPDATE loans SET status=? WHERE id=?", (new_status, loan_id))
            conn.commit()
            st.success(f"✅ Loan ID {loan_id} has been {new_status}.")
    else:
        st.info("No loan applications found.")

# --------------------------
# Repay Loan
# --------------------------
elif menu == "Repay Loan":
    st.header("💳 Loan Repayment")
    df = pd.read_sql_query("SELECT * FROM loans WHERE status='Approved' AND payment_status='Unpaid'", conn)
    if not df.empty:
        st.dataframe(df)
        loan_id = st.number_input("Enter Loan ID to Pay", min_value=1, step=1)
        payment_method = st.selectbox("Select Payment Method", ["Easypaisa", "JazzCash"])
        if st.button("💸 Make Payment"):
            receipt = generate_receipt()
            c.execute("UPDATE loans SET payment_status='Paid', receipt_no=? WHERE id=?", (receipt, loan_id))
            conn.commit()
            st.success(f"✅ Payment Successful via {payment_method}! Receipt No: {receipt}")
    else:
        st.info("No pending loans for repayment.")

# --------------------------
# Loan History
# --------------------------
elif menu == "Loan History":
    st.header("📜 Loan History")
    df = pd.read_sql_query("SELECT * FROM loans", conn)
    if not df.empty:
        st.dataframe(df)
    else:
        st.info("No loans found.")
