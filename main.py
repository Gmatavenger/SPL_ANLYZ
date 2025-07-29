import tkinter as tk
# from splunk_automator.gui import SplunkAutomatorApp
try:
    from splunk_automator.gui import SplunkAutomatorApp
except ImportError:
    print("Failed to import SplunkAutomatorApp from gui.")
    raise


def main():
    root = tk.Tk()
    root.minsize(700, 500)
    app = SplunkAutomatorApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: root.quit())
    root.mainloop()

if __name__ == "__main__":
    main()