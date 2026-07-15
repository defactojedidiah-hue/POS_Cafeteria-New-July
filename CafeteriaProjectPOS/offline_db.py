import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path("offline_cache.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_local_db() -> None:
    with get_conn() as conn:
        cur = conn.cursor()

        # ── Transactions ──
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions_local (
                txn_id TEXT PRIMARY KEY,
                dt TEXT NOT NULL,
                total REAL NOT NULL,
                method TEXT NOT NULL,
                cash REAL DEFAULT 0,
                change_amount REAL DEFAULT 0,
                customer_name TEXT DEFAULT '',
                department TEXT DEFAULT '',
                buyer_type TEXT DEFAULT '',
                store TEXT NOT NULL DEFAULT 'cafestore',
                sync_status TEXT NOT NULL DEFAULT 'pending',
                sync_error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                synced_at TEXT DEFAULT ''
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transaction_items_local (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_id TEXT NOT NULL,
                barcode TEXT NOT NULL,
                name TEXT NOT NULL,
                category TEXT DEFAULT '',
                price REAL NOT NULL,
                qty INTEGER NOT NULL,
                line_total REAL NOT NULL,
                FOREIGN KEY (txn_id) REFERENCES transactions_local(txn_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS stock_adjustments_local (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txn_id TEXT NOT NULL,
                barcode TEXT NOT NULL,
                qty_change INTEGER NOT NULL,
                store TEXT NOT NULL DEFAULT 'cafestore',
                sync_status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)

        # ── Product cache (for offline barcode scan) ──────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products_cache (
                barcode TEXT NOT NULL,
                store   TEXT NOT NULL DEFAULT 'cafestore',
                name    TEXT NOT NULL,
                category TEXT DEFAULT '',
                price   REAL NOT NULL DEFAULT 0,
                stock   INTEGER NOT NULL DEFAULT 0,
                is_daily INTEGER NOT NULL DEFAULT 0,
                date_added TEXT DEFAULT '',
                image_url  TEXT DEFAULT '',
                cached_at  TEXT NOT NULL,
                PRIMARY KEY (barcode, store)
            )
        """)

        # ── Migrations for older db files ──
        cols = {row['name'] for row in cur.execute("PRAGMA table_info(transactions_local)").fetchall()}
        if 'store'      not in cols: cur.execute("ALTER TABLE transactions_local ADD COLUMN store TEXT NOT NULL DEFAULT 'cafestore'")
        if 'buyer_type' not in cols: cur.execute("ALTER TABLE transactions_local ADD COLUMN buyer_type TEXT DEFAULT ''")

        cols = {row['name'] for row in cur.execute("PRAGMA table_info(stock_adjustments_local)").fetchall()}
        if 'store' not in cols: cur.execute("ALTER TABLE stock_adjustments_local ADD COLUMN store TEXT NOT NULL DEFAULT 'cafestore'")

        # ── Migration: add image_url to products_cache if missing ──
        prod_cols = {row['name'] for row in cur.execute("PRAGMA table_info(products_cache)").fetchall()}
        if 'image_url' not in prod_cols:
            cur.execute("ALTER TABLE products_cache ADD COLUMN image_url TEXT DEFAULT ''")

        # Indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_sync ON transactions_local(sync_status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_txn         ON transaction_items_local(txn_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_adj_sync    ON stock_adjustments_local(sync_status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_products_store    ON products_cache(store)")


# ════════════════════════════════════════════════════════════
#  PRODUCT CACHE
# ════════════════════════════════════════════════════════════
def save_products_cache(rows: list, store: str = 'cafestore') -> None:
    """
    rows = list of tuples:
      (barcode, name, category, price, stock, is_daily, date_added)
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.cursor()
        # clear old cache for this store
        cur.execute("DELETE FROM products_cache WHERE store = ?", (store,))
        for row in rows:
            barcode    = str(row[0])
            name       = str(row[1])
            category   = str(row[2])
            price      = float(row[3])
            stock      = int(row[4])
            is_daily   = int(row[5]) if len(row) > 5 else 0
            date_added = str(row[6]) if len(row) > 6 else ""
            image_url  = str(row[7]) if len(row) > 7 else ""
            cur.execute("""
                INSERT OR REPLACE INTO products_cache
                    (barcode, store, name, category, price, stock, is_daily, date_added, image_url, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (barcode, store, name, category, price, stock, is_daily, date_added, image_url, now_str))


def get_cached_products(store: str = 'cafestore') -> list:
    """Returns list of tuples: (barcode, name, category, price, stock, is_daily, date_added, image_url)"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT barcode, name, category, price, stock, is_daily, date_added, image_url
            FROM products_cache
            WHERE store = ?
            ORDER BY name ASC
        """, (store,))
        return [(r['barcode'], r['name'], r['category'],
                 float(r['price']), int(r['stock']),
                 int(r['is_daily']), r['date_added'],
                 r['image_url'] if r['image_url'] else "") for r in cur.fetchall()]


def update_product_stock_in_cache(barcode: str, store: str, new_stock: int) -> None:
    """
    Directly update the stock of ONE product in the local SQLite cache.
    Called immediately after a Firestore stock deduction so the cache is
    always accurate — avoids the Firestore query propagation race condition.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE products_cache
               SET stock = ?, cached_at = ?
             WHERE barcode = ? AND store = ?
        """, (max(0, int(new_stock)),
              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              barcode, store))


def get_cached_product_by_barcode(barcode: str, store: str = 'cafestore'):
    """Returns a single product dict or None."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT barcode, name, category, price, stock, is_daily, date_added
            FROM products_cache
            WHERE barcode = ? AND store = ?
        """, (barcode, store))
        row = cur.fetchone()
        if row:
            return {"barcode": row['barcode'], "name": row['name'],
                    "category": row['category'], "price": float(row['price']),
                    "stock": int(row['stock'])}
        return None


# ════════════════════════════════════════════════════════════
#  TRANSACTIONS
# ════════════════════════════════════════════════════════════
def save_transaction_local(
    txn_id: str, dt: str, total: float, method: str,
    cash: float, change: float, customer_name: str,
    department: str, buyer_type: str, cart: list,
    store: str = 'cafestore') -> None:

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO transactions_local (
                txn_id, dt, total, method, cash, change_amount,
                customer_name, department, buyer_type, store,
                sync_status, sync_error, created_at, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '', ?, '')
        """, (txn_id, dt, total, method, cash, change,
              customer_name, department, buyer_type, store, now_str))

        cur.execute("DELETE FROM transaction_items_local  WHERE txn_id = ?", (txn_id,))
        cur.execute("DELETE FROM stock_adjustments_local WHERE txn_id = ?", (txn_id,))

        for item in cart:
            barcode    = str(item.get("barcode","")).strip()
            name       = str(item.get("name","")).strip()
            category   = str(item.get("category","")).strip()
            price      = float(item.get("price",0))
            qty        = int(item.get("qty",0))
            line_total = price * qty
            cur.execute("""
                INSERT INTO transaction_items_local
                    (txn_id, barcode, name, category, price, qty, line_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (txn_id, barcode, name, category, price, qty, line_total))
            cur.execute("""
                INSERT INTO stock_adjustments_local
                    (txn_id, barcode, qty_change, store, sync_status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
            """, (txn_id, barcode, -qty, store, now_str))


def get_pending_transactions() -> list:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM transactions_local
            WHERE sync_status IN ('pending', 'failed')
            ORDER BY created_at ASC
        """)
        txns = [dict(r) for r in cur.fetchall()]
        for txn in txns:
            cur.execute("""
                SELECT barcode, name, category, price, qty, line_total
                FROM transaction_items_local WHERE txn_id = ? ORDER BY id ASC
            """, (txn["txn_id"],))
            txn["items"] = [dict(r) for r in cur.fetchall()]
        return txns


def mark_transaction_synced(txn_id: str) -> None:
    synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE transactions_local SET sync_status='synced',sync_error='',synced_at=? WHERE txn_id=?",
                    (synced_at, txn_id))
        cur.execute("UPDATE stock_adjustments_local SET sync_status='synced' WHERE txn_id=?", (txn_id,))


def mark_transaction_failed(txn_id: str, error_message: str) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE transactions_local SET sync_status='failed',sync_error=? WHERE txn_id=?",
                    (error_message[:300], txn_id))


def get_pending_count() -> int:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM transactions_local WHERE sync_status IN ('pending','failed')")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def get_all_local_transactions(store: str = 'cafestore') -> list:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM transactions_local WHERE store=? ORDER BY dt DESC", (store,))
        return [dict(r) for r in cur.fetchall()]


def get_local_customer_names(store: str = 'cafestore') -> list:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT customer_name FROM transactions_local
            WHERE store=? AND TRIM(customer_name) != ''
            ORDER BY customer_name COLLATE NOCASE ASC
        """, (store,))
        return [str(r[0]) for r in cur.fetchall() if r[0]]


def get_local_transaction_items(txn_id: str) -> list:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT barcode, name, category, price, qty, line_total
            FROM transaction_items_local WHERE txn_id=? ORDER BY id ASC
        """, (txn_id,))
        return [dict(r) for r in cur.fetchall()]


# ════════════════════════════════════════════════════════════
#  LOYALTY CARD / COOP MEMBER  — local SQLite cache
# ════════════════════════════════════════════════════════════
def _ensure_loyalty_table():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS loyalty_members (
                card_barcode TEXT PRIMARY KEY,
                member_id    TEXT NOT NULL,
                name         TEXT NOT NULL,
                department   TEXT NOT NULL DEFAULT '',
                store        TEXT NOT NULL DEFAULT 'cafestore',
                registered_at TEXT NOT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_loyalty_store ON loyalty_members(store)")


def save_loyalty_member_local(member_id: str, name: str, department: str,
                               card_barcode: str, store: str = 'cafestore') -> None:
    _ensure_loyalty_table()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO loyalty_members
                (card_barcode, member_id, name, department, store, registered_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (card_barcode, member_id, name, department, store, now_str))


def cache_loyalty_members(members: list, store: str = 'cafestore') -> None:
    """Replace all cached members for this store."""
    _ensure_loyalty_table()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM loyalty_members WHERE store = ?", (store,))
        for m in members:
            cur.execute("""
                INSERT OR REPLACE INTO loyalty_members
                    (card_barcode, member_id, name, department, store, registered_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (m["card_barcode"], m["member_id"], m["name"],
                  m["department"], store, now_str))


def get_cached_loyalty_members(store: str = 'cafestore') -> list:
    _ensure_loyalty_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT card_barcode, member_id, name, department
            FROM loyalty_members WHERE store = ?
            ORDER BY name ASC
        """, (store,))
        return [{"card_barcode": r[0], "member_id": r[1],
                 "name": r[2], "department": r[3]} for r in cur.fetchall()]


def get_loyalty_member_by_card_local(card_barcode: str) -> dict:
    _ensure_loyalty_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT card_barcode, member_id, name, department
            FROM loyalty_members WHERE card_barcode = ?
        """, (card_barcode,))
        row = cur.fetchone()
        if row:
            return {"card_barcode": row[0], "member_id": row[1],
                    "name": row[2], "department": row[3]}
        return None


def delete_loyalty_member_local(card_barcode: str) -> None:
    _ensure_loyalty_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM loyalty_members WHERE card_barcode = ?", (card_barcode,))


# ════════════════════════════════════════════════════════════
#  TEACHER REGISTRY  — local SQLite cache
# ════════════════════════════════════════════════════════════
def _ensure_teacher_table():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teachers_registry (
                teacher_id    TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                department    TEXT NOT NULL DEFAULT '',
                store         TEXT NOT NULL DEFAULT 'cafestore',
                registered_at TEXT NOT NULL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_teacher_name  ON teachers_registry(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_teacher_store ON teachers_registry(store)")


def save_teacher_local(teacher_id: str, name: str, department: str,
                        store: str = 'cafestore') -> None:
    _ensure_teacher_table()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO teachers_registry
                (teacher_id, name, department, store, registered_at)
            VALUES (?, ?, ?, ?, ?)
        """, (teacher_id, name, department, store, now_str))


def get_teacher_by_name(name: str) -> dict:
    _ensure_teacher_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT teacher_id, name, department
            FROM teachers_registry
            WHERE LOWER(name) = LOWER(?)
        """, (name.strip(),))
        row = cur.fetchone()
        if row:
            return {"teacher_id": row[0], "name": row[1], "department": row[2]}
        return None


def cache_teachers(teachers: list, store: str = 'cafestore') -> None:
    _ensure_teacher_table()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM teachers_registry WHERE store = ?", (store,))
        for t in teachers:
            cur.execute("""
                INSERT OR REPLACE INTO teachers_registry
                    (teacher_id, name, department, store, registered_at)
                VALUES (?, ?, ?, ?, ?)
            """, (t["teacher_id"], t["name"], t["department"], store, now_str))


def get_cached_teachers(store: str = 'cafestore') -> list:
    _ensure_teacher_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT teacher_id, name, department
            FROM teachers_registry WHERE store = ?
            ORDER BY name ASC
        """, (store,))
        return [{"teacher_id": r[0], "name": r[1], "department": r[2]}
                for r in cur.fetchall()]

# ════════════════════════════════════════════════════════════
#  SALARY DEDUCTIONS — local SQLite
# ════════════════════════════════════════════════════════════
def _ensure_deductions_table():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS salary_deductions (
                doc_id     TEXT PRIMARY KEY,
                faculty    TEXT NOT NULL,
                department TEXT DEFAULT '',
                amount     REAL NOT NULL DEFAULT 0,
                note       TEXT DEFAULT '',
                datetime   TEXT NOT NULL
            )
        """)


def save_deduction_local(doc_id: str, faculty: str, department: str,
                          amount: float, note: str, dt: str) -> None:
    _ensure_deductions_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO salary_deductions
                (doc_id, faculty, department, amount, note, datetime)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (doc_id, faculty, department, float(amount), note, dt))


def get_all_deductions_local() -> list:
    _ensure_deductions_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT doc_id, faculty, department, amount, note, datetime
            FROM salary_deductions ORDER BY datetime DESC
        """)
        return [{"doc_id":r[0],"faculty":r[1],"department":r[2],
                 "amount":float(r[3]),"note":r[4],"datetime":r[5]}
                for r in cur.fetchall()]


def get_deductions_by_faculty_local(faculty: str) -> list:
    _ensure_deductions_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT doc_id, faculty, department, amount, note, datetime
            FROM salary_deductions WHERE faculty=? ORDER BY datetime DESC
        """, (faculty,))
        return [{"doc_id":r[0],"faculty":r[1],"department":r[2],
                 "amount":float(r[3]),"note":r[4],"datetime":r[5]}
                for r in cur.fetchall()]


def get_total_deducted_local(faculty: str) -> float:
    _ensure_deductions_table()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT SUM(amount) FROM salary_deductions WHERE faculty=?", (faculty,))
        result = cur.fetchone()[0]
        return round(float(result) if result else 0.0, 2)