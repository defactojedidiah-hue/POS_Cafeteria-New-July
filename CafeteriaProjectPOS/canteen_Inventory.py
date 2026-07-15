import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
import database as db
import offline_db
import auto_sync
import threading
import sys, subprocess
import os

# ── Auto-install reportlab if missing ──
try:
    import reportlab
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "reportlab"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ════════════════════════════════════════════════════════════
#  CODE128 B BARCODE ENGINE — pure Python, scanner-readable
# ════════════════════════════════════════════════════════════
_C128B = [
    (2,1,2,2,2,2),(2,2,2,1,2,2),(2,2,2,2,2,1),(1,2,1,2,2,3),
    (1,2,1,3,2,2),(1,3,1,2,2,2),(1,2,2,2,1,3),(1,2,2,3,1,2),
    (1,3,2,2,1,2),(2,2,1,2,1,3),(2,2,1,3,1,2),(2,3,1,2,1,2),
    (1,1,2,2,3,2),(1,2,2,1,3,2),(1,2,2,2,3,1),(1,1,3,2,2,2),
    (1,2,3,1,2,2),(1,2,3,2,2,1),(2,2,3,2,1,1),(2,2,1,1,3,2),
    (2,2,1,2,3,1),(2,1,3,2,1,2),(2,2,3,1,1,2),(3,1,2,1,3,1),
    (3,1,1,2,2,2),(3,2,1,1,2,2),(3,2,1,2,2,1),(3,1,2,2,1,2),
    (3,2,2,1,1,2),(3,2,2,2,1,1),(2,1,2,1,2,3),(2,1,2,3,2,1),
    (2,3,2,1,2,1),(1,1,1,3,2,3),(1,3,1,1,2,3),(1,3,1,3,2,1),
    (1,1,2,3,1,3),(1,3,2,1,1,3),(1,3,2,3,1,1),(2,1,1,3,1,3),
    (2,3,1,1,1,3),(2,3,1,3,1,1),(1,1,3,1,2,3),(1,1,3,3,2,1),
    (1,3,3,1,2,1),(1,1,2,1,3,3),(1,1,2,3,3,1),(1,3,2,1,3,1),
    (3,1,3,1,2,1),(2,1,1,3,3,1),(2,3,1,1,3,1),(2,1,3,1,1,3),
    (2,1,3,3,1,1),(2,1,3,1,3,1),(3,1,1,1,2,3),(3,1,1,3,2,1),
    (3,3,1,1,2,1),(3,1,2,1,1,3),(3,1,2,3,1,1),(3,3,2,1,1,1),
    (3,1,4,1,1,1),(2,2,1,4,1,1),(4,3,1,1,1,1),(1,1,1,2,2,4),
    (1,1,1,4,2,2),(1,2,1,1,2,4),(1,2,1,4,2,1),(1,4,1,1,2,2),
    (1,4,1,2,2,1),(1,1,2,2,1,4),(1,1,2,4,1,2),(1,2,2,1,1,4),
    (1,2,2,4,1,1),(1,4,2,1,1,2),(1,4,2,2,1,1),(2,4,1,2,1,1),
    (2,2,1,1,1,4),(4,1,3,1,1,1),(2,4,1,1,1,2),(1,3,4,1,1,1),
    (1,1,1,2,4,2),(1,2,1,1,4,2),(1,2,1,2,4,1),(1,1,4,2,1,2),
    (1,2,4,1,1,2),(1,2,4,2,1,1),(4,1,2,1,1,2),(4,2,2,1,1,1),
    (4,1,1,2,1,2),(4,2,1,1,1,2),(4,2,1,2,1,1),(2,1,2,1,4,1),
    (2,1,4,1,2,1),(4,1,2,1,2,1),(1,1,2,1,2,4),
]
_C128B_START = (2,1,1,4,1,2)
_C128B_STOP  = (2,3,3,1,1,1,2)


def _encode_code128b(text):
    """Return list of module widths for Code128 B (bar/space alternating, starts bar)."""
    modules = list(_C128B_START)
    check   = 104
    for i, ch in enumerate(text):
        v = ord(ch) - 32
        if not (0 <= v < len(_C128B)):
            continue
        modules.extend(_C128B[v])
        check += v * (i + 1)
    chk_v = check % 103
    if 0 <= chk_v < len(_C128B):
        modules.extend(_C128B[chk_v])
    modules.extend(_C128B_STOP)
    modules.append(2)
    return modules


def _draw_code128_on_canvas(tk_canvas, text, canvas_width=500,
                             bar_height=70, y_offset=8):
    """Draw a real, scanner-readable Code128 B barcode on a tkinter Canvas."""
    modules   = _encode_code128b(text)
    total_mod = sum(modules)
    # Cap at 2px per module — keeps bars narrow enough for phone scanners
    mod_px    = min(2.0, (canvas_width - 28) / max(total_mod, 1))
    mod_px    = max(1.0, mod_px)
    # Center the barcode on the canvas
    actual_w  = sum(max(1, round(w * mod_px)) for w in modules)
    x         = (canvas_width - actual_w) // 2
    for i, w in enumerate(modules):
        px = max(1, round(w * mod_px))
        if i % 2 == 0:
            tk_canvas.create_rectangle(x, y_offset, x + px,
                                        y_offset + bar_height,
                                        fill="#000000", outline="")
        x += px
    tk_canvas.create_text(canvas_width // 2, y_offset + bar_height + 13,
                           text=text, fill="#1A1A2E",
                           font=("Courier", 9, "bold"), anchor="center")


def _gen_barcode_pil(text, width=400, height=90):
    """Generate Code128 barcode as PIL Image via python-barcode. Returns None on failure."""
    try:
        import barcode as _bc
        from barcode.writer import ImageWriter as _IW
        import io as _io
        from PIL import Image as _PI
        opts = {"module_height": 10.0, "module_width": 0.38,
                "quiet_zone": 3.5, "font_size": 9, "text_distance": 4.0,
                "background": "white", "foreground": "black", "write_text": True}
        buf = _io.BytesIO()
        _bc.get_barcode_class("code128")(text, writer=_IW()).write(buf, options=opts)
        buf.seek(0)
        img = _PI.open(buf).convert("RGB")
        new_h = int(img.height * width / img.width)
        return img.resize((width, max(new_h, height)), _PI.LANCZOS)
    except Exception:
        return None
BG_DARK = "#F5F5F5"
BG_PANEL = "#FFFFFF"
BG_ROW = "#F0F4F8"
BG_ROW_ALT = "#E8EEF4"
BG_SIDEBAR = "#E3F2FD"
HEADER_RED = "#1565C0"
ACCENT_RED = "#1976D2"
TEXT_WHITE = "#1A1A2E"
TEXT_GREY = "#546E7A"
COL_HDR = "#BBDEFB"
BTN_BLUE = "#1565C0"
GREEN = "#2E7D32"
ORANGE = "#FF6D00"
SIDEBAR_W = 72


# ══════════════════════════════════════════════════════════════
#  HELPER: safely unpack a credit row regardless of tuple size
#  BUG FIX: credit rows are now always 7 fields:
#    (txn_id, dt, total, customer_name, department, buyer_type, item_count)
#  This helper prevents "too many values to unpack" errors.
# ══════════════════════════════════════════════════════════════
def _unpack_credit_row(r):
    """
    Safely unpack a credit row tuple.
    Returns: (txn_id, dt, total, customer_name, department, buyer_type, item_count)
    """
    if len(r) >= 7:
        return r[0], r[1], r[2], r[3], r[4], r[5], r[6]
    elif len(r) == 6:
        # Old format without buyer_type — pad with empty string
        return r[0], r[1], r[2], r[3], r[4], "", r[5]
    else:
        # Fallback for unexpected formats
        vals = list(r) + [""] * 7
        return vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], vals[6]


# ══════════════════════════════════════════════════════════════
#  HELPER: safely unpack a full transaction row
#  Full rows are 11 fields:
#    (txn_id, dt, total, method, cash, change,
#     customer_name, department, buyer_type, item_names, item_count)
# ══════════════════════════════════════════════════════════════
def _unpack_txn_row(r):
    """
    Safely unpack a full transaction row.
    Returns: (txn_id, dt, total, method, cash, change,
              customer_name, department, buyer_type, item_names, item_count)
    """
    if len(r) >= 11:
        return r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]
    elif len(r) == 10:
        # Missing buyer_type — insert empty string at index 8
        return r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], "", r[8], r[9]
    else:
        vals = list(r) + ["", "", 0]
        return vals[0], vals[1], vals[2], vals[3], vals[4], vals[5], vals[6], vals[7], vals[8], vals[9], vals[10]


class CanteenInventoryApp(ctk.CTk):
    def __init__(self, login_window=None):
        super().__init__()
        self.login_window = login_window
        self.title("Canteen — Inventory")
        self.attributes("-fullscreen", True)
        self.state("zoomed")
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(fg_color="#F5F5F5")
        self.resizable(True, True)
        db.init_db()
        self._build_header()
        self._build_layout()
        self._nav("sales")
        # Start background auto-sync watcher
        auto_sync.start(store="canteen")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        auto_sync.stop()
        self.destroy()
        if self.login_window:
            try:
                self.login_window.deiconify()
            except Exception:
                pass

    # ── HEADER ──────────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color="#1565C0", height=80, corner_radius=0)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        import os
        try:
            from PIL import Image
            PIL_OK = True
        except ImportError:
            PIL_OK = False

        base = os.path.dirname(os.path.abspath(__file__))

        fpath_isufst = os.path.join(base, "isufstlogo.png")
        try:
            if PIL_OK and os.path.exists(fpath_isufst):
                img = Image.open(fpath_isufst).resize((62, 62), Image.LANCZOS)
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
                      command=self._exit_app
                      ).pack(side="right", padx=(8, 0))

        self.clock_lbl = ctk.CTkLabel(right, text="",
                                      font=ctk.CTkFont(size=12, weight="bold"),
                                      text_color="white", justify="right")
        self.clock_lbl.pack(side="right", padx=(0, 8))

        fpath_ccs = os.path.join(base, "ccslogo.png")
        try:
            if PIL_OK and os.path.exists(fpath_ccs):
                img = Image.open(fpath_ccs).resize((62, 62), Image.LANCZOS)
                photo = ctk.CTkImage(light_image=img, dark_image=img, size=(62, 62))
                ctk.CTkLabel(right, image=photo, text="",
                             fg_color="transparent").pack(side="right", padx=(0, 6), pady=8)
        except Exception:
            pass

        center = ctk.CTkFrame(hdr, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")
        self.hdr_title = ctk.CTkLabel(
            center, text="INVENTORY MANAGEMENT",
            font=ctk.CTkFont(family="Georgia", size=24, weight="bold"),
            text_color="white")
        self.hdr_title.pack()
        self.hdr_sub_lbl = ctk.CTkLabel(
            center, text="Canteen",
            font=ctk.CTkFont(family="Georgia", size=12),
            text_color="#BBDEFB")
        self.hdr_sub_lbl.pack()

        self._tick()

    def _tick(self):
        now = datetime.now()
        self.clock_lbl.configure(
            text=f"{now.strftime('%a, %b %d, %Y')}  {now.strftime('%I:%M %p')}")
        self.after(1000, self._tick)

    # ── LAYOUT ──────────────────────────────────────────────────
    def _build_layout(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_sidebar(body)

        self.content = ctk.CTkFrame(body, fg_color="#F5F5F5", corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

    # ── SIDEBAR ─────────────────────────────────────────────────
    def _build_sidebar(self, parent):
        sb = ctk.CTkFrame(parent, fg_color="#E3F2FD",
                          width=SIDEBAR_W, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.pack_propagate(False)

        self.nav_btns = {}
        nav_items = [
            ("sales",   "📊", "Sales"),
            ("stock",   "📦", "Stock"),
            ("loyalty", "⭐", "Member"),
            ("credit",  "👤", "Credit"),
            ("member",  "🧾", "Mbr Txn"),
            ("orders",  "📱", "Orders"),
            ("history", "🕐", "History"),
        ]
        for key, icon, label in nav_items:
            f = ctk.CTkFrame(sb, fg_color="transparent", cursor="hand2",
                             width=SIDEBAR_W, height=64)
            f.pack(fill="x")
            f.pack_propagate(False)

            icon_lbl = ctk.CTkLabel(f, text=icon, font=ctk.CTkFont(size=18),
                                    text_color="#546E7A")
            icon_lbl.place(relx=0.5, rely=0.35, anchor="center")
            text_lbl = ctk.CTkLabel(f, text=label,
                                    font=ctk.CTkFont(size=9, weight="bold"),
                                    text_color="#546E7A")
            text_lbl.place(relx=0.5, rely=0.75, anchor="center")

            for widget in (f, icon_lbl, text_lbl):
                widget.bind("<Button-1>", lambda e, k=key: self._nav(k))

            self.nav_btns[key] = (f, icon_lbl, text_lbl)

        # ── ☁️ Backup button at bottom of sidebar ──
        self._backup_panel_open = False
        self._sidebar_parent = parent  # store for later use
        ctk.CTkButton(sb, text="☁️\nBackup",
                      width=SIDEBAR_W-8, height=52,
                      fg_color="transparent", hover_color="#BBDEFB",
                      text_color="#1565C0",
                      font=ctk.CTkFont(size=10, weight="bold"),
                      corner_radius=6,
                      command=self._on_backup_btn_click
                      ).pack(side="bottom", pady=(0,4))

    # ════════════════════════════════════════════════════════════
    #  ☁️ BACKUP & SYNC PANEL
    # ════════════════════════════════════════════════════════════
    def _on_backup_btn_click(self):
        if self._backup_panel_open:
            if hasattr(self, "_backup_panel_frame") and \
               self._backup_panel_frame.winfo_exists():
                self._backup_panel_frame.destroy()
            self._backup_panel_open = False
        else:
            self._backup_panel_open = True
            self._build_backup_panel()

    def _build_backup_panel(self):
        import json, os, sqlite3
        PANEL_W  = 290
        SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "backup_settings.json")

        def _load():
            try:
                with open(SETTINGS) as f: return json.load(f)
            except Exception:
                return {"last_backup":"Never","auto_backup":False,"auto_sync":True}

        def _save(d):
            try:
                with open(SETTINGS,"w") as f: json.dump(d,f,indent=2)
            except Exception as e:
                print(f"backup_settings save error: {e}")

        bk = _load()

        # ── Panel frame ──
        panel = ctk.CTkFrame(self._sidebar_parent, fg_color="#F5F7FA",
                             width=PANEL_W, corner_radius=0,
                             border_width=1, border_color="#E0E0E0")
        panel.grid(row=0, column=0, sticky="ns", padx=(SIDEBAR_W, 0))
        panel.grid_propagate(False)
        self._backup_panel_frame = panel

        # ── Header ──
        hdr = ctk.CTkFrame(panel, fg_color="#1565C0", height=46, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="☁️  Backup & Sync",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").place(x=12, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="✕", width=30, height=30,
                      fg_color="#8B0000", hover_color="#5D0000",
                      text_color="white", font=ctk.CTkFont(size=12),
                      corner_radius=4,
                      command=self._on_backup_btn_click
                      ).place(relx=1.0, x=-8, rely=0.5, anchor="e")

        # ── Status ──
        online = db.has_internet()
        st_f = ctk.CTkFrame(panel, fg_color="#FFFFFF", corner_radius=8,
                            border_width=1, border_color="#BBDEFB")
        st_f.pack(fill="x", padx=10, pady=(10,4))
        ctk.CTkLabel(st_f,
                     text="🌐 Online" if online else "📴 Offline",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#2E7D32" if online else "#C62828"
                     ).pack(side="left", padx=10, pady=8)
        last_lbl = ctk.CTkLabel(st_f,
                                 text=f"Last: {bk.get('last_backup','Never')}",
                                 font=ctk.CTkFont(size=9), text_color="#546E7A")
        last_lbl.pack(side="right", padx=8)

        btn_kw = dict(height=40, corner_radius=8,
                      font=ctk.CTkFont(size=12, weight="bold"),
                      text_color="white")

        # ── Status label for backup/restore feedback ──
        status_lbl = ctk.CTkLabel(panel, text="", font=ctk.CTkFont(size=11),
                                   text_color="#546E7A", wraplength=220)
        status_lbl.pack(fill="x", padx=10, pady=(0,4))

        def _show_status(msg, success=False, error=False):
            color = "#2E7D32" if success else ("#C62828" if error else "#546E7A")
            try:
                status_lbl.configure(text=msg, text_color=color)
            except Exception:
                pass

        # ── Backup button ──
        def _do_backup():
            if not db.has_internet():
                messagebox.showwarning("Offline",
                    "No internet.\nConnect and try again.", parent=self)
                return
            bkp_btn.configure(text="⏳ Backing up...", state="disabled")
            panel.update()
            _show_status("⏳  Backup in progress...")
            def _bg():
                try:
                    _run_backup()
                    dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    bk["last_backup"] = dt
                    _save(bk)
                    def _on_done():
                        try: bkp_btn.configure(text="☁️  Backup Database", state="normal")
                        except Exception: pass
                        try: last_lbl.configure(text=f"Last: {dt}")
                        except Exception: pass
                        _show_status(f"✅  Backup complete! {dt}", success=True)
                    self.after(0, _on_done)
                except Exception as e:
                    def _on_err():
                        try: bkp_btn.configure(text="☁️  Backup Database", state="normal")
                        except Exception: pass
                        _show_status(f"❌  Backup failed: {e}", error=True)
                    self.after(0, _on_err)
            threading.Thread(target=_bg, daemon=True).start()

        bkp_btn = ctk.CTkButton(panel, text="☁️  Backup Database",
                                 fg_color="#1565C0", hover_color="#1976D2",
                                 command=_do_backup, **btn_kw)
        bkp_btn.pack(fill="x", padx=10, pady=(0,6))

        # ── Restore button ──
        def _do_restore():
            if not db.has_internet():
                messagebox.showwarning("Offline",
                    "No internet.\nConnect and try again.", parent=self)
                return
            if not messagebox.askyesno("Restore",
                "⚠️ Replace local data with Firestore?\n\nContinue?",
                parent=self):
                return
            rst_btn.configure(text="⏳ Restoring...", state="disabled")
            panel.update()
            _show_status("⏳  Restore in progress...")
            def _bg():
                try:
                    _run_restore()
                    self.after(0, lambda: [
                        rst_btn.configure(text="🔄  Restore Database",
                                          state="normal"),
                        _show_status("✅  Restore complete!",
                                                  success=True),
                        self._nav("stock") if hasattr(self, "_nav") else None
                    ])
                except Exception as e:
                    self.after(0, lambda: [
                        rst_btn.configure(text="🔄  Restore Database",
                                          state="normal"),
                        _show_status(f"❌  Restore failed: {e}",
                                                  error=True)
                    ])
            threading.Thread(target=_bg, daemon=True).start()

        rst_btn = ctk.CTkButton(panel, text="🔄  Restore Database",
                                 fg_color="#546E7A", hover_color="#37474F",
                                 command=_do_restore, **btn_kw)
        rst_btn.pack(fill="x", padx=10, pady=(0,6))

        # ── DB Stats ──
        ctk.CTkFrame(panel, fg_color="#E0E0E0", height=1
                     ).pack(fill="x", padx=10, pady=6)
        st2 = ctk.CTkFrame(panel, fg_color="#FFFFFF", corner_radius=8,
                           border_width=1, border_color="#E0E0E0")
        st2.pack(fill="x", padx=10)
        ctk.CTkLabel(st2, text="🗄️ Local Database",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#546E7A").pack(anchor="w", padx=12, pady=(8,2))
        try:
            conn = sqlite3.connect(str(offline_db.DB_PATH))
            cur  = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM transactions_local"); t = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM products_cache");     p = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM transactions_local WHERE sync_status IN ('pending','failed')"); pending = cur.fetchone()[0]
            conn.close()
            ctk.CTkLabel(st2, text=f"  Transactions: {t}",
                         font=ctk.CTkFont(size=11), text_color="#546E7A"
                         ).pack(anchor="w", padx=12)
            ctk.CTkLabel(st2, text=f"  Products: {p}",
                         font=ctk.CTkFont(size=11), text_color="#546E7A"
                         ).pack(anchor="w", padx=12)
            pend_color = "#C62828" if pending > 0 else "#2E7D32"
            ctk.CTkLabel(st2, text=f"  ⏳ Pending sync: {pending}",
                         font=ctk.CTkFont(size=11, weight="bold"), text_color=pend_color
                         ).pack(anchor="w", padx=12, pady=(0,8))
        except Exception as e:
            ctk.CTkLabel(st2, text=f"  DB error: {e}",
                         font=ctk.CTkFont(size=9), text_color="#C62828"
                         ).pack(anchor="w", padx=12, pady=(0,8))

        # ── Backup logic ──
        def _run_backup():
            conn = sqlite3.connect(str(offline_db.DB_PATH))
            conn.row_factory = sqlite3.Row
            cur  = conn.cursor()
            this_store = "canteen"

            # ── Step 0: Delete existing Firestore transactions for this store ──
            # So deleted local transactions also disappear from Firestore
            try:
                results = db._query("transactions",
                                    filters=[["store","EQUAL", this_store]])
                for r in results:
                    dn = r.get("document",{}).get("name","")
                    if dn:
                        txn_id = db._parse_doc(r).get("txn_id","")
                        # Delete items first
                        try:
                            items = db._query("transaction_items",
                                             filters=[["txn_id","EQUAL",txn_id]])
                            for it in items:
                                idn = it.get("document",{}).get("name","")
                                if idn: db._delete_doc("transaction_items", idn.split("/")[-1])
                        except Exception:
                            pass
                        db._delete_doc("transactions", dn.split("/")[-1])
            except Exception as e:
                print(f"Firestore pre-clear error: {e}")

            BATCH = 400
            cur.execute("SELECT * FROM transactions_local")
            writes = []; synced_ids = []
            for row in cur.fetchall():
                d = dict(row); txn_id = d.get("txn_id","")
                if not txn_id: continue
                synced_ids.append(txn_id)
                writes.append(db._make_batch_upsert("transactions", txn_id, {
                    "txn_id":txn_id,"datetime":d.get("dt",""),
                    "total":float(d.get("total",0)),"payment_method":d.get("method",""),
                    "cash_given":float(d.get("cash",0)),"change_given":float(d.get("change_amount",0)),
                    "customer_name":d.get("customer_name",""),"department":d.get("department",""),
                    "buyer_type":d.get("buyer_type",""),
                    "store":d.get("store","canteen"),"item_count":0,
                }))
                if len(writes)>=BATCH: db._batch_write(writes); writes=[]
            if writes: db._batch_write(writes); writes=[]
            print(f"[Backup] {len(synced_ids)} transactions done")
            # ── Batch transaction items ──
            cur.execute("SELECT * FROM transaction_items_local")
            writes = []
            for row in cur.fetchall():
                d = dict(row)
                doc_id = f"{d.get('txn_id','')}__{d.get('id','')}"
                writes.append(db._make_batch_upsert("transaction_items", doc_id, {
                    "txn_id":d.get("txn_id",""),"barcode":d.get("barcode",""),
                    "name":d.get("name",""),"category":d.get("category",""),
                    "price":float(d.get("price",0)),"qty":int(d.get("qty",0)),
                }))
                if len(writes)>=BATCH: db._batch_write(writes); writes=[]
            if writes: db._batch_write(writes); writes=[]
            print("[Backup] Items done")
            # ── Batch products ──
            cur.execute("SELECT * FROM products_cache")
            for row in cur.fetchall():
                d = dict(row); store=d.get("store","canteen"); bc=d.get("barcode","")
                writes.append(db._make_batch_upsert("products", f"{store}_{bc}", {
                    "barcode":bc,"name":d.get("name",""),"category":d.get("category",""),
                    "price":float(d.get("price",0)),"stock":int(d.get("stock",0)),
                    "store":store,"is_daily":int(d.get("is_daily",0)),
                    "date_added":d.get("date_added",""),"image_url":d.get("image_url","") or "",
                }))
                if len(writes)>=BATCH: db._batch_write(writes); writes=[]
            if writes: db._batch_write(writes); writes=[]
            print("[Backup] Products done")

            # ── Backup loyalty members (shared coop members) ──
            cur.execute("SELECT * FROM loyalty_members")
            for row in cur.fetchall():
                d = dict(row)
                mid = d.get("member_id","")
                bc  = d.get("card_barcode","")
                doc_id = f"{d.get('store','coop')}_{mid}"
                try:
                    db._set_doc("loyalty_members", doc_id, {
                        "member_id":    mid,
                        "name":         d.get("name",""),
                        "department":   d.get("department",""),
                        "card_barcode": bc,
                        "store":        d.get("store","coop"),
                    })
                except Exception as e:
                    print(f"Backup member error: {e}")

            # ── Mark ALL transactions as synced after backup ──
            from datetime import datetime
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for txn_id in synced_ids:
                try:
                    cur.execute("""
                        UPDATE transactions_local
                        SET sync_status='synced', sync_error='', synced_at=?
                        WHERE txn_id=?
                    """, (now, txn_id))
                except Exception as e:
                    print(f"Mark synced error: {e}")
            conn.commit()
            conn.close()

        def _run_restore():
            import sqlite3
            # ── Restore products DIRECTLY from Firestore (not from SQLite cache) ──
            for store in ["cafestore","canteen"]:
                try:
                    results = db._query("products", filters=[["store","EQUAL",store]])
                    rows = []
                    for r in results:
                        d = db._parse_doc(r)
                        rows.append((
                            d.get("barcode",""), d.get("name",""), d.get("category",""),
                            float(d.get("price",0)), int(d.get("stock",0)),
                            int(d.get("is_daily",0)), d.get("date_added",""),
                            d.get("image_url","") or "",
                        ))
                    offline_db.save_products_cache(rows, store)
                    print(f"[Restore] Products {store}: {len(rows)} items")
                except Exception as e:
                    print(f"Restore products {store}: {e}")
            # ── Restore loyalty members ──
            for store in ["coop","cafestore","canteen"]:
                try:
                    results = db._query("loyalty_members",
                                        filters=[["store","EQUAL",store]])
                    members = []
                    for r in results:
                        d = db._parse_doc(r)
                        members.append({
                            "member_id":    d.get("member_id",""),
                            "name":         d.get("name",""),
                            "department":   d.get("department",""),
                            "card_barcode": d.get("card_barcode",""),
                        })
                    offline_db.cache_loyalty_members(members, store)
                    print(f"[Restore] Members {store}: {len(members)} members")
                except Exception as e:
                    print(f"Restore loyalty {store}: {e}")
            # Restore ALL transactions from Firestore → SQLite
            for store in ["cafestore","canteen"]:
                try:
                    results = db._query("transactions",
                                        filters=[["store","EQUAL",store]])
                    conn = sqlite3.connect(str(offline_db.DB_PATH), timeout=30)
                    cur  = conn.cursor()
                    for r in results:
                        d = db._parse_doc(r)
                        txn_id = d.get("txn_id","")
                        if not txn_id: continue
                        dt_val = d.get("datetime","") or d.get("dt","") or ""
                        cur.execute("""
                            INSERT OR REPLACE INTO transactions_local
                            (txn_id, dt, total, method, cash, change_amount,
                             customer_name, department, buyer_type, store,
                             sync_status, created_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?,'synced',?)
                        """, (
                            txn_id,
                            dt_val,
                            float(d.get("total",0)),
                            d.get("payment_method",""),
                            float(d.get("cash_given",0)),
                            float(d.get("change_given",0)),
                            d.get("customer_name",""),
                            d.get("department",""),
                            d.get("buyer_type",""),
                            store,
                            dt_val or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        ))
                    conn.commit(); conn.close()
                    print(f"Restored transactions for {store}")
                except Exception as e:
                    print(f"Restore transactions {store}: {e}")

            # ── Restore salary deductions from Firestore ──
            try:
                import time; time.sleep(0.5)  # wait for transactions conn to close
                results = db._query("salary_deductions")
                for r in results:
                    d = db._parse_doc(r)
                    doc_id = d.get("doc_id","") or r.get("document",{}).get("name","").split("/")[-1]
                    if not doc_id: continue
                    offline_db.save_deduction_local(
                        doc_id,
                        d.get("faculty",""),
                        d.get("department",""),
                        float(d.get("amount",0)),
                        d.get("note",""),
                        d.get("datetime",""),
                    )
                print(f"Restored {len(results)} deduction(s).")
            except Exception as e:
                print(f"Restore deductions: {e}")

    def _highlight_nav(self, key):
        for k, (f, icon_lbl, text_lbl) in self.nav_btns.items():
            if k == key:
                f.configure(fg_color="#1976D2")
                icon_lbl.configure(text_color="white")
                text_lbl.configure(text_color="white")
            else:
                f.configure(fg_color="transparent")
                icon_lbl.configure(text_color="#546E7A")
                text_lbl.configure(text_color="#546E7A")

    def _nav(self, key):
        self._highlight_nav(key)
        for w in self.content.winfo_children():
            w.destroy()
        if key == "sales":
            self.hdr_title.configure(text="SALES OVERVIEW")
            self._show_sales_report()
        elif key == "stock":
            self.hdr_title.configure(text="INVENTORY MANAGEMENT")
            self._show_stock()
        elif key == "history":
            self.hdr_title.configure(text="TRANSACTION HISTORY")
            self._show_history()
        elif key == "credit":
            self.hdr_title.configure(text="CREDIT / UTANG MONITOR")
            self._show_credit()
        elif key == "member":
            self.hdr_title.configure(text="COOP MEMBER TRANSACTIONS")
            self._show_member_dashboard()
        elif key == "loyalty":
            self.hdr_title.configure(text="COOP MEMBER LOYALTY CARDS")
            self._show_loyalty_dashboard()
        elif key == "orders":
            self.hdr_title.configure(text="📱 MOBILE ORDERS")
            self._show_mobile_orders()

    # ════════════════════════════════════════════════════════════
    #  STOCK PAGE
    # ════════════════════════════════════════════════════════════
    def _show_stock(self):
        page = ctk.CTkFrame(self.content, fg_color="#F5F5F5", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(3, weight=1)
        page.columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(page, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 0))
        title_row.columnconfigure(0, weight=1)

        ctk.CTkLabel(title_row, text="Inventory Management",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#1A1A2E").grid(row=0, column=0, sticky="w")

        btn_row = ctk.CTkFrame(title_row, fg_color="transparent")
        btn_row.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(btn_row, text="🖨  Print Stocks", width=140, height=36,
                      fg_color="#2E7D32", hover_color="#1B5E20",
                      text_color="white",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8,
                      command=self._print_stock_list
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="🗑  Delete Selected", width=150, height=36,
                      fg_color="#5D0000", hover_color="#8B0000",
                      text_color="white",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8,
                      command=self._delete_selected_products
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="＋  Add Product",
                      height=36, width=145,
                      fg_color=BTN_BLUE, hover_color="#1976D2",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      corner_radius=8,
                      command=self._add_product_dialog
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="＋  Add Item/Barcode",
                      height=36, width=165,
                      fg_color="#7B1FA2", hover_color="#6A1B9A",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      corner_radius=8,
                      command=self._generate_barcode_dialog
                      ).pack(side="left")

        filters = ctk.CTkFrame(page, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", padx=24, pady=(12, 0))
        filters.columnconfigure(0, weight=1)

        search_wrap = ctk.CTkFrame(filters, fg_color="#FFFFFF", corner_radius=8,
                                   border_width=1, border_color="#1565C0")
        search_wrap.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        search_wrap.columnconfigure(1, weight=1)
        ctk.CTkLabel(search_wrap, text="🔍", font=ctk.CTkFont(size=14),
                     text_color="#546E7A").grid(row=0, column=0, padx=(12, 4))
        self.stock_search = ctk.StringVar()
        self.stock_search.trace_add("write", lambda *_: self._reload_stock())
        ctk.CTkEntry(search_wrap, textvariable=self.stock_search,
                     placeholder_text="Search by name or barcode...",
                     border_width=0, fg_color="transparent", height=40,
                     font=ctk.CTkFont(size=13), text_color="black",
                     placeholder_text_color="#546E7A"
                     ).grid(row=0, column=1, sticky="ew", padx=(0, 8))

        cats = ["All Categories"] + db.get_categories()
        self.cat_var = ctk.StringVar(value="All Categories")

        # ── Custom scrollable category dropdown (shows 5 at a time) ──
        cat_btn_frame = ctk.CTkFrame(filters, fg_color="#FFFFFF", corner_radius=8,
                                     border_width=1, border_color="#1565C0",
                                     width=170, height=40)
        cat_btn_frame.grid(row=0, column=1, padx=(0, 8))
        cat_btn_frame.pack_propagate(False)
        cat_btn_frame.columnconfigure(0, weight=1)

        self._cat_lbl = ctk.CTkLabel(cat_btn_frame, textvariable=self.cat_var,
                                      fg_color="transparent", text_color="black",
                                      font=ctk.CTkFont(size=12), anchor="w",
                                      cursor="hand2")
        self._cat_lbl.grid(row=0, column=0, sticky="ew", padx=(10, 4), pady=2)
        ctk.CTkLabel(cat_btn_frame, text="▼", fg_color="transparent",
                     text_color=BTN_BLUE, font=ctk.CTkFont(size=10),
                     cursor="hand2"
                     ).grid(row=0, column=1, padx=(0, 8))

        def _open_cat_dropdown(event=None):
            import tkinter as tk
            dp = tk.Toplevel(self)
            dp.overrideredirect(True)
            dp.configure(bg="#FFFFFF")
            dp.attributes("-topmost", True)
            # Position below the button
            dp.update_idletasks()
            x = cat_btn_frame.winfo_rootx()
            y = cat_btn_frame.winfo_rooty() + cat_btn_frame.winfo_height()
            w = max(cat_btn_frame.winfo_width(), 200)
            visible = min(len(cats), 5)
            row_h   = 28
            dp.geometry(f"{w}x{visible * row_h + 2}+{x}+{y}")

            outer = tk.Frame(dp, bg="#1565C0", bd=1, relief="flat")
            outer.pack(fill="both", expand=True)
            lb = tk.Listbox(outer, bg="#FFFFFF", fg="#1A1A2E",
                            font=("Segoe UI", 11),
                            selectbackground="#BBDEFB",
                            selectforeground="#1A1A2E",
                            activestyle="dotbox", relief="flat",
                            bd=0, highlightthickness=0,
                            cursor="hand2")
            sb = tk.Scrollbar(outer, orient="vertical", command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            if len(cats) > 5:
                sb.pack(side="right", fill="y")
            lb.pack(fill="both", expand=True)

            for c in cats:
                lb.insert(tk.END, f"  {c}")
            # Pre-select current
            try:
                idx = cats.index(self.cat_var.get())
                lb.selection_set(idx)
                lb.see(idx)
            except ValueError:
                pass

            def _pick(evt=None):
                sel = lb.curselection()
                if sel:
                    chosen = cats[sel[0]]
                    self.cat_var.set(chosen)
                    self._reload_stock()
                dp.destroy()

            lb.bind("<<ListboxSelect>>", _pick)
            lb.bind("<Return>", _pick)
            dp.bind("<Escape>", lambda e: dp.destroy())
            dp.bind("<FocusOut>", lambda e: dp.destroy())
            lb.focus_set()

        for widget in [self._cat_lbl, cat_btn_frame]:
            widget.bind("<Button-1>", _open_cat_dropdown)
        # Also bind the arrow label
        cat_btn_frame.winfo_children()[-1].bind("<Button-1>", _open_cat_dropdown)

        self.sort_var = ctk.StringVar(value="No Sort")
        ctk.CTkOptionMenu(filters, variable=self.sort_var,
                          values=["No Sort", "High to Low Stock", "Low to High Stock",
                                  "Newest Added Item", "Oldest Added Item"],
                          width=170, height=40,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF",
                          dropdown_text_color="#1A1A2E",
                          text_color="black", font=ctk.CTkFont(size=12),
                          command=lambda _: self._reload_stock()
                          ).grid(row=0, column=2)

        col_hdr = ctk.CTkFrame(page, fg_color=COL_HDR, height=36, corner_radius=0)
        col_hdr.grid(row=2, column=0, sticky="ew", padx=24, pady=(10, 0))
        col_hdr.pack_propagate(False)
        col_hdr.columnconfigure(1, weight=1)

        # Select All checkbox
        self._stock_select_all = ctk.BooleanVar(value=False)
        self._stock_check_vars = {}
        def _toggle_stock_all():
            val = self._stock_select_all.get()
            for var in self._stock_check_vars.values():
                var.set(val)
        ctk.CTkCheckBox(col_hdr, text="", variable=self._stock_select_all,
                        width=22, checkbox_width=20, checkbox_height=20,
                        border_color="#1565C0", fg_color="#1565C0",
                        corner_radius=10, command=_toggle_stock_all
                        ).place(x=8, rely=0.5, anchor="w")

        for txt, col, anchor, w in [
            ("NAME",     1, "w",      0),
            ("CATEGORY", 2, "center", 160),
            ("STOCK",    3, "center", 130),
            ("PRICE",    4, "center", 130),
            ("ACTIONS",  5, "center", 180),
        ]:
            kw = {"font": ctk.CTkFont(size=11, weight="bold"),
                  "text_color": TEXT_GREY, "fg_color": "transparent", "anchor": anchor}
            if w == 0:
                ctk.CTkLabel(col_hdr, text=txt, **kw).grid(
                    row=0, column=col, sticky="w", padx=(4, 0), pady=6)
            else:
                ctk.CTkLabel(col_hdr, text=txt, width=w, **kw).grid(
                    row=0, column=col, padx=4, pady=6)

        self.stock_table = ctk.CTkScrollableFrame(
            page, fg_color="#F5F5F5",
            scrollbar_button_color=BTN_BLUE, corner_radius=0)
        self.stock_table.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 12))
        self.stock_table.columnconfigure(0, weight=1)

        self._reload_stock()

    def _reload_stock(self):
        if not hasattr(self, "stock_table"):
            return
        try:
            self.stock_table.winfo_children()
        except Exception:
            return
        for w in self.stock_table.winfo_children():
            w.destroy()

        # fetch fresh from Firestore (or cache)
        rows = db.get_all_products(store="canteen")
        search = self.stock_search.get().lower().strip()
        cat = self.cat_var.get()
        sort = self.sort_var.get()

        if search:
            rows = [r for r in rows if search in r[1].lower() or search in r[0].lower()]
        if cat != "All Categories":
            rows = [r for r in rows if r[2] == cat]

        # ── Sort ── index 6 = date_added string "YYYY-MM-DD"
        if sort == "High to Low Stock":
            rows = sorted(rows, key=lambda r: r[4], reverse=True)
        elif sort == "Low to High Stock":
            rows = sorted(rows, key=lambda r: r[4])
        elif sort == "Newest Added Item":
            rows = sorted(rows, key=lambda r: str(r[6]) if len(r) > 6 and r[6] else "", reverse=True)
        elif sort == "Oldest Added Item":
            rows = sorted(rows, key=lambda r: str(r[6]) if len(r) > 6 and r[6] else "")

        if not rows:
            ctk.CTkLabel(self.stock_table, text="No products found.",
                         font=ctk.CTkFont(size=14), text_color="#546E7A").pack(pady=40)
            return

        self._stock_check_vars = {}
        for i, row_data in enumerate(rows):
            barcode    = row_data[0]
            name       = row_data[1]
            category   = row_data[2]
            price      = row_data[3]
            stock      = row_data[4]
            date_added = row_data[6] if len(row_data) > 6 else ""

            bg = BG_ROW if i % 2 == 0 else BG_ROW_ALT
            row = ctk.CTkFrame(self.stock_table, fg_color=bg,
                               corner_radius=0, height=48)
            row.pack(fill="x")
            row.pack_propagate(False)
            row.columnconfigure(1, weight=1)

            # Checkbox col 0
            cb_var = ctk.BooleanVar(value=False)
            self._stock_check_vars[barcode] = cb_var
            ctk.CTkCheckBox(row, text="", variable=cb_var,
                            width=22, checkbox_width=20, checkbox_height=20,
                            border_color="#1565C0", fg_color="#1565C0",
                            corner_radius=10
                            ).grid(row=0, column=0, padx=(10,4), pady=8)

            nf = ctk.CTkFrame(row, fg_color="transparent")
            nf.grid(row=0, column=1, sticky="w", padx=(4, 8), pady=8)
            ctk.CTkLabel(nf, text=name,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#1A1A2E", anchor="w").pack(anchor="w")
            sub = barcode
            if date_added:
                sub += f"  ·  Added: {date_added}"
            ctk.CTkLabel(nf, text=sub,
                         font=ctk.CTkFont(size=10),
                         text_color="#546E7A", anchor="w").pack(anchor="w")

            ctk.CTkLabel(row, text=category, width=160, anchor="center",
                         font=ctk.CTkFont(size=12), text_color="#546E7A"
                         ).grid(row=0, column=2, padx=4)

            color = GREEN if stock >= 10 else ORANGE
            ctk.CTkLabel(row, text=str(stock), width=130, anchor="center",
                         font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=color).grid(row=0, column=3, padx=4)

            ctk.CTkLabel(row, text=f"₱{price:.2f}", width=130, anchor="center",
                         font=ctk.CTkFont(size=13), text_color="#1A1A2E"
                         ).grid(row=0, column=4, padx=4)

            act = ctk.CTkFrame(row, fg_color="transparent", width=180)
            act.grid(row=0, column=5, padx=(4, 14))
            ctk.CTkButton(act, text="Edit", width=55, height=30,
                          fg_color=BTN_BLUE, hover_color="#1976D2",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          command=lambda b=barcode, n=name, c=category, p=price, s=stock:
                          self._edit_dialog(b, n, c, p, s)
                          ).pack(side="left", padx=(0, 3))
            ctk.CTkButton(act, text="🔢", width=36, height=30,
                          fg_color="#7B1FA2", hover_color="#6A1B9A",
                          font=ctk.CTkFont(size=12), corner_radius=6,
                          command=lambda b=barcode, n=name, p=price:
                          self._show_barcode_popup(b, n, p)
                          ).pack(side="left", padx=(0, 3))
            ctk.CTkButton(act, text="Del", width=46, height=30,
                          fg_color="#5D0000", hover_color="#8B0000",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          command=lambda b=barcode, n=name:
                          self._delete_product(b, n)
                          ).pack(side="left")

    def _print_stock_list(self):
        import os, platform, subprocess, tempfile
        prods = db.get_all_products(store="canteen")

        def generate_pdf(prods):
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.units import cm
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
                from reportlab.lib.styles import ParagraphStyle
                from reportlab.lib.enums import TA_CENTER
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); tmp.close()
                doc = SimpleDocTemplate(tmp.name, pagesize=A4,
                                        topMargin=1.5*cm, bottomMargin=1.5*cm,
                                        leftMargin=2*cm, rightMargin=2*cm)
                BLUE = colors.HexColor("#1565C0"); GREY = colors.HexColor("#555555")
                story = []
                c_s = ParagraphStyle("c", fontSize=20, fontName="Helvetica-Bold",
                                     textColor=BLUE, alignment=TA_CENTER, spaceAfter=3)
                s_s = ParagraphStyle("s", fontSize=10, fontName="Helvetica",
                                     textColor=GREY, alignment=TA_CENTER, spaceAfter=2)
                story.extend([
                    Paragraph("CANTEEN", c_s),
                    Paragraph("Stock Inventory List", s_s),
                    Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y  %I:%M %p')}", s_s),
                    Spacer(1, 0.3*cm),
                    HRFlowable(width="100%", thickness=2, color=BLUE),
                    Spacer(1, 0.3*cm)
                ])
                t_data = [["Product Name", "Category", "Stock", "Price"]]
                for p in sorted(prods, key=lambda x: x[1]):
                    bc, name, cat, price, stock = p[0], p[1], p[2], p[3], p[4]
                    t_data.append([name, cat, str(stock), f"₱{float(price):.2f}"])
                if len(t_data) == 1:
                    t_data.append(["No products found", "", "", ""])
                t = Table(t_data, colWidths=[7*cm, 4*cm, 2.5*cm, 3*cm], repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,0), BLUE),
                    ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                    ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                    ("FONTSIZE",   (0,0), (-1,-1), 10),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#F9F9F9"), colors.white]),
                    ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#DDDDDD")),
                    ("TOPPADDING", (0,0), (-1,-1), 6),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                    ("LEFTPADDING",  (0,0), (-1,-1), 10),
                    ("ALIGN", (2,0), (3,-1), "CENTER"),
                    ("TEXTCOLOR",  (2,1), (2,-1), colors.HexColor("#C62828")),
                    ("FONTNAME",   (2,1), (2,-1), "Helvetica-Bold"),
                    ("TEXTCOLOR",  (3,1), (3,-1), BLUE),
                    ("FONTNAME",   (3,1), (3,-1), "Helvetica-Bold"),
                ]))
                story.extend([t, Spacer(1, 0.4*cm),
                               HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DDDDDD")),
                               Paragraph(f"Total Products: {len(prods)}",
                                         ParagraphStyle("f", fontSize=9, textColor=GREY, alignment=TA_CENTER))])
                doc.build(story)
                return tmp.name
            except ImportError:
                return None

        pdf_path = generate_pdf(prods)
        if pdf_path:
            try:
                if platform.system() == "Windows": os.startfile(pdf_path)
                elif platform.system() == "Darwin": subprocess.run(["open", pdf_path])
                else: subprocess.run(["xdg-open", pdf_path])
                messagebox.showinfo("PDF Ready", "Stock list PDF opened!\nPrint it from the PDF viewer.", parent=self)
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=self)
        else:
            messagebox.showinfo("Install Required", "pip install reportlab", parent=self)

    def _delete_selected_products(self):
        selected = [bc for bc, var in self._stock_check_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("No Selection",
                                "Select product(s) using the checkbox first.", parent=self)
            return
        if not messagebox.askyesno("Delete Products",
                                   f"Permanently delete {len(selected)} selected product(s)?\n\n"
                                   f"⚠ This cannot be undone!", parent=self):
            return
        for bc in selected:
            db.delete_product(bc, store="canteen")
        self._reload_stock()

    # ── ADD / EDIT PRODUCT ──────────────────────────────────────
    def _add_product_dialog(self):
        self._product_form("Add New Product", None, "", "", "", "", "")

    def _edit_dialog(self, barcode, name, category, price, stock):
        # Fetch existing image_url from SQLite
        existing_img = ""
        try:
            prods = db.get_all_products(store="canteen")
            for p in prods:
                if p[0] == barcode:
                    existing_img = p[7] if len(p) > 7 else ""
                    break
        except Exception:
            pass
        self._product_form("Edit Product", barcode, barcode, name,
                           category, str(price), str(stock), existing_img)

    def _upload_image_to_storage(self, image_path, barcode, store="canteen"):
        """Upload image to Firebase Storage using service account token."""
        try:
            import urllib.request, urllib.parse, json as _json

            # Use project ID from database module
            project_id = db.PROJECT_ID
            # Firebase Storage bucket — try .firebasestorage.app first, fallback to .appspot.com
            bucket = f"{project_id}.firebasestorage.app"

            # Read image
            with open(image_path, "rb") as img_f:
                image_data = img_f.read()

            ext = os.path.splitext(image_path)[1].lower().lstrip(".")
            if ext == "jpg": ext = "jpeg"
            mime_type = f"image/{ext}"

            # File path in storage
            file_name   = f"products/{store}_{barcode}.{ext}"
            encoded_name = urllib.parse.quote(file_name, safe="")

            # Get OAuth2 token from service account (same as Firestore)
            token = db._get_token()

            upload_url = (
                f"https://firebasestorage.googleapis.com/v0/b/"
                f"{urllib.parse.quote(bucket, safe='')}/o"
                f"?name={encoded_name}"
            )

            req = urllib.request.Request(
                upload_url,
                data=image_data,
                method="POST",
                headers={
                    "Content-Type": mime_type,
                    "Authorization": f"Bearer {token}"
                }
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = _json.loads(resp.read())

            token_dl = result.get("downloadTokens", "")
            download_url = (
                f"https://firebasestorage.googleapis.com/v0/b/"
                f"{urllib.parse.quote(bucket, safe='')}/o/"
                f"{urllib.parse.quote(file_name, safe='')}"
                f"?alt=media&token={token_dl}"
            )
            print(f"[Storage] Uploaded: {file_name}")
            return download_url

        except Exception as e:
            print(f"[Storage] Upload error: {e}")
            return None

    def _product_form(self, title, orig_barcode, barcode, name, category, price, stock, existing_img=""):
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color="#111111")
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        win.after(50, win.focus_force)
        win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"444x660+{(sw-444)//2}+{(sh-660)//2}")
        inner = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=16)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        ph = ctk.CTkFrame(inner, fg_color="#1565C0", height=50, corner_radius=0)
        ph.pack(fill="x"); ph.pack_propagate(False)
        ctk.CTkLabel(ph, text=f"📦  {title}",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(ph, text="✕", width=32, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13), corner_radius=6,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        fields = {}
        existing_cats = db.get_categories(store="canteen")
        defs = [("Barcode",      "barcode",  barcode),
                ("Product Name", "name",     name),
                ("Category",     "category", category),
                ("Price (₱)",    "price",    price),
                ("Stock Qty",    "stock",    stock)]

        # ── Static markup state ──
        if not hasattr(self, "_markup_pct"):
            self._markup_pct = 10

        for lbl, key, val in defs:
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x", padx=28, pady=5)
            ctk.CTkLabel(row, text=lbl, width=120, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
            if key == "category":
                e = ctk.CTkComboBox(row, height=38,
                                    fg_color="#FFFFFF",
                                    border_width=1, border_color="#1565C0",
                                    text_color="black",
                                    font=ctk.CTkFont(size=13),
                                    dropdown_fg_color="#FFFFFF",
                                    dropdown_text_color="#1A1A2E",
                                    button_color=BTN_BLUE,
                                    button_hover_color="#1976D2",
                                    values=existing_cats if existing_cats else
                                    ["Beverage","Food","Snacks","Supplies","Drinks","Other"])
                e.set(val if val else "")
            else:
                e = ctk.CTkEntry(row, height=38, fg_color="#BBDEFB",
                                 border_width=1, border_color="#1565C0",
                                 text_color="black", font=ctk.CTkFont(size=13))
                if val:
                    e.insert(0, val)
                if key == "barcode" and orig_barcode:
                    e.configure(state="disabled", text_color="#546E7A")
            e.pack(side="left", fill="x", expand=True)
            fields[key] = e

            # ── Inject Markup % + Total Item Price after Price field ──
            if key == "price":
                mk_row = ctk.CTkFrame(inner, fg_color="transparent")
                mk_row.pack(fill="x", padx=28, pady=5)
                ctk.CTkLabel(mk_row, text="Markup %", width=120, anchor="w",
                             font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
                markup_cb = ctk.CTkComboBox(mk_row, height=38, width=160,
                                            fg_color="#FFFFFF",
                                            border_width=1, border_color="#1565C0",
                                            text_color="black",
                                            font=ctk.CTkFont(size=13),
                                            dropdown_fg_color="#FFFFFF",
                                            dropdown_text_color="#1A1A2E",
                                            button_color=BTN_BLUE,
                                            button_hover_color="#1976D2",
                                            values=["0%","5%","10%","15%","20%",
                                                    "25%","30%","40%","50%"])
                markup_cb.set(f"{self._markup_pct}%")
                markup_cb.pack(side="left")

                tp_row = ctk.CTkFrame(inner, fg_color="transparent")
                tp_row.pack(fill="x", padx=28, pady=5)
                ctk.CTkLabel(tp_row, text="Total Item Price", width=120, anchor="w",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color="#2E7D32").pack(side="left")
                total_price_e = ctk.CTkEntry(tp_row, height=38, fg_color="#E8F5E9",
                                             border_width=2, border_color="#2E7D32",
                                             text_color="#2E7D32",
                                             font=ctk.CTkFont(size=13, weight="bold"))
                total_price_e.pack(side="left", fill="x", expand=True)
                fields["total_price"] = total_price_e

                def _recalc(*_):
                    try:
                        base = float(fields["price"].get().strip())
                        pct_str = markup_cb.get().replace("%","").strip()
                        pct  = float(pct_str) if pct_str else 0
                        self._markup_pct = int(pct)
                        total = base * (1 + pct / 100)
                        fields["total_price"].configure(state="normal")
                        fields["total_price"].delete(0, "end")
                        fields["total_price"].insert(0, f"{total:.2f}")
                    except Exception:
                        pass

                fields["price"].bind("<KeyRelease>", _recalc)
                markup_cb.configure(command=lambda v: _recalc())
                if price:
                    win.after(100, _recalc)


        # ── Image upload row ──
        img_path_ref = {"path": None}
        img_row = ctk.CTkFrame(inner, fg_color="transparent")
        img_row.pack(fill="x", padx=28, pady=5)
        ctk.CTkLabel(img_row, text="Product Photo", width=120, anchor="w",
                     font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
        has_existing = bool(existing_img and existing_img.strip())
        img_status = ctk.CTkLabel(img_row,
                                  text="✅ Image already uploaded" if has_existing else "No image selected",
                                  font=ctk.CTkFont(size=11),
                                  text_color="#2E7D32" if has_existing else "#90A4AE")
        img_status.pack(side="left", fill="x", expand=True)

        def _pick_image():
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                parent=win, title="Select Product Image",
                filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp")])
            if path:
                img_path_ref["path"] = path
                fname = os.path.basename(path)
                short = fname if len(fname) <= 22 else fname[:19] + "..."
                img_status.configure(text=f"✅ {short}", text_color="#2E7D32")

        ctk.CTkButton(img_row, text="📷 Browse",
                      width=90, height=34,
                      fg_color="#1565C0", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=11), text_color="white",
                      command=_pick_image).pack(side="right")

        # ── Upload status label ──
        upload_lbl = ctk.CTkLabel(inner, text="",
                                   font=ctk.CTkFont(size=11),
                                   text_color="#1565C0")
        upload_lbl.pack(pady=(0,4))

        def save():
            try:
                bc  = fields["barcode"].get().strip() if not orig_barcode else orig_barcode
                nm  = fields["name"].get().strip()
                cat = fields["category"].get().strip()
                pr  = float(fields["total_price"].get().strip() or fields["price"].get().strip())
                st  = int(fields["stock"].get().strip())
                if not bc or not nm or not cat:
                    raise ValueError("empty")
            except Exception:
                messagebox.showerror("Error", "Please fill all fields correctly.", parent=win)
                return

            # Save product first
            if orig_barcode:
                db.update_product(orig_barcode, nm, cat, pr, st, store="canteen")
            else:
                db.add_product(bc, nm, cat, pr, st, store="canteen")

            # Upload image if selected
            if img_path_ref["path"] and db.has_internet():
                upload_lbl.configure(text="⏳ Uploading image...", text_color="#1565C0")
                win.update()
                def _do_upload():
                    url = self._upload_image_to_storage(img_path_ref["path"], bc)
                    if url:
                        # ── Save image_url to SQLite only — Firestore updated on Backup ──
                        try:
                            db.update_product(bc, nm, cat, pr, st,
                                              store="canteen", image_url=url)
                        except Exception as e:
                            print(f"SQLite image_url save error: {e}")
                        self.after(0, lambda: upload_lbl.configure(
                            text="✅ Image saved locally!", text_color="#2E7D32"))
                    else:
                        self.after(0, lambda: upload_lbl.configure(
                            text="⚠️ Image upload failed", text_color="#C62828"))
                    self.after(500, lambda: [win.destroy(),
                                             self._reload_stock(),
                                             self.cat_var.set("All Categories")])
                threading.Thread(target=_do_upload, daemon=True).start()
            else:
                if img_path_ref["path"] and not db.has_internet():
                    messagebox.showwarning("Offline",
                        "Product saved locally.\nConnect to internet to upload image.",
                        parent=win)
                win.destroy()
                self._reload_stock()
                self.cat_var.set("All Categories")

        ctk.CTkButton(inner, text="💾  Save", height=44,
                      fg_color="#1976D2", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      corner_radius=8, command=save
                      ).pack(fill="x", padx=28, pady=(10, 0))
        win.bind("<Return>", lambda e: save())
        # Auto-focus first editable field
        win.after(100, lambda: (
            fields["name"].focus_set() if orig_barcode
            else fields["barcode"].focus_set()
        ))

    def _delete_product(self, barcode, name):
        if messagebox.askyesno("Delete Product",
                               f"Delete '{name}'? This cannot be undone.", parent=self):
            db.delete_product(barcode, store="canteen")
            self._reload_stock()

    # ════════════════════════════════════════════════════════════
    #  SALES REPORT
    # ════════════════════════════════════════════════════════════
    # ── SHARED LOYALTY MEMBER HELPERS ───────────────────────────
    def _get_all_coop_members(self):
        """Fetch loyalty members from ALL stores so one card works everywhere."""
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
        return sorted(all_members, key=lambda m: m.get("name", ""))

    def _find_member_by_name(self, name):
        """Find a loyalty member by name across all stores."""
        for store in ["coop", "cafestore", "canteen"]:
            try:
                m = db.get_loyalty_member_by_card_name(name, store=store)
                if m:
                    return m
            except Exception:
                pass
        return None

    def _show_sales_report(self):
        """Embedded sales report — lives inside the content area, no popup."""
        import calendar as cal_mod
        page = ctk.CTkFrame(self.content, fg_color="#F5F5F5", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)
        self._rpt_win = self   # fallback reference used by _print_report

        # ── Title bar ──
        hbar = ctk.CTkFrame(page, fg_color="#FFFFFF", height=60, corner_radius=0)
        hbar.grid(row=0, column=0, sticky="ew")
        hbar.pack_propagate(False)
        ctk.CTkLabel(hbar, text="📊  Sales Overview",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#1A1A2E").place(x=20, rely=0.5, anchor="w")
        ctk.CTkButton(hbar, text="🖨  Print Report", width=140, height=36,
                      fg_color="#2E7D32", hover_color="#1B5E20", text_color="white",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8,
                      command=self._print_report
                      ).place(relx=0.88, rely=0.5, anchor="center")

        # ── Controls row ──
        ctrl = ctk.CTkFrame(page, fg_color="#FFFFFF", corner_radius=10,
                            border_width=1, border_color="#BBDEFB")
        ctrl.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 6))

        ctk.CTkLabel(ctrl, text="📊  Period:",
                     font=ctk.CTkFont(size=12), text_color="#546E7A"
                     ).pack(side="left", padx=(12, 6), pady=8)

        self._rpt_period_var = ctk.StringVar(value="Month")
        ctk.CTkOptionMenu(ctrl, variable=self._rpt_period_var,
                          values=["Month", "Year"], width=110, height=32,
                          fg_color="#FFFFFF", button_color="#1565C0",
                          button_hover_color="#0D47A1",
                          dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                          text_color="black", font=ctk.CTkFont(size=12, weight="bold"),
                          command=lambda v: self._select_period(v.lower())
                          ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(ctrl, text="Month:", font=ctk.CTkFont(size=12),
                     text_color="#546E7A").pack(side="left", padx=(0, 4))

        month_names = list(cal_mod.month_name)[1:]
        now = datetime.now()
        self._rpt_month_var = ctk.StringVar(value=cal_mod.month_name[now.month])
        ctk.CTkOptionMenu(ctrl, variable=self._rpt_month_var, values=month_names,
                          width=140, height=32,
                          fg_color="#FFFFFF", button_color="#1565C0",
                          button_hover_color="#0D47A1",
                          dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                          text_color="#1A1A2E", font=ctk.CTkFont(size=12),
                          command=lambda _: self._select_period(self._rpt_period_var.get().lower())
                          ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(ctrl, text="Year:", font=ctk.CTkFont(size=12),
                     text_color="#546E7A").pack(side="left", padx=(0, 4))

        year_values = [str(y) for y in range(now.year - 5, now.year + 6)]
        self._rpt_year_var = ctk.StringVar(value=str(now.year))
        ctk.CTkOptionMenu(ctrl, variable=self._rpt_year_var, values=year_values,
                          width=100, height=32,
                          fg_color="#FFFFFF", button_color="#1565C0",
                          button_hover_color="#0D47A1",
                          dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                          text_color="#1A1A2E", font=ctk.CTkFont(size=12),
                          command=lambda _: self._select_period(self._rpt_period_var.get().lower())
                          ).pack(side="left", padx=(0, 12))

        ctk.CTkFrame(ctrl, fg_color="#1565C0", width=2, height=30).pack(side="left", padx=8)

        ctk.CTkLabel(ctrl, text="📅 Single Date:", font=ctk.CTkFont(size=12),
                     text_color="#546E7A").pack(side="left", padx=(8, 4))
        self._from_var = ctk.StringVar()
        self._to_var   = ctk.StringVar()
        self._date_lbl = ctk.CTkLabel(ctrl, text="Pick a date",
                                      font=ctk.CTkFont(size=12, weight="bold"),
                                      text_color="#E65100", cursor="hand2")
        self._date_lbl.pack(side="left", padx=4)
        self._date_lbl.bind("<Button-1>", lambda e: self._open_rpt_calendar(
            "single", self._from_var, self._date_lbl))
        ctk.CTkButton(ctrl, text="✕", width=30, height=30,
                      fg_color=BTN_BLUE, hover_color="#1976D2",
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=self._clear_rpt_dates
                      ).pack(side="left", padx=(6, 8))

        self._rpt_body = ctk.CTkScrollableFrame(page, fg_color="transparent",
                                                 scrollbar_button_color=BTN_BLUE)
        self._rpt_body.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 16))
        self._select_period("month")

    def _open_rpt_calendar(self, which, var, lbl):
        import calendar as cal_mod
        win = ctk.CTkToplevel(self)
        win.title("Pick a Date")
        win.geometry("360x360")
        win.configure(fg_color="#F5F5F5")
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"360x360+{(sw-360)//2}+{(sh-360)//2}")

        now   = datetime.now()
        state = {"year": now.year, "month": now.month}

        def build(year, month):
            for w in win.winfo_children(): w.destroy()
            hdr = ctk.CTkFrame(win, fg_color="#1565C0", height=52, corner_radius=0)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            ctk.CTkButton(hdr, text="◀", width=34, height=30,
                          fg_color="transparent", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(-1)).place(x=8, rely=0.5, anchor="w")
            ctk.CTkLabel(hdr, text=f"{cal_mod.month_name[month]} {year}",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkButton(hdr, text="▶", width=34, height=30,
                          fg_color="transparent", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(1)).place(relx=1.0, x=-8, rely=0.5, anchor="e")
            pick_row = ctk.CTkFrame(win, fg_color="transparent")
            pick_row.pack(fill="x", padx=12, pady=(10, 6))
            month_names = list(cal_mod.month_name)[1:]
            month_var = ctk.StringVar(value=cal_mod.month_name[month])
            year_values = [str(y) for y in range(now.year-5, now.year+6)]
            year_var = ctk.StringVar(value=str(year))
            def on_month_change(m):
                state["month"] = month_names.index(m)+1; build(state["year"], state["month"])
            def on_year_change(y):
                state["year"] = int(y); build(state["year"], state["month"])
            ctk.CTkOptionMenu(pick_row, variable=month_var, values=month_names, width=170, height=34,
                              fg_color="#FFFFFF", button_color="#1565C0", button_hover_color="#0D47A1",
                              dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                              text_color="#1A1A2E", font=ctk.CTkFont(size=12),
                              command=on_month_change).pack(side="left", padx=(0,8))
            ctk.CTkOptionMenu(pick_row, variable=year_var, values=year_values, width=110, height=34,
                              fg_color="#FFFFFF", button_color="#1565C0", button_hover_color="#0D47A1",
                              dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                              text_color="#1A1A2E", font=ctk.CTkFont(size=12),
                              command=on_year_change).pack(side="left")
            dh = ctk.CTkFrame(win, fg_color="transparent")
            dh.pack(fill="x", padx=10, pady=(4,0))
            for d in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
                ctk.CTkLabel(dh, text=d, width=48,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#546E7A").pack(side="left")
            gf = ctk.CTkFrame(win, fg_color="transparent")
            gf.pack(fill="x", padx=10, pady=4)
            for week in cal_mod.monthcalendar(year, month):
                rf = ctk.CTkFrame(gf, fg_color="transparent")
                rf.pack(fill="x", pady=2)
                for day in week:
                    if day == 0:
                        ctk.CTkLabel(rf, text="", width=48).pack(side="left")
                    else:
                        is_today = (day==now.day and month==now.month and year==now.year)
                        ctk.CTkButton(rf, text=str(day), width=42, height=30,
                                      fg_color="#1976D2" if is_today else BTN_BLUE,
                                      hover_color="#0D47A1" if is_today else "#1976D2",
                                      font=ctk.CTkFont(size=11), corner_radius=4,
                                      command=lambda d=day: pick(d)
                                      ).pack(side="left", padx=2)

        def go(delta):
            m = state["month"]+delta; y = state["year"]
            if m>12: m=1; y+=1
            if m<1:  m=12; y-=1
            state["year"]=y; state["month"]=m; build(y,m)

        def pick(day):
            chosen = f"{state['year']:04d}-{state['month']:02d}-{day:02d}"
            var.set(chosen)
            lbl.configure(text=f"{state['month']:02d}/{day:02d}/{state['year']}")
            win.destroy()
            if which == "single":
                for w in self._rpt_body.winfo_children(): w.destroy()
                data = db.get_sales_report_custom(chosen, chosen, store="canteen")
                self._render_report_body(data, chosen)

        build(state["year"], state["month"])

    def _clear_rpt_dates(self):
        self._from_var.set(""); self._to_var.set("")
        try: self._date_lbl.configure(text="Pick a date")
        except: pass
        self._select_period(self._rpt_period_var.get().lower())

    def _select_period(self, period):
        import calendar as cal_mod
        self._rpt_period = period
        for w in self._rpt_body.winfo_children(): w.destroy()
        single_date = getattr(self, "_from_var", ctk.StringVar()).get().strip()
        if single_date:
            data = db.get_sales_report_custom(single_date, single_date, store="canteen")
            self._render_report_body(data, single_date); return
        selected_year  = int(self._rpt_year_var.get())
        selected_month_name = self._rpt_month_var.get()
        selected_month = list(cal_mod.month_name).index(selected_month_name)
        if period == "month":
            start_date = f"{selected_year:04d}-{selected_month:02d}-01"
            last_day   = cal_mod.monthrange(selected_year, selected_month)[1]
            end_date   = f"{selected_year:04d}-{selected_month:02d}-{last_day:02d}"
            data  = db.get_sales_report_custom(start_date, end_date, store="canteen")
            label = f"{selected_month_name} {selected_year}"
        elif period == "year":
            start_date = f"{selected_year:04d}-01-01"
            end_date   = f"{selected_year:04d}-12-31"
            data  = db.get_sales_report_custom(start_date, end_date, store="canteen")
            label = f"Year {selected_year}"
        else:
            data  = db.get_sales_report("month", store="canteen")
            label = "Month"
        self._render_report_body(data, label)

    def _print_report(self):
        import os, platform, subprocess, tempfile, calendar as cal_mod
        from_str = getattr(self, '_from_var', ctk.StringVar()).get().strip()
        if from_str:
            data   = db.get_sales_report_custom(from_str, from_str, store="canteen")
            period = from_str
        else:
            selected_year  = int(self._rpt_year_var.get())
            selected_month_name = self._rpt_month_var.get()
            selected_month = list(cal_mod.month_name).index(selected_month_name)
            sel_period     = self._rpt_period_var.get().lower()
            if sel_period == "month":
                start_date = f"{selected_year:04d}-{selected_month:02d}-01"
                last_day   = cal_mod.monthrange(selected_year, selected_month)[1]
                end_date   = f"{selected_year:04d}-{selected_month:02d}-{last_day:02d}"
                data   = db.get_sales_report_custom(start_date, end_date, store="canteen")
                period = f"{selected_month_name} {selected_year}"
            elif sel_period == "year":
                start_date = f"{selected_year:04d}-01-01"
                end_date   = f"{selected_year:04d}-12-31"
                data   = db.get_sales_report_custom(start_date, end_date, store="canteen")
                period = f"Year {selected_year}"
            else:
                data   = db.get_sales_report("month", store="canteen")
                period = "Month"

        def generate_pdf(data, period):
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.units import cm
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
                from reportlab.lib.styles import ParagraphStyle
                from reportlab.lib.enums import TA_CENTER
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); tmp.close()
                doc = SimpleDocTemplate(tmp.name, pagesize=A4,
                                        topMargin=1.5*cm, bottomMargin=1.5*cm,
                                        leftMargin=2*cm, rightMargin=2*cm)
                RED  = colors.HexColor("#1565C0")
                GREY = colors.HexColor("#555555")
                story = []
                c_s = ParagraphStyle("c", fontSize=22, fontName="Helvetica-Bold",
                                     textColor=RED, alignment=TA_CENTER, spaceAfter=4)
                s_s = ParagraphStyle("s", fontSize=11, fontName="Helvetica",
                                     textColor=GREY, alignment=TA_CENTER, spaceAfter=2)
                story.extend([Paragraph("CAFETERIA STORE", c_s),
                               Paragraph("Sales Report", s_s),
                               Paragraph(f"Period: {period}", s_s),
                               Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y  %I:%M %p')}", s_s),
                               Spacer(1, 0.4*cm),
                               HRFlowable(width="100%", thickness=2, color=RED),
                               Spacer(1, 0.3*cm)])
                lbl_s = ParagraphStyle("lbl", fontSize=9, fontName="Helvetica-Bold", textColor=GREY, alignment=TA_CENTER)
                val_s = ParagraphStyle("val", fontSize=18, fontName="Helvetica-Bold", textColor=RED, alignment=TA_CENTER)
                flat  = [[Paragraph("TOTAL REVENUE",lbl_s), Paragraph("TRANSACTIONS",lbl_s), Paragraph("AVG TRANSACTION",lbl_s)],
                         [Paragraph(f"P{data['revenue']:.2f}",val_s), Paragraph(str(data['count']),val_s), Paragraph(f"P{data['avg']:.2f}",val_s)]]
                t = Table(flat, colWidths=[5.5*cm,5.5*cm,5.5*cm])
                t.setStyle(TableStyle([("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                                       ("INNERGRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                                       ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#FFF8F8")),
                                       ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
                story.extend([t, Spacer(1,0.4*cm)])
                hdr_s = ParagraphStyle("h", fontSize=13, fontName="Helvetica-Bold",
                                       textColor=colors.HexColor("#1A1A2E"), spaceAfter=6)
                story.append(Paragraph("Payment Method Breakdown", hdr_s))
                pay_data = [["Payment Method","Amount"]]
                for m in ["Cash","Credit / Utang"]:
                    pay_data.append([m, f"P{data['by_method'].get(m,0):.2f}"])
                pt = Table(pay_data, colWidths=[10*cm,6.5*cm])
                pt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),RED),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                                        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),11),
                                        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F9F9F9"),colors.white]),
                                        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                                        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
                                        ("LEFTPADDING",(0,0),(-1,-1),12)]))
                story.extend([pt, Spacer(1,0.4*cm), Paragraph("Items Sold", hdr_s)])
                items_data = [["Product","Category","Qty","Price","Revenue"]]
                for nm, cat, qty, rev in (data["items_sold"] or []):
                    unit_price = rev / qty if qty else 0
                    items_data.append([nm, cat, str(qty), f"₱{unit_price:.2f}", f"₱{rev:.2f}"])
                if len(items_data)==1: items_data.append(["No data","","","",""])
                it = Table(items_data, colWidths=[5.5*cm,3.5*cm,2*cm,2.5*cm,3*cm])
                it.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),RED),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                                        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),10),
                                        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F9F9F9"),colors.white]),
                                        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                                        ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
                                        ("LEFTPADDING",(0,0),(-1,-1),10),
                                        ("ALIGN",(2,0),(4,-1),"CENTER"),
                                        ("TEXTCOLOR",(4,1),(4,-1),RED),("FONTNAME",(4,1),(4,-1),"Helvetica-Bold")]))
                story.extend([it, Spacer(1,0.5*cm),
                               HRFlowable(width="100%",thickness=1,color=colors.HexColor("#DDDDDD")),
                               Paragraph("Store POS — Auto-generated Report",
                                         ParagraphStyle("f",fontSize=8,textColor=GREY,alignment=TA_CENTER))])
                doc.build(story)
                return tmp.name
            except ImportError:
                return None

        pdf_path = generate_pdf(data, period)
        parent = self
        if pdf_path:
            try:
                if platform.system() == "Windows": os.startfile(pdf_path)
                elif platform.system() == "Darwin": subprocess.run(["open", pdf_path])
                else: subprocess.run(["xdg-open", pdf_path])
                messagebox.showinfo("PDF Ready", "PDF report opened!", parent=parent)
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=parent)
        else:
            messagebox.showinfo("Install Required", "pip install reportlab", parent=parent)

    def _render_report_body(self, data, period_label):
        cards = ctk.CTkFrame(self._rpt_body, fg_color="transparent")
        cards.pack(fill="x", pady=(4,14))
        cards.columnconfigure((0,1,2), weight=1)
        for col, (label, val, vcolor) in enumerate([
            ("TOTAL REVENUE",   f"₱{data['revenue']:.2f}", ACCENT_RED),
            ("TRANSACTIONS",    str(data["count"]),         TEXT_WHITE),
            ("AVG TRANSACTION", f"₱{data['avg']:.2f}",     TEXT_WHITE),
        ]):
            card = ctk.CTkFrame(cards, fg_color="#FFFFFF", corner_radius=10)
            card.grid(row=0, column=col, sticky="ew", padx=5, pady=4)
            ctk.CTkLabel(card, text=label, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#546E7A").pack(anchor="w", padx=16, pady=(14,2))
            ctk.CTkLabel(card, text=val, font=ctk.CTkFont(size=24, weight="bold"),
                         text_color=vcolor).pack(anchor="w", padx=16, pady=(0,14))

        ctk.CTkLabel(self._rpt_body, text=f"Payment Method Breakdown — {period_label}",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#1A1A2E").pack(anchor="w", pady=(0,8))
        pay_row = ctk.CTkFrame(self._rpt_body, fg_color="transparent")
        pay_row.pack(fill="x", pady=(0,16))
        pay_row.columnconfigure((0,1,2), weight=1)
        for col, (method, icon) in enumerate([("Cash","💵"),("Cash (Mobile)","📲"),("Credit / Utang","💳")]):
            # Cash total = Cash + Cash (Mobile) combined
            if method == "Cash":
                amt = data["by_method"].get("Cash", 0) + data["by_method"].get("Cash (Mobile)", 0) + data["by_method"].get("Mobile Order", 0)
            else:
                amt = data["by_method"].get(method, 0)
            card = ctk.CTkFrame(pay_row, fg_color="#FFFFFF", corner_radius=10)
            card.grid(row=0, column=col, sticky="ew", padx=5, pady=4)
            ctk.CTkLabel(card, text=f"{icon}  {method.replace(' / Utang','/Utang')}",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#546E7A").pack(anchor="w", padx=16, pady=(14,2))
            ctk.CTkLabel(card, text=f"₱{amt:.2f}",
                         font=ctk.CTkFont(size=22, weight="bold"),
                         text_color="#1A1A2E").pack(anchor="w", padx=16, pady=(0,14))

        ctk.CTkLabel(self._rpt_body, text="Items Sold",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#1A1A2E").pack(anchor="w", pady=(0,8))
        th = ctk.CTkFrame(self._rpt_body, fg_color=COL_HDR, height=34, corner_radius=4)
        th.pack(fill="x"); th.pack_propagate(False); th.columnconfigure(0, weight=1)
        for txt, col, w, anchor in [
            ("ITEM NAME",0,0,"w"),("CATEGORY",1,160,"center"),
            ("QUANTITY SOLD",2,120,"center"),("REVENUE",3,110,"center")]:
            kw = {"font":ctk.CTkFont(size=10,weight="bold"),
                  "text_color":TEXT_GREY,"fg_color":"transparent","anchor":anchor}
            if w==0: ctk.CTkLabel(th,text=txt,**kw).grid(row=0,column=col,sticky="w",padx=(14,4),pady=6)
            else:    ctk.CTkLabel(th,text=txt,width=w,**kw).grid(row=0,column=col,padx=4,pady=6)

        if not data["items_sold"]:
            ctk.CTkLabel(self._rpt_body, text="No sales data.",
                         font=ctk.CTkFont(size=13), text_color="#546E7A").pack(pady=20)
        else:
            for i,(name,cat,qty,rev) in enumerate(data["items_sold"]):
                bg = BG_ROW if i%2==0 else BG_ROW_ALT
                r  = ctk.CTkFrame(self._rpt_body, fg_color=bg, height=38, corner_radius=0)
                r.pack(fill="x"); r.pack_propagate(False); r.columnconfigure(0,weight=1)
                ctk.CTkLabel(r,text=name,anchor="w",font=ctk.CTkFont(size=12),
                             text_color="#1A1A2E").grid(row=0,column=0,sticky="w",padx=(14,4))
                ctk.CTkLabel(r,text=cat,width=160,anchor="center",
                             font=ctk.CTkFont(size=12),text_color="#546E7A").grid(row=0,column=1,padx=4)
                ctk.CTkLabel(r,text=str(qty),width=120,anchor="center",
                             font=ctk.CTkFont(size=12,weight="bold"),
                             text_color="#1A1A2E").grid(row=0,column=2,padx=4)
                ctk.CTkLabel(r,text=f"₱{rev:.2f}",width=110,anchor="center",
                             font=ctk.CTkFont(size=12,weight="bold"),
                             text_color="#1565C0").grid(row=0,column=3,padx=4)

    # ════════════════════════════════════════════════════════════
    #  HISTORY PAGE
    # ════════════════════════════════════════════════════════════
    def _show_history(self):
        page = ctk.CTkFrame(self.content, fg_color="#F5F5F5", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(0, weight=0)
        page.rowconfigure(1, weight=0)
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)

        loading = ctk.CTkLabel(page, text="⏳  Loading transactions...",
                               font=ctk.CTkFont(size=16), text_color="#546E7A")
        loading.grid(row=2, column=0)

        def _fetch():
            rows = db.get_all_transactions(store="canteen")
            self.after(0, lambda r=rows: _render(r))

        def _render(all_rows):
            loading.destroy()
            total_rev = sum(r[2] for r in all_rows)

            top = ctk.CTkFrame(page, fg_color="transparent")
            top.grid(row=0, column=0, sticky="ew", padx=24, pady=(18,6))
            top.columnconfigure(0, weight=1)
            ctk.CTkLabel(top, text="Transaction History",
                         font=ctk.CTkFont(size=22, weight="bold"),
                         text_color="#1A1A2E").grid(row=0, column=0, sticky="w")

            fbar = ctk.CTkFrame(page, fg_color="#FFFFFF", corner_radius=8,
                                border_width=1, border_color="#1565C0")
            fbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(0,6))
            fbar.columnconfigure(1, weight=1)

            ctk.CTkLabel(fbar, text="🔢  TXN ID:",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#546E7A").grid(row=0, column=0, padx=(14,6), pady=8)
            self.hist_txn_search = ctk.StringVar()
            ctk.CTkEntry(fbar, textvariable=self.hist_txn_search,
                         placeholder_text="Search by Transaction ID...",
                         border_width=0, fg_color="#FFFFFF", height=34,
                         font=ctk.CTkFont(size=13), text_color="black",
                         placeholder_text_color="#546E7A", width=220
                         ).grid(row=0, column=1, sticky="w", padx=(0,16), pady=8)

            ctk.CTkFrame(fbar, fg_color="#1565C0", width=2, height=28).grid(row=0, column=2, padx=8)

            ctk.CTkLabel(fbar, text="💳  Method:",
                         font=ctk.CTkFont(size=12), text_color="#546E7A"
                         ).grid(row=0, column=3, padx=(8,4))

            self.hist_method_var = ctk.StringVar(value="All Methods")
            ctk.CTkOptionMenu(fbar, variable=self.hist_method_var,
                              values=["All Methods","Cash","Credit / Utang"],
                              width=150, height=30,
                              fg_color="#FFFFFF", button_color=BTN_BLUE,
                              button_hover_color="#1976D2",
                              dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                              text_color="black", font=ctk.CTkFont(size=11),
                              command=lambda _: self._reload_history_table(all_rows, table)
                              ).grid(row=0, column=4, padx=(0,12), pady=8)

            ctk.CTkFrame(fbar, fg_color="#1565C0", width=2, height=28).grid(row=0, column=5, padx=8)

            ctk.CTkLabel(fbar, text="📅  Date:",
                         font=ctk.CTkFont(size=12), text_color="#546E7A"
                         ).grid(row=0, column=6, padx=(8,4))
            self.hist_date_var = ctk.StringVar()
            self.hist_date_lbl = ctk.CTkLabel(fbar, text="All dates",
                                              font=ctk.CTkFont(size=12, weight="bold"),
                                              text_color="#E65100", cursor="hand2")
            self.hist_date_lbl.grid(row=0, column=7, padx=4)
            self.hist_date_lbl.bind("<Button-1>", lambda e: self._open_hist_calendar())

            ctk.CTkButton(fbar, text="✕ Clear", width=70, height=30,
                          fg_color=BTN_BLUE, hover_color="#1976D2",
                          font=ctk.CTkFont(size=11), corner_radius=6,
                          command=lambda: [self.hist_date_var.set(""),
                                           self.hist_date_lbl.configure(text="All dates"),
                                           self.hist_method_var.set("All Methods"),
                                           self._reload_history_table(all_rows, table)]
                          ).grid(row=0, column=8, padx=(4,14))

            table = ctk.CTkScrollableFrame(page, fg_color="#F0F4F8",
                                           scrollbar_button_color=BTN_BLUE, corner_radius=0)
            table.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0,12))
            table.columnconfigure(0, weight=1)
            self._hist_table    = table
            self._hist_all_rows = all_rows

            self.hist_txn_search.trace_add(
                "write", lambda *_: self._reload_history_table(all_rows, table))

            if not all_rows:
                ctk.CTkLabel(table, text="No transactions yet.",
                             font=ctk.CTkFont(size=14), text_color="#546E7A").pack(pady=40)
                return

            self._reload_history_table(all_rows, table)

        threading.Thread(target=_fetch, daemon=True).start()

    def _open_hist_calendar(self):
        import calendar as cal_mod
        win = ctk.CTkToplevel(self)
        win.title("Pick a Date"); win.geometry("320x300")
        win.configure(fg_color="#F5F5F5"); win.grab_set(); win.resizable(False,False)
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"320x300+{(sw-320)//2}+{(sh-300)//2}")
        now   = datetime.now()
        state = {"year": now.year, "month": now.month}

        def build(year, month):
            for w in win.winfo_children(): w.destroy()
            hdr = ctk.CTkFrame(win, fg_color="#1565C0", height=44, corner_radius=0)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            ctk.CTkButton(hdr, text="◀", width=36, height=30,
                          fg_color="transparent", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(-1)).place(x=8, rely=0.5, anchor="w")
            ctk.CTkLabel(hdr, text=f"{cal_mod.month_name[month]}  {year}",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkButton(hdr, text="▶", width=36, height=30,
                          fg_color="transparent", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(1)).place(relx=1.0, x=-8, rely=0.5, anchor="e")
            dh = ctk.CTkFrame(win, fg_color="transparent")
            dh.pack(fill="x", padx=10, pady=(6,0))
            for d in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
                ctk.CTkLabel(dh, text=d, width=36,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#546E7A").pack(side="left")
            gf = ctk.CTkFrame(win, fg_color="transparent")
            gf.pack(fill="x", padx=10, pady=4)
            for week in cal_mod.monthcalendar(year, month):
                rf = ctk.CTkFrame(gf, fg_color="transparent"); rf.pack(fill="x", pady=1)
                for day in week:
                    if day == 0: ctk.CTkLabel(rf, text="", width=36).pack(side="left")
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
            chosen = f"{state['year']:04d}-{state['month']:02d}-{day:02d}"
            self.hist_date_var.set(chosen)
            self.hist_date_lbl.configure(text=f"{state['month']:02d}/{day:02d}/{state['year']}")
            win.destroy()
            self._reload_history_table(self._hist_all_rows, self._hist_table)

        build(state["year"], state["month"])

    def _reload_history_table(self, all_rows, table):
        for w in table.winfo_children(): w.destroy()

        txn_q    = getattr(self,'hist_txn_search',ctk.StringVar()).get().strip()
        method_q = getattr(self,'hist_method_var',ctk.StringVar(value="All Methods")).get().strip()
        date_q   = getattr(self,'hist_date_var',ctk.StringVar()).get().strip()

        rows = all_rows
        if txn_q:    rows = [r for r in rows if txn_q in str(r[0])]
        if method_q != "All Methods": rows = [r for r in rows if r[3] == method_q]
        if date_q:   rows = [r for r in rows if r[1][:10] == date_q]

        if not rows:
            ctk.CTkLabel(table, text="No transactions found.",
                         font=ctk.CTkFont(size=14), text_color="#546E7A").pack(pady=40)
            return

        pay_colors = {"Cash":"#E65100","Credit / Utang":"#7B1FA2","Cash (Mobile)":"#1565C0","Mobile Order":"#1565C0"}
        pay_icons  = {"Cash":"💵","Credit / Utang":"💳","Cash (Mobile)":"📲","Mobile Order":"📲"}
        card_bgs   = ["#F0F4F8","#E8EEF4"]

        for i, row_data in enumerate(rows):
            # ── Use helper to safely unpack 11-field transaction row ──
            txn_id,dt,total,method,cash,change,cname,dept,buyer_type,item_names,item_count = _unpack_txn_row(row_data)

            try:
                dt_obj   = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                date_str = dt_obj.strftime("%b %d, %Y")
                time_str = dt_obj.strftime("%I:%M %p")
            except Exception:
                date_str = dt[:10]; time_str = ""

            bar_color  = pay_colors.get(method, TEXT_WHITE)
            card_bg    = card_bgs[i % 2]
            icon       = pay_icons.get(method, "💰")
            method_lbl = method.replace("Credit / Utang","Credit/Utang")

            container = ctk.CTkFrame(table, fg_color=card_bg, corner_radius=6)
            container.pack(fill="x", pady=(0,2), padx=2)
            ctk.CTkFrame(container, fg_color=bar_color, width=6,
                         corner_radius=3).place(x=0, y=0, relheight=1)

            summary = ctk.CTkFrame(container, fg_color="transparent", height=40, cursor="hand2")
            summary.pack(fill="x", padx=(8,0)); summary.pack_propagate(False)

            # Show short txn_id instead of row number
            short_id = str(txn_id)[-8:] if txn_id else "—"
            num_badge = ctk.CTkFrame(summary, fg_color=bar_color, corner_radius=4, width=72, height=16)
            num_badge.place(x=0, rely=0.5, anchor="w"); num_badge.pack_propagate(False)
            ctk.CTkLabel(num_badge, text=short_id,
                         font=ctk.CTkFont(size=9, weight="bold"),
                         text_color="#FFFFFF").place(relx=0.5, rely=0.5, anchor="center")

            ctk.CTkLabel(summary, text=date_str,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#1A1A2E").place(x=80, rely=0.28, anchor="w")
            ctk.CTkLabel(summary, text=time_str,
                         font=ctk.CTkFont(size=10),
                         text_color="#546E7A").place(x=80, rely=0.72, anchor="w")
            ctk.CTkLabel(summary, text=f"🛒 {item_count} item(s)",
                         font=ctk.CTkFont(size=11), text_color="#546E7A"
                         ).place(relx=0.30, rely=0.5, anchor="w")
            ctk.CTkLabel(summary, text=f"{icon} {method_lbl}",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=bar_color).place(relx=0.50, rely=0.5, anchor="w")
            if method == "Cash" and change > 0:
                ctk.CTkLabel(summary, text=f"Chg:₱{change:.2f}",
                             font=ctk.CTkFont(size=10), text_color="#2E7D32"
                             ).place(relx=0.68, rely=0.5, anchor="w")
            elif method == "Credit / Utang" and cname:
                ctk.CTkLabel(summary, text=cname,
                             font=ctk.CTkFont(size=10), text_color="#546E7A"
                             ).place(relx=0.68, rely=0.5, anchor="w")
            ctk.CTkLabel(summary, text=f"₱{total:.2f}",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#1565C0").place(relx=0.87, rely=0.5, anchor="w")

            arrow_lbl = ctk.CTkLabel(summary, text="▼",
                                     font=ctk.CTkFont(size=9), text_color=bar_color)
            arrow_lbl.place(relx=0.97, rely=0.5, anchor="center")

            detail_panel = ctk.CTkFrame(container, fg_color="#FFFFFF", corner_radius=0)
            expanded = [False]

            def _toggle(dp=detail_panel, txid=txn_id, exp=expanded, al=arrow_lbl, bc=bar_color):
                exp[0] = not exp[0]
                if exp[0]:
                    al.configure(text="▲")
                    dp.pack(fill="x")
                    for w in dp.winfo_children(): w.destroy()
                    # ── Fetch items for this transaction (online or offline) ──
                    items = db.get_transaction_items(txid)

                    ih = ctk.CTkFrame(dp, fg_color="#F5F5F5", height=28, corner_radius=0)
                    ih.pack(fill="x"); ih.pack_propagate(False); ih.columnconfigure(1,weight=1)
                    for txt,col,ww in [("  PRODUCT",0,240),("CATEGORY",1,0),("PRICE",2,90),("QTY",3,50),("SUBTOTAL",4,100)]:
                        kw2={"font":ctk.CTkFont(size=10,weight="bold"),"text_color":"#1A1A2E","fg_color":"transparent","anchor":"w"}
                        if ww==0: ctk.CTkLabel(ih,text=txt,**kw2).grid(row=0,column=col,sticky="w",padx=(10,4),pady=4)
                        else:     ctk.CTkLabel(ih,text=txt,width=ww,**kw2).grid(row=0,column=col,padx=(10,4),pady=4)

                    if not items:
                        # ── Show message if no items found (debug aid) ──
                        ctk.CTkLabel(dp, text="No item details found for this transaction.",
                                     font=ctk.CTkFont(size=11), text_color="#546E7A").pack(pady=8)
                    else:
                        for j,(iname,icat,iprice,iqty) in enumerate(items):
                            ibg = "#FFFFFF" if j%2==0 else "#F7F9FC"
                            ir  = ctk.CTkFrame(dp, fg_color=ibg, height=30, corner_radius=0)
                            ir.pack(fill="x"); ir.pack_propagate(False); ir.columnconfigure(1,weight=1)
                            ctk.CTkLabel(ir,text=f"  {iname}",width=240,anchor="w",
                                         font=ctk.CTkFont(size=12,weight="bold"),text_color="#1A1A2E"
                                         ).grid(row=0,column=0,sticky="w",padx=(10,4))
                            ctk.CTkLabel(ir,text=icat,anchor="w",
                                         font=ctk.CTkFont(size=11),text_color="#546E7A"
                                         ).grid(row=0,column=1,sticky="w",padx=4)
                            ctk.CTkLabel(ir,text=f"₱{iprice:.2f}",width=90,anchor="w",
                                         font=ctk.CTkFont(size=11),text_color="#1A1A2E"
                                         ).grid(row=0,column=2,padx=(10,4))
                            ctk.CTkLabel(ir,text=str(iqty),width=50,anchor="center",
                                         font=ctk.CTkFont(size=12,weight="bold"),text_color="#1A1A2E"
                                         ).grid(row=0,column=3,padx=4)
                            ctk.CTkLabel(ir,text=f"₱{iprice*iqty:.2f}",width=100,anchor="w",
                                         font=ctk.CTkFont(size=12,weight="bold"),text_color="#1565C0"
                                         ).grid(row=0,column=4,padx=(10,4))
                else:
                    al.configure(text="▼")
                    for ch in dp.winfo_children(): ch.destroy()
                    dp.pack_forget()

            for widget in [summary, arrow_lbl]:
                widget.bind("<Button-1>", lambda e, t=_toggle: t())

    # ════════════════════════════════════════════════════════════
    #  CREDIT PAGE
    # ════════════════════════════════════════════════════════════
    def _open_calendar(self, which, var, lbl, all_rows, table):
        import calendar as cal_mod
        win = ctk.CTkToplevel(self)
        win.title("Pick a Date"); win.geometry("320x300")
        win.configure(fg_color="#F5F5F5"); win.grab_set(); win.resizable(False,False)
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"320x300+{(sw-320)//2}+{(sh-300)//2}")
        now   = datetime.now()
        state = {"year": now.year, "month": now.month}

        def build(year, month):
            for w in win.winfo_children(): w.destroy()
            hdr = ctk.CTkFrame(win, fg_color="#1565C0", height=44, corner_radius=0)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            ctk.CTkButton(hdr, text="◀", width=36, height=30,
                          fg_color="transparent", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(-1)).place(x=8, rely=0.5, anchor="w")
            ctk.CTkLabel(hdr, text=f"{cal_mod.month_name[month]}  {year}",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkButton(hdr, text="▶", width=36, height=30,
                          fg_color="transparent", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(1)).place(relx=1.0, x=-8, rely=0.5, anchor="e")
            dh = ctk.CTkFrame(win, fg_color="transparent")
            dh.pack(fill="x", padx=10, pady=(6,0))
            for d in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
                ctk.CTkLabel(dh,text=d,width=36,font=ctk.CTkFont(size=10,weight="bold"),
                             text_color="#546E7A").pack(side="left")
            gf = ctk.CTkFrame(win, fg_color="transparent")
            gf.pack(fill="x", padx=10, pady=4)
            for week in cal_mod.monthcalendar(year, month):
                rf = ctk.CTkFrame(gf, fg_color="transparent"); rf.pack(fill="x", pady=1)
                for day in week:
                    if day==0: ctk.CTkLabel(rf,text="",width=36).pack(side="left")
                    else:
                        is_today = (day==now.day and month==now.month and year==now.year)
                        ctk.CTkButton(rf,text=str(day),width=34,height=28,
                                      fg_color="#1976D2" if is_today else BTN_BLUE,
                                      hover_color="#0D47A1" if is_today else "#1976D2",
                                      font=ctk.CTkFont(size=11),corner_radius=4,
                                      command=lambda d=day: pick(d)
                                      ).pack(side="left",padx=1)

        def go(delta):
            m = state["month"]+delta; y = state["year"]
            if m>12: m=1; y+=1
            if m<1:  m=12; y-=1
            state["year"]=y; state["month"]=m; build(y,m)

        def pick(day):
            chosen = f"{state['year']:04d}-{state['month']:02d}-{day:02d}"
            var.set(chosen)
            lbl.configure(text=f"{'From' if which=='from' else 'To'}: {state['month']:02d}/{day:02d}/{state['year']}",
                          text_color="#E65100")
            win.destroy()
            self._reload_credit(all_rows, table)

        build(state["year"], state["month"])

    def _show_credit(self):
        page = ctk.CTkFrame(self.content, fg_color="#F5F5F5", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(3, weight=1)
        page.rowconfigure(4, weight=0)
        page.columnconfigure(0, weight=1)
        loading = ctk.CTkLabel(page, text="⏳  Loading credits...",
                               font=ctk.CTkFont(size=16), text_color="#546E7A")
        loading.grid(row=3, column=0)
        def _fetch():
            rows        = db.get_credits(store="canteen")
            total       = sum(r[2] for r in rows)
            deduct_map  = db.get_all_deductions_map()  # batch fetch all deductions
            self.after(0, lambda r=rows, t=total, dm=deduct_map: [
                loading.destroy(),
                self._render_credit_page(page, r, t, dm)])
        threading.Thread(target=_fetch, daemon=True).start()

    def _render_credit_page(self, page, all_rows, total_cred, deduct_map=None):
        # Guard: page may have been destroyed if user navigated away
        try:
            page.winfo_children()
        except Exception:
            return
        # Store deduct_map as instance var so _reload_credit can access it
        self._deduct_map = deduct_map or {}
        for w in page.winfo_children(): w.destroy()
        page.rowconfigure(3, weight=1)
        page.rowconfigure(4, weight=0)
        page.columnconfigure(0, weight=1)

        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(18,0))
        top.columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Credit / Utang Monitor",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#1A1A2E").grid(row=0, column=0, sticky="w")
        btn_top = ctk.CTkFrame(top, fg_color="transparent")
        btn_top.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(btn_top, text="➕ Add Credit", width=120, height=36,
                      fg_color="#1565C0", hover_color="#0D47A1",
                      text_color="white",
                      font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
                      command=lambda: self._add_credit_dialog(page, all_rows, total_cred)
                      ).pack(side="left", padx=(0,8))
        ctk.CTkButton(btn_top, text="🖨  Print All", width=110, height=36,
                      fg_color="#2E7D32", hover_color="#1B5E20",
                      text_color="white",
                      font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
                      command=lambda: self._print_credit_slip(all_rows, "")
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_top, text="🗑  Delete Selected", width=145, height=36,
                      fg_color="#5D0000", hover_color="#8B0000",
                      text_color="white",
                      font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
                      command=lambda: self._delete_selected_credits(all_rows)
                      ).pack(side="left")

        filters = ctk.CTkFrame(page, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", padx=24, pady=(10,0))
        filters.columnconfigure(0, weight=1)

        search_wrap = ctk.CTkFrame(filters, fg_color="#FFFFFF", corner_radius=8,
                                   border_width=1, border_color="#1565C0")
        search_wrap.grid(row=0, column=0, sticky="ew", padx=(0,8))
        search_wrap.columnconfigure(1, weight=1)
        ctk.CTkLabel(search_wrap, text="🔍", font=ctk.CTkFont(size=14),
                     text_color="#546E7A").grid(row=0, column=0, padx=(12,4))
        self.credit_search = ctk.StringVar()
        ctk.CTkEntry(search_wrap, textvariable=self.credit_search,
                     placeholder_text="Search by name...",
                     border_width=0, fg_color="transparent", height=36,
                     font=ctk.CTkFont(size=13), text_color="black",
                     placeholder_text_color="#546E7A"
                     ).grid(row=0, column=1, sticky="ew", padx=(0,8))

        # ── Department filter ──
        depts = ["All Departments"] + sorted(set(r[4] for r in all_rows if r[4]))
        self.credit_dept_var = ctk.StringVar(value="All Departments")
        ctk.CTkOptionMenu(filters, variable=self.credit_dept_var,
                          values=depts, width=160, height=36,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                          text_color="black", font=ctk.CTkFont(size=12),
                          command=lambda _: self._reload_credit(all_rows, credit_table)
                          ).grid(row=0, column=1, padx=(0,8))

        # ── Member type filter ──
        self.credit_type_var = ctk.StringVar(value="All Types")
        ctk.CTkOptionMenu(filters, variable=self.credit_type_var,
                          values=["All Types", "Member", "Others"],
                          width=130, height=36,
                          fg_color="#FFFFFF", button_color=BTN_BLUE,
                          button_hover_color="#1976D2",
                          dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                          text_color="black", font=ctk.CTkFont(size=12),
                          command=lambda _: self._reload_credit(all_rows, credit_table)
                          ).grid(row=0, column=2, padx=(0,8))

        self.credit_from_var = ctk.StringVar()
        self.credit_to_var   = ctk.StringVar()

        hdr = ctk.CTkFrame(page, fg_color=COL_HDR, height=36, corner_radius=4)
        hdr.grid(row=2, column=0, sticky="ew", padx=24, pady=(8,2))
        hdr.pack_propagate(False)
        hdr.columnconfigure(1, weight=1)

        # Select All checkbox
        self._credit_select_all = ctk.BooleanVar(value=False)
        def _toggle_credit_all():
            val = self._credit_select_all.get()
            for var in self._credit_checked.values():
                var.set(val)
        ctk.CTkCheckBox(hdr, text="", variable=self._credit_select_all,
                        width=22, checkbox_width=20, checkbox_height=20,
                        border_color="#1565C0", fg_color="#1565C0",
                        corner_radius=10, command=_toggle_credit_all
                        ).place(x=8, rely=0.5, anchor="w")

        for txt, col, w in [("NAME",1,0),("DEPARTMENT",2,160),("BALANCE",3,140)]:
            kw = {"font":ctk.CTkFont(size=11,weight="bold"),
                  "text_color":TEXT_GREY,"fg_color":"transparent","anchor":"w"}
            if w==0: ctk.CTkLabel(hdr,text=txt,**kw).grid(row=0,column=col,sticky="w",padx=(4,4),pady=5)
            else:    ctk.CTkLabel(hdr,text=txt,width=w,**kw).grid(row=0,column=col,padx=4,pady=5)

        credit_table = ctk.CTkScrollableFrame(page, fg_color="#F0F4F8",
                                              scrollbar_button_color=BTN_BLUE, corner_radius=0)
        credit_table.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 8))
        credit_table.columnconfigure(0, weight=1)

        self.credit_search.trace_add(
            "write", lambda *_: self._reload_credit(all_rows, credit_table))
        self._reload_credit(all_rows, credit_table)

    def _reload_credit(self, all_rows, table):
        for w in table.winfo_children(): w.destroy()

        search    = self.credit_search.get().lower().strip()
        dept      = self.credit_dept_var.get()
        type_f    = getattr(self, 'credit_type_var', ctk.StringVar(value="All Types")).get().strip()
        from_str  = getattr(self,'credit_from_var',ctk.StringVar()).get().strip()
        to_str    = getattr(self,'credit_to_var',  ctk.StringVar()).get().strip()

        rows = all_rows
        # r[3] = customer_name, r[4] = department (in 7-field credit row)
        if search:   rows = [r for r in rows if search in (r[3] or "").lower() or search in str(r[0]).lower()]
        if dept != "All Departments": rows = [r for r in rows if r[4] == dept]
        if from_str:
            try:
                fd = datetime.strptime(from_str,"%Y-%m-%d")
                rows = [r for r in rows if datetime.strptime(r[1][:10],"%Y-%m-%d") >= fd]
            except ValueError: pass
        if to_str:
            try:
                td = datetime.strptime(to_str,"%Y-%m-%d")
                rows = [r for r in rows if datetime.strptime(r[1][:10],"%Y-%m-%d") <= td]
            except ValueError: pass

        # ── Member / Others type filter ──
        if type_f and type_f != "All Types":
            filtered_names = set()
            # Group by name first to check per person
            from collections import defaultdict as _dd
            name_rows = _dd(list)
            for r in rows: name_rows[r[3] or "Unknown"].append(r)
            for pname in name_rows:
                is_member = False
                for store in ["coop", "cafestore", "canteen"]:
                    try:
                        m = db.get_loyalty_member_by_card_name(pname, store=store)
                        if m:
                            is_member = True
                            break
                    except Exception:
                        pass
                if type_f == "Member" and is_member:
                    filtered_names.add(pname)
                elif type_f == "Others" and not is_member:
                    filtered_names.add(pname)
            rows = [r for r in rows if (r[3] or "Unknown") in filtered_names]

        if not rows:
            ctk.CTkLabel(table, text="No credit records found.",
                         font=ctk.CTkFont(size=14), text_color="#546E7A").pack(pady=40)
            return

        from collections import OrderedDict
        grouped = OrderedDict()
        for r in rows:
            grouped.setdefault(r[3] or "Unknown", []).append(r)

        grand_total = sum(r[2] for r in rows) if search else 0.0

        if not hasattr(self,'_credit_checked'): self._credit_checked = {}

        # ── Pre-load ALL loyalty members once (avoid per-person queries) ──
        _all_members = {}
        for store in ["coop", "cafestore", "canteen"]:
            try:
                for m in db.get_all_loyalty_members(store=store):
                    _all_members[m["name"].strip().lower()] = m
            except Exception:
                pass

        # ── Pre-load ALL teachers once ──
        _all_teachers = {}
        try:
            for t in db.get_all_teachers(store="canteen"):
                _all_teachers[t["name"].strip().lower()] = t
        except Exception:
            pass

        def _find_member_cached(name):
            return _all_members.get(name.strip().lower())

        def _find_teacher_cached(name):
            return _all_teachers.get(name.strip().lower())

        for person_name, person_rows in grouped.items():
            person_total = sum(r[2] for r in person_rows)
            # r[4] = department, r[6] = item_count (in 7-field credit row)
            dept_name    = person_rows[0][4] or "-"
            txn_count    = len(person_rows)
            latest_dt    = person_rows[0][1]
            try:    latest_str = datetime.strptime(latest_dt,"%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y")
            except: latest_str = latest_dt[:10]

            cb_key = person_name
            if cb_key not in self._credit_checked:
                self._credit_checked[cb_key] = ctk.BooleanVar(value=False)
            cb_var = self._credit_checked[cb_key]

            card = ctk.CTkFrame(table, fg_color="#FFFFFF",
                                corner_radius=8, border_width=1, border_color="#E0E0E0")
            card.pack(fill="x", pady=(0,4), padx=2)
            card.columnconfigure(0, weight=1)

            card_hdr = ctk.CTkFrame(card, fg_color="#FFFFFF", corner_radius=8, height=60)
            card_hdr.pack(fill="x", padx=1, pady=(1,0))
            card_hdr.pack_propagate(False)
            card_hdr.columnconfigure(2, weight=1)

            cb_frame = ctk.CTkFrame(card_hdr, fg_color="transparent")
            cb_frame.grid(row=0, column=0, padx=(10,4), pady=8)
            ctk.CTkCheckBox(cb_frame, text="", variable=cb_var,
                            width=22, checkbox_width=22, checkbox_height=22,
                            border_color="#1565C0", fg_color="#2E7D32",
                            corner_radius=11,
                            hover_color="#1B5E20"
                            ).pack()

            av = ctk.CTkFrame(card_hdr, fg_color="#1565C0", corner_radius=20, width=36, height=36)
            av.grid(row=0, column=1, padx=(0,8), pady=8)
            av.pack_propagate(False)
            ctk.CTkLabel(av, text=person_name[0].upper(),
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")

            info_f = ctk.CTkFrame(card_hdr, fg_color="transparent")
            info_f.grid(row=0, column=2, sticky="w")
            # Name row with primary key
            name_row = ctk.CTkFrame(info_f, fg_color="transparent")
            name_row.pack(anchor="w", fill="x")
            ctk.CTkLabel(name_row, text=person_name,
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#1A1A2E").pack(side="left")
            # Check member loyalty card first (searches all stores)
            _mid = _find_member_cached(person_name)
            if _mid:
                ctk.CTkLabel(name_row,
                             text=f"  🪪 {_mid['member_id']}",
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#7B1FA2").pack(side="left", padx=(6,0))
            else:
                # Check teacher registry (Others/non-member)
                _tid = _find_teacher_cached(person_name)
                if _tid:
                    ctk.CTkLabel(name_row,
                                 text=f"  🏫 {_tid['teacher_id']}",
                                 font=ctk.CTkFont(size=10, weight="bold"),
                                 text_color="#E65100").pack(side="left", padx=(6,0))
                else:
                    # Auto-register teacher if they have credit and dept
                    if dept_name and dept_name != "-":
                        _new = db.ensure_teacher_registered(person_name, dept_name)
                        _all_teachers[person_name.strip().lower()] = _new
                        ctk.CTkLabel(name_row,
                                     text=f"  🏫 {_new['teacher_id']}",
                                     font=ctk.CTkFont(size=10, weight="bold"),
                                     text_color="#E65100").pack(side="left", padx=(6,0))
            ctk.CTkLabel(info_f,
                         text=f"{dept_name}  •  {txn_count} transaction(s)  •  Latest: {latest_str}",
                         font=ctk.CTkFont(size=10), text_color="#546E7A").pack(anchor="w")

            action_f = ctk.CTkFrame(card_hdr, fg_color="transparent")
            action_f.grid(row=0, column=3, sticky="e", padx=(8,12))

            # ── Show balance adjusted for admin deductions ──
            deducted  = getattr(self, '_deduct_map', {}).get(person_name, 0.0)
            balance   = round(max(person_total - deducted, 0), 2)
            is_paid   = (balance == 0 and person_total > 0)
            bal_color = "#2E7D32" if is_paid else "#1565C0"
            bal_text  = "PAID ✓" if is_paid else f"₱{balance:.2f}"

            bal_frame = ctk.CTkFrame(action_f, fg_color="transparent")
            bal_frame.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(bal_frame, text=f"₱{person_total:.2f}",
                         font=ctk.CTkFont(size=11), text_color="#546E7A").pack(anchor="e")
            ctk.CTkLabel(bal_frame, text=bal_text,
                         font=ctk.CTkFont(size=16, weight="bold"),
                         text_color=bal_color).pack(anchor="e")

            dot_btn = ctk.CTkButton(action_f, text="⋯", width=34, height=34,
                                    fg_color="#FFFFFF", hover_color="#F0F4F8",
                                    text_color="#000000",
                                    border_width=1, border_color="#CFD8DC",
                                    font=ctk.CTkFont(size=16, weight="bold"),
                                    corner_radius=6)
            dot_btn.pack(side="left", padx=(0,6))

            ctk.CTkButton(action_f, text="🖨", width=34, height=34,
                          fg_color="#2E7D32", hover_color="#1B5E20", text_color="white",
                          font=ctk.CTkFont(size=14), corner_radius=6,
                          command=lambda r=person_rows, n=person_name:
                              self._print_credit_slip(r, n)
                          ).pack(side="left", padx=(0,6))

            ctk.CTkButton(action_f, text="Del", width=40, height=34,
                          fg_color="#5D0000", hover_color="#8B0000", text_color="white",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          command=lambda n=person_name, pr=person_rows:
                              self._delete_single_credit(n, pr, all_rows)
                          ).pack(side="left")

            txn_panel = ctk.CTkFrame(card, fg_color="#FFFFFF", corner_radius=0)
            expanded  = [False]

            # ── BUG FIX 3: Use _unpack_credit_row() to safely unpack 7-field rows ──
            # Previously this loop used a 6-field unpack which crashed because
            # credit rows now have 7 fields (added buyer_type at index [5])
            def _toggle_txn(panel=txn_panel, prows=person_rows, btn=dot_btn, exp=expanded):
                exp[0] = not exp[0]
                if exp[0]:
                    btn.configure(text="⌃")
                    panel.pack(fill="x", padx=1, pady=(0,1))
                    for w in panel.winfo_children(): w.destroy()

                    sh = ctk.CTkFrame(panel, fg_color="#F5F5F5", height=30, corner_radius=0)
                    sh.pack(fill="x"); sh.pack_propagate(False)
                    sh.columnconfigure(2, weight=1)
                    for txt,col,w in [("  TXN ID",0,110),("DATE & TIME",1,190),("ITEMS",2,0),("AMOUNT",3,110)]:
                        kw2={"font":ctk.CTkFont(size=10,weight="bold"),
                             "text_color":"#1A1A2E","fg_color":"transparent","anchor":"w"}
                        if w==0: ctk.CTkLabel(sh,text=txt,**kw2).grid(row=0,column=col,sticky="w",padx=(8,4),pady=5)
                        else:    ctk.CTkLabel(sh,text=txt,width=w,**kw2).grid(row=0,column=col,padx=(8,4),pady=5)

                    for j, r in enumerate(prows):
                        # ── Safe unpack: credit row has 7 fields ──
                        # (txn_id, dt, total, customer_name, department, buyer_type, item_count)
                        txn_id, dt, total, cname, dname, buyer_type, icount = _unpack_credit_row(r)

                        try:    ds = datetime.strptime(dt,"%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y  %I:%M %p")
                        except: ds = dt[:16]

                        # ── Fetch actual item names for this transaction (online or offline) ──
                        items = db.get_transaction_items(txn_id)
                        if items:
                            item_text = ", ".join([f"{nm} x{qty}" for nm,_cat,_price,qty in items])
                        else:
                            item_text = f"{icount} item(s)" if icount else "No items"

                        ibg = "#FFFFFF" if j%2==0 else "#F7F9FC"
                        ir  = ctk.CTkFrame(panel, fg_color=ibg, height=34, corner_radius=0)
                        ir.pack(fill="x"); ir.pack_propagate(False); ir.columnconfigure(2,weight=1)
                        ctk.CTkLabel(ir,text=f"  #{txn_id}",width=110,anchor="w",
                                     font=ctk.CTkFont(size=11,weight="bold"),text_color="#1A1A2E"
                                     ).grid(row=0,column=0,padx=(8,4))
                        ctk.CTkLabel(ir,text=ds,width=190,anchor="w",
                                     font=ctk.CTkFont(size=11),text_color="#1A1A2E"
                                     ).grid(row=0,column=1,padx=(8,4))
                        ctk.CTkLabel(ir,text=item_text,anchor="w",
                                     font=ctk.CTkFont(size=11),text_color="#546E7A"
                                     ).grid(row=0,column=2,sticky="w",padx=4)
                        ctk.CTkLabel(ir,text=f"₱{total:.2f}",width=110,anchor="center",
                                     font=ctk.CTkFont(size=12,weight="bold"),text_color="#1565C0"
                                     ).grid(row=0,column=3,padx=(4,8))

                    st_bar = ctk.CTkFrame(panel, fg_color="#FFFFFF", height=32, corner_radius=0)
                    st_bar.pack(fill="x"); st_bar.pack_propagate(False)
                    ctk.CTkLabel(st_bar, text=f"Total Utang: ₱{sum(r[2] for r in prows):.2f}",
                                 font=ctk.CTkFont(size=12,weight="bold"),
                                 text_color="#1565C0").place(relx=0.97, rely=0.5, anchor="e")
                else:
                    btn.configure(text="⋯")
                    panel.pack_forget()

            dot_btn.configure(command=_toggle_txn)

    # ── BUG FIX 2: Mark as Paid — use _unpack_credit_row() to avoid "too many values" error ──
    # Previously unpacked as 6 values but credit rows now have 7 fields
    def _add_credit_dialog(self, page, all_rows, total_cred):
        """Add credit — Member ID, Name, Amount only."""
        win = ctk.CTkToplevel(self)
        win.title("Add Credit / Utang")
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        win.resizable(False, False)
        W, H = 420, 300
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        win.configure(fg_color="#FFFFFF")

        ctk.CTkLabel(win, text="➕  Add Credit / Utang",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#1565C0").pack(pady=(16,2))
        ctk.CTkLabel(win, text="Enter Member ID to auto-fill name",
                     font=ctk.CTkFont(size=11),
                     text_color="#546E7A").pack(pady=(0,8))

        form = ctk.CTkFrame(win, fg_color="transparent")
        form.pack(fill="x", padx=24)
        form.columnconfigure(1, weight=1)

        def _field(lbl, row, ph="", readonly=False):
            ctk.CTkLabel(form, text=lbl,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#546E7A", anchor="w", width=110
                         ).grid(row=row, column=0, sticky="w", pady=(6,0))
            var = ctk.StringVar()
            e   = ctk.CTkEntry(form, textvariable=var,
                               placeholder_text=ph, height=36,
                               font=ctk.CTkFont(size=12),
                               state="disabled" if readonly else "normal",
                               fg_color="#F5F5F5" if readonly else "#FFFFFF")
            e.grid(row=row, column=1, sticky="ew", padx=(10,0), pady=(6,0))
            return var, e

        mid_var,    _   = _field("Member ID:", 0, "e.g. MBR-001")
        name_var,  ne   = _field("Name:",      1, "Auto-filled...", readonly=True)
        amount_var, _   = _field("Amount (₱):",2, "e.g. 150.00")

        status_lbl = ctk.CTkLabel(win, text="",
                                   font=ctk.CTkFont(size=11),
                                   text_color="#2E7D32")
        status_lbl.pack(pady=(6,0))

        dept_ref = {"v": ""}

        def _lookup(*args):
            mid = mid_var.get().strip()
            if len(mid) >= 2:
                members = db.get_all_loyalty_members(store="coop") or []
                for m in members:
                    if m.get("member_id","").lower() == mid.lower() or                        mid.lower() in m.get("member_id","").lower():
                        ne.configure(state="normal")
                        name_var.set(m.get("name",""))
                        ne.configure(state="disabled")
                        dept_ref["v"] = m.get("department","")
                        status_lbl.configure(
                            text=f"✅ Found: {m.get('name','')}",
                            text_color="#2E7D32")
                        return
                ne.configure(state="normal")
                dept_ref["v"] = ""
                status_lbl.configure(
                    text="⚠️ Not found — type name manually",
                    text_color="#F57F17")
            else:
                ne.configure(state="normal")
                name_var.set("")
                ne.configure(state="disabled")
                dept_ref["v"] = ""
                status_lbl.configure(text="")

        mid_var.trace_add("write", _lookup)

        def _save():
            mid  = mid_var.get().strip()
            name = name_var.get().strip()
            dept = dept_ref["v"]
            try:
                amount = float(amount_var.get().strip())
                if amount <= 0: raise ValueError()
            except Exception:
                messagebox.showwarning("Invalid",
                    "Please enter a valid amount.", parent=win)
                return
            if not name:
                messagebox.showwarning("Required",
                    "Member not found. Enter Member ID first.", parent=win)
                return
            win.destroy()
            from datetime import datetime as _dt
            now  = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
            cart = [{"barcode": mid or "MANUAL",
                     "name":    f"Credit — {name}",
                     "price":   amount, "qty": 1, "category": "Credit"}]
            def _do():
                try:
                    txn_id = db.save_transaction(
                        dt=now, total=amount,
                        method="Credit / Utang",
                        cash_given=0, change_given=0,
                        customer_name=name, department=dept,
                        items=cart, buyer_type="Member",
                        store="canteen",
                    )
                    self.after(0, lambda: [
                        messagebox.showinfo("✅ Credit Added",
                            f"₱{amount:.2f} credit added for {name}\n"
                            f"Transaction: {txn_id}", parent=self),
                        self._show_credit()
                    ])
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror(
                        "Error", f"Failed: {e}", parent=self))
            threading.Thread(target=_do, daemon=True).start()

        btn_f = ctk.CTkFrame(win, fg_color="transparent")
        btn_f.pack(side="bottom", pady=14)
        ctk.CTkButton(btn_f, text="💾 Add Credit",
                      width=150, height=40,
                      fg_color="#1565C0", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=_save).pack(side="left", padx=(0,8))
        ctk.CTkButton(btn_f, text="Cancel",
                      width=100, height=40,
                      fg_color="#757575", hover_color="#546E7A",
                      font=ctk.CTkFont(size=13),
                      command=win.destroy).pack(side="left")
        win.bind("<Return>", lambda e: _save())
    def _delete_selected_credits(self, all_rows):
        """Delete ALL credit transactions for selected customers."""
        selected_names = [n for n, var in self._credit_checked.items() if var.get()]
        if not selected_names:
            messagebox.showinfo("No Selection",
                                "Select customer(s) using the checkbox first.", parent=self)
            return
        if not messagebox.askyesno("Delete Credits",
                                   f"Permanently delete ALL credit transactions for "
                                   f"{len(selected_names)} customer(s)?\n\n"
                                   f"⚠ This cannot be undone!", parent=self):
            return
        for name in selected_names:
            self._do_delete_credit(name)
        messagebox.showinfo("Deleted",
                            f"✓ Credit records deleted for {len(selected_names)} customer(s).",
                            parent=self)
        self._show_credit()

    def _delete_single_credit(self, name, person_rows, all_rows):
        """Delete credit transactions for one customer."""
        if not messagebox.askyesno("Delete Credit",
                                   f"Delete ALL credit transactions for '{name}'?\n\n"
                                   f"⚠ This cannot be undone!", parent=self):
            return
        self._do_delete_credit(name)
        self._show_credit()

    def _do_delete_credit(self, name):
        """Core delete logic — Firestore + SQLite for one customer."""
        import sqlite3
        store = "canteen"
        # Firestore
        try:
            results = db._query("transactions",
                                filters=[["customer_name","EQUAL", name]])
            for r in results:
                d = db._parse_doc(r)
                if d.get("store","") != store: continue
                txn_id = d.get("txn_id","")
                items = db._query("transaction_items",
                                  filters=[["txn_id","EQUAL",txn_id]])
                for it in items:
                    dn = it.get("document",{}).get("name","")
                    if dn: db._delete_doc("transaction_items", dn.split("/")[-1])
                dn = r.get("document",{}).get("name","")
                if dn: db._delete_doc("transactions", dn.split("/")[-1])
        except Exception as e:
            print(f"Firestore delete error: {e}")
        # SQLite
        try:
            conn = sqlite3.connect(str(offline_db.DB_PATH))
            cur  = conn.cursor()
            cur.execute("SELECT txn_id FROM transactions_local WHERE customer_name=? AND store=?",
                        (name, store))
            for (tid,) in cur.fetchall():
                cur.execute("DELETE FROM transaction_items_local WHERE txn_id=?", (tid,))
            cur.execute("DELETE FROM transactions_local WHERE customer_name=? AND store=?",
                        (name, store))
            conn.commit(); conn.close()
        except Exception as e:
            print(f"SQLite delete error: {e}")

    def _mark_selected_paid(self, all_rows):
        if not hasattr(self,'_credit_checked'):
            messagebox.showinfo("No Selection","Select customer(s) first using the checkbox.",parent=self); return
        selected_names = [name for name, var in self._credit_checked.items() if var.get()]
        if not selected_names:
            messagebox.showinfo("No Selection","Select at least one customer using the checkbox.",parent=self); return

        from collections import OrderedDict
        grouped = OrderedDict()
        for r in all_rows:
            # ── Safe unpack: 7-field credit row ──
            txn_id, dt, total, cname, dept, buyer_type, icount = _unpack_credit_row(r)
            nm = cname or "Unknown"
            if nm in selected_names:
                grouped.setdefault(nm, []).append(r)

        total_paid = sum(r[2] for rs in grouped.values() for r in rs)
        if not messagebox.askyesno("Mark Paid",
                                   f"Mark {len(selected_names)} customer(s) as FULLY PAID?\n\n"
                                   f"Total: ₱{total_paid:.2f}\n\n"
                                   f"Customers: {', '.join(selected_names)}",
                                   parent=self): return
        try:
            for name, person_rows in grouped.items():
                for r in person_rows:
                    # ── Safe unpack per row ──
                    txn_id, dt, total, cname, dname, buyer_type, icount = _unpack_credit_row(r)
                    # Delete transaction items from Firestore
                    item_docs = db._query("transaction_items", filters=[["txn_id","EQUAL",txn_id]])
                    for it in item_docs:
                        doc_name = it.get("document",{}).get("name","")
                        if doc_name: db._delete_doc("transaction_items", doc_name.split("/")[-1])
                    # Delete transaction from Firestore (query by txn_id only, filter store in Python)
                    txn_docs = db._query("transactions", filters=[["txn_id","EQUAL",txn_id]])
                    for tr in txn_docs:
                        d = db._parse_doc(tr)
                        if d.get("store","") != "canteen": continue
                        doc_name = tr.get("document",{}).get("name","")
                        if doc_name: db._delete_doc("transactions", doc_name.split("/")[-1])
            # Reset checkboxes for paid customers
            for name in selected_names:
                if name in self._credit_checked:
                    self._credit_checked[name].set(False)
            messagebox.showinfo("Paid","Selected customer(s) marked as fully paid!",parent=self)
            self._show_credit()
        except Exception as e:
            messagebox.showerror("Error",f"Unable to mark as paid.\n\n{e}",parent=self)

    def _update_credit_footer(self, rows, search, grouped=None, grand_total=0.0):
        pass  # Footer removed

    def _print_credit_slip(self, rows, search):
        import os, platform, subprocess, tempfile
        name_label = search.title() if isinstance(search,str) and search else "All Customers"

        def _norm(name):
            return " ".join((name or "").strip().lower().split())

        # ── Build ID map — members take priority over teachers ──
        member_id_map = {}
        try:
            for store in ["coop","cafestore","canteen"]:
                for m in (db.get_all_loyalty_members(store=store) or []):
                    member_id_map[_norm(m.get("name",""))] = m.get("member_id","")
            for store in ["cafestore","canteen"]:
                for t in (db.get_all_teachers(store=store) or []):
                    key = _norm(t.get("name",""))
                    if key not in member_id_map:
                        member_id_map[key] = t.get("teacher_id","")
        except Exception as e:
            print(f"[CreditPrint] ID lookup error: {e}")

        # ── For any name not found, try direct SQLite lookup ──
        try:
            import sqlite3 as _sql
            conn = _sql.connect(str(offline_db.DB_PATH))
            conn.row_factory = _sql.Row
            cur = conn.cursor()
            for row in rows:
                _, _, _, cname, _, _, _ = _unpack_credit_row(row)
                if not cname: continue
                key = _norm(cname)
                if key not in member_id_map or not member_id_map[key]:
                    cur.execute("SELECT member_id FROM loyalty_members WHERE LOWER(TRIM(name))=?",
                                (key,))
                    r = cur.fetchone()
                    if r:
                        member_id_map[key] = r["member_id"]
                    else:
                        cur.execute("SELECT teacher_id FROM teachers_registry WHERE LOWER(TRIM(name))=?",
                                    (key,))
                        r = cur.fetchone()
                        if r:
                            member_id_map[key] = r["teacher_id"]
            conn.close()
        except Exception as e:
            print(f"[CreditPrint] SQLite fallback error: {e}")

        def generate_pdf(rows, name_label, member_id_map):
            try:
                from reportlab.lib.pagesizes import A5
                from reportlab.lib import colors
                from reportlab.lib.units import cm
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
                from reportlab.lib.styles import ParagraphStyle
                from reportlab.lib.enums import TA_CENTER
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); tmp.close()
                doc = SimpleDocTemplate(tmp.name, pagesize=A5,
                                        topMargin=1.1*cm, bottomMargin=1.1*cm,
                                        leftMargin=1.2*cm, rightMargin=1.2*cm)
                RED  = colors.HexColor("#1565C0")
                GREY = colors.HexColor("#555555")
                BLACK= colors.HexColor("#222222")
                story = []
                c_s = ParagraphStyle("c",fontSize=18,fontName="Helvetica-Bold",textColor=RED,alignment=TA_CENTER,spaceAfter=2)
                s_s = ParagraphStyle("s",fontSize=9, fontName="Helvetica",   textColor=GREY,alignment=TA_CENTER,spaceAfter=2)
                n_s = ParagraphStyle("n",fontSize=13,fontName="Helvetica-Bold",textColor=BLACK,alignment=TA_CENTER,spaceAfter=4)
                story.extend([Paragraph("CANTEEN",c_s),
                               Paragraph("Credit / Utang Slip",s_s),
                               Paragraph(f"Printed: {datetime.now().strftime('%B %d, %Y  %I:%M %p')}",s_s),
                               Spacer(1,0.2*cm),HRFlowable(width="100%",thickness=2,color=RED),
                               Spacer(1,0.2*cm),Paragraph(f"Customer: {name_label}",n_s),Spacer(1,0.2*cm)])
                from collections import OrderedDict
                grouped = OrderedDict()
                for row in rows:
                    txn_id, dt, total, cname, dept_name, buyer_type, icount = _unpack_credit_row(row)
                    if not cname: continue
                    if cname not in grouped:
                        grouped[cname] = {"dept": dept_name, "total": 0.0}
                    grouped[cname]["total"] += float(total)
                t_data = [["MBR/TCH ID", "Name", "Department", "Amount"]]
                for cname, info in grouped.items():
                    mid = member_id_map.get(" ".join(cname.strip().lower().split()), "Unregistered")
                    t_data.append([mid, cname, info["dept"] or "-", f"₱{info['total']:.2f}"])
                if len(t_data) == 1:
                    t_data.append(["-", "No records", "-", "₱0.00"])
                t = Table(t_data, colWidths=[2.5*cm,4.5*cm,2.8*cm,2.4*cm], repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND",(0,0),(-1,0),RED),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                    ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,0),9),
                    ("FONTSIZE",(0,1),(-1,-1),8),
                    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F9F9F9"),colors.white]),
                    ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                    ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
                    ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
                    ("ALIGN",(0,0),(0,-1),"CENTER"),("ALIGN",(3,0),(3,-1),"RIGHT"),
                    ("TEXTCOLOR",(3,1),(3,-1),RED),("FONTNAME",(3,1),(3,-1),"Helvetica-Bold")]))
                story.append(t)
                story.append(Spacer(1,0.25*cm))
                grand = sum(info["total"] for info in grouped.values())
                tt = Table([["","","TOTAL UTANG",f"₱{grand:.2f}"]],
                           colWidths=[2.5*cm,4.5*cm,2.8*cm,2.4*cm])
                tt.setStyle(TableStyle([
                    ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#FFF0F0")),
                    ("TEXTCOLOR",(2,0),(3,0),RED),("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),
                    ("FONTSIZE",(0,0),(-1,-1),10),("BOX",(0,0),(-1,-1),1.2,RED),
                    ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
                    ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
                    ("ALIGN",(3,0),(3,0),"RIGHT")]))
                story.extend([tt,Spacer(1,0.35*cm),
                               HRFlowable(width="100%",thickness=1,color=colors.HexColor("#DDDDDD")),
                               Paragraph("Canteen POS — Credit Slip",
                                         ParagraphStyle("f",fontSize=8,textColor=GREY,alignment=TA_CENTER))])
                doc.build(story)
                return tmp.name
            except ImportError:
                return None

        pdf_path = generate_pdf(rows, name_label, member_id_map)
        if pdf_path:
            try:
                if platform.system()=="Windows": os.startfile(pdf_path)
                elif platform.system()=="Darwin": subprocess.run(["open",pdf_path])
                else: subprocess.run(["xdg-open",pdf_path])
                messagebox.showinfo("PDF Ready","Credit slip PDF opened!\nPrint it from the PDF viewer.",parent=self)
            except Exception as ex:
                messagebox.showerror("Error",str(ex),parent=self)
        else:
            messagebox.showinfo("Install Required","pip install reportlab",parent=self)

    # ════════════════════════════════════════════════════════════
    #  CUSTOMER COOP MEMBER PAGE
    # ── BUG FIX 1: Offline member display ──
    # Previously buyer_type was read from r[8] which only exists in 11-field rows.
    # Now using _unpack_txn_row() which safely handles both 10 and 11-field rows.
    # ════════════════════════════════════════════════════════════
    def _show_member_dashboard(self):
        import calendar as cal_mod
        page = ctk.CTkFrame(self.content, fg_color="#F5F5F5", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(3, weight=1)
        page.columnconfigure(0, weight=1)
        loading = ctk.CTkLabel(page, text="⏳  Loading member transactions...",
                               font=ctk.CTkFont(size=16), text_color="#546E7A")
        loading.grid(row=3, column=0)

        def _fetch():
            rows = db.get_all_transactions(store="canteen")
            self.after(0, lambda r=rows: _render(r))

        def _render(all_rows):
            loading.destroy()
            member_rows = []
            for r in all_rows:
                # ── Use safe unpack so buyer_type is always at index [8] ──
                txn_id,dt,total,method,cash,change,cname,dept,buyer_type,item_names,item_count = _unpack_txn_row(r)
                # Filter: only show "Member" buyer_type with a valid customer name
                if (buyer_type or "").strip() == "Member" and (cname or "").strip():
                    member_rows.append((txn_id,dt,total,method,cash,change,cname,dept,buyer_type,item_names,item_count))

            top = ctk.CTkFrame(page, fg_color="transparent")
            top.grid(row=0, column=0, sticky="ew", padx=24, pady=(18,6))
            top.columnconfigure(0, weight=1)
            ctk.CTkLabel(top, text="Coop Member Transactions",
                         font=ctk.CTkFont(size=22, weight="bold"),
                         text_color="#1A1A2E").grid(row=0, column=0, sticky="w")
            self._member_check_vars = {}
            # Delete selected button
            del_btn_frame = ctk.CTkFrame(top, fg_color="transparent")
            del_btn_frame.grid(row=0, column=1, sticky="e")
            ctk.CTkButton(del_btn_frame, text="🗑  Delete Selected",
                          width=150, height=34, fg_color="#5D0000", hover_color="#8B0000",
                          font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
                          command=lambda: self._delete_selected_member_txns()
                          ).pack(side="left", padx=(0,8))
            # (total removed)

            filters = ctk.CTkFrame(page, fg_color="#FFFFFF", corner_radius=8,
                                   border_width=1, border_color="#1565C0")
            filters.grid(row=1, column=0, sticky="ew", padx=24, pady=(0,8))

            ctk.CTkLabel(filters, text="🔍", font=ctk.CTkFont(size=14),
                         text_color="#546E7A").grid(row=0,column=0,padx=(12,4),pady=8)
            self.member_search_var = ctk.StringVar()
            ctk.CTkEntry(filters, textvariable=self.member_search_var,
                         placeholder_text="Search member name or transaction ID...",
                         border_width=0, fg_color="#FFFFFF", height=34,
                         font=ctk.CTkFont(size=13), text_color="black",
                         placeholder_text_color="#546E7A", width=200
                         ).grid(row=0,column=1,sticky="w",padx=(0,12),pady=8)

            ctk.CTkFrame(filters,fg_color="#1565C0",width=2,height=28).grid(row=0,column=2,padx=8)

            # ── Cash / Credit filter dropdown ──
            ctk.CTkLabel(filters, text="💳 Method:", font=ctk.CTkFont(size=12),
                         text_color="#546E7A").grid(row=0, column=2, padx=(8,4))
            self.member_method_var = ctk.StringVar(value="All Methods")
            ctk.CTkOptionMenu(filters, variable=self.member_method_var,
                              values=["All Methods", "Cash", "Cash (Mobile)", "Credit / Utang", "Mobile Order"],
                              width=160, height=30,
                              fg_color="#FFFFFF", button_color=BTN_BLUE,
                              button_hover_color="#1976D2",
                              dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                              text_color="black", font=ctk.CTkFont(size=11),
                              command=lambda _: self._reload_member_table(member_rows, member_table)
                              ).grid(row=0, column=3, padx=(0,8), pady=8)

            ctk.CTkFrame(filters,fg_color="#1565C0",width=2,height=28).grid(row=0,column=4,padx=8)

            ctk.CTkLabel(filters,text="📊 Period:",font=ctk.CTkFont(size=12),
                         text_color="#546E7A").grid(row=0,column=5,padx=(8,4))
            self.member_period_var = ctk.StringVar(value="Month")
            ctk.CTkOptionMenu(filters,variable=self.member_period_var,
                              values=["Month","Year"],width=90,height=30,
                              fg_color="#FFFFFF",button_color=BTN_BLUE,
                              button_hover_color="#1976D2",dropdown_fg_color="#FFFFFF",
                              dropdown_text_color="#1A1A2E",text_color="black",
                              font=ctk.CTkFont(size=11),
                              command=lambda _: self._reload_member_table(member_rows, member_table)
                              ).grid(row=0,column=6,padx=(0,8),pady=8)

            month_names = list(cal_mod.month_name)[1:]
            now = datetime.now()
            self.member_month_var = ctk.StringVar(value=cal_mod.month_name[now.month])
            ctk.CTkOptionMenu(filters,variable=self.member_month_var,
                              values=month_names,width=130,height=30,
                              fg_color="#FFFFFF",button_color=BTN_BLUE,
                              button_hover_color="#1976D2",dropdown_fg_color="#FFFFFF",
                              dropdown_text_color="#1A1A2E",text_color="black",
                              font=ctk.CTkFont(size=11),
                              command=lambda _: self._reload_member_table(member_rows, member_table)
                              ).grid(row=0,column=7,padx=(0,8),pady=8)

            year_values = [str(y) for y in range(now.year-5, now.year+6)]
            self.member_year_var = ctk.StringVar(value=str(now.year))
            ctk.CTkOptionMenu(filters,variable=self.member_year_var,
                              values=year_values,width=90,height=30,
                              fg_color="#FFFFFF",button_color=BTN_BLUE,
                              button_hover_color="#1976D2",dropdown_fg_color="#FFFFFF",
                              dropdown_text_color="#1A1A2E",text_color="black",
                              font=ctk.CTkFont(size=11),
                              command=lambda _: self._reload_member_table(member_rows, member_table)
                              ).grid(row=0,column=8,padx=(0,8),pady=8)

            ctk.CTkFrame(filters,fg_color="#1565C0",width=2,height=28).grid(row=0,column=9,padx=8)

            ctk.CTkLabel(filters,text="📅 Single Date:",font=ctk.CTkFont(size=12),
                         text_color="#546E7A").grid(row=0,column=10,padx=(8,4))
            self.member_date_var = ctk.StringVar()
            self.member_date_lbl = ctk.CTkLabel(filters,text="Pick a date",
                                                font=ctk.CTkFont(size=12,weight="bold"),
                                                text_color="#E65100",cursor="hand2")
            self.member_date_lbl.grid(row=0,column=11,padx=4)
            self.member_date_lbl.bind("<Button-1>",
                lambda e: self._open_member_calendar(member_rows, member_table))

            ctk.CTkButton(filters,text="✕",width=30,height=30,
                          fg_color=BTN_BLUE,hover_color="#1976D2",
                          font=ctk.CTkFont(size=11),corner_radius=6,
                          command=lambda: [self.member_date_var.set(""),
                                           self.member_date_lbl.configure(text="Pick a date"),
                                           self.member_method_var.set("All Methods"),
                                           self.member_source_var.set("All"),
                                           self._reload_member_table(member_rows,member_table)]
                          ).grid(row=0,column=12,padx=(4,4),pady=8)

            # ── 📱 Mobile Orders filter — next to X button ──
            self.member_source_var = ctk.StringVar(value="All")
            ctk.CTkOptionMenu(filters, variable=self.member_source_var,
                              values=["All", "POS Orders", "Mobile Orders"],
                              width=130, height=30,
                              fg_color="#FFFFFF", button_color=BTN_BLUE,
                              button_hover_color="#1976D2",
                              dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                              text_color="black", font=ctk.CTkFont(size=11),
                              command=lambda _: self._reload_member_table(member_rows, member_table)
                              ).grid(row=0, column=13, padx=(0,4), pady=8)

            ctk.CTkButton(filters,text="🖨 Print All",width=96,height=30,
                          fg_color="#2E7D32",hover_color="#1B5E20",
                          text_color="white",font=ctk.CTkFont(size=11,weight="bold"),
                          corner_radius=6,
                          command=lambda: self._print_member_summary(
                              self._filter_member_rows(member_rows), None)
                          ).grid(row=0,column=14,padx=(0,12),pady=8)

            # ── Column header with Select All ──
            mcol_hdr = ctk.CTkFrame(page, fg_color=COL_HDR, height=34, corner_radius=0)
            mcol_hdr.grid(row=2, column=0, sticky="ew", padx=24, pady=(4,0))
            mcol_hdr.pack_propagate(False)
            mcol_hdr.columnconfigure(1, weight=1)
            self._member_select_all = ctk.BooleanVar(value=False)
            def _toggle_member_all():
                val = self._member_select_all.get()
                for var in self._member_check_vars.values():
                    var.set(val)
            ctk.CTkCheckBox(mcol_hdr, text="", variable=self._member_select_all,
                            width=22, checkbox_width=20, checkbox_height=20,
                            border_color="#1565C0", fg_color="#1565C0",
                            corner_radius=10, command=_toggle_member_all
                            ).place(x=8, rely=0.5, anchor="w")
            ctk.CTkLabel(mcol_hdr, text="NAME / MEMBER ID",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=TEXT_GREY, fg_color="transparent", anchor="w"
                         ).grid(row=0, column=1, sticky="w", padx=(4,4), pady=5)
            ctk.CTkLabel(mcol_hdr, text="TOTAL",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=TEXT_GREY, fg_color="transparent", anchor="e",
                         width=120
                         ).grid(row=0, column=2, padx=(4,80), pady=5)

            member_table = ctk.CTkScrollableFrame(page, fg_color="#F0F4F8",
                                                  scrollbar_button_color=BTN_BLUE, corner_radius=0)
            member_table.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0,12))
            member_table.columnconfigure(0, weight=1)
            self._member_all_rows = member_rows
            self.member_search_var.trace_add("write",
                lambda *_: self._reload_member_table(member_rows, member_table))
            self._reload_member_table(member_rows, member_table)

        threading.Thread(target=_fetch, daemon=True).start()

    def _open_member_calendar(self, all_rows, table):
        import calendar as cal_mod
        win = ctk.CTkToplevel(self)
        win.title("Pick a Date"); win.geometry("320x300")
        win.configure(fg_color="#F5F5F5"); win.grab_set(); win.resizable(False,False)
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"320x300+{(sw-320)//2}+{(sh-300)//2}")
        now   = datetime.now()
        state = {"year": now.year, "month": now.month}

        def build(year, month):
            for w in win.winfo_children(): w.destroy()
            hdr = ctk.CTkFrame(win,fg_color="#1565C0",height=44,corner_radius=0)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            ctk.CTkButton(hdr,text="◀",width=36,height=30,fg_color="transparent",
                          hover_color="#0D47A1",font=ctk.CTkFont(size=14),text_color="white",
                          command=lambda: go(-1)).place(x=8,rely=0.5,anchor="w")
            ctk.CTkLabel(hdr,text=f"{cal_mod.month_name[month]}  {year}",
                         font=ctk.CTkFont(size=14,weight="bold"),
                         text_color="white").place(relx=0.5,rely=0.5,anchor="center")
            ctk.CTkButton(hdr,text="▶",width=36,height=30,fg_color="transparent",
                          hover_color="#0D47A1",font=ctk.CTkFont(size=14),text_color="white",
                          command=lambda: go(1)).place(relx=1.0,x=-8,rely=0.5,anchor="e")
            dh = ctk.CTkFrame(win,fg_color="transparent")
            dh.pack(fill="x",padx=10,pady=(6,0))
            for d in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
                ctk.CTkLabel(dh,text=d,width=36,font=ctk.CTkFont(size=10,weight="bold"),
                             text_color="#546E7A").pack(side="left")
            gf = ctk.CTkFrame(win,fg_color="transparent")
            gf.pack(fill="x",padx=10,pady=4)
            for week in cal_mod.monthcalendar(year,month):
                rf = ctk.CTkFrame(gf,fg_color="transparent"); rf.pack(fill="x",pady=1)
                for day in week:
                    if day==0: ctk.CTkLabel(rf,text="",width=36).pack(side="left")
                    else:
                        is_today=(day==now.day and month==now.month and year==now.year)
                        ctk.CTkButton(rf,text=str(day),width=34,height=28,
                                      fg_color="#1976D2" if is_today else BTN_BLUE,
                                      hover_color="#0D47A1" if is_today else "#1976D2",
                                      font=ctk.CTkFont(size=11),corner_radius=4,
                                      command=lambda d=day: pick(d)
                                      ).pack(side="left",padx=1)

        def go(delta):
            m=state["month"]+delta; y=state["year"]
            if m>12: m=1; y+=1
            if m<1:  m=12; y-=1
            state["year"]=y; state["month"]=m; build(y,m)

        def pick(day):
            chosen=f"{state['year']:04d}-{state['month']:02d}-{day:02d}"
            self.member_date_var.set(chosen)
            self.member_date_lbl.configure(text=f"{state['month']:02d}/{day:02d}/{state['year']}")
            win.destroy()
            self._reload_member_table(all_rows, table)

        build(state["year"], state["month"])

    def _filter_member_rows(self, all_rows):
        import calendar as cal_mod
        rows = list(all_rows)
        search      = getattr(self,'member_search_var',ctk.StringVar()).get().strip().lower()
        period      = getattr(self,'member_period_var',ctk.StringVar(value='Month')).get().strip()
        month_name  = getattr(self,'member_month_var',
                              ctk.StringVar(value=cal_mod.month_name[datetime.now().month])).get().strip()
        year_str    = getattr(self,'member_year_var',ctk.StringVar(value=str(datetime.now().year))).get().strip()
        date_q      = getattr(self,'member_date_var',ctk.StringVar()).get().strip()
        method_q    = getattr(self,'member_method_var',ctk.StringVar(value='All Methods')).get().strip()
        source_q    = getattr(self,'member_source_var',ctk.StringVar(value='All')).get().strip()
        if search:
            rows = [r for r in rows if search in str(r[0]).lower() or search in str(r[6]).lower()]
        # Method filter
        if method_q and method_q != "All Methods":
            rows = [r for r in rows if str(r[3]) == method_q]
        # Source filter: POS Orders vs Mobile Orders
        if source_q == "Mobile Orders":
            rows = [r for r in rows if str(r[3]) == "Mobile Order"]
        elif source_q == "POS Orders":
            rows = [r for r in rows if str(r[3]) != "Mobile Order"]
        if date_q:
            rows = [r for r in rows if str(r[1])[:10] == date_q]
        else:
            try:
                year = int(year_str)
                if period == 'Month':
                    month = list(cal_mod.month_name).index(month_name)
                    rows  = [r for r in rows if str(r[1])[:7] == f"{year:04d}-{month:02d}"]
                elif period == 'Year':
                    rows  = [r for r in rows if str(r[1])[:4] == f"{year:04d}"]
            except Exception:
                pass
        return rows

    def _reload_member_table(self, all_rows, table):
        for w in table.winfo_children(): w.destroy()
        rows = self._filter_member_rows(all_rows)
        if not rows:
            ctk.CTkLabel(table, text="No member transactions found.",
                         font=ctk.CTkFont(size=14), text_color="#546E7A").pack(pady=40)
            return

        from collections import OrderedDict
        grouped = OrderedDict()
        for r in rows:
            grouped.setdefault(r[6].strip(),[]).append(r)

        for member_name, member_rows in grouped.items():
            total_amount = sum(float(r[2]) for r in member_rows)
            txn_count    = len(member_rows)
            latest_dt    = member_rows[0][1]
            try:    latest_str = datetime.strptime(latest_dt,"%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y")
            except: latest_str = str(latest_dt)[:10]

            card = ctk.CTkFrame(table, fg_color="#FFFFFF",
                                corner_radius=8, border_width=1, border_color="#1565C0")
            card.pack(fill="x", pady=(0,6), padx=2)
            card.columnconfigure(0, weight=1)

            hdr = ctk.CTkFrame(card, fg_color="#FFFFFF", corner_radius=8, height=54, cursor="hand2")
            hdr.pack(fill="x", padx=1, pady=(1,0))
            hdr.pack_propagate(False)
            hdr.columnconfigure(2, weight=1)

            # Checkbox
            _mcb = ctk.BooleanVar(value=False)
            self._member_check_vars[member_name] = _mcb
            ctk.CTkCheckBox(hdr, text="", variable=_mcb,
                            width=22, checkbox_width=22, checkbox_height=22,
                            border_color="#1565C0", fg_color="#1565C0",
                            corner_radius=11
                            ).grid(row=0, column=0, padx=(10, 4), pady=8)

            av = ctk.CTkFrame(hdr, fg_color="#1565C0", corner_radius=20, width=36, height=36)
            av.grid(row=0,column=1,padx=(0,8),pady=8); av.pack_propagate(False)
            ctk.CTkLabel(av, text=member_name[0].upper(),
                         font=ctk.CTkFont(size=14,weight="bold"),
                         text_color="white").place(relx=0.5,rely=0.5,anchor="center")

            info_f = ctk.CTkFrame(hdr, fg_color="transparent")
            info_f.grid(row=0,column=2,sticky="w")
            name_row2 = ctk.CTkFrame(info_f, fg_color="transparent")
            name_row2.pack(anchor="w", fill="x")
            ctk.CTkLabel(name_row2, text=member_name,
                         font=ctk.CTkFont(size=13,weight="bold"),
                         text_color="#1A1A2E").pack(side="left")
            _mi = self._find_member_by_name(member_name)
            if _mi:
                ctk.CTkLabel(name_row2,
                             text=f"  🪪 {_mi['member_id']}",
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#7B1FA2").pack(side="left", padx=(6,0))
            else:
                _ti = db.get_teacher_by_name(member_name)
                if _ti:
                    ctk.CTkLabel(name_row2,
                                 text=f"  🏫 {_ti['teacher_id']}",
                                 font=ctk.CTkFont(size=10, weight="bold"),
                                 text_color="#E65100").pack(side="left", padx=(6,0))
            ctk.CTkLabel(info_f, text=f"{txn_count} transaction(s)  •  Latest: {latest_str}",
                         font=ctk.CTkFont(size=10), text_color="#546E7A").pack(anchor="w")

            action_f = ctk.CTkFrame(hdr, fg_color="transparent")
            action_f.grid(row=0,column=3,sticky="e",padx=(8,12))
            ctk.CTkLabel(action_f, text=f"₱{total_amount:.2f}",
                         font=ctk.CTkFont(size=16,weight="bold"),
                         text_color="#1565C0").pack(side="left",padx=(0,10))

            arrow_lbl = ctk.CTkLabel(action_f, text="▼",
                                     font=ctk.CTkFont(size=11,weight="bold"),text_color="#1565C0")
            arrow_lbl.pack(side="left",padx=(0,8))

            ctk.CTkButton(action_f, text="🖨", width=34, height=34,
                          fg_color="#2E7D32", hover_color="#1B5E20",
                          text_color="white", font=ctk.CTkFont(size=14), corner_radius=6,
                          command=lambda mr=member_rows, mn=member_name:
                              self._print_member_summary(mr, mn)
                          ).pack(side="left")

            txn_panel = ctk.CTkFrame(card, fg_color="#FFFFFF", corner_radius=0)
            expanded  = [False]

            def _toggle(panel=txn_panel, prows=member_rows, al=arrow_lbl, exp=expanded):
                exp[0] = not exp[0]
                if exp[0]:
                    al.configure(text="▲")
                    panel.pack(fill="x",padx=1,pady=(0,1))
                    for w in panel.winfo_children(): w.destroy()
                    sh = ctk.CTkFrame(panel,fg_color="#F5F5F5",height=30,corner_radius=0)
                    sh.pack(fill="x"); sh.pack_propagate(False)
                    sh.columnconfigure(0,weight=0); sh.columnconfigure(1,weight=0)
                    sh.columnconfigure(2,weight=0); sh.columnconfigure(3,weight=1)
                    for txt,col,w,anch in [("  TXN ID",0,110,"w"),("DATE & TIME",1,170,"w"),("METHOD",2,120,"w"),("AMOUNT",3,0,"e")]:
                        kw2={"font":ctk.CTkFont(size=10,weight="bold"),
                             "text_color":"#1A1A2E","fg_color":"transparent","anchor":anch}
                        if w==0:
                            ctk.CTkLabel(sh,text=txt,**kw2).grid(row=0,column=col,sticky="e",padx=(4,16),pady=5)
                        else:
                            ctk.CTkLabel(sh,text=txt,width=w,**kw2).grid(row=0,column=col,padx=(8,4),pady=5)
                    for j,r in enumerate(prows):
                        # ── Safe unpack for member transaction row (11 fields) ──
                        txn_id,dt,total,method,cash,change,cname,dept,buyer_type,item_names,item_count = _unpack_txn_row(r)
                        try:    ds = datetime.strptime(dt,"%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y  %I:%M %p")
                        except: ds = str(dt)[:16]
                        ibg = "#FFFFFF" if j%2==0 else "#F7F9FC"
                        ir  = ctk.CTkFrame(panel,fg_color=ibg,height=34,corner_radius=0)
                        ir.pack(fill="x"); ir.pack_propagate(False)
                        ir.columnconfigure(3,weight=1)
                        ctk.CTkLabel(ir,text=f"  #{txn_id}",width=110,anchor="w",
                                     font=ctk.CTkFont(size=11,weight="bold"),text_color="#1A1A2E"
                                     ).grid(row=0,column=0,padx=(8,4))
                        ctk.CTkLabel(ir,text=ds,width=170,anchor="w",
                                     font=ctk.CTkFont(size=11),text_color="#1A1A2E"
                                     ).grid(row=0,column=1,padx=(8,4))
                        ctk.CTkLabel(ir,text=method.replace("Credit / Utang","Credit/Utang"),width=120,anchor="w",
                                     font=ctk.CTkFont(size=11),text_color="#546E7A"
                                     ).grid(row=0,column=2,padx=(8,4))
                        ctk.CTkLabel(ir,text=f"₱{float(total):.2f}",anchor="e",
                                     font=ctk.CTkFont(size=12,weight="bold"),text_color="#1565C0"
                                     ).grid(row=0,column=3,sticky="e",padx=(4,16))
                    st_bar = ctk.CTkFrame(panel,fg_color="#FFFFFF",height=32,corner_radius=0)
                    st_bar.pack(fill="x"); st_bar.pack_propagate(False)
                    ctk.CTkLabel(st_bar,text=f"Total Bought: ₱{sum(float(r[2]) for r in prows):.2f}",
                                 font=ctk.CTkFont(size=12,weight="bold"),
                                 text_color="#1565C0").place(relx=0.97,rely=0.5,anchor="e")
                else:
                    al.configure(text="▼")
                    panel.pack_forget()

            for widget in [hdr, arrow_lbl, info_f]:
                widget.bind("<Button-1>", lambda e, t=_toggle: t())

    def _print_member_summary(self, rows, member_name=None):
        import os, platform, subprocess, tempfile
        title_name = member_name if member_name else "All COOP Members"

        def generate_pdf(rows, title_name):
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.units import cm
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
                from reportlab.lib.styles import ParagraphStyle
                from reportlab.lib.enums import TA_CENTER
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); tmp.close()
                doc = SimpleDocTemplate(tmp.name, pagesize=A4,
                                        topMargin=1.4*cm, bottomMargin=1.4*cm,
                                        leftMargin=1.6*cm, rightMargin=1.6*cm)
                BLUE = colors.HexColor("#1565C0"); GREY = colors.HexColor("#555555")
                story = []
                c_s = ParagraphStyle("c",fontSize=20,fontName="Helvetica-Bold",textColor=BLUE,alignment=TA_CENTER,spaceAfter=3)
                s_s = ParagraphStyle("s",fontSize=10,fontName="Helvetica",     textColor=GREY,alignment=TA_CENTER,spaceAfter=2)
                story.extend([Paragraph("CAFETERIA STORE",c_s),
                               Paragraph("Customer COOP Member Report",s_s),
                               Paragraph(title_name,s_s),
                               Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y  %I:%M %p')}",s_s),
                               Spacer(1,0.3*cm),HRFlowable(width="100%",thickness=2,color=BLUE),Spacer(1,0.3*cm)])
                if member_name:
                    t_data = [["TXN ID","DATE & TIME","METHOD","AMOUNT"]]
                    for r in rows:
                        txn_id,dt,total,method,cash,change,cname,dept,buyer_type,item_names,item_count = _unpack_txn_row(r)
                        try:    ds = datetime.strptime(dt,"%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y %I:%M %p")
                        except: ds = str(dt)[:16]
                        t_data.append([f"#{txn_id}",ds,method,f"₱{float(total):.2f}"])
                    story.append(Paragraph(f"Total Bought: ₱{sum(float(r[2]) for r in rows):.2f}",s_s))
                    story.append(Spacer(1,0.2*cm))
                    widths = [3*cm,7*cm,4*cm,3*cm]
                else:
                    member_id_map = {}
                    try:
                        for store in ["coop","cafestore","canteen"]:
                            for m in (db.get_all_loyalty_members(store=store) or []):
                                member_id_map[m.get("name","").strip().lower()] = m.get("member_id","")
                    except Exception:
                        pass
                    from collections import OrderedDict
                    grouped = OrderedDict()
                    for r in rows: grouped.setdefault(r[6],[]).append(r)
                    t_data = [["MBR ID","Member Name","Transactions","Total Bought"]]
                    for name,rs in grouped.items():
                        mid = member_id_map.get(name.strip().lower(), "-")
                        t_data.append([mid, name, str(len(rs)), f"₱{sum(float(x[2]) for x in rs):.2f}"])
                    widths = [3*cm,6*cm,3*cm,5*cm]
                t = Table(t_data, colWidths=widths, repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND",(0,0),(-1,0),BLUE),("TEXTCOLOR",(0,0),(-1,0),colors.white),
                    ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#F9F9F9"),colors.white]),
                    ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
                    ("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),
                    ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8)]))
                story.append(t)
                doc.build(story)
                return tmp.name
            except ImportError:
                return None

        pdf_path = generate_pdf(rows, title_name)
        if pdf_path:
            try:
                if platform.system()=="Windows": os.startfile(pdf_path)
                elif platform.system()=="Darwin": subprocess.run(["open",pdf_path])
                else: subprocess.run(["xdg-open",pdf_path])
                messagebox.showinfo("PDF Ready","Member report PDF opened!",parent=self)
            except Exception as ex:
                messagebox.showerror("Error",str(ex),parent=self)
        else:
            messagebox.showinfo("Install Required","pip install reportlab",parent=self)



    # ════════════════════════════════════════════════════════════
    #  LOYALTY CARD / COOP MEMBER REGISTRATION
    # ════════════════════════════════════════════════════════════
    def _show_loyalty_dashboard(self):
        import random, string, os, platform, subprocess, tempfile
        page = ctk.CTkFrame(self.content, fg_color="#F5F5F5", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(3, weight=1)  # row 3 = table (scrollable, expands)
        page.columnconfigure(0, weight=1)

        # ── Title + buttons ──
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 0))
        top.columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Coop Member Loyalty Cards",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="#1A1A2E").grid(row=0, column=0, sticky="w")
        btn_f = ctk.CTkFrame(top, fg_color="transparent")
        btn_f.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(btn_f, text="🖨  Print Members", width=145, height=36,
                      fg_color="#2E7D32", hover_color="#1B5E20",
                      font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
                      command=lambda: self._print_loyalty_list()
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_f, text="🗑  Delete Selected", width=150, height=36,
                      fg_color="#5D0000", hover_color="#8B0000",
                      font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
                      command=lambda: self._delete_selected_members()
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_f, text="＋  Register Member", width=160, height=36,
                      fg_color=BTN_BLUE, hover_color="#1976D2",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=8,
                      command=lambda: self._register_loyalty_member(page)
                      ).pack(side="left")

        # ── Search + Department filter bar ──
        fbar = ctk.CTkFrame(page, fg_color="#FFFFFF", corner_radius=8,
                            border_width=1, border_color="#1565C0")
        fbar.grid(row=1, column=0, sticky="ew", padx=24, pady=(10, 0))
        fbar.columnconfigure(1, weight=1)

        ctk.CTkLabel(fbar, text="🔍", font=ctk.CTkFont(size=14),
                     text_color="#546E7A").grid(row=0, column=0, padx=(12, 4), pady=8)
        self._loyalty_search_var = ctk.StringVar()
        self._loyalty_search_var.trace_add("write", lambda *_: self._reload_loyalty_table())
        ctk.CTkEntry(fbar, textvariable=self._loyalty_search_var,
                     placeholder_text="Search by name or member ID...",
                     border_width=0, fg_color="#FFFFFF", height=34,
                     font=ctk.CTkFont(size=13), text_color="black",
                     placeholder_text_color="#546E7A"
                     ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=8)

        ctk.CTkFrame(fbar, fg_color="#1565C0", width=2, height=28
                     ).grid(row=0, column=2, padx=8)

        ctk.CTkLabel(fbar, text="🏢 Dept:", font=ctk.CTkFont(size=12),
                     text_color="#546E7A").grid(row=0, column=3, padx=(8, 4))
        self._loyalty_dept_var = ctk.StringVar(value="All Depts")
        self._loyalty_dept_menu = ctk.CTkOptionMenu(
            fbar, variable=self._loyalty_dept_var,
            values=["All Depts"],
            width=150, height=30,
            fg_color="#FFFFFF", button_color=BTN_BLUE,
            button_hover_color="#1976D2",
            dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
            text_color="black", font=ctk.CTkFont(size=11),
            command=lambda _: self._reload_loyalty_table())
        self._loyalty_dept_menu.grid(row=0, column=4, padx=(0, 8), pady=8)

        ctk.CTkButton(fbar, text="✕", width=30, height=30,
                      fg_color=BTN_BLUE, hover_color="#1976D2",
                      font=ctk.CTkFont(size=11), corner_radius=6,
                      command=lambda: [self._loyalty_search_var.set(""),
                                       self._loyalty_dept_var.set("All Depts"),
                                       self._reload_loyalty_table()]
                      ).grid(row=0, column=5, padx=(0, 12), pady=8)

        # ── Column header with Select All ──
        col_hdr = ctk.CTkFrame(page, fg_color=COL_HDR, height=34, corner_radius=0)
        col_hdr.grid(row=2, column=0, sticky="ew", padx=24, pady=(6, 0))
        col_hdr.pack_propagate(False)
        col_hdr.columnconfigure(1, weight=1)
        # Select-All checkbox
        self._loyalty_select_all = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(col_hdr, text="", variable=self._loyalty_select_all,
                        width=22, checkbox_width=20, checkbox_height=20,
                        border_color="#1565C0", fg_color="#1565C0",
                        corner_radius=10,
                        command=self._toggle_select_all_members
                        ).place(x=8, rely=0.5, anchor="w")
        for txt, col, w in [("NAME / MEMBER ID", 1, 0), ("DEPARTMENT", 2, 140),
                            ("CARD BARCODE", 3, 180), ("ACTIONS", 4, 200)]:
            kw = {"font": ctk.CTkFont(size=11, weight="bold"),
                  "text_color": TEXT_GREY, "fg_color": "transparent", "anchor": "w"}
            if w == 0:
                ctk.CTkLabel(col_hdr, text=txt, **kw).grid(row=0, column=col, sticky="w", padx=(4, 4), pady=6)
            else:
                ctk.CTkLabel(col_hdr, text=txt, width=w, **kw).grid(row=0, column=col, padx=4, pady=6)

        # ── Table ──
        table = ctk.CTkScrollableFrame(page, fg_color="#F5F5F5",
                                       scrollbar_button_color=BTN_BLUE, corner_radius=0)
        table.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 12))
        table.columnconfigure(0, weight=1)
        self._loyalty_table      = table
        self._loyalty_checks     = {}
        self._loyalty_check_vars = {}
        # initialise filter vars so _reload_loyalty_table can access them
        if not hasattr(self, "_loyalty_search_var"):
            self._loyalty_search_var = ctk.StringVar()
        if not hasattr(self, "_loyalty_dept_var"):
            self._loyalty_dept_var = ctk.StringVar(value="All Depts")
        self._reload_loyalty_table()

    def _reload_loyalty_table(self):
        for w in self._loyalty_table.winfo_children():
            w.destroy()
        self._loyalty_check_vars = {}
        all_members = self._get_all_coop_members()

        # ── Update department dropdown with current unique depts ──
        if hasattr(self, "_loyalty_dept_menu") and all_members:
            depts = ["All Depts"] + sorted(set(m["department"] for m in all_members if m.get("department")))
            self._loyalty_dept_menu.configure(values=depts)

        # ── Apply filters ──
        search = getattr(self, "_loyalty_search_var", ctk.StringVar()).get().strip().lower()
        dept_f = getattr(self, "_loyalty_dept_var", ctk.StringVar(value="All Depts")).get().strip()

        members = all_members or []
        if search:
            members = [m for m in members
                       if search in m.get("name","").lower()
                       or search in m.get("member_id","").lower()
                       or search in m.get("card_barcode","").lower()]
        if dept_f and dept_f != "All Depts":
            members = [m for m in members if m.get("department","") == dept_f]

        if not members:
            ctk.CTkLabel(self._loyalty_table,
                         text="No members found." if (search or dept_f != "All Depts")
                              else "No members registered yet.",
                         font=ctk.CTkFont(size=14), text_color="#546E7A").pack(pady=40)
            return
        for i, m in enumerate(members):
            bg  = BG_ROW if i % 2 == 0 else BG_ROW_ALT
            row = ctk.CTkFrame(self._loyalty_table, fg_color=bg, corner_radius=0, height=60)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)
            row.columnconfigure(1, weight=1)

            # Checkbox col 0
            cb_var = ctk.BooleanVar(value=False)
            self._loyalty_check_vars[m["card_barcode"]] = cb_var
            ctk.CTkCheckBox(row, text="", variable=cb_var,
                            width=22, checkbox_width=20, checkbox_height=20,
                            border_color="#1565C0", fg_color="#1565C0",
                            corner_radius=10
                            ).grid(row=0, column=0, padx=(10, 6), pady=8)

            # Name col 1 (expands)
            nf = ctk.CTkFrame(row, fg_color="transparent")
            nf.grid(row=0, column=1, sticky="w", padx=(4, 4), pady=6)
            ctk.CTkLabel(nf, text=m["name"],
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#1A1A2E", anchor="w").pack(anchor="w")
            ctk.CTkLabel(nf, text=m["member_id"],
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#1565C0", anchor="w").pack(anchor="w")

            # Dept col 2
            ctk.CTkLabel(row, text=m["department"], width=140, anchor="center",
                         font=ctk.CTkFont(size=12), text_color="#546E7A"
                         ).grid(row=0, column=2, padx=4)

            # Card barcode col 3
            ctk.CTkLabel(row, text=m["card_barcode"], width=180, anchor="center",
                         font=ctk.CTkFont(size=11), text_color="#546E7A"
                         ).grid(row=0, column=3, padx=4)

            # Actions col 4
            act = ctk.CTkFrame(row, fg_color="transparent", width=200)
            act.grid(row=0, column=4, padx=(4, 14))
            ctk.CTkButton(act, text="✏ Edit", width=58, height=32,
                          fg_color="#1565C0", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          command=lambda mm=m: self._edit_loyalty_member(mm)
                          ).pack(side="left", padx=(0, 3))
            ctk.CTkButton(act, text="🖨 Card", width=64, height=32,
                          fg_color=GREEN, hover_color="#1B5E20",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          command=lambda mm=m: self._print_loyalty_card(mm)
                          ).pack(side="left", padx=(0, 3))
            ctk.CTkButton(act, text="Del", width=46, height=32,
                          fg_color="#5D0000", hover_color="#8B0000",
                          font=ctk.CTkFont(size=11, weight="bold"), corner_radius=6,
                          command=lambda mm=m: self._delete_loyalty_member(mm)
                          ).pack(side="left")

    def _register_loyalty_member(self, page):
        import random, string
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color="#111111")
        win.grab_set(); win.resizable(False, False)
        win.bind("<Escape>", lambda e: win.destroy())
        win.after(50, win.focus_force)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"444x446+{(sw-444)//2}+{(sh-446)//2}")
        ri = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=14)
        ri.pack(fill="both", expand=True, padx=2, pady=2)
        reg_hdr = ctk.CTkFrame(ri, fg_color="#1565C0", height=50, corner_radius=0)
        reg_hdr.pack(fill="x"); reg_hdr.pack_propagate(False)
        ctk.CTkLabel(reg_hdr, text="＋  Register Coop Member",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(reg_hdr, text="✕", width=32, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13), corner_radius=6,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        fields = {}
        # Auto-generate member_id and card_barcode
        auto_id       = "MBR-" + "".join(random.choices(string.digits, k=6))
        auto_barcode  = "CARD-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

        defs = [
            ("Full Name",     "name",         ""),
            ("Department",    "department",   ""),
            ("Member ID",     "member_id",    auto_id),
            ("Card Barcode",  "card_barcode", auto_barcode),
        ]
        for lbl, key, val in defs:
            row = ctk.CTkFrame(ri, fg_color="transparent")
            row.pack(fill="x", padx=28, pady=5)
            ctk.CTkLabel(row, text=lbl, width=120, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
            if key == "department":
                e = ctk.CTkComboBox(row, height=36,
                                    fg_color="#FFFFFF", border_width=1, border_color="#1565C0",
                                    text_color="black", font=ctk.CTkFont(size=13),
                                    dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                                    button_color=BTN_BLUE, button_hover_color="#1976D2",
                                    values=["CCS","COED","COAG","COM","Other"])
                e.set("")
            else:
                e = ctk.CTkEntry(row, height=36, fg_color="#BBDEFB",
                                 border_width=1, border_color="#1565C0",
                                 text_color="black", font=ctk.CTkFont(size=13))
                if val: e.insert(0, val)
            e.pack(side="left", fill="x", expand=True)
            fields[key] = e

        def regen_card():
            new_bc = "CARD-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
            fields["card_barcode"].delete(0, "end")
            fields["card_barcode"].insert(0, new_bc)

        ctk.CTkButton(ri, text="🔄  Regenerate Card Barcode", height=30,
                      fg_color="#7B1FA2", hover_color="#6A1B9A",
                      font=ctk.CTkFont(size=11), text_color="white", corner_radius=6,
                      command=regen_card).pack(padx=28, pady=(4, 0))

        def save():
            name       = fields["name"].get().strip()
            dept       = fields["department"].get().strip()
            member_id  = fields["member_id"].get().strip()
            card_bc    = fields["card_barcode"].get().strip()
            if not name or not dept or not member_id or not card_bc:
                messagebox.showerror("Error", "Please fill all fields.", parent=win)
                return
            db.add_loyalty_member(member_id, name, dept, card_bc, store="coop")
            messagebox.showinfo("Registered",
                                f"✓ Member registered!\n\n{name} | {dept}\nID: {member_id}",
                                parent=win)
            win.destroy()
            self._reload_loyalty_table()

        ctk.CTkButton(ri, text="💾  Save Member", height=44,
                      fg_color="#1976D2", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      corner_radius=8, command=save
                      ).pack(fill="x", padx=28, pady=(14, 0))

    def _delete_loyalty_member(self, member):
        if messagebox.askyesno("Delete Member",
                               f"Delete member '{member['name']}'?", parent=self):
            db.delete_loyalty_member(member["card_barcode"])
            self._reload_loyalty_table()

    def _print_loyalty_list(self):
        import os, platform, subprocess, tempfile
        members = []
        for store in ["coop", "cafestore", "canteen"]:
            try:
                ms = db.get_all_loyalty_members(store=store) or []
                members.extend(ms)
            except Exception:
                pass
        seen = set(); unique = []
        for m in members:
            mid = m.get("member_id","")
            if mid not in seen:
                seen.add(mid); unique.append(m)
        members = sorted(unique, key=lambda x: x.get("name",""))

        def generate_pdf(members):
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.units import cm
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
                from reportlab.lib.styles import ParagraphStyle
                from reportlab.lib.enums import TA_CENTER
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); tmp.close()
                doc = SimpleDocTemplate(tmp.name, pagesize=A4,
                                        topMargin=1.5*cm, bottomMargin=1.5*cm,
                                        leftMargin=2*cm, rightMargin=2*cm)
                BLUE = colors.HexColor("#1565C0"); GREY = colors.HexColor("#555555")
                story = []
                c_s = ParagraphStyle("c", fontSize=20, fontName="Helvetica-Bold",
                                     textColor=BLUE, alignment=TA_CENTER, spaceAfter=3)
                s_s = ParagraphStyle("s", fontSize=10, fontName="Helvetica",
                                     textColor=GREY, alignment=TA_CENTER, spaceAfter=2)
                story.extend([
                    Paragraph("CANTEEN", c_s),
                    Paragraph("Coop Member List", s_s),
                    Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y  %I:%M %p')}", s_s),
                    Spacer(1, 0.3*cm),
                    HRFlowable(width="100%", thickness=2, color=BLUE),
                    Spacer(1, 0.3*cm)
                ])
                t_data = [["Member ID", "Name", "Department", "Card ID"]]
                for m in members:
                    t_data.append([
                        m.get("member_id", "-"),
                        m.get("name", "-"),
                        m.get("department", "-"),
                        m.get("card_barcode", "-"),
                    ])
                if len(t_data) == 1:
                    t_data.append(["-", "No members found", "-", "-"])
                t = Table(t_data, colWidths=[3*cm, 6*cm, 4*cm, 3.5*cm], repeatRows=1)
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,0), BLUE),
                    ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                    ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                    ("FONTSIZE",   (0,0), (-1,-1), 10),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#F9F9F9"), colors.white]),
                    ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#DDDDDD")),
                    ("TOPPADDING", (0,0), (-1,-1), 6),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 6),
                    ("LEFTPADDING",  (0,0), (-1,-1), 10),
                    ("ALIGN", (0,0), (0,-1), "CENTER"),
                ]))
                story.extend([t, Spacer(1,0.4*cm),
                               HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DDDDDD")),
                               Paragraph(f"Total Members: {len(members)}",
                                         ParagraphStyle("f", fontSize=9, textColor=GREY, alignment=TA_CENTER))])
                doc.build(story)
                return tmp.name
            except ImportError:
                return None

        pdf_path = generate_pdf(members)
        if pdf_path:
            try:
                if platform.system() == "Windows": os.startfile(pdf_path)
                elif platform.system() == "Darwin": subprocess.run(["open", pdf_path])
                else: subprocess.run(["xdg-open", pdf_path])
                messagebox.showinfo("PDF Ready", "Member list PDF opened!\nPrint it from the PDF viewer.", parent=self)
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=self)
        else:
            messagebox.showinfo("Install Required", "pip install reportlab", parent=self)

    def _print_loyalty_card(self, member):
        """Show a loyalty card preview window — no external library needed.
           The user can take a photo with their phone or print via screenshot."""
        import tkinter as tk

        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color="#111111")   # black border
        win.resizable(False, False)
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        win.after(50, win.focus_force)
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        # Use scrollable inner so nothing is hidden
        W, H = 644, min(sh - 80, 900)
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        # White rounded inner
        ci = ctk.CTkFrame(win, fg_color="#F0F4F8", corner_radius=14)
        ci.pack(fill="both", expand=True, padx=2, pady=2)

        # ── Header ──
        hdr = ctk.CTkFrame(ci, fg_color="#1565C0", height=50, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🪪  Loyalty Card Preview",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="✕", width=32, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13), corner_radius=6,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        # Scrollable body
        scroll_body = ctk.CTkScrollableFrame(ci, fg_color="#F0F4F8",
                                              scrollbar_button_color="#1565C0")
        scroll_body.pack(fill="both", expand=True)

        # ── Card canvas (CR80 proportions: 3.375" x 2.125" → ~540 x 340 px) ──
        CW, CH = 580, 360
        card_frame = ctk.CTkFrame(scroll_body, fg_color="#E0E0E0", corner_radius=12)
        card_frame.pack(padx=20, pady=(16, 8))

        canvas = tk.Canvas(card_frame, width=CW, height=CH,
                           bg="#1565C0", highlightthickness=0)
        canvas.pack(padx=4, pady=4)

        # ── Card background gradient effect ──
        canvas.create_rectangle(0, 0, CW, CH, fill="#1565C0", outline="")
        # Dark stripe at bottom
        canvas.create_rectangle(0, CH-80, CW, CH, fill="#0D47A1", outline="")
        # Gold accent stripe
        canvas.create_rectangle(0, 60, CW, 65, fill="#F9A825", outline="")

        # ── Title ──
        canvas.create_text(CW//2, 20, text="ISUFST CAFETERIA",
                           fill="white", font=("Helvetica", 16, "bold"), anchor="center")
        canvas.create_text(CW//2, 45, text="COOP Member Loyalty Card",
                           fill="#BBDEFB", font=("Helvetica", 11), anchor="center")

        # ── Member info ──
        canvas.create_text(28, 90,
                           text=member["name"].upper(),
                           fill="#F9A825",
                           font=("Helvetica", 20, "bold"), anchor="w")
        canvas.create_text(28, 125,
                           text=f"Department: {member['department']}",
                           fill="white",
                           font=("Helvetica", 12), anchor="w")
        canvas.create_text(28, 148,
                           text=f"Member ID: {member['member_id']}",
                           fill="#F9A825",
                           font=("Helvetica", 12, "bold"), anchor="w")

        # ── Barcode — real Code128 B, properly sized ──
        bc_text  = member["card_barcode"]
        bc_mods  = _encode_code128b(bc_text)
        bc_total = sum(bc_mods)
        bc_avail = CW - 60
        bc_mpx   = min(1.5, bc_avail / max(bc_total, 1))   # cap at 1.5px — scannable
        bc_mpx   = max(0.8, bc_mpx)
        bc_by    = 178
        bc_bh    = 42
        bc_actual_w = sum(max(1, round(m * bc_mpx)) for m in bc_mods)
        # White background wider than barcode
        canvas.create_rectangle(18, bc_by - 4, 18 + bc_actual_w + 20,
                                  bc_by + bc_bh + 14,
                                  fill="#FFFFFF", outline="")
        bx_start = 26
        bx_cur   = bx_start
        for bi, bm in enumerate(bc_mods):
            bpx = max(1, round(bm * bc_mpx))
            if bi % 2 == 0:
                canvas.create_rectangle(bx_cur, bc_by, bx_cur + bpx,
                                         bc_by + bc_bh,
                                         fill="#000000", outline="")
            bx_cur += bpx
        canvas.create_text((bx_start + bx_cur) // 2, bc_by + bc_bh + 8,
                            text=bc_text, fill="#1A1A2E",
                            font=("Courier", 7, "bold"), anchor="center")

        # ── MEMBER chip placeholder ──
        canvas.create_rectangle(380, 85, 440, 130, fill="#F9A825", outline="#E65100", width=2)
        canvas.create_line(380, 100, 440, 100, fill="#E65100", width=1)
        canvas.create_line(380, 115, 440, 115, fill="#E65100", width=1)
        canvas.create_line(400, 85,  400, 130, fill="#E65100", width=1)
        canvas.create_line(420, 85,  420, 130, fill="#E65100", width=1)

        # ── Bottom text ──
        canvas.create_text(CW//2, CH-50,
                           text="Scan this card at the cafeteria POS",
                           fill="#BBDEFB", font=("Helvetica", 10), anchor="center")
        canvas.create_text(CW//2, CH-30,
                           text="Valid only at ISUFST Cafeteria",
                           fill="#90CAF9", font=("Helvetica", 9), anchor="center")

        # ── BACK OF CARD label ──
        ctk.CTkLabel(scroll_body, text="— BACK OF CARD —",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#546E7A").pack(pady=(8, 4))

        back_wrap = ctk.CTkFrame(scroll_body, fg_color="#E0E0E0", corner_radius=12)
        back_wrap.pack(padx=20, pady=(0, 6))
        back_cv = tk.Canvas(back_wrap, width=CW, height=CH,
                            bg="#0D47A1", highlightthickness=0)
        back_cv.pack(padx=4, pady=4)
        # background
        back_cv.create_rectangle(0, 0, CW, CH, fill="#0D47A1", outline="")
        # magnetic stripe
        back_cv.create_rectangle(0, 28, CW, 76, fill="#111111", outline="")
        back_cv.create_text(CW//2, 52, text="MAGNETIC STRIPE",
                            fill="#333333", font=("Helvetica", 8), anchor="center")
        # signature strip
        back_cv.create_rectangle(18, 90, CW-90, 128, fill="#FFFFFF",
                                  outline="#CCCCCC", width=1)
        back_cv.create_text(28, 109, text="Authorized Signature",
                            fill="#999999", font=("Helvetica", 7), anchor="w")
        # barcode on back — real Code128 B, properly sized
        bc2      = member["card_barcode"]
        bc2_mods = _encode_code128b(bc2)
        bc2_tot  = sum(bc2_mods)
        bc2_avail = CW - 60
        bc2_mpx  = min(1.5, bc2_avail / max(bc2_tot, 1))
        bc2_mpx  = max(0.8, bc2_mpx)
        bc2_by   = 138
        bc2_bh   = 38
        bc2_actual_w = sum(max(1, round(m * bc2_mpx)) for m in bc2_mods)
        back_cv.create_rectangle(18, bc2_by - 4, 18 + bc2_actual_w + 20,
                                  bc2_by + bc2_bh + 12,
                                  fill="#FFFFFF", outline="")
        bx2_cur = 26
        for bi2, bm2 in enumerate(bc2_mods):
            bpx2 = max(1, round(bm2 * bc2_mpx))
            if bi2 % 2 == 0:
                back_cv.create_rectangle(bx2_cur, bc2_by, bx2_cur + bpx2,
                                          bc2_by + bc2_bh,
                                          fill="#000000", outline="")
            bx2_cur += bpx2
        back_cv.create_text((26 + bx2_cur) // 2, bc2_by + bc2_bh + 6,
                            text=bc2, fill="#1A1A2E",
                            font=("Courier", 6, "bold"), anchor="center")
        # footer text
        back_cv.create_text(CW//2, CH-38,
                            text="Property of ISUFST Cafeteria.",
                            fill="#90CAF9", font=("Helvetica", 7), anchor="center")
        back_cv.create_text(CW//2, CH-22,
                            text="If found, please return to the nearest office.",
                            fill="#90CAF9", font=("Helvetica", 7), anchor="center")
        back_cv.create_text(CW-16, CH-7,
                            text=f"ID: {member['member_id']}",
                            fill="#F9A825", font=("Helvetica", 7, "bold"), anchor="e")

        # ── Info + instructions ──
        info = ctk.CTkFrame(scroll_body, fg_color="transparent")
        info.pack(padx=30, pady=(0, 6))
        ctk.CTkLabel(info,
                     text="📸  Take a photo of this card with your phone, or press Print Screen to capture.",
                     font=ctk.CTkFont(size=11), text_color="#546E7A",
                     wraplength=560, justify="center").pack()

        # ── Member details below card ──
        details = ctk.CTkFrame(scroll_body, fg_color="#FFFFFF", corner_radius=10,
                               border_width=1, border_color="#BBDEFB")
        details.pack(fill="x", padx=30, pady=(0, 6))
        for label, val in [
            ("Name",      member["name"]),
            ("Dept",      member["department"]),
            ("Member ID", member["member_id"]),
            ("Card Code", member["card_barcode"]),
        ]:
            row = ctk.CTkFrame(details, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=f"{label}:", width=90,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#1565C0", anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=val,
                         font=ctk.CTkFont(size=12),
                         text_color="#1A1A2E", anchor="w").pack(side="left")

        btn_row2 = ctk.CTkFrame(ci, fg_color="transparent")
        btn_row2.pack(fill="x", padx=12, pady=(4, 10))
        btn_row2.columnconfigure(0, weight=1)
        btn_row2.columnconfigure(1, weight=1)
        ctk.CTkButton(btn_row2, text="🖨  Print Card",
                      height=42, fg_color=GREEN, hover_color="#1B5E20",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="white", corner_radius=8,
                      command=lambda: self._print_loyalty_card_pdf(member)
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btn_row2, text="✕  Close",
                      height=42, fg_color="#5D0000", hover_color="#8B0000",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="white", corner_radius=8,
                      command=win.destroy
                      ).grid(row=0, column=1, sticky="ew")





    # ── Delete selected member groups ────────────────────────
    def _delete_selected_member_txns(self):
        if not hasattr(self, "_member_check_vars") or not self._member_check_vars:
            messagebox.showinfo("No Selection",
                                "Select member(s) using the checkbox first.", parent=self)
            return
        selected = [name for name, var in self._member_check_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("No Selection",
                                "Select member(s) using the checkbox first.", parent=self)
            return
        if not messagebox.askyesno("Delete Transactions",
                                   f"Permanently delete ALL transactions for "
                                   f"{len(selected)} member(s)?\n\n"
                                   f"Members: {', '.join(selected)}\n\n"
                                   f"⚠ This cannot be undone!",
                                   parent=self):
            return
        try:
            import sqlite3
            deleted_count = 0
            store = "canteen"

            for name in selected:
                # ── 1. Delete from Firestore ──
                try:
                    # Query by customer_name only (avoids composite index requirement)
                    results = db._query("transactions",
                                        filters=[["customer_name", "EQUAL", name]])
                    for r in results:
                        d      = db._parse_doc(r)
                        # Only delete if matching store
                        if d.get("store", "") != store:
                            continue
                        txn_id = d.get("txn_id", "")
                        # Delete transaction items first
                        items = db._query("transaction_items",
                                          filters=[["txn_id","EQUAL", txn_id]])
                        for it in items:
                            dn = it.get("document",{}).get("name","")
                            if dn: db._delete_doc("transaction_items", dn.split("/")[-1])
                        # Delete the transaction
                        dn = r.get("document",{}).get("name","")
                        if dn: db._delete_doc("transactions", dn.split("/")[-1])
                        deleted_count += 1
                except Exception as fe:
                    print(f"Firestore delete error for {name}: {fe}")

                # ── 2. Delete from local SQLite cache (by customer_name) ──
                try:
                    conn = sqlite3.connect(str(offline_db.DB_PATH))
                    cur  = conn.cursor()
                    # Get txn_ids for this customer from local cache
                    cur.execute(
                        "SELECT txn_id FROM transactions_local "
                        "WHERE customer_name = ? AND store = ?", (name, store))
                    local_ids = [row[0] for row in cur.fetchall()]
                    for tid in local_ids:
                        cur.execute("DELETE FROM transaction_items_local WHERE txn_id = ?", (tid,))
                    cur.execute(
                        "DELETE FROM transactions_local WHERE customer_name = ? AND store = ?",
                        (name, store))
                    conn.commit()
                    conn.close()
                    deleted_count += len(local_ids)
                except Exception as se:
                    print(f"SQLite delete error for {name}: {se}")

            messagebox.showinfo("Deleted",
                                f"✓ Transactions deleted for {len(selected)} member(s).",
                                parent=self)
            self._nav("member_txn")  # Stay on member transactions page and refresh
        except Exception as e:
            messagebox.showerror("Error", f"Delete failed:\n{e}", parent=self)

    # ── Loyalty select-all toggle ─────────────────────────────
    def _toggle_select_all_members(self):
        val = self._loyalty_select_all.get()
        for var in self._loyalty_check_vars.values():
            var.set(val)

    # ── Delete selected loyalty members ──────────────────────
    def _delete_selected_members(self):
        selected = [bc for bc, var in self._loyalty_check_vars.items() if var.get()]
        if not selected:
            messagebox.showinfo("No Selection", "Select member(s) using the checkbox first.", parent=self)
            return
        if not messagebox.askyesno("Delete Selected",
                                   f"Delete {len(selected)} selected member(s)?", parent=self):
            return
        for bc in selected:
            db.delete_loyalty_member(bc)
        self._reload_loyalty_table()

    # ── Edit loyalty member ───────────────────────────────────
    def _edit_loyalty_member(self, member):
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color="#111111")
        win.grab_set(); win.resizable(False, False)
        win.bind("<Escape>", lambda e: win.destroy())
        win.after(50, win.focus_force)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"444x336+{(sw-444)//2}+{(sh-336)//2}")
        emi = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=14)
        emi.pack(fill="both", expand=True, padx=2, pady=2)
        eh = ctk.CTkFrame(emi, fg_color="#1565C0", height=50, corner_radius=0)
        eh.pack(fill="x"); eh.pack_propagate(False)
        ctk.CTkLabel(eh, text="✏  Edit Member",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(eh, text="✕", width=32, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13), corner_radius=6,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        fields = {}
        defs = [("Full Name", "name", member["name"]),
                ("Department", "department", member["department"])]
        for lbl, key, val in defs:
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=28, pady=8)
            ctk.CTkLabel(row, text=lbl, width=120, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
            if key == "department":
                e = ctk.CTkComboBox(row, height=36, fg_color="#FFFFFF",
                                    border_width=1, border_color="#1565C0",
                                    text_color="black", font=ctk.CTkFont(size=13),
                                    dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                                    button_color=BTN_BLUE, button_hover_color="#1976D2",
                                    values=["CCS","COED","COAG","COM","Other"])
                e.set(val)
            else:
                e = ctk.CTkEntry(row, height=36, fg_color="#BBDEFB",
                                 border_width=1, border_color="#1565C0",
                                 text_color="black", font=ctk.CTkFont(size=13))
                e.insert(0, val)
            e.pack(side="left", fill="x", expand=True)
            fields[key] = e

        # ID and barcode (readonly display)
        for lbl, val in [("Member ID", member["member_id"]),
                          ("Card Barcode", member["card_barcode"])]:
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=28, pady=4)
            ctk.CTkLabel(row, text=lbl, width=120, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
            ctk.CTkLabel(row, text=val, anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#1565C0").pack(side="left")

        def save_edit():
            new_name = fields["name"].get().strip()
            new_dept = fields["department"].get().strip()
            if not new_name or not new_dept:
                messagebox.showerror("Error", "Name and Department cannot be empty.", parent=win)
                return
            db.add_loyalty_member(member["member_id"], new_name, new_dept,
                                   member["card_barcode"], store="coop")
            win.destroy()
            self._reload_loyalty_table()

        ctk.CTkButton(win, text="💾  Save Changes", height=42,
                      fg_color="#1976D2", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=14, weight="bold"),
                      corner_radius=8, command=save_edit
                      ).pack(fill="x", padx=28, pady=(12, 4))
        ctk.CTkButton(win, text="Cancel", height=34,
                      fg_color="#546E7A", hover_color="#37474F",
                      font=ctk.CTkFont(size=12), text_color="white",
                      corner_radius=8, command=win.destroy
                      ).pack(fill="x", padx=28)

    # ── Print loyalty card as PDF ─────────────────────────────
    def _print_loyalty_card_pdf(self, member):
        """Generate loyalty card PDF that matches the on-screen card preview."""
        import os, platform, subprocess, tempfile
        try:
            from reportlab.lib          import colors
            from reportlab.lib.units    import mm
            from reportlab.pdfgen       import canvas as pdf_canvas

            # CR80 card size
            W, H = 85.6*mm, 54*mm
            tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); tmp.close()

            c = pdf_canvas.Canvas(tmp.name, pagesize=(W, H))

            BLUE  = colors.HexColor("#1565C0")
            DBLUE = colors.HexColor("#0D47A1")
            GOLD  = colors.HexColor("#F9A825")

            # ── FRONT of card ──
            # Blue background
            c.setFillColor(BLUE)
            c.rect(0, 0, W, H, fill=1, stroke=0)

            # Dark stripe bottom
            c.setFillColor(DBLUE)
            c.rect(0, 0, W, 14*mm, fill=1, stroke=0)

            # Gold accent stripe
            c.setFillColor(GOLD)
            c.rect(0, H - 16*mm, W, 1.2*mm, fill=1, stroke=0)

            # Title
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(W/2, H - 6*mm, "ISUFST CAFETERIA")
            c.setFont("Helvetica", 6)
            c.drawCentredString(W/2, H - 10*mm, "COOP Member Loyalty Card")

            # Gold name
            c.setFillColor(GOLD)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(5*mm, H - 22*mm, member["name"].upper())

            # White dept + ID
            c.setFillColor(colors.white)
            c.setFont("Helvetica", 7)
            c.drawString(5*mm, H - 27*mm, f"Department: {member['department']}")
            c.setFillColor(GOLD)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(5*mm, H - 31*mm, f"Member ID: {member['member_id']}")

            # Chip placeholder (gold rectangle)
            c.setFillColor(GOLD)
            c.setStrokeColor(colors.HexColor("#E65100"))
            c.rect(W - 22*mm, H - 30*mm, 12*mm, 10*mm, fill=1, stroke=1)
            # chip lines
            c.setStrokeColor(colors.HexColor("#E65100"))
            c.setLineWidth(0.4)
            for yy in [H-24*mm, H-27*mm]:
                c.line(W-22*mm, yy, W-10*mm, yy)
            for xx in [W-18*mm, W-14*mm]:
                c.line(xx, H-30*mm, xx, H-20*mm)

            # Barcode — drawn on solid white background strip
            try:
                from reportlab.graphics.barcode import code128
                bc_obj = code128.Code128(member["card_barcode"],
                                         barWidth=1.0, barHeight=8*mm,
                                         humanReadable=False)
                bc_w = bc_obj.width
                bx   = (W - bc_w) / 2   # center on card
                by   = 5*mm
                # White background with adequate quiet zone
                c.setFillColor(colors.white)
                c.rect(bx - 3*mm, by - 0.5*mm, bc_w + 6*mm, 10.5*mm, fill=1, stroke=0)
                # Draw barcode bars (reset fill to black first!)
                c.setFillColor(colors.black)
                bc_obj.drawOn(c, bx, by)
                # Barcode text below bars
                c.setFillColor(colors.black)
                c.setFont("Courier-Bold", 5.5)
                c.drawCentredString(W/2, by - 1.5*mm, member["card_barcode"])
            except Exception as be:
                # Fallback: white strip with text only
                c.setFillColor(colors.white)
                c.rect(3*mm, 3*mm, W-6*mm, 10*mm, fill=1, stroke=0)
                c.setFillColor(colors.black)
                c.setFont("Courier-Bold", 7)
                c.drawCentredString(W/2, 6*mm, member["card_barcode"])

            # Bottom text at very bottom of card
            c.setFillColor(colors.HexColor("#BBDEFB"))
            c.setFont("Helvetica", 4.5)
            c.drawCentredString(W/2, 1.5*mm, "Scan at cafeteria POS  •  Valid only at ISUFST Cafeteria")

            c.showPage()

            # ── BACK of card ──
            c.setFillColor(DBLUE)
            c.rect(0, 0, W, H, fill=1, stroke=0)

            # Magnetic stripe
            c.setFillColor(colors.black)
            c.rect(0, H-14*mm, W, 10*mm, fill=1, stroke=0)

            # Signature strip
            c.setFillColor(colors.white)
            c.rect(5*mm, H-28*mm, W-25*mm, 8*mm, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#999999"))
            c.setFont("Helvetica", 5)
            c.drawString(7*mm, H-23*mm, "Authorized Signature")

            # Barcode on back — centered white strip
            try:
                from reportlab.graphics.barcode import code128 as code128b
                bc2   = code128b.Code128(member["card_barcode"],
                                          barWidth=1.0, barHeight=7*mm,
                                          humanReadable=False)
                bc2_w = bc2.width
                bx2   = (W - bc2_w) / 2
                by2   = 6.5*mm
                c.setFillColor(colors.white)
                c.rect(bx2-3*mm, by2-0.5*mm, bc2_w+6*mm, 10*mm, fill=1, stroke=0)
                # Reset fill to black before drawing barcode
                c.setFillColor(colors.black)
                bc2.drawOn(c, bx2, by2)
                c.setFont("Courier-Bold", 5)
                c.drawCentredString(W/2, by2 - 1.5*mm, member["card_barcode"])
            except Exception:
                c.setFillColor(colors.white)
                c.rect(3*mm, 5*mm, W-6*mm, 8*mm, fill=1, stroke=0)
                c.setFillColor(colors.black)
                c.setFont("Courier-Bold", 6)
                c.drawCentredString(W/2, 7*mm, member["card_barcode"])

            # Footer
            c.setFillColor(colors.HexColor("#90CAF9"))
            c.setFont("Helvetica", 5)
            c.drawCentredString(W/2, 3*mm,
                "Property of ISUFST Cafeteria. If found, please return.")
            c.setFillColor(GOLD)
            c.setFont("Helvetica-Bold", 5)
            c.drawRightString(W-3*mm, 1*mm, f"ID: {member['member_id']}")

            c.save()

            if platform.system() == "Windows":  os.startfile(tmp.name)
            elif platform.system() == "Darwin": subprocess.run(["open", tmp.name])
            else:                               subprocess.run(["xdg-open", tmp.name])
            messagebox.showinfo("Card Ready",
                                "Loyalty card PDF opened!\n"
                                "Front & Back included.\n"
                                "Print on CR80 card size.", parent=self)
        except ImportError:
            messagebox.showinfo("Install Required", "pip install reportlab", parent=self)
        except Exception as ex:
            messagebox.showerror("Error", str(ex), parent=self)

    # ── Inline barcode viewer popup (no external PDF) ─────────
    def _show_barcode_popup(self, barcode, name, price):
        """Show real Code128 barcode image inline — no external browser."""
        import tkinter as tk, io, tempfile, os
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color="#111111")
        win.grab_set(); win.resizable(False, False)
        win.bind("<Escape>", lambda e: win.destroy())
        win.after(50, win.focus_force)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"560x340+{(sw-560)//2}+{(sh-340)//2}")

        inner = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=14)
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        # Header
        hdr = ctk.CTkFrame(inner, fg_color="#7B1FA2", height=46, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🔢  Product Barcode",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="white").place(x=14, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="✕", width=30, height=30,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=12), corner_radius=6,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        # Product name + price
        ctk.CTkLabel(inner, text=name,
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#1A1A2E").pack(pady=(12, 0))
        ctk.CTkLabel(inner, text=f"₱{price:.2f}",
                     font=ctk.CTkFont(size=13), text_color="#1565C0").pack(pady=(2,0))

        # Barcode image frame
        bc_frame = ctk.CTkFrame(inner, fg_color="#FFFFFF", corner_radius=8,
                                border_width=1, border_color="#7B1FA2")
        bc_frame.pack(fill="x", padx=24, pady=(10, 6))

        # Try real barcode via reportlab → PIL image
        bc_img_label = ctk.CTkLabel(bc_frame, text="", fg_color="#FFFFFF")
        bc_img_label.pack(padx=8, pady=8)

        self._bc_photo_ref = None  # keep reference

        def render_barcode():
            import tkinter as tk
            # Try PIL-based barcode first (python-barcode library)
            img = _gen_barcode_pil(barcode, width=500, height=100)
            if img is not None:
                try:
                    photo = ctk.CTkImage(light_image=img, dark_image=img,
                                         size=(500, img.height))
                    self._bc_photo_ref = photo
                    bc_img_label.configure(image=photo, text="")
                    new_h = img.height
                    win.geometry(f"560x{360+new_h}+{(sw-560)//2}+{(sh-(360+new_h))//2}")
                    return
                except Exception:
                    pass
            # Fallback: real Code128 B on tkinter canvas
            bc_img_label.pack_forget()
            bc_frame_inner = ctk.CTkFrame(bc_frame, fg_color="#FFFFFF")
            bc_frame_inner.pack(fill="x")
            c = tk.Canvas(bc_frame_inner, bg="#FFFFFF",
                          width=500, height=100, highlightthickness=0)
            c.pack(padx=4, pady=4)
            _draw_code128_on_canvas(c, barcode, canvas_width=500,
                                     bar_height=72, y_offset=6)

        win.after(80, render_barcode)

        # Buttons
        btn_f = ctk.CTkFrame(inner, fg_color="transparent")
        btn_f.pack(fill="x", padx=24, pady=(4, 14))
        btn_f.columnconfigure(0, weight=1); btn_f.columnconfigure(1, weight=1)
        ctk.CTkButton(btn_f, text="🖨  Print Label",
                      height=40, fg_color="#2E7D32", hover_color="#1B5E20",
                      font=ctk.CTkFont(size=13, weight="bold"), text_color="white",
                      corner_radius=8,
                      command=lambda: self._print_barcode_label(barcode, name, price)
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(btn_f, text="✕  Close",
                      height=40, fg_color="#5D0000", hover_color="#8B0000",
                      font=ctk.CTkFont(size=13, weight="bold"), text_color="white",
                      corner_radius=8, command=win.destroy
                      ).grid(row=0, column=1, sticky="ew")


    # ── Generate Barcode dialog ───────────────────────────────
    def _generate_barcode_dialog(self):
        import random, string
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color="#111111")   # black border
        win.grab_set(); win.resizable(False, False)
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"488x780+{(sw-488)//2}+{(sh-780)//2}")
        # Rounded white inner
        gi = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=14)
        gi.pack(fill="both", expand=True, padx=2, pady=2)
        # Header
        gh = ctk.CTkFrame(gi, fg_color="#7B1FA2", height=50, corner_radius=0)
        gh.pack(fill="x"); gh.pack_propagate(False)
        ctk.CTkLabel(gh, text="＋  Add Item / Generate Barcode",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(gh, text="✕", width=32, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13), corner_radius=6,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        ctk.CTkLabel(gi, text="Fill in product details — a unique barcode will be generated.",
                     font=ctk.CTkFont(size=11), text_color="#546E7A",
                     wraplength=420).pack(padx=24, pady=(12, 4))

        fields = {}
        existing_cats = db.get_categories(store="canteen")

        def regen():
            new_bc = "CAF" + str(int(__import__("time").time()))[-6:] +                      "".join(random.choices(string.digits, k=2))
            fields["barcode"].configure(state="normal")
            fields["barcode"].delete(0, "end")
            fields["barcode"].insert(0, new_bc)
            fields["barcode"].configure(state="disabled")

        auto_bc = "CAF" + str(int(__import__("time").time()))[-6:] +                   "".join(random.choices(string.digits, k=2))

        defs = [("Product Name", "name",     ""),
                ("Barcode",      "barcode",   auto_bc),
                ("Category",     "category",  ""),
                ("Price (₱)",    "price",     ""),
                ("Stock Qty",    "stock",     "30")]

        for lbl, key, val in defs:
            row = ctk.CTkFrame(gi, fg_color="transparent")
            row.pack(fill="x", padx=24, pady=4)
            ctk.CTkLabel(row, text=lbl, width=120, anchor="w",
                         font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
            if key == "category":
                e = ctk.CTkComboBox(row, height=36, fg_color="#FFFFFF",
                                    border_width=1, border_color="#7B1FA2",
                                    text_color="black", font=ctk.CTkFont(size=13),
                                    dropdown_fg_color="#FFFFFF", dropdown_text_color="#1A1A2E",
                                    button_color="#7B1FA2", button_hover_color="#6A1B9A",
                                    values=existing_cats if existing_cats else
                                    ["Beverage","Food","Snacks","Supplies","Drinks","Other"])
                e.set("")
            elif key == "barcode":
                e = ctk.CTkEntry(row, height=36, fg_color="#F3E5F5",
                                 border_width=1, border_color="#7B1FA2",
                                 text_color="#7B1FA2", font=ctk.CTkFont(size=13,weight="bold"),
                                 state="disabled")
                e.configure(state="normal"); e.insert(0, val); e.configure(state="disabled")
            else:
                e = ctk.CTkEntry(row, height=36, fg_color="#BBDEFB",
                                 border_width=1, border_color="#1565C0",
                                 text_color="black", font=ctk.CTkFont(size=13))
                if val: e.insert(0, val)
            e.pack(side="left", fill="x", expand=True)
            fields[key] = e

            # ── Inject Markup % + Total Item Price after Price field ──
            if key == "price":
                mk_row2 = ctk.CTkFrame(gi, fg_color="transparent")
                mk_row2.pack(fill="x", padx=24, pady=4)
                ctk.CTkLabel(mk_row2, text="Markup %", width=120, anchor="w",
                             font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
                markup_cb2 = ctk.CTkComboBox(mk_row2, height=36, width=160,
                                             fg_color="#FFFFFF",
                                             border_width=1, border_color="#7B1FA2",
                                             text_color="black",
                                             font=ctk.CTkFont(size=13),
                                             dropdown_fg_color="#FFFFFF",
                                             dropdown_text_color="#1A1A2E",
                                             button_color="#7B1FA2",
                                             button_hover_color="#6A1B9A",
                                             values=["0%","5%","10%","15%","20%",
                                                     "25%","30%","40%","50%"])
                markup_cb2.set(f"{getattr(self, '_markup_pct', 10)}%")
                markup_cb2.pack(side="left")

                tp_row2 = ctk.CTkFrame(gi, fg_color="transparent")
                tp_row2.pack(fill="x", padx=24, pady=4)
                ctk.CTkLabel(tp_row2, text="Total Item Price", width=120, anchor="w",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color="#2E7D32").pack(side="left")
                total_price_e2 = ctk.CTkEntry(tp_row2, height=36, fg_color="#E8F5E9",
                                              border_width=2, border_color="#2E7D32",
                                              text_color="#2E7D32",
                                              font=ctk.CTkFont(size=13, weight="bold"))
                total_price_e2.pack(side="left", fill="x", expand=True)
                fields["total_price"] = total_price_e2

                def _recalc2(*_):
                    try:
                        base = float(fields["price"].get().strip())
                        pct_str = markup_cb2.get().replace("%","").strip()
                        pct  = float(pct_str) if pct_str else 0
                        self._markup_pct = int(pct)
                        total = base * (1 + pct / 100)
                        fields["total_price"].configure(state="normal")
                        fields["total_price"].delete(0, "end")
                        fields["total_price"].insert(0, f"{total:.2f}")
                    except Exception:
                        pass

                fields["price"].bind("<KeyRelease>", _recalc2)
                markup_cb2.configure(command=lambda v: _recalc2())



        # ── Barcode preview inside dialog ──
        prev_outer = ctk.CTkFrame(gi, fg_color="#F3E5F5", corner_radius=10,
                                  border_width=1, border_color="#7B1FA2")
        prev_outer.pack(fill="x", padx=24, pady=(6, 2))
        bc_canvas = ctk.CTkLabel(prev_outer, text="Barcode preview will appear here...",
                                  fg_color="#FFFFFF", text_color="#AAAAAA",
                                  font=ctk.CTkFont(size=11), width=420, height=90)
        bc_canvas.pack(padx=6, pady=6)

        self._gen_bc_photo = None

        def _draw_bc(*_):
            fields["barcode"].configure(state="normal")
            bv = fields["barcode"].get().strip()
            fields["barcode"].configure(state="disabled")
            if not bv: return
            # Try PIL barcode image first (python-barcode)
            img = _gen_barcode_pil(bv, width=400, height=80)
            if img is not None:
                try:
                    photo = ctk.CTkImage(light_image=img, dark_image=img,
                                         size=(400, img.height))
                    self._gen_bc_photo = photo
                    bc_canvas.configure(image=photo, text="",
                                        width=400, height=img.height)
                    return
                except Exception:
                    pass
            # Fallback: draw real Code128 B barcode on an embedded tk.Canvas
            import tkinter as tk
            bc_canvas.pack_forget()
            for w in prev_outer.winfo_children():
                w.destroy()
            c = tk.Canvas(prev_outer, bg="#FFFFFF",
                          width=410, height=88, highlightthickness=0)
            c.pack(padx=6, pady=6)
            _draw_code128_on_canvas(c, bv, canvas_width=400,
                                     bar_height=60, y_offset=6)
        win.after(120, _draw_bc)

        def regen_refresh():
            regen(); win.after(60, _draw_bc)

        ctk.CTkButton(gi, text="🔄  Regenerate Barcode", height=28,
                      fg_color="#7B1FA2", hover_color="#6A1B9A",
                      font=ctk.CTkFont(size=11), text_color="white", corner_radius=6,
                      command=regen_refresh).pack(padx=24, pady=(4, 0))

        _saved_bc = [None]

        # ── Image upload for non-barcode items ──
        img_path_ref2 = {"path": None}
        img_row2 = ctk.CTkFrame(gi, fg_color="transparent")
        img_row2.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(img_row2, text="Product Photo", width=120, anchor="w",
                     font=ctk.CTkFont(size=12), text_color="#546E7A").pack(side="left")
        img_status2 = ctk.CTkLabel(img_row2, text="No image selected",
                                   font=ctk.CTkFont(size=11), text_color="#90A4AE")
        img_status2.pack(side="left", fill="x", expand=True)

        def _pick_image2():
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                parent=win, title="Select Product Image",
                filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp")])
            if path:
                img_path_ref2["path"] = path
                fname = os.path.basename(path)
                short = fname if len(fname) <= 22 else fname[:19] + "..."
                img_status2.configure(text=f"✅ {short}", text_color="#2E7D32")

        ctk.CTkButton(img_row2, text="📷 Browse",
                      width=90, height=30,
                      fg_color="#7B1FA2", hover_color="#6A1B9A",
                      font=ctk.CTkFont(size=11), text_color="white",
                      command=_pick_image2).pack(side="right")

        upload_lbl2 = ctk.CTkLabel(gi, text="",
                                    font=ctk.CTkFont(size=11),
                                    text_color="#7B1FA2")
        upload_lbl2.pack(pady=(0,2))

        def _do_save():
            try:
                fields["barcode"].configure(state="normal")
                bc  = fields["barcode"].get().strip()
                fields["barcode"].configure(state="disabled")
                nm  = fields["name"].get().strip()
                cat = fields["category"].get().strip()
                pr  = float(fields["total_price"].get().strip() or fields["price"].get().strip())
                st  = int(fields["stock"].get().strip())
                if not bc or not nm or not cat:
                    raise ValueError("empty")
                db.add_product(bc, nm, cat, pr, st, store="canteen")
                _saved_bc[0] = (bc, nm, pr)
                print_btn.configure(state="normal",
                                    fg_color="#2E7D32", hover_color="#1B5E20",
                                    text="🖨  Print Barcode")
                save_btn.configure(fg_color="#546E7A", hover_color="#37474F",
                                   text="✓  Saved!")
                self._reload_stock()
                # Upload image if selected
                if img_path_ref2["path"] and db.has_internet():
                    upload_lbl2.configure(text="⏳ Uploading image...", text_color="#7B1FA2")
                    win.update()
                    def _do_upload2():
                        url = self._upload_image_to_storage(img_path_ref2["path"], bc)
                        if url:
                            # ── Save image_url to SQLite only — Firestore updated on Backup ──
                            try:
                                db.update_product(bc, nm, cat, pr, st,
                                                  store="canteen", image_url=url)
                            except Exception as e:
                                print(f"SQLite image_url save error: {e}")
                            self.after(0, lambda: (
                                upload_lbl2.configure(text="✅ Image saved locally!", text_color="#2E7D32")
                                if upload_lbl2.winfo_exists() else None
                            ) if hasattr(upload_lbl2, 'winfo_exists') else None)
                        else:
                            self.after(0, lambda: (
                                upload_lbl2.configure(text="⚠️ Image upload failed", text_color="#C62828")
                                if upload_lbl2.winfo_exists() else None
                            ) if hasattr(upload_lbl2, 'winfo_exists') else None)
                    threading.Thread(target=_do_upload2, daemon=True).start()
            except Exception as ex:
                messagebox.showerror("Error", "Fill all fields correctly.", parent=win)

        def _do_print():
            if _saved_bc[0]:
                bc, nm, pr = _saved_bc[0]
                self._print_barcode_label(bc, nm, pr)

        btn_r = ctk.CTkFrame(gi, fg_color="transparent")
        btn_r.pack(fill="x", padx=24, pady=(8, 12))
        btn_r.columnconfigure(0, weight=1)
        btn_r.columnconfigure(1, weight=1)

        save_btn = ctk.CTkButton(btn_r, text="💾  Save Product",
                      height=44, fg_color="#1565C0", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="white", corner_radius=8, command=_do_save)
        save_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0,4))
        win.bind("<Return>", lambda e: _do_save())
        win.after(100, lambda: fields["name"].focus_set())

        print_btn = ctk.CTkButton(btn_r, text="🖨  Print Barcode",
                      height=44, fg_color="#BBBBBB", hover_color="#BBBBBB",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="white", corner_radius=8,
                      state="disabled", command=_do_print)
        print_btn.grid(row=0, column=1, sticky="ew", pady=(0,4))

        ctk.CTkButton(gi, text="✕  Close",
                      height=38, fg_color="#5D0000", hover_color="#8B0000",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      text_color="white", corner_radius=8, command=win.destroy
                      ).pack(fill="x", padx=24, pady=(0, 12))

    # ── Print barcode label PDF ───────────────────────────────
    def _print_barcode_label(self, barcode, name, price):
        import os, platform, subprocess, tempfile
        try:
            from reportlab.lib.pagesizes import landscape
            from reportlab.lib          import colors
            from reportlab.lib.units    import mm
            from reportlab.platypus     import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles   import ParagraphStyle
            from reportlab.lib.enums    import TA_CENTER
            from reportlab.graphics.barcode import code128

            # Label size: 50mm x 30mm
            W, H = 50*mm, 30*mm
            tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); tmp.close()
            doc  = SimpleDocTemplate(tmp.name, pagesize=(W, H),
                                     topMargin=2*mm, bottomMargin=2*mm,
                                     leftMargin=2*mm, rightMargin=2*mm)
            story = []
            n_s = ParagraphStyle("n", fontSize=8, fontName="Helvetica-Bold",
                                  alignment=TA_CENTER, spaceAfter=1)
            story.append(Paragraph(name, n_s))
            story.append(Spacer(1, 1*mm))
            try:
                bc_obj = code128.Code128(barcode, barWidth=0.6, barHeight=8*mm)
                story.append(bc_obj)
            except Exception:
                pass
            story.append(Paragraph(barcode,
                         ParagraphStyle("bc", fontSize=6, fontName="Courier",
                                        alignment=TA_CENTER)))
            doc.build(story)
            if platform.system() == "Windows":  os.startfile(tmp.name)
            elif platform.system() == "Darwin": subprocess.run(["open", tmp.name])
            else:                               subprocess.run(["xdg-open", tmp.name])
            messagebox.showinfo("Barcode Ready",
                                f"Barcode label PDF opened!\n{name}\n{barcode}",
                                parent=self)
        except ImportError:
            messagebox.showinfo("Install Required", "pip install reportlab", parent=self)
        except Exception as ex:
            messagebox.showerror("Error", str(ex), parent=self)

    # ════════════════════════════════════════════════════════════
    #  MOBILE ORDERS — from StockFlow Hub app
    # ════════════════════════════════════════════════════════════
    def _show_mobile_orders(self):
        page = ctk.CTkFrame(self.content, fg_color="#F5F5F5", corner_radius=0)
        page.grid(row=0, column=0, sticky="nsew")
        page.rowconfigure(2, weight=1)
        page.columnconfigure(0, weight=1)

        # ── Header ──
        hdr = ctk.CTkFrame(page, fg_color="#FFFFFF", height=60, corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="📱  Mobile Orders",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#1A1A2E").pack(side="left", padx=20, pady=15)
        ctk.CTkButton(hdr, text="🔄 Refresh", width=100, height=34,
                      fg_color="#1565C0", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=12),
                      command=self._show_mobile_orders
                      ).pack(side="right", padx=20, pady=13)

        # ── Filter bar ──
        filter_frame = ctk.CTkFrame(page, fg_color="#FFFFFF", height=54, corner_radius=0)
        filter_frame.grid(row=1, column=0, sticky="ew", pady=(1,0))
        filter_frame.pack_propagate(False)

        self._order_status_filter = ctk.StringVar(value="Pending")
        self._order_date_filter   = ctk.StringVar(value="")

        left_f = ctk.CTkFrame(filter_frame, fg_color="transparent")
        left_f.pack(side="left", padx=8, pady=8)

        btn_refs   = {}
        count_lbls = {}  # badge labels per tab

        tab_map = [
            ("Pending",  "Pending Orders"),
            ("Approved", "Preparing Items"),
            ("History",  "History"),
        ]

        def _switch(key, btns):
            self._order_status_filter.set(key)
            for k, b in btns.items():
                b.configure(
                    fg_color="#1565C0" if k==key else "#E0E0E0",
                    text_color="white" if k==key else "#1A1A2E")
            self._reload_mobile_orders(table)

        for key, label in tab_map:
            clr  = "#1565C0" if key=="Pending" else "#E0E0E0"
            tclr = "white"   if key=="Pending" else "#1A1A2E"
            frame_btn = ctk.CTkFrame(left_f, fg_color="transparent")
            frame_btn.pack(side="left", padx=(0,6))
            b = ctk.CTkButton(frame_btn, text=label, width=130, height=34,
                              fg_color=clr, text_color=tclr,
                              hover_color="#0D47A1",
                              font=ctk.CTkFont(size=12))
            b.pack()
            btn_refs[key] = b
            # Badge only for Pending and Approved (not History)
            if key != "History":
                count_lbl = ctk.CTkLabel(frame_btn, text="",
                                         font=ctk.CTkFont(size=9, weight="bold"),
                                         fg_color="#E53935", text_color="white",
                                         corner_radius=8, width=0)
                count_lbl.place(relx=1.0, rely=0.0, anchor="ne", x=-2, y=-2)
                count_lbls[key] = count_lbl

        for key in btn_refs:
            btn_refs[key].configure(command=lambda k=key: _switch(k, btn_refs))

        # Date picker button (same style as sales dash)
        right_f = ctk.CTkFrame(filter_frame, fg_color="transparent")
        right_f.pack(side="right", padx=12, pady=8)
        date_lbl = ctk.CTkLabel(right_f, text="📅 All Dates",
                                font=ctk.CTkFont(size=12),
                                text_color="#1565C0", cursor="hand2")
        date_lbl.pack(side="left", padx=(0,8))
        date_lbl.bind("<Button-1>", lambda e: self._open_orders_calendar(table, date_lbl))
        ctk.CTkButton(right_f, text="Clear", width=60, height=34,
                      fg_color="#757575", hover_color="#546E7A",
                      font=ctk.CTkFont(size=12),
                      command=lambda: [
                          self._order_date_filter.set(""),
                          date_lbl.configure(text="📅 All Dates"),
                          self._reload_mobile_orders(table)
                      ]).pack(side="left")

        # ── Orders table ──
        table = ctk.CTkScrollableFrame(page, fg_color="#F0F4F8",
                                       scrollbar_button_color="#1565C0",
                                       corner_radius=0)
        table.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
        table.columnconfigure(0, weight=1)

        # Load counts for badge
        self._load_order_counts(count_lbls)
        self._reload_mobile_orders(table)

    def _load_order_counts(self, count_lbls):
        """Load pending/approved counts and show badges — filtered by store."""
        def _fetch():
            try:
                for key in ["Pending", "Approved"]:
                    results = db._query("mobile_orders",
                                        filters=[["status","EQUAL", key],
                                                 ["store", "EQUAL", "canteen"]])
                    count = len(list(results))
                    lbl   = count_lbls.get(key)
                    if lbl:
                        self.after(0, lambda c=count, l=lbl: l.configure(
                            text=f" {c} " if c > 0 else "",
                            width=20 if c > 0 else 0
                        ))
            except Exception:
                pass
        threading.Thread(target=_fetch, daemon=True).start()

    def _open_orders_calendar(self, table, date_lbl):
        """Calendar picker — same style as sales dash."""
        import calendar as cal_mod
        win = ctk.CTkToplevel(self)
        win.title("Pick a Date")
        win.configure(fg_color="#F5F5F5")
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"360x360+{(sw-360)//2}+{(sh-360)//2}")

        now   = datetime.now()
        state = {"year": now.year, "month": now.month}

        def build(year, month):
            for w in win.winfo_children(): w.destroy()
            hdr = ctk.CTkFrame(win, fg_color="#1565C0", height=52, corner_radius=0)
            hdr.pack(fill="x"); hdr.pack_propagate(False)
            ctk.CTkButton(hdr, text="◀", width=34, height=30,
                          fg_color="transparent", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(-1)).place(x=8, rely=0.5, anchor="w")
            ctk.CTkLabel(hdr, text=f"{cal_mod.month_name[month]} {year}",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color="white").place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkButton(hdr, text="▶", width=34, height=30,
                          fg_color="transparent", hover_color="#0D47A1",
                          font=ctk.CTkFont(size=14), text_color="white",
                          command=lambda: go(1)).place(relx=1.0, x=-8, rely=0.5, anchor="e")
            # Month/Year dropdowns
            pick_row = ctk.CTkFrame(win, fg_color="transparent")
            pick_row.pack(fill="x", padx=12, pady=(10,6))
            month_names = list(cal_mod.month_name)[1:]
            month_var   = ctk.StringVar(value=cal_mod.month_name[month])
            year_values = [str(y) for y in range(now.year-5, now.year+6)]
            year_var    = ctk.StringVar(value=str(year))
            def on_month(m): state["month"]=month_names.index(m)+1; build(state["year"],state["month"])
            def on_year(y):  state["year"]=int(y); build(state["year"],state["month"])
            ctk.CTkOptionMenu(pick_row, variable=month_var, values=month_names,
                              width=170, height=34,
                              fg_color="#FFFFFF", button_color="#1565C0",
                              button_hover_color="#0D47A1",
                              dropdown_fg_color="#FFFFFF",
                              dropdown_text_color="#1A1A2E",
                              text_color="#1A1A2E",
                              font=ctk.CTkFont(size=12),
                              command=on_month).pack(side="left", padx=(0,8))
            ctk.CTkOptionMenu(pick_row, variable=year_var, values=year_values,
                              width=110, height=34,
                              fg_color="#FFFFFF", button_color="#1565C0",
                              button_hover_color="#0D47A1",
                              dropdown_fg_color="#FFFFFF",
                              dropdown_text_color="#1A1A2E",
                              text_color="#1A1A2E",
                              font=ctk.CTkFont(size=12),
                              command=on_year).pack(side="left")
            # Day headers
            dh = ctk.CTkFrame(win, fg_color="transparent")
            dh.pack(fill="x", padx=10, pady=(4,0))
            for d in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
                ctk.CTkLabel(dh, text=d, width=48,
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color="#546E7A").pack(side="left")
            # Day buttons
            gf = ctk.CTkFrame(win, fg_color="transparent")
            gf.pack(fill="x", padx=10, pady=4)
            for week in cal_mod.monthcalendar(year, month):
                rf = ctk.CTkFrame(gf, fg_color="transparent")
                rf.pack(fill="x", pady=2)
                for day in week:
                    if day == 0:
                        ctk.CTkLabel(rf, text="", width=48).pack(side="left")
                    else:
                        is_today = (day==now.day and month==now.month and year==now.year)
                        ctk.CTkButton(rf, text=str(day), width=42, height=30,
                                      fg_color="#1976D2" if is_today else BTN_BLUE,
                                      hover_color="#0D47A1",
                                      font=ctk.CTkFont(size=11), corner_radius=4,
                                      command=lambda d=day: pick(d)
                                      ).pack(side="left", padx=2)

        def go(delta):
            m = state["month"]+delta; y = state["year"]
            if m>12: m=1;  y+=1
            if m<1:  m=12; y-=1
            state["year"]=y; state["month"]=m; build(y,m)

        def pick(day):
            chosen = f"{state['year']:04d}-{state['month']:02d}-{day:02d}"
            self._order_date_filter.set(chosen)
            date_lbl.configure(text=f"📅 {state['month']:02d}/{day:02d}/{state['year']}")
            win.destroy()
            self._reload_mobile_orders(table)

        build(state["year"], state["month"])

    def _reload_mobile_orders(self, table):
        for w in table.winfo_children():
            w.destroy()
        loading = ctk.CTkLabel(table, text="⏳  Loading orders...",
                               font=ctk.CTkFont(size=14), text_color="#546E7A")
        loading.pack(pady=40)

        status_filter = getattr(self, "_order_status_filter",
                                ctk.StringVar(value="Pending")).get()
        date_filter   = getattr(self, "_order_date_filter",
                                ctk.StringVar(value="")).get().strip()

        def _fetch():
            try:
                if status_filter == "History":
                    res1 = list(db._query("mobile_orders",
                                          filters=[["status","EQUAL","Completed"],
                                                   ["store","EQUAL","canteen"]]))
                    res2 = list(db._query("mobile_orders",
                                          filters=[["status","EQUAL","Cancelled"],
                                                   ["store","EQUAL","canteen"]]))
                    results = res1 + res2
                else:
                    results = list(db._query("mobile_orders",
                                             filters=[["status","EQUAL",status_filter],
                                                      ["store","EQUAL","canteen"]]))
                orders = []
                for r in results:
                    d = db._parse_doc(r)
                    d["doc_id"] = r.get("document",{}).get("name","").split("/")[-1]
                    if date_filter and not str(d.get("datetime","")).startswith(date_filter):
                        continue
                    # If order has items from both stores, filter to show only this store's items
                    order_store = str(d.get("store",""))
                    if order_store == "both":
                        orig_items = d.get("items") or []
                        if isinstance(orig_items, list):
                            store_items = [i for i in orig_items
                                          if isinstance(i, dict) and
                                          str(i.get("store","")) == "canteen"]
                            if store_items:
                                d["items"] = store_items
                                d["total"] = sum(float(i.get("subtotal",0) or 0)
                                                 for i in store_items)
                                orders.append(d)
                        continue
                    orders.append(d)
                orders.sort(key=lambda x: str(x.get("datetime","")), reverse=True)
                self.after(0, lambda o=orders: self._render_mobile_orders(table, o))
            except Exception as e:
                self.after(0, lambda: loading.configure(text=f"❌ Error: {e}"))

        threading.Thread(target=_fetch, daemon=True).start()

    def _render_mobile_orders(self, table, orders):
        # Guard: table may have been destroyed if user navigated away
        try:
            table.winfo_children()
        except Exception:
            return
        for w in table.winfo_children():
            w.destroy()

        status_filter = getattr(self, "_order_status_filter",
                                ctk.StringVar(value="Pending")).get()

        tab_labels = {
            "Pending":  "pending orders",
            "Approved": "items being prepared",
            "History":  "history",
        }

        if not orders:
            ctk.CTkLabel(table,
                         text=f"No {tab_labels.get(status_filter,'orders')}.",
                         font=ctk.CTkFont(size=14),
                         text_color="#546E7A").pack(pady=40)
            return

        STATUS_COLORS = {
            "Pending":   "#F57F17",
            "Approved":  "#1565C0",
            "Completed": "#2E7D32",
            "Cancelled": "#C62828",
        }

        for order in orders:
            card = ctk.CTkFrame(table, fg_color="#FFFFFF", corner_radius=10,
                                border_width=1, border_color="#E0E0E0")
            card.pack(fill="x", pady=(0,10), padx=2)

            order_id  = str(order.get("order_id") or "—")
            member_id = str(order.get("member_id") or "—")
            member    = str(order.get("member_name") or "Unknown")
            dept      = str(order.get("department") or "—")
            status    = str(order.get("status") or "Pending")
            total     = 0.0
            try: total = float(order.get("total") or 0)
            except: pass
            date      = str(order.get("date_display") or "")
            datetime_ = str(order.get("datetime") or "")
            doc_id    = str(order.get("doc_id") or "")
            items     = order.get("items") or []
            if not isinstance(items, list): items = []
            c_note    = str(order.get("cashier_note") or "")

            display_status = "Preparing Items" if status=="Approved" else status

            # ── Card header ──
            ch = ctk.CTkFrame(card, fg_color="#F8F9FA", corner_radius=8)
            ch.pack(fill="x", padx=10, pady=(10,0))
            ctk.CTkLabel(ch, text=f"🧾  {order_id}",
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#1A1A2E").pack(side="left", padx=12, pady=8)
            s_color = STATUS_COLORS.get(status,"#888")
            ctk.CTkLabel(ch, text=f"  {display_status}  ",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         fg_color=s_color, text_color="white",
                         corner_radius=6).pack(side="right", padx=12, pady=8)

            # ── Member info ──
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(fill="x", padx=14, pady=(8,0))
            info.columnconfigure(1, weight=1)

            def _row(parent, label, value, r):
                ctk.CTkLabel(parent, text=label,
                             font=ctk.CTkFont(size=13, weight="bold"),
                             text_color="#546E7A", width=120, anchor="w"
                             ).grid(row=r, column=0, sticky="w", pady=2)
                ctk.CTkLabel(parent, text=str(value),
                             font=ctk.CTkFont(size=13, weight="bold"),
                             text_color="#1A1A2E", anchor="w"
                             ).grid(row=r, column=1, sticky="w", pady=1)

            contact = str(order.get("phone","") or order.get("contact","") or "—")
            try:
                dt_display = datetime.strptime(datetime_[:19], "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y %I:%M %p") if datetime_ else date
            except Exception:
                dt_display = datetime_[:16] if datetime_ else date
            _row(info, "Member ID:",  member_id, 0)
            _row(info, "Name:",       member,    1)
            _row(info, "Department:", dept,      2)
            _row(info, "📞 Contact:", contact,   3)
            _row(info, "🕐 Order Date:", dt_display, 4)

            # ── Divider ──
            ctk.CTkFrame(card, fg_color="#E0E0E0", height=1
                         ).pack(fill="x", padx=14, pady=(10,6))

            # ── Items table ──
            if items:
                ih = ctk.CTkFrame(card, fg_color="#EEF2FF", corner_radius=4)
                ih.pack(fill="x", padx=14, pady=(0,0))
                ih.columnconfigure(0, weight=1)
                for col, txt, wd in [(0,"ITEM",0),(1,"QTY",60),(2,"PRICE",80),(3,"SUBTOTAL",90)]:
                    ctk.CTkLabel(ih, text=txt,
                                 font=ctk.CTkFont(size=10, weight="bold"),
                                 text_color="#546E7A", width=wd if wd else 0,
                                 anchor="w" if col==0 else "e"
                                 ).grid(row=0, column=col,
                                        sticky="w" if col==0 else "e",
                                        padx=(10,4) if col==0 else (0,10), pady=4)

                for i, item in enumerate(items):
                    if not isinstance(item, dict): continue
                    bg = "#FFFFFF" if i%2==0 else "#FAFAFA"
                    row_f = ctk.CTkFrame(card, fg_color=bg, corner_radius=0)
                    row_f.pack(fill="x", padx=14)
                    row_f.columnconfigure(0, weight=1)

                    iname  = str(item.get("name","") or item.get("product_name","") or "")
                    # qty — Firestore may return int or float or string
                    _qty = item.get("quantity", item.get("qty", 1))
                    try: iqty = int(float(str(_qty))) if _qty is not None else 1
                    except: iqty = 1
                    # price
                    _price = item.get("price", 0)
                    try: iprice = float(str(_price)) if _price is not None else 0.0
                    except: iprice = 0.0
                    inote  = str(item.get("note","") or "")
                    # subtotal
                    _sub = item.get("subtotal", None)
                    try: isub = float(str(_sub)) if _sub is not None else iprice * iqty
                    except: isub = iprice * iqty

                    name_col = ctk.CTkFrame(row_f, fg_color="transparent")
                    name_col.grid(row=0, column=0, sticky="w", padx=(10,4), pady=(4,0))
                    ctk.CTkLabel(name_col, text=iname,
                                 font=ctk.CTkFont(size=14, weight="bold"),
                                 text_color="#1A1A2E").pack(anchor="w")
                    if inote and inote.lower() != "null":
                        note_box = ctk.CTkFrame(row_f, fg_color="#E3F2FD",
                                                corner_radius=6,
                                                border_width=1,
                                                border_color="#1565C0")
                        note_box.grid(row=1, column=0, columnspan=4,
                                      sticky="ew", padx=10, pady=(2,6))
                        ctk.CTkLabel(note_box,
                                     text=f"📝  Note:  {inote}",
                                     font=ctk.CTkFont(size=13, weight="bold"),
                                     text_color="#000000",
                                     anchor="w"
                                     ).pack(anchor="w", padx=10, pady=6)

                    ctk.CTkLabel(row_f, text=str(iqty),
                                 font=ctk.CTkFont(size=12),
                                 text_color="#1A1A2E", width=60, anchor="e"
                                 ).grid(row=0, column=1, sticky="e", padx=(0,4), pady=4)
                    ctk.CTkLabel(row_f, text=f"₱{iprice:.2f}",
                                 font=ctk.CTkFont(size=12),
                                 text_color="#1A1A2E", width=80, anchor="e"
                                 ).grid(row=0, column=2, sticky="e", padx=(0,4), pady=4)
                    ctk.CTkLabel(row_f, text=f"₱{isub:.2f}",
                                 font=ctk.CTkFont(size=12, weight="bold"),
                                 text_color="#1565C0", width=90, anchor="e"
                                 ).grid(row=0, column=3, sticky="e", padx=(0,10), pady=4)
            else:
                ctk.CTkLabel(card, text="No items data.",
                             font=ctk.CTkFont(size=11),
                             text_color="#546E7A").pack(anchor="w", padx=14, pady=4)

            # ── Total ──
            ctk.CTkFrame(card, fg_color="#E0E0E0", height=1
                         ).pack(fill="x", padx=14, pady=(6,4))
            total_row = ctk.CTkFrame(card, fg_color="transparent")
            total_row.pack(fill="x", padx=14, pady=(0,8))
            ctk.CTkLabel(total_row, text="TOTAL",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#546E7A").pack(side="left")
            ctk.CTkLabel(total_row, text=f"₱{total:.2f}",
                         font=ctk.CTkFont(size=18, weight="bold"),
                         text_color="#1565C0").pack(side="right")

            # Cashier note
            if c_note:
                lbl_text = f"❌ Reason: {c_note}" if status=="Cancelled" else f"💬 Note: {c_note}"
                ctk.CTkLabel(card, text=lbl_text,
                             font=ctk.CTkFont(size=11),
                             text_color="#C62828" if status=="Cancelled" else "#1565C0",
                             wraplength=500, justify="left"
                             ).pack(anchor="w", padx=14, pady=(0,8))

            # ── Action buttons ──
            if status == "Pending":
                note_frame = ctk.CTkFrame(card, fg_color="#F8F9FA", corner_radius=6)
                note_frame.pack(fill="x", padx=14, pady=(4,4))

                ctk.CTkLabel(note_frame, text="Note to member (optional):",
                             font=ctk.CTkFont(size=11),
                             text_color="#546E7A").pack(anchor="w", padx=10, pady=(4,2))
                note_var = ctk.StringVar()
                ctk.CTkEntry(note_frame, textvariable=note_var,
                             placeholder_text="e.g. Your order is being prepared...",
                             height=34, font=ctk.CTkFont(size=11)
                             ).pack(fill="x", padx=10, pady=(0,8))

                btn_row = ctk.CTkFrame(card, fg_color="transparent")
                btn_row.pack(fill="x", padx=14, pady=(0,12))
                _accept_btn = ctk.CTkButton(btn_row, text="✓ Accept Order",
                              width=140, height=38,
                              fg_color="#2E7D32", hover_color="#1B5E20",
                              font=ctk.CTkFont(size=13, weight="bold"))
                _accept_btn.configure(command=lambda did=doc_id, o=order, nv=note_var, b=_accept_btn: [
                    b.configure(state="disabled", text="⏳ Processing..."),
                    self._accept_order(did, o, nv.get(), table, btn=b)
                ])
                _accept_btn.pack(side="left", padx=(0,8))
                ctk.CTkButton(btn_row, text="✕ Decline Order",
                              width=130, height=38,
                              fg_color="#C62828", hover_color="#8B0000",
                              font=ctk.CTkFont(size=13),
                              command=lambda did=doc_id, nv=note_var: self._decline_order_dialog(
                                  did, nv.get(), table)
                              ).pack(side="left")

            elif status == "Approved":
                _complete_btn = ctk.CTkButton(card, text="✅ Order Ready — Mark as Completed",
                              height=40, fg_color="#2E7D32",
                              hover_color="#1B5E20",
                              font=ctk.CTkFont(size=13, weight="bold"))
                _complete_btn.configure(command=lambda did=doc_id, o=order, b=_complete_btn: [
                    b.configure(state="disabled", text="⏳ Processing..."),
                    self._complete_order(did, o, table, btn=b)
                ])
                _complete_btn.pack(fill="x", padx=14, pady=(0,12))

    def _accept_order(self, doc_id, order, cashier_note, table, pay_method="Mobile Order", btn=None):
        """Accept order — ONLY update status. Stock deducted on Mark as Complete."""
        def _do():
            try:
                db._update_doc("mobile_orders", doc_id, {
                    "status":       "Approved",
                    "cashier_note": cashier_note,
                    "notification": "Your order has been accepted! We are now preparing your items."
                                    + (f" Note: {cashier_note}" if cashier_note else ""),
                })
                self.after(0, lambda: [
                    messagebox.showinfo("Accepted",
                        "✅ Order accepted!\nMember notified.", parent=self),
                    self._reload_mobile_orders(table)
                ])
            except Exception as e:
                self.after(0, lambda err=e: [
                    messagebox.showerror("Error", f"Failed: {err}", parent=self),
                    btn.configure(state="normal", text="✓ Accept Order") if btn else None
                ])
        threading.Thread(target=_do, daemon=True).start()

    def _decline_order_dialog(self, doc_id, existing_note, table):
        win = ctk.CTkToplevel(self)
        win.title("Decline Order")
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        win.resizable(False, False)
        W, H = 440, 260
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        win.configure(fg_color="#FFFFFF")

        ctk.CTkLabel(win, text="✕  Decline Order",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#C62828").pack(pady=(20,4))
        ctk.CTkLabel(win, text="Reason for declining (required):",
                     font=ctk.CTkFont(size=12),
                     text_color="#546E7A").pack(pady=(0,6))

        reason_var = ctk.StringVar(value=existing_note)
        ctk.CTkEntry(win, textvariable=reason_var,
                     placeholder_text="e.g. Item out of stock...",
                     height=40, font=ctk.CTkFont(size=13),
                     width=380).pack(pady=(0,16))

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack()

        def _confirm():
            reason = reason_var.get().strip()
            if not reason:
                messagebox.showwarning("Required",
                    "Please enter a reason.", parent=win)
                return
            win.destroy()
            def _do():
                try:
                    db._update_doc("mobile_orders", doc_id, {
                        "status":       "Cancelled",
                        "cashier_note": reason,
                        "notification": f"Your order has been declined. Reason: {reason}",
                    })
                    self.after(0, lambda: self._reload_mobile_orders(table))
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror(
                        "Error", f"Failed: {e}", parent=self))
            threading.Thread(target=_do, daemon=True).start()

        ctk.CTkButton(btn_row, text="Confirm Decline",
                      width=160, height=38,
                      fg_color="#C62828", hover_color="#8B0000",
                      font=ctk.CTkFont(size=13, weight="bold"),
                      command=_confirm).pack(side="left", padx=(0,8))
        ctk.CTkButton(btn_row, text="Back",
                      width=100, height=38,
                      fg_color="#757575", hover_color="#546E7A",
                      font=ctk.CTkFont(size=13),
                      command=win.destroy).pack(side="left")
        win.bind("<Return>", lambda e: _confirm())

    def _complete_order(self, doc_id, order, table, btn=None):
        # ── Disable button immediately to prevent double click ──
        if btn:
            try: btn.configure(state="disabled", text="⏳ Processing...")
            except Exception: pass
        def _do():
            try:
                from datetime import datetime as _dt
                # ── Move to Completed ──
                db._update_doc("mobile_orders", doc_id, {
                    "status":       "Completed",
                    "cashier_note": "Your order is on the way!",
                    "notification": "Your order is on the way! 🚀 Please prepare to receive it.",
                })
                # ── Save transaction (this also deducts stock via save_transaction) ──
                items = order.get("items",[]) if order else []
                if not isinstance(items, list): items = []
                cart_items = []
                total = 0.0
                for item in items:
                    if not isinstance(item, dict): continue
                    raw_id  = str(item.get("product_id","") or item.get("barcode","") or "")
                    istore  = str(item.get("store","canteen"))
                    barcode = raw_id
                    for prefix in ["cafestore_", "canteen_"]:
                        if raw_id.startswith(prefix):
                            barcode = raw_id[len(prefix):]
                            istore  = prefix.rstrip("_")
                            break
                    qty   = 1
                    try: qty = int(item.get("quantity",1) or 1)
                    except: pass
                    price = 0.0
                    try: price = float(item.get("price",0) or 0)
                    except: pass
                    total += price * qty
                    cart_items.append({
                        "barcode":  barcode,
                        "name":     str(item.get("name","")),
                        "price":    price,
                        "qty":      qty,
                        "category": str(item.get("category","General")),
                    })
                member_name = str(order.get("member_name","") if order else "")
                dept        = str(order.get("department","")  if order else "")
                db.save_transaction(
                    dt=_dt.now().strftime("%Y-%m-%d %H:%M:%S"),
                    total=total, method="Cash (Mobile)",
                    cash_given=total, change_given=0,
                    customer_name=member_name, department=dept,
                    items=cart_items, buyer_type="Member",
                    store="canteen",
                )
                self.after(0, lambda: [
                    messagebox.showinfo("Completed",
                        "✅ Order Completed!\nStock deducted.\nMember notified.", parent=self),
                    self._reload_mobile_orders(table),
                    self._reload_stock() if hasattr(self, "stock_table") else None
                ])
            except Exception as e:
                self.after(0, lambda: [
                    messagebox.showerror("Error", f"Failed: {e}", parent=self),
                    btn.configure(state="normal", text="✅ Order Ready — Mark as Completed") if btn else None
                ])
        threading.Thread(target=_do, daemon=True).start()


    # ── EXIT ─────────────────────────────────────────────────────
    def _exit_app(self):
        if messagebox.askyesno("Exit", "Are you sure you want to exit?", parent=self):
            self.destroy()


if __name__ == "__main__":
    import splash, login

    def _open_app(username, role, login_win):
        app = CanteenInventoryApp(login_window=login_win)
        app.mainloop()

    def _after_splash():
        # LOGIN DISABLED FOR TESTING — re-enable before deployment
        _open_app("store", "store", None)
        # login.require_login(
        #     allowed_roles=["store", "admin"],
        #     on_success=_open_app
        # )

    splash.show_splash(on_done=_after_splash, duration=3.0)