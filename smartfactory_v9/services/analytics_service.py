from database.db_manager import get_db_connection
from config import Config
from datetime import datetime

def calculate_kpis():
    conn = get_db_connection()
    today_str = datetime.now().strftime('%Y-%m-%d')

    rows = conn.execute("SELECT m.name, p.* FROM machines m JOIN production_logs p ON m.id = p.machine_id WHERE p.date = ?", (today_str,)).fetchall()

    try:
        thresh_row = conn.execute("SELECT value FROM settings WHERE key='threshold_eff'").fetchone()
        thresh = float(thresh_row['value']) if thresh_row else 75.0
    except:
        thresh = 75.0

    data = []
    total_eff, delays = 0, 0

    for r in rows:
        eff = 0
        if r['planned_qty'] > 0:
            eff = round((r['actual_qty'] / r['planned_qty'] * 100), 1)

        util = round((r['runtime_hours'] / Config.SHIFT_HOURS * 100), 1)
        idle = round(max(0, Config.SHIFT_HOURS - r['runtime_hours']), 1)

        status = "Good"
        if eff < thresh: status = "Critical"
        elif eff < (thresh + 15): status = "Warning"

        if r['actual_qty'] < r['planned_qty']: delays += 1

        data.append({
            "id": r['machine_id'],
            "name": r['name'], 
            "efficiency": eff, 
            "utilization": util, 
            "idle_time": idle, 
            "actual_qty": r['actual_qty'], 
            "planned_qty": r['planned_qty'], 
            "status": status
        })
        total_eff += eff

    avg = round(total_eff / len(data), 1) if data else 0
    bottleneck = min(data, key=lambda x: x['efficiency'])['name'] if data else "None"

    conn.close()
    return {
        "kpi_summary": {
            "avg_efficiency": avg, 
            "total_machines": len(data), 
            "delayed_orders": delays, 
            "bottleneck": bottleneck
        }, 
        "machines": data
    }

def get_analytics_data():
    conn = get_db_connection()

    rankings = conn.execute('''
        SELECT m.name, AVG((p.actual_qty * 1.0 / p.planned_qty) * 100) as avg_eff 
        FROM machines m JOIN production_logs p ON m.id = p.machine_id 
        WHERE p.planned_qty > 0
        GROUP BY m.id ORDER BY avg_eff DESC
    ''').fetchall()

    trend = conn.execute('''
        SELECT date, AVG((actual_qty * 1.0 / planned_qty) * 100) as daily_eff
        FROM production_logs 
        WHERE planned_qty > 0
        GROUP BY date ORDER BY date DESC LIMIT 7
    ''').fetchall()

    conn.close()

    trend_labels = [r['date'] for r in trend][::-1]
    trend_data = [round(r['daily_eff'], 1) for r in trend][::-1]

    return {
        "rankings": [{"name": r['name'], "avg_eff": round(r['avg_eff'], 1)} for r in rankings],
        "trend": {"labels": trend_labels, "data": trend_data}
    }
