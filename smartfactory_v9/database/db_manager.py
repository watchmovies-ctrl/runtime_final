import sqlite3
from config import Config
from werkzeug.security import generate_password_hash
import random
from datetime import datetime, timedelta

def get_db_connection():
    conn = sqlite3.connect(Config.DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Create Tables
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, role TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS machines (id INTEGER PRIMARY KEY, name TEXT, type TEXT, capacity_per_hour INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS production_logs (id INTEGER PRIMARY KEY, machine_id INTEGER, date TEXT, planned_qty INTEGER, actual_qty INTEGER, runtime_hours REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY, machine_id INTEGER, message TEXT, severity TEXT, created_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')

    # Seed Users
    c.execute('SELECT count(*) FROM users')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', ('admin', generate_password_hash('admin123'), 'admin'))
        c.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', ('operator', generate_password_hash('operator123'), 'operator'))

    # Seed Machines & Data
    c.execute('SELECT count(*) FROM machines')
    if c.fetchone()[0] == 0:
        machines = [('CNC-01', 'Milling', 100), ('CNC-02', 'Milling', 100), ('PRESS-A', 'Press', 500), ('PACK-01', 'Packing', 1000)]
        c.executemany('INSERT INTO machines (name, type, capacity_per_hour) VALUES (?, ?, ?)', machines)

        # Seed History Data (for reports/analytics)
        today = datetime.now().date()
        for i in range(7):
            date_str = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            for machine_id in range(1, 5): 
                planned = 800 if machine_id <= 2 else (4000 if machine_id == 3 else 8000)
                actual = int(planned * random.uniform(0.7, 0.95))
                runtime = round(random.uniform(6.5, 8.0), 1)

                c.execute("INSERT INTO production_logs (machine_id, date, planned_qty, actual_qty, runtime_hours) VALUES (?, ?, ?, ?, ?)", 
                          (machine_id, date_str, planned, actual, runtime))

    # Ensure current day logs exist for Dashboard
    today_str = datetime.now().strftime('%Y-%m-%d')
    c.execute("SELECT count(*) FROM production_logs WHERE date = ?", (today_str,))
    if c.fetchone()[0] == 0:
        for machine_id in range(1, 5): 
             planned = 800 if machine_id <= 2 else (4000 if machine_id == 3 else 8000)
             c.execute("INSERT INTO production_logs (machine_id, date, planned_qty, actual_qty, runtime_hours) VALUES (?, ?, ?, 0, 0.0)", 
                       (machine_id, today_str, planned))

    # Seed Settings
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('plant_name', 'Nagpur MIDC Zone-A')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('threshold_eff', '75.0')")

    conn.commit()
    conn.close()
