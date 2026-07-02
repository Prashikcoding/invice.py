import sqlite3
import streamlit as st
import pandas as pd
from datetime import datetime, date
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

# --- DB SETUP ---
DB = 'freelance.db'
conn = sqlite3.connect(DB, check_same_thread=False)
cur = conn.cursor()

# Create tables
cur.execute('''CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    gst TEXT,
    created_at TEXT DEFAULT CURRENT_DATE
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    title TEXT,
    rate REAL,
    rate_type TEXT, -- 'hourly' or 'fixed'
    status TEXT DEFAULT 'Active',
    FOREIGN KEY(client_id) REFERENCES clients(id)
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS time_logs (
    id INTEGER PRIMARY KEY,
    project_id INTEGER,
    log_date TEXT,
    hours REAL,
    description TEXT,
    FOREIGN KEY(project_id) REFERENCES projects(id)
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    client_id INTEGER,
    invoice_date TEXT,
    due_date TEXT,
    status TEXT DEFAULT 'Unpaid', -- Paid, Unpaid, Overdue
    total REAL,
    FOREIGN KEY(client_id) REFERENCES clients(id)
)''')

cur.execute('''CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER,
    description TEXT,
    qty REAL,
    unit_price REAL,
    amount REAL,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id)
)''')
conn.commit()

# --- HELPER FUNCTIONS ---
def add_client(name, email, phone, gst):
    cur.execute("INSERT INTO clients(name,email,phone,gst) VALUES (?,?,?,?)", 
                (name,email,phone,gst))
    conn.commit()

def get_clients():
    return pd.read_sql("SELECT * FROM clients", conn)

def add_project(client_id, title, rate, rate_type):
    cur.execute("INSERT INTO projects(client_id,title,rate,rate_type) VALUES (?,?,?,?)",
                (client_id,title,rate,rate_type))
    conn.commit()

def log_hours(project_id, log_date, hours, desc):
    cur.execute("INSERT INTO time_logs(project_id,log_date,hours,description) VALUES (?,?,?,?)",
                (project_id,str(log_date),hours,desc))
    conn.commit()

def create_invoice_pdf(client_name, items, total):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, 750, "INVOICE")
    c.setFont("Helvetica", 12)
    c.drawString(50, 720, f"Bill To: {client_name}")
    c.drawString(50, 700, f"Date: {date.today()}")
    
    y = 650
    c.drawString(50, y, "Description")
    c.drawString(350, y, "Amount")
    y -= 20
    for desc, amt in items:
        c.drawString(50, y, desc)
        c.drawString(350, y, f"Rs. {amt:.2f}")
        y -= 20
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(300, y-20, f"Total: Rs. {total:.2f}")
    c.save()
    buffer.seek(0)
    return buffer

# --- STREAMLIT UI ---
st.set_page_config(page_title="Freelance Invoice Tracker", layout="wide")
st.title("💼 Freelance Invoice & Client Tracker")

menu = st.sidebar.selectbox("Menu", ["Dashboard", "Clients", "Projects", "Log Hours", "Create Invoice"])

if menu == "Dashboard":
    st.subheader("Earnings Overview")
    df_inv = pd.read_sql("SELECT * FROM invoices", conn)
    df_paid = df_inv[df_inv['status']=='Paid']
    col1,col2,col3 = st.columns(3)
    col1.metric("Total Earned", f"Rs. {df_paid['total'].sum():.2f}")
    col2.metric("Unpaid Invoices", len(df_inv[df_inv['status']=='Unpaid']))
    col3.metric("This Month", f"Rs. {df_paid[pd.to_datetime(df_paid['invoice_date']).dt.month==date.today().month]['total'].sum():.2f}")
    
    st.dataframe(df_inv.sort_values('invoice_date', ascending=False))

elif menu == "Clients":
    st.subheader("Add New Client")
    with st.form("client_form"):
        name = st.text_input("Client Name*")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        gst = st.text_input("GST Number")
        if st.form_submit_button("Add Client"):
            add_client(name,email,phone,gst)
            st.success(f"Added {name}")
    st.subheader("All Clients")
    st.dataframe(get_clients())

elif menu == "Projects":
    st.subheader("Add Project")
    clients = get_clients()
    if not clients.empty:
        with st.form("project_form"):
            client_id = st.selectbox("Client", clients['id'], format_func=lambda x: clients[clients['id']==x]['name'].values[0])
            title = st.text_input("Project Title*")
            rate = st.number_input("Rate", min_value=0.0)
            rate_type = st.selectbox("Rate Type", ["hourly", "fixed"])
            if st.form_submit_button("Add Project"):
                add_project(client_id,title,rate,rate_type)
                st.success("Project Added")
    df_proj = pd.read_sql("SELECT p.id, c.name as client, p.title, p.rate, p.rate_type FROM projects p JOIN clients c ON p.client_id=c.id", conn)
    st.dataframe(df_proj)

elif menu == "Log Hours":
    st.subheader("Log Work Hours")
    projects = pd.read_sql("SELECT p.id, p.title, c.name FROM projects p JOIN clients c ON p.client_id=c.id", conn)
    if not projects.empty:
        with st.form("hours_form"):
            proj_id = st.selectbox("Project", projects['id'], format_func=lambda x: f"{projects[projects['id']==x]['title'].values[0]} - {projects[projects['id']==x]['name'].values[0]}")
            log_date = st.date_input("Date", value=date.today())
            hours = st.number_input("Hours", min_value=0.0, step=0.5)
            desc = st.text_input("Work Description")
            if st.form_submit_button("Log Hours"):
                log_hours(proj_id,log_date,hours,desc)
                st.success("Hours Logged")

elif menu == "Create Invoice":
    st.subheader("Generate Invoice")
    clients = get_clients()
    if not clients.empty:
        client_id = st.selectbox("Select Client", clients['id'], format_func=lambda x: clients[clients['id']==x]['name'].values[0])
        client_name = clients[clients['id']==client_id]['name'].values[0]
        
        # Auto pull unbilled hours
        unbilled = pd.read_sql(f"""SELECT t.description, t.hours, p.rate, t.hours*p.rate as amount 
                                   FROM time_logs t JOIN projects p ON t.project_id=p.id 
                                   WHERE p.client_id={client_id}""", conn)
        st.write("Unbilled Items:")
        st.dataframe(unbilled)
        
        if st.button("Generate Invoice PDF") and not unbilled.empty:
            total = unbilled['amount'].sum()
            items = list(zip(unbilled['description'], unbilled['amount']))
            pdf = create_invoice_pdf(client_name, items, total)
            
            # Save invoice to DB
            cur.execute("INSERT INTO invoices(client_id,invoice_date,due_date,total) VALUES (?,?,?,?)",
                        (client_id, str(date.today()), str(date.today()), total))
            inv_id = cur.lastrowid
            for _,row in unbilled.iterrows():
                cur.execute("INSERT INTO invoice_items(invoice_id,description,qty,unit_price,amount) VALUES (?,?,?,?,?)",
                            (inv_id,row['description'],row['hours'],row['rate'],row['amount']))
            conn.commit()
            
            st.download_button("Download Invoice", pdf, file_name=f"Invoice_{client_name}_{date.today()}.pdf")
            st.success("Invoice Created & Saved!")