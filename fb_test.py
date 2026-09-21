import requests
FB = "https://otp-5acda-default-rtdb.firebaseio.com"
print("=== Firebase Test ===")
try:
    r = requests.get(FB + "/.json", timeout=15)
    print("GET:", r.status_code, r.text[:200])
except Exception as e:
    print("GET failed:", str(e)[:200])
try:
    r = requests.put(FB + "/test.json", json={"ok": True}, timeout=15)
    print("PUT:", r.status_code, r.text[:200])
except Exception as e:
    print("PUT failed:", str(e)[:200])
try:
    r = requests.get(FB + "/test.json", timeout=15)
    print("GET2:", r.status_code, r.text[:200])
except Exception as e:
    print("GET2 failed:", str(e)[:200])
try:
    requests.delete(FB + "/test.json", timeout=15)
    print("DELETE: done")
except: pass
print("=== END ===")
