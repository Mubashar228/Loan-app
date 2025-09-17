import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import random, string
import os

# --------------------------
# Database Setup & Migration
# --------------------------
conn = sqlite3.connect("loans.db")
c = conn.cursor()

# Create table if not exists
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

# 🆕 Add missing columns safely (schema migration)
def add_column_if_not_exists(column_name, column_type):
    try:
        c.execute(f"ALTER TABLE loans ADD COLUMN {column_name} {column_type}")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists

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
# Streamlit App
# --------------------------
st.set_page_config(page_title="Udhar Loan App", page_icon="💰", layout="wide")
st.title("💰 Udhar (Loan) Management System")

menu = st.sidebar.radio("📌 Select Option", ["Apply for Loan", "Admin - Approve Loans", "Repay Loan", "Loan History"])

# Apply for Loan
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
            if name.strip() == "" or phone.strip() == "" or cnic.strip() == "":
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
