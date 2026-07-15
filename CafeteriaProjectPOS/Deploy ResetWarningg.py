"""
deployment_reset.py — Clear ALL data from Firestore and Firebase Storage
Use this BEFORE deployment to start with a clean database.

⚠️  WARNING: This is IRREVERSIBLE. All data will be permanently deleted.
     Run this only when you are sure you want a fresh start.

Collections cleared:
  - transactions
  - transaction_items
  - products
  - loyalty_members
  - salary_deductions
  - teachers (if exists)
  - mobile_orders (Android app orders)
  - users (Android app users)

Storage cleared:
  - products/ (all product images)
"""

import json
import os
import urllib.request
import urllib.parse
import time

# ── Load credentials ──
_base      = os.path.dirname(os.path.abspath(__file__))
_cred_file = os.path.join(_base, "cafeteriadatabase-firebase-adminsdk-fbsvc-5b5f4a27c0.json")
with open(_cred_file) as f:
    _cred_data = json.load(f)

PROJECT_ID = _cred_data["project_id"]
BUCKET     = f"{PROJECT_ID}.firebasestorage.app"
BASE_URL   = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

import database as db


def confirm():
    print("=" * 60)
    print("  ⚠️   DEPLOYMENT RESET TOOL")
    print("=" * 60)
    print()
    print("This will PERMANENTLY DELETE:")
    print("  • All transactions")
    print("  • All products")
    print("  • All loyalty members")
    print("  • All salary deductions")
    print("  • All mobile orders (Android app)")
    print("  • All product images in Storage")
    print()
    print("This is IRREVERSIBLE!")
    print()
    ans = input("Type  YES DELETE ALL  to confirm: ").strip()
    if ans != "YES DELETE ALL":
        print("\n❌ Cancelled. Nothing was deleted.")
        return False
    print()
    return True


def delete_collection(collection):
    """Delete all documents in a Firestore collection."""
    token    = db._get_token()
    deleted  = 0
    page_token = None

    while True:
        url = f"{BASE_URL}/{collection}?pageSize=300"
        if page_token:
            url += f"&pageToken={page_token}"
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"   ⚠️  Error listing {collection}: {e}")
            break

        docs = data.get("documents", [])
        if not docs:
            break

        for doc in docs:
            doc_name = doc.get("name", "")
            if not doc_name:
                continue
            doc_id = doc_name.split("/")[-1]
            try:
                token = db._get_token()
                del_url = f"{BASE_URL}/{collection}/{doc_id}"
                req2 = urllib.request.Request(
                    del_url,
                    method="DELETE",
                    headers={"Authorization": f"Bearer {token}"})
                urllib.request.urlopen(req2, timeout=30)
                deleted += 1
            except Exception as e:
                print(f"   ⚠️  Error deleting {collection}/{doc_id}: {e}")

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return deleted


def delete_storage_folder(prefix="products/"):
    """Delete all files under a prefix in Firebase Storage."""
    token   = db._get_token()
    deleted = 0
    page_token = None

    while True:
        encoded_bucket = urllib.parse.quote(BUCKET, safe='')
        url = (f"https://firebasestorage.googleapis.com/v0/b/{encoded_bucket}/o"
               f"?prefix={urllib.parse.quote(prefix, safe='')}&maxResults=300")
        if page_token:
            url += f"&pageToken={urllib.parse.quote(page_token, safe='')}"

        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"   ⚠️  Error listing storage: {e}")
            break

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            name = item.get("name", "")
            if not name:
                continue
            try:
                token = db._get_token()
                encoded_name   = urllib.parse.quote(name, safe="")
                del_url = (f"https://firebasestorage.googleapis.com/v0/b/"
                           f"{encoded_bucket}/o/{encoded_name}")
                req2 = urllib.request.Request(
                    del_url,
                    method="DELETE",
                    headers={"Authorization": f"Bearer {token}"})
                urllib.request.urlopen(req2, timeout=30)
                deleted += 1
                print(f"   🗑  Deleted image: {name}")
            except Exception as e:
                print(f"   ⚠️  Error deleting {name}: {e}")

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return deleted


def clear_local_sqlite():
    """Clear all local SQLite data."""
    import sqlite3
    import offline_db as _odb
    conn = sqlite3.connect(str(_odb.DB_PATH))
    cur  = conn.cursor()
    tables = [
        "transactions_local",
        "transaction_items_local",
        "products_cache",
        "loyalty_members",
        "salary_deductions",
        "teachers_registry",
    ]
    cleared = 0
    for table in tables:
        try:
            cur.execute(f"DELETE FROM {table}")
            cleared += cur.rowcount
        except Exception as e:
            print(f"   ⚠️  Could not clear {table}: {e}")
    conn.commit()
    conn.close()
    return cleared


def main():
    if not confirm():
        return

    print("🚀 Starting deployment reset...\n")
    total_deleted = 0

    # ── Firestore Collections ──
    collections = [
        "transactions",
        "transaction_items",
        "products",
        "loyalty_members",
        "salary_deductions",
        "mobile_orders",
        "users",
        "teachers",
    ]

    print("📦 Clearing Firestore collections...")
    for col in collections:
        print(f"   Deleting {col}...", end=" ", flush=True)
        count = delete_collection(col)
        total_deleted += count
        print(f"✅ {count} document(s) deleted")
        time.sleep(0.3)  # small delay to avoid rate limiting

    # ── Firebase Storage ──
    print("\n🖼️  Clearing Firebase Storage images...")
    img_deleted = delete_storage_folder("products/")
    print(f"   ✅ {img_deleted} image(s) deleted")

    # ── Local SQLite ──
    print("\n💾 Clearing local SQLite database...")
    local_cleared = clear_local_sqlite()
    print(f"   ✅ {local_cleared} local record(s) cleared")

    print()
    print("=" * 60)
    print(f"✅ Firestore:  {total_deleted} document(s) deleted")
    print(f"✅ Storage:    {img_deleted} image(s) deleted")
    print(f"✅ SQLite:     {local_cleared} record(s) cleared")
    print("=" * 60)
    print()
    print("🎉 Reset complete! Your system is ready for deployment.")
    print("   You can now add fresh products, members, and data.")


if __name__ == "__main__":
    main()