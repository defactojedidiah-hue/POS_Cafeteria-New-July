import json, os, time, random, urllib.request, urllib.parse
from datetime import datetime, timedelta
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import socket
import offline_db

# ── SETUP ─────────────────────────────────────────────────────
base = os.path.dirname(os.path.abspath(__file__))
CRED_PATH = os.path.join(base, "cafeteriadatabase-firebase-adminsdk-fbsvc-5b5f4a27c0.json")

with open(CRED_PATH) as f:
    _cred_data = json.load(f)

PROJECT_ID = _cred_data["project_id"]
BASE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

_credentials = None


def _get_token():
    global _credentials
    if _credentials is None:
        _credentials = service_account.Credentials.from_service_account_file(
            CRED_PATH, scopes=["https://www.googleapis.com/auth/datastore"])
    if not _credentials.valid:
        _credentials.refresh(Request())
    return _credentials.token


def _req(method, path, body=None):
    url   = BASE_URL + path
    token = _get_token()
    data  = json.dumps(body).encode() if body else None
    req   = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.code, e.read().decode())
        return None
    except Exception as e:
        print("Request Error:", type(e).__name__, str(e))
        return None


def _query(collection, filters=None, order_by=None, limit=None):
    token = _get_token()
    url   = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents:runQuery"
    where_clause = None
    if filters:
        if len(filters) == 1:
            f = filters[0]
            where_clause = {"fieldFilter": {"field": {"fieldPath": f[0]},
                                            "op": f[1], "value": _to_fs_value(f[2])}}
        else:
            where_clause = {"compositeFilter": {"op": "AND", "filters": [
                {"fieldFilter": {"field": {"fieldPath": fi[0]},
                                 "op": fi[1], "value": _to_fs_value(fi[2])}} for fi in filters]}}
    query = {"from": [{"collectionId": collection}]}
    if where_clause: query["where"]   = where_clause
    if order_by:     query["orderBy"] = [{"field": {"fieldPath": order_by[0]}, "direction": order_by[1]}]
    if limit:        query["limit"]   = limit
    body = json.dumps({"structuredQuery": query}).encode()
    req  = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        resp    = urllib.request.urlopen(req, timeout=20)
        results = json.loads(resp.read())
        return [r for r in results if "document" in r]
    except urllib.error.HTTPError as e:
        print("Query HTTP Error", e.code, ":", e.read().decode()); return []
    except Exception as e:
        print("Query error:", type(e).__name__, str(e)); return []


def _to_fs_value(val):
    if isinstance(val, bool):  return {"booleanValue": val}
    if isinstance(val, int):   return {"integerValue": str(val)}
    if isinstance(val, float): return {"doubleValue": val}
    if isinstance(val, str):   return {"stringValue": val}
    if isinstance(val, list):  return {"arrayValue": {
        "values": [_to_fs_value(v) for v in val]}}
    if isinstance(val, dict):  return {"mapValue": {
        "fields": {k: _to_fs_value(v) for k, v in val.items()}}}
    if val is None: return {"nullValue": None}
    return {"stringValue": str(val)}


def _from_fs_value(val):
    if "stringValue"  in val: return val["stringValue"]
    if "integerValue" in val: return int(val["integerValue"])
    if "doubleValue"  in val: return float(val["doubleValue"])
    if "booleanValue" in val: return val["booleanValue"]
    if "nullValue"    in val: return None
    if "arrayValue"   in val:
        values = val["arrayValue"].get("values", [])
        return [_from_fs_value(v) for v in values]
    if "mapValue"     in val:
        fields = val["mapValue"].get("fields", {})
        return {k: _from_fs_value(v) for k, v in fields.items()}
    return None


def _parse_doc(doc_result):
    doc    = doc_result["document"] if "document" in doc_result else doc_result
    fields = doc.get("fields", {})
    result = {k: _from_fs_value(v) for k, v in fields.items()}
    if "name" in doc:
        result["_doc_name"] = doc["name"]
        result["_doc_id"]   = doc["name"].split("/")[-1]
    return result


def _to_fs_fields(d):
    return {"fields": {k: _to_fs_value(v) for k, v in d.items()}}


def _set_doc(collection, doc_id, data):
    _req("PATCH", f"/{collection}/{doc_id}", _to_fs_fields(data))


def _batch_write(writes):
    """Send up to 500 writes in a single Firestore batch request."""
    if not writes:
        return
    token  = _get_token()
    url    = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents:batchWrite"
    body   = json.dumps({"writes": writes}).encode("utf-8")
    req    = urllib.request.Request(url, data=body, method="POST",
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
    except Exception as e:
        print(f"Batch write error: {e}")


def _make_batch_upsert(collection, doc_id, data):
    """Build a single write object for use in _batch_write."""
    doc_path = f"projects/{PROJECT_ID}/databases/(default)/documents/{collection}/{doc_id}"
    return {
        "update": {"name": doc_path, "fields": _to_fs_fields(data)["fields"]},
    }


def _update_doc(collection, doc_id, data):
    """Partial update — only updates specified fields, keeps all others intact."""
    field_paths = ",".join(data.keys())
    url_path = f"/{collection}/{doc_id}?updateMask.fieldPaths=" +                "&updateMask.fieldPaths=".join(data.keys())
    _req("PATCH", url_path, _to_fs_fields(data))


def _get_doc(collection, doc_id):
    result = _req("GET", f"/{collection}/{doc_id}")
    if result and "fields" in result:
        return _parse_doc(result)
    return None


def _delete_doc(collection, doc_id):
    _req("DELETE", f"/{collection}/{doc_id}")


# ── INIT ──────────────────────────────────────────────────────
def init_db():
    offline_db.init_local_db()


def init_salary_table():
    pass


def has_internet(host="8.8.8.8", port=53, timeout=2):
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port)); s.close()
        return True
    except OSError:
        return False


def _get_next_txn_id(store="cafestore"):
    import string
    if store == "cafestore":
        return "TXN-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    else:
        return "CAN-" + str(int(time.time() * 1000))[-8:]


# ════════════════════════════════════════════════════════════
#  PRODUCT CACHE  — saves products to SQLite when online
#  so that barcode scan works offline too
# ════════════════════════════════════════════════════════════
def _cache_products(rows, store):
    """Save product list to offline_db for offline use."""
    try:
        offline_db.save_products_cache(rows, store)
    except Exception as e:
        print("Product cache write error:", e)


def _get_cached_products(store):
    """Load products from offline cache."""
    try:
        return offline_db.get_cached_products(store)
    except Exception:
        return []


# ── PRODUCTS ──────────────────────────────────────────────────
def get_all_products(store="cafestore"):
    """PRIMARY: SQLite. Firestore only used for initial populate if cache empty."""
    cached = _get_cached_products(store)
    if cached:
        return sorted(cached, key=lambda r: r[1])
    # Cache empty — try Firestore once to populate
    if has_internet():
        results = _query("products", filters=[["store", "EQUAL", store]])
        rows = []
        for r in results:
            d = _parse_doc(r)
            rows.append((
                d.get("barcode", ""), d.get("name", ""), d.get("category", ""),
                float(d.get("price", 0)), int(d.get("stock", 0)),
                int(d.get("is_daily", 0)), d.get("date_added", ""),
                d.get("image_url", "")
            ))
        rows_sorted = sorted(rows, key=lambda r: r[1])
        _cache_products(rows_sorted, store)
        return rows_sorted
    return []


def add_product(barcode, name, category, price, stock, store="cafestore", is_daily=0, image_url=""):
    """SQLite only. Firestore updated via Backup button to save free quota.
    Exception: Daily Menu items are pushed to Firestore immediately."""
    today = datetime.now().strftime("%Y-%m-%d")
    existing = [r for r in get_all_products(store) if r[0] != barcode]
    existing.append((barcode, name, category, float(price), int(stock), int(is_daily), today, image_url))
    _cache_products(sorted(existing, key=lambda r: r[1]), store)
    # ── Push Daily Menu items to Firestore immediately so app sees them ──
    if category == "Daily Menu" or int(is_daily) == 1:
        try:
            from datetime import datetime as _dt2
            _now = _dt2.now().strftime("%Y-%m-%d %H:%M:%S")
            _set_doc("products", f"{store}_{barcode}", {
                "barcode": barcode, "name": name, "category": category,
                "price": float(price), "stock": int(stock), "store": store,
                "is_daily": int(is_daily), "date_added": today,
                "daily_added_at": _now,
                "image_url": image_url or "",
            })
        except Exception as e:
            print(f"[Daily Menu] Firestore push error: {e}")


def update_product(barcode, name, category, price, stock, is_daily=0, store="cafestore", image_url=None):
    """SQLite only. Preserves existing image_url if not provided. Firestore via Backup.
    Exception: Daily Menu items are pushed to Firestore immediately."""
    today = datetime.now().strftime("%Y-%m-%d")
    # Preserve existing image_url from SQLite if not provided
    if image_url is None:
        existing_prods = get_all_products(store)
        for p in existing_prods:
            if p[0] == barcode:
                image_url = p[7] if len(p) > 7 else ""
                break
        if image_url is None:
            image_url = ""
    existing = [r for r in get_all_products(store) if r[0] != barcode]
    existing.append((barcode, name, category, float(price), int(stock), int(is_daily), today, image_url))
    _cache_products(sorted(existing, key=lambda r: r[1]), store)
    # ── Push Daily Menu items to Firestore immediately so app sees them ──
    if category == "Daily Menu" or int(is_daily) == 1:
        try:
            from datetime import datetime as _dt2
            _now = _dt2.now().strftime("%Y-%m-%d %H:%M:%S")
            _set_doc("products", f"{store}_{barcode}", {
                "barcode": barcode, "name": name, "category": category,
                "price": float(price), "stock": int(stock), "store": store,
                "is_daily": int(is_daily), "date_added": today,
                "daily_added_at": _now,
                "image_url": image_url or "",
            })
        except Exception as e:
            print(f"[Daily Menu] Firestore push error: {e}")


def delete_product(barcode, store="cafestore"):
    """SQLite only. Firestore updated via Backup button."""
    existing = [r for r in get_all_products(store) if r[0] != barcode]
    _cache_products(existing, store)


def get_categories(store="cafestore"):
    rows = get_all_products(store)
    cats = sorted({r[2] for r in rows})
    if store == "canteen":
        # Always ensure Daily Menu is available
        default = ["Daily Menu","Rice Meal","Soup","Pork","Beef","Fish",
                   "Chicken","Vegetable","Egg Dish","Noodles","Beverages",
                   "Drinks","Snacks","Dessert","Other"]
        if not cats:
            return default
        # Merge existing + defaults, keep Daily Menu always first
        merged = sorted(set(cats) | set(default))
        if "Daily Menu" in merged:
            merged.remove("Daily Menu")
            merged.insert(0, "Daily Menu")
        return merged
    if not cats:
        return ["Beverage","Drinks","Food","Snacks","Supplies",
                "Bread & Pastry","Dairy","Frozen","Personal Care","Other"]
    return cats


def get_customer_names(store="cafestore"):
    """PRIMARY: SQLite."""
    names = set()
    for n in offline_db.get_local_customer_names(store):
        if n: names.add(n)
    return sorted(names)


def generate_barcode(store="cafestore"):
    """Generate unique barcode — check against SQLite cache."""
    prefix = "CAN" if store == "canteen" else "CAF"
    existing = {r[0] for r in get_all_products(store)}
    while True:
        code = prefix + str(int(time.time()))[-6:] + str(random.randint(10,99))
        if code not in existing:
            return code


# ── TRANSACTIONS / OFFLINE SYNC ───────────────────────────────
def _save_transaction_online(txn_id, dt, total, method, cash_given, change_given,
                             customer_name, department, buyer_type, items, store="cafestore"):
    item_names = ", ".join(item["name"] + " " + str(item["qty"]) + "x" for item in items)
    item_count = len(items)
    _set_doc("transactions", txn_id, {
        "txn_id": txn_id, "datetime": dt, "total": float(total),
        "payment_method": method, "cash_given": float(cash_given),
        "change_given": float(change_given), "customer_name": customer_name,
        "department": department, "buyer_type": buyer_type, "store": store,
        "item_names": item_names, "item_count": item_count
    })
    for i, item in enumerate(items):
        _set_doc("transaction_items", txn_id + "_" + str(i), {
            "txn_id": txn_id, "barcode": item["barcode"],
            "name": item["name"], "category": item["category"],
            "price": float(item["price"]), "qty": int(item["qty"])
        })
        doc_id = store + "_" + item["barcode"]
        prod   = _get_doc("products", doc_id)
        if prod:
            new_stock = max(0, int(prod.get("stock", 0)) - int(item["qty"]))
            prod["stock"] = new_stock
            _set_doc("products", doc_id, prod)
            # ── FIX: immediately update local SQLite cache per item ──
            # Firestore collection queries can lag behind a PATCH write by
            # a brief moment. If we relied only on the get_all_products()
            # refresh below, the query might return old stock and overwrite
            # the cache — causing the "item still scannable after sold out" bug.
            try:
                offline_db.update_product_stock_in_cache(item["barcode"], store, new_stock)
            except Exception as e:
                print("Cache stock patch error:", e)
    # Refresh full cache from Firestore (best-effort; SQLite already patched above)
    try: get_all_products(store)
    except: pass


def upload_offline_transaction_to_firestore(txn):
    _save_transaction_online(
        txn_id=txn["txn_id"], dt=txn["dt"], total=txn["total"],
        method=txn["method"], cash_given=txn.get("cash",0),
        change_given=txn.get("change_amount",0),
        customer_name=txn.get("customer_name",""),
        department=txn.get("department",""),
        buyer_type=txn.get("buyer_type",""),
        items=txn.get("items",[]), store=txn.get("store","cafestore"))


def sync_pending_transactions(skip_txn_id=None):
    if not has_internet(): return 0
    pending = offline_db.get_pending_transactions()
    synced  = 0
    for txn in pending:
        if skip_txn_id and txn.get("txn_id") == skip_txn_id: continue
        try:
            upload_offline_transaction_to_firestore(txn)
            offline_db.mark_transaction_synced(txn["txn_id"])
            synced += 1
        except Exception as e:
            offline_db.mark_transaction_failed(txn["txn_id"], str(e))
    return synced


def save_transaction(dt, total, method, cash_given, change_given,
                     customer_name, department, items,
                     buyer_type="", store="cafestore"):
    """
    SQLite first for ALL transactions (fast, offline-safe).
    Credit/Utang → ALSO saved to Firestore directly (admin sees live).
    Non-credit → marked pending, auto-sync watcher pushes when online.
    """
    txn_id = _get_next_txn_id(store=store)

    # 1. Always save to SQLite first
    offline_db.save_transaction_local(
        txn_id=txn_id, dt=dt, total=float(total), method=method,
        cash=float(cash_given), change=float(change_given),
        customer_name=customer_name, department=department,
        buyer_type=buyer_type, cart=items, store=store)

    # 2. Deduct stock from SQLite immediately
    for item in items:
        try:
            cached = offline_db.get_cached_product_by_barcode(item["barcode"], store)
            if cached:
                new_stock = max(0, int(cached.get("stock", 0)) - int(item.get("qty", 0)))
                offline_db.update_product_stock_in_cache(item["barcode"], store, new_stock)
        except Exception as e:
            print("Stock deduct error:", e)

    # 3. Credit/Utang → push to Firestore immediately (admin needs to see live)
    if method == "Credit / Utang":
        if has_internet():
            try:
                _save_transaction_online(txn_id, dt, total, method, cash_given,
                                         change_given, customer_name, department,
                                         buyer_type, items, store=store)
                offline_db.mark_transaction_synced(txn_id)
            except Exception as e:
                print(f"Credit Firestore sync error: {e}")
                offline_db.mark_transaction_failed(txn_id, str(e))
        else:
            # Offline — will sync when internet returns
            offline_db.mark_transaction_failed(txn_id, "offline")
    else:
        # Non-credit → auto-sync watcher handles it
        pass  # stays as pending in SQLite

    return txn_id


def get_all_transactions(store="cafestore"):
    """PRIMARY: SQLite."""
    rows = []
    local_rows = offline_db.get_all_local_transactions(store)
    for d in local_rows:
        txn_id     = d.get("txn_id","")
        items      = offline_db.get_local_transaction_items(txn_id)
        item_names = ", ".join(f"{it.get('name','')} {int(it.get('qty',0))}x" for it in items)
        rows.append((
            txn_id, d.get("dt",""), float(d.get("total",0)),
            d.get("method",""), float(d.get("cash",0)),
            float(d.get("change_amount",0)), d.get("customer_name",""),
            d.get("department",""), d.get("buyer_type",""),
            item_names, len(items)
        ))
    rows.sort(key=lambda r: r[1], reverse=True)
    return rows


def get_transaction_items(txn_id):
    """PRIMARY: SQLite."""
    rows = []
    for item in offline_db.get_local_transaction_items(txn_id):
        rows.append((item.get("name",""), item.get("category",""),
                     float(item.get("price",0)), int(item.get("qty",0))))
    return rows


def get_credits(store="cafestore"):
    """
    Merge SQLite (local) + Firestore (online) — shows ALL credit records.
    SQLite = new transactions saved locally.
    Firestore = old transactions + credit synced from admin.
    Returns 7-field tuples: (txn_id, dt, total, customer_name, dept, buyer_type, item_count)
    """
    seen = set()
    rows = []

    # 1. Read SQLite first (fast, always available)
    local_rows = offline_db.get_all_local_transactions(store)
    for d in local_rows:
        if d.get("method","") == "Credit / Utang":
            txn_id = d.get("txn_id","")
            seen.add(txn_id)
            items = offline_db.get_local_transaction_items(txn_id)
            rows.append((
                txn_id, d.get("dt",""),
                float(d.get("total",0)), d.get("customer_name",""),
                d.get("department",""), d.get("buyer_type",""),
                len(items)
            ))

    # 2. Merge Firestore records (catches old data not in SQLite)
    if has_internet():
        try:
            results = _query("transactions",
                             filters=[["store","EQUAL",store]])
            for r in results:
                d = _parse_doc(r)
                if d.get("payment_method","") != "Credit / Utang": continue
                txn_id = d.get("txn_id","")
                if txn_id in seen: continue  # already in SQLite
                seen.add(txn_id)
                rows.append((
                    txn_id, d.get("datetime",""),
                    float(d.get("total",0)), d.get("customer_name",""),
                    d.get("department",""), d.get("buyer_type",""),
                    int(d.get("item_count",0))
                ))
        except Exception as e:
            print(f"get_credits Firestore merge error: {e}")

    rows.sort(key=lambda r: r[1], reverse=True)
    return rows
    return rows


def get_credit_summary(store="cafestore"):
    results = get_credits(store=store)
    summary = {}
    for r in results:
        # r = (txn_id, dt, total, customer_name, department, buyer_type, item_count)
        name = r[3]; dept = r[4]; total = float(r[2])
        if not name: continue
        if name not in summary: summary[name] = {"dept":dept,"total":0.0,"count":0}
        summary[name]["total"] += total; summary[name]["count"] += 1
    return sorted([(n,v["dept"],v["total"],v["count"]) for n,v in summary.items()],
                  key=lambda r: r[2], reverse=True)


def _build_report_sqlite(store, since=None, until=None):
    """Build sales report from SQLite."""
    local_rows = offline_db.get_all_local_transactions(store)
    if since:  local_rows = [r for r in local_rows if r.get("dt","") >= since]
    if until:  local_rows = [r for r in local_rows if r.get("dt","") <= until]
    count=0; revenue=0.0; by_method={}; items_map={}
    for d in local_rows:
        count += 1; total = float(d.get("total",0)); revenue += total
        m = d.get("method","")
        # Keep Cash (Mobile) separate so it shows in breakdown
        by_method[m] = by_method.get(m,0.0) + total
        for it in offline_db.get_local_transaction_items(d.get("txn_id","")):
            nm = it.get("name","")
            if nm not in items_map:
                items_map[nm] = {"cat":it.get("category",""),"qty":0,"rev":0.0}
            qty = int(it.get("qty",0))
            items_map[nm]["qty"] += qty
            items_map[nm]["rev"] += qty * float(it.get("price",0))
    items_sold = sorted([(nm,v["cat"],v["qty"],v["rev"]) for nm,v in items_map.items()],
                        key=lambda r: r[2], reverse=True)
    return {"count":count,"revenue":revenue,"by_method":by_method,
            "items_sold":items_sold,"avg":revenue/count if count else 0}


def get_sales_report(period="week", store="cafestore"):
    """PRIMARY: SQLite."""
    now = datetime.now()
    if   period == "day":   since = now.replace(hour=0,minute=0,second=0).strftime("%Y-%m-%d %H:%M:%S")
    elif period == "week":  since = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    elif period == "month": since = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    else:                   since = "2000-01-01 00:00:00"
    return _build_report_sqlite(store, since=since)


def get_sales_report_custom(from_date, to_date, store="cafestore"):
    """PRIMARY: SQLite."""
    return _build_report_sqlite(store,
                                since=from_date + " 00:00:00",
                                until=to_date   + " 23:59:59")


# ── SALARY DEDUCTIONS ─────────────────────────────────────────
def add_deduction(faculty, department, amount, note, dt):
    """Saves to SQLite + Firestore directly (admin always online)."""
    doc_id = "ded_" + str(int(time.time()))
    offline_db._ensure_deductions_table()
    offline_db.save_deduction_local(doc_id, faculty, department, float(amount), note, dt)
    # Always push to Firestore so Store/Karen can read it live
    try:
        _set_doc("salary_deductions", doc_id, {
            "doc_id": doc_id, "faculty": faculty, "department": department,
            "amount": float(amount), "note": note, "datetime": dt
        })
    except Exception as e:
        print(f"Firestore deduction sync error: {e}")


def get_deductions():
    """PRIMARY: SQLite."""
    offline_db._ensure_deductions_table()
    rows = offline_db.get_all_deductions_local()
    return [(r["doc_id"],r["faculty"],r["department"],
             r["amount"],r["note"],r["datetime"]) for r in rows]


def get_deductions_by_faculty(faculty):
    """PRIMARY: SQLite."""
    offline_db._ensure_deductions_table()
    rows = offline_db.get_deductions_by_faculty_local(faculty)
    return [(r["doc_id"],r["faculty"],r["department"],
             r["amount"],r["note"],r["datetime"]) for r in rows]


def get_total_deducted(faculty):
    """Read from Firestore for live admin deductions. SQLite fallback."""
    if has_internet():
        try:
            results = _query("salary_deductions", filters=[["faculty","EQUAL",faculty]])
            return round(sum(float(_parse_doc(r).get("amount",0)) for r in results), 2)
        except Exception as e:
            print(f"get_total_deducted Firestore error: {e}")
    offline_db._ensure_deductions_table()
    return offline_db.get_total_deducted_local(faculty)


def get_all_deductions_map():
    """
    Fetch ALL deductions in ONE Firestore call → {faculty: total_deducted}.
    Fast — one query instead of one per person.
    Falls back to SQLite if offline.
    """
    if has_internet():
        try:
            results = _query("salary_deductions")
            deduct_map = {}
            for r in results:
                d = _parse_doc(r)
                faculty = d.get("faculty", "")
                if faculty:
                    deduct_map[faculty] = deduct_map.get(faculty, 0.0) + float(d.get("amount", 0))
            return deduct_map
        except Exception as e:
            print(f"get_all_deductions_map Firestore error: {e}")
    # Offline fallback — SQLite
    offline_db._ensure_deductions_table()
    rows = offline_db.get_all_deductions_local()
    result = {}
    for r in rows:
        faculty = r["faculty"]
        result[faculty] = result.get(faculty, 0.0) + float(r["amount"])
    return result


def mark_paid(faculty, department, dt):
    """SQLite + Firestore directly."""
    doc_id = "ded_" + str(int(time.time()))
    offline_db._ensure_deductions_table()
    offline_db.save_deduction_local(doc_id, faculty, department,
                                     0.0, "FULLY PAID - Record Cleared", dt)
    try:
        _set_doc("salary_deductions", doc_id, {
            "doc_id": doc_id, "faculty": faculty, "department": department,
            "amount": 0.0, "note": "FULLY PAID - Record Cleared", "datetime": dt
        })
    except Exception as e:
        print(f"Firestore mark_paid sync error: {e}")


def delete_faculty_credits(faculty, store="cafestore"):
    """Delete from SQLite + Firestore (keep both in sync)."""
    import sqlite3
    # 1. Delete from SQLite
    try:
        conn = sqlite3.connect(str(offline_db.DB_PATH))
        cur  = conn.cursor()
        cur.execute("SELECT txn_id FROM transactions_local WHERE customer_name=? AND store=?",
                    (faculty, store))
        tids = [r[0] for r in cur.fetchall()]
        for tid in tids:
            cur.execute("DELETE FROM transaction_items_local WHERE txn_id=?", (tid,))
        cur.execute("DELETE FROM transactions_local WHERE customer_name=? AND store=?",
                    (faculty, store))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"delete_faculty_credits SQLite error: {e}")
    # 2. Delete from Firestore (so admin and inventory stay in sync)
    if has_internet():
        try:
            results = _query("transactions",
                             filters=[["customer_name","EQUAL",faculty]])
            for r in results:
                d = _parse_doc(r)
                if d.get("store","") != store: continue
                txn_id = d.get("txn_id","")
                items = _query("transaction_items",
                               filters=[["txn_id","EQUAL",txn_id]])
                for it in items:
                    dn = it.get("document",{}).get("name","")
                    if dn: _delete_doc("transaction_items", dn.split("/")[-1])
                dn = r.get("document",{}).get("name","")
                if dn: _delete_doc("transactions", dn.split("/")[-1])
        except Exception as e:
            print(f"delete_faculty_credits Firestore error: {e}")


def reduce_stock(barcode, qty, store="cafestore"):
    """SQLite first."""
    try:
        cached = offline_db.get_cached_product_by_barcode(barcode, store)
        if cached:
            new_stock = max(0, int(cached.get("stock", 0)) - int(qty))
            offline_db.update_product_stock_in_cache(barcode, store, new_stock)
    except Exception as e:
        print(f"reduce_stock SQLite error: {e}")


# ════════════════════════════════════════════════════════════
#  LOYALTY CARD / COOP MEMBER
# ════════════════════════════════════════════════════════════
def add_loyalty_member(member_id, name, department, card_barcode, store="coop"):
    """SQLite first + Firestore directly so admin can see immediately."""
    offline_db.save_loyalty_member_local(member_id, name, department, card_barcode, store)
    if has_internet():
        try:
            doc_id = f"{store}_{member_id}"
            _set_doc("loyalty_members", doc_id, {
                "member_id":    member_id,
                "name":         name,
                "department":   department,
                "card_barcode": card_barcode,
                "store":        store,
            })
        except Exception as e:
            print(f"Firestore member sync error: {e}")


def get_all_loyalty_members(store="cafestore"):
    """PRIMARY: SQLite. Populate from Firestore if empty."""
    cached = offline_db.get_cached_loyalty_members(store)
    if cached:
        return sorted(cached, key=lambda m: m["name"])
    if has_internet():
        results = _query("loyalty_members", filters=[["store","EQUAL",store]])
        members = []
        for r in results:
            d = _parse_doc(r)
            members.append({"member_id":d.get("member_id",""),
                            "name":d.get("name",""),
                            "department":d.get("department",""),
                            "card_barcode":d.get("card_barcode","")})
        try: offline_db.cache_loyalty_members(members, store)
        except Exception: pass
        return sorted(members, key=lambda m: m["name"])
    return []


def get_loyalty_member_by_card(card_barcode, store="cafestore"):
    """PRIMARY: SQLite."""
    return offline_db.get_loyalty_member_by_card_local(card_barcode)


def delete_loyalty_member(card_barcode):
    """SQLite first. Firestore via Backup."""
    offline_db.delete_loyalty_member_local(card_barcode)


def get_loyalty_member_by_card_name(name, store="cafestore"):
    """PRIMARY: SQLite."""
    try:
        members = offline_db.get_cached_loyalty_members(store)
        for m in members:
            if m["name"].strip().lower() == name.strip().lower():
                return m
    except Exception:
        pass
    return None


# ════════════════════════════════════════════════════════════
#  TEACHER REGISTRY  (non-member faculty with credit/utang)
# ════════════════════════════════════════════════════════════
def _generate_teacher_id():
    import string
    return "TCH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def ensure_teacher_registered(name, department, store="cafestore"):
    """
    If this teacher (by name) is not yet in the registry, auto-create
    a TCH-XXXXXX primary key and save them.
    Returns the teacher dict.
    """
    # Check local cache first
    existing = offline_db.get_teacher_by_name(name)
    if existing:
        return existing
    # Not found — create new locally
    teacher_id = _generate_teacher_id()
    offline_db.save_teacher_local(teacher_id, name, department, store)
    return {"teacher_id": teacher_id, "name": name, "department": department}


def get_teacher_by_name(name, store="cafestore"):
    """PRIMARY: SQLite."""
    return offline_db.get_teacher_by_name(name)


def get_all_teachers(store="cafestore"):
    """PRIMARY: SQLite."""
    cached = offline_db.get_cached_teachers(store)
    if cached:
        return sorted(cached, key=lambda t: t["name"])
    if has_internet():
        results = _query("teachers", filters=[["store","EQUAL",store]])
        teachers = []
        for r in results:
            d = _parse_doc(r)
            teachers.append({"teacher_id":d.get("teacher_id",""),
                             "name":d.get("name",""),
                             "department":d.get("department","")})
        try: offline_db.cache_teachers(teachers, store)
        except Exception: pass
        return sorted(teachers, key=lambda t: t["name"])
    return offline_db.get_cached_teachers(store)