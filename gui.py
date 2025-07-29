import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import asyncio
import threading
from datetime import datetime
import re

from .config import Config
from .logging_setup import logger
from .credentials import load_credentials, save_credentials
from .dashboard import (
    load_dashboards, save_dashboards, get_groups, select_all, deselect_all, refresh_dashboard_list
)
from .time_range import TimeRangeDialog
from .splunk_automation import process_single_dashboard

class SplunkAutomatorApp:
    MAX_CONCURRENT_DASHBOARDS = 3

    def __init__(self, master: tk.Tk):
        self.master = master
        master.title("Splunk Dashboard Automator")
        master.geometry("1200x800")
        self.status_message = tk.StringVar()
        self.session = {
            "username": None,
            "password": None,
            "dashboards": [],
        }

        self._setup_ui()
        self._load_credentials()
        self._load_dashboards()
        logger.info("SplunkAutomatorApp initialized.")

    def _setup_ui(self):
        # Menu
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Manage Credentials", command=self.manage_credentials)
        settings_menu.add_command(label="Export Results", command=self.export_results)
        # Main Frame
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)
        # Controls Frame
        controls_frame = ttk.Frame(main_frame)
        controls_frame.grid(row=0, column=0, sticky="ew", pady=(0,10))
        ttk.Button(controls_frame, text="Add", command=self.add_dashboard).grid(row=0, column=0, padx=5)
        ttk.Button(controls_frame, text="Delete", command=self.delete_dashboard).grid(row=0, column=1, padx=5)
        ttk.Button(controls_frame, text="Select All", command=self.select_all_dashboards).grid(row=0, column=2, padx=5)
        ttk.Button(controls_frame, text="Deselect All", command=self.deselect_all_dashboards).grid(row=0, column=3, padx=5)
        ttk.Button(controls_frame, text="Capture Screenshots", command=self.capture_screenshots_thread).grid(row=0, column=4, padx=20)
        ttk.Button(controls_frame, text="Analyze Dashboards", command=self.analyze_dashboards_thread).grid(row=0, column=5, padx=5)
        # Group Filter
        ttk.Label(controls_frame, text="Filter by Group:").grid(row=0, column=6, padx=(20,5))
        self.group_filter_var = tk.StringVar(value="All")
        self.group_filter = ttk.Combobox(controls_frame, textvariable=self.group_filter_var, state="readonly", width=15)
        self.group_filter.grid(row=0, column=7, padx=5)
        self.group_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh_dashboard_list())
        # Treeview for dashboards
        tree_frame = ttk.LabelFrame(main_frame, text="Dashboards")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        main_frame.grid_rowconfigure(1, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        self.treeview = ttk.Treeview(tree_frame, columns=("Sel","Name","URL","Group","Status"), show="headings", selectmode="extended")
        for col, width in zip(("Sel","Name","URL","Group","Status"), (40,250,400,100,300)):
            self.treeview.heading(col, text=col)
            self.treeview.column(col, width=width)
        tree_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.treeview.yview)
        self.treeview.configure(yscrollcommand=tree_scrollbar.set)
        tree_scrollbar.grid(row=0, column=1, sticky="ns")
        self.treeview.grid(row=0, column=0, sticky="nsew")
        self.treeview.bind("<Button-1>", self.toggle_selection)
        # Progress Bar and Status
        analysis_frame = ttk.Frame(main_frame)
        analysis_frame.grid(row=2, column=0, sticky="ew", pady=10)
        self.progress_bar = ttk.Progressbar(analysis_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, expand=True, padx=20, side=tk.LEFT)
        status_frame = ttk.Frame(self.master)
        status_frame.grid(row=1, column=0, sticky="ew")
        ttk.Label(status_frame, textvariable=self.status_message, anchor="w").pack(fill=tk.X)
        for i in range(3): main_frame.grid_rowconfigure(i, weight=0 if i!=1 else 1)
        main_frame.grid_columnconfigure(0, weight=1)

    def _load_credentials(self):
        username, password = load_credentials()
        self.session['username'] = username
        self.session['password'] = password

    def _load_dashboards(self):
        self.session['dashboards'] = load_dashboards()
        self.refresh_dashboard_list()
        self.update_group_filter()

    # --- Dashboard Management ---
    def add_dashboard(self):
        dlg = tk.Toplevel(self.master)
        dlg.title("Add Dashboard")
        dlg.transient(self.master)
        dlg.grab_set()
        frm = ttk.Frame(dlg, padding=15)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Dashboard name:").grid(row=0, column=0, sticky="e", pady=5)
        name_var = tk.StringVar()
        ttk.Entry(frm, textvariable=name_var, width=40).grid(row=0, column=1, pady=5)
        ttk.Label(frm, text="Dashboard URL:").grid(row=1, column=0, sticky="e", pady=5)
        url_var = tk.StringVar()
        ttk.Entry(frm, textvariable=url_var, width=40).grid(row=1, column=1, pady=5)
        ttk.Label(frm, text="Group name:").grid(row=2, column=0, sticky="e", pady=5)
        existing_groups = get_groups(self.session['dashboards'])
        group_var = tk.StringVar()
        group_combo = ttk.Combobox(frm, textvariable=group_var, values=existing_groups, width=37)
        group_combo.grid(row=2, column=1, pady=5)
        group_combo.set(existing_groups[0] if existing_groups else "Default")
        def on_ok():
            name = name_var.get().strip()
            url = url_var.get().strip()
            group = group_var.get().strip() or "Default"
            if not name:
                messagebox.showerror("Input Error", "Dashboard name cannot be empty.", parent=dlg)
                return
            if not url or not (url.startswith("http://") or url.startswith("https://")):
                messagebox.showerror("Invalid URL", "URL must start with http or https.", parent=dlg)
                return
            name_lower = name.lower()
            if any(d["name"].strip().lower() == name_lower for d in self.session["dashboards"]):
                messagebox.showerror("Duplicate", "Dashboard name already exists.", parent=dlg)
                return
            self.session['dashboards'].append({"name": name, "url": url, "group": group, "selected": True})
            save_dashboards(self.session['dashboards'])
            self.refresh_dashboard_list()
            self.update_group_filter()
            dlg.destroy()
        ttk.Button(frm, text="Add", command=on_ok).grid(row=3, column=0, columnspan=2, pady=10)
        dlg.wait_window()

    def delete_dashboard(self):
        selection = self.treeview.selection()
        if not selection:
            messagebox.showwarning("Selection Error", "Please select a dashboard to delete.")
            return
        if messagebox.askyesno("Confirm Delete", "Delete selected dashboards?"):
            indices = sorted([int(iid) for iid in selection], reverse=True)
            for index in indices:
                if 0 <= index < len(self.session['dashboards']):
                    del self.session['dashboards'][index]
            save_dashboards(self.session['dashboards'])
            self.refresh_dashboard_list()
            self.update_group_filter()

    def select_all_dashboards(self):
        select_all(self.session['dashboards'])
        self.refresh_dashboard_list()

    def deselect_all_dashboards(self):
        deselect_all(self.session['dashboards'])
        self.refresh_dashboard_list()

    def toggle_selection(self, event):
        item_id = self.treeview.identify_row(event.y)
        if not item_id or self.treeview.identify_column(event.x) != "#1":
            return
        try:
            db = self.session['dashboards'][int(item_id)]
            db["selected"] = not db.get("selected", False)
            self.refresh_dashboard_list()
        except (IndexError, ValueError):
            pass

    def refresh_dashboard_list(self):
        refresh_dashboard_list(self.treeview, self.session['dashboards'], self.group_filter_var)

    def update_group_filter(self):
        groups = get_groups(self.session['dashboards'])
        self.group_filter['values'] = groups
        if self.group_filter_var.get() not in groups:
            self.group_filter_var.set("All")

    # --- Credentials ---
    def manage_credentials(self):
        dlg = tk.Toplevel(self.master)
        dlg.title("Manage Credentials")
        dlg.transient(self.master)
        dlg.grab_set()
        frm = ttk.Frame(dlg, padding=15)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text="Splunk Username:").grid(row=0, column=0, sticky="e", pady=5)
        user_var = tk.StringVar(value=self.session.get("username", ""))
        user_entry = ttk.Entry(frm, textvariable=user_var, width=30)
        user_entry.grid(row=0, column=1, pady=5)
        user_entry.focus_set()
        ttk.Label(frm, text="Splunk Password:").grid(row=1, column=0, sticky="e", pady=5)
        pass_var = tk.StringVar(value=self.session.get("password", ""))
        pass_entry = ttk.Entry(frm, textvariable=pass_var, show="*", width=30)
        pass_entry.grid(row=1, column=1, pady=5)
        show_pw_var = tk.BooleanVar()
        def toggle_pw():
            pass_entry.config(show="" if show_pw_var.get() else "*")
        show_pw = ttk.Checkbutton(frm, text="Show", variable=show_pw_var, command=toggle_pw)
        show_pw.grid(row=1, column=2, padx=5)
        def save_and_close():
            username = user_var.get().strip()
            password = pass_var.get().strip()
            if not username or not password:
                messagebox.showerror("Input Error", "Both username and password are required.", parent=dlg)
                return
            self.session["username"] = username
            self.session["password"] = password
            save_credentials(username, password)
            messagebox.showinfo("Credentials Saved", "Credentials have been updated for this session.", parent=dlg)
            dlg.destroy()
        ttk.Button(frm, text="Save", command=save_and_close).grid(row=2, column=0, columnspan=3, pady=10)
        dlg.wait_window()

    # --- Export ---
    def export_results(self):
        if not self.session['dashboards']:
            messagebox.showinfo("Nothing to export", "No dashboards loaded.")
            return
        file = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if not file:
            return
        import csv
        with open(file, "w", newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Name", "URL", "Group", "Status"])
            for db in self.session['dashboards']:
                writer.writerow([db['name'], db['url'], db.get('group',"Default"), db.get('status',"")])
        self.status_message.set(f"Exported results to {file}")

    # --- Screenshot and Analysis routines ---
    def capture_screenshots_thread(self):
        selected_dbs = [db for db in self.session['dashboards'] if db.get('selected')]
        if not selected_dbs:
            messagebox.showwarning("No Selection", "Please select dashboards.")
            return
        dialog = TimeRangeDialog(self.master)
        self.master.wait_window(dialog)
        if not dialog.result:
            return
        start_dt = dialog.result['start']
        end_dt = dialog.result['end']
        username = self.session['username']
        password = self.session['password']
        if not username or not password:
            messagebox.showerror("Credentials Error", "Splunk credentials are not set.")
            return
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = len(selected_dbs)
        def run():
            asyncio.run(self._capture_screenshots_async(selected_dbs, start_dt, end_dt, username, password))
        threading.Thread(target=run, daemon=True).start()

    async def _capture_screenshots_async(self, dashboards, start_dt, end_dt, username, password):
        from playwright.async_api import async_playwright
        semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_DASHBOARDS)
        async with async_playwright() as p:
            async def wrapper(db, idx):
                async with semaphore:
                    try:
                        await process_single_dashboard(p, db, start_dt, end_dt, username, password, capture_only=True)
                        self.treeview.set(str(idx), column="Status", value="Screenshot Success")
                    except Exception as e:
                        logger.error(f"Screenshot failed: {e}")
                        self.treeview.set(str(idx), column="Status", value=f"Failed: {e}")
                    self.progress_bar['value'] += 1
            tasks = [wrapper(db, idx) for idx, db in enumerate(dashboards)]
            await asyncio.gather(*tasks)
        self.status_message.set("Screenshot capture run has finished.")

    def analyze_dashboards_thread(self):
        # Similar to capture_screenshots_thread, but call process_single_dashboard with capture_only=False
        # and (optionally) add any further analysis logic.
        pass

# --- End of SplunkAutomatorApp class ---
