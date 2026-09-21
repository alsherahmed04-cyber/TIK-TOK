import os, json, threading, time
from flask import Flask, request, jsonify
from flask_cors import CORS
import bot as B

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type", "X-Password"],
     methods=["GET", "POST", "OPTIONS"])
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Ahmed")
ACC_FILE = "accounts.json"
lock = threading.Lock()

def load_data():
    with lock:
        if not os.path.exists(ACC_FILE):
            return {"accounts": []}
        with open(ACC_FILE, encoding='utf-8') as f:
            return json.load(f)

def save_data(d):
    with lock:
        with open(ACC_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

class Manager:
    def __init__(self):
        self.running = False
        self.stop_event = threading.Event()
        self.logs = []
        self.log_lock = threading.Lock()
        self.scores = {}
        self.status = {}
    def log(self, msg):
        with self.log_lock:
            self.logs.append(msg)
            if len(self.logs) > 2000:
                self.logs.pop(0)
    def set_score(self, user, score):
        self.scores[user] = score
    def run_account(self, acc):
        u = acc["username"]
        p = acc.get("password", "")
        px = (acc.get("proxy") or "").strip() or None
        self.status[u] = "جاري الدخول"
        t, c, user = B.login(u, p, px)
        if not t:
            self.status[u] = "فشل الدخول"
            self.log(f"[X] {u}: فشل الدخول")
            return
        B.attest(t, c, px)
        self.set_score(u, user.get("score", 0))
        self.status[u] = "شغال"
        self.log(f"[OK] {u} متصل")
        B.farmer(u, t, c, self.stop_event, self.log, px, lambda s: self.set_score(u, s))
        self.status[u] = "متوقف"
    def start_one(self, acc, delay=0):
        if delay: time.sleep(delay)
        if not self.stop_event.is_set():
            self.run_account(acc)
    def start(self):
        if self.running:
            return False, "البوت شغال بالفعل"
        data = load_data()
        accounts = data.get("accounts", [])
        if not accounts:
            return False, "لا توجد حسابات"
        self.stop_event.clear()
        self.running = True
        self.log(f"[SYSTEM] تشغيل ({len(accounts)} حساب)")
        for i, acc in enumerate(accounts):
            t = threading.Thread(target=self.start_one, args=(acc, i * 5), daemon=True)
            t.start()
        return True, "تم التشغيل"
    def add_account_live(self, acc):
        if self.running:
            t = threading.Thread(target=self.start_one, args=(acc, 0), daemon=True)
            t.start()
    def stop(self):
        if not self.running:
            return False, "البوت مش شغال"
        self.stop_event.set()
        self.running = False
        self.log("[SYSTEM] إيقاف")
        return True, "تم الإيقاف"

manager = Manager()

def auth_ok():
    return request.headers.get("X-Password") == ADMIN_PASSWORD

@app.route("/")
def home():
    return "<h1>MOON API Running</h1>"

@app.route("/api/data")
def api_data():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = load_data()
    with manager.log_lock:
        logs = list(manager.logs[-200:])
    return jsonify({
        "accounts": d.get("accounts", []),
        "running": manager.running,
        "scores": manager.scores,
        "status": manager.status,
        "logs": logs
    })

@app.route("/api/start", methods=["POST"])
def api_start():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    ok, msg = manager.start()
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/stop", methods=["POST"])
def api_stop():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    ok, msg = manager.stop()
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/clear", methods=["POST"])
def api_clear():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    with manager.log_lock:
        manager.logs.clear()
    return jsonify({"ok": True, "msg": "تم مسح السجل"})

@app.route("/api/add", methods=["POST"])
def api_add():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    u = (d.get("username") or "").strip()
    p = (d.get("password") or "").strip()
    if not u or not p:
        return jsonify({"ok": False, "msg": "أدخل الاسم وكلمة المرور"})
    data = load_data()
    if any(a["username"] == u for a in data["accounts"]):
        return jsonify({"ok": False, "msg": "الحساب موجود"})
    new_acc = {"username": u, "password": p, "proxy": (d.get("proxy") or "").strip()}
    data["accounts"].append(new_acc)
    save_data(data)
    if manager.running:
        manager.add_account_live(new_acc)
    return jsonify({"ok": True, "msg": f"تم إضافة {u}"})

@app.route("/api/delete", methods=["POST"])
def api_delete():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    u = (d.get("username") or "").strip()
    data = load_data()
    data["accounts"] = [a for a in data["accounts"] if a["username"] != u]
    save_data(data)
    manager.scores.pop(u, None)
    manager.status.pop(u, None)
    return jsonify({"ok": True, "msg": f"تم حذف {u}"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
