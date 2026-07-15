import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
import threading
import tkinter as tk
import database as db
import offline_db
import json
import os

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ─────────────────────────────────────────────
#  COLORS
# ─────────────────────────────────────────────
BG_DARK    = "#F5F5F5"
BG_PANEL   = "#FFFFFF"
BG_ROW     = "#F0F4F8"
BG_SIDEBAR = "#FFFFFF"
HEADER_CLR = "#1565C0"
ACCENT_CLR = "#1976D2"
TEXT_DARK  = "#1A1A2E"
TEXT_GREY  = "#546E7A"
COL_HDR    = "#BBDEFB"
BTN_QTY    = "#1565C0"
GREEN      = "#2E7D32"
ORANGE     = "#E65100"

DEPARTMENTS = ["CCS", "COED", "COAG", "COM", "Other"]
# ── FIX: Cash → Student/Other + Member only (Others removed from cash)
# ──      Credit stays Member + Others (non-member teacher)
CASH_CATEGORIES   = ["Student/Other", "Member"]
CREDIT_CATEGORIES = ["Member", "Others"]

# ─────────────────────────────────────────────
#  SHORTCUT PERSISTENCE
# ─────────────────────────────────────────────
_BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
SHORTCUTS_FILE = os.path.join(_BASE_DIR, "karen_shortcuts_config.json")

DEFAULT_SHORTCUTS = {
    "Help":          "F1",
    "Checkout":      "F2",
    "Search":        "F3",
    "New":           "F4",
    "Refresh":       "F5",
    "Scan":          "F6",
    "Customize":     "F7",
    "Edit":          "F8",
    "Delete":        "F9",
    "Last Txn":      "F10",
    "Add Qty":       "CTRL+F11",
    "Mobile Orders": "F11",
    "Logout":        "F12",
}


def _load_shortcuts_from_file():
    try:
        if os.path.exists(SHORTCUTS_FILE):
            with open(SHORTCUTS_FILE, "r") as f:
                data = json.load(f)
            # Accept if all default keys are present
            if set(DEFAULT_SHORTCUTS.keys()).issubset(set(data.keys())):
                return {k: data[k] for k in DEFAULT_SHORTCUTS}
    except Exception:
        pass
    return dict(DEFAULT_SHORTCUTS)


def _save_shortcuts_to_file(shortcuts: dict):
    try:
        with open(SHORTCUTS_FILE, "w") as f:
            json.dump(shortcuts, f, indent=2)
    except Exception as e:
        print("Shortcut save error:", e)


class CanteenDashboard(ctk.CTkToplevel):

    def _get_products(self):
        try:
            rows = db.get_all_products(store="canteen")
            return {r[0]: {"name": r[1], "category": r[2], "price": r[3], "stock": r[4]}
                    for r in rows}
        except Exception:
            return {}

    def _get_member_names(self):
        """Fetch loyalty members from ALL stores so card works in both systems."""
        all_members = []
        seen = set()
        for store in ["coop", "cafestore", "canteen"]:
            try:
                members = db.get_all_loyalty_members(store=store)
                for m in (members or []):
                    bc = m.get("card_barcode", "")
                    if bc not in seen:
                        seen.add(bc)
                        all_members.append(m)
            except Exception:
                pass
        return all_members

    def __init__(self, login_window, username):
        super().__init__(login_window)
        self.login_window = login_window
        self.username     = username
        self.title("Cafeteria Canteen — Point of Sale")
        self.attributes("-fullscreen", True)
        self.state("zoomed")
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        self.configure(fg_color=BG_DARK)
        self.protocol("WM_DELETE_WINDOW", self._logout)

        self.cart       = []
        self.pay_method = "Cash"

        self.shortcuts          = _load_shortcuts_from_file()
        self._shortcut_bindings = {}

        self._build_header()
        self._build_body()
        self._build_statusbar()
        self._refresh_cart()
        self._apply_shortcuts()

    # ── HEADER ───────────────────────────────────────────────
    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=HEADER_CLR, height=80, corner_radius=0)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)

        fpath_isufst = os.path.join(_BASE_DIR, "isufstlogo.png")
        try:
            if PIL_OK and os.path.exists(fpath_isufst):
                img   = Image.open(fpath_isufst).resize((62, 62), Image.LANCZOS)
                photo = ctk.CTkImage(light_image=img, dark_image=img, size=(62, 62))
                ctk.CTkLabel(hdr, image=photo, text="",
                             fg_color="transparent").pack(side="left", padx=(14, 6), pady=8)
        except Exception:
            pass

        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.pack(side="right", padx=(0, 10))
        ctk.CTkButton(right, text="Logout", width=80, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=12, weight="bold"),
                      command=self._logout).pack(side="right", padx=(8, 0))
        self.clock_lbl = ctk.CTkLabel(right, text="",
                                      font=ctk.CTkFont(size=12, weight="bold"),
                                      text_color="white", justify="right")
        self.clock_lbl.pack(side="right", padx=(0, 8))

        fpath_ccs = os.path.join(_BASE_DIR, "ccslogo.png")
        try:
            if PIL_OK and os.path.exists(fpath_ccs):
                img   = Image.open(fpath_ccs).resize((62, 62), Image.LANCZOS)
                photo = ctk.CTkImage(light_image=img, dark_image=img, size=(62, 62))
                ctk.CTkLabel(right, image=photo, text="",
                             fg_color="transparent").pack(side="right", padx=(0, 6), pady=8)
        except Exception:
            pass

        center = ctk.CTkFrame(hdr, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(center, text="CAFETERIA CANTEEN",
                     font=ctk.CTkFont(family="Georgia", size=24, weight="bold"),
                     text_color="white").pack()
        ctk.CTkLabel(center, text="Canteen  |  Point of Sale",
                     font=ctk.CTkFont(family="Georgia", size=12),
                     text_color="#BBDEFB").pack()
        self._tick()

    def _tick(self):
        now = datetime.now()
        self.clock_lbl.configure(
            text=f"{now.strftime('%a, %b %d, %Y')}\n{now.strftime('%I:%M %p')}")
        self.after(1000, self._tick)

    # ── BODY ─────────────────────────────────────────────────
    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.rowconfigure(0, weight=1)
        self._build_left(body)
        self._build_right(body)

    # ── LEFT PANEL ───────────────────────────────────────────
    def _build_left(self, parent):
        left = ctk.CTkFrame(parent, fg_color=BG_PANEL, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        left.rowconfigure(3, weight=1)
        left.columnconfigure(0, weight=1)

        # Barcode row
        bc_row = ctk.CTkFrame(left, fg_color="transparent")
        bc_row.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))
        bc_row.columnconfigure(0, weight=1)

        bc_frame = ctk.CTkFrame(bc_row, fg_color="#BBDEFB", corner_radius=8)
        bc_frame.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        bc_frame.columnconfigure(1, weight=1)
        ctk.CTkLabel(bc_frame, text="▐║▌║▐║",
                     font=ctk.CTkFont(size=12), text_color="#546E7A"
                     ).grid(row=0, column=0, padx=(12, 6))

        self.barcode_var   = ctk.StringVar()
        self.barcode_entry = ctk.CTkEntry(
            bc_frame, textvariable=self.barcode_var,
            placeholder_text="Scan barcode or type and press Enter...",
            border_width=0, fg_color="#BBDEFB",
            font=ctk.CTkFont(size=14), text_color="#1A1A2E",
            placeholder_text_color="#546E7A", height=40)
        self.barcode_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.after(200, self.barcode_entry.focus_set)
        self.barcode_entry.bind("<Return>", self._scan_barcode)

        ctk.CTkButton(bc_row, text="Scan", width=82, height=40,
                      fg_color=ACCENT_CLR, hover_color="#0D47A1",
                      font=ctk.CTkFont(size=15, weight="bold"), corner_radius=8,
                      command=self._scan_barcode).grid(row=0, column=1)

        # Search row
        search_outer = ctk.CTkFrame(left, fg_color="transparent")
        search_outer.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 6))
        search_outer.columnconfigure(0, weight=1)
        search_center = ctk.CTkFrame(search_outer, fg_color="transparent")
        search_center.pack(anchor="center")
        search_frame  = ctk.CTkFrame(search_center, fg_color="#BBDEFB", corner_radius=8)
        search_frame.pack(fill="x")
        search_frame.columnconfigure(1, weight=1)
        ctk.CTkLabel(search_frame, text="🔍", font=ctk.CTkFont(size=13),
                     text_color="#546E7A").grid(row=0, column=0, padx=(10, 4))
        self.search_var   = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            search_frame, textvariable=self.search_var,
            placeholder_text="Search Item...",
            border_width=0, fg_color="#BBDEFB",
            font=ctk.CTkFont(size=13), text_color="#1A1A2E",
            placeholder_text_color="#546E7A", height=36, width=340)
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", self._on_search_type)
        self.search_entry.bind("<FocusOut>",   lambda e: self.after(150, self._hide_search_suggestions))
        self.search_entry.bind("<Down>",       self._search_focus_down)
        self.search_entry.bind("<Escape>",     lambda e: self._hide_search_suggestions())

        # Keep a reference to search_frame for overlay positioning
        self._search_frame_ref = search_frame

        # Search suggestion overlay — parented to main window, floats via place()
        self._search_suggest_frame = tk.Frame(
            self, bg="#FFFFFF",
            highlightbackground="#1565C0", highlightthickness=1)
        self._search_suggest_lb = tk.Listbox(
            self._search_suggest_frame,
            bg="#FFFFFF", fg="#1A1A2E", font=("Segoe UI", 11),
            selectbackground="#BBDEFB", selectforeground="#1A1A2E",
            activestyle="dotbox", relief="flat", bd=0,
            highlightthickness=0, cursor="hand2")
        self._search_suggest_lb.pack(fill="both", expand=True)
        self._search_suggest_lb.bind("<<ListboxSelect>>", self._on_search_select)
        self._search_suggest_lb.bind("<Escape>", lambda e: self._hide_search_suggestions())

        # Column headers
        col_hdr = ctk.CTkFrame(left, fg_color=COL_HDR, height=34, corner_radius=0)
        col_hdr.grid(row=2, column=0, sticky="ew")
        col_hdr.pack_propagate(False)
        kw = {"font": ctk.CTkFont(size=11, weight="bold"),
              "text_color": TEXT_GREY, "fg_color": "transparent"}
        ctk.CTkLabel(col_hdr, text="SEL",        **kw).place(x=14,      rely=0.5, anchor="w")
        ctk.CTkLabel(col_hdr, text="ITEM",       **kw).place(x=54,      rely=0.5, anchor="w")
        ctk.CTkLabel(col_hdr, text="QTY",        **kw).place(relx=0.60, rely=0.5, anchor="center")
        ctk.CTkLabel(col_hdr, text="UNIT PRICE", **kw).place(relx=0.80, rely=0.5, anchor="center")
        ctk.CTkLabel(col_hdr, text="AMOUNT",     **kw).place(relx=0.90, rely=0.5, anchor="center")
        ctk.CTkLabel(col_hdr, text="DEL",        **kw).place(relx=0.975,rely=0.5, anchor="center")

        # Cart
        cart_container = ctk.CTkFrame(left, fg_color=BG_PANEL, corner_radius=0)
        cart_container.grid(row=3, column=0, sticky="nsew")
        cart_container.rowconfigure(0, weight=1)
        cart_container.columnconfigure(0, weight=1)
        self.cart_frame = ctk.CTkScrollableFrame(
            cart_container, fg_color=BG_PANEL,
            scrollbar_button_color="#1E3A50", corner_radius=0)
        self.cart_frame.grid(row=0, column=0, sticky="nsew")
        self.cart_frame.columnconfigure(0, weight=1)

    # ── SEARCH AUTOCOMPLETE ──────────────────────────────────
    def _position_search_suggestions(self):
        try:
            self.update_idletasks()
            sf  = self._search_frame_ref
            rx  = sf.winfo_rootx() - self.winfo_rootx()
            ry  = sf.winfo_rooty() - self.winfo_rooty() + sf.winfo_height()
            rw  = sf.winfo_width()
            cnt = self._search_suggest_lb.size()
            rh  = min(cnt, 8) * 26 + 4
            self._search_suggest_frame.place(x=rx, y=ry, width=rw, height=rh)
            self._search_suggest_frame.lift()
        except Exception:
            pass

    def _on_search_type(self, event=None):
        typed = self.search_var.get().strip().lower()
        if not typed:
            self._hide_search_suggestions(); return
        products = self._get_products()
        matches  = [(k, v) for k, v in products.items()
                    if (typed in v["name"].lower() or typed in k)
                    and v.get("stock", 0) > 0]
        if not matches:
            self._hide_search_suggestions(); return
        self._search_suggest_lb.delete(0, tk.END)
        for barcode, prod in matches[:8]:
            self._search_suggest_lb.insert(
                tk.END,
                f"  {prod['name']}  —  ₱{prod['price']:.2f}  [{barcode}]  · Stock: {prod['stock']}")
        self.after(20, self._position_search_suggestions)

    def _on_search_select(self, event=None):
        sel = self._search_suggest_lb.curselection()
        if not sel: return
        text    = self._search_suggest_lb.get(sel[0])
        barcode = text.strip().split("[")[-1].split("]")[0]
        self._hide_search_suggestions()
        self.search_var.set("")
        products = self._get_products()
        product  = products.get(barcode)
        if not product: return
        if product.get("stock", 0) <= 0:
            messagebox.showerror("Out of Stock",
                f"'{product['name']}' is OUT OF STOCK!", parent=self)
            return
        stock_limit = product.get("stock", 9999)
        for item in self.cart:
            if item["barcode"] == barcode:
                if item["qty"] >= stock_limit:
                    messagebox.showwarning("Stock Limit",
                        f"Only {stock_limit} in stock for '{product['name']}'!", parent=self)
                    return
                item["qty"] += 1
                self._refresh_cart(); return
        self.cart.append({"barcode": barcode, "name": product["name"],
                          "price": product["price"], "category": product["category"],
                          "stock": stock_limit, "qty": 1, "selected": False})
        self._refresh_cart()

    def _hide_search_suggestions(self):
        self._search_suggest_frame.place_forget()

    def _search_focus_down(self, event=None):
        self._search_suggest_lb.focus_set()
        if self._search_suggest_lb.size() > 0:
            self._search_suggest_lb.selection_set(0)

    # ── RIGHT PANEL ──────────────────────────────────────────
    def _build_right(self, parent):
        self.right = ctk.CTkFrame(parent, fg_color=BG_SIDEBAR,
                                  width=520, corner_radius=0)
        self.right.grid(row=0, column=1, sticky="nsew")
        self.right.pack_propagate(False)
        self.right.grid_propagate(False)
        self.right.rowconfigure(0, weight=1)
        self.right.rowconfigure(1, weight=0)
        self.right.columnconfigure(0, weight=1)

        top = ctk.CTkScrollableFrame(self.right, fg_color=BG_SIDEBAR,
                                     scrollbar_button_color=BTN_QTY, corner_radius=0)
        top.grid(row=0, column=0, sticky="nsew")
        top.columnconfigure(0, weight=1)
        P = 16

        ctk.CTkLabel(top, text="Order Summary",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color="#000000", anchor="w"
                     ).pack(anchor="w", padx=P, pady=(16, 8))

        total_box = ctk.CTkFrame(top, fg_color=HEADER_CLR, corner_radius=10,
                                 border_width=2, border_color="#0D47A1", height=56)
        total_box.pack(fill="x", padx=P, pady=(0, 4))
        total_box.pack_propagate(False)
        ctk.CTkLabel(total_box, text="TOTAL",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="white").place(x=14, rely=0.5, anchor="w")
        self.total_val = ctk.CTkLabel(total_box, text="₱0.00",
                                      font=ctk.CTkFont(size=22, weight="bold"),
                                      text_color="white")
        self.total_val.place(relx=0.97, rely=0.5, anchor="e")

        ctk.CTkFrame(top, fg_color="#BBDEFB", height=2).pack(fill="x", padx=P, pady=(8, 4))

        ctk.CTkLabel(top, text="LAST SCANNED ITEM",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#000000", anchor="w"
                     ).pack(anchor="w", padx=P, pady=(4, 2))

        self.item_detail_frame = ctk.CTkFrame(top, fg_color="#EEF4FF",
                                              corner_radius=10,
                                              border_width=1, border_color="#BBDEFB",
                                              height=90)
        self.item_detail_frame.pack(fill="x", padx=P, pady=(0, 8))
        self.item_detail_frame.pack_propagate(False)

        self.item_detail_barcode = ctk.CTkLabel(
            self.item_detail_frame, text="—",
            font=ctk.CTkFont(size=11), text_color="#546E7A")
        self.item_detail_barcode.place(x=14, y=10)
        self.item_detail_name = ctk.CTkLabel(
            self.item_detail_frame, text="No item scanned yet",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#000000")
        self.item_detail_name.place(x=14, y=30)
        self.item_detail_price = ctk.CTkLabel(
            self.item_detail_frame, text="",
            font=ctk.CTkFont(size=13), text_color=HEADER_CLR)
        self.item_detail_price.place(x=14, y=60)

        bottom = ctk.CTkFrame(self.right, fg_color=BG_SIDEBAR, corner_radius=0)
        bottom.grid(row=1, column=0, sticky="ew")
        ctk.CTkFrame(bottom, fg_color="#BBDEFB", height=2).pack(fill="x")

        btn_row = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_row.pack(fill="x", padx=P, pady=(8, 4))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        ctk.CTkButton(btn_row, text="↺  Clear All",
                      height=34, fg_color="#5D0000", hover_color="#8B0000",
                      corner_radius=8, font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="white", command=self._clear_all
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(btn_row, text="🗑  Delete Selected",
                      height=34, fg_color="#5D0000", hover_color="#8B0000",
                      corner_radius=8, font=ctk.CTkFont(size=11, weight="bold"),
                      text_color="white", command=self._delete_selected
                      ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.checkout_btn = ctk.CTkButton(
            bottom, text="🛒  Checkout",
            height=60, fg_color=ACCENT_CLR, hover_color="#0D47A1",
            corner_radius=12, font=ctk.CTkFont(size=20, weight="bold"),
            text_color="white", command=self._open_checkout_popup)
        self.checkout_btn.pack(fill="x", padx=P, pady=(0, 12))

    # ════════════════════════════════════════════════════════
    #  CHECKOUT POPUP
    # ════════════════════════════════════════════════════════
    def _open_checkout_popup(self):
        if not self.cart:
            messagebox.showwarning("Empty Cart", "No items in cart!", parent=self)
            return

        total = round(sum(i["price"] * i["qty"] for i in self.cart), 2)

        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)
        popup.configure(fg_color="#FFFFFF")
        popup.grab_set()
        self._pause_shortcuts()
        popup.bind("<Destroy>",
                   lambda e: self._resume_shortcuts() if e.widget is popup else None)

        W, H = 560, 640
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        popup.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        outer = tk.Frame(popup, bg="#0D47A1", bd=0, relief="flat")
        outer.pack(fill="both", expand=True)

        inner = ctk.CTkFrame(outer, fg_color="#FFFFFF", corner_radius=12)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        inner.rowconfigure(1, weight=1)
        inner.rowconfigure(2, weight=0)
        inner.columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(inner, fg_color=HEADER_CLR, height=54, corner_radius=10)
        hdr.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🛒  Checkout",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")

        total_badge = ctk.CTkFrame(hdr, fg_color="#0D47A1", corner_radius=20, height=32)
        total_badge.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(total_badge, text=f"  ₱{total:.2f}  ",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color="white", fg_color="transparent").pack(padx=8, pady=4)

        ctk.CTkButton(hdr, text="✕", width=34, height=34,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=17,
                      command=popup.destroy).place(relx=0.97, rely=0.5, anchor="e")

        body = ctk.CTkScrollableFrame(inner, fg_color="#FFFFFF",
                                      scrollbar_button_color=BTN_QTY, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew", padx=4)
        P = 18

        def section_label(text):
            ctk.CTkLabel(body, text=text,
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#546E7A", anchor="w"
                         ).pack(anchor="w", padx=P, pady=(12, 3))

        def bordered_option_menu(parent, variable, values):
            frame = ctk.CTkFrame(parent, fg_color="#F5F7FA", corner_radius=8,
                                 border_width=2, border_color="#BBDEFB")
            frame.pack(fill="x", padx=P, pady=(0, 2))
            menu = ctk.CTkOptionMenu(
                frame, variable=variable, values=values,
                fg_color="#F5F7FA", button_color=HEADER_CLR,
                button_hover_color="#0D47A1",
                dropdown_fg_color="#FFFFFF", dropdown_text_color="#000000",
                text_color="#000000", font=ctk.CTkFont(size=13, weight="bold"),
                corner_radius=6, height=38, anchor="w")
            menu.pack(fill="x", padx=4, pady=4)
            return frame, menu

        section_label("PAYMENT METHOD")
        pay_var = ctk.StringVar(value="Cash")
        pay_frame, pay_menu = bordered_option_menu(body, pay_var, ["Cash", "Credit / Utang"])

        section_label("CUSTOMER CATEGORY")
        # ── FIX: default is now "Student/Other" ──
        cat_var = ctk.StringVar(value="Student/Other")
        cat_frame, cat_menu = bordered_option_menu(body, cat_var, CASH_CATEGORIES)

        # Customer Name
        name_lbl = ctk.CTkLabel(body, text="CUSTOMER NAME",
                                font=ctk.CTkFont(size=10, weight="bold"),
                                text_color="#546E7A", anchor="w")
        name_outer = ctk.CTkFrame(body, fg_color="#F5F7FA", corner_radius=8,
                                  border_width=2, border_color="#BBDEFB")
        name_var   = ctk.StringVar()
        name_entry = ctk.CTkEntry(name_outer, textvariable=name_var,
                                  placeholder_text="Customer name...",
                                  height=38, fg_color="#F5F7FA", border_width=0,
                                  text_color="#000000", placeholder_text_color="#90A4AE",
                                  font=ctk.CTkFont(size=13))
        name_entry.pack(fill="x", padx=8, pady=4)

        # Name suggestion overlay — parented to popup, positioned with place()
        name_suggest_frame = tk.Frame(popup, bg="#FFFFFF",
                                      highlightbackground="#1565C0", highlightthickness=1)
        name_suggest_lb = tk.Listbox(
            name_suggest_frame,
            bg="#FFFFFF", fg="#1A1A2E", font=("Segoe UI", 11),
            selectbackground="#BBDEFB", selectforeground="#1A1A2E",
            activestyle="dotbox", relief="flat", bd=0,
            highlightthickness=0, cursor="hand2")
        name_suggest_lb.pack(fill="both", expand=True)

        def _hide_name_suggestions():
            name_suggest_frame.place_forget()

        def _show_name_suggestions_positioned():
            try:
                popup.update_idletasks()
                rx = name_outer.winfo_rootx() - popup.winfo_rootx()
                ry = name_outer.winfo_rooty() - popup.winfo_rooty() + name_outer.winfo_height()
                rw = name_outer.winfo_width()
                rh = min(name_suggest_lb.size(), 6) * 26 + 4
                name_suggest_frame.place(x=rx, y=ry, width=rw, height=rh)
                name_suggest_frame.lift()
            except Exception:
                pass

        # ── Preload members + teachers once for fast name suggestions ──
        _cached_members = []
        try:
            _cached_members = self._get_member_names()
            for store in ["cafestore", "canteen"]:
                for t in (db.get_all_teachers(store=store) or []):
                    _cached_members.append({
                        "name": t.get("name", ""),
                        "department": t.get("department", ""),
                    })
        except Exception:
            pass

        def _update_name_suggestions(*args):
            typed = name_var.get().strip().lower()
            _hide_name_suggestions()
            if not typed: return
            matches = [m for m in _cached_members if typed in m.get("name", "").lower()]
            if not matches: return
            name_suggest_lb.delete(0, tk.END)
            for m in matches[:6]:
                name_suggest_lb.insert(tk.END, f"  {m['name']}  [{m.get('department','')}]")
            popup.after(30, _show_name_suggestions_positioned)

        def _on_name_suggest_select(event=None):
            sel = name_suggest_lb.curselection()
            if not sel: return
            text = name_suggest_lb.get(sel[0])
            parts = text.strip().split("[")
            chosen_name = parts[0].strip()
            chosen_dept = parts[1].rstrip("]").strip() if len(parts) > 1 else ""
            _hide_name_suggestions()
            name_var.trace_remove("write", name_var.trace_info()[0][1])
            name_var.set(chosen_name)
            if chosen_dept: dept_var.set(chosen_dept)
            name_var.trace_add("write", _update_name_suggestions)
            name_entry.focus()

        name_var.trace_add("write", _update_name_suggestions)
        name_suggest_lb.bind("<<ListboxSelect>>", _on_name_suggest_select)

        # Department
        dept_lbl = ctk.CTkLabel(body, text="DEPARTMENT",
                                font=ctk.CTkFont(size=10, weight="bold"),
                                text_color="#546E7A", anchor="w")
        dept_var = ctk.StringVar(value="Select department...")
        dept_outer = ctk.CTkFrame(body, fg_color="#F5F7FA", corner_radius=8,
                                  border_width=2, border_color="#BBDEFB")
        dept_menu = ctk.CTkOptionMenu(
            dept_outer, variable=dept_var, values=DEPARTMENTS, height=38,
            fg_color="#F5F7FA", button_color=HEADER_CLR, button_hover_color="#0D47A1",
            dropdown_fg_color="#FFFFFF", dropdown_text_color="#000000",
            text_color="#000000", font=ctk.CTkFont(size=13),
            corner_radius=6, anchor="w")
        dept_menu.pack(fill="x", padx=4, pady=4)

        # Loyalty Card
        loyalty_lbl = ctk.CTkLabel(body, text="SCAN LOYALTY CARD",
                                   font=ctk.CTkFont(size=10, weight="bold"),
                                   text_color="#7B1FA2", anchor="w")
        loyalty_var   = ctk.StringVar()
        loyalty_outer = ctk.CTkFrame(body, fg_color="#F3E5F5",
                                     corner_radius=8, border_width=2, border_color="#7B1FA2")
        loyalty_inner_row = ctk.CTkFrame(loyalty_outer, fg_color="transparent")
        loyalty_inner_row.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(loyalty_inner_row, text="💳",
                     font=ctk.CTkFont(size=14), fg_color="transparent"
                     ).pack(side="left", padx=(6, 4))
        loyalty_entry = ctk.CTkEntry(
            loyalty_inner_row, textvariable=loyalty_var,
            placeholder_text="Scan loyalty card barcode...",
            border_width=0, fg_color="#F3E5F5",
            font=ctk.CTkFont(size=13), text_color="#000000",
            placeholder_text_color="#9C27B0", height=36)
        loyalty_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        loyalty_info = ctk.CTkLabel(body, text="",
                                    font=ctk.CTkFont(size=11, weight="bold"),
                                    text_color="#7B1FA2")

        def on_loyalty_scan(event=None):
            card_id = loyalty_var.get().strip()
            if not card_id: return
            member = db.get_loyalty_member_by_card(card_id)
            if member:
                name_var.set(member["name"])
                dept_var.set(member["department"])
                loyalty_info.configure(
                    text=f"✓  {member['name']} | {member['department']} | ID: {member['member_id']}",
                    text_color="#2E7D32")
                cat_var.set("Member")
                _update_fields("Member")
            else:
                loyalty_info.configure(text="⚠  Card not found", text_color="#C62828")

        loyalty_entry.bind("<Return>", on_loyalty_scan)

        # Cash entry
        cash_lbl = ctk.CTkLabel(body, text="CUSTOMER CASH",
                                font=ctk.CTkFont(size=10, weight="bold"),
                                text_color="#546E7A", anchor="w")
        cash_outer = ctk.CTkFrame(body, fg_color="#F5F7FA", corner_radius=8,
                                  border_width=2, border_color="#BBDEFB")
        cash_inner = ctk.CTkFrame(cash_outer, fg_color="transparent")
        cash_inner.pack(fill="x", padx=4, pady=4)
        ctk.CTkLabel(cash_inner, text="₱",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#546E7A", fg_color="transparent").pack(side="left", padx=(6, 2))
        cash_var = ctk.StringVar()
        cash_entry = ctk.CTkEntry(cash_inner, textvariable=cash_var,
                                  placeholder_text="Enter amount (optional)...",
                                  border_width=0, fg_color="#F5F7FA",
                                  font=ctk.CTkFont(size=14), text_color="#000000",
                                  placeholder_text_color="#90A4AE", height=36)
        cash_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        # Quick cash buttons
        qf = ctk.CTkFrame(body, fg_color="transparent")
        for amt in [20, 50, 100, 500]:
            ctk.CTkButton(qf, text=f"₱{amt}", width=80, height=32,
                          fg_color=BTN_QTY, hover_color="#0D47A1",
                          font=ctk.CTkFont(size=12, weight="bold"),
                          text_color="white", corner_radius=8,
                          command=lambda a=amt, cv=cash_var: cv.set(
                              str(float(cv.get() or 0) + a))
                          ).pack(side="left", padx=4)

        # Live change preview — only shows when cash > 0
        chg_preview = ctk.CTkLabel(body, text="",
                                   font=ctk.CTkFont(size=13, weight="bold"),
                                   text_color="#2E7D32", anchor="center")

        def _update_chg_preview(*_):
            try:
                c = float(cash_var.get())
                if c <= 0:
                    chg_preview.configure(text="", text_color="#2E7D32")
                    return
                diff = c - total
                if diff < 0:
                    chg_preview.configure(
                        text=f"⚠  Not Enough!  Short by ₱{abs(diff):.2f}",
                        text_color="#C62828")
                else:
                    chg_preview.configure(
                        text=f"Change: ₱{diff:.2f}",
                        text_color="#2E7D32")
            except ValueError:
                chg_preview.configure(text="", text_color="#2E7D32")

        cash_var.trace_add("write", _update_chg_preview)

        # ── Dynamic field show/hide ──
        # Cash: Student/Other → cash only (anonymous, no name/dept)
        #       Member         → name + dept + loyalty + cash
        # Credit: Member       → name + dept + loyalty
        #         Others        → name + dept (teacher)
        def _update_fields(cat=None, pay=None):
            cat = cat or cat_var.get()
            pay = pay or pay_var.get()

            name_lbl.pack_forget()
            name_outer.pack_forget()
            _hide_name_suggestions()
            dept_lbl.pack_forget()
            dept_outer.pack_forget()
            loyalty_lbl.pack_forget()
            loyalty_outer.pack_forget()
            loyalty_info.pack_forget()
            cash_lbl.pack_forget()
            cash_outer.pack_forget()
            qf.pack_forget()
            chg_preview.pack_forget()

            if pay == "Cash":
                if cat == "Member":
                    name_lbl.pack(anchor="w", padx=P, pady=(10, 3))
                    name_outer.pack(fill="x", padx=P, pady=(0, 2))
                    dept_lbl.pack(anchor="w", padx=P, pady=(10, 3))
                    dept_outer.pack(fill="x", padx=P, pady=(0, 2))
                    loyalty_lbl.pack(anchor="w", padx=P, pady=(10, 3))
                    loyalty_outer.pack(fill="x", padx=P, pady=(0, 2))
                    loyalty_info.pack(anchor="w", padx=P, pady=(2, 0))
                # Student/Other → anonymous, no name/dept fields shown
                cash_lbl.pack(anchor="w", padx=P, pady=(10, 3))
                cash_outer.pack(fill="x", padx=P, pady=(0, 4))
                qf.pack(padx=P, pady=(4, 2))
                chg_preview.pack(fill="x", padx=P, pady=(2, 10))

            elif pay == "Credit / Utang":
                name_lbl.pack(anchor="w", padx=P, pady=(10, 3))
                name_outer.pack(fill="x", padx=P, pady=(0, 2))
                dept_lbl.pack(anchor="w", padx=P, pady=(10, 3))
                dept_outer.pack(fill="x", padx=P, pady=(0, 2))
                if cat == "Member":
                    loyalty_lbl.pack(anchor="w", padx=P, pady=(10, 3))
                    loyalty_outer.pack(fill="x", padx=P, pady=(0, 2))
                    loyalty_info.pack(anchor="w", padx=P, pady=(2, 8))
                else:
                    ctk.CTkFrame(body, fg_color="transparent", height=10).pack()

        def _focus_correct_field():
            pay = pay_var.get()
            cat = cat_var.get()
            if pay == "Cash" and cat == "Member":
                name_entry.focus()
            elif pay == "Cash":
                cash_entry.focus()
            else:
                name_entry.focus()

        cat_menu.configure(command=lambda v: [_update_fields(cat=v),
            popup.after(50, _focus_correct_field)])
        pay_menu.configure(command=lambda v: [
            cat_menu.configure(values=CASH_CATEGORIES if v == "Cash" else CREDIT_CATEGORIES),
            cat_var.set("Student/Other" if v == "Cash" else "Member"),
            _update_fields(pay=v),
            popup.after(50, _focus_correct_field)])

        _update_fields()
        popup.after(100, _focus_correct_field)
        popup.bind("<Return>", lambda e: _confirm())
        popup.bind("<KP_Enter>", lambda e: _confirm())
        cash_entry.bind("<Return>", lambda e: _confirm())
        name_entry.bind("<Return>", lambda e: _confirm())

        # Sticky bottom buttons
        btn_bottom = ctk.CTkFrame(inner, fg_color="#FFFFFF", corner_radius=0)
        btn_bottom.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 4))
        ctk.CTkFrame(btn_bottom, fg_color="#BBDEFB", height=2).pack(fill="x", pady=(0, 6))

        def _confirm():
            pay = pay_var.get()
            cat = cat_var.get()

            if pay == "Cash":
                try:    cash = float(cash_var.get())
                except: cash = 0.0
                # ── FIX: cash is OPTIONAL — only validate if cashier typed an amount ──
                if cash > 0 and cash < total:
                    messagebox.showerror("Not Enough",
                        f"Cash ₱{cash:.2f} is not enough.\n"
                        f"Short by ₱{total - cash:.2f}.", parent=popup)
                    return
                change = round(max(cash - total, 0), 2)
                cname  = ""
                dept   = ""
                if cat == "Member":
                    cname = name_var.get().strip()
                    if not cname:
                        messagebox.showerror("Error", "Please enter member name.", parent=popup)
                        return
                    dept = dept_var.get()
                    if dept == "Select department...":
                        messagebox.showerror("Error", "Please select a department.", parent=popup)
                        return
                # Student/Other → anonymous, no validation needed
                popup.destroy()
                self._save_and_clear("Cash", total, cash=cash, change=change,
                                     cname=cname, dept=dept, buyer_type=cat)
                self._show_payment_success(change)

            elif pay == "Credit / Utang":
                cname = name_var.get().strip()
                dept  = dept_var.get()
                if not cname:
                    messagebox.showerror("Error", "Please enter customer name.", parent=popup)
                    return
                if dept == "Select department...":
                    messagebox.showerror("Error", "Please select a department.", parent=popup)
                    return
                popup.destroy()
                messagebox.showinfo("Credit Recorded",
                                    f"✓ Credit recorded!\n\nCustomer: {cname}\n"
                                    f"Dept: {dept}\nAmount: ₱{total:.2f}", parent=self)
                if cat == "Others":
                    threading.Thread(target=lambda: db.ensure_teacher_registered(cname, dept),
                                     daemon=True).start()
                self._save_and_clear("Credit / Utang", total, cname=cname, dept=dept,
                                     buyer_type=cat)

        ctk.CTkButton(btn_bottom, text="✓  Confirm Payment",
                      height=52, fg_color=GREEN, hover_color="#1B5E20",
                      corner_radius=10, font=ctk.CTkFont(size=16, weight="bold"),
                      text_color="white", command=_confirm
                      ).pack(fill="x", padx=12, pady=(0, 6))

        ctk.CTkButton(btn_bottom, text="✕  Cancel",
                      height=36, fg_color="#5D0000", hover_color="#8B0000",
                      corner_radius=8, font=ctk.CTkFont(size=12, weight="bold"),
                      text_color="white", command=popup.destroy
                      ).pack(fill="x", padx=12, pady=(0, 6))

        self._bind_shortcuts_to_popup(popup, _confirm)

    # ════════════════════════════════════════════════════════
    #  PAYMENT SUCCESS DIALOG — Change only, big display
    # ════════════════════════════════════════════════════════
    def _show_payment_success(self, change):
        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color="#111111")
        win.grab_set()
        win.resizable(False, False)
        W, H = 360, 260
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        inner = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=14)
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        hdr = ctk.CTkFrame(inner, fg_color=GREEN, height=58, corner_radius=10)
        hdr.pack(fill="x", padx=4, pady=(4, 0))
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="✓  Transaction Successful!",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color="white").place(relx=0.5, rely=0.5, anchor="center")

        chg_box = ctk.CTkFrame(inner, fg_color="#E8F5E9", corner_radius=14,
                               border_width=2, border_color="#A5D6A7")
        chg_box.pack(fill="both", expand=True, padx=20, pady=12)
        ctk.CTkLabel(chg_box, text="CHANGE",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#546E7A").pack(anchor="center", pady=(18, 4))
        ctk.CTkLabel(chg_box, text=f"₱{change:.2f}",
                     font=ctk.CTkFont(size=44, weight="bold"),
                     text_color=GREEN).pack(anchor="center", pady=(0, 18))

        ctk.CTkButton(inner, text="OK  ✓",
                      height=46, fg_color=GREEN, hover_color="#1B5E20",
                      corner_radius=10, font=ctk.CTkFont(size=15, weight="bold"),
                      text_color="white", command=win.destroy
                      ).pack(fill="x", padx=20, pady=(0, 14))

        win.bind("<Return>",   lambda e: win.destroy())
        win.bind("<KP_Enter>", lambda e: win.destroy())
        win.bind("<Escape>",   lambda e: win.destroy())
        win.bind("<space>",    lambda e: win.destroy())
        win.after(50, win.focus_set)

    # ════════════════════════════════════════════════════════
    #  CART RENDER
    # ════════════════════════════════════════════════════════
    def _refresh_cart(self):
        for w in self.cart_frame.winfo_children():
            w.destroy()
        if not self.cart:
            empty = ctk.CTkFrame(self.cart_frame, fg_color="transparent")
            empty.pack(pady=60)
            ctk.CTkLabel(empty, text="🛒", font=ctk.CTkFont(size=44),
                         text_color="#BBDEFB").pack()
            ctk.CTkLabel(empty, text="No items scanned yet",
                         font=ctk.CTkFont(size=14), text_color="#546E7A").pack(pady=2)
            ctk.CTkLabel(empty, text="Scan a barcode to add items",
                         font=ctk.CTkFont(size=11), text_color="#90A4AE").pack()
        else:
            for idx, item in enumerate(self.cart):
                self._render_row(idx, item)
        self._update_totals()
        self.barcode_entry.focus()

    def _render_row(self, idx, item):
        row = ctk.CTkFrame(self.cart_frame, fg_color=BG_ROW, corner_radius=4, height=56)
        row.pack(fill="x", padx=4, pady=2)
        row.pack_propagate(False)

        sel_var = ctk.BooleanVar(value=item.get("selected", False))
        ctk.CTkCheckBox(row, variable=sel_var, width=20, text="",
                        checkbox_width=18, checkbox_height=18,
                        border_color="#1E3A50", fg_color=BTN_QTY,
                        command=lambda i=idx, v=sel_var: self._toggle_sel(i, v)
                        ).place(x=14, rely=0.5, anchor="w")
        ctk.CTkLabel(row, text=item["name"],
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#1A1A2E", anchor="w"
                     ).place(x=54, rely=0.28, anchor="w")
        ctk.CTkLabel(row, text=f"{item['category']} · {item['barcode']}",
                     font=ctk.CTkFont(size=9), text_color="#546E7A", anchor="w"
                     ).place(x=54, rely=0.68, anchor="w")

        qty_inner = ctk.CTkFrame(row, fg_color="transparent")
        qty_inner.place(relx=0.62, rely=0.5, anchor="center")
        stock_limit = item.get("stock", 9999)

        ctk.CTkButton(qty_inner, text="−", width=26, height=26,
                      fg_color=BTN_QTY, hover_color="#0D47A1",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=4,
                      command=lambda i=idx: self._change_qty(i, -1)).pack(side="left")

        qty_edit_var = ctk.StringVar(value=str(item["qty"]))
        qty_edit = ctk.CTkEntry(qty_inner, textvariable=qty_edit_var,
                                width=38, height=26, fg_color="#FFFFFF",
                                border_width=1, border_color="#BBDEFB",
                                font=ctk.CTkFont(size=12, weight="bold"),
                                text_color="#000000", justify="center")
        qty_edit.pack(side="left", padx=2)

        def _apply_edit(event=None, i=idx, v=qty_edit_var, sl=stock_limit):
            try:
                new_qty = int(v.get())
                if new_qty <= 0:
                    self.cart.pop(i)
                elif new_qty > sl:
                    messagebox.showwarning("Stock Limit", f"Only {sl} in stock!", parent=self)
                    self.cart[i]["qty"] = sl
                else:
                    self.cart[i]["qty"] = new_qty
                self._refresh_cart()
            except ValueError:
                pass

        qty_edit.bind("<Return>",   _apply_edit)
        qty_edit.bind("<FocusOut>", _apply_edit)

        plus_btn = ctk.CTkButton(qty_inner, text="+", width=26, height=26,
                      fg_color=BTN_QTY if item["qty"] < stock_limit else "#AAAAAA",
                      hover_color="#0D47A1" if item["qty"] < stock_limit else "#AAAAAA",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=4,
                      state="normal" if item["qty"] < stock_limit else "disabled",
                      command=lambda i=idx: self._change_qty(i, 1))
        plus_btn.pack(side="left")

        ctk.CTkLabel(row, text=f"₱{item['price']:.2f}",
                     font=ctk.CTkFont(size=12), text_color="#546E7A", anchor="center"
                     ).place(relx=0.80, rely=0.5, anchor="center")
        ctk.CTkLabel(row, text=f"₱{item['price'] * item['qty']:.2f}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#1A1A2E", anchor="center"
                     ).place(relx=0.90, rely=0.5, anchor="center")
        ctk.CTkButton(row, text="🗑", width=28, height=28,
                      fg_color="#3D0000", hover_color="#700000",
                      corner_radius=5, font=ctk.CTkFont(size=13),
                      command=lambda i=idx: self._delete_item(i)
                      ).place(relx=0.975, rely=0.5, anchor="center")

    def _scan_barcode(self, event=None):
        code = self.barcode_var.get().strip()
        if not code: return
        self.status_lbl.configure(text=f"Searching: {code}...")
        self.barcode_entry.configure(state="disabled")
        def _do():
            products = self._get_products()
            product  = products.get(code)
            self.after(0, lambda: self._finish_scan(code, product))
        threading.Thread(target=_do, daemon=True).start()

    def _finish_scan(self, code, product):
        self.barcode_entry.configure(state="normal")
        self.barcode_var.set("")
        self.barcode_entry.focus()
        if not product:
            self.status_lbl.configure(text=f"Not found: {code}")
            self.item_detail_barcode.configure(text=code, text_color="#B71C1C")
            self.item_detail_name.configure(text="Item not found!", text_color="#B71C1C")
            self.item_detail_price.configure(text="Add this item in Inventory first")
            self.after(3000, self._clear_item_detail)
            messagebox.showerror("Not Found",
                f"Barcode {code} not found.\nAdd it in Inventory first.", parent=self)
            return
        self.item_detail_barcode.configure(text=f"Barcode: {code}", text_color="#546E7A")
        self.item_detail_name.configure(text=product["name"], text_color="#000000")
        self.item_detail_price.configure(
            text=f"₱{product['price']:.2f}  |  {product['category']}", text_color=HEADER_CLR)
        stock_limit     = product.get("stock", 9999)
        current_in_cart = sum(i["qty"] for i in self.cart if i["barcode"] == code)
        if stock_limit <= 0:
            messagebox.showerror("Out of Stock",
                f"'{product['name']}' is OUT OF STOCK!", parent=self)
            return
        if current_in_cart >= stock_limit:
            messagebox.showwarning("Stock Limit",
                f"Cannot add more '{product['name']}'.\nOnly {stock_limit} in stock!", parent=self)
            return
        for item in self.cart:
            if item["barcode"] == code:
                item["qty"] += 1
                self._refresh_cart(); return
        self.cart.append({"barcode": code, "name": product["name"],
                          "price": product["price"], "category": product["category"],
                          "stock": stock_limit, "qty": 1, "selected": False})
        self._refresh_cart()

    def _clear_item_detail(self):
        self.item_detail_barcode.configure(text="—", text_color="#546E7A")
        self.item_detail_name.configure(text="No item scanned yet", text_color="#000000")
        self.item_detail_price.configure(text="")

    def _toggle_sel(self, idx, var): self.cart[idx]["selected"] = var.get()

    def _change_qty(self, idx, delta):
        item  = self.cart[idx]
        stock = item.get("stock", 9999)
        new_q = item["qty"] + delta
        if new_q <= 0:
            self.cart.pop(idx)
        elif new_q > stock:
            messagebox.showwarning("Stock Limit",
                f"Only {stock} in stock for '{item['name']}'!", parent=self)
            return
        else:
            self.cart[idx]["qty"] = new_q
        self._refresh_cart()

    def _delete_item(self, idx):
        self.cart.pop(idx); self._refresh_cart()

    def _delete_selected(self):
        selected = [i for i, item in enumerate(self.cart) if item.get("selected", False)]
        if not selected:
            messagebox.showinfo("No Selection", "Please check items to delete first.", parent=self)
            return
        if messagebox.askyesno("Delete Selected", f"Delete {len(selected)} item(s)?", parent=self):
            for i in reversed(selected): self.cart.pop(i)
            self._refresh_cart()

    def _clear_all(self):
        if self.cart and messagebox.askyesno("Clear Cart", "Remove all items?", parent=self):
            self.cart.clear(); self._refresh_cart()

    def _update_totals(self):
        total = round(sum(i["price"] * i["qty"] for i in self.cart), 2)
        self.total_val.configure(text=f"₱{total:.2f}")
        self.status_lbl.configure(
            text=f"{sum(i['qty'] for i in self.cart)} item(s) · {len(self.cart)} product(s)")

    def _save_and_clear(self, method, total, cash=0.0, change=0.0,
                        cname="", dept="", buyer_type=""):
        try:
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.save_transaction(dt, total, method, cash, change,
                                cname, dept, self.cart,
                                buyer_type=buyer_type, store="canteen")
        except Exception as e:
            print("Save error:", e)

        # ── Auto-register as Coop Member if Member type + no card yet ──
        if buyer_type == "Member" and cname.strip():
            try:
                existing = None
                for store in ["coop", "cafestore", "canteen"]:
                    existing = db.get_loyalty_member_by_card_name(cname.strip(), store=store)
                    if existing:
                        break
                if not existing:
                    import random, string
                    member_id  = "MBR-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
                    card_bc    = "CARD-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
                    db.add_loyalty_member(member_id, cname.strip(), dept or "", card_bc, store="coop")
                    print(f"Auto-registered member: {cname} → {member_id}")
            except Exception as e:
                print("Auto-register error:", e)

        self.cart.clear()
        self._clear_item_detail()
        self._refresh_cart()

    # ── STATUS BAR ───────────────────────────────────────────
    def _build_statusbar(self):
        fbar = ctk.CTkFrame(self, fg_color="#FFFFFF", height=48, corner_radius=0)
        fbar.pack(fill="x", side="bottom")
        fbar.pack_propagate(False)
        ctk.CTkFrame(fbar, fg_color="#BBDEFB", height=2).pack(fill="x", side="top")

        fkeys = [
            ("F1","Help"), ("F2","Checkout"), ("F3","Search"), ("F4","New"),
            ("F5","Refresh"), ("F6","Scan"), ("F7","⚙ Keys"), ("F8","Edit"),
            ("F9","Delete"), ("F10","Last Txn"), ("F11","📱Orders"), ("F12","Logout"),
        ]
        for fk, label in fkeys:
            f = ctk.CTkFrame(fbar, fg_color="transparent")
            f.pack(side="left", padx=4, pady=6)
            ctk.CTkLabel(f, text=fk,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         fg_color=HEADER_CLR, text_color="white",
                         corner_radius=4, width=38, height=26
                         ).pack(side="left", padx=(0, 3))
            ctk.CTkLabel(f, text=label,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#1A1A2E").pack(side="left")

        # ☁️ Backup button in statusbar
        self._backup_panel_open = False
        ctk.CTkButton(fbar, text="☁️  Backup", width=90, height=32,
                      fg_color="#1565C0", hover_color="#1976D2",
                      text_color="white", font=ctk.CTkFont(size=11, weight="bold"),
                      corner_radius=6,
                      command=self._toggle_backup_popup
                      ).pack(side="right", padx=8, pady=6)

        sb = ctk.CTkFrame(self, fg_color="#E3F2FD", height=26, corner_radius=0)
        sb.pack(fill="x", side="bottom")
        self.status_lbl = ctk.CTkLabel(sb, text="0 item(s) · 0 product(s)",
                                       font=ctk.CTkFont(size=12), text_color="#546E7A")
        self.status_lbl.pack(side="left", padx=16)

    # ════════════════════════════════════════════════════════
    #  SHORTCUT KEY SYSTEM
    #  • Multiple keys per action: comma-separated e.g. "F2,CTRL+Q"
    #  • Persistent: saved to karen_shortcuts_config.json
    #  • Works in checkout popup via _bind_shortcuts_to_popup
    # ════════════════════════════════════════════════════════
    def _parse_key_string(self, key_str):
        key_str = key_str.strip().upper()
        parts   = [p.strip() for p in key_str.split("+")]
        mods, key = [], parts[-1]
        for p in parts[:-1]:
            if p in ("CTRL", "CONTROL"): mods.append("Control")
            elif p == "ALT":             mods.append("Alt")
            elif p == "SHIFT":           mods.append("Shift")
        tk_key = key if (key.startswith("F") and key[1:].isdigit()) else key.lower()
        return ("<" + "-".join(mods) + "-" + tk_key + ">" if mods else "<" + tk_key + ">")

    def _get_action_map(self):
        return {
            "Help":      lambda e: self._fkey_help(),
            "Checkout":  lambda e: self._open_checkout_popup(),
            "Search":    lambda e: self.search_entry.focus(),
            "New":       lambda e: self._fkey_new(),
            "Refresh":   lambda e: self._fkey_refresh(),
            # ── F6 Scan — scans if barcode typed, else focuses entry ──
            "Scan":      lambda e: (self._scan_barcode() if self.barcode_var.get().strip()
                                    else self.barcode_entry.focus()),
            "Customize": lambda e: self._open_shortcut_editor(),
            "Edit":      lambda e: self._fkey_edit(),
            "Delete":    lambda e: self._delete_selected(),
            "Last Txn":  lambda e: self._fkey_last_transaction(),
            "Add Qty":   lambda e: self._fkey_add_qty(),
            "Mobile Orders": lambda e: self._fkey_mobile_orders(),
            "Logout":    lambda e: self._logout(),
        }

    def _pause_shortcuts(self):
        for seqs in self._shortcut_bindings.values():
            for seq in seqs:
                try: self.unbind(seq)
                except Exception: pass

    def _resume_shortcuts(self):
        self._apply_shortcuts()

    def _apply_shortcuts(self):
        for seqs in self._shortcut_bindings.values():
            for seq in seqs:
                try: self.unbind(seq)
                except Exception: pass
        self._shortcut_bindings.clear()

        action_map = self._get_action_map()
        for action, key_str in self.shortcuts.items():
            handler = action_map.get(action)
            if not handler: continue
            self._shortcut_bindings[action] = []
            for k in [x.strip() for x in key_str.split(",") if x.strip()]:
                try:
                    seq = self._parse_key_string(k)
                    self.bind(seq, handler)
                    self._shortcut_bindings[action].append(seq)
                except Exception as ex:
                    print(f"Bind error {action} → {k}: {ex}")

    def _bind_shortcuts_to_popup(self, popup, confirm_fn):
        for action in ("Checkout",):
            key_str = self.shortcuts.get(action, "")
            for k in [x.strip() for x in key_str.split(",") if x.strip()]:
                try:
                    popup.bind(self._parse_key_string(k), lambda e, fn=confirm_fn: fn())
                except Exception:
                    pass
        for k in [x.strip() for x in self.shortcuts.get("Help","").split(",") if x.strip()]:
            try: popup.bind(self._parse_key_string(k), lambda e: self._fkey_help())
            except Exception: pass
        for k in [x.strip() for x in self.shortcuts.get("Logout","").split(",") if x.strip()]:
            try: popup.bind(self._parse_key_string(k), lambda e: popup.destroy())
            except Exception: pass
        popup.bind("<Return>", lambda e: confirm_fn())
        popup.bind("<Escape>", lambda e: popup.destroy())

    # ── F1 HELP ──────────────────────────────────────────────
    def _fkey_help(self):
        win = ctk.CTkToplevel(self)
        win.title("Keyboard Shortcuts")
        win.geometry("560x640")
        win.configure(fg_color="#F5F5F5")
        win.grab_set(); win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"560x640+{(sw-560)//2}+{(sh-640)//2}")

        hdr = ctk.CTkFrame(win, fg_color=HEADER_CLR, height=50, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="⌨  Keyboard Shortcuts",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="✕", width=32, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13), corner_radius=6,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        ctk.CTkLabel(win,
                     text="Tip: Assign multiple keys per action (e.g. F2,CTRL+Q).",
                     font=ctk.CTkFont(size=11), text_color="#546E7A"
                     ).pack(anchor="w", padx=16, pady=(8, 2))

        scroll = ctk.CTkScrollableFrame(win, fg_color="#F5F5F5")
        scroll.pack(fill="both", expand=True, padx=16, pady=(4, 4))

        for action, key_str in self.shortcuts.items():
            row = ctk.CTkFrame(scroll, fg_color="#FFFFFF", corner_radius=6, height=40)
            row.pack(fill="x", pady=2); row.pack_propagate(False)
            ctk.CTkLabel(row, text=key_str, width=160,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         fg_color=HEADER_CLR, text_color="white",
                         corner_radius=4).place(x=8, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text=action, font=ctk.CTkFont(size=11),
                         text_color="#1A1A2E").place(x=178, rely=0.5, anchor="w")

        ctk.CTkButton(win, text="⚙  Customize Shortcuts",
                      height=40, fg_color=ACCENT_CLR, hover_color="#0D47A1",
                      corner_radius=8, font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="white",
                      command=lambda: [win.destroy(), self._open_shortcut_editor()]
                      ).pack(fill="x", padx=16, pady=(4, 12))

    # ── CUSTOMIZE SHORTCUTS EDITOR ───────────────────────────
    def _open_shortcut_editor(self):
        win = ctk.CTkToplevel(self)
        win.title("Customize Shortcuts")
        win.geometry("580x720")
        win.configure(fg_color="#F5F5F5")
        win.grab_set(); win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"580x720+{(sw-580)//2}+{(sh-720)//2}")

        hdr = ctk.CTkFrame(win, fg_color=HEADER_CLR, height=54, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="⚙  Customize Shortcut Keys",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="✕", width=32, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13), corner_radius=6,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        ctk.CTkLabel(win,
                     text="Separate multiple keys with a comma:  F2  |  F2,CTRL+Q  |  ALT+C,F3",
                     font=ctk.CTkFont(size=11), text_color="#546E7A",
                     wraplength=540).pack(anchor="w", padx=18, pady=(10, 4))

        scroll = ctk.CTkScrollableFrame(win, fg_color="#F5F5F5")
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        entries = {}
        for action, key_str in self.shortcuts.items():
            row = ctk.CTkFrame(scroll, fg_color="#FFFFFF", corner_radius=8, height=52)
            row.pack(fill="x", pady=3); row.pack_propagate(False)
            ctk.CTkLabel(row, text=action, width=110,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#1A1A2E").place(x=10, rely=0.5, anchor="w")
            ctk.CTkLabel(row, text="e.g. F2,CTRL+Q",
                         font=ctk.CTkFont(size=9),
                         text_color="#90A4AE").place(x=120, rely=0.5, anchor="w")
            var = ctk.StringVar(value=key_str)
            e = ctk.CTkEntry(row, textvariable=var, width=230, height=36,
                             fg_color="#EEF4FF", border_width=2, border_color="#BBDEFB",
                             text_color="#1A1A2E", font=ctk.CTkFont(size=12))
            e.place(relx=0.97, rely=0.5, anchor="e")
            entries[action] = var

        btn_row = ctk.CTkFrame(win, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 12))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)

        def _save():
            new_shortcuts = {}
            for action, var in entries.items():
                val = var.get().strip()
                if not val:
                    messagebox.showerror("Invalid",
                        f"'{action}' shortcut cannot be empty.", parent=win)
                    return
                new_shortcuts[action] = val.upper()
            self.shortcuts = new_shortcuts
            self._apply_shortcuts()
            _save_shortcuts_to_file(self.shortcuts)
            messagebox.showinfo("Saved",
                "✓ Shortcuts saved!\nThey will be remembered after restart.", parent=win)
            win.destroy()

        def _reset():
            if messagebox.askyesno("Reset", "Reset all shortcuts to default?", parent=win):
                self.shortcuts = dict(DEFAULT_SHORTCUTS)
                self._apply_shortcuts()
                _save_shortcuts_to_file(self.shortcuts)
                win.destroy()
                self._open_shortcut_editor()

        ctk.CTkButton(btn_row, text="💾  Save & Remember",
                      height=44, fg_color=GREEN, hover_color="#1B5E20",
                      corner_radius=8, font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="white", command=_save
                      ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btn_row, text="↺  Reset Defaults",
                      height=44, fg_color="#E65100", hover_color="#BF360C",
                      corner_radius=8, font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="white", command=_reset
                      ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    # ── F-key action methods ──────────────────────────────────
    def _fkey_new(self):
        if messagebox.askyesno("New Transaction", "Clear cart and start fresh?", parent=self):
            self.cart.clear(); self._refresh_cart()

    def _fkey_edit(self):
        selected = [i for i, item in enumerate(self.cart) if item.get("selected")]
        if not selected:
            messagebox.showinfo("Edit",
                "Select an item first (checkbox), then press Edit.", parent=self)
            return
        idx  = selected[0]; item = self.cart[idx]
        win  = ctk.CTkToplevel(self)
        win.title("Edit Quantity"); win.geometry("300x160")
        win.configure(fg_color="#F5F5F5"); win.grab_set(); win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"300x160+{(sw-300)//2}+{(sh-160)//2}")
        ctk.CTkLabel(win, text=f"Edit: {item['name']}",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="#1A1A2E").pack(pady=(16, 4))
        ctk.CTkLabel(win, text="Enter new quantity:",
                     font=ctk.CTkFont(size=11), text_color="#546E7A").pack()
        qty_var = ctk.StringVar(value=str(item["qty"]))
        ctk.CTkEntry(win, textvariable=qty_var, width=100, height=34,
                     font=ctk.CTkFont(size=14), text_color="#1A1A2E",
                     fg_color="#BBDEFB", border_width=0, justify="center").pack(pady=8)
        def _apply():
            try:
                nq = int(qty_var.get())
                if nq <= 0: self.cart.pop(idx)
                else:       self.cart[idx]["qty"] = nq
                self._refresh_cart(); win.destroy()
            except ValueError:
                messagebox.showerror("Invalid", "Enter a valid number.", parent=win)
        ctk.CTkButton(win, text="Apply", height=34,
                      fg_color=HEADER_CLR, hover_color="#0D47A1",
                      text_color="white", font=ctk.CTkFont(size=12, weight="bold"),
                      command=_apply).pack(fill="x", padx=20)

    # ════════════════════════════════════════════════════════
    #  F5 — REAL REFRESH (re-fetch products + sync offline)
    # ════════════════════════════════════════════════════════
    def _fkey_refresh(self):
        self.status_lbl.configure(text="🔄 Refreshing...")
        def _do():
            try:
                # Sync any pending offline transactions first
                synced = db.sync_pending_transactions()
                # Re-fetch products (updates SQLite cache from Firestore if online)
                db.get_all_products(store="canteen")
                msg = "✅ Refreshed!"
                if synced > 0:
                    msg += f"  ({synced} offline txn(s) synced)"
            except Exception as e:
                msg = f"⚠ Refresh error: {e}"
            self.after(0, lambda: self.status_lbl.configure(text=msg))
            # Clear the message after 3 seconds
            self.after(3000, lambda: self.status_lbl.configure(
                text=f"{sum(i['qty'] for i in self.cart)} item(s) · {len(self.cart)} product(s)"))
        import threading
        threading.Thread(target=_do, daemon=True).start()

    # ════════════════════════════════════════════════════════
    #  F10 — LAST TRANSACTION VIEWER
    # ════════════════════════════════════════════════════════
    def _fkey_last_transaction(self):
        """Show the most recent 1 transaction in a popup."""
        try:
            rows = db.get_all_transactions(store="canteen")
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self); return

        if not rows:
            messagebox.showinfo("Last Transaction", "No transactions yet.", parent=self)
            return

        r    = rows[0]   # newest first
        vals = list(r) + [""] * 11
        txn_id, dt, total, method = vals[0], vals[1], vals[2], vals[3]
        cash, change, cname, dept = vals[4], vals[5], vals[6], vals[7]

        items = db.get_transaction_items(txn_id)

        win = ctk.CTkToplevel(self)
        win.overrideredirect(True)
        win.configure(fg_color="#111111")
        win.grab_set(); win.resizable(False, False)
        W, H = 480, 420
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        inner = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=14)
        inner.pack(fill="both", expand=True, padx=2, pady=2)

        hdr = ctk.CTkFrame(inner, fg_color=HEADER_CLR, height=52, corner_radius=10)
        hdr.pack(fill="x", padx=4, pady=(4, 0)); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="🕐  Last Transaction",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="white").place(x=14, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="✕", width=32, height=32,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13), corner_radius=16,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        body = ctk.CTkScrollableFrame(inner, fg_color="#FFFFFF",
                                      scrollbar_button_color=BTN_QTY, corner_radius=0)
        body.pack(fill="both", expand=True, padx=8, pady=6)

        def info_row(label, value, val_color="#1A1A2E"):
            f = ctk.CTkFrame(body, fg_color="#F5F7FA", corner_radius=6, height=34)
            f.pack(fill="x", pady=2); f.pack_propagate(False)
            ctk.CTkLabel(f, text=label, width=110, anchor="w",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#546E7A").place(x=10, rely=0.5, anchor="w")
            ctk.CTkLabel(f, text=str(value), anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=val_color).place(x=120, rely=0.5, anchor="w")

        try:
            dt_str = datetime.strptime(str(dt), "%Y-%m-%d %H:%M:%S").strftime("%b %d, %Y  %I:%M %p")
        except Exception:
            dt_str = str(dt)

        info_row("TXN ID",    txn_id)
        info_row("Date/Time", dt_str)
        info_row("Total",     f"₱{float(total):.2f}", HEADER_CLR)
        info_row("Method",    method)
        if cname: info_row("Customer", cname)
        if dept:  info_row("Dept",     dept)
        if float(cash) > 0:
            info_row("Cash",   f"₱{float(cash):.2f}")
            info_row("Change", f"₱{float(change):.2f}", GREEN)

        ctk.CTkLabel(body, text="ITEMS SOLD",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color="#546E7A").pack(anchor="w", padx=4, pady=(8, 2))

        if items:
            for iname, icat, iprice, iqty in items:
                ir = ctk.CTkFrame(body, fg_color="#EEF4FF", corner_radius=6, height=30)
                ir.pack(fill="x", pady=1); ir.pack_propagate(False)
                ctk.CTkLabel(ir, text=f"  {iname}",
                             font=ctk.CTkFont(size=11), text_color="#1A1A2E",
                             anchor="w").place(x=0, rely=0.5, anchor="w")
                ctk.CTkLabel(ir, text=f"x{iqty}  ₱{iprice * iqty:.2f}",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=HEADER_CLR).place(relx=0.97, rely=0.5, anchor="e")
        else:
            ctk.CTkLabel(body, text="No item details found.",
                         font=ctk.CTkFont(size=11), text_color="#546E7A"
                         ).pack(anchor="w", padx=4)

        ctk.CTkButton(inner, text="Close",
                      height=38, fg_color=BTN_QTY, hover_color="#0D47A1",
                      corner_radius=8, font=ctk.CTkFont(size=13, weight="bold"),
                      text_color="white", command=win.destroy
                      ).pack(fill="x", padx=16, pady=(4, 10))

        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<F10>",    lambda e: win.destroy())


    # ════════════════════════════════════════════════════════
    #  F11 — MOBILE ORDERS NOTIFICATION POPUP
    # ════════════════════════════════════════════════════════
    def _fkey_mobile_orders(self):
        """F11 — Show pending mobile orders from Coop Members app."""
        win = ctk.CTkToplevel(self)
        win.title("📱 Mobile Orders")
        win.configure(fg_color="#F5F5F5")
        win.grab_set()
        win.resizable(False, False)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        W, H = 640, 700
        win.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        # ── Header ──
        hdr = ctk.CTkFrame(win, fg_color=HEADER_CLR, height=54, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="📱  Mobile Orders — Pending",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="white").place(x=16, rely=0.5, anchor="w")
        ctk.CTkButton(hdr, text="🔄", width=36, height=36,
                      fg_color="transparent", hover_color="#0D47A1",
                      font=ctk.CTkFont(size=16), text_color="white",
                      command=lambda: _reload()).place(relx=0.88, rely=0.5, anchor="e")
        ctk.CTkButton(hdr, text="✕", width=36, height=36,
                      fg_color="#8B0000", hover_color="#600000",
                      font=ctk.CTkFont(size=13, weight="bold"), corner_radius=18,
                      command=win.destroy).place(relx=0.97, rely=0.5, anchor="e")

        # ── Scrollable orders area ──
        scroll = ctk.CTkScrollableFrame(win, fg_color="#F0F4F8",
                                        scrollbar_button_color=HEADER_CLR,
                                        corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)
        scroll.columnconfigure(0, weight=1)

        loading_lbl = ctk.CTkLabel(scroll, text="⏳  Loading orders...",
                                    font=ctk.CTkFont(size=14), text_color="#546E7A")
        loading_lbl.pack(pady=60)

        STATUS_COLORS = {"Pending": "#F57F17", "Approved": "#1565C0",
                         "Completed": "#2E7D32", "Cancelled": "#C62828"}

        def _reload():
            for w in scroll.winfo_children(): w.destroy()
            lbl = ctk.CTkLabel(scroll, text="⏳  Loading...",
                               font=ctk.CTkFont(size=14), text_color="#546E7A")
            lbl.pack(pady=60)

            def _fetch():
                try:
                    results = list(db._query("mobile_orders",
                                             filters=[["status","EQUAL","Pending"],
                                                      ["store","EQUAL","canteen"]]))
                    orders = []
                    for r in results:
                        d = db._parse_doc(r)
                        d["doc_id"] = r.get("document",{}).get("name","").split("/")[-1]
                        orders.append(d)
                    orders.sort(key=lambda x: str(x.get("datetime","")), reverse=True)
                    win.after(0, lambda o=orders: _render(o))
                except Exception as e:
                    win.after(0, lambda: lbl.configure(text=f"❌ Error: {e}"))

            threading.Thread(target=_fetch, daemon=True).start()

        def _render(orders):
            for w in scroll.winfo_children(): w.destroy()
            if not orders:
                ctk.CTkLabel(scroll, text="✅  No pending orders!",
                             font=ctk.CTkFont(size=15, weight="bold"),
                             text_color="#2E7D32").pack(pady=80)
                return

            for order in orders:
                card = ctk.CTkFrame(scroll, fg_color="#FFFFFF", corner_radius=10,
                                    border_width=1, border_color="#E0E0E0")
                card.pack(fill="x", pady=(0,8), padx=12)

                order_id  = str(order.get("order_id","—"))
                member    = str(order.get("member_name","Unknown"))
                dept      = str(order.get("department","—"))
                total     = 0.0
                try: total = float(order.get("total",0) or 0)
                except: pass
                date      = str(order.get("date_display",""))
                doc_id    = str(order.get("doc_id",""))
                items     = order.get("items") or []
                if not isinstance(items, list): items = []

                # Card header
                ch = ctk.CTkFrame(card, fg_color="#F8F9FA", corner_radius=8)
                ch.pack(fill="x", padx=10, pady=(10,0))
                ctk.CTkLabel(ch, text=f"🧾  {order_id}  •  {member}",
                             font=ctk.CTkFont(size=12, weight="bold"),
                             text_color="#1A1A2E").pack(side="left", padx=12, pady=8)
                ctk.CTkLabel(ch, text="  Pending  ",
                             font=ctk.CTkFont(size=10, weight="bold"),
                             fg_color="#F57F17", text_color="white",
                             corner_radius=6).pack(side="right", padx=12, pady=8)

                ctk.CTkLabel(card, text=f"{dept}  •  {date}",
                             font=ctk.CTkFont(size=10), text_color="#546E7A"
                             ).pack(anchor="w", padx=14)

                # Items
                for item in items:
                    if not isinstance(item, dict): continue
                    iname = str(item.get("name",""))
                    iqty  = 1
                    try: iqty = int(item.get("quantity",1) or 1)
                    except: pass
                    iprice = 0.0
                    try: iprice = float(item.get("price",0) or 0)
                    except: pass
                    inote = str(item.get("note","") or "")
                    isub  = iprice * iqty
                    txt   = f"  • {iname}  x{iqty}  ₱{iprice:.2f} = ₱{isub:.2f}"
                    if inote: txt += f"   📝 {inote}"
                    ctk.CTkLabel(card, text=txt, font=ctk.CTkFont(size=11),
                                 text_color="#1A1A2E", anchor="w"
                                 ).pack(anchor="w", padx=14, pady=1)

                # Total
                ctk.CTkFrame(card, fg_color="#E0E0E0", height=1
                             ).pack(fill="x", padx=14, pady=(6,4))
                tot_row = ctk.CTkFrame(card, fg_color="transparent")
                tot_row.pack(fill="x", padx=14, pady=(0,6))
                ctk.CTkLabel(tot_row, text="TOTAL",
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color="#546E7A").pack(side="left")
                ctk.CTkLabel(tot_row, text=f"₱{total:.2f}",
                             font=ctk.CTkFont(size=16, weight="bold"),
                             text_color=HEADER_CLR).pack(side="right")

                # Note to member
                note_f = ctk.CTkFrame(card, fg_color="#F8F9FA", corner_radius=6)
                note_f.pack(fill="x", padx=14, pady=(0,4))
                ctk.CTkLabel(note_f, text="Note to member (optional):",
                             font=ctk.CTkFont(size=10), text_color="#546E7A"
                             ).pack(anchor="w", padx=10, pady=(6,2))
                note_var = ctk.StringVar()
                ctk.CTkEntry(note_f, textvariable=note_var,
                             placeholder_text="e.g. Preparing your order...",
                             height=32, font=ctk.CTkFont(size=11)
                             ).pack(fill="x", padx=10, pady=(0,8))

                # Buttons
                btn_r = ctk.CTkFrame(card, fg_color="transparent")
                btn_r.pack(fill="x", padx=14, pady=(0,10))
                ctk.CTkButton(btn_r, text="✓ Accept",
                              width=120, height=36,
                              fg_color="#2E7D32", hover_color="#1B5E20",
                              font=ctk.CTkFont(size=12, weight="bold"),
                              command=lambda did=doc_id, o=order, nv=note_var: _accept(did, o, nv.get(), win)
                              ).pack(side="left", padx=(0,8))
                ctk.CTkButton(btn_r, text="✕ Decline",
                              width=110, height=36,
                              fg_color="#C62828", hover_color="#8B0000",
                              font=ctk.CTkFont(size=12),
                              command=lambda did=doc_id, nv=note_var: _decline(did, nv.get(), win)
                              ).pack(side="left")

        def _accept(doc_id, order, note, parent_win):
            import sqlite3 as _sql
            items = order.get("items") or []
            if not isinstance(items, list): items = []
            def _do():
                try:
                    # Update Firestore status
                    db._update_doc("mobile_orders", doc_id, {
                        "status":       "Approved",
                        "cashier_note": note,
                        "notification": "Your order has been accepted! We are now preparing your items." + (f" Note: {note}" if note else ""),
                    })
                    # Deduct stock
                    conn = _sql.connect(str(offline_db.DB_PATH))
                    cur  = conn.cursor()
                    for item in items:
                        if not isinstance(item, dict): continue
                        barcode = str(item.get("product_id",""))
                        qty = 1
                        try: qty = int(item.get("quantity",1) or 1)
                        except: pass
                        istore = str(item.get("store","cafestore"))
                        if barcode:
                            cur.execute("""UPDATE products_cache
                                SET stock = MAX(0, stock - ?)
                                WHERE barcode = ? AND store = ?""",
                                (qty, barcode, istore))
                    conn.commit(); conn.close()
                    win.after(0, lambda: [
                        messagebox.showinfo("✅ Accepted",
                            "Order accepted! Stock deducted. Member notified.", parent=win),
                        _reload()
                    ])
                except Exception as e:
                    win.after(0, lambda: messagebox.showerror("Error", str(e), parent=win))
            threading.Thread(target=_do, daemon=True).start()

        def _decline(doc_id, note, parent_win):
            reason = note.strip()
            if not reason:
                messagebox.showwarning("Required",
                    "Please enter a reason in the note field before declining.", parent=win)
                return
            def _do():
                try:
                    db._update_doc("mobile_orders", doc_id, {
                        "status":       "Cancelled",
                        "cashier_note": reason,
                        "notification": f"Your order has been declined. Reason: {reason}",
                    })
                    win.after(0, lambda: [
                        messagebox.showinfo("Declined", "Order declined.", parent=win),
                        _reload()
                    ])
                except Exception as e:
                    win.after(0, lambda: messagebox.showerror("Error", str(e), parent=win))
            threading.Thread(target=_do, daemon=True).start()

        _reload()
        win.bind("<Escape>", lambda e: win.destroy())


    # ════════════════════════════════════════════════════════
    #  CTRL+F11 — ADD QTY +1 TO SELECTED (OR FIRST) ITEM
    # ════════════════════════════════════════════════════════
    def _fkey_add_qty(self):
        if not self.cart:
            self.status_lbl.configure(text="⚠  Cart is empty — nothing to add qty to.")
            return
        selected = [i for i, item in enumerate(self.cart) if item.get("selected")]
        idx = selected[0] if selected else 0
        self._change_qty(idx, 1)

    # ════════════════════════════════════════════════════════════
    #  ☁️ BACKUP & SYNC
    # ════════════════════════════════════════════════════════════
    def _toggle_backup_popup(self):
        if self._backup_panel_open:
            if hasattr(self, "_backup_win") and self._backup_win.winfo_exists():
                self._backup_win.destroy()
            self._backup_panel_open = False
        else:
            self._backup_panel_open = True
            self._build_backup_popup()

    def _build_backup_popup(self):
        win = ctk.CTkToplevel(self)
        win.title("☁️ Backup & Sync")
        win.configure(fg_color="#F5F7FA")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        win.update_idletasks()
        sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
        win.geometry(f"280x420+{sw-295}+{sh-470}")
        self._backup_win = win
        win.protocol("WM_DELETE_WINDOW", lambda: [
            win.destroy(), setattr(self, "_backup_panel_open", False)])
        self._fill_backup_popup(win)

    def _fill_backup_popup(self, win):
        import json, os, sqlite3
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
                print(f"Settings save error: {e}")
        bk = _load()
        hdr = ctk.CTkFrame(win, fg_color="#1565C0", height=46, corner_radius=0)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="☁️  Backup & Sync",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").place(x=12, rely=0.5, anchor="w")
        online = db.has_internet()
        st_f = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=8,
                            border_width=1, border_color="#BBDEFB")
        st_f.pack(fill="x", padx=12, pady=(12,4))
        ctk.CTkLabel(st_f, text="🌐 Online" if online else "📴 Offline",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="#2E7D32" if online else "#C62828"
                     ).pack(side="left", padx=10, pady=8)
        last_lbl = ctk.CTkLabel(st_f, text=f"Last: {bk.get('last_backup','Never')}",
                                 font=ctk.CTkFont(size=9), text_color="#546E7A")
        last_lbl.pack(side="right", padx=8)
        btn_kw = dict(height=40, corner_radius=8,
                      font=ctk.CTkFont(size=12, weight="bold"), text_color="white")
        def _run_backup():
            conn = sqlite3.connect(str(offline_db.DB_PATH))
            conn.row_factory = sqlite3.Row; cur = conn.cursor()
            cur.execute("SELECT * FROM transactions_local")
            for row in cur.fetchall():
                d = dict(row); txn_id = d.get("txn_id","")
                try: db._set_doc("transactions", txn_id, {"txn_id":txn_id,"datetime":d.get("dt",""),"total":float(d.get("total",0)),"payment_method":d.get("method",""),"cash_given":float(d.get("cash",0)),"change_given":float(d.get("change_amount",0)),"customer_name":d.get("customer_name",""),"department":d.get("department",""),"buyer_type":d.get("buyer_type",""),"store":d.get("store","cafestore"),"item_count":0})
                except Exception as e: print(f"Backup txn: {e}")
            cur.execute("SELECT * FROM transaction_items_local")
            for row in cur.fetchall():
                d = dict(row); doc_id = f"{d.get('txn_id','')}_{d.get('id','')}"
                try: db._set_doc("transaction_items", doc_id, {"txn_id":d.get("txn_id",""),"barcode":d.get("barcode",""),"name":d.get("name",""),"category":d.get("category",""),"price":float(d.get("price",0)),"qty":int(d.get("qty",0))})
                except Exception as e: print(f"Backup item: {e}")
            cur.execute("SELECT * FROM products_cache")
            for row in cur.fetchall():
                d = dict(row); store=d.get("store","cafestore"); bc=d.get("barcode","")
                try: db._set_doc("products", f"{store}_{bc}", {"barcode":bc,"name":d.get("name",""),"category":d.get("category",""),"price":float(d.get("price",0)),"stock":int(d.get("stock",0)),"store":store,"is_daily":int(d.get("is_daily",0)),"date_added":d.get("date_added",""),"image_url":d.get("image_url","") or ""})
                except Exception as e: print(f"Backup product: {e}")
            conn.close()
        def _run_restore():
            for store in ["cafestore","canteen"]:
                offline_db.save_products_cache(db.get_all_products(store=store), store)
        def _do_backup():
            if not db.has_internet():
                messagebox.showwarning("Offline","No internet.", parent=win); return
            bkp_btn.configure(text="⏳ Backing up...", state="disabled"); win.update()
            def _bg():
                try:
                    _run_backup(); dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    bk["last_backup"]=dt; _save(bk)
                    self.after(0, lambda: [bkp_btn.configure(text="☁️  Backup Database", state="normal"), last_lbl.configure(text=f"Last: {dt}"), messagebox.showinfo("✅ Done", f"Backup complete!\n{dt}", parent=win)])
                except Exception as e:
                    self.after(0, lambda: [bkp_btn.configure(text="☁️  Backup Database", state="normal"), messagebox.showerror("❌ Error", str(e), parent=win)])
            threading.Thread(target=_bg, daemon=True).start()
        def _do_restore():
            if not db.has_internet():
                messagebox.showwarning("Offline","No internet.", parent=win); return
            if not messagebox.askyesno("Restore","⚠️ Replace local data?\n\nContinue?", parent=win): return
            rst_btn.configure(text="⏳ Restoring...", state="disabled"); win.update()
            def _bg():
                try:
                    _run_restore()
                    self.after(0, lambda: [rst_btn.configure(text="🔄  Restore Database", state="normal"), messagebox.showinfo("✅ Restored","Restored!",parent=win)])
                except Exception as e:
                    self.after(0, lambda: [rst_btn.configure(text="🔄  Restore Database", state="normal"), messagebox.showerror("❌ Error",str(e),parent=win)])
            threading.Thread(target=_bg, daemon=True).start()
        bkp_btn = ctk.CTkButton(win, text="☁️  Backup Database", fg_color="#1565C0", hover_color="#1976D2", command=_do_backup, **btn_kw)
        bkp_btn.pack(fill="x", padx=12, pady=(0,6))
        rst_btn = ctk.CTkButton(win, text="🔄  Restore Database", fg_color="#546E7A", hover_color="#37474F", command=_do_restore, **btn_kw)
        rst_btn.pack(fill="x", padx=12, pady=(0,6))
        ctk.CTkFrame(win, fg_color="#E0E0E0", height=1).pack(fill="x", padx=12, pady=6)
        try:
            conn = sqlite3.connect(str(offline_db.DB_PATH)); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM transactions_local"); t = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM products_cache"); p = cur.fetchone()[0]
            conn.close()
            st2 = ctk.CTkFrame(win, fg_color="#FFFFFF", corner_radius=8, border_width=1, border_color="#E0E0E0")
            st2.pack(fill="x", padx=12)
            ctk.CTkLabel(st2, text="🗄️ Local Database", font=ctk.CTkFont(size=11, weight="bold"), text_color="#546E7A").pack(anchor="w", padx=12, pady=(8,2))
            ctk.CTkLabel(st2, text=f"  Transactions: {t}", font=ctk.CTkFont(size=11), text_color="#546E7A").pack(anchor="w", padx=12)
            ctk.CTkLabel(st2, text=f"  Products: {p}", font=ctk.CTkFont(size=11), text_color="#546E7A").pack(anchor="w", padx=12, pady=(0,8))
        except Exception as e:
            ctk.CTkLabel(win, text=f"DB error: {e}", font=ctk.CTkFont(size=9), text_color="#C62828").pack(padx=12)


    def _logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to logout?", parent=self):
            self.destroy()
            self.login_window.deiconify()


if __name__ == "__main__":
    import splash

    def _after_splash():
        root = ctk.CTk()
        root.withdraw()
        CanteenDashboard(root, "canteen").mainloop()

    splash.show_splash(on_done=_after_splash, duration=2.5)