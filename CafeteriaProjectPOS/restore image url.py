"""
restore_image_urls.py — Restore image_url for all products from Firebase Storage
Place this in your project folder and run it ONCE.

What it does:
1. Lists all images in Firebase Storage under products/
2. Matches each image to a product in your SQLite
3. Updates image_url in both SQLite and Firestore
"""
import sqlite3
import json
import urllib.request
import urllib.parse
import os

# ── Load credentials (same as database.py) ──
_base = os.path.dirname(os.path.abspath(__file__))
_cred_file = os.path.join(_base, "cafeteriadatabase-firebase-adminsdk-fbsvc-5b5f4a27c0.json")
with open(_cred_file) as f:
    _cred_data = json.load(f)

PROJECT_ID = _cred_data["project_id"]
BUCKET     = f"{PROJECT_ID}.firebasestorage.app"

import database as db
import offline_db


def list_storage_images():
    """List all files under products/ in Firebase Storage."""
    token   = db._get_token()
    encoded = urllib.parse.quote(BUCKET, safe='')
    url     = (
        f"https://firebasestorage.googleapis.com/v0/b/{encoded}/o"
        f"?prefix=products%2F&maxResults=200"
    )
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data.get("items", [])


def build_download_url(item):
    """Build download URL from Storage item metadata."""
    name       = item.get("name", "")         # e.g. products/canteen_KAR002.png
    token_dl   = item.get("downloadTokens","")
    encoded    = urllib.parse.quote(name, safe="")
    bucket_enc = urllib.parse.quote(BUCKET, safe="")
    return (
        f"https://firebasestorage.googleapis.com/v0/b/"
        f"{bucket_enc}/o/{encoded}?alt=media&token={token_dl}"
    )


def main():
    print("🔍 Listing images in Firebase Storage...")
    items = list_storage_images()
    print(f"   Found {len(items)} image(s) in storage.\n")

    conn = sqlite3.connect(str(offline_db.DB_PATH))
    conn.row_factory = sqlite3.Row
    cur  = conn.cursor()

    updated_sqlite   = 0
    updated_firestore = 0
    skipped          = 0

    for item in items:
        name = item.get("name", "")  # e.g. products/canteen_KAR002.png
        if not name.startswith("products/"):
            continue

        # Extract filename without extension: canteen_KAR002
        filename  = os.path.splitext(os.path.basename(name))[0]
        url       = build_download_url(item)

        # Parse store and barcode from filename
        # Format: {store}_{barcode}  e.g. canteen_KAR002
        parts = filename.split("_", 1)
        if len(parts) < 2:
            print(f"   ⚠️  Can't parse: {filename}")
            skipped += 1
            continue

        store   = parts[0]   # canteen or cafestore
        barcode = parts[1]   # KAR002

        # ── Update SQLite ──
        cur.execute(
            "UPDATE products_cache SET image_url=? WHERE barcode=? AND store=?",
            (url, barcode, store))
        if cur.rowcount > 0:
            updated_sqlite += 1
            print(f"   ✅ [{store}] barcode={barcode} → URL restored")
        else:
            # Try without store filter
            cur.execute(
                "SELECT barcode, store, name FROM products_cache WHERE barcode=?",
                (barcode,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE products_cache SET image_url=? WHERE barcode=?",
                    (url, barcode))
                updated_sqlite += 1
                print(f"   ✅ [{row['store']}] {row['name']} barcode={barcode} → URL restored")
            else:
                print(f"   ⚠️  No product found for barcode={barcode} store={store}")
                skipped += 1

        # ── Update Firestore ──
        try:
            doc_id = f"{store}_{barcode}"
            existing = db._get_doc("products", doc_id)
            if existing:
                existing["image_url"] = url
                db._set_doc("products", doc_id, existing)
                updated_firestore += 1
        except Exception as e:
            print(f"   ⚠️  Firestore update error for {filename}: {e}")

    conn.commit()
    conn.close()

    print(f"\n{'='*50}")
    print(f"✅ SQLite updated:    {updated_sqlite} product(s)")
    print(f"✅ Firestore updated: {updated_firestore} product(s)")
    print(f"⚠️  Skipped:          {skipped}")
    print(f"{'='*50}")
    print("\nDone! All image URLs have been restored.")
    print("Your Android app should now show all product images.")


if __name__ == "__main__":
    main()