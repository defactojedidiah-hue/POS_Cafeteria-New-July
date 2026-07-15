import customtkinter as ctk
from store_dashboard import StoreDashboard

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

if __name__ == "__main__":
    app = ctk.CTk()
    app.withdraw()
    StoreDashboard(app, "store").mainloop()