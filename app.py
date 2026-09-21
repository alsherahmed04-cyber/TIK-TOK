import os, json, threading, time
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import bot as B

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type", "X-Password"],
     methods=["GET", "POST", "OPTIONS"])
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Ahmed")
ACC_FILE = "accounts.json"
HIST_FILE = "history.json"
TX_FILE = "transactions.json"
lock = threading.Lock()

def load_data():
    with lock:
        if not os.path.exists(ACC_FILE):
            return {"accounts": [], "rotation_seconds": 600}
        with open(ACC_FILE, encoding='utf-8') as f:
            d = json.load(f)
            d.setdefault("rotation_seconds", 600)
            return d

def save_data(d):
    with lock:
        with open(ACC_FILE, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

def load_tx():
    with lock:
        if not os.path.exists(TX_FILE): return []
        try:
            with open(TX_FILE, encoding='utf-8') as f: return json.load(f)
        except: return []

def save_tx(t):
    with lock:
        with open(TX_FILE, 'w', encoding='utf-8') as f:
            json.dump(t, f, ensure_ascii=False, indent=2)

def append_tx(entry):
    t = load_tx()
    t.append(entry)
    if len(t) > 2000: t = t[-2000:]
    save_tx(t)

def load_history():
    with lock:
        if not os.path.exists(HIST_FILE): return []
        try:
            with open(HIST_FILE, encoding='utf-8') as f: return json.load(f)
        except: return []

def save_history(h):
    with lock:
        with open(HIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(h, f, ensure_ascii=False, indent=2)

def append_history(entry):
    h = load_history()
    h.append(entry)
    if len(h) > 1000: h = h[-1000:]
    save_history(h)

class Manager:
    def __init__(self):
        self.logs = []
        self.log_lock = threading.Lock()
        self.scores = {}
        self.status = {}
        self.threads = {}      # username -> (stop_event, thread, start_time)
    def log(self, msg, kind="info"):
        with self.log_lock:
            self.logs.append({"t": datetime.now().strftime("%H:%M:%S"), "m": msg, "k": kind})
            if len(self.logs) > 2000: self.logs.pop(0)
    def set_score(self, user, score):
        self.scores[user] = score
    def run_account(self, acc, stop_ev):
        u = acc["username"]; p = acc.get("password","")
        self.status[u] = "جاري الدخول"
        self.log(f"[{u}] جاري تسجيل الدخول...", "info")
        t, c, user = B.login(u, p)
        if not t:
            self.status[u] = "فشل الدخول"
            self.log(f"[{u}] ❌ فشل الدخول", "err")
            return
        B.attest(t, c, None, u)
        start_score = user.get("score", 0) or 0
        self.set_score(u, start_score)
        self.status[u] = "شغال"
        self.log(f"[{u}] ✅ متصل - رصيد البداية: {start_score}", "ok")
        session = {"start_time": time.time(), "start_score": start_score, "end_score": start_score}
        def scb(s):
            self.set_score(u, s); session["end_score"] = s
        B.farmer(u, t, c, stop_ev, lambda m: self.log(m, "ok"), None, scb)
        et = time.time(); es = session["end_score"]
        collected = es - session["start_score"]
        append_history({
            "account": u,
            "start_time": datetime.fromtimestamp(session["start_time"]).strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.fromtimestamp(et).strftime("%Y-%m-%d %H:%M:%S"),
            "start_score": session["start_score"],
            "end_score": es, "collected": collected,
            "duration_seconds": int(et - session["start_time"]),
        })
        self.status[u] = "متوقف"
        self.log(f"[{u}] ⏹ انتهت - جمع: {collected} نقطة", "info")
    def start_one(self, username):
        data = load_data()
        acc = next((a for a in data.get("accounts", []) if a["username"] == username), None)
        if not acc:
            return False, "الحساب غير موجود"
        if username in self.threads:
            ev, th, st = self.threads[username]
            if th.is_alive():
                return False, f"{username} شغال بالفعل"
        ev = threading.Event()
        th = threading.Thread(target=self.run_account, args=(acc, ev), daemon=True)
        th.start()
        self.threads[username] = (ev, th, time.time())
        return True, f"تم تشغيل {username}"
    def stop_one(self, username):
        if username not in self.threads:
            return False, f"{username} مش شغال"
        ev, th, st = self.threads[username]
        ev.set()
        self.status[username] = "متوقف"
        self.log(f"[{username}] ⏹ إيقاف يدوي", "warn")
        try: del self.threads[username]
        except: pass
        return True, f"تم إيقاف {username}"
    def stop_all(self):
        for u in list(self.threads.keys()):
            self.stop_one(u)
        return True, "تم إيقاف الكل"
    def status_one(self, u):
        if u in self.threads:
            ev, th, st = self.threads[u]
            if th.is_alive():
                return "شغال", int(time.time() - st), st
        return self.status.get(u, "متوقف"), 0, 0

manager = Manager()

def auth_ok():
    return request.headers.get("X-Password") == ADMIN_PASSWORD

@app.route("/")
def home(): return "<h1>MOON API Running</h1>"

@app.route("/api/data")
def api_data():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = load_data()
    with manager.log_lock: logs = list(manager.logs[-300:])
    accounts = d.get("accounts", [])
    # ترتيب: الشغال الأول
    running_first = []
    stopped = []
    for a in accounts:
        st, elapsed, st_time = manager.status_one(a["username"])
        a["_status"] = st
        a["_elapsed"] = elapsed
        a["_start_time"] = st_time
        if st == "شغال":
            running_first.append(a)
        else:
            stopped.append(a)
    sorted_accs = running_first + stopped
    # معلومات الجلسة الحالية (أول حساب شغال)
    session_info = None
    if running_first:
        top = running_first[0]
        session_len = 600  # 10 دقايق
        elapsed = top["_elapsed"]
        remaining = max(0, session_len - (elapsed % session_len))
        session_info = {
            "account": top["username"],
            "elapsed": elapsed,
            "remaining": remaining,
            "session_length": session_len,
            "progress": int((elapsed % session_len) / session_len * 100),
        }
    return jsonify({
        "accounts": sorted_accs,
        "scores": manager.scores,
        "status": manager.status,
        "logs": logs,
        "session": session_info,
    })

@app.route("/api/start-one", methods=["POST"])
def api_start_one():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    u = (request.json or {}).get("username", "").strip()
    ok, msg = manager.start_one(u)
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/stop-one", methods=["POST"])
def api_stop_one():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    u = (request.json or {}).get("username", "").strip()
    ok, msg = manager.stop_one(u)
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/stop-all", methods=["POST"])
def api_stop_all():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    ok, msg = manager.stop_all()
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/start-all", methods=["POST"])
def api_start_all():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    data = load_data()
    for a in data.get("accounts", []):
        manager.start_one(a["username"])
    return jsonify({"ok": True, "msg": "تم تشغيل الكل"})

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
    data["accounts"].append({"username": u, "password": p, "proxy": ""})
    save_data(data)
    return jsonify({"ok": True, "msg": f"تم إضافة {u}"})

@app.route("/api/delete", methods=["POST"])
def api_delete():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    u = (d.get("username") or "").strip()
    manager.stop_one(u)
    data = load_data()
    data["accounts"] = [a for a in data["accounts"] if a["username"] != u]
    save_data(data)
    manager.scores.pop(u, None)
    manager.status.pop(u, None)
    return jsonify({"ok": True, "msg": f"تم حذف {u}"})

@app.route("/api/buy", methods=["POST"])
def api_buy():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    acc_name = (d.get("account") or "").strip()
    service = (d.get("service") or "").strip()
    target = (d.get("target") or "").strip()
    amount = int(d.get("amount", 0) or 0)
    extra = (d.get("extra") or "").strip()
    if not acc_name or not service or not target or amount <= 0:
        return jsonify({"ok": False, "msg": "أدخل كل البيانات"})
    data = load_data()
    acc = next((a for a in data.get("accounts", []) if a["username"] == acc_name), None)
    if not acc: return jsonify({"ok": False, "msg": "الحساب غير موجود"})
    t, c, user = B.login(acc_name, acc["password"])
    if not t: return jsonify({"ok": False, "msg": "فشل تسجيل الدخول"})
    B.attest(t, c, None, acc_name)
    cur = user.get("score", 0) or 0
    ok, result = B.create_order(t, c, service, target, amount, extra, None, acc_name)
    if ok:
        ns = B.fetch_score(t, c, None, acc_name)
        if ns is not None: manager.set_score(acc_name, ns)
        manager.log(f"[BUY] {acc_name}: {service} × {amount} → {target} | ✅", "ok")
        return jsonify({"ok": True, "msg": f"✅ تم الشراء! الرصيد: {ns if ns is not None else cur}", "order": result, "new_score": ns})
    manager.log(f"[BUY] {acc_name}: فشل - {result}", "err")
    return jsonify({"ok": False, "msg": f"❌ {result}"})

@app.route("/api/history")
def api_history():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    h = load_history()
    return jsonify({"history": list(reversed(h[-200:]))})

@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    save_history([])
    return jsonify({"ok": True, "msg": "تم المسح"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
