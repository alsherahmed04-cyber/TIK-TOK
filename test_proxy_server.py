import requests, urllib3
urllib3.disable_warnings()
p = {"http": "socks4://150.109.247.86:8443", "https": "socks4://150.109.247.86:8443"}
try:
    r = requests.get("http://ip-api.com/json", proxies=p, timeout=15, verify=False)
    print(f"✅ اتصال: {r.json().get('query')} - {r.json().get('country')}")
except Exception as e:
    print(f"❌ {str(e)[:100]}")
