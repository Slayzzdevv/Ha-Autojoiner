from flask import Flask, jsonify, request
from datetime import datetime
import threading
import os
import json
import time

def read_dashboard():
    try:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return None

app = Flask(__name__)

brainrots = []
lock = threading.Lock()

MAX_BRAINROTS = 100
EXPIRATION_SECONDS = 40

user_settings = {}
settings_lock = threading.Lock()

HWID_FILE = "authorized_hwids.json"
authorized_hwids = []
hwid_lock = threading.Lock()
MAX_AUTHORIZED_HWIDS = 2

# Control panel data
control_settings = {
    "global_filter": 10000000,
    "global_autojoin": False,
    "maintenance_mode": False
}
control_lock = threading.Lock()

user_activity = {}  # {user_id: {"last_seen": timestamp, "settings": {}}}
activity_lock = threading.Lock()

broadcast_messages = []
broadcast_lock = threading.Lock()

kicked_users = set()  # Track kicked users
kicked_lock = threading.Lock()

def load_authorized_hwids():
    global authorized_hwids
    try:
        if os.path.exists(HWID_FILE):
            with open(HWID_FILE, 'r') as f:
                data = json.load(f)
                authorized_hwids = data.get('hwids', [])
                print(f"Loaded {len(authorized_hwids)} authorized HWIDs from file")
    except Exception as e:
        print(f"Error loading HWIDs: {e}")
        authorized_hwids = []

def save_authorized_hwids():
    try:
        with open(HWID_FILE, 'w') as f:
            json.dump({'hwids': authorized_hwids}, f)
        print(f"Saved {len(authorized_hwids)} authorized HWIDs to file")
    except Exception as e:
        print(f"Error saving HWIDs: {e}")

load_authorized_hwids()

def clean_old():
    global brainrots
    now = datetime.now().timestamp()
    with lock:
        brainrots = [b for b in brainrots if now - b.get("timestamp", 0) < EXPIRATION_SECONDS]

@app.route("/api/verify-hwid", methods=["POST"])
def verify_hwid():
    data = request.get_json()
    if not data or "hwid" not in data:
        return jsonify({"error": "no hwid provided"}), 400
    
    hwid = data["hwid"]
    
    with hwid_lock:
        if hwid in authorized_hwids:
            return jsonify({"authorized": True, "message": "Access granted"})
        
        if len(authorized_hwids) < MAX_AUTHORIZED_HWIDS:
            authorized_hwids.append(hwid)
            save_authorized_hwids()
            return jsonify({"authorized": True, "message": "HWID added to authorized list"})
        else:
            return jsonify({"authorized": False, "message": "Maximum authorized HWIDs reached"}), 403

@app.route("/", methods=["GET"])
def home():
    dashboard_html = read_dashboard()
    if dashboard_html:
        return dashboard_html
    else:
        return """
        <html>
        <head><title>HA AutoJoiner API</title></head>
        <body style="font-family: Arial; padding: 40px; background: #0d0d12; color: #fff;">
            <h1>🧠 HA AutoJoiner API</h1>
            <p>API Status: Online</p>
            <p>Brainrots: <a href="/api/brainrots" style="color: #7c3aed;">/api/brainrots</a></p>
            <p>Dashboard: <a href="/dashboard.html" style="color: #7c3aed;">/dashboard.html</a></p>
        </body>
        </html>
        """

@app.route("/dashboard.html", methods=["GET"])
def dashboard():
    dashboard_html = read_dashboard()
    if dashboard_html:
        return dashboard_html
    else:
        return "Dashboard not found", 404

@app.route("/control.html", methods=["GET"])
def control():
    try:
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "control.html")
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return "Control panel not found", 404

@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({"status": "online", "brainrots": len(brainrots)})

@app.route("/api/brainrots", methods=["GET"])
def get_brainrots():
    clean_old()
    with lock:
        sorted_list = sorted(brainrots, key=lambda x: x.get("value", 0), reverse=True)
    return jsonify({"brainrots": sorted_list})

@app.route("/api/brainrots", methods=["POST"])
def add_brainrot():
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400
    
    required = ["name", "displayValue", "jobId", "value"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"missing {field}"}), 400
    
    clean_old()
    
    brainrot = {
        "name": data["name"],
        "displayValue": data["displayValue"],
        "jobId": data["jobId"],
        "value": data["value"],
        "playerCount": data.get("playerCount", "?/8"),
        "imageUrl": data.get("imageUrl"),
        "timestamp": datetime.now().timestamp()
    }
    
    with lock:
        for i, existing in enumerate(brainrots):
            if existing["jobId"] == brainrot["jobId"] and existing["name"] == brainrot["name"]:
                brainrots[i] = brainrot
                return jsonify({"status": "updated", "brainrot": brainrot})
        
        if len(brainrots) >= MAX_BRAINROTS:
            brainrots.sort(key=lambda x: x.get("value", 0))
            brainrots.pop(0)
        
        brainrots.append(brainrot)
    
    return jsonify({"status": "added", "brainrot": brainrot})

@app.route("/api/brainrots", methods=["DELETE"])
def clear_brainrots():
    global brainrots
    with lock:
        brainrots = []
    return jsonify({"status": "cleared"})

@app.route("/api/brainrots/<job_id>", methods=["DELETE"])
def delete_brainrot(job_id):
    global brainrots
    with lock:
        brainrots = [b for b in brainrots if b["jobId"] != job_id]
    return jsonify({"status": "deleted"})

@app.route("/api/settings/<user_id>", methods=["GET"])
def get_settings(user_id):
    # Track user activity when loading settings
    with activity_lock:
        if user_id not in user_activity:
            user_activity[user_id] = {}
        user_activity[user_id]["last_seen"] = datetime.now().timestamp()
        
        # Get current settings if available
        with settings_lock:
            if user_id in user_settings:
                user_activity[user_id]["settings"] = user_settings[user_id]
    
    with settings_lock:
        settings = user_settings.get(user_id, {})
    return jsonify({"settings": settings})

@app.route("/api/settings/<user_id>", methods=["POST"])
def save_settings(user_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400
    
    with settings_lock:
        user_settings[user_id] = data.get("settings", {})
    
    # Track user activity
    with activity_lock:
        if user_id not in user_activity:
            user_activity[user_id] = {}
        user_activity[user_id]["last_seen"] = datetime.now().timestamp()
        user_activity[user_id]["settings"] = user_settings[user_id]
    
    return jsonify({"status": "saved", "settings": user_settings[user_id]})

# Endpoint for Lua to check for commands
@app.route("/api/client/commands/<user_id>", methods=["GET"])
def get_client_commands(user_id):
    # Track user activity when checking for commands
    with activity_lock:
        if user_id not in user_activity:
            user_activity[user_id] = {}
        user_activity[user_id]["last_seen"] = datetime.now().timestamp()
        
        # Update settings if available
        with settings_lock:
            if user_id in user_settings:
                user_activity[user_id]["settings"] = user_settings[user_id]
    
    commands = []
    
    # Check for kick
    with kicked_lock:
        if user_id in kicked_users:
            commands.append({"type": "kick", "reason": "User kicked by admin"})
            return jsonify({"commands": commands})  # Return immediately after kick
    
    # Check for global settings
    with control_lock:
        if control_settings.get("maintenance_mode", False):
            commands.append({"type": "maintenance", "message": "Server in maintenance mode"})
    
    # Send broadcast messages
    with broadcast_lock:
        if broadcast_messages:
            for msg in broadcast_messages:
                commands.append({"type": "broadcast", "message": msg["text"]})
    
    # Send updated settings if they exist
    with settings_lock:
        if user_id in user_settings:
            commands.append({"type": "settings", "data": user_settings[user_id]})
    
    return jsonify({"commands": commands})

# Control Panel Endpoints

@app.route("/api/control/stats", methods=["GET"])
def get_control_stats():
    with activity_lock:
        # Count users active in last 24 hours
        now = datetime.now().timestamp()
        connected = len([u for u, data in user_activity.items() 
                        if now - data.get("last_seen", 0) < 86400])
        
        # Count active autojoins
        active_autojoins = len([u for u, data in user_activity.items() 
                               if data.get("settings", {}).get("autoJoinEnabled", False)])
    
    return jsonify({
        "connected_users": connected,
        "active_autojoins": active_autojoins,
        "total_brainrots": len(brainrots)
    })

@app.route("/api/control/settings", methods=["GET"])
def get_control_settings():
    with control_lock:
        return jsonify(control_settings)

@app.route("/api/control/settings/global-filter", methods=["POST"])
def set_global_filter():
    data = request.get_json()
    if not data or "value" not in data:
        return jsonify({"error": "no value provided"}), 400
    
    with control_lock:
        control_settings["global_filter"] = data["value"]
    
    # Apply to all users
    with settings_lock:
        for user_id in user_settings:
            if "minMoneyFilter" in user_settings[user_id]:
                user_settings[user_id]["minMoneyFilter"] = data["value"]
    
    return jsonify({"status": "success", "value": data["value"]})

@app.route("/api/control/settings/global-autojoin", methods=["POST"])
def toggle_global_autojoin():
    data = request.get_json()
    if not data or "enabled" not in data:
        return jsonify({"error": "no enabled value provided"}), 400
    
    with control_lock:
        control_settings["global_autojoin"] = data["enabled"]
    
    # Apply to all users
    with settings_lock:
        for user_id in user_settings:
            user_settings[user_id]["autoJoinEnabled"] = data["enabled"]
    
    return jsonify({"status": "success", "enabled": data["enabled"]})

@app.route("/api/control/settings/maintenance", methods=["POST"])
def toggle_maintenance():
    data = request.get_json()
    if not data or "enabled" not in data:
        return jsonify({"error": "no enabled value provided"}), 400
    
    with control_lock:
        control_settings["maintenance_mode"] = data["enabled"]
    
    return jsonify({"status": "success", "enabled": data["enabled"]})

@app.route("/api/control/broadcast", methods=["POST"])
def send_broadcast():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "no message provided"}), 400
    
    message = {
        "text": data["message"],
        "timestamp": datetime.now().timestamp()
    }
    
    with broadcast_lock:
        broadcast_messages.append(message)
        # Keep only last 10 messages
        if len(broadcast_messages) > 10:
            broadcast_messages.pop(0)
    
    return jsonify({"status": "success", "message": message})

@app.route("/api/control/broadcast/command", methods=["POST"])
def send_broadcast_command():
    data = request.get_json()
    if not data or "command" not in data:
        return jsonify({"error": "no command provided"}), 400
    
    command = data["command"]
    
    # Apply command to all users
    with settings_lock:
        for user_id in user_settings:
            if command == "pause":
                user_settings[user_id]["autoJoinEnabled"] = False
            elif command == "resume":
                user_settings[user_id]["autoJoinEnabled"] = True
    
    return jsonify({"status": "success", "command": command})

@app.route("/api/control/users", methods=["GET"])
def get_users():
    with activity_lock:
        now = datetime.now().timestamp()
        users = []
        
        for user_id, data in user_activity.items():
            last_seen = data.get("last_seen", 0)
            if now - last_seen < 86400:  # Last 24 hours
                settings = data.get("settings", {})
                users.append({
                    "user_id": user_id,
                    "last_seen": last_seen,
                    "auto_join_enabled": settings.get("autoJoinEnabled", False),
                    "min_filter": settings.get("minMoneyFilter", 0)
                })
        
        return jsonify({"users": users})

@app.route("/api/control/user/<user_id>/filter", methods=["POST"])
def set_user_filter(user_id):
    data = request.get_json()
    if not data or "value" not in data:
        return jsonify({"error": "no value provided"}), 400
    
    with settings_lock:
        if user_id not in user_settings:
            user_settings[user_id] = {}
        user_settings[user_id]["minMoneyFilter"] = data["value"]
    
    return jsonify({"status": "success", "user_id": user_id, "value": data["value"]})

@app.route("/api/control/user/<user_id>/kick", methods=["POST"])
def kick_user(user_id):
    with activity_lock:
        if user_id in user_activity:
            del user_activity[user_id]
    
    with settings_lock:
        if user_id in user_settings:
            del user_settings[user_id]
    
    # Add to kicked users set
    with kicked_lock:
        kicked_users.add(user_id)
    
    # Remove from kicked set after 30 seconds
    def remove_from_kicked():
        time.sleep(30)
        with kicked_lock:
            kicked_users.discard(user_id)
    
    threading.Thread(target=remove_from_kicked, daemon=True).start()
    
    return jsonify({"status": "success", "user_id": user_id})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

