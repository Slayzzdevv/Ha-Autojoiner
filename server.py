from flask import Flask, jsonify, request
from datetime import datetime
import threading

app = Flask(__name__)

brainrots = []
lock = threading.Lock()

MAX_BRAINROTS = 100
EXPIRATION_SECONDS = 300

def clean_old():
    global brainrots
    now = datetime.now().timestamp()
    with lock:
        brainrots = [b for b in brainrots if now - b.get("timestamp", 0) < EXPIRATION_SECONDS]

@app.route("/", methods=["GET"])
def home():
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

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

