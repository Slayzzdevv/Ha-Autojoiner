from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime
import threading
import os

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

def clean_old():
    global brainrots
    now = datetime.now().timestamp()
    with lock:
        brainrots = [b for b in brainrots if now - b.get("timestamp", 0) < EXPIRATION_SECONDS]

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
    
    return jsonify({"status": "saved", "settings": user_settings[user_id]})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

