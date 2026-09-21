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
lock = threading.Lock()

def load_history():
    with lock:
        if not os.path.exists(HIST_FILE):
            return []
        try:
            with open(HIST_FILE, encoding='utf-8') as f:
                return json.load(f)
        except:
            return []

def save_history(h):
    with lock:
        with open(HIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(h, f, ensure_ascii=False, indent=2)

def append_history(entry):
    h = load_history()
    h.append(entry)
    if len(h) > 1000:
        h = h[-1000:]
    save_history(h)

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

class Manager:
    def __init__(self):
        self.running = False
        self.stop_event = threading.Event()
        self.logs = []
        self.log_lock = threading.Lock()
        self.scores = {}
        self.status = {}
        self.rotate_idx = 0
        self.current_stop = None
        self.current_start = 0
        self.current_account = None
        self.scheduler_thread = None

    def log(self, msg):
        with self.log_lock:
            self.logs.append(msg)
            if len(self.logs) > 2000:
                self.logs.pop(0)

    def set_score(self, user, score):
        self.scores[user] = score

    def run_account(self, acc, stop_ev):
        u = acc["username"]
        p = acc.get("password", "")
        self.status[u] = "جاري الدخول"
        t, c, user = B.login(u, p)
        if not t:
            self.status[u] = "فشل الدخول"
            self.log(f"[X] {u}: فشل الدخول")
            return
        B.attest(t, c, None, u)
        start_score = user.get("score", 0) or 0
        self.set_score(u, start_score)
        self.status[u] = "شغال"
        self.log(f"[OK] {u} متصل (رصيد البداية: {start_score})")
        session = {"start_time": time.time(), "start_score": start_score, "end_score": start_score}
        def score_cb(s):
            self.set_score(u, s)
            session["end_score"] = s
        B.farmer(u, t, c, stop_ev, self.log, None, score_cb)
        end_time = time.time()
        end_score = session.get("end_score", start_score)
        collected = end_score - start_score
        entry = {
            "account": u,
            "start_time": datetime.fromtimestamp(session["start_time"]).strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S"),
            "start_score": start_score,
            "end_score": end_score,
            "collected": collected,
            "duration_seconds": int(end_time - session["start_time"]),
        }
        append_history(entry)
        self.status[u] = "متوقف"
        self.log(f"[{u}] انتهت - جمع: {collected} نقطة (من {start_score} لـ {end_score})")

    def start_current(self):
        data = load_data()
        accounts = data.get("accounts", [])
        if not accounts:
            self.log("[SYSTEM] لا توجد حسابات")
            return
        self.rotate_idx = self.rotate_idx % len(accounts)
        acc = accounts[self.rotate_idx]
        self.current_stop = threading.Event()
        self.current_start = time.time()
        self.current_account = acc["username"]
        self.log(f"[SYSTEM] ▶ الحساب الحالي: {acc['username']} ({self.rotate_idx+1}/{len(accounts)})")
        threading.Thread(target=self.run_account, args=(acc, self.current_stop), daemon=True).start()

    def scheduler(self):
        while self.running and not self.stop_event.is_set():
            time.sleep(2)
            if not self.running:
                break
            data = load_data()
            rotation = int(data.get("rotation_seconds", 600))
            elapsed = time.time() - self.current_start
            if elapsed >= rotation:
                if self.current_stop:
                    self.current_stop.set()
                time.sleep(3)
                if self.stop_event.is_set():
                    break
                self.rotate_idx += 1
                self.start_current()

    def start(self):
        if self.running:
            return False, "البوت شغال بالفعل"
        data = load_data()
        if not data.get("accounts"):
            return False, "لا توجد حسابات"
        self.stop_event.clear()
        self.running = True
        self.rotate_idx = 0
        self.start_current()
        self.scheduler_thread = threading.Thread(target=self.scheduler, daemon=True)
        self.scheduler_thread.start()
        return True, "تم التشغيل"

    def stop(self):
        if not self.running:
            return False, "البوت مش شغال"
        self.stop_event.set()
        if self.current_stop:
            self.current_stop.set()
        self.running = False
        self.current_account = None
        self.log("[SYSTEM] ⏹ إيقاف")
        return True, "تم الإيقاف"

manager = Manager()

def auth_ok():
    return request.headers.get("X-Password") == ADMIN_PASSWORD

@app.route("/")
def home():
    return "<h1>MOON API Running</h1>"

@app.route("/api/data")
def api_data():
    if not auth_ok():
        return jsonify({"error": "unauthorized"}), 401
    d = load_data()
    with manager.log_lock:
        logs = list(manager.logs[-200:])
    accounts = d.get("accounts", [])
    rotation = int(d.get("rotation_seconds", 600))
    current_acc = None
    seconds_remaining = 0
    progress = 0
    if manager.running and accounts:
        idx = manager.rotate_idx % len(accounts)
        current_acc = accounts[idx]["username"]
        elapsed = time.time() - manager.current_start
        seconds_remaining = max(0, int(rotation - elapsed))
        progress = min(100, int((elapsed / rotation) * 100))
    return jsonify({
        "accounts": accounts,
        "running": manager.running,
        "scores": manager.scores,
        "status": manager.status,
        "logs": logs,
        "rotation_seconds": rotation,
        "current_account": current_acc,
        "seconds_remaining": seconds_remaining,
        "progress": progress,
        "rotate_idx": manager.rotate_idx
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
    data["accounts"].append({"username": u, "password": p, "proxy": ""})
    save_data(data)
    total = len(data["accounts"])
    if manager.running:
        manager.log(f"[SYSTEM] ➕ تم إضافة {u} (سيُدرج في الدورة - الحساب #{total})")
    return jsonify({"ok": True, "msg": f"تم إضافة {u} (سيُدرج تلقائياً في الدورة)"})

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

@app.route("/api/rotation", methods=["POST"])
def api_rotation():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    d = request.json or {}
    secs = int(d.get("seconds", 600))
    if secs < 30: secs = 30
    data = load_data()
    data["rotation_seconds"] = secs
    save_data(data)
    return jsonify({"ok": True, "msg": f"مدة الدوران: {secs} ثانية"})

@app.route("/api/history")
def api_history():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    h = load_history()
    return jsonify({"history": list(reversed(h[-200:]))})

@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    if not auth_ok(): return jsonify({"error": "unauthorized"}), 401
    save_history([])
    return jsonify({"ok": True, "msg": "تم مسح السجل التاريخي"})


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
        return jsonify({"ok": False, "msg": "أدخل كل البيانات المطلوبة"})
    data = load_data()
    acc = next((a for a in data.get("accounts", []) if a["username"] == acc_name), None)
    if not acc:
        return jsonify({"ok": False, "msg": "الحساب غير موجود"})
    # تسجيل دخول
    t, c, user = B.login(acc_name, acc["password"])
    if not t:
        return jsonify({"ok": False, "msg": "فشل تسجيل الدخول للحساب"})
    B.attest(t, c, None, acc_name)
    current_score = user.get("score", 0) or 0
    # محاولة الشراء
    ok, result = B.create_order(t, c, service, target, amount, extra, None, acc_name)
    if ok:
        # جلب الرصيد الجديد
        new_score = B.fetch_score(t, c, None, acc_name)
        if new_score is not None:
            manager.set_score(acc_name, new_score)
        manager.log(f"[BUY] {acc_name}: {service} × {amount} → {target} | ✅ نجح")
        return jsonify({"ok": True, "msg": f"✅ تم الشراء! الرصيد الجديد: {new_score if new_score is not None else current_score}", "order": result, "new_score": new_score})
    else:
        manager.log(f"[BUY] {acc_name}: {service} × {amount} → {target} | ❌ {result}")
        return jsonify({"ok": False, "msg": f"❌ فشل: {result}"})

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
