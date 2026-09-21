import os, json, threading
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# CORS: اسمح لأي origin مع الهيدرز المطلوبة
CORS(app, resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type", "X-Password"],
     methods=["GET", "POST", "OPTIONS"],
     supports_credentials=False)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Ahmed")
ACC_FILE = "accounts.json"
lock = threading.Lock()

def load_data():
    with lock:
        if not os.path.exists(ACC_FILE):
            return {"accounts": [], "target_user": ""}
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
            if len(self.logs) > 2000: self.logs.pop(0)
    def run_account(self, acc, target, avatar, init_count):
        import bot as B
        u = acc["username"]
        self.status[u] = "جاري الدخول"
        t, c, user = B.login(u, acc["password"])
        if not t:
            self.status[u] = "فشل الدخول"
            self.log(f"[X] {u}: فشل الدخول")
            return
        B.attest(t, c)
        self.scores[u] = user.get("score", 0)
        self.status[u] = "شغال"
        B.farmer(u, t, c, target, avatar, init_count, self.stop_event, self.log)
        self.status[u] = "متوقف"
    def start(self):
        import bot as B
        if self.running: return False, "البوت شغال بالفعل"
        data = load_data()
        accounts = data.get("accounts", [])
        target = data.get("target_user", "")
        if not accounts: return False, "لا توجد حسابات"
        if not target: return False, "حدد الحساب المستهدف"
        tacc = next((a for a in accounts if a["username"] == target), None)
        if not tacc: return False, "الهدف غير موجود"
        t_tok, t_csrf, _ = B.login(target, tacc["password"])
        if not t_tok: return False, "فشل الدخول للحساب المستهدف"
        me = B.fetch_user_data(t_tok, t_csrf)
        avatar = me.get("avatar", "") or "https://p16-common-sign.tiktokcdn-eu.com/tos-alisg-avt-0068/0cd6feb16816a94d33aec63be51033f2~tplv-tiktokx-cropcenter:720:720.jpeg"
        init = me.get("followerCount", 0) or 0
        self.stop_event.clear()
        self.running = True
        self.log(f"[SYSTEM] تشغيل البوت ({len(accounts)} حساب)")
        for acc in accounts:
            threading.Thread(target=self.run_account, args=(acc, target, avatar, init), daemon=True).start()
        return True, "تم التشغيل"
    def stop(self):
        if not self.running: return False, "البوت مش شغال"
        self.stop_event.set()
        self.running = False
        self.log("[SYSTEM] إيقاف البوت")
        return True, "تم الإيقاف"

manager = Manager()

def auth_ok():
    return request.headers.get("X-Password") == ADMIN_PASSWORD

@app.route("/")
def home(): return "<h1>MOON API Running</h1>"

@app.route("/api/data")
def api_data():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = load_data()
    with manager.log_lock: logs = list(manager.logs[-200:])
    return jsonify({"accounts": d.get("accounts", []), "target_user": d.get("target_user", ""),
        "running": manager.running, "scores": manager.scores, "status": manager.status, "logs": logs})

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
    with manager.log_lock: manager.logs.clear()
    return jsonify({"ok": True, "msg": "تم المسح"})

@app.route("/api/add", methods=["POST"])
def api_add():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    u = (d.get("username") or "").strip()
    p = (d.get("password") or "").strip()
    if not u or not p: return jsonify({"ok": False, "msg": "أدخل الاسم وكلمة المرور"})
    data = load_data()
    if any(a["username"] == u for a in data["accounts"]):
        return jsonify({"ok": False, "msg": "الحساب موجود"})
    data["accounts"].append({"username": u, "password": p})
    save_data(data)
    return jsonify({"ok": True, "msg": f"تم إضافة {u}"})

@app.route("/api/delete", methods=["POST"])
def api_delete():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    u = (d.get("username") or "").strip()
    data = load_data()
    data["accounts"] = [a for a in data["accounts"] if a["username"] != u]
    if data.get("target_user") == u: data["target_user"] = ""
    save_data(data)
    return jsonify({"ok": True, "msg": f"تم حذف {u}"})

@app.route("/api/target", methods=["POST"])
def api_target():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    u = (d.get("username") or "").strip()
    data = load_data()
    if not any(a["username"] == u for a in data["accounts"]):
        return jsonify({"ok": False, "msg": "الحساب غير موجود"})
    data["target_user"] = u
    save_data(data)
    return jsonify({"ok": True, "msg": f"الهدف: {u}"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
