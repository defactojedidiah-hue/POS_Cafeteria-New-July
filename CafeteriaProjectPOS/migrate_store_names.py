"""
migrate_store_names.py
Run this ONCE on each PC to update old store names in SQLite.

Store PC:    cafeteria  → cafestore
Canteen PC:  karinderia → canteen

Run: python migrate_store_names.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "offline_cache.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print("❌ offline_cache.db not found! Nothing to migrate.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    print("🔄 Starting migration...")

    # ── transactions_local ──
    try:
        cur.execute("UPDATE transactions_local SET store='cafestore' WHERE store='cafeteria'")
        cur.execute("UPDATE transactions_local SET store='canteen'   WHERE store='karinderia'")
        print(f"  ✅ transactions_local updated: {conn.total_changes} rows")
    except Exception as e:
        print(f"  ⚠️ transactions_local: {e}")

    # ── products_cache ──
    try:
        cur.execute("UPDATE products_cache SET store='cafestore' WHERE store='cafeteria'")
        cur.execute("UPDATE products_cache SET store='canteen'   WHERE store='karinderia'")
        print(f"  ✅ products_cache updated")
    except Exception as e:
        print(f"  ⚠️ products_cache: {e}")

    # ── loyalty_members_cache ──
    try:
        cur.execute("UPDATE loyalty_members_cache SET store='cafestore' WHERE store='cafeteria'")
        cur.execute("UPDATE loyalty_members_cache SET store='canteen'   WHERE store='karinderia'")
        print(f"  ✅ loyalty_members_cache updated")
    except Exception as e:
        print(f"  ⚠️ loyalty_members_cache: {e}")

    # ── stock_adjustments_local ──
    try:
        cur.execute("UPDATE stock_adjustments_local SET store='cafestore' WHERE store='cafeteria'")
        cur.execute("UPDATE stock_adjustments_local SET store='canteen'   WHERE store='karinderia'")
        print(f"  ✅ stock_adjustments_local updated")
    except Exception as e:
        print(f"  ⚠️ stock_adjustments_local: {e}")

    # ── salary_deductions ──
    try:
        cur.execute("UPDATE salary_deductions SET store='cafestore' WHERE store='cafeteria'")
        cur.execute("UPDATE salary_deductions SET store='canteen'   WHERE store='karinderia'")
        print(f"  ✅ salary_deductions updated")
    except Exception as e:
        print(f"  ⚠️ salary_deductions: {e}")

    conn.commit()
    conn.close()

    print("\n✅ Migration complete! Store names updated successfully.")
    print("👉 Now open the Inventory and click ☁️ Backup → Backup Database")
    print("   to push updated data back to Firestore.\n")

if __name__ == "__main__":
    migrate()
    input("Press Enter to close...")