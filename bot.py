import requests, hmac, hashlib, time, uuid, json, random, re, os

DEVINFO = '{"d":"61393235613366373261636533656632","n":"494e46494e495820496e66696e6978205836383733","o":"16","t":"d","v":"2.2.9","s":"0,0"}'
KEY = bytes([b ^ 0x43 for b in [0x35,0x30,0x1c,0x2f,0x2c,0x2c,0x28,0x31,0x35,0x30,0x1c,0x2f,0x2c,0x2c,0x28,0x31]])
OP_IDS = {
    "LoginAccount": "3522613813036d73817b2715e67743f8d23d7a85ad08b7e12aa3b29a24a17c43",
    "AttestDevice": "bfaf5a72aeb9a337811da6a6d13e0b73680a18ffde0c59a23701e55b98ac2515",
    "FetchScore": "88d30eeca55c0538539ad8217dfefd52b2f47015200cdbb7cb6ea5a765381d69",
    "CreateOrder": "ad7a6397c3970b1e7601f69d24989bff330e256ee5e39321a8d1ad3fe3879b48",
    "GetUsers": "41454e2194d7c30f1c6e11c2c246bcc0377da65a8bf06276ca5ea9ec9ff538b6"
}
URL = "https://api.tikspark.xyz/graphql"
PROXY_URL = os.getenv("PROXY_URL", "")

def signature(ts, nonce, payload):
    return hmac.new(KEY, f"{ts}-{nonce}-{payload}".encode(), hashlib.sha256).hexdigest()

def graphql(query, op, auth=True, token=None, csrf=None):
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
        "Content-Type": "application/json",
        "User-Agent": "okhttp/4.12.0"
    }
    if op in OP_IDS: headers["X-APOLLO-OPERATION-ID"] = OP_IDS[op]
    if auth:
        headers["token"] = token
        headers["x-csrf-token"] = csrf
    try:
        proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
        r = requests.post(URL, headers=headers, data=payload, timeout=20, proxies=proxies)
        return r, r.json()
    except Exception as e:
        return None, {"error": str(e)}

def login(username, password, retries=5):
    q = {"operationName": "LoginAccount",
        "variables": {"data": {"id": "", "uniqueId": username, "nickname": "",
            "avatarMedium": "", "followerCount": 0, "followingCount": 0, "videoCount": 0,
            "privateAccount": False, "diggCount": 0, "authMethod": "local", "password": password}},
        "query": "mutation LoginAccount($data: TiktokInfo) { loginTiktok(data: $data) { accessToken refreshToken user { __typename ...UserFields } } } fragment UserFields on User { _id tiktokId nickname email score diggCount followerCount followingCount friendCount isMembershipExpired heartCount username avatar banned vip vipExpiresAt authMethod isSubscription allowd referralCode referralCount referredBy }"}
    for attempt in range(retries):
        resp, data = graphql(q, "LoginAccount", auth=False)
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
                if m: wait = int(m.group(1)) + 1
            except: pass
            time.sleep(wait)
            continue
        return None, None, None
    return None, None, None

def fetch_user_data(token, csrf):
    q = {"operationName": "GetUsers", "variables": {},
         "query": "query GetUsers { me { __typename ...UserFields } } fragment UserFields on User { _id tiktokId nickname email score diggCount followerCount followingCount friendCount isMembershipExpired heartCount username avatar banned vip vipExpiresAt authMethod isSubscription allowd referralCode referralCount referredBy }"}
    _, data = graphql(q, "GetUsers", True, token, csrf)
    return data.get("data", {}).get("me", {}) if "errors" not in data else {}

def fetch_score(token, csrf):
    q = {"operationName": "FetchScore", "variables": {}, "query": "query FetchScore { fetchScore }"}
    _, data = graphql(q, "FetchScore", True, token, csrf)
    return data.get("data", {}).get("fetchScore") if "errors" not in data else None

def attest(token, csrf):
    q = {"operationName": "AttestDevice",
        "variables": {"integrityToken": "CpsCARCnMGtvLkiuhYFGDW3rUoE73im9X9NmXA1cHOZZOzgRp5FtsmIrZBoNek0K7XIoZiR9XKg1bpApXNem9MbcR4UiIxz1n4Wgv_LA4hSSAbHzpaAfXcnLyKgwnOXGRUieQ4OOpMTMDRxD6O7kd3jjAfcbcHFt3bdgyw7CJYpxz4oq3lIti658lCdnt1NvJzUwfYSp6eWKcvKV5lScaq-nkplRn7hz38A8kLhYNx6w-7rne41hWCR6BQISVfBewaqeh7RL-9iEDrzK-ECbdEwBnpO-LfAqCJKn1bf5VkVxuPAz5qPvB8cNE7ZBMAyMnDHdjNDwpnZMA2EXsgRsyT6Fm_l3MNugWDdWbRgww6sAw6KrRzeBDETsXTh1ZBpqAWerZWp6AIjaDa-b0NFbOS69HsGnfpE7hljmu7OTsd4tM6nM50qiSc4QGuD4aM-joJFkYKIsWf_grquB66bYnYa2mCWcPl1hIEApHMXbCLiO7nwX-8LXEwCDvVNT4f8mjgtI1__D_C-f4g",
                    "requestHash": "gPyB7FF-XeZc2kwi2L-KZXs21Z8oPErvHD9gn572PyM"},
        "query": "mutation AttestDevice($integrityToken: String!, $requestHash: String!) { attestDevice(integrityToken: $integrityToken, requestHash: $requestHash) { ok verified } }"}
    _, data = graphql(q, "AttestDevice", True, token, csrf)
    return "errors" not in data

def create_order(token, csrf, target_user, avatar, initial_count, logger):
    q = {"operationName": "CreateOrder",
        "variables": {"type": "followers", "amount": 20, "tiktokerUsername": target_user,
                    "avatar": avatar, "initialCount": initial_count},
        "query": "mutation CreateOrder($type: Action!, $amount: Int!, $tiktokerUsername: String, $videoLink: String, $avatar: String, $initialCount: Int) { createOrder(orderInput: { type: $type amount: $amount tiktokerUsername: $tiktokerUsername videoLink: $videoLink avatar: $avatar initialCount: $initialCount } ) { _id status } }"}
    _, data = graphql(q, "CreateOrder", True, token, csrf)
    if "errors" not in data:
        logger(f"[{target_user}] تم إنشاء طلب 20 متابع")
        return True
    return False

def farmer(username, token, csrf, target_user, avatar, init_count, stop_event, logger):
    logger(f"[~] بدء التجميع لـ {username}")
    last = 0
    s = fetch_score(token, csrf) or 0
    if s >= 100 and create_order(token, csrf, target_user, avatar, init_count, logger):
        last = s
    while not stop_event.is_set():
        try:
            q = {"operationName": "GetOrders", "variables": {}, "query": "query GetOrders { getOrders { _id status } }"}
            _, data = graphql(q, "GetOrders", True, token, csrf)
            orders = data.get("data", {}).get("getOrders", [])
            pending = [o["_id"] for o in orders if o.get("status") == "pending"]
            if not pending:
                stop_event.wait(10)
                continue
            for task in pending:
                if stop_event.is_set(): break
                rnd = random.randint(3000, 4500)
                q = {"operationName": "ActionOrder",
                    "variables": {"orderId": task,
                        "validationData": {"attempts": 1, "initialNumber": float(rnd),
                            "timeSpent": float(random.randint(4000, 7000)),
                            "actualCount": rnd + 1, "source": "CLIENT_CRONET"}},
                    "query": "mutation ActionOrder($orderId: ID!, $validationData: ValidationDataInput!) { actionOrder(orderId: $orderId, validationData: $validationData) { score } }"}
                _, result = graphql(q, "ActionOrder", True, token, csrf)
                if "errors" not in result:
                    score = fetch_score(token, csrf)
                    if score is not None:
                        logger(f"[{username}] تمت المهمة! الرصيد: {score}")
                        if score - last >= 100 and create_order(token, csrf, target_user, avatar, init_count, logger):
                            last = score
                stop_event.wait(random.uniform(1.5, 3.0))
        except Exception as e:
            logger(f"[{username}] خطأ: {e}")
            stop_event.wait(5)
    logger(f"[{username}] توقف")
