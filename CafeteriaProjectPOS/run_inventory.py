import customtkinter as ctk
from Store_Inventory import InventoryApp

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

if __name__ == "__main__":
    app = InventoryApp()
    app.mainloop()
