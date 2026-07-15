"""
fix_duplicates.py — Run this ONCE to clean up duplicate transaction items
Place this file in your project folder and run it.
"""
import sqlite3

conn = sqlite3.connect("offline_cache.db")
cur  = conn.cursor()

# ── Check duplicates before fix ──
cur.execute("""
    SELECT txn_id, name, COUNT(*) as cnt
    FROM transaction_items_local
    GROUP BY txn_id, name
    HAVING cnt > 1
""")
dupes = cur.fetchall()
print(f"Found {len(dupes)} duplicate item(s):")
for d in dupes:
    print(f"  txn_id={d[0]}  item={d[1]}  count={d[2]}")

if not dupes:
    print("No duplicates found! Database is clean.")
    conn.close()
    exit()

# ── Fix: keep only the latest row for each txn_id + name combo ──
cur.execute("""
    DELETE FROM transaction_items_local
    WHERE rowid NOT IN (
        SELECT MAX(rowid)
        FROM transaction_items_local
        GROUP BY txn_id, name
    )
""")
deleted = cur.rowcount
conn.commit()

# ── Verify ──
cur.execute("SELECT COUNT(*) FROM transaction_items_local")
total = cur.fetchone()[0]
conn.close()

print(f"\n✅ Deleted {deleted} duplicate rows.")
print(f"   Remaining transaction items: {total}")
print("\nDone! Your sales report should now show correct quantities.")