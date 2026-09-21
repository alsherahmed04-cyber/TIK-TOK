import requests, hmac, hashlib, time, uuid, json, random, re

import hashlib as _hl

def _proxies(proxy):
    if not proxy: return None
    return {"http": proxy, "https": proxy}

def signature(ts, nonce, payload):
    return hmac.new(KEY, f"{ts}-{nonce}-{payload}".encode(), hashlib.sha256).hexdigest()

def graphql(query, op, auth=True, token=None, csrf=None, proxy=None, username=None):
    payload = json.dumps(query, separators=(',', ':'))
    ts = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())[:16]
    headers = {
        "X-APOLLO-OPERATION-NAME": op,
        "Accept": "multipart/mixed; deferSpec=20220824, application/json",
        "x-language": "ar", "x-app-name": "com.dev.vidspark",
        "x-device-info": DEVINFO,
        "x-app-sig": signature(ts, nonce, payload),
        "x-app-ts": ts, "x-app-nonce": nonce,
        "Content-Type": "application/json", "User-Agent": "okhttp/4.12.0"
    }
    if op in OP_IDS: headers["X-APOLLO-OPERATION-ID"] = OP_IDS[op]
    if auth:
        headers["token"] = token
        headers["x-csrf-token"] = csrf
    try:
        r = requests.post(URL, headers=headers, data=payload, timeout=20, proxies=_proxies(proxy))
        return r, r.json()
    except Exception as e:
        return None, {"error": str(e)}

def login(username, password, proxy=None, retries=5):
    q = {"operationName": "LoginAccount",
        "variables": {"data": {"id": "", "uniqueId": username, "nickname": "",
            "avatarMedium": "", "followerCount": 0, "followingCount": 0, "videoCount": 0,
            "privateAccount": False, "diggCount": 0, "authMethod": "local", "password": password}},
        "query": "mutation LoginAccount($data: TiktokInfo) { loginTiktok(data: $data) { accessToken refreshToken user { __typename ...UserFields } } } fragment UserFields on User { _id tiktokId nickname email score diggCount followerCount followingCount friendCount isMembershipExpired heartCount username avatar banned vip vipExpiresAt authMethod isSubscription allowd referralCode referralCount referredBy }"}
    for attempt in range(retries):
        resp, data = graphql(q, "LoginAccount", auth=False, proxy=proxy)
        if resp and "errors" not in data:
            t = data['data']['loginTiktok']['accessToken']
            c = resp.headers.get("x-csrf-token", "")
            u = data['data']['loginTiktok']['user']
            return t, c, u
        err = data.get("errors", [{"message": "غير معروف"}])[0]["message"]
        if "Rate limit exceeded" in err:
            wait = 5 + attempt * 3
            try:
                m = re.search(r'wait (\d+) seconds?', err)
                if m: wait = int(m.group(1)) + 2
            except: pass
            time.sleep(wait)
            continue
        return None, None, None
    return None, None, None

def attest(token, csrf, proxy=None, username=None):
    q = {"operationName": "AttestDevice",
        "variables": {"integrityToken": "CpsCARCnMGtvLkiuhYFGDW3rUoE73im9X9NmXA1cHOZZOzgRp5FtsmIrZBoNek0K7XIoZiR9XKg1bpApXNem9MbcR4UiIxz1n4Wgv_LA4hSSAbHzpaAfXcnLyKgwnOXGRUieQ4OOpMTMDRxD6O7kd3jjAfcbcHFt3bdgyw7CJYpxz4oq3lIti658lCdnt1NvJzUwfYSp6eWKcvKV5lScaq-nkplRn7hz38A8kLhYNx6w-7rne41hWCR6BQISVfBewaqeh7RL-9iEDrzK-ECbdEwBnpO-LfAqCJKn1bf5VkVxuPAz5qPvB8cNE7ZBMAyMnDHdjNDwpnZMA2EXsgRsyT6Fm_l3MNugWDdWbRgww6sAw6KrRzeBDETsXTh1ZBpqAWerZWp6AIjaDa-b0NFbOS69HsGnfpE7hljmu7OTsd4tM6nM50qiSc4QGuD4aM-joJFkYKIsWf_grquB66bYnYa2mCWcPl1hIEApHMXbCLiO7nwX-8LXEwCDvVNT4f8mjgtI1__D_C-f4g",
                    "requestHash": "gPyB7FF-XeZc2kwi2L-KZXs21Z8oPErvHD9gn572PyM"},
        "query": "mutation AttestDevice($integrityToken: String!, $requestHash: String!) { attestDevice(integrityToken: $integrityToken, requestHash: $requestHash) { ok verified } }"}
    _, data = graphql(q, "AttestDevice", True, token, csrf, proxy)
    return "errors" not in data

def fetch_score(token, csrf, proxy=None, username=None):
    q = {"operationName": "FetchScore", "variables": {}, "query": "query FetchScore { fetchScore }"}
    _, data = graphql(q, "FetchScore", True, token, csrf, proxy)
    return data.get("data", {}).get("fetchScore") if "errors" not in data else None

def create_order(token, csrf, service_type, target, amount, avatar="", extra=None, proxy=None, username=None):
    """إنشاء طلب شراء خدمة (الصيغة الصحيحة: orderInput كـ object)"""
    if not avatar:
        avatar = "https://p16-common-sign.tiktokcdn.com/musically-maliva-obj/1594805258216454~tplv-tiktokx-cropcenter:720:720.webp"
    order_input = {
        "type": service_type,
        "amount": int(amount),
        "avatar": avatar
    }
    if service_type == "followers":
        order_input["tiktokerUsername"] = target
    else:
        order_input["videoLink"] = target
    q = {
        "operationName": "CreateOrder",
        "variables": {"orderInput": order_input},
        "query": "mutation CreateOrder($orderInput: OrderInput!) { createOrder(orderInput: $orderInput) { _id type amount status score createdAt } }"
    }
    _, data = graphql(q, None, True, token, csrf, proxy)
    if "errors" not in data:
        return True, data.get("data", {}).get("createOrder", {})
    return False, data.get("errors", [{}])[0].get("message", "خطأ غير معروف")

def farmer(username, token, csrf, stop_event, logger, proxy=None, score_callback=None):
    """نسخة طبق الأصل من T.py الأصلي"""
    logger(f"[~] {username}: بدء التجميع")
    # الرصيد الابتدائي
    s = fetch_score(token, csrf)
    if s is not None and score_callback: score_callback(s)
    while not stop_event.is_set():
        try:
            q = {"operationName": "GetOrders", "variables": {}, "query": "query GetOrders { getOrders { _id status } }"}
            _, data = graphql(q, "GetOrders", True, token, csrf)
            orders = data.get("data", {}).get("getOrders", []) or []
            pending = [o["_id"] for o in orders if o.get("status") == "pending"]
            if not pending:
                stop_event.wait(10)
                continue
            for task in pending:
                if stop_event.is_set(): break
                rnd = random.randint(3000, 4500)
                q = {"operationName": "ActionOrder",
                    "variables": {"orderId": task,
                        "validationData": {"attempts": 1,
                            "initialNumber": float(rnd),
                            "timeSpent": float(random.randint(4000, 7000)),
                            "actualCount": rnd + 1,
                            "source": "CLIENT_CRONET"}},
                    "query": "mutation ActionOrder($orderId: ID!, $validationData: ValidationDataInput!) { actionOrder(orderId: $orderId, validationData: $validationData) { score taskProgress { count startTime taskProgressLimit } } }"}
                _, result = graphql(q, "ActionOrder", True, token, csrf)
                if "errors" not in result:
                    score = fetch_score(token, csrf)
                    if score is not None:
                        logger(f"[{username}] ✓ تمت المهمة! الرصيد: {score}")
                        if score_callback: score_callback(score)
                    else:
                        logger(f"[{username}] ✓ تمت المهمة!")
                else:
                    err = result.get("errors",[{}])[0].get("message","")[:60]
                    if "Rate limit" in err or "Too many" in err:
                        logger(f"[{username}] ⏳ {err}")
                        stop_event.wait(5)
                    elif "TASK_ALREADY_SUBMITTED" in err:
                        pass
                    elif "TASK_UNAVAILABLE" in err or "TASK_TOO_FAST" in err:
                        pass
                    else:
                        logger(f"[{username}] {err}")
                stop_event.wait(random.uniform(1.5, 3.0))
        except Exception as e:
            logger(f"[{username}] خطأ: {str(e)[:80]}")
            stop_event.wait(5)
    logger(f"[{username}] ⏹ توقف")