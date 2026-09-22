import requests, hmac, hashlib, time, uuid, json, random, re

# ثوابت
PASSWORD = "d02d5189"
DEVINFO = '{"d":"61393235613366373261636533656632","n":"494e46494e495820496e66696e6978205836383733","o":"16","t":"d","v":"2.2.9","s":"0,0"}'
KEY = bytes([b ^ 0x43 for b in [0x35,0x30,0x1c,0x2f,0x2c,0x2c,0x28,0x31,0x35,0x30,0x1c,0x2f,0x2c,0x2c,0x28,0x31]])
OP_IDS = {
    "LoginAccount": "3522613813036d73817b2715e67743f8d23d7a85ad08b7e12aa3b29a24a17c43",
    "AttestDevice": "bfaf5a72aeb9a337811da6a6d13e0b73680a18ffde0c59a23701e55b98ac2515",
    "FetchScore": "88d30eeca55c0538539ad8217dfefd52b2f47015200cdbb7cb6ea5a765381d69",
    "CreateOrder": "ad7a6397c3970b1e7601f69d24989bff330e256ee5e39321a8d1ad3fe3879b48",
    "GetUsers": "41454e2194d7c30f1c6e11c2c246bcc0377da65a8bf06276ca5ea9ec9ff538b6"
}

def _proxies(proxy):
    """يرجع dict البروكسي أو None"""
    if not proxy or not proxy.strip():
        return None
    p = proxy.strip()
    return {"http": p, "https": p}

def signature(ts, nonce, payload):
    return hmac.new(KEY, f"{ts}-{nonce}-{payload}".encode(), hashlib.sha256).hexdigest()

def graphql(query, op, auth=True, token=None, csrf=None, proxy=None):
    url = "https://api.tikspark.xyz/graphql"
    payload = json.dumps(query, separators=(',', ':'))
    ts = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())[:16]
    headers = {
        "X-APOLLO-OPERATION-NAME": op,
        "Accept": "multipart/mixed; deferSpec=20220824, application/json",
        "x-language": "ar",
        "x-app-name": "com.dev.vidspark",
        "x-device-info": DEVINFO,
        "x-app-sig": signature(ts, nonce, payload),
        "x-app-ts": ts,
        "x-app-nonce": nonce,
        "Content-Type": "application/json",
        "User-Agent": "okhttp/4.12.0"
    }
    if op in OP_IDS:
        headers["X-APOLLO-OPERATION-ID"] = OP_IDS[op]
    if auth:
        headers["token"] = token
        headers["x-csrf-token"] = csrf
    try:
        resp = requests.post(url, headers=headers, data=payload, timeout=25, proxies=_proxies(proxy))
        return resp, resp.json()
    except Exception as e:
        return None, {"error": str(e)}

def login(username, password=None, retries=3, proxy=None):
    """تسجيل دخول / إنشاء حساب تلقائي"""
    if password is None:
        password = PASSWORD
    for attempt in range(retries):
        q = {
            "operationName": "LoginAccount",
            "variables": {
                "data": {
                    "id": "", "uniqueId": username, "nickname": "",
                    "avatarMedium": "https://p16-common-sign.tiktokcdn.com/musically-maliva-obj/1594805258216454~tplv-tiktokx-cropcenter:720:720.webp",
                    "followerCount": 0, "followingCount": 0, "videoCount": 0,
                    "privateAccount": False, "diggCount": 0,
                    "authMethod": "local", "password": password
                }
            },
            "query": "mutation LoginAccount($data: TiktokInfo) { loginTiktok(data: $data) { accessToken refreshToken user { __typename ...UserFields } } } fragment UserFields on User { _id tiktokId nickname email score diggCount followerCount followingCount friendCount isMembershipExpired heartCount username avatar banned vip vipExpiresAt authMethod isSubscription allowd referralCode referralCount referredBy }"
        }
        resp, data = graphql(q, "LoginAccount", auth=False, proxy=proxy)
        if resp and "errors" not in data:
            token = data['data']['loginTiktok']['accessToken']
            csrf = resp.headers.get("x-csrf-token", "")
            user = data['data']['loginTiktok']['user']
            return token, csrf, user
        else:
            err = data.get("errors", [{"message": "غير معروف"}])[0]["message"]
            if "Rate limit exceeded" in err:
                wait = 2
                try:
                    match = re.search(r'wait (\d+) seconds?', err)
                    if match:
                        wait = int(match.group(1)) + 1
                except:
                    pass
                time.sleep(wait)
                continue
            else:
                return None, None, {"error": err}
    return None, None, {"error": "فشل بعد محاولات"}

def attest(token, csrf, proxy=None):
    q = {
        "operationName": "AttestDevice",
        "variables": {
            "integrityToken": "CpsCARCnMGtvLkiuhYFGDW3rUoE73im9X9NmXA1cHOZZOzgRp5FtsmIrZBoNek0K7XIoZiR9XKg1bpApXNem9MbcR4UiIxz1n4Wgv_LA4hSSAbHzpaAfXcnLyKgwnOXGRUieQ4OOpMTMDRxD6O7kd3jjAfcbcHFt3bdgyw7CJYpxz4oq3lIti658lCdnt1NvJzUwfYSp6eWKcvKV5lScaq-nkplRn7hz38A8kLhYNx6w-7rne41hWCR6BQISVfBewaqeh7RL-9iEDrzK-ECbdEwBnpO-LfAqCJKn1bf5VkVxuPAz5qPvB8cNE7ZBMAyMnDHdjNDwpnZMA2EXsgRsyT6Fm_l3MNugWDdWbRgww6sAw6KrRzeBDETsXTh1ZBpqAWerZWp6AIjaDa-b0NFbOS69HsGnfpE7hljmu7OTsd4tM6nM50qiSc4QGuD4aM-joJFkYKIsWf_grquB66bYnYa2mCWcPl1hIEApHMXbCLiO7nwX-8LXEwCDvVNT4f8mjgtI1__D_C-f4g",
            "requestHash": "gPyB7FF-XeZc2kwi2L-KZXs21Z8oPErvHD9gn572PyM"
        },
        "query": "mutation AttestDevice($integrityToken: String!, $requestHash: String!) { attestDevice(integrityToken: $integrityToken, requestHash: $requestHash) { ok verified } }"
    }
    _, data = graphql(q, "AttestDevice", True, token, csrf, proxy=proxy)
    return "errors" not in data

def fetch_user_data(token, csrf, proxy=None):
    q = {
        "operationName": "GetUsers",
        "variables": {},
        "query": "query GetUsers { me { __typename ...UserFields } }  fragment UserFields on User { _id tiktokId nickname email score diggCount followerCount followingCount friendCount isMembershipExpired heartCount username avatar banned vip vipExpiresAt authMethod isSubscription allowd referralCode referralCount referredBy }"
    }
    _, data = graphql(q, "GetUsers", True, token, csrf, proxy=proxy)
    if "errors" not in data:
        me = data.get("data", {}).get("me", {})
        return me.get("avatar", ""), me.get("followerCount", 0) or 0
    return "", 0

def fetch_score(token, csrf, proxy=None):
    q = {"operationName": "FetchScore", "variables": {}, "query": "query FetchScore { fetchScore }"}
    _, data = graphql(q, "FetchScore", True, token, csrf, proxy=proxy)
    if "errors" not in data:
        return data.get("data", {}).get("fetchScore")
    return None

def farmer(username, token, csrf, stop_event=None, logger=None, proxy=None, score_callback=None):
    if logger is None:
        logger = print
    logger(f"[~] {username}: بدء التجميع" + (f" (proxy)" if proxy else ""))
    s = fetch_score(token, csrf, proxy=proxy)
    if s is not None and score_callback:
        score_callback(s)
    while True:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            q = {"operationName": "GetOrders", "variables": {}, "query": "query GetOrders { getOrders { _id status } }"}
            _, data = graphql(q, "GetOrders", True, token, csrf, proxy=proxy)
            orders = data.get("data", {}).get("getOrders", [])
            pending = [o["_id"] for o in orders if o.get("status") == "pending"]
            if not pending:
                time.sleep(10)
                continue
            for task in pending:
                if stop_event is not None and stop_event.is_set():
                    break
                rnd = random.randint(3000, 4500)
                q = {
                    "operationName": "ActionOrder",
                    "variables": {
                        "orderId": task,
                        "validationData": {
                            "attempts": 1,
                            "initialNumber": float(rnd),
                            "timeSpent": float(random.randint(4000, 7000)),
                            "actualCount": rnd + 1,
                            "source": "CLIENT_CRONET"
                        }
                    },
                    "query": "mutation ActionOrder($orderId: ID!, $validationData: ValidationDataInput!) { actionOrder(orderId: $orderId, validationData: $validationData) { score taskProgress { count startTime taskProgressLimit } } }"
                }
                _, result = graphql(q, "ActionOrder", True, token, csrf, proxy=proxy)
                if "errors" not in result:
                    score = fetch_score(token, csrf, proxy=proxy)
                    if score is not None:
                        logger(f"[{username}] ✓ الرصيد: {score}")
                        if score_callback:
                            score_callback(score)
                    else:
                        logger(f"[{username}] ✓ تمت المهمة")
                else:
                    err = result.get("errors", [{}])[0].get("message", "")[:60]
                    if "Rate limit" in err or "Too many" in err:
                        logger(f"[{username}] ⏳ Rate limit")
                        time.sleep(5)
                    elif "TASK_ALREADY_SUBMITTED" in err or "TASK_UNAVAILABLE" in err or "TASK_TOO_FAST" in err:
                        pass
                    elif "INVALID_VALIDATION" in err:
                        pass
                    else:
                        logger(f"[{username}] {err}")
                time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            logger(f"[{username}] خطأ: {str(e)[:80]}")
            time.sleep(5)
    if logger:
        logger(f"[{username}] ⏹ توقف")

def create_order(token, csrf, service_type, target, amount, avatar="", extra=None, proxy=None):
    if not avatar:
        avatar = "https://p16-common-sign.tiktokcdn.com/musically-maliva-obj/1594805258216454~tplv-tiktokx-cropcenter:720:720.webp"
    order_input = {"type": service_type, "amount": int(amount), "avatar": avatar}
    if service_type == "followers":
        order_input["tiktokerUsername"] = target
    else:
        order_input["videoLink"] = target
    q = {
        "operationName": "CreateOrder",
        "variables": {"orderInput": order_input},
        "query": "mutation CreateOrder($orderInput: OrderInput!) { createOrder(orderInput: $orderInput) { _id type amount status score createdAt } }"
    }
    _, data = graphql(q, "CreateOrder", True, token, csrf, proxy=proxy)
    if "errors" not in data:
        return True, data.get("data", {}).get("createOrder", {})
    return False, data.get("errors", [{}])[0].get("message", "خطأ غير معروف")

def fetch_my_orders(token, csrf, proxy=None):
    """جلب أوامر المستخدم (myOrders)"""
    q = {"operationName": None, "variables": {},
         "query": "query { myOrders { _id type amount status fulfilled createdAt videoLink tiktokerUsername } }"}
    _, data = graphql(q, None, True, token, csrf, proxy=proxy)
    if "errors" not in data:
        return data.get("data", {}).get("myOrders", []) or []
    return []
