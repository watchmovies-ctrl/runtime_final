from flask import Flask, render_template, jsonify, request, redirect, url_for, session, Response, flash
from config import Config
from database.db_manager import init_db, get_db_connection
from services.analytics_service import calculate_kpis, get_analytics_data
from werkzeug.security import check_password_hash
import random
import csv
import io
import datetime

app = Flask(__name__)
app.config.from_object(Config)

# Initialize DB
with app.app_context():
    init_db()

# Middleware
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- AUTH ROUTES ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (request.form['username'],)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], request.form['password']):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- MAIN PAGES ---
@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html', active_page='dashboard')

@app.route('/machines', methods=['GET', 'POST'])
@login_required
def machines():
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form.get('name')
        m_type = request.form.get('type')
        capacity = request.form.get('capacity')

        if name and m_type and capacity:
            conn.execute('INSERT INTO machines (name, type, capacity_per_hour) VALUES (?, ?, ?)', (name, m_type, capacity))
            machine_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            today_str = datetime.datetime.now().strftime('%Y-%m-%d')
            conn.execute("INSERT INTO production_logs (machine_id, date, planned_qty, actual_qty, runtime_hours) VALUES (?, ?, ?, 0, 0.0)", 
                       (machine_id, today_str, int(capacity)*8))
            conn.commit()
            flash("Machine Added Successfully!")
        else:
            flash("Error: Missing fields")
        return redirect(url_for('machines'))

    machines_list = conn.execute('SELECT * FROM machines').fetchall()
    conn.close()
    return render_template('machines.html', active_page='machines', machines=machines_list)

@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()
    logs = conn.execute('''
        SELECT p.date, m.name as machine_name, p.planned_qty, p.actual_qty, p.runtime_hours 
        FROM production_logs p 
        JOIN machines m ON p.machine_id = m.id 
        ORDER BY p.date DESC
    ''').fetchall()
    conn.close()
    return render_template('reports.html', active_page='reports', logs=logs)

@app.route('/alerts')
@login_required
def alerts():
    conn = get_db_connection()
    # Fetch alerts - Join with machines to get names
    alerts_list = conn.execute('''
        SELECT a.*, m.name as machine_name 
        FROM alerts a 
        LEFT JOIN machines m ON a.machine_id = m.id 
        ORDER BY a.created_at DESC
    ''').fetchall()

    # Calculate counts
    c = sum(1 for a in alerts_list if a['severity']=='Critical')
    w = sum(1 for a in alerts_list if a['severity']=='Warning')
    i = sum(1 for a in alerts_list if a['severity']=='Info')

    conn.close()
    return render_template('alerts.html', active_page='alerts', alerts=alerts_list, c=c, w=w, i=i)

@app.route('/analytics')
@login_required
def analytics():
    data = get_analytics_data()
    return render_template('analytics.html', active_page='analytics', 
                         rankings=data['rankings'], 
                         trend_labels=data['trend']['labels'], 
                         trend_data=data['trend']['data'])

@app.route('/help')
@login_required
def help_page():
    return render_template('help.html', active_page='help')

@app.route('/settings')
@login_required
def settings():
    conn = get_db_connection()
    # Get settings or defaults
    settings_rows = conn.execute("SELECT * FROM settings").fetchall()
    s = {row['key']: row['value'] for row in settings_rows}
    # Ensure defaults exist in dictionary if DB is empty
    if 'plant_name' not in s: s['plant_name'] = 'Nagpur MIDC Zone-A'
    if 'threshold_eff' not in s: s['threshold_eff'] = '75.0'
    conn.close()
    return render_template('settings.html', active_page='settings', s=s)

@app.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    conn = get_db_connection()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('plant_name', request.form.get('plant_name', 'Nagpur MIDC')))
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', ('threshold_eff', request.form.get('threshold_eff', '75.0')))
    conn.commit()
    conn.close()
    flash("Settings Updated Successfully!")
    return redirect(url_for('settings'))

@app.route('/download_csv')
@login_required
def download_csv():
    conn = get_db_connection()
    logs = conn.execute('SELECT p.date, m.name, p.planned_qty, p.actual_qty FROM production_logs p JOIN machines m ON p.machine_id = m.id').fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Machine', 'Planned', 'Actual'])
    for r in logs: 
        writer.writerow([r['date'], r['name'], r['planned_qty'], r['actual_qty']])

    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=report.csv"})

# --- API ENDPOINTS ---
@app.route('/api/dashboard')
@login_required
def api_data(): 
    return jsonify(calculate_kpis())

@app.route('/api/simulate')
@login_required
def simulate():
    conn = get_db_connection()
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    logs = conn.execute("SELECT id, actual_qty, planned_qty, runtime_hours, machine_id FROM production_logs WHERE date = ?", (today_str,)).fetchall()

    for log in logs:
        if log['actual_qty'] < log['planned_qty']:
            increment = random.randint(10, 50)
            new_qty = min(log['planned_qty'], log['actual_qty'] + increment)
            new_run = min(8.0, log['runtime_hours'] + random.uniform(0.1, 0.3))

            conn.execute("UPDATE production_logs SET actual_qty = ?, runtime_hours = ? WHERE id = ?", (new_qty, round(new_run, 2), log['id']))

            # Generate Random Alerts for Demo
            eff = (new_qty / log['planned_qty']) * 100
            if eff < 60 and random.random() < 0.3:
                 created = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                 # Check if alert already exists for today to avoid spam
                 existing = conn.execute("SELECT id FROM alerts WHERE machine_id = ? AND message LIKE 'Efficiency drop%' AND created_at LIKE ?", (log['machine_id'], today_str + '%')).fetchone()
                 if not existing:
                     conn.execute("INSERT INTO alerts (machine_id, message, severity, created_at) VALUES (?, ?, ?, ?)",
                                  (log['machine_id'], f"Efficiency drop detected: {int(eff)}%", "Warning", created))

    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
