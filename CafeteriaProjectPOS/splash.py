"""
splash.py — Splash screen for StockFlow POS System
Simple clean splash: logo + StockFlow name only, plain white background
"""
import customtkinter as ctk
import os

BG_CLR     = "#FFFFFF"
HEADER_CLR = "#1565C0"


class SplashScreen(ctk.CTkToplevel):
    def __init__(self, parent, on_done, duration=2.5):
        super().__init__(parent)
        self.on_done  = on_done
        self.duration = duration

        self.overrideredirect(True)
        self.configure(fg_color=BG_CLR)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        W, H = 860, 540
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

        self._build_ui()
        self.update()
        self._start_loading()

    def _build_ui(self):
        main = ctk.CTkFrame(self, fg_color=BG_CLR, corner_radius=0)
        main.pack(fill="both", expand=True)

        # ── Logo ──
        logo_frame = ctk.CTkFrame(main, fg_color="#EEF2FF",
                                   width=160, height=160,
                                   corner_radius=80)
        logo_frame.pack(pady=(100, 20))
        logo_frame.pack_propagate(False)

        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "isufst_logo.png")
        if os.path.exists(logo_path):
            try:
                from PIL import Image
                img = ctk.CTkImage(Image.open(logo_path), size=(120, 120))
                ctk.CTkLabel(logo_frame, image=img, text="",
                             fg_color="transparent").place(relx=0.5, rely=0.5, anchor="center")
            except Exception:
                self._text_logo(logo_frame)
        else:
            self._text_logo(logo_frame)

        # ── StockFlow name ──
        ctk.CTkLabel(main, text="StockFlow",
                     font=ctk.CTkFont(family="Segoe UI", size=48, weight="bold"),
                     text_color=HEADER_CLR).pack(pady=(0, 4))

        # ── Thin loading bar ──
        bar_bg = ctk.CTkFrame(main, fg_color="#E8EAF6",
                               height=5, corner_radius=3, width=340)
        bar_bg.pack(pady=(36, 0))
        bar_bg.pack_propagate(False)

        self._bar_fill = ctk.CTkFrame(bar_bg, fg_color=HEADER_CLR,
                                       height=5, corner_radius=3, width=0)
        self._bar_fill.place(x=0, y=0, relheight=1.0)
        self._bar_bg_w = 340

    def _text_logo(self, frame):
        ctk.CTkLabel(frame, text="SF",
                     font=ctk.CTkFont(family="Segoe UI", size=36, weight="bold"),
                     text_color=HEADER_CLR,
                     fg_color="transparent").place(relx=0.5, rely=0.5, anchor="center")

    def _start_loading(self):
        steps    = 50
        interval = self.duration / steps

        def _animate(step=0):
            if step > steps:
                self.after(200, self._finish)
                return
            pct    = step / steps
            fill_w = int(self._bar_bg_w * pct)
            self._bar_fill.configure(width=max(0, fill_w))
            self.after(int(interval * 1000), lambda: _animate(step + 1))

        _animate()

    def _finish(self):
        self.destroy()
        self.on_done()


def show_splash(on_done, duration=2.5):
    root = ctk.CTk()
    root.withdraw()
    SplashScreen(root, on_done=lambda: [root.destroy(), on_done()],
                 duration=duration)
    root.mainloop()