"""
login.py — Unified Login for StockFlow POS System
Run this file directly OR used by individual system files.

Credentials:
  admin      → Admin Dashboard
  store      → Store Inventory
  karinderia → Karen Inventory
"""
import customtkinter as ctk
import os, json

HEADER_CLR = "#1565C0"
ACCENT_CLR  = "#0D47A1"
WHITE       = "#FFFFFF"
BG_CLR      = "#EEF2FF"

_SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "backup_settings.json")

def _get_admin_password():
    try:
        with open(_SETTINGS_FILE) as f:
            return json.load(f).get("password", "admin123")
    except Exception:
        return "admin123"

_USERS = {
    "admin":      {"pw": _get_admin_password, "role": "admin"},
    "cafestore":  {"pw": lambda: "store123",   "role": "cafestore"},
    "canteen":    {"pw": lambda: "canteen123", "role": "canteen"},
}


class LoginWindow(ctk.CTk):
    def __init__(self, allowed_roles=None, on_success=None):
        super().__init__()
        self.allowed_roles = allowed_roles
        self.on_success    = on_success
        self.title("StockFlow — Login")
        self.resizable(False, False)
        self.configure(fg_color=BG_CLR)
        W, H = 1100, 650
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")
        self._build_ui()
        self.after(200, lambda: self._user_entry.focus())
        self.bind("<Return>",   lambda e: self._login())
        self.bind("<KP_Enter>", lambda e: self._login())

    def _build_ui(self):
        left = ctk.CTkFrame(self, fg_color=HEADER_CLR, width=420, corner_radius=0)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        circle = ctk.CTkFrame(left, fg_color=ACCENT_CLR,
                               width=260, height=260, corner_radius=130)
        circle.place(relx=0.5, rely=0.35, anchor="center")
        circle.pack_propagate(False)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "isufst_logo.png")
        if os.path.exists(logo_path):
            try:
                from PIL import Image
                img = ctk.CTkImage(Image.open(logo_path), size=(160, 160))
                ctk.CTkLabel(circle, image=img, text="", fg_color="transparent"
                             ).place(relx=0.5, rely=0.5, anchor="center")
            except Exception:
                self._circle_text(circle)
        else:
            self._circle_text(circle)

        ctk.CTkLabel(left, text="StockFlow",
                     font=ctk.CTkFont(family="Segoe UI", size=40, weight="bold"),
                     text_color=WHITE).place(relx=0.5, rely=0.65, anchor="center")
        ctk.CTkLabel(left, text="Intelligent Inventory Monitoring\n& Sales Recording System",
                     font=ctk.CTkFont(family="Segoe UI", size=14),
                     text_color="#90CAF9", justify="center"
                     ).place(relx=0.5, rely=0.76, anchor="center")
        ctk.CTkLabel(left, text="ISUFST \u2013 San Enrique Campus",
                     font=ctk.CTkFont(family="Segoe UI", size=11),
                     text_color="#64B5F6").place(relx=0.5, rely=0.92, anchor="center")

        right = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0)
        right.pack(side="right", fill="both", expand=True)

        ctk.CTkLabel(right, text="Welcome Back!",
                     font=ctk.CTkFont(family="Segoe UI", size=36, weight="bold"),
                     text_color=HEADER_CLR).place(relx=0.5, rely=0.20, anchor="center")
        ctk.CTkLabel(right, text="Please log in to your account.",
                     font=ctk.CTkFont(family="Segoe UI", size=15),
                     text_color="#78909C").place(relx=0.5, rely=0.30, anchor="center")

        uf = ctk.CTkFrame(right, fg_color="#F5F7FA", corner_radius=8,
                           border_width=1, border_color="#BBDEFB", width=380, height=54)
        uf.place(relx=0.5, rely=0.44, anchor="center")
        uf.pack_propagate(False)
        uf_inner = ctk.CTkFrame(uf, fg_color="transparent")
        uf_inner.pack(fill="both", expand=True, padx=12)
        ctk.CTkLabel(uf_inner, text="\U0001f464", font=ctk.CTkFont(size=15),
                     text_color="#90A4AE").pack(side="left", padx=(0,8))
        self._user_var = ctk.StringVar()
        self._user_entry = ctk.CTkEntry(uf_inner, textvariable=self._user_var,
                     placeholder_text="Username", border_width=0, fg_color="transparent",
                     text_color="#1A1A2E", placeholder_text_color="#90A4AE",
                     font=ctk.CTkFont(family="Segoe UI", size=15))
        self._user_entry.pack(side="left", fill="both", expand=True)

        pf = ctk.CTkFrame(right, fg_color="#F5F7FA", corner_radius=8,
                           border_width=1, border_color="#BBDEFB", width=380, height=54)
        pf.place(relx=0.5, rely=0.57, anchor="center")
        pf.pack_propagate(False)
        pf_inner = ctk.CTkFrame(pf, fg_color="transparent")
        pf_inner.pack(fill="both", expand=True, padx=12)
        ctk.CTkLabel(pf_inner, text="\U0001f512", font=ctk.CTkFont(size=15),
                     text_color="#90A4AE").pack(side="left", padx=(0,8))
        self._pw_var = ctk.StringVar()
        self._pw_entry = ctk.CTkEntry(pf_inner, textvariable=self._pw_var,
                     placeholder_text="Password", show="\u25cf",
                     border_width=0, fg_color="transparent",
                     text_color="#1A1A2E", placeholder_text_color="#90A4AE",
                     font=ctk.CTkFont(family="Segoe UI", size=15))
        self._pw_entry.pack(side="left", fill="both", expand=True)
        self._show_pw = False
        eye = ctk.CTkLabel(pf_inner, text="\U0001f441", font=ctk.CTkFont(size=15),
                            text_color="#90A4AE", cursor="hand2")
        eye.pack(side="right", padx=(6,0))
        eye.bind("<Button-1>", self._toggle_pw)

        self._err_lbl = ctk.CTkLabel(right, text="",
                                      font=ctk.CTkFont(family="Segoe UI", size=12),
                                      text_color="#C62828")
        self._err_lbl.place(relx=0.5, rely=0.67, anchor="center")

        ctk.CTkButton(right, text="LOG IN", width=380, height=54,
                      fg_color=HEADER_CLR, hover_color=ACCENT_CLR,
                      text_color=WHITE,
                      font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
                      corner_radius=8, command=self._login
                      ).place(relx=0.5, rely=0.78, anchor="center")

        ctk.CTkLabel(right, text="ISUFST Cafeteria POS  |  v1.0",
                     font=ctk.CTkFont(family="Segoe UI", size=10),
                     text_color="#B0BEC5").place(relx=0.5, rely=0.95, anchor="center")

    def _circle_text(self, frame):
        ctk.CTkLabel(frame, text="CAFETERIA",
                     font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
                     text_color=WHITE,
                     fg_color="transparent").place(relx=0.5, rely=0.5, anchor="center")

    def _toggle_pw(self, e=None):
        self._show_pw = not self._show_pw
        self._pw_entry.configure(show="" if self._show_pw else "\u25cf")

    def _login(self):
        username = self._user_var.get().strip().lower()
        password = self._pw_var.get().strip()
        if not username:
            self._err_lbl.configure(text="\u26a0  Please enter your username."); return
        if not password:
            self._err_lbl.configure(text="\u26a0  Please enter your password."); return
        if username not in _USERS:
            self._err_lbl.configure(text="\u26a0  Invalid username or password.")
            self._pw_var.set(""); self._pw_entry.focus(); return
        info = _USERS[username]
        role = info["role"]
        if self.allowed_roles and role not in self.allowed_roles:
            self._err_lbl.configure(text="\u26a0  Access not allowed for this system.")
            self._pw_var.set(""); self._pw_entry.focus(); return
        if password != info["pw"]():
            self._err_lbl.configure(text="\u26a0  Invalid username or password.")
            self._pw_var.set(""); self._pw_entry.focus(); return
        self._err_lbl.configure(text="")
        self.withdraw()
        if self.on_success:
            self.on_success(username, role, self)
        else:
            _auto_launch(username, role, self)


def _auto_launch(username, role, login_win):
    import importlib, sys
    base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, base)
    if role == "admin":
        mod = importlib.import_module("admin_dashboard")
        mod.AdminDashboard(login_window=login_win).mainloop()
    elif role == "cafestore":
        mod = importlib.import_module("Store_Inventory")
        mod.InventoryApp(login_window=login_win).mainloop()
    elif role == "canteen":
        mod = importlib.import_module("canteen_inventory")
        mod.KarenderiaInventoryApp(login_window=login_win).mainloop()


def require_login(allowed_roles=None, on_success=None):
    """Used by individual system files to show login gate."""
    LoginWindow(allowed_roles=allowed_roles, on_success=on_success).mainloop()


if __name__ == "__main__":
    import splash
    def _after_splash():
        LoginWindow().mainloop()
    splash.show_splash(on_done=_after_splash, duration=3.0)