import tkinter as tk
from .gui import SplunkAutomatorApp

def main():
    root = tk.Tk()
    root.minsize(700, 500)
    app = SplunkAutomatorApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: root.quit())
    root.mainloop()

if __name__ == "__main__":
    main()