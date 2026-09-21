import os, json, threading, time, hashlib, uuid
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
import bot as B

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type", "X-Phone", "X-Password"],
     methods=["GET", "POST", "OPTIONS"])
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Ahmed")

USERS_FILE = "users.json"
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
lock = threading.Lock()

# ============ USERS ============
def load_users():
    with lock:
        if not os.path.exists(USERS_FILE): return {}
        try:
            with open(USERS_FILE, encoding='utf-8') as f: return json.load(f)
        except: return {}

def save_users(u):
    with lock:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(u, f, ensure_ascii=False, indent=2)

def hash_pwd(p): return hashlib.sha256(p.encode()).hexdigest()

def ufile(phone, kind): return os.path.join(DATA_DIR, f"{phone}_{kind}.json")

def uload(phone, kind, default):
    p = ufile(phone, kind)
    with lock:
        if not os.path.exists(p): return default
        try:
            with open(p, encoding='utf-8') as f: return json.load(f)
        except: return default

def usave(phone, kind, d):
    p = ufile(phone, kind)
    with lock:
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

def get_phone():
    return (request.headers.get("X-Phone") or "").strip()

def auth_ok():
    return get_phone() in load_users()

# ============ MANAGERS (per user) ============
class UserManager:
    def __init__(self, phone):
        self.phone = phone
        self.logs = []
        self.log_lock = threading.Lock()
        self.scores = {}
        self.status = {}
        self.threads = {}
    def log(self, msg, kind="info"):
        with self.log_lock:
            self.logs.append({"t": datetime.now().strftime("%H:%M:%S"), "m": msg, "k": kind})
            if len(self.logs) > 1500: self.logs.pop(0)
    def set_score(self, u, s): self.scores[u] = s
    def accs(self): return uload(self.phone, "accounts", {"accounts": []}).get("accounts", [])
    def run_account(self, acc, stop_ev):
        u = acc["username"]
        self.status[u] = "جاري الدخول"
        self.log(f"[{u}] تسجيل الدخول...", "info")
        t, c, user = B.login(u, acc.get("password", ""))
        if not t:
            self.status[u] = "فشل الدخول"
            self.log(f"[{u}] ❌ فشل", "err"); return
        B.attest(t, c, None, u)
        start_score = user.get("score", 0) or 0
        self.set_score(u, start_score)
        self.status[u] = "شغال"
        self.log(f"[{u}] ✅ متصل ({start_score} نقطة)", "ok")
        session = {"t0": time.time(), "s0": start_score, "s1": start_score}
        def scb(s): self.set_score(u, s); session["s1"] = s
        B.farmer(u, t, c, stop_ev, lambda m: self.log(m, "ok"), None, scb)
        et = time.time(); es = session["s1"]
        collected = es - session["s0"]
        h = uload(self.phone, "history", [])
        h.append({
            "account": u,
            "start_time": datetime.fromtimestamp(session["t0"]).strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.fromtimestamp(et).strftime("%Y-%m-%d %H:%M:%S"),
            "start_score": session["s0"], "end_score": es,
            "collected": collected, "duration_seconds": int(et - session["t0"]),
        })
        if len(h) > 1000: h = h[-1000:]
        usave(self.phone, "history", h)
        self.status[u] = "متوقف"
        self.log(f"[{u}] ⏹ انتهى ({collected:+d})", "info")
    def start_one(self, username):
        acc = next((a for a in self.accs() if a["username"] == username), None)
        if not acc: return False, "الحساب غير موجود"
        if username in self.threads and self.threads[username][1].is_alive():
            return False, "شغال بالفعل"
        ev = threading.Event()
        th = threading.Thread(target=self.run_account, args=(acc, ev), daemon=True)
        th.start()
        self.threads[username] = (ev, th, time.time())
        return True, f"تم تشغيل {username}"
    def stop_one(self, username):
        if username not in self.threads: return False, "مش شغال"
        ev, th, st = self.threads[username]
        ev.set(); self.status[username] = "متوقف"
        self.log(f"[{username}] ⏹ إيقاف يدوي", "warn")
        try: del self.threads[username]
        except: pass
        return True, f"تم إيقاف {username}"
    def stop_all(self):
        for u in list(self.threads.keys()): self.stop_one(u)
        return True, "تم إيقاف الكل"
    def status_one(self, u):
        if u in self.threads:
            ev, th, st = self.threads[u]
            if th.is_alive(): return "شغال", int(time.time() - st), st
        return self.status.get(u, "متوقف"), 0, 0

managers = {}
def mgr():
    p = get_phone()
    if p not in managers: managers[p] = UserManager(p)
    return managers[p]

# ============ AUTH ROUTES ============
@app.route("/api/register", methods=["POST"])
def api_register():
    d = request.json or {}
    phone = (d.get("phone") or "").strip()
    pwd = (d.get("password") or "").strip()
    dev = (d.get("device_id") or "").strip()
    if len(phone) < 8 or len(pwd) < 4:
        return jsonify({"ok": False, "msg": "رقم أو كلمة مرور قصيرة"})
    users = load_users()
    if phone in users:
        return jsonify({"ok": False, "msg": "الرقم مسجل بالفعل"})
    users[phone] = {
        "password": hash_pwd(pwd),
        "device_id": dev,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_users(users)
    # إنشاء ملفات فارغة
    usave(phone, "accounts", {"accounts": []})
    usave(phone, "history", [])
    usave(phone, "transactions", [])
    return jsonify({"ok": True, "msg": "✅ تم إنشاء الحساب"})

@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.json or {}
    phone = (d.get("phone") or "").strip()
    pwd = (d.get("password") or "").strip()
    dev = (d.get("device_id") or "").strip()
    users = load_users()
    if phone not in users:
        return jsonify({"ok": False, "msg": "الرقم غير مسجل"})
    if users[phone]["password"] != hash_pwd(pwd):
        return jsonify({"ok": False, "msg": "كلمة المرور غلط"})
    # تحديث device_id لو جديد
    if dev and not users[phone].get("device_id"):
        users[phone]["device_id"] = dev
        save_users(users)
    return jsonify({"ok": True, "msg": "مرحباً"})

@app.route("/api/forgot/check", methods=["POST"])
def api_forgot_check():
    d = request.json or {}
    phone = (d.get("phone") or "").strip()
    dev = (d.get("device_id") or "").strip()
    users = load_users()
    if phone not in users:
        return jsonify({"ok": False, "msg": "الرقم غير مسجل"})
    saved_dev = users[phone].get("device_id", "")
    if not saved_dev:
        return jsonify({"ok": True, "msg": "لا يوجد جهاز مرتبط"})
    if saved_dev == dev:
        return jsonify({"ok": True, "msg": "الجهاز متطابق"})
    return jsonify({"ok": False, "msg": "❌ هذا ليس الجهاز المسجل"})

@app.route("/api/forgot/reset", methods=["POST"])
def api_forgot_reset():
    d = request.json or {}
    phone = (d.get("phone") or "").strip()
    new_pwd = (d.get("new_password") or "").strip()
    dev = (d.get("device_id") or "").strip()
    if len(new_pwd) < 4:
        return jsonify({"ok": False, "msg": "كلمة قصيرة"})
    users = load_users()
    if phone not in users:
        return jsonify({"ok": False, "msg": "غير مسجل"})
    if users[phone].get("device_id") != dev:
        return jsonify({"ok": False, "msg": "الجهاز غير متطابق"})
    users[phone]["password"] = hash_pwd(new_pwd)
    save_users(users)
    return jsonify({"ok": True, "msg": "✅ تم تغيير كلمة المرور"})

# ============ MAIN API ============
@app.route("/")
def home(): return "<h1>MOON API Running</h1>"

@app.route("/api/data")
def api_data():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    m = mgr()
    d = uload(m.phone, "accounts", {"accounts": []})
    with m.log_lock: logs = list(m.logs[-250:])
    rf, st = [], []
    for a in d.get("accounts", []):
        s, el, stt = m.status_one(a["username"])
        a["_status"] = s; a["_elapsed"] = el
        (rf if s == "شغال" else st).append(a)
    return jsonify({
        "accounts": rf + st,
        "scores": m.scores, "status": m.status, "logs": logs,
    })

@app.route("/api/start-one", methods=["POST"])
def api_start_one():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    u = (request.json or {}).get("username", "").strip()
    ok, msg = mgr().start_one(u)
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/stop-one", methods=["POST"])
def api_stop_one():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    u = (request.json or {}).get("username", "").strip()
    ok, msg = mgr().stop_one(u)
    return jsonify({"ok": ok, "msg": msg})

@app.route("/api/stop-all", methods=["POST"])
def api_stop_all():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    return jsonify({"ok": True, "msg": mgr().stop_all()[1]})

@app.route("/api/start-all", methods=["POST"])
def api_start_all():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    m = mgr()
    for a in m.accs(): m.start_one(a["username"])
    return jsonify({"ok": True, "msg": "تم"})

@app.route("/api/clear", methods=["POST"])
def api_clear():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    m = mgr()
    with m.log_lock: m.logs.clear()
    return jsonify({"ok": True, "msg": "تم"})

@app.route("/api/add", methods=["POST"])
def api_add():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    u = (d.get("username") or "").strip()
    p = (d.get("password") or "").strip()
    if not u or not p: return jsonify({"ok": False, "msg": "أدخل الاسم وكلمة المرور"})
    m = mgr()
    data = uload(m.phone, "accounts", {"accounts": []})
    if any(a["username"] == u for a in data["accounts"]):
        return jsonify({"ok": False, "msg": "موجود"})
    data["accounts"].append({"username": u, "password": p})
    usave(m.phone, "accounts", data)
    return jsonify({"ok": True, "msg": f"تم إضافة {u}"})

@app.route("/api/delete", methods=["POST"])
def api_delete():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    u = (d.get("username") or "").strip()
    m = mgr()
    m.stop_one(u)
    data = uload(m.phone, "accounts", {"accounts": []})
    data["accounts"] = [a for a in data["accounts"] if a["username"] != u]
    usave(m.phone, "accounts", data)
    m.scores.pop(u, None); m.status.pop(u, None)
    return jsonify({"ok": True, "msg": f"تم حذف {u}"})

@app.route("/api/history")
def api_history():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    h = uload(get_phone(), "history", [])
    return jsonify({"history": list(reversed(h[-200:]))})

@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    usave(get_phone(), "history", [])
    return jsonify({"ok": True})

@app.route("/api/transactions")
def api_tx():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    t = uload(get_phone(), "transactions", [])
    return jsonify({"transactions": list(reversed(t[-200:]))})

@app.route("/api/transactions/clear", methods=["POST"])
def api_tx_clear():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    usave(get_phone(), "transactions", [])
    return jsonify({"ok": True})

@app.route("/api/buy", methods=["POST"])
def api_buy():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    acc_name = (d.get("account") or "").strip()
    service = (d.get("service") or "").strip()
    target = (d.get("target") or "").strip()
    amount = int(d.get("amount", 0) or 0)
    if not acc_name or not service or not target or amount <= 0:
        return jsonify({"ok": False, "msg": "أدخل كل البيانات"})
    m = mgr()
    acc = next((a for a in m.accs() if a["username"] == acc_name), None)
    if not acc: return jsonify({"ok": False, "msg": "الحساب غير موجود"})
    t, c, user = B.login(acc_name, acc["password"])
    if not t: return jsonify({"ok": False, "msg": "فشل الدخول"})
    B.attest(t, c, None, acc_name)
    before = user.get("score", 0) or 0
    ok, result = B.create_order(t, c, service, target, amount, None, None, acc_name)
    entry = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "account": acc_name, "service": service, "target": target, "amount": amount,
        "before": before, "after": before, "cost": 0,
        "ok": bool(ok), "msg": result if not ok else "تم"
    }
    tx = uload(m.phone, "transactions", [])
    if ok:
        ns = B.fetch_score(t, c, None, acc_name)
        if ns is not None:
            m.set_score(acc_name, ns)
            entry["after"] = ns
            entry["cost"] = before - ns
        tx.append(entry)
        if len(tx) > 1000: tx = tx[-1000:]
        usave(m.phone, "transactions", tx)
        return jsonify({"ok": True, "msg": "✅ تم الشراء", "tx": entry})
    tx.append(entry)
    if len(tx) > 1000: tx = tx[-1000:]
    usave(m.phone, "transactions", tx)
    return jsonify({"ok": False, "msg": f"❌ {result}", "tx": entry})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
