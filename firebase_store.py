# -*- coding: utf-8 -*-
"""طبقة تخزين Firebase Realtime Database"""
import requests, os, threading, json

FB_URL = os.getenv("FB_URL", "https://otp-5acda-default-rtdb.firebaseio.com").rstrip("/")
_lock = threading.Lock()

def fb_get(path):
    try:
        r = requests.get(f"{FB_URL}/{path}.json", timeout=15)
        if r.status_code == 200:
            return r.json()
    except: pass
    return None

def fb_put(path, data):
    try:
        r = requests.put(f"{FB_URL}/{path}.json", json=data, timeout=15)
        return r.status_code == 200
    except: return False

def fb_delete(path):
    try:
        r = requests.delete(f"{FB_URL}/{path}.json", timeout=15)
        return r.status_code == 200
    except: return False

# ============ USERS ============
def load_users():
    with _lock:
        return fb_get("moon/users") or {}

def save_users(users):
    with _lock:
        return fb_put("moon/users", users)

def save_user(phone, data):
    with _lock:
        users = fb_get("moon/users") or {}
        users[phone] = data
        return fb_put("moon/users", users)

def delete_user(phone):
    with _lock:
        users = fb_get("moon/users") or {}
        users.pop(phone, None)
        return fb_put("moon/users", users)

# ============ ACCOUNTS ============
def load_accounts(phone):
    with _lock:
        d = fb_get(f"moon/accounts/{phone}")
        if not d or not isinstance(d, dict):
            return {"accounts": []}
        if "accounts" not in d:
            d["accounts"] = []
        return d

def save_accounts(phone, data):
    with _lock:
        return fb_put(f"moon/accounts/{phone}", data)

# ============ HISTORY ============
def load_history(phone):
    with _lock:
        d = fb_get(f"moon/history/{phone}")
        if not d: return []
        if isinstance(d, list): return [x for x in d if x]
        if isinstance(d, dict): return [v for k,v in sorted(d.items()) if v]
        return []

def save_history(phone, data):
    with _lock:
        return fb_put(f"moon/history/{phone}", data)

def append_history(phone, entry):
    with _lock:
        h = fb_get(f"moon/history/{phone}")
        if not h: h = []
        elif isinstance(h, dict): h = [v for k,v in sorted(h.items()) if v]
        h.append(entry)
        if len(h) > 500: h = h[-500:]
        return fb_put(f"moon/history/{phone}", h)

# ============ TRANSACTIONS ============
def load_tx(phone):
    with _lock:
        d = fb_get(f"moon/transactions/{phone}")
        if not d: return []
        if isinstance(d, list): return [x for x in d if x]
        if isinstance(d, dict): return [v for k,v in sorted(d.items()) if v]
        return []

def save_tx(phone, data):
    with _lock:
        return fb_put(f"moon/transactions/{phone}", data)

def append_tx(phone, entry):
    with _lock:
        t = fb_get(f"moon/transactions/{phone}")
        if not t: t = []
        elif isinstance(t, dict): t = [v for k,v in sorted(t.items()) if v]
        t.append(entry)
        if len(t) > 500: t = t[-500:]
        return fb_put(f"moon/transactions/{phone}", t)
