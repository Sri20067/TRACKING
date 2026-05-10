from flask import Flask, request, jsonify, render_template
import sqlite3
from datetime import datetime
import json
import urllib.request
import urllib.parse

app = Flask(__name__)

# -------------------------------
# Alert Configuration
# -------------------------------
ALERT_PHONE    = "+916382188633"    # Your phone number (with country code)
SMS_API_KEY    = "textbelt"         # Textbelt key (free = 1/day). Buy at textbelt.com

# Telegram Bot Alerts (FREE & UNLIMITED)
# Step 1: Open Telegram → search @BotFather → /newbot → get your TOKEN
# Step 2: Start your bot, send any message, then open:
#         https://api.telegram.org/botYOUR_TOKEN/getUpdates
#         Find "id" inside "chat" — that's your CHAT_ID
TELEGRAM_TOKEN   = "8234321568:AAHbZxY7FSKZMJEKmxGZZcZcnVpzDSknKGY" # Bot token added
TELEGRAM_CHAT_ID = "5091612018"    # Chat ID automatically extracted
TELEGRAM_ENABLED = True            # Alerts are now active!

# -------------------------------
# Database
# -------------------------------
def get_db_connection():
    conn = sqlite3.connect("tracking.db")
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gps_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT,
            latitude REAL,
            longitude REAL,
            timestamp TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT,
            trip_count INTEGER,
            recorded_time TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT,
            violation_type TEXT,
            recorded_time TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT UNIQUE,
            exc_lat_min REAL, exc_lat_max REAL, exc_lon_min REAL, exc_lon_max REAL,
            dmp_lat_min REAL, dmp_lat_max REAL, dmp_lon_min REAL, dmp_lon_max REAL,
            cor_lat_min REAL, cor_lat_max REAL, cor_lon_min REAL, cor_lon_max REAL,
            updated_time TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT,
            event_type TEXT,
            detail TEXT,
            latitude REAL,
            longitude REAL,
            recorded_time TEXT
        )
    """)

    conn.commit()
    conn.close()

# -------------------------------
# Static Data
# -------------------------------
registered_vehicles = {
    "TN09AB1234": {
        "permit_id": "PERMIT001",
        "max_trips": 5,
        "active": True
    }
}

# St. Joseph's College of Engineering, Chennai (OMR)
# Excavation Zone: ~5m radius area at the college
EXCAVATION_ZONE = {
    "lat_min": 12.86940,
    "lat_max": 12.86950,
    "lon_min": 80.21578,
    "lon_max": 80.21588
}

# Dump Zone: ~5 meters north of excavation
DUMP_ZONE = {
    "lat_min": 12.86985,
    "lat_max": 12.86995,
    "lon_min": 80.21578,
    "lon_max": 80.21588
}

# Route Corridor: covers both zones and the path between
ROUTE_CORRIDOR = {
    "lat_min": 12.86930,
    "lat_max": 12.87000,
    "lon_min": 80.21570,
    "lon_max": 80.21600
}

def load_zones_from_db():
    """Load persisted zone coordinates from DB on startup."""
    global EXCAVATION_ZONE, DUMP_ZONE, ROUTE_CORRIDOR
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM zones WHERE vehicle_id = 'TN09AB1234'")
    row = cursor.fetchone()
    conn.close()
    if row:
        EXCAVATION_ZONE = {
            "lat_min": row["exc_lat_min"], "lat_max": row["exc_lat_max"],
            "lon_min": row["exc_lon_min"], "lon_max": row["exc_lon_max"]
        }
        DUMP_ZONE = {
            "lat_min": row["dmp_lat_min"], "lat_max": row["dmp_lat_max"],
            "lon_min": row["dmp_lon_min"], "lon_max": row["dmp_lon_max"]
        }
        ROUTE_CORRIDOR = {
            "lat_min": row["cor_lat_min"], "lat_max": row["cor_lat_max"],
            "lon_min": row["cor_lon_min"], "lon_max": row["cor_lon_max"]
        }
        print("[DB] Zones loaded from database.")
    else:
        print("[DB] No saved zones found, using defaults.")

vehicle_state = {
    "TN09AB1234": {
        "in_excavation": True,
        "trip_active": False,
        "trip_count": 0,
        "sms_sent": False,
        "route_sms_sent": False
    }
}

vehicle_violation = {"TN09AB1234": False}
route_violation = {"TN09AB1234": False}

def is_inside_zone(lat, lon, zone):
    return (
        zone["lat_min"] <= lat <= zone["lat_max"] and
        zone["lon_min"] <= lon <= zone["lon_max"]
    )

def send_sms(phone, message):
    safe_msg = message.encode('ascii', 'ignore').decode('ascii')
    print(f"Attempting to send SMS to {phone}: {safe_msg}")
    url = "https://textbelt.com/text"
    data = urllib.parse.urlencode({
        'phone': phone,
        'message': message,
        'key': SMS_API_KEY
    }).encode('ascii')
    try:
        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode('utf-8'))
            print(f"SMS Response: {result}")
            return result.get("success", False)
    except Exception as e:
        print(f"Failed to send SMS: {e}")
        return False

def send_telegram(message):
    """Send a Telegram message via Bot API (free, unlimited)."""
    if not TELEGRAM_ENABLED or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram] Disabled or credentials not set. Skipping.")
        return False
    try:
        safe_msg = message.encode('ascii', 'ignore').decode('ascii')
        print(f"[Telegram] Sending message: {safe_msg}")
        encoded_msg = urllib.parse.quote(message)
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={encoded_msg}&parse_mode=Markdown"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get('ok'):
                print(f"[Telegram] Message sent successfully.")
                return True
            else:
                print(f"[Telegram] Failed: {result}")
                return False
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False

def alert(message):
    """Send both SMS and Telegram alerts."""
    send_sms(ALERT_PHONE, message)
    send_telegram(message)

# -------------------------------
# Routes
# -------------------------------
@app.route("/")
def home():
    return "Backend Server Running"

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

# Set zones dynamically from dashboard map clicks
@app.route("/set_zones", methods=["POST"])
def set_zones():
    global EXCAVATION_ZONE, DUMP_ZONE, ROUTE_CORRIDOR
    data = request.get_json()

    radius = 0.0002  # ~20 meters radius (phone GPS friendly)

    if "start" in data:
        lat, lon = data["start"]["lat"], data["start"]["lon"]
        EXCAVATION_ZONE = {
            "lat_min": lat - radius, "lat_max": lat + radius,
            "lon_min": lon - radius, "lon_max": lon + radius
        }

    if "end" in data:
        lat, lon = data["end"]["lat"], data["end"]["lon"]
        DUMP_ZONE = {
            "lat_min": lat - radius, "lat_max": lat + radius,
            "lon_min": lon - radius, "lon_max": lon + radius
        }

    # Update route corridor to cover both zones
    ROUTE_CORRIDOR = {
        "lat_min": min(EXCAVATION_ZONE["lat_min"], DUMP_ZONE["lat_min"]) - 0.001,
        "lat_max": max(EXCAVATION_ZONE["lat_max"], DUMP_ZONE["lat_max"]) + 0.001,
        "lon_min": min(EXCAVATION_ZONE["lon_min"], DUMP_ZONE["lon_min"]) - 0.001,
        "lon_max": max(EXCAVATION_ZONE["lon_max"], DUMP_ZONE["lon_max"]) + 0.001
    }

    # Persist zones to database
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO zones (
            vehicle_id,
            exc_lat_min, exc_lat_max, exc_lon_min, exc_lon_max,
            dmp_lat_min, dmp_lat_max, dmp_lon_min, dmp_lon_max,
            cor_lat_min, cor_lat_max, cor_lon_min, cor_lon_max,
            updated_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vehicle_id) DO UPDATE SET
            exc_lat_min=excluded.exc_lat_min, exc_lat_max=excluded.exc_lat_max,
            exc_lon_min=excluded.exc_lon_min, exc_lon_max=excluded.exc_lon_max,
            dmp_lat_min=excluded.dmp_lat_min, dmp_lat_max=excluded.dmp_lat_max,
            dmp_lon_min=excluded.dmp_lon_min, dmp_lon_max=excluded.dmp_lon_max,
            cor_lat_min=excluded.cor_lat_min, cor_lat_max=excluded.cor_lat_max,
            cor_lon_min=excluded.cor_lon_min, cor_lon_max=excluded.cor_lon_max,
            updated_time=excluded.updated_time
    """, (
        'TN09AB1234',
        EXCAVATION_ZONE["lat_min"], EXCAVATION_ZONE["lat_max"],
        EXCAVATION_ZONE["lon_min"], EXCAVATION_ZONE["lon_max"],
        DUMP_ZONE["lat_min"], DUMP_ZONE["lat_max"],
        DUMP_ZONE["lon_min"], DUMP_ZONE["lon_max"],
        ROUTE_CORRIDOR["lat_min"], ROUTE_CORRIDOR["lat_max"],
        ROUTE_CORRIDOR["lon_min"], ROUTE_CORRIDOR["lon_max"],
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()
    print("[DB] Zones saved to database.")

    return jsonify({"status": "Zones updated", "excavation": EXCAVATION_ZONE, "dump": DUMP_ZONE})

# Reset trip count
@app.route("/reset_trips", methods=["POST"])
def reset_trips():
    vehicle_id = "TN09AB1234"
    vehicle_state[vehicle_id]["trip_count"] = 0
    vehicle_state[vehicle_id]["in_excavation"] = True
    vehicle_state[vehicle_id]["trip_active"] = False
    vehicle_state[vehicle_id]["sms_sent"] = False
    vehicle_state[vehicle_id]["route_sms_sent"] = False
    vehicle_violation[vehicle_id] = False
    route_violation[vehicle_id] = False
    return jsonify({"status": "Trips reset", "trip_count": 0})

# Get current zone coordinates
@app.route("/get_zones", methods=["GET"])
def get_zones():
    return jsonify({
        "excavation": EXCAVATION_ZONE,
        "dump": DUMP_ZONE,
        "corridor": ROUTE_CORRIDOR
    })

# Event history: violations + trip completions
@app.route("/event_history", methods=["GET"])
def event_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT event_type, detail, latitude, longitude, recorded_time
        FROM events
        WHERE vehicle_id = 'TN09AB1234'
        ORDER BY id DESC LIMIT 30
    """)
    rows = cursor.fetchall()
    conn.close()
    events = [{
        "event_type": r["event_type"],
        "detail": r["detail"],
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "recorded_time": r["recorded_time"]
    } for r in rows]
    return jsonify({"events": events})

# Dashboard data API
@app.route("/dashboard_data", methods=["GET"])
def dashboard_data():
    vehicle_id = "TN09AB1234"
    state = vehicle_state[vehicle_id]

    return jsonify({
        "vehicle_id": vehicle_id,
        "trip_count": state["trip_count"],
        "trip_limit": registered_vehicles[vehicle_id]["max_trips"],
        "trip_violation": vehicle_violation[vehicle_id],
        "route_violation": route_violation[vehicle_id],
        "in_excavation": state["in_excavation"],
        "trip_active": state["trip_active"]
    })

# Latest GPS location API
@app.route("/gps_location", methods=["GET"])
def gps_location():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT latitude, longitude, timestamp FROM gps_logs
        WHERE vehicle_id = 'TN09AB1234'
        ORDER BY id DESC LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        return jsonify({
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "timestamp": row["timestamp"]
        })
    else:
        # Default to excavation zone center if no GPS data yet
        return jsonify({
            "latitude": 12.86945,
            "longitude": 80.21583,
            "timestamp": datetime.now().isoformat()
        })

# GPS history for route trail
@app.route("/gps_history", methods=["GET"])
def gps_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT latitude, longitude, timestamp FROM gps_logs
        WHERE vehicle_id = 'TN09AB1234'
        ORDER BY id DESC LIMIT 50
    """)
    rows = cursor.fetchall()
    conn.close()

    history = [{"latitude": r["latitude"], "longitude": r["longitude"], "timestamp": r["timestamp"]} for r in rows]
    history.reverse()  # oldest first for drawing trail

    return jsonify({"history": history})

# GPS receive API
@app.route("/send_gps", methods=["POST"])
def receive_gps():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 415

    data = request.get_json()

    required_fields = ["vehicle_id", "latitude", "longitude", "timestamp"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    vehicle_id = data["vehicle_id"]
    latitude = data["latitude"]
    longitude = data["longitude"]
    timestamp = data["timestamp"]

    # Save GPS data to database for trail/history
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO gps_logs (vehicle_id, latitude, longitude, timestamp) VALUES (?, ?, ?, ?)",
        (vehicle_id, latitude, longitude, timestamp)
    )
    conn.commit()
    conn.close()

    state = vehicle_state[vehicle_id]
    conn = get_db_connection()

    inside_excavation = is_inside_zone(latitude, longitude, EXCAVATION_ZONE)
    inside_dump = is_inside_zone(latitude, longitude, DUMP_ZONE)
    inside_route = is_inside_zone(latitude, longitude, ROUTE_CORRIDOR)

    if state["in_excavation"] and not inside_excavation:
        state["trip_active"] = True
        state["in_excavation"] = False

    if state["trip_active"] and inside_dump:
        state["trip_active"] = False
        state["trip_count"] += 1
        state["in_excavation"] = True
        # Log trip completion event
        conn.execute(
            "INSERT INTO events (vehicle_id, event_type, detail, latitude, longitude, recorded_time) VALUES (?, ?, ?, ?, ?, ?)",
            (vehicle_id, "TRIP_COMPLETE",
             f"Trip #{state['trip_count']} completed",
             latitude, longitude, datetime.now().isoformat())
        )
        conn.commit()

    if state["trip_count"] > registered_vehicles[vehicle_id]["max_trips"]:
        vehicle_violation[vehicle_id] = True
        if not state.get("sms_sent", False):
            msg = f"🚨 ALERT: Vehicle {vehicle_id} has exceeded its trip limit! Immediate action required."
            alert(msg)
            state["sms_sent"] = True
            # Log trip-limit violation event
            conn.execute(
                "INSERT INTO events (vehicle_id, event_type, detail, latitude, longitude, recorded_time) VALUES (?, ?, ?, ?, ?, ?)",
                (vehicle_id, "TRIP_LIMIT_EXCEEDED",
                 f"Exceeded max trips ({registered_vehicles[vehicle_id]['max_trips']}). Count: {state['trip_count']}",
                 latitude, longitude, datetime.now().isoformat())
            )
            conn.commit()

    if not inside_route:
        route_violation[vehicle_id] = True
        vehicle_violation[vehicle_id] = True
        if not state.get("route_sms_sent", False):
            msg = f"🚨 ALERT: Vehicle {vehicle_id} has left the permitted route! Check location immediately."
            alert(msg)
            state["route_sms_sent"] = True
            # Log route deviation event
            conn.execute(
                "INSERT INTO events (vehicle_id, event_type, detail, latitude, longitude, recorded_time) VALUES (?, ?, ?, ?, ?, ?)",
                (vehicle_id, "ROUTE_DEVIATION",
                 f"Vehicle moved outside the permitted corridor at ({latitude:.6f}, {longitude:.6f})",
                 latitude, longitude, datetime.now().isoformat())
            )
            conn.commit()

    conn.close()

    return jsonify({
        "status": "VIOLATION DETECTED" if vehicle_violation[vehicle_id] else "GPS processed",
        "vehicle_id": vehicle_id,
        "trip_count": state["trip_count"]
    })

# -------------------------------
# Start Server
# -------------------------------
if __name__ == "__main__":
    create_tables()
    load_zones_from_db()  # Restore persisted zones on startup
    app.run(host="0.0.0.0", debug=True, ssl_context='adhoc')