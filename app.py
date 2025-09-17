import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import random, string

# --------------------------
# Database Setup
# --------------------------
conn = sqlite3.connect("loans.db")
c = conn.cursor()

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

# --------------------------
# Helper Functions
# --------------------------
def calculate_total(amount, interest_rate, days):
    interest = (amount * interest_rate * days) / 365
    total = amount + interest
    return round(total, 2)

def generate_receipt():
    return "TXN-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# --------------------------
# App Title
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
        phone = st.text_input("Enter Your Phone Number")
        amount = st.number_input("Loan Amount", min_value=1000.0, step=500.0)
        duration_days = st.slider("Loan Duration (Days)", 7, 180, 30)
        interest_rate = st.number_input("Annual Interest Rate (%)", value=10.0) / 100
        
        submit = st.form_submit_button("📨 Submit Loan Request")
        
        if submit:
            if name.strip() == "" or phone.strip() == "":
                st.error("❌ Name and Phone are required!")
            else:
                total_payable = calculate_total(amount, interest_rate, duration_days)
                due_date = (datetime.today() + timedelta(days=duration_days)).strftime("%Y-%m-%d")
                c.execute("""
                    INSERT INTO loans (name, phone, amount, interest, total_payable, status, due_date, payment_status, receipt_no)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (name, phone, amount, interest_rate, total_payable, "Pending", due_date, "Unpaid", None))
                conn.commit()
                st.success(f"✅ Loan Request Submitted! Total Payable: {total_payable} | Due Date: {due_date}")

# --------------------------
# Admin Panel - Approve/Reject Loans
# --------------------------
elif menu == "Admin - Approve Loans":
    st.header("🛠 Admin Panel - Approve or Reject Loans")
    status_filter = st.selectbox("Filter Loans by Status", ["Pending", "Approved", "Rejected"])
    df = pd.read_sql(f"SELECT * FROM loans WHERE status='{status_filter}'", conn)
    
    if df.empty:
        st.info("📭 No loans found for this status.")
    else:
        st.dataframe(df)
        selected_id = st.selectbox("Select Loan ID to Approve/Reject", df["id"].tolist())
        action = st.radio("Action", ["Approve ✅", "Reject ❌"])
        if st.button("Submit Action"):
            new_status = "Approved" if "Approve" in action else "Rejected"
            c.execute("UPDATE loans SET status=? WHERE id=?", (new_status, selected_id))
            conn.commit()
            st.success(f"Loan {new_status} Successfully!")

# --------------------------
# Repay Loan (Payment Gateway Mockup)
# --------------------------
elif menu == "Repay Loan":
    st.header("💵 Repay Your Loan")
    phone = st.text_input("Enter Your Phone Number to Find Your Loans")
    if phone:
        df = pd.read_sql("SELECT * FROM loans WHERE phone=? AND status='Approved' AND payment_status='Unpaid'", conn, params=(phone,))
        if df.empty:
            st.info("✅ No unpaid approved loans found for this phone number.")
        else:
            st.dataframe(df)
            selected_id = st.selectbox("Select Loan ID to Repay", df["id"].tolist())
            payment_method = st.selectbox("Choose Payment Method", ["EasyPaisa", "JazzCash"])
            
            if st.button("💳 Make Payment"):
                receipt = generate_receipt()
                c.execute("UPDATE loans SET payment_status='Paid', receipt_no=? WHERE id=?", (receipt, selected_id))
                conn.commit()
                st.success(f"🎉 Payment Successful via {payment_method}!\n📄 Receipt No: {receipt}")

# --------------------------
# Loan History
# --------------------------
elif menu == "Loan History":
    st.header("📜 Your Loan History")
    phone = st.text_input("Enter Your Phone Number to View History")
    if phone:
        df = pd.read_sql("SELECT * FROM loans WHERE phone=?", conn, params=(phone,))
        if df.empty:
            st.info("No loans found for this phone number.")
        else:
            # Status ko color coding dene ke liye
            df["status"] = df["status"].apply(lambda x: "✅ Approved" if x=="Approved" else "⏳ Pending" if x=="Pending" else "❌ Rejected")
            df["payment_status"] = df["payment_status"].apply(lambda x: "💰 Paid" if x=="Paid" else "🔴 Unpaid")
            st.dataframe(df)
