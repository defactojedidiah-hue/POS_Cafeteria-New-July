"""
rename_txn_ids.py
Renames KAR-xxxxxxxx → CAN-xxxxxxxx in SQLite.
Run ONCE on the Canteen PC only.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "offline_cache.db")

def rename():
    if not os.path.exists(DB_PATH):
        print("❌ offline_cache.db not found!")
        return

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    print("🔄 Finding KAR- transactions...\n")

    # ── Show KAR- transactions before fix ──
    cur.execute("SELECT txn_id FROM transactions_local WHERE txn_id LIKE 'KAR-%'")
    kar_rows = [r[0] for r in cur.fetchall()]
    print(f"Found {len(kar_rows)} KAR- transactions to rename.\n")

    if not kar_rows:
        print("✅ No KAR- transactions found. Nothing to rename!")
        conn.close()
        input("\nPress Enter to close...")
        return

    # ── Rename in transactions_local ──
    renamed = 0
    for old_id in kar_rows:
        new_id = old_id.replace("KAR-", "CAN-", 1)
        try:
            # Update transactions_local
            cur.execute("UPDATE transactions_local SET txn_id=? WHERE txn_id=?",
                        (new_id, old_id))
            # Update transaction_items_local
            cur.execute("UPDATE transaction_items_local SET txn_id=? WHERE txn_id=?",
                        (new_id, old_id))
            # Update stock_adjustments_local
            try:
                cur.execute("UPDATE stock_adjustments_local SET txn_id=? WHERE txn_id=?",
                            (new_id, old_id))
            except Exception:
                pass
            renamed += 1
            print(f"  ✅ {old_id} → {new_id}")
        except Exception as e:
            print(f"  ⚠️ Failed {old_id}: {e}")

    conn.commit()
    conn.close()

    print(f"\n✅ Renamed {renamed} transactions successfully!")
    print("👉 Now click ☁️ Backup → Backup Database to push to Firestore.\n")

if __name__ == "__main__":
    rename()
    input("Press Enter to close...")