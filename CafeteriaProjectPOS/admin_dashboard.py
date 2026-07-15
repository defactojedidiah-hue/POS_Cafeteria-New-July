import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from collections import defaultdict
import database as db
import offline_db
import threading
import os
import json

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

BG_DARK    = "#F5F5F5"
BG_PANEL   = "#FFFFFF"
BG_ROW     = "#F0F4F8"
BG_ROW_ALT = "#E8EEF4"
BG_SIDEBAR = "#E3F2FD"
HEADER_RED = "#1565C0"
ACCENT_RED = "#1976D2"
TEXT_WHITE = "#1A1A2E"
TEXT_GREY  = "#546E7A"
COL_HDR    = "#BBDEFB"
BTN_BLUE   = "#1565C0"
GREEN      = "#2E7D32"
ORANGE     = "#FF6D00"
SIDEBAR_W  = 80


class AdminDashboard(ctk.CTk):
    def __init__(self, login_window=None):
        super().__init__()
        self.login_window = login_window
        self.title("Cafe Store — Admin Dashboard")
        self.attributes("-fullscreen", True)
        self.state("zoomed")
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(fg_color="#F5F7FA")
        self.protocol("WM_DELETE_WINDOW", self._logout)
        db.init_db()
        self._build_header()
        self._build_layout()
        self._nav("overview")
        self._bind_fkeys()
        # ── Auto-sync from Firestore on startup ──
        threading.Thread(target=self._auto_sync_on_startup, daemon=True).start()

    # ── HEADER ──────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="#1565C0", height=80, corner_radius=0)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        base = os.path.dirname(os.path.abspath(__file__))

        fpath = os.path.join(base, "isufstlogo.png")
        try:
            if PIL_OK and os.path.exists(fpath):
                img   = Image.open(fpath).resize((62, 62), Image.LANCZOS)
                photo = ctk.CTkImage(light_image=img, dark_image=img, size=(62, 62))
                ctk.CTkLabel(hdr, image=photo, text="",
                             fg_color="transparent").pack(side="left", padx=(14, 6), pady=8)
        except Exception:
            pass

        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.pack(side="right", padx=(0, 10))
        ctk.CTkButton(right, text="✕  Exit", width=90, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._logout).pack(side="right", padx=(8, 0))
        self.clock_lbl = ctk.CTkLabel(right, text="",
                                       font=ctk.CTkFont(size=12, weight="bold"),
                                       text_color="white", justify="right")
        self.clock_lbl.pack(side="right", padx=(0, 8))
        self._tick()
        fpath2 = os.path.join(base, "ccslogo.png")
        try:
            if PIL_OK and os.path.exists(fpath2):
                img   = Image.open(fpath2).resize((62, 62), Image.LANCZOS)
                photo = ctk.CTkImage(light_image=img, dark_image=img, size=(62, 62))
                ctk.CTkLabel(right, image=photo, text="",
                             fg_color="transparent").pack(side="right", padx=(0, 6), pady=8)
        except Exception:
            pass

        center = ctk.CTkFrame(hdr, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")
        self.hdr_title = ctk.CTkLabel(
            center, text="ADMIN DASHBOARD",
            font=ctk.CTkFont(family="Georgia", size=24, weight="bold"),
            text_color="white")
        self.hdr_title.pack()
        ctk.CTkLabel(center, text="Admin",
                     font=ctk.CTkFont(family="Georgia", size=12),
                     text_color="#BBDEFB").pack()

    def _tick(self):
        now = datetime.now()
        self.clock_lbl.configure(
            text=now.strftime("%a, %b %d, %Y") + "\n" + now.strftime("%I:%M %p"))
        self.after(1000, self._tick)

    # ── AUTO-SYNC ON STARTUP ─────────────────────────────────
    def _auto_sync_on_startup(self):
        """Pull latest data from Firestore into SQLite silently on startup."""
        if not db.has_internet():
            print("[AdminSync] Offline — skipping auto-sync.")
            return
        print("[AdminSync] Online — syncing from Firestore...")
        try:
            import sqlite3 as _sql
            conn = _sql.connect(str(offline_db.DB_PATH))
            conn.row_factory = _sql.Row
            cur  = conn.cursor()
            for store in ["cafestore", "canteen"]:
                try:
                    results = db._query("transactions", filters=[["store", "EQUAL", store]])
                    for r in results:
                        d = db._parse_doc(r)
                        txn_id = d.get("txn_id", "")
                        if not txn_id: continue
                        cur.execute("""
                            INSERT OR REPLACE INTO transactions_local
                                (txn_id, dt, total, method, cash, change_amount,
                                 customer_name, department, buyer_type,
                                 store, sync_status, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'synced', ?)
                        """, (txn_id, d.get("datetime",""), float(d.get("total",0)),
                              d.get("payment_method",""), float(d.get("cash_given",0)),
                              float(d.get("change_given",0)), d.get("customer_name",""),
                              d.get("department",""), d.get("buyer_type",""),
                              store, d.get("datetime",""),))
                except Exception as e:
                    print(f"[AdminSync] Transactions {store}: {e}")
            try:
                for r in db._query("transaction_items"):
                    d = db._parse_doc(r)
                    txn_id = d.get("txn_id","")
                    if not txn_id: continue
                    cur.execute("""INSERT OR IGNORE INTO transaction_items_local
                        (txn_id, barcode, name, category, price, qty, line_total)
                        VALUES (?,?,?,?,?,?,?)""",
                        (txn_id, d.get("barcode",""), d.get("name",""),
                         d.get("category",""), float(d.get("price",0)),
                         int(d.get("qty",0)),
                         float(d.get("price",0))*int(d.get("qty",0)),))
            except Exception as e:
                print(f"[AdminSync] Items: {e}")
            conn.commit(); conn.close()
            for store in ["cafestore","canteen"]:
                try:
                    prods = db.get_all_products(store=store)
                    if prods: offline_db.save_products_cache(prods, store)
                except Exception as e:
                    print(f"[AdminSync] Products {store}: {e}")
            for store in ["coop","cafestore","canteen"]:
                try:
                    results = db._query("loyalty_members", filters=[["store","EQUAL",store]])
                    members = [{"member_id":db._parse_doc(r).get("member_id",""),
                                "name":db._parse_doc(r).get("name",""),
                                "department":db._parse_doc(r).get("department",""),
                                "card_barcode":db._parse_doc(r).get("card_barcode","")}
                               for r in results]
                    if members: offline_db.cache_loyalty_members(members, store)
                except Exception as e:
                    print(f"[AdminSync] Loyalty {store}: {e}")
            print("[AdminSync] ✅ Auto-sync complete.")
            self.after(0, lambda: self._nav(getattr(self, "_current_nav", "overview")))
        except Exception as e:
            print(f"[AdminSync] Error: {e}")

    # ── LAYOUT ──────────────────────────────
    def _build_layout(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self._build_sidebar(body)
        self.content = ctk.CTkFrame(body, fg_color="#F5F7FA", corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

    # ── ASYNC HELPER ────────────────────────
    def _show_loading(self, text="Loading..."):
        for w in self.content.winfo_children():
            w.destroy()
        frame = ctk.CTkFrame(self.content, fg_color="#F5F7FA", corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text="⏳  " + text,
                     font=ctk.CTkFont(size=18), text_color="#333333"
                     ).grid(row=0, column=0)

    def _run_async(self, fetch_fn, render_fn, loading_text="Loading..."):
        self._show_loading(loading_text)
        def _bg():
            try:
                data = fetch_fn()
                self.after(0, lambda d=data: render_fn(d))
            except Exception as e:
                self.after(0, lambda: self._show_error(str(e)))
        threading.Thread(target=_bg, daemon=True).start()

    def _show_error(self, msg):
        for w in self.content.winfo_children():
            w.destroy()
        frame = ctk.CTkFrame(self.content, fg_color="#F5F7FA", corner_radius=0)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text="❌  Error: " + msg,
                     font=ctk.CTkFont(size=14), text_color="#1565C0"
                     ).grid(row=0, column=0)

    # ── SIDEBAR ─────────────────────────────
    def _build_sidebar(self, parent):
        self._sidebar_parent = parent
        sb = ctk.CTkFrame(parent, fg_color="#F0F7FF", width=SIDEBAR_W, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.pack_propagate(False)
        self.nav_btns = {}
        for key, icon, label in [
            ("overview", "📊", "Overview"),
            ("sales",    "💰", "Sales"),
            ("coop",     "⭐", "Members"),
            ("credits",  "👤", "Credits"),
            ("history",  "🕐", "History"),
        ]:
            f = ctk.CTkFrame(sb, fg_color="transparent", cursor="hand2",
                             width=SIDEBAR_W, height=64)
            f.pack(fill="x")
            f.pack_propagate(False)
            il = ctk.CTkLabel(f, text=icon, font=ctk.CTkFont(size=20), text_color="#333333")
            il.place(relx=0.5, rely=0.35, anchor="center")
            tl = ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=9, weight="bold"),
                               text_color="#333333")
            tl.place(relx=0.5, rely=0.75, anchor="center")
            for w in (f, il, tl):
                w.bind("<Button-1>", lambda e, k=key: self._nav(k))
            self.nav_btns[key] = (f, il, tl)


    def _highlight_nav(self, key):
        for k, (f, il, tl) in self.nav_btns.items():
            if k == key:
                f.configure(fg_color="#1976D2")
                il.configure(text_color="white")
                tl.configure(text_color="white")
            else:
                f.configure(fg_color="transparent")
                il.configure(text_color="#333333")
                tl.configure(text_color="#333333")

    def _nav(self, key):
        self._current_nav = key
        self._highlight_nav(key)
        for w in self.content.winfo_children():
            w.destroy()
        titles = {"overview":"ADMIN DASHBOARD","credits":"CREDIT MONITOR",
                  "history":"TRANSACTION HISTORY","sales":"SALES REPORT",
                  "coop":"COOP MEMBERS"}
        self.hdr_title.configure(text=titles.get(key, "ADMIN DASHBOARD"))
        if key == "overview":
            self._show_loading("Loading Overview...")
            def _ov():
                _s = "canteen" if "canteen" in getattr(self,"active_store",ctk.StringVar(value="Cafe Store")).get().lower() else "cafestore"
                sales = db.get_sales_report("month", store=_s)
                creds = db.get_credit_summary(store=_s)
                self.after(0, lambda: self._render_overview_data(sales, creds))
            threading.Thread(target=_ov, daemon=True).start()
        elif key == "credits":
            self._show_loading("Loading Credits...")
            def _cr():
                _s = "canteen" if "canteen" in getattr(self,"credit_store_var",ctk.StringVar()).get().lower() else "cafestore"
                data = db.get_credit_summary(store=_s)
                self.after(0, lambda d=data: self._render_credits_data(d))
            threading.Thread(target=_cr, daemon=True).start()
        elif key == "history":
            self._show_loading("Loading History...")
            def _hi():
                deds  = db.get_deductions()
                creds = db.get_credit_summary()
                self.after(0, lambda d=deds, c=creds: self._render_history_data(d, c))
            threading.Thread(target=_hi, daemon=True).start()
        elif key == "sales":
            self._show_sales()
        elif key == "coop":
            self._show_coop_members()

    # ════════════════════════════════════════
    #  OVERVIEW
    # ════════════════════════════════════════
    def _render_overview_data(self, sales_data, credit_sum):
        for w in self.content.winfo_children(): w.destroy()
        if not hasattr(self, "active_store"):
            self.active_store = ctk.StringVar(value="Cafe Store")

        page = ctk.CTkScrollableFrame(self.content, fg_color="#F5F7FA", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)

        ctk.CTkLabel(page, text="Overview",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#000000").pack(anchor="w", padx=24, pady=(18, 2))
        ctk.CTkLabel(page,
                     text=f"📅  Overview for: {datetime.now().strftime('%B %Y')}",
                     font=ctk.CTkFont(size=13),
                     text_color="#546E7A").pack(anchor="w", padx=24, pady=(0, 6))

        # ── Store selector tabs ──
        store_tabs = ctk.CTkFrame(page, fg_color="transparent")
        store_tabs.pack(anchor="center", padx=24, pady=(0, 14))

        ov_btns = {}
        def _set_ov_store(label, btns):
            self.active_store.set(label)
            for l2, b in btns.items():
                b.configure(fg_color="#1976D2" if l2==label else BTN_BLUE,
                            hover_color="#0D47A1" if l2==label else "#1976D2")
            self._nav("overview")

        _cur = self.active_store.get()
        for label in ["Cafe Store", "Cafeteria Canteen"]:
            is_active = (label == _cur)
            b = ctk.CTkButton(store_tabs, text=label, width=280, height=52,
                              fg_color="#1976D2" if is_active else BTN_BLUE,
                              hover_color="#0D47A1" if is_active else "#1976D2",
                              font=ctk.CTkFont(size=16, weight="bold"), corner_radius=10)
            b.pack(side="left", padx=(0, 12))
            ov_btns[label] = b
        for label, b in ov_btns.items():
            b.configure(command=lambda l=label, bts=ov_btns: _set_ov_store(l, bts))

        total_utang = sum(r[2] for r in credit_sum)

        # ── Active store banner ──
        cur_store = self.active_store.get()
        banner = ctk.CTkFrame(page, fg_color="#1565C0", corner_radius=10, height=44)
        banner.pack(fill="x", padx=24, pady=(0, 12))
        banner.pack_propagate(False)
        ctk.CTkLabel(banner,
                     text=f"📊  {cur_store} — Overview",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="white").place(relx=0.5, rely=0.5, anchor="center")
        # ONE shared grid container for all 4 boxes.
        # Row 0 = stat cards (Revenue | Total Utang)
        # Row 1 = detail cards (Departments | Top Utang)
        # Both rows share the same columnconfigure so edges align exactly.
        # ══════════════════════════════════════════════════════════════
        grid = ctk.CTkFrame(page, fg_color="transparent")
        grid.pack(fill="x", padx=24, pady=(0, 18))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        # ── ROW 0, COL 0: Monthly Revenue ──
        rev_card = ctk.CTkFrame(grid, fg_color="#FFFFFF", corner_radius=12,
                                border_width=2, border_color=ACCENT_RED)
        rev_card.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 8))
        ctk.CTkLabel(rev_card, text="  Monthly Revenue",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#333333").pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(rev_card, text="P" + "{:.2f}".format(sales_data["revenue"]),
                     font=ctk.CTkFont(size=30, weight="bold"),
                     text_color="#1565C0").pack(anchor="w", padx=18, pady=(0, 16))

        # ── ROW 0, COL 1: Total Utang ──
        utg_card = ctk.CTkFrame(grid, fg_color="#FFFFFF", corner_radius=12,
                                border_width=2, border_color="#7E57C2")
        utg_card.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 8))
        ctk.CTkLabel(utg_card, text="  Total Utang",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#333333").pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(utg_card, text="P" + "{:.2f}".format(total_utang),
                     font=ctk.CTkFont(size=30, weight="bold"),
                     text_color="#6A1B9A").pack(anchor="w", padx=18, pady=(0, 16))

        # Build dept totals
        dept_totals = defaultdict(float)
        dept_counts = defaultdict(int)
        for (name, dept, total, count) in credit_sum:
            key = dept.strip() if dept else "Other"
            dept_totals[key] += total
            dept_counts[key] += 1

        # ── ROW 1, COL 0: Departments ──
        left_f = ctk.CTkFrame(grid, fg_color="#FFFFFF", corner_radius=12,
                              border_width=2, border_color="#1565C0")
        left_f.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(0, 0))

        ctk.CTkLabel(left_f, text="Departments",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#000000").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(left_f, text="Total debt per department",
                     font=ctk.CTkFont(size=10), text_color="#333333"
                     ).pack(anchor="w", padx=16, pady=(0, 8))

        dh = ctk.CTkFrame(left_f, fg_color=COL_HDR, height=28, corner_radius=4)
        dh.pack(fill="x", padx=8)
        dh.pack_propagate(False)
        dh.columnconfigure(0, weight=1)
        ctk.CTkLabel(dh, text="DEPARTMENT", anchor="w",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#333333", fg_color="transparent"
                     ).grid(row=0, column=0, sticky="w", padx=(12, 4), pady=4)
        ctk.CTkLabel(dh, text="MEMBERS", width=80, anchor="center",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#333333", fg_color="transparent"
                     ).grid(row=0, column=1, padx=4, pady=4)
        ctk.CTkLabel(dh, text="TOTAL DEBT", width=110, anchor="center",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#333333", fg_color="transparent"
                     ).grid(row=0, column=2, padx=(4, 12), pady=4)

        if not dept_totals:
            ctk.CTkLabel(left_f, text="No credit records.",
                         font=ctk.CTkFont(size=13), text_color="#333333").pack(pady=16)
        else:
            for i, (dept, total) in enumerate(
                    sorted(dept_totals.items(), key=lambda x: x[1], reverse=True)):
                bg = '#FFFFFF' if i % 2 == 0 else '#F5F7FA'
                dr = ctk.CTkFrame(left_f, fg_color=bg, corner_radius=0, height=40)
                dr.pack(fill="x", padx=8)
                dr.pack_propagate(False)
                dr.columnconfigure(0, weight=1)
                ctk.CTkLabel(dr, text=dept, anchor="w",
                             font=ctk.CTkFont(size=13, weight="bold"),
                             text_color="#000000"
                             ).grid(row=0, column=0, sticky="w", padx=(12, 4))
                ctk.CTkLabel(dr, text=str(dept_counts[dept]), width=90, anchor="center",
                             font=ctk.CTkFont(size=12), text_color="#333333"
                             ).grid(row=0, column=1, padx=4)
                ctk.CTkLabel(dr, text="P" + "{:.2f}".format(total),
                             width=120, anchor="e",
                             font=ctk.CTkFont(size=13, weight="bold"),
                             text_color="#1565C0"
                             ).grid(row=0, column=2, padx=(4, 16))

        ctk.CTkFrame(left_f, fg_color="transparent", height=10).pack()

        # ── ROW 1, COL 1: Top Utang ──
        right_f = ctk.CTkFrame(grid, fg_color="#FFFFFF", corner_radius=12,
                               border_width=2, border_color="#7E57C2")
        right_f.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(0, 0))

        ctk.CTkLabel(right_f, text="Top Utang",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#000000").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(right_f, text="Highest individual remaining balance",
                     font=ctk.CTkFont(size=10), text_color="#333333"
                     ).pack(anchor="w", padx=16, pady=(0, 8))

        if not credit_sum:
            ctk.CTkLabel(right_f, text="No records.",
                         font=ctk.CTkFont(size=13), text_color="#333333").pack(pady=16)
        else:
            for i, (name, dept, total, count) in enumerate(credit_sum[:8]):
                deducted = db.get_total_deducted(name)
                balance  = round(max(total - deducted, 0), 2)
                is_p     = (balance == 0 and total > 0)
                bg = '#FFFFFF' if i % 2 == 0 else '#F5F7FA'
                rr = ctk.CTkFrame(right_f, fg_color=bg, corner_radius=0, height=40)
                rr.pack(fill="x", padx=8)
                rr.pack_propagate(False)
                rr.columnconfigure(0, weight=1)
                ctk.CTkLabel(rr, text=name, anchor="w",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color="#2E7D32" if is_p else TEXT_WHITE
                             ).grid(row=0, column=0, sticky="w", padx=(12, 4))
                ctk.CTkLabel(rr, text=dept or "-", width=90, anchor="center",
                             font=ctk.CTkFont(size=11), text_color="#7B1FA2"
                             ).grid(row=0, column=1, padx=4)
                ctk.CTkLabel(rr,
                             text="PAID" if is_p else "P" + "{:.2f}".format(balance),
                             width=120, anchor="e",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color="#2E7D32" if is_p else ACCENT_RED
                             ).grid(row=0, column=2, padx=(4, 16))

        ctk.CTkFrame(right_f, fg_color="transparent", height=10).pack()

    # ════════════════════════════════════════
    #  CREDITS MONITOR
    # ════════════════════════════════════════
    def _render_credits_data(self, credit_summary):
        for w in self.content.winfo_children(): w.destroy()
        _cr_store      = "canteen" if "canteen" in getattr(self,"credit_store_var",ctk.StringVar()).get().lower() else "cafestore"
        credit_summary = db.get_credit_summary(store=_cr_store)
        page = ctk.CTkFrame(self.content, fg_color="#F5F7FA", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(5, weight=1)
        page.columnconfigure(0, weight=1)

        total_utang = sum(r[2] for r in credit_summary)

        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 0))
        top.columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Credit / Utang Monitor",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#000000").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(top, text=str(len(credit_summary)) + " member(s)",
                     font=ctk.CTkFont(size=12), text_color="#546E7A"
                     ).grid(row=1, column=0, sticky="w")

        store_tabs = ctk.CTkFrame(page, fg_color="transparent")
        store_tabs.grid(row=1, column=0, pady=(8, 0))
        if not hasattr(self, "credit_store_var"):
            self.credit_store_var = ctk.StringVar(value="Cafe Store")

        def _set_credit_store(label, btns):
            self.credit_store_var.set(label)
            for l2, b in btns.items():
                b.configure(fg_color="#1976D2" if l2==label else BTN_BLUE)
            self._reload_admin_credits(credit_summary)

        _cur_cr = self.credit_store_var.get()
        credit_btns = {}
        for label in ["Cafe Store", "Cafeteria Canteen"]:
            is_active = (label == _cur_cr)
            b = ctk.CTkButton(store_tabs, text=label, width=280, height=52,
                              fg_color="#1976D2" if is_active else BTN_BLUE,
                              hover_color="#0D47A1" if is_active else "#1976D2",
                              font=ctk.CTkFont(size=16, weight="bold"), corner_radius=10)
            b.pack(side="left", padx=(0, 12), pady=8)
            credit_btns[label] = b
        for label, b in credit_btns.items():
            b.configure(command=lambda l=label, bts=credit_btns: _set_credit_store(l, bts))

        # ── Store banner ──
        cr_banner = ctk.CTkFrame(page, fg_color="#1565C0", corner_radius=10, height=44)
        cr_banner.grid(row=2, column=0, sticky="ew", padx=24, pady=(4, 0))
        cr_banner.pack_propagate(False)
        self._cr_banner_lbl = ctk.CTkLabel(cr_banner,
                     text=f"👤  {_cur_cr} — Credit Monitor",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="white")
        self._cr_banner_lbl.place(relx=0.5, rely=0.5, anchor="center")

        sf = ctk.CTkFrame(page, fg_color="#FFFFFF", corner_radius=8,
                          border_width=1, border_color="#1565C0")
        sf.grid(row=3, column=0, sticky="ew", padx=24, pady=(6, 0))
        sf.columnconfigure(1, weight=1)
        ctk.CTkLabel(sf, text="🔍", font=ctk.CTkFont(size=14),
                     text_color="#333333").grid(row=0, column=0, padx=(12, 4))
        self.admin_credit_search = ctk.StringVar()
        ctk.CTkEntry(sf, textvariable=self.admin_credit_search,
                     placeholder_text="Search by name...",
                     border_width=0, fg_color="transparent", height=38,
                     font=ctk.CTkFont(size=13), text_color="black",
                     placeholder_text_color="#333333"
                     ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkFrame(sf, fg_color="#BBDEFB", width=2, height=28
                     ).grid(row=0, column=2, padx=4)
        ctk.CTkLabel(sf, text="Dept:",
                     font=ctk.CTkFont(size=12), text_color="#546E7A"
                     ).grid(row=0, column=3, padx=(4,2))
        self.admin_credit_dept_var = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(sf, variable=self.admin_credit_dept_var,
                          values=["All","CCS","COED","COAG","COM","Other"],
                          width=110, height=32,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF",
                          dropdown_text_color="#1A1A2E",
                          text_color="black", font=ctk.CTkFont(size=11),
                          command=lambda _: self._reload_admin_credits(credit_summary)
                          ).grid(row=0, column=4, padx=(0,12), pady=8)

        hdr = ctk.CTkFrame(page, fg_color=COL_HDR, height=36, corner_radius=0)
        hdr.grid(row=4, column=0, sticky="ew", padx=24, pady=(4, 0))
        hdr.pack_propagate(False)
        hdr.columnconfigure(0, weight=1)
        for txt, col, w in [("NAME / ID",0,0),("TYPE",1,90),("DEPT",2,100),("TXN",3,60),
                              ("TOTAL UTANG",4,110),("DEDUCTED",5,100),
                              ("BALANCE",6,100),("ACTION",7,200)]:
            kw = {"font":ctk.CTkFont(size=10,weight="bold"),
                  "text_color":TEXT_GREY,"fg_color":"transparent","anchor":"w"}
            if w == 0:
                ctk.CTkLabel(hdr, text=txt, **kw).grid(
                    row=0, column=col, sticky="w", padx=(18,4), pady=5)
            else:
                ctk.CTkLabel(hdr, text=txt, width=w, **kw).grid(
                    row=0, column=col, padx=4, pady=5)

        self.credit_table = ctk.CTkScrollableFrame(page, fg_color="#F5F7FA",
                                                    scrollbar_button_color=BTN_BLUE,
                                                    corner_radius=0)
        self.credit_table.grid(row=5, column=0, sticky="nsew", padx=24, pady=(0, 12))
        self.credit_table.columnconfigure(0, weight=1)
        self.admin_credit_search.trace_add(
            "write", lambda *_: self._reload_admin_credits(credit_summary))
        self._reload_admin_credits(credit_summary)

    def _reload_admin_credits(self, all_rows):
        for w in self.credit_table.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.credit_table, text="⏳  Loading...",
                     font=ctk.CTkFont(size=14), text_color="#333333").pack(pady=40)
        store_label = self.credit_store_var.get() if hasattr(self, "credit_store_var") else "Cafe Store"
        dept_f = getattr(self, "admin_credit_dept_var", ctk.StringVar(value="All")).get()
        store_key   = "canteen" if "canteen" in store_label.lower() else "cafestore"
        # Update banner label
        try:
            self._cr_banner_lbl.configure(text=f"👤  {store_label} — Credit Monitor")
        except Exception:
            pass
        def _fetch():
            rows = db.get_credit_summary(store=store_key)
            self.after(0, lambda r=rows: self._render_admin_credits(r))
        threading.Thread(target=_fetch, daemon=True).start()

    def _render_admin_credits(self, all_rows):
        for w in self.credit_table.winfo_children():
            w.destroy()
        store_label = self.credit_store_var.get() if hasattr(self, "credit_store_var") else "Cafe Store"
        store_key   = "canteen" if "canteen" in store_label.lower() else "cafestore"
        q    = self.admin_credit_search.get().lower().strip()
        rows = [r for r in all_rows if q in r[0].lower()] if q else all_rows
        if not rows:
            ctk.CTkLabel(self.credit_table, text="No records found.",
                         font=ctk.CTkFont(size=14), text_color="#333333").pack(pady=40)
            return
        for i, (name, dept, total, count) in enumerate(rows):
            deducted  = db.get_total_deducted(name)
            balance   = round(max(total - deducted, 0), 2)
            is_paid   = (balance == 0 and total > 0)
            bg        = "#E8F5E9" if is_paid else (BG_ROW if i % 2 == 0 else BG_ROW_ALT)

            # ── Lookup member type + primary ID ──
            member_info = None
            member_type = "Others"
            member_type_color = "#E65100"
            primary_id  = ""
            try:
                member_info = db.get_loyalty_member_by_card_name(name, store="coop")
                if not member_info:
                    member_info = db.get_loyalty_member_by_card_name(name, store="cafestore")
                if not member_info:
                    member_info = db.get_loyalty_member_by_card_name(name, store="canteen")
            except Exception:
                pass
            if member_info:
                member_type = "Member"
                member_type_color = "#7B1FA2"
                primary_id  = member_info.get("member_id", "")
            else:
                try:
                    teacher = db.get_teacher_by_name(name)
                    if teacher:
                        primary_id = teacher.get("teacher_id", "")
                        member_type = "Others"
                        member_type_color = "#E65100"
                except Exception:
                    pass

            row = ctk.CTkFrame(self.credit_table, fg_color=bg,
                               corner_radius=6, border_width=1,
                               border_color="#BBDEFB" if not is_paid else "#A5D6A7")
            row.pack(fill="x", pady=2, padx=2)
            row.columnconfigure(0, weight=1)

            inner = ctk.CTkFrame(row, fg_color="transparent", height=60)
            inner.pack(fill="x"); inner.pack_propagate(False)
            inner.columnconfigure(0, weight=1)

            if is_paid:
                ctk.CTkFrame(inner, fg_color=GREEN, width=5,
                             corner_radius=0).place(x=0, y=0, relheight=1)

            # Name + primary ID stacked
            nf = ctk.CTkFrame(inner, fg_color="transparent")
            nf.grid(row=0, column=0, sticky="w", padx=(14, 4), pady=6)
            ctk.CTkLabel(nf, text=name, anchor="w",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#2E7D32" if is_paid else TEXT_WHITE
                         ).pack(anchor="w")
            if primary_id:
                ctk.CTkLabel(nf, text=primary_id, anchor="w",
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=member_type_color
                             ).pack(anchor="w")

            # Type badge
            type_badge = ctk.CTkFrame(inner, fg_color=member_type_color,
                                       corner_radius=6, width=80, height=24)
            type_badge.grid(row=0, column=1, padx=4)
            type_badge.pack_propagate(False)
            ctk.CTkLabel(type_badge, text=member_type,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")

            ctk.CTkLabel(inner, text=dept or "-", width=100, anchor="center",
                         font=ctk.CTkFont(size=12), text_color="#546E7A"
                         ).grid(row=0, column=2, padx=4)
            ctk.CTkLabel(inner, text=str(count), width=60, anchor="center",
                         font=ctk.CTkFont(size=12), text_color="#333333"
                         ).grid(row=0, column=3, padx=4)
            ctk.CTkLabel(inner, text=f"₱{total:.2f}",
                         width=110, anchor="center",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#1565C0"
                         ).grid(row=0, column=4, padx=4)
            ctk.CTkLabel(inner, text=f"₱{deducted:.2f}",
                         width=100, anchor="center",
                         font=ctk.CTkFont(size=12), text_color="#2E7D32"
                         ).grid(row=0, column=5, padx=4)
            bal_color = GREEN if is_paid else (ORANGE if balance < total * 0.5 else ACCENT_RED)
            ctk.CTkLabel(inner, text="PAID" if is_paid else f"₱{balance:.2f}",
                         width=100, anchor="center",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=bal_color
                         ).grid(row=0, column=6, padx=4)

            act_f = ctk.CTkFrame(inner, fg_color="transparent")
            act_f.grid(row=0, column=7, padx=(4, 10), sticky="e")

            ctk.CTkButton(act_f, text="Deduct",
                          width=64, height=30,
                          fg_color="#7B1FA2" if not is_paid else "#AAAAAA",
                          hover_color="#6A1B9A" if not is_paid else "#AAAAAA",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          text_color="white",
                          state="normal" if not is_paid else "disabled",
                          command=lambda n=name, d=dept, b=balance:
                              self._deduct_dialog(n, d, b)
                          ).pack(side="left", padx=(0, 3))

            ctk.CTkButton(act_f, text="🖨 Print",
                          width=64, height=30,
                          fg_color=GREEN, hover_color="#1B5E20",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          text_color="white",
                          command=lambda n=name, d=dept, t=total, ded=deducted, b=balance:
                              self._print_credit_summary(n, d, t, ded, b)
                          ).pack(side="left", padx=(0, 3))

            ctk.CTkButton(act_f, text="Del",
                          width=46, height=30,
                          fg_color="#5D0000", hover_color="#8B0000",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          text_color="white",
                          command=lambda n=name, d=dept, ar=all_rows:
                              self._delete_paid_faculty(n, d, ar)
                          ).pack(side="left")

    def _deduct_dialog(self, name, dept, balance):
        win = ctk.CTkToplevel(self)
        win.title("Salary Deduction")
        win.geometry("420x440")
        win.configure(fg_color="#FFFFFF")
        win.grab_set()
        win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        wx = (sw - 420) // 2
        wy = (sh - 440) // 2
        win.geometry("420x440+" + str(wx) + "+" + str(wy))

        ctk.CTkLabel(win, text="Salary Deduction",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="#000000").pack(pady=(22, 6))

        info = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=8,
                             border_width=1, border_color="#7E57C2")
        info.pack(fill="x", padx=28, pady=(0, 14))
        ctk.CTkLabel(info, text="  " + name,
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#6A1B9A").pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(info, text="Department: " + (dept or "-"),
                     font=ctk.CTkFont(size=11),
                     text_color="#333333").pack(anchor="w", padx=14)
        ctk.CTkLabel(info,
                     text="Remaining Balance: P" + "{:.2f}".format(balance),
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#1565C0").pack(anchor="w", padx=14, pady=(2, 10))

        r1 = ctk.CTkFrame(win, fg_color="transparent")
        r1.pack(fill="x", padx=28, pady=5)
        ctk.CTkLabel(r1, text="Amount to Deduct (P)", width=170, anchor="w",
                     font=ctk.CTkFont(size=12), text_color="#333333").pack(side="left")
        amount_entry = ctk.CTkEntry(r1, height=36, fg_color="#BBDEFB",
                                     border_width=1, border_color="#1565C0",
                                     text_color="black", font=ctk.CTkFont(size=13))
        amount_entry.pack(side="left", fill="x", expand=True)

        r2 = ctk.CTkFrame(win, fg_color="transparent")
        r2.pack(fill="x", padx=28, pady=5)
        ctk.CTkLabel(r2, text="Note / Reason", width=170, anchor="w",
                     font=ctk.CTkFont(size=12), text_color="#333333").pack(side="left")
        note_entry = ctk.CTkEntry(r2, height=36, fg_color="#BBDEFB",
                                   border_width=1, border_color="#1565C0",
                                   text_color="black", font=ctk.CTkFont(size=13))
        note_entry.pack(side="left", fill="x", expand=True)

        def save():
            try:
                amt = round(float(amount_entry.get().strip()), 2)
                if amt <= 0:
                    raise ValueError
                if round(amt, 2) > round(balance, 2):
                    messagebox.showerror(
                        "Error",
                        "Amount exceeds balance P" + "{:.2f}".format(balance),
                        parent=win)
                    return
                note = note_entry.get().strip() or "Salary deduction"
                dt   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.add_deduction(name, dept or "", amt, note, dt)
                messagebox.showinfo(
                    "Success",
                    "P" + "{:.2f}".format(amt) + " deducted from " + name,
                    parent=win)
                win.destroy()
                self._nav("credits")
            except ValueError:
                messagebox.showerror("Error", "Please enter a valid amount.", parent=win)

        # ── Buttons pinned to BOTTOM so they're always visible ──
        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=28, pady=(0, 20))

        ctk.CTkButton(btn_frame, text="Cancel", height=40,
                      fg_color="#546E7A", hover_color="#37474F",
                      text_color="white",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8,
                      command=win.destroy).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(btn_frame, text="✔  Confirm Deduction", height=44,
                      fg_color="#2E7D32", hover_color="#1B5E20",
                      text_color="white",
                      font=ctk.CTkFont(size=14, weight="bold"), corner_radius=8,
                      command=save).pack(fill="x")

    # ════════════════════════════════════════
    #  HISTORY
    # ════════════════════════════════════════
    def _render_history_data(self, all_deductions, credit_sum):
        for w in self.content.winfo_children(): w.destroy()
        page = ctk.CTkFrame(self.content, fg_color="#F5F7FA", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(0, weight=0)
        page.rowconfigure(1, weight=0)
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)

        credit_totals      = {r[0]: r[2] for r in credit_sum}
        total_deducted_all = sum(r[3] for r in all_deductions)

        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 6))
        top.columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Deduction History",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#000000").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(top, text=str(len(all_deductions)) + " deduction(s)",
                     font=ctk.CTkFont(size=12), text_color="#546E7A"
                     ).grid(row=1, column=0, sticky="w")

        fbar = ctk.CTkFrame(page, fg_color="#FFFFFF", corner_radius=8,
                             border_width=1, border_color="#000000")
        fbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 6))

        ctk.CTkLabel(fbar, text="🔍  Faculty:",
                     font=ctk.CTkFont(size=12), text_color="#333333"
                     ).pack(side="left", padx=(14, 4), pady=8)
        self.hist_name_var = ctk.StringVar()
        ctk.CTkEntry(fbar, textvariable=self.hist_name_var,
                     placeholder_text="Search by faculty name...",
                     border_width=0, fg_color="#FFFFFF", height=32, width=200,
                     font=ctk.CTkFont(size=12), text_color="black",
                     placeholder_text_color="#333333"
                     ).pack(side="left", padx=(0, 10), pady=6)

        ctk.CTkFrame(fbar, fg_color="#FFFFFF", width=2, height=28).pack(side="left", padx=8)

        ctk.CTkLabel(fbar, text="Date:",
                     font=ctk.CTkFont(size=12), text_color="#333333"
                     ).pack(side="left", padx=(4, 4))
        self.hist_date_var = ctk.StringVar()
        self.hist_date_lbl = ctk.CTkLabel(fbar, text="All dates",
                                           font=ctk.CTkFont(size=12, weight="bold"),
                                           text_color="#E65100", cursor="hand2")
        self.hist_date_lbl.pack(side="left", padx=4)
        ctk.CTkButton(fbar, text="Clear", width=60, height=28,
                      fg_color=BTN_BLUE, hover_color="#1976D2",
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=lambda: [self.hist_date_var.set(""),
                                       self.hist_date_lbl.configure(text="All dates"),
                                       self._reload_deduction_table(all_deductions, credit_totals, ded_table)]
                      ).pack(side="left", padx=(6, 14))

        ded_table = ctk.CTkScrollableFrame(page, fg_color="#F5F7FA",
                                            scrollbar_button_color=BTN_BLUE,
                                            corner_radius=0)
        ded_table.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 12))
        ded_table.columnconfigure(0, weight=1)

        self.hist_date_lbl.bind("<Button-1>",
                                 lambda e: self._open_ded_calendar(all_deductions, credit_totals, ded_table))
        self.hist_name_var.trace_add("write",
                                      lambda *_: self._reload_deduction_table(all_deductions, credit_totals, ded_table))

        self._reload_deduction_table(all_deductions, credit_totals, ded_table)

    def _open_ded_calendar(self, all_deductions, credit_totals, table):
        import calendar as cal_mod
        win = ctk.CTkToplevel(self)
        win.title("Pick a Date")
        win.geometry("320x300")
        win.configure(fg_color="#FFFFFF")
        win.grab_set(); win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry("320x300+" + str((sw-320)//2) + "+" + str((sh-300)//2))
        now   = datetime.now()
        state = {"year": now.year, "month": now.month}

        def build(year, month):
            for w in win.winfo_children(): w.destroy()
            hdr = ctk.CTkFrame(win, fg_color="#1565C0", height=44, corner_radius=0)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            ctk.CTkButton(hdr, text="<", width=36, height=30, fg_color="transparent",
                          hover_color="#1565C0", font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(-1)).place(x=8, rely=0.5, anchor="w")
            ctk.CTkLabel(hdr, text=cal_mod.month_name[month] + "  " + str(year),
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkButton(hdr, text=">", width=36, height=30, fg_color="transparent",
                          hover_color="#1565C0", font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(1)).place(relx=1.0, x=-8, rely=0.5, anchor="e")
            dh = ctk.CTkFrame(win, fg_color="transparent")
            dh.pack(fill="x", padx=10, pady=(6,0))
            for d in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
                ctk.CTkLabel(dh, text=d, width=36, font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#333333").pack(side="left")
            gf = ctk.CTkFrame(win, fg_color="transparent")
            gf.pack(fill="x", padx=10, pady=4)
            for week in cal_mod.monthcalendar(year, month):
                rf = ctk.CTkFrame(gf, fg_color="transparent")
                rf.pack(fill="x", pady=1)
                for day in week:
                    if day == 0:
                        ctk.CTkLabel(rf, text="", width=36).pack(side="left")
                    else:
                        is_today = (day==now.day and month==now.month and year==now.year)
                        ctk.CTkButton(rf, text=str(day), width=34, height=28,
                                      fg_color="#1976D2" if is_today else BTN_BLUE,
                                      hover_color="#0D47A1" if is_today else "#1976D2",
                                      font=ctk.CTkFont(size=11), corner_radius=4,
                                      command=lambda d=day: pick(d)
                                      ).pack(side="left", padx=1)

        def go(delta):
            m = state["month"]+delta; y = state["year"]
            if m>12: m=1; y+=1
            if m<1: m=12; y-=1
            state["year"]=y; state["month"]=m; build(y,m)

        def pick(day):
            chosen = str(state["year"]).zfill(4)+"-"+str(state["month"]).zfill(2)+"-"+str(day).zfill(2)
            self.hist_date_var.set(chosen)
            self.hist_date_lbl.configure(
                text=str(state["month"]).zfill(2)+"/"+str(day).zfill(2)+"/"+str(state["year"]))
            win.destroy()
            self._reload_deduction_table(all_deductions, credit_totals, table)

        build(state["year"], state["month"])

    def _reload_deduction_table(self, all_rows, credit_totals, table):
        for w in table.winfo_children(): w.destroy()
        name_q = getattr(self, "hist_name_var", ctk.StringVar()).get().lower().strip()
        date_q = getattr(self, "hist_date_var", ctk.StringVar()).get().strip()

        rows = all_rows
        if name_q:
            rows = [r for r in rows if name_q in r[1].lower()]
        if date_q:
            rows = [r for r in rows if r[5][:10] == date_q]

        if not rows:
            ctk.CTkLabel(table, text="No deduction records found.",
                         font=ctk.CTkFont(size=14), text_color="#333333").pack(pady=40)
            return

        hdr = ctk.CTkFrame(table, fg_color=COL_HDR, height=30, corner_radius=4)
        hdr.pack(fill="x", pady=(0, 2))
        hdr.pack_propagate(False)
        hdr.columnconfigure(0, weight=1)
        for txt, col, w, anch in [
            ("FACULTY NAME", 0, 0,   "w"),
            ("DEPT",         1, 120, "center"),
            ("DEDUCTED",     2, 110, "center"),
            ("NOTE",         3, 200, "w"),
            ("DATE & TIME",  4, 200, "center"),
            ("STATUS",       5, 100, "center"),
        ]:
            kw = {"font":ctk.CTkFont(size=10,weight="bold"),
                  "text_color":TEXT_GREY,"fg_color":"transparent","anchor":anch}
            if w==0:
                ctk.CTkLabel(hdr,text=txt,**kw).grid(row=0,column=col,sticky="w",padx=(16,4),pady=4)
            else:
                ctk.CTkLabel(hdr,text=txt,width=w,**kw).grid(row=0,column=col,padx=4,pady=4)

        for i, (ded_id, faculty, dept, amount, note, dt) in enumerate(rows):
            try:
                dt_str = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y  %I:%M %p")
            except Exception:
                dt_str = dt[:16]

            total_credit   = credit_totals.get(faculty, 0)
            total_deducted = db.get_total_deducted(faculty)
            balance        = max(total_credit - total_deducted, 0)
            is_paid        = (balance == 0 and total_credit > 0)

            bg = '#FFFFFF' if i % 2 == 0 else '#F5F7FA'
            row = ctk.CTkFrame(table, fg_color=bg, corner_radius=0, height=46)
            row.pack(fill="x")
            row.pack_propagate(False)
            row.columnconfigure(0, weight=1)

            bar_color = GREEN if is_paid else "#7E57C2"
            ctk.CTkFrame(row, fg_color=bar_color, width=5,
                         corner_radius=0).place(x=0, y=0, relheight=1)

            ctk.CTkLabel(row, text=faculty, anchor="w",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#000000"
                         ).grid(row=0, column=0, sticky="w", padx=(14, 8))
            ctk.CTkLabel(row, text=dept or "-", width=120, anchor="center",
                         font=ctk.CTkFont(size=11), text_color="#7B1FA2"
                         ).grid(row=0, column=1, padx=4)
            ctk.CTkLabel(row, text="P" + "{:.2f}".format(amount) if amount > 0 else "-",
                         width=110, anchor="center",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#2E7D32" if amount > 0 else TEXT_GREY
                         ).grid(row=0, column=2, padx=4)
            ctk.CTkLabel(row, text=note or "-", width=200, anchor="w",
                         font=ctk.CTkFont(size=11), text_color="#333333"
                         ).grid(row=0, column=3, padx=4)
            ctk.CTkLabel(row, text=dt_str, width=200, anchor="center",
                         font=ctk.CTkFont(size=11), text_color="#000000"
                         ).grid(row=0, column=4, padx=4)

            if is_paid:
                status_lbl = ctk.CTkLabel(row, text="  PAID  ", width=100, anchor="center",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="#2E7D32", fg_color="#FFFFFF", corner_radius=6)
            else:
                status_lbl = ctk.CTkLabel(row, text=" Deducted ", width=100, anchor="center",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="#6A1B9A", fg_color="#FFFFFF", corner_radius=6)
            status_lbl.grid(row=0, column=5, padx=(4, 14))

    # ════════════════════════════════════════
    #  SALES
    # ════════════════════════════════════════
    def _show_sales(self):
        page = ctk.CTkFrame(self.content, fg_color="#F5F7FA", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(0, weight=0)
        page.rowconfigure(1, weight=0)
        page.rowconfigure(2, weight=0)
        page.rowconfigure(3, weight=1)
        page.columnconfigure(0, weight=1)

        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 4))
        top.columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Sales Report",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#000000").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(top, text="🖨  Print Report", width=140, height=36,
                      fg_color="#2E7D32", hover_color="#1B5E20",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      text_color="white", corner_radius=8,
                      command=self._print_sales_report
                      ).grid(row=0, column=1, sticky="e")

        store_tabs = ctk.CTkFrame(page, fg_color="transparent")
        store_tabs.grid(row=1, column=0, pady=(0, 4))
        if not hasattr(self, "sales_store_var"):
            self.sales_store_var = ctk.StringVar(value="Cafe Store")

        def _set_sales_store(label, btns):
            self.sales_store_var.set(label)
            for l2, b in btns.items():
                b.configure(fg_color="#1976D2" if l2==label else BTN_BLUE)
            self._reload_sales()

        _cur_s = self.sales_store_var.get()
        sales_btns = {}
        for label in ["Cafe Store", "Cafeteria Canteen"]:
            is_active = (label == _cur_s)
            b = ctk.CTkButton(store_tabs, text=label, width=280, height=52,
                              fg_color="#1976D2" if is_active else BTN_BLUE,
                              hover_color="#0D47A1" if is_active else "#1976D2",
                              font=ctk.CTkFont(size=16, weight="bold"), corner_radius=10)
            b.pack(side="left", padx=(0, 12), pady=8)
            sales_btns[label] = b
        for label, b in sales_btns.items():
            b.configure(command=lambda l=label, bts=sales_btns: _set_sales_store(l, bts))

        ctrl = ctk.CTkFrame(page, fg_color="#FFFFFF", corner_radius=8)
        ctrl.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 4))

        ctk.CTkLabel(ctrl, text="Period:",
                     font=ctk.CTkFont(size=12), text_color="#333333"
                     ).pack(side="left", padx=(12, 6), pady=8)
        self.sales_period = ctk.StringVar(value="Month")
        ctk.CTkOptionMenu(ctrl, variable=self.sales_period,
                          values=["Day", "Week", "Month", "Year"],
                          width=100, height=32,
                          fg_color=BTN_BLUE, button_color=ACCENT_RED,
                          button_hover_color="#0D47A1", dropdown_fg_color="#FFFFFF",
                          text_color="white", font=ctk.CTkFont(size=12, weight="bold"),
                          command=lambda v: self._reload_sales()
                          ).pack(side="left", padx=(0, 6))
        ctk.CTkFrame(ctrl, fg_color="#BBDEFB", width=2, height=28).pack(side="left", padx=6)
        ctk.CTkLabel(ctrl, text="Month:",
                     font=ctk.CTkFont(size=12), text_color="#333333"
                     ).pack(side="left", padx=(4, 4))
        import calendar as _cal
        month_names = ["All"] + [_cal.month_name[m] for m in range(1, 13)]
        self.sales_month_var = ctk.StringVar(value=_cal.month_name[datetime.now().month])
        ctk.CTkOptionMenu(ctrl, variable=self.sales_month_var,
                          values=month_names, width=120, height=32,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                          text_color="black", font=ctk.CTkFont(size=11),
                          command=lambda v: self._reload_sales()
                          ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(ctrl, text="Year:",
                     font=ctk.CTkFont(size=12), text_color="#333333"
                     ).pack(side="left", padx=(4, 4))
        cur_year = datetime.now().year
        year_values = [str(y) for y in range(cur_year - 4, cur_year + 2)]
        self.sales_year_var = ctk.StringVar(value=str(cur_year))
        ctk.CTkOptionMenu(ctrl, variable=self.sales_year_var,
                          values=year_values, width=90, height=32,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                          text_color="black", font=ctk.CTkFont(size=11),
                          command=lambda v: self._reload_sales()
                          ).pack(side="left", padx=(0, 6))
        ctk.CTkFrame(ctrl, fg_color="#BBDEFB", width=2, height=28).pack(side="left", padx=6)
        ctk.CTkLabel(ctrl, text="Date:",
                     font=ctk.CTkFont(size=12), text_color="#333333"
                     ).pack(side="left", padx=(4, 4))
        self.sales_date_var = ctk.StringVar()
        self.sales_date_lbl = ctk.CTkLabel(ctrl, text="All dates",
                                            font=ctk.CTkFont(size=12, weight="bold"),
                                            text_color="#E65100", cursor="hand2")
        self.sales_date_lbl.pack(side="left", padx=4)
        self.sales_date_lbl.bind("<Button-1>", lambda e: self._open_sales_calendar())
        ctk.CTkButton(ctrl, text="Clear", width=60, height=28,
                      fg_color=BTN_BLUE, hover_color="#1976D2",
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=lambda: [self.sales_date_var.set(""),
                                       self.sales_date_lbl.configure(text="All dates"),
                                       self._reload_sales()]
                      ).pack(side="left", padx=(6, 8))

        self.sales_body = ctk.CTkScrollableFrame(page, fg_color="#F5F7FA",
                                                  scrollbar_button_color=BTN_BLUE,
                                                  corner_radius=0)
        self.sales_body.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 12))
        self.sales_body.columnconfigure(0, weight=1)
        self._reload_sales()

    def _open_sales_calendar(self):
        import calendar as cal_mod
        win = ctk.CTkToplevel(self)
        win.title("Pick a Date")
        win.geometry("320x300")
        win.configure(fg_color="#FFFFFF")
        win.grab_set(); win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry("320x300+" + str((sw-320)//2) + "+" + str((sh-300)//2))
        now   = datetime.now()
        state = {"year": now.year, "month": now.month}

        def build(year, month):
            for w in win.winfo_children(): w.destroy()
            hdr = ctk.CTkFrame(win, fg_color="#1565C0", height=44, corner_radius=0)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            ctk.CTkButton(hdr, text="<", width=36, height=30,
                          fg_color="transparent", hover_color="#1565C0",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(-1)).place(x=8, rely=0.5, anchor="w")
            ctk.CTkLabel(hdr, text=cal_mod.month_name[month] + "  " + str(year),
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkButton(hdr, text=">", width=36, height=30,
                          fg_color="transparent", hover_color="#1565C0",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(1)).place(relx=1.0, x=-8, rely=0.5, anchor="e")
            dh = ctk.CTkFrame(win, fg_color="transparent")
            dh.pack(fill="x", padx=10, pady=(6,0))
            for d in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
                ctk.CTkLabel(dh, text=d, width=36,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#333333").pack(side="left")
            gf = ctk.CTkFrame(win, fg_color="transparent")
            gf.pack(fill="x", padx=10, pady=4)
            for week in cal_mod.monthcalendar(year, month):
                rf = ctk.CTkFrame(gf, fg_color="transparent")
                rf.pack(fill="x", pady=1)
                for day in week:
                    if day == 0:
                        ctk.CTkLabel(rf, text="", width=36).pack(side="left")
                    else:
                        is_today = (day==now.day and month==now.month and year==now.year)
                        ctk.CTkButton(rf, text=str(day), width=34, height=28,
                                      fg_color="#1976D2" if is_today else BTN_BLUE,
                                      hover_color="#0D47A1" if is_today else "#1976D2",
                                      font=ctk.CTkFont(size=11), corner_radius=4,
                                      command=lambda d=day: pick(d)
                                      ).pack(side="left", padx=1)

        def go(delta):
            m = state["month"]+delta; y = state["year"]
            if m>12: m=1; y+=1
            if m<1:  m=12; y-=1
            state["year"]=y; state["month"]=m; build(y,m)

        def pick(day):
            chosen = str(state["year"]).zfill(4) + "-" + str(state["month"]).zfill(2) + "-" + str(day).zfill(2)
            self.sales_date_var.set(chosen)
            self.sales_date_lbl.configure(
                text=str(state["month"]).zfill(2) + "/" + str(day).zfill(2) + "/" + str(state["year"]))
            win.destroy()
            self._reload_sales()

        build(state["year"], state["month"])

    def _print_sales_report(self):
        import platform, subprocess, tempfile
        date_q = getattr(self, "sales_date_var", ctk.StringVar()).get().strip()
        period = self.sales_period.get().lower()
        if date_q:
            data   = db.get_sales_report_custom(date_q, date_q)
            period_label = date_q
        else:
            data   = db.get_sales_report(period)
            period_label = self.sales_period.get()
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.units import cm
            from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                             Paragraph, Spacer, HRFlowable)
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.enums import TA_CENTER
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.close()
            doc = SimpleDocTemplate(tmp.name, pagesize=A4,
                                    topMargin=1.5*cm, bottomMargin=1.5*cm,
                                    leftMargin=2*cm, rightMargin=2*cm)
            RED  = colors.HexColor("#1565C0")
            GREY = colors.HexColor("#555555")
            story = []
            c_s = ParagraphStyle("c", fontSize=20, fontName="Helvetica-Bold",
                                  textColor=RED, alignment=TA_CENTER, spaceAfter=4)
            s_s = ParagraphStyle("s", fontSize=10, fontName="Helvetica",
                                  textColor=GREY, alignment=TA_CENTER, spaceAfter=2)
            story.append(Paragraph("CAFETERIA STORE", c_s))
            story.append(Paragraph("Sales Report", s_s))
            story.append(Paragraph("Period: " + period_label, s_s))
            story.append(Paragraph("Printed: " + datetime.now().strftime("%B %d, %Y  %I:%M %p"), s_s))
            story.append(Spacer(1, 0.4*cm))
            story.append(HRFlowable(width="100%", thickness=2, color=RED))
            story.append(Spacer(1, 0.3*cm))
            lbl_s = ParagraphStyle("l", fontSize=9, fontName="Helvetica-Bold",
                                    textColor=GREY, alignment=TA_CENTER)
            val_s = ParagraphStyle("v", fontSize=18, fontName="Helvetica-Bold",
                                    textColor=RED, alignment=TA_CENTER)
            flat = [
                [Paragraph("TOTAL REVENUE", lbl_s),
                 Paragraph("TRANSACTIONS", lbl_s),
                 Paragraph("AVG TRANSACTION", lbl_s)],
                [Paragraph("P" + "{:.2f}".format(data["revenue"]), val_s),
                 Paragraph(str(data["count"]), val_s),
                 Paragraph("P" + "{:.2f}".format(data["avg"]), val_s)],
            ]
            t = Table(flat, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
            t.setStyle(TableStyle([
                ("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#FFF8F8")),
                ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.4*cm))
            h_s = ParagraphStyle("h", fontSize=13, fontName="Helvetica-Bold",
                                   textColor=colors.HexColor("#F5F5F5"), spaceAfter=6)
            story.append(Paragraph("Payment Method Breakdown", h_s))
            pd = [["Payment Method", "Amount"]]
            for m in ["Cash", "Cash (Mobile)", "Credit / Utang"]:
                amt = (data["by_method"].get("Cash",0) + data["by_method"].get("Cash (Mobile)",0) + data["by_method"].get("Mobile Order",0)) if m == "Cash" else data["by_method"].get(m, 0)
                pd.append([m, "P" + "{:.2f}".format(amt)])
            pt = Table(pd, colWidths=[10*cm, 6.5*cm])
            pt.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),RED),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),11),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F9F9F9"),colors.white]),
                ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
                ("LEFTPADDING",(0,0),(-1,-1),12),
            ]))
            story.append(pt)
            story.append(Spacer(1, 0.4*cm))
            story.append(Paragraph("Items Sold", h_s))
            id_ = [["Product", "Category", "Qty", "Revenue"]]
            for name, cat, qty, rev in (data["items_sold"] or []):
                id_.append([name, cat, str(qty), "P" + "{:.2f}".format(rev)])
            if len(id_) == 1:
                id_.append(["No data", "", "", ""])
            it = Table(id_, colWidths=[7*cm, 4*cm, 3*cm, 2.5*cm])
            it.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),RED),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),10),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F9F9F9"),colors.white]),
                ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
                ("LEFTPADDING",(0,0),(-1,-1),10),
            ]))
            story.append(it)
            story.append(Spacer(1, 0.4*cm))
            f_s = ParagraphStyle("f", fontSize=8, textColor=GREY, alignment=TA_CENTER)
            story.append(Paragraph("Cafe Store POS - Auto-generated Report", f_s))
            doc.build(story)
            if platform.system() == "Windows":
                os.startfile(tmp.name)
            elif platform.system() == "Darwin":
                subprocess.run(["open", tmp.name])
            else:
                subprocess.run(["xdg-open", tmp.name])
            messagebox.showinfo("PDF Ready", "Report PDF opened!", parent=self)
        except ImportError:
            messagebox.showinfo("Install Required", "pip install reportlab", parent=self)
        except Exception as ex:
            messagebox.showerror("Error", str(ex), parent=self)

    def _reload_sales(self):
        for w in self.sales_body.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.sales_body, text="⏳  Loading sales data...",
                     font=ctk.CTkFont(size=14), text_color="#333333").pack(pady=40)
        store_label = self.sales_store_var.get() if hasattr(self, "sales_store_var") else "Cafeteria Store"
        store_key   = "canteen" if "canteen" in store_label.lower() else "cafestore"
        date_q      = self.sales_date_var.get().strip() if hasattr(self, "sales_date_var") else ""
        period      = self.sales_period.get().lower()
        import calendar as _cal
        month_name  = getattr(self, "sales_month_var", ctk.StringVar(value="All")).get()
        year_str    = getattr(self, "sales_year_var", ctk.StringVar(value=str(datetime.now().year))).get()
        def _fetch():
            if date_q:
                data = db.get_sales_report_custom(date_q, date_q, store=store_key)
            elif month_name != "All" and year_str:
                try:
                    month_num = list(_cal.month_name).index(month_name)
                    year_num  = int(year_str)
                    last_day  = _cal.monthrange(year_num, month_num)[1]
                    data = db.get_sales_report_custom(
                        f"{year_num:04d}-{month_num:02d}-01",
                        f"{year_num:04d}-{month_num:02d}-{last_day:02d}",
                        store=store_key)
                except Exception:
                    data = db.get_sales_report(period, store=store_key)
            elif year_str and month_name == "All":
                try:
                    year_num = int(year_str)
                    data = db.get_sales_report_custom(
                        f"{year_num:04d}-01-01", f"{year_num:04d}-12-31", store=store_key)
                except Exception:
                    data = db.get_sales_report(period, store=store_key)
            else:
                data = db.get_sales_report(period, store=store_key)
            self.after(0, lambda d=data: self._render_sales_data(d))
        threading.Thread(target=_fetch, daemon=True).start()

    def _render_sales_data(self, data):
        for w in self.sales_body.winfo_children():
            w.destroy()

        # ── Store header banner ──
        store_label = self.sales_store_var.get() if hasattr(self, "sales_store_var") else "Cafe Store"
        store_banner = ctk.CTkFrame(self.sales_body, fg_color="#1565C0",
                                    corner_radius=10, height=44)
        store_banner.pack(fill="x", pady=(0, 10))
        store_banner.pack_propagate(False)
        ctk.CTkLabel(store_banner,
                     text=f"📊  {store_label} — Sales Data",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="white").place(relx=0.5, rely=0.5, anchor="center")

        cards = ctk.CTkFrame(self.sales_body, fg_color="transparent")
        cards.pack(fill="x", pady=(4, 14))
        cards.columnconfigure((0, 1, 2), weight=1)
        for col, (lbl, val, vc) in enumerate([
            ("TOTAL REVENUE",    "P" + "{:.2f}".format(data["revenue"]), ACCENT_RED),
            ("TRANSACTIONS",     str(data["count"]),                      TEXT_WHITE),
            ("AVG TRANSACTION",  "P" + "{:.2f}".format(data["avg"]),     TEXT_WHITE),
        ]):
            c = ctk.CTkFrame(cards, fg_color="#FFFFFF", corner_radius=10)
            c.grid(row=0, column=col, sticky="ew", padx=5, pady=4)
            ctk.CTkLabel(c, text=lbl, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#333333").pack(anchor="w", padx=16, pady=(14, 2))
            ctk.CTkLabel(c, text=val, font=ctk.CTkFont(size=24, weight="bold"),
                         text_color=vc).pack(anchor="w", padx=16, pady=(0, 14))

        ctk.CTkLabel(self.sales_body, text="Payment Breakdown",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#000000").pack(anchor="w", pady=(0, 6))
        pr = ctk.CTkFrame(self.sales_body, fg_color="transparent")
        pr.pack(fill="x", pady=(0, 14))
        pr.columnconfigure((0, 1, 2), weight=1)
        for col, (m, icon, accent) in enumerate([
            ("Cash",           "💵", "#1565C0"),
            ("Cash (Mobile)",  "📲", "#0D47A1"),
            ("Credit / Utang", "💳", "#7B1FA2"),
        ]):
            if m == "Cash":
                amt = data["by_method"].get("Cash", 0) + data["by_method"].get("Cash (Mobile)", 0) + data["by_method"].get("Mobile Order", 0)
            else:
                amt = data["by_method"].get(m, 0)
            card = ctk.CTkFrame(pr, fg_color="#FFFFFF", corner_radius=10,
                                border_width=2, border_color=accent)
            card.grid(row=0, column=col, sticky="ew", padx=5)
            ctk.CTkLabel(card, text=f"{icon}  {m.replace(' / Utang', '/Utang')}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=accent).pack(anchor="w", padx=14, pady=(12, 4))
            ctk.CTkLabel(card, text=f"₱{amt:.2f}",
                         font=ctk.CTkFont(size=22, weight="bold"),
                         text_color="#1A1A2E").pack(anchor="w", padx=14, pady=(0, 12))

        ctk.CTkLabel(self.sales_body, text="Items Sold",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#000000").pack(anchor="w", pady=(0, 6))
        th = ctk.CTkFrame(self.sales_body, fg_color=COL_HDR, height=32, corner_radius=4)
        th.pack(fill="x")
        th.pack_propagate(False)
        th.columnconfigure(0, weight=1)
        for txt, col, w in [("PRODUCT",0,0),("CATEGORY",1,160),("QTY",2,100),("REVENUE",3,110)]:
            kw = {"font":ctk.CTkFont(size=10,weight="bold"),
                  "text_color":TEXT_GREY,"fg_color":"transparent","anchor":"w"}
            if w == 0:
                ctk.CTkLabel(th, text=txt, **kw).grid(
                    row=0, column=col, sticky="w", padx=(14, 4), pady=5)
            else:
                ctk.CTkLabel(th, text=txt, width=w, **kw).grid(
                    row=0, column=col, padx=4, pady=5)

        if not data["items_sold"]:
            ctk.CTkLabel(self.sales_body, text="No sales data.",
                         font=ctk.CTkFont(size=13), text_color="#333333").pack(pady=20)
        else:
            for i, (name, cat, qty, rev) in enumerate(data["items_sold"]):
                bg = '#FFFFFF' if i % 2 == 0 else '#F5F7FA'
                r  = ctk.CTkFrame(self.sales_body, fg_color=bg, height=38, corner_radius=0)
                r.pack(fill="x")
                r.pack_propagate(False)
                r.columnconfigure(0, weight=1)
                ctk.CTkLabel(r, text=name, anchor="w",
                             font=ctk.CTkFont(size=12), text_color="#000000"
                             ).grid(row=0, column=0, sticky="w", padx=(14, 4))
                ctk.CTkLabel(r, text=cat, width=160, anchor="center",
                             font=ctk.CTkFont(size=12), text_color="#333333"
                             ).grid(row=0, column=1, padx=4)
                ctk.CTkLabel(r, text=str(qty), width=100, anchor="center",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color="#000000").grid(row=0, column=2, padx=4)
                ctk.CTkLabel(r, text="P" + "{:.2f}".format(rev),
                             width=110, anchor="center",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color="#1565C0").grid(row=0, column=3, padx=4)

    def _print_credit_summary(self, name, dept, total, deducted, balance):
        import platform, subprocess, tempfile
        try:
            from reportlab.lib.pagesizes import A5
            from reportlab.lib import colors
            from reportlab.lib.units import cm
            from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                             Paragraph, Spacer, HRFlowable)
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.enums import TA_CENTER
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp.close()
            doc = SimpleDocTemplate(tmp.name, pagesize=A5,
                                    topMargin=1.2*cm, bottomMargin=1.2*cm,
                                    leftMargin=1.5*cm, rightMargin=1.5*cm)
            RED  = colors.HexColor("#1565C0")
            GREY = colors.HexColor("#555555")
            story = []
            c_s = ParagraphStyle("c", fontSize=18, fontName="Helvetica-Bold",
                                  textColor=RED, alignment=TA_CENTER, spaceAfter=2)
            s_s = ParagraphStyle("s", fontSize=10, fontName="Helvetica",
                                  textColor=GREY, alignment=TA_CENTER, spaceAfter=2)
            n_s = ParagraphStyle("n", fontSize=13, fontName="Helvetica-Bold",
                                  textColor=colors.HexColor("#222222"),
                                  alignment=TA_CENTER, spaceAfter=4)
            story.append(Paragraph("CAFETERIA STORE", c_s))
            story.append(Paragraph("Credit Summary Slip", s_s))
            story.append(Paragraph("Printed: " + datetime.now().strftime("%B %d, %Y  %I:%M %p"), s_s))
            story.append(Spacer(1, 0.3*cm))
            story.append(HRFlowable(width="100%", thickness=2, color=RED))
            story.append(Spacer(1, 0.2*cm))
            story.append(Paragraph(name, n_s))
            story.append(Paragraph("Department: " + (dept or "-"), s_s))
            story.append(Spacer(1, 0.3*cm))
            data = [
                ["Total Utang",   "P" + "{:.2f}".format(total)],
                ["Deducted",      "P" + "{:.2f}".format(deducted)],
                ["Balance",       "P" + "{:.2f}".format(balance)],
            ]
            t = Table(data, colWidths=[7*cm, 4.5*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(0,-1), colors.HexColor("#F9F9F9")),
                ("BACKGROUND",    (1,2),(1,2),  colors.HexColor("#FFF0F0")),
                ("TEXTCOLOR",     (1,2),(1,2),  RED),
                ("FONTNAME",      (0,0),(-1,-1),"Helvetica-Bold"),
                ("FONTSIZE",      (0,0),(-1,-1), 12),
                ("GRID",          (0,0),(-1,-1), 0.5, colors.HexColor("#DDDDDD")),
                ("TOPPADDING",    (0,0),(-1,-1), 8),
                ("BOTTOMPADDING", (0,0),(-1,-1), 8),
                ("LEFTPADDING",   (0,0),(-1,-1), 12),
                ("BOX",           (0,0),(-1,-1), 1.5, RED),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.4*cm))
            story.append(HRFlowable(width="100%", thickness=1,
                                     color=colors.HexColor("#DDDDDD")))
            f_s = ParagraphStyle("f", fontSize=8, textColor=GREY, alignment=TA_CENTER)
            story.append(Paragraph("Cafe Store Admin - Credit Summary", f_s))
            doc.build(story)
            if platform.system() == "Windows":
                os.startfile(tmp.name)
            elif platform.system() == "Darwin":
                subprocess.run(["open", tmp.name])
            else:
                subprocess.run(["xdg-open", tmp.name])
            messagebox.showinfo("PDF Ready", "Credit slip opened!", parent=self)
        except ImportError:
            messagebox.showinfo("Install Required", "pip install reportlab", parent=self)
        except Exception as ex:
            messagebox.showerror("Error", str(ex), parent=self)

    def _save_sales_pdf(self):
        from tkinter import filedialog
        import platform, subprocess

        date_q = getattr(self, "sales_date_var", ctk.StringVar()).get().strip()
        period = self.sales_period.get().lower()
        if date_q:
            data         = db.get_sales_report_custom(date_q, date_q)
            period_label = date_q
        else:
            data         = db.get_sales_report(period)
            period_label = self.sales_period.get()

        fname = "Sales_Report_" + period_label.replace(" ", "_") + ".pdf"
        save_path = filedialog.asksaveasfilename(
            title="Save Sales Report as PDF",
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")],
            initialfile=fname
        )
        if not save_path:
            return

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.units import cm
            from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                             Paragraph, Spacer, HRFlowable)
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.enums import TA_CENTER

            doc = SimpleDocTemplate(save_path, pagesize=A4,
                                    topMargin=1.5*cm, bottomMargin=1.5*cm,
                                    leftMargin=2*cm, rightMargin=2*cm)
            RED  = colors.HexColor("#1565C0")
            GREY = colors.HexColor("#555555")
            story = []
            c_s = ParagraphStyle("c", fontSize=20, fontName="Helvetica-Bold",
                                  textColor=RED, alignment=TA_CENTER, spaceAfter=4)
            s_s = ParagraphStyle("s", fontSize=10, fontName="Helvetica",
                                  textColor=GREY, alignment=TA_CENTER, spaceAfter=2)
            story.append(Paragraph("CAFETERIA STORE - ADMIN", c_s))
            story.append(Paragraph("Sales Report", s_s))
            story.append(Paragraph("Period: " + period_label, s_s))
            story.append(Paragraph(
                "Generated: " + datetime.now().strftime("%B %d, %Y  %I:%M %p"), s_s))
            story.append(Spacer(1, 0.4*cm))
            story.append(HRFlowable(width="100%", thickness=2, color=RED))
            story.append(Spacer(1, 0.3*cm))
            lbl_s = ParagraphStyle("l", fontSize=9, fontName="Helvetica-Bold",
                                    textColor=GREY, alignment=TA_CENTER)
            val_s = ParagraphStyle("v", fontSize=18, fontName="Helvetica-Bold",
                                    textColor=RED, alignment=TA_CENTER)
            flat = [
                [Paragraph("TOTAL REVENUE", lbl_s),
                 Paragraph("TRANSACTIONS", lbl_s),
                 Paragraph("AVG TRANSACTION", lbl_s)],
                [Paragraph("P" + "{:.2f}".format(data["revenue"]), val_s),
                 Paragraph(str(data["count"]), val_s),
                 Paragraph("P" + "{:.2f}".format(data["avg"]), val_s)],
            ]
            t = Table(flat, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
            t.setStyle(TableStyle([
                ("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#FFF8F8")),
                ("TOPPADDING",(0,0),(-1,-1),8),
                ("BOTTOMPADDING",(0,0),(-1,-1),8),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.4*cm))
            h_s = ParagraphStyle("h", fontSize=13, fontName="Helvetica-Bold",
                                   textColor=colors.HexColor("#F5F5F5"), spaceAfter=6)
            story.append(Paragraph("Payment Method Breakdown", h_s))
            pd_data = [["Payment Method", "Amount"]]
            for m in ["Cash", "Cash (Mobile)", "Credit / Utang"]:
                amt2 = (data["by_method"].get("Cash",0) + data["by_method"].get("Cash (Mobile)",0) + data["by_method"].get("Mobile Order",0)) if m == "Cash" else data["by_method"].get(m, 0)
                pd_data.append([m, "P" + "{:.2f}".format(amt2)])
            pt = Table(pd_data, colWidths=[10*cm, 6.5*cm])
            pt.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),RED),
                ("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                ("FONTSIZE",(0,0),(-1,-1),11),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F9F9F9"),colors.white]),
                ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                ("TOPPADDING",(0,0),(-1,-1),7),
                ("BOTTOMPADDING",(0,0),(-1,-1),7),
                ("LEFTPADDING",(0,0),(-1,-1),12),
            ]))
            story.append(pt)
            story.append(Spacer(1, 0.4*cm))
            story.append(Paragraph("Items Sold", h_s))
            id_data = [["Product", "Category", "Qty", "Revenue"]]
            for name, cat, qty, rev in (data["items_sold"] or []):
                id_data.append([name, cat, str(qty), "P" + "{:.2f}".format(rev)])
            if len(id_data) == 1:
                id_data.append(["No sales data", "", "", ""])
            it = Table(id_data, colWidths=[7*cm, 4*cm, 3*cm, 2.5*cm])
            it.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),RED),
                ("TEXTCOLOR",(0,0),(-1,0),colors.white),
                ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                ("FONTSIZE",(0,0),(-1,-1),10),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F9F9F9"),colors.white]),
                ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                ("TOPPADDING",(0,0),(-1,-1),6),
                ("BOTTOMPADDING",(0,0),(-1,-1),6),
                ("LEFTPADDING",(0,0),(-1,-1),10),
                ("TEXTCOLOR",(3,1),(3,-1),RED),
                ("FONTNAME",(3,1),(3,-1),"Helvetica-Bold"),
            ]))
            story.append(it)
            story.append(Spacer(1, 0.5*cm))
            story.append(HRFlowable(width="100%", thickness=1,
                                     color=colors.HexColor("#DDDDDD")))
            f_s = ParagraphStyle("f", fontSize=8, textColor=GREY, alignment=TA_CENTER)
            story.append(Paragraph("Cafe Store Admin - Auto-generated Sales Report", f_s))
            doc.build(story)
            messagebox.showinfo("Saved!", "PDF saved to: " + save_path, parent=self)
        except ImportError:
            messagebox.showinfo("Install Required", "pip install reportlab", parent=self)
        except Exception as ex:
            messagebox.showerror("Error", str(ex), parent=self)

    # ── DELETE PAID FACULTY ─────────────────────────────────
    def _delete_paid_faculty(self, name, dept, all_rows):
        """Delete ALL credit transactions for a faculty member from both stores."""
        if not messagebox.askyesno(
                "Delete Records",
                f"Permanently delete ALL credit records for '{name}'?\n\n"
                f"⚠ This cannot be undone!",
                parent=self):
            return
        try:
            import sqlite3
            store_label = self.credit_store_var.get() if hasattr(self, "credit_store_var") else "Cafe Store"
            store_key   = "canteen" if "canteen" in store_label.lower() else "cafestore"
            # Delete from Firestore — query by customer_name only, filter in Python
            try:
                results = db._query("transactions",
                                    filters=[["customer_name","EQUAL", name]])
                for r in results:
                    d = db._parse_doc(r)
                    if d.get("store","") != store_key: continue
                    txn_id = d.get("txn_id","")
                    items = db._query("transaction_items",
                                      filters=[["txn_id","EQUAL",txn_id]])
                    for it in items:
                        dn = it.get("document",{}).get("name","")
                        if dn: db._delete_doc("transaction_items", dn.split("/")[-1])
                    dn = r.get("document",{}).get("name","")
                    if dn: db._delete_doc("transactions", dn.split("/")[-1])
            except Exception as fe:
                print(f"Firestore delete error: {fe}")
            # Delete from local SQLite cache
            try:
                import offline_db as _odb
                conn = sqlite3.connect(str(_odb.DB_PATH))
                cur  = conn.cursor()
                cur.execute(
                    "SELECT txn_id FROM transactions_local WHERE customer_name=? AND store=?",
                    (name, store_key))
                tids = [r[0] for r in cur.fetchall()]
                for tid in tids:
                    cur.execute("DELETE FROM transaction_items_local WHERE txn_id=?", (tid,))
                cur.execute(
                    "DELETE FROM transactions_local WHERE customer_name=? AND store=?",
                    (name, store_key))
                conn.commit()
                conn.close()
            except Exception as se:
                print(f"SQLite delete error: {se}")
            messagebox.showinfo("Deleted",
                                f"✓ All credit records for '{name}' deleted.",
                                parent=self)
            self._nav("credits")
        except Exception as e:
            messagebox.showerror("Error", f"Delete failed:\n{e}", parent=self)

    # ════════════════════════════════════════
    #  COOP MEMBERS — All members from all stores
    # ════════════════════════════════════════
    def _show_coop_members(self):
        page = ctk.CTkFrame(self.content, fg_color="#F5F7FA", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(4, weight=1)
        page.columnconfigure(0, weight=1)

        # ── Header ──
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 6))
        top.columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="All Coop Members",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#1A1A2E").grid(row=0, column=0, sticky="w")
        ctk.CTkButton(top, text="➕ Register Member",
                      width=160, height=36,
                      fg_color="#2E7D32", hover_color="#1B5E20",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=lambda: self._register_member_dialog(page)
                      ).grid(row=0, column=1, sticky="e")

        # ── Search + Dept filter ──
        fbar = ctk.CTkFrame(page, fg_color="#FFFFFF", corner_radius=8,
                            border_width=1, border_color="#1565C0")
        fbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 4))
        fbar.columnconfigure(1, weight=1)
        ctk.CTkLabel(fbar, text="🔍", font=ctk.CTkFont(size=14),
                     text_color="#546E7A").grid(row=0, column=0, padx=(12,4), pady=8)
        self._coop_search_var = ctk.StringVar()
        ctk.CTkEntry(fbar, textvariable=self._coop_search_var,
                     placeholder_text="Search by name or member ID...",
                     border_width=0, fg_color="#FFFFFF", height=34,
                     font=ctk.CTkFont(size=13), text_color="black",
                     placeholder_text_color="#546E7A"
                     ).grid(row=0, column=1, sticky="ew", padx=(0,8), pady=8)
        ctk.CTkFrame(fbar, fg_color="#BBDEFB", width=2, height=28
                     ).grid(row=0, column=2, padx=4)
        ctk.CTkLabel(fbar, text="Dept:",
                     font=ctk.CTkFont(size=12), text_color="#546E7A"
                     ).grid(row=0, column=3, padx=(4,2))
        self._coop_dept_var = ctk.StringVar(value="All")
        ctk.CTkOptionMenu(fbar, variable=self._coop_dept_var,
                          values=["All","CCS","COED","COAG","COM","Other"],
                          width=110, height=32,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF",
                          dropdown_text_color="#1A1A2E",
                          text_color="black", font=ctk.CTkFont(size=11),
                          command=lambda _: self._reload_coop_table()
                          ).grid(row=0, column=4, padx=(0,12), pady=8)

        # ── Column header ──
        col_hdr = ctk.CTkFrame(page, fg_color=COL_HDR, height=34, corner_radius=0)
        col_hdr.grid(row=2, column=0, sticky="ew", padx=24)
        col_hdr.pack_propagate(False)
        col_hdr.columnconfigure(1, weight=1)
        for txt, col, w in [("", 0, 40), ("NAME / MEMBER ID", 1, 0),
                             ("DEPARTMENT", 2, 140), ("CARD BARCODE", 3, 180),
                             ("ACTIONS", 4, 200)]:
            kw = {"font": ctk.CTkFont(size=11, weight="bold"),
                  "text_color": TEXT_GREY, "fg_color": "transparent", "anchor": "w"}
            if w == 0:
                ctk.CTkLabel(col_hdr, text=txt, **kw).grid(
                    row=0, column=col, sticky="w", padx=(4,4), pady=6)
            else:
                ctk.CTkLabel(col_hdr, text=txt, width=w, **kw).grid(
                    row=0, column=col, padx=4, pady=6)

        table = ctk.CTkScrollableFrame(page, fg_color="#F5F7FA",
                                        scrollbar_button_color=BTN_BLUE, corner_radius=0)
        table.grid(row=4, column=0, sticky="nsew", padx=24, pady=(0, 12))
        table.columnconfigure(0, weight=1)
        self._coop_table = table
        self._all_members_cache = []
        self._coop_search_var.trace_add("write", lambda *_: self._reload_coop_table())
        self._reload_coop_table()

    def _register_member_dialog(self, page):
        """Register a new Coop Member from Admin Dashboard."""
        import random, string
        win = ctk.CTkToplevel(self)
        win.title("Register Coop Member")
        win.grab_set()
        win.resizable(False, False)
        W, H = 420, 360
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        win.configure(fg_color="#FFFFFF")

        ctk.CTkLabel(win, text="➕  Register Coop Member",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#1565C0").pack(pady=(18,4))

        form = ctk.CTkFrame(win, fg_color="transparent")
        form.pack(fill="x", padx=24)
        form.columnconfigure(1, weight=1)

        def _row(lbl, row, ph=""):
            ctk.CTkLabel(form, text=lbl, width=120, anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#546E7A").grid(row=row, column=0, sticky="w", pady=(8,0))
            var = ctk.StringVar()
            e = ctk.CTkEntry(form, textvariable=var, placeholder_text=ph,
                             height=36, font=ctk.CTkFont(size=12))
            e.grid(row=row, column=1, sticky="ew", padx=(10,0), pady=(8,0))
            return var

        name_var = _row("Full Name:",   0, "e.g. Juan Dela Cruz")

        ctk.CTkLabel(form, text="Department:", width=120, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#546E7A").grid(row=1, column=0, sticky="w", pady=(8,0))
        dept_var = ctk.StringVar(value="CCS")
        ctk.CTkOptionMenu(form, variable=dept_var,
                          values=["CCS","COED","COAG","COM","Other"],
                          width=200, height=36,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF",
                          dropdown_text_color="#1A1A2E",
                          text_color="black",
                          font=ctk.CTkFont(size=12)
                          ).grid(row=1, column=1, sticky="w", padx=(10,0), pady=(8,0))

        # Auto-generated fields
        mid  = "MBR-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        card = "CARD-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

        mid_frame = ctk.CTkFrame(form, fg_color="#F5F5F5", corner_radius=6)
        mid_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12,0))
        ctk.CTkLabel(mid_frame, text=f"Member ID: {mid}   Card: {card}",
                     font=ctk.CTkFont(size=11), text_color="#546E7A"
                     ).pack(padx=12, pady=8)

        status_lbl = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11))
        status_lbl.pack(pady=(8,0))

        def _save():
            name = name_var.get().strip()
            dept = dept_var.get().strip()
            if not name:
                messagebox.showwarning("Required", "Please enter full name.", parent=win)
                return
            win.destroy()
            def _do():
                try:
                    db.add_loyalty_member(mid, name, dept, card, store="coop")
                    self.after(0, lambda: [
                        messagebox.showinfo("✅ Registered",
                            "Member registered!\n\nName: " + name + "\nID: " + mid + "\nCard: " + card,
                            parent=self),
                        self._reload_coop_table()
                    ])
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror(
                        "Error", str(e), parent=self))
            threading.Thread(target=_do, daemon=True).start()

        btn_f = ctk.CTkFrame(win, fg_color="transparent")
        btn_f.pack(side="bottom", pady=16)
        ctk.CTkButton(btn_f, text="💾 Register",
                      width=140, height=40,
                      fg_color="#2E7D32", hover_color="#1B5E20",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=_save).pack(side="left", padx=(0,8))
        ctk.CTkButton(btn_f, text="Cancel",
                      width=100, height=40,
                      fg_color="#757575", hover_color="#546E7A",
                      font=ctk.CTkFont(size=13),
                      command=win.destroy).pack(side="left")
        win.bind("<Return>", lambda e: _save())

    def _reload_coop_table(self):
        for w in self._coop_table.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._coop_table, text="⏳  Loading...",
                     font=ctk.CTkFont(size=14), text_color="#333333").pack(pady=40)
        def _fetch():
            all_members = []
            seen = set()
            for store in ["coop", "cafestore", "canteen"]:
                try:
                    members = db.get_all_loyalty_members(store=store) or []
                    for m in members:
                        bc = m.get("card_barcode", "")
                        if bc not in seen:
                            seen.add(bc)
                            all_members.append(m)
                except Exception:
                    pass
            all_members.sort(key=lambda m: m.get("name", ""))
            self.after(0, lambda ms=all_members: self._render_coop_table(ms))
        threading.Thread(target=_fetch, daemon=True).start()

    def _render_coop_table(self, all_members):
        self._all_members_cache = all_members
        for w in self._coop_table.winfo_children():
            w.destroy()
        search = getattr(self, "_coop_search_var", ctk.StringVar()).get().strip().lower()
        dept_f = getattr(self, "_coop_dept_var", ctk.StringVar(value="All")).get()
        members = all_members
        if search:
            members = [m for m in members
                       if search in m.get("name","").lower()
                       or search in m.get("member_id","").lower()]
        if dept_f != "All":
            members = [m for m in members if m.get("department","") == dept_f]

        if not members:
            ctk.CTkLabel(self._coop_table,
                         text="No members found." if (search or dept_f != "All") else "No members registered yet.",
                         font=ctk.CTkFont(size=14), text_color="#546E7A").pack(pady=40)
            return

        for i, m in enumerate(members):
            bg = BG_ROW if i % 2 == 0 else BG_ROW_ALT
            row = ctk.CTkFrame(self._coop_table, fg_color=bg,
                               corner_radius=6, border_width=1, border_color="#BBDEFB")
            row.pack(fill="x", pady=2)

            inner = ctk.CTkFrame(row, fg_color="transparent", height=60)
            inner.pack(fill="x"); inner.pack_propagate(False)
            inner.columnconfigure(1, weight=1)

            # Avatar
            av = ctk.CTkFrame(inner, fg_color="#1565C0", corner_radius=20, width=36, height=36)
            av.grid(row=0, column=0, padx=(10,8), pady=12)
            av.pack_propagate(False)
            ctk.CTkLabel(av, text=m.get("name","?")[0].upper(),
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")

            # Name + ID
            nf = ctk.CTkFrame(inner, fg_color="transparent")
            nf.grid(row=0, column=1, sticky="w", padx=(0,8), pady=6)
            ctk.CTkLabel(nf, text=m.get("name",""),
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#1A1A2E", anchor="w").pack(anchor="w")
            ctk.CTkLabel(nf, text="ID: " + m.get("member_id",""),
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#7B1FA2", anchor="w").pack(anchor="w")

            ctk.CTkLabel(inner, text=m.get("department",""),
                         width=140, anchor="center",
                         font=ctk.CTkFont(size=12), text_color="#546E7A"
                         ).grid(row=0, column=2, padx=4)
            ctk.CTkLabel(inner, text=m.get("card_barcode",""),
                         width=180, anchor="center",
                         font=ctk.CTkFont(size=11), text_color="#546E7A"
                         ).grid(row=0, column=3, padx=(4,4))

            # Action buttons
            act = ctk.CTkFrame(inner, fg_color="transparent", width=200)
            act.grid(row=0, column=4, padx=(4,10))
            ctk.CTkButton(act, text="✏ Edit", width=56, height=28,
                          fg_color="#1565C0", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=10, weight="bold"),
                          command=lambda mem=m: self._edit_member_dialog(mem)
                          ).pack(side="left", padx=(0,4))
            ctk.CTkButton(act, text="💳 Card", width=60, height=28,
                          fg_color="#7B1FA2", hover_color="#6A1B9A",
                          font=ctk.CTkFont(size=10, weight="bold"),
                          command=lambda mem=m: self._view_member_card(mem)
                          ).pack(side="left", padx=(0,4))
            ctk.CTkButton(act, text="🗑 Del", width=52, height=28,
                          fg_color="#C62828", hover_color="#8B0000",
                          font=ctk.CTkFont(size=10, weight="bold"),
                          command=lambda mem=m: self._delete_member(mem)
                          ).pack(side="left")

    def _edit_member_dialog(self, member):
        win = ctk.CTkToplevel(self)
        win.title("Edit Member")
        win.grab_set(); win.resizable(False, False)
        W, H = 400, 280
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        win.configure(fg_color="#FFFFFF")
        ctk.CTkLabel(win, text="✏  Edit Coop Member",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#1565C0").pack(pady=(18,10))
        form = ctk.CTkFrame(win, fg_color="transparent")
        form.pack(fill="x", padx=24)
        form.columnconfigure(1, weight=1)
        ctk.CTkLabel(form, text="Full Name:", width=100, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#546E7A").grid(row=0, column=0, sticky="w", pady=(0,6))
        name_var = ctk.StringVar(value=member.get("name",""))
        ctk.CTkEntry(form, textvariable=name_var, height=36,
                     font=ctk.CTkFont(size=12)
                     ).grid(row=0, column=1, sticky="ew", padx=(10,0), pady=(0,6))
        ctk.CTkLabel(form, text="Department:", width=100, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#546E7A").grid(row=1, column=0, sticky="w")
        dept_var = ctk.StringVar(value=member.get("department","CCS"))
        ctk.CTkOptionMenu(form, variable=dept_var,
                          values=["CCS","COED","COAG","COM","Other"],
                          width=200, height=36,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF",
                          dropdown_text_color="#1A1A2E",
                          text_color="black",
                          font=ctk.CTkFont(size=12)
                          ).grid(row=1, column=1, sticky="w", padx=(10,0))
        def _save():
            nm = name_var.get().strip()
            dp = dept_var.get().strip()
            if not nm:
                messagebox.showwarning("Required", "Name cannot be empty.", parent=win)
                return
            win.destroy()
            def _do():
                try:
                    db.update_loyalty_member(
                        member.get("member_id",""), nm, dp,
                        member.get("card_barcode",""), store="coop")
                    self.after(0, lambda: [
                        messagebox.showinfo("✅ Updated", "Member updated!", parent=self),
                        self._reload_coop_table()
                    ])
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Error", str(e), parent=self))
            threading.Thread(target=_do, daemon=True).start()
        bf = ctk.CTkFrame(win, fg_color="transparent")
        bf.pack(side="bottom", pady=16)
        ctk.CTkButton(bf, text="💾 Save", width=120, height=38,
                      fg_color="#1565C0", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=_save).pack(side="left", padx=(0,8))
        ctk.CTkButton(bf, text="Cancel", width=90, height=38,
                      fg_color="#757575", hover_color="#546E7A",
                      font=ctk.CTkFont(size=12),
                      command=win.destroy).pack(side="left")
        win.bind("<Return>", lambda e: _save())

    def _view_member_card(self, member):
        """Show loyalty card popup with Print option."""
        win = ctk.CTkToplevel(self)
        win.title("Loyalty Card")
        win.grab_set(); win.resizable(False, False)
        W, H = 400, 300
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        win.configure(fg_color="#FFFFFF")
        # Card preview
        card_f = ctk.CTkFrame(win, fg_color="#1565C0", corner_radius=14,
                              width=340, height=180)
        card_f.pack(padx=30, pady=(20,10)); card_f.pack_propagate(False)
        ctk.CTkLabel(card_f, text="ISUFST COOP LOYALTY CARD",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#BBDEFB").place(x=16, y=14)
        av2 = ctk.CTkFrame(card_f, fg_color="#FFFFFF", corner_radius=24,
                            width=48, height=48)
        av2.place(x=16, y=40); av2.pack_propagate(False)
        ctk.CTkLabel(av2, text=member.get("name","?")[0].upper(),
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#1565C0").place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(card_f, text=member.get("name",""),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=76, y=46)
        ctk.CTkLabel(card_f, text=member.get("department",""),
                     font=ctk.CTkFont(size=11),
                     text_color="#BBDEFB").place(x=76, y=72)
        ctk.CTkLabel(card_f, text="Member ID: " + member.get("member_id",""),
                     font=ctk.CTkFont(size=10),
                     text_color="#90CAF9").place(x=16, y=120)
        ctk.CTkLabel(card_f, text="Card: " + member.get("card_barcode",""),
                     font=ctk.CTkFont(size=10),
                     text_color="#90CAF9").place(x=16, y=142)
        # Buttons
        bf = ctk.CTkFrame(win, fg_color="transparent")
        bf.pack(pady=10)
        ctk.CTkButton(bf, text="🖨 Print Card", width=130, height=38,
                      fg_color="#2E7D32", hover_color="#1B5E20",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=lambda: self._print_member_card(member)
                      ).pack(side="left", padx=(0,8))
        ctk.CTkButton(bf, text="Close", width=90, height=38,
                      fg_color="#757575", hover_color="#546E7A",
                      font=ctk.CTkFont(size=12),
                      command=win.destroy).pack(side="left")

    def _print_member_card(self, member):
        """Generate PDF loyalty card for printing."""
        try:
            import tempfile, subprocess, sys
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.units import mm
            fname = tempfile.mktemp(suffix=".pdf")
            c = rl_canvas.Canvas(fname, pagesize=(85*mm, 54*mm))
            c.setFillColorRGB(0.08, 0.39, 0.73)
            c.rect(0, 0, 85*mm, 54*mm, fill=1, stroke=0)
            c.setFillColorRGB(1,1,1)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(5*mm, 46*mm, "ISUFST COOP LOYALTY CARD")
            c.setFont("Helvetica-Bold", 13)
            c.drawString(5*mm, 36*mm, member.get("name",""))
            c.setFont("Helvetica", 9)
            c.drawString(5*mm, 29*mm, member.get("department",""))
            c.setFont("Helvetica", 8)
            c.drawString(5*mm, 18*mm, "Member ID: " + member.get("member_id",""))
            c.drawString(5*mm, 12*mm, "Card: " + member.get("card_barcode",""))
            c.save()
            if sys.platform == "win32":
                os.startfile(fname)
            else:
                subprocess.Popen(["xdg-open", fname])
        except ImportError:
            messagebox.showinfo("Print Card",
                "Member ID: " + member.get("member_id","") + "\n" +
                "Card: " + member.get("card_barcode","") + "\n\n" +
                "(Install reportlab for PDF printing)", parent=self)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _delete_member(self, member):
        name = member.get("name","this member")
        if not messagebox.askyesno("Delete Member",
                "Delete " + name + "?\n\nThis cannot be undone.", parent=self):
            return
        def _do():
            try:
                db.delete_loyalty_member(
                    member.get("member_id",""),
                    member.get("card_barcode",""),
                    store="coop")
                self.after(0, lambda: [
                    messagebox.showinfo("Deleted", name + " removed!", parent=self),
                    self._reload_coop_table()
                ])
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e), parent=self))
        threading.Thread(target=_do, daemon=True).start()

    # ════════════════════════════════════════
    #  F-KEY SHORTCUTS
    # ════════════════════════════════════════
    def _bind_fkeys(self):
        self.bind("<F1>",  lambda e: self._nav("overview"))
        self.bind("<F2>",  lambda e: self._nav("sales"))
        self.bind("<F3>",  lambda e: self._nav("coop"))
        self.bind("<F4>",  lambda e: self._nav("credits"))
        self.bind("<F5>",  lambda e: self._nav("history"))
        self.bind("<F12>", lambda e: self._logout())
        # Show F-key help on F1 only when already on overview
        self.bind("<Escape>", lambda e: self._logout())

    # ── LOGOUT / EXIT ────────────────────────────────────────
    # ════════════════════════════════════════
    #  ☁️ BACKUP & SYNC
    # ════════════════════════════════════════
    # ════════════════════════════════════════════════════════════
    #  ☁️ BACKUP & SYNC PANEL (slide from sidebar)
    # ════════════════════════════════════════════════════════════
    def _logout(self):
        if messagebox.askyesno("Exit", "Are you sure you want to exit?", parent=self):
            self.destroy()
            if self.login_window:
                self.login_window.deiconify()


if __name__ == "__main__":
    import splash, login

    def _open_admin(username, role, login_win):
        app = AdminDashboard(login_window=login_win)
        app.mainloop()

    def _after_splash():
        # LOGIN DISABLED FOR TESTING — re-enable before deployment
        _open_admin("admin", "admin", None)
        # login.require_login(
        #     allowed_roles=["admin"],
        #     on_success=_open_admin
        # )

    splash.show_splash(on_done=_after_splash, duration=3.0)