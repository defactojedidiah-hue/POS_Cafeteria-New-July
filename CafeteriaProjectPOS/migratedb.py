"""
migrate_db.py — Run this ONCE to copy data from old offline_cache.db
to new separate database files.

Run: python migrate_db.py
"""
import sqlite3
import os
import shutil
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OLD_DB     = os.path.join(BASE_DIR, "offline_cache.db")
STORE_DB   = os.path.join(BASE_DIR, "offline_cache_cafestore.db")
CANTEEN_DB = os.path.join(BASE_DIR, "offline_cache_canteen.db")

def migrate():
    if not os.path.exists(OLD_DB):
        print("❌ offline_cache.db not found! Nothing to migrate.")
        return

    print(f"✅ Found old database: {OLD_DB}")
    print("Starting migration...\n")

    # ── Connect to old DB ──
    old_conn = sqlite3.connect(OLD_DB)
    old_conn.row_factory = sqlite3.Row
    old_cur  = old_conn.cursor()

    # ── Import offline_db to initialize new DB files ──
    import offline_db

    # ── 1. Migrate transactions ──
    print("📦 Migrating transactions...")
    old_cur.execute("SELECT * FROM transactions_local")
    txns = old_cur.fetchall()

    store_txns   = [dict(r) for r in txns if dict(r).get("store","cafestore") == "cafestore"]
    canteen_txns = [dict(r) for r in txns if dict(r).get("store","") == "canteen"]
    print(f"   Store transactions:   {len(store_txns)}")
    print(f"   Canteen transactions: {len(canteen_txns)}")

    # ── 2. Migrate transaction items ──
    old_cur.execute("SELECT * FROM transaction_items_local")
    items = [dict(r) for r in old_cur.fetchall()]
    store_txn_ids   = {t["txn_id"] for t in store_txns}
    canteen_txn_ids = {t["txn_id"] for t in canteen_txns}
    store_items     = [i for i in items if i.get("txn_id","") in store_txn_ids]
    canteen_items   = [i for i in items if i.get("txn_id","") in canteen_txn_ids]
    print(f"   Store items:   {len(store_items)}")
    print(f"   Canteen items: {len(canteen_items)}")

    # ── 3. Migrate products ──
    old_cur.execute("SELECT * FROM products_cache")
    prods = [dict(r) for r in old_cur.fetchall()]
    store_prods   = [p for p in prods if p.get("store","cafestore") == "cafestore"]
    canteen_prods = [p for p in prods if p.get("store","") == "canteen"]
    print(f"   Store products:   {len(store_prods)}")
    print(f"   Canteen products: {len(canteen_prods)}")

    # ── 4. Migrate loyalty members ──
    old_cur.execute("SELECT * FROM loyalty_members")
    members = [dict(r) for r in old_cur.fetchall()]
    print(f"   Members: {len(members)}")

    # ── 5. Migrate salary deductions ──
    try:
        old_cur.execute("SELECT * FROM salary_deductions")
        deductions = [dict(r) for r in old_cur.fetchall()]
    except Exception:
        deductions = []
    print(f"   Salary deductions: {len(deductions)}")

    old_conn.close()

    # ── Write to STORE DB ──
    print("\n💾 Writing to offline_cache_cafestore.db...")
    os.environ["STOCKFLOW_STORE"] = "cafestore"
    # Force reload of DB_PATH
    import importlib
    importlib.reload(offline_db)

    store_conn = sqlite3.connect(STORE_DB)
    store_conn.row_factory = sqlite3.Row
    sc = store_conn.cursor()

    # Copy transactions
    for t in store_txns:
        try:
            sc.execute("""INSERT OR REPLACE INTO transactions_local
                (txn_id, dt, total, method, cash, change_amount,
                 customer_name, department, buyer_type, store, synced)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (t.get("txn_id",""), t.get("dt",""), t.get("total",0),
                 t.get("method",""), t.get("cash",0), t.get("change_amount",0),
                 t.get("customer_name",""), t.get("department",""),
                 t.get("buyer_type",""), t.get("store","cafestore"),
                 t.get("synced",0)))
        except Exception as e:
            print(f"   ⚠ Txn error: {e}")

    # Copy items
    for i in store_items:
        try:
            sc.execute("""INSERT OR REPLACE INTO transaction_items_local
                (txn_id, barcode, name, category, price, qty)
                VALUES (?,?,?,?,?,?)""",
                (i.get("txn_id",""), i.get("barcode",""), i.get("name",""),
                 i.get("category",""), i.get("price",0), i.get("qty",0)))
        except Exception as e:
            print(f"   ⚠ Item error: {e}")

    # Copy products
    for p in store_prods:
        try:
            sc.execute("""INSERT OR REPLACE INTO products_cache
                (barcode, store, name, category, price, stock,
                 is_daily, date_added, image_url, cached_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (p.get("barcode",""), "cafestore", p.get("name",""),
                 p.get("category",""), p.get("price",0), p.get("stock",0),
                 p.get("is_daily",0), p.get("date_added",""),
                 p.get("image_url",""), p.get("cached_at","")))
        except Exception as e:
            print(f"   ⚠ Product error: {e}")

    # Copy members
    for m in members:
        try:
            sc.execute("""INSERT OR REPLACE INTO loyalty_members
                (member_id, name, department, card_barcode, store)
                VALUES (?,?,?,?,?)""",
                (m.get("member_id",""), m.get("name",""),
                 m.get("department",""), m.get("card_barcode",""),
                 m.get("store","coop")))
        except Exception as e:
            print(f"   ⚠ Member error: {e}")

    # Copy deductions
    for d in deductions:
        try:
            sc.execute("""INSERT OR REPLACE INTO salary_deductions
                (id, faculty_name, department, amount, date, note, store)
                VALUES (?,?,?,?,?,?,?)""",
                (d.get("id",""), d.get("faculty_name",""),
                 d.get("department",""), d.get("amount",0),
                 d.get("date",""), d.get("note",""),
                 d.get("store","cafestore")))
        except Exception as e:
            pass  # table might not exist

    store_conn.commit()
    store_conn.close()
    print(f"   ✅ Store DB done!")

    # ── Write to CANTEEN DB ──
    print("\n💾 Writing to offline_cache_canteen.db...")
    canteen_conn = sqlite3.connect(CANTEEN_DB)
    cc = canteen_conn.cursor()

    for t in canteen_txns:
        try:
            cc.execute("""INSERT OR REPLACE INTO transactions_local
                (txn_id, dt, total, method, cash, change_amount,
                 customer_name, department, buyer_type, store, synced)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (t.get("txn_id",""), t.get("dt",""), t.get("total",0),
                 t.get("method",""), t.get("cash",0), t.get("change_amount",0),
                 t.get("customer_name",""), t.get("department",""),
                 t.get("buyer_type",""), t.get("store","canteen"),
                 t.get("synced",0)))
        except Exception as e:
            print(f"   ⚠ Txn error: {e}")

    for i in canteen_items:
        try:
            cc.execute("""INSERT OR REPLACE INTO transaction_items_local
                (txn_id, barcode, name, category, price, qty)
                VALUES (?,?,?,?,?,?)""",
                (i.get("txn_id",""), i.get("barcode",""), i.get("name",""),
                 i.get("category",""), i.get("price",0), i.get("qty",0)))
        except Exception as e:
            print(f"   ⚠ Item error: {e}")

    for p in canteen_prods:
        try:
            cc.execute("""INSERT OR REPLACE INTO products_cache
                (barcode, store, name, category, price, stock,
                 is_daily, date_added, image_url, cached_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (p.get("barcode",""), "canteen", p.get("name",""),
                 p.get("category",""), p.get("price",0), p.get("stock",0),
                 p.get("is_daily",0), p.get("date_added",""),
                 p.get("image_url",""), p.get("cached_at","")))
        except Exception as e:
            print(f"   ⚠ Product error: {e}")

    for m in members:
        try:
            cc.execute("""INSERT OR REPLACE INTO loyalty_members
                (member_id, name, department, card_barcode, store)
                VALUES (?,?,?,?,?)""",
                (m.get("member_id",""), m.get("name",""),
                 m.get("department",""), m.get("card_barcode",""),
                 m.get("store","coop")))
        except Exception as e:
            print(f"   ⚠ Member error: {e}")

    canteen_conn.commit()
    canteen_conn.close()
    print(f"   ✅ Canteen DB done!")

    print("\n" + "="*50)
    print("✅ MIGRATION COMPLETE!")
    print(f"   Store transactions:   {len(store_txns)}")
    print(f"   Canteen transactions: {len(canteen_txns)}")
    print(f"   Store products:       {len(store_prods)}")
    print(f"   Canteen products:     {len(canteen_prods)}")
    print(f"   Members:              {len(members)}")
    print("="*50)
    print("\nYou can now open Store Inventory and Canteen Inventory!")
    print("Old offline_cache.db is kept as backup — safe to delete later.")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    migrate()