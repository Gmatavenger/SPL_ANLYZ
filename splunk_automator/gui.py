import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import asyncio
import json
import os
from datetime import datetime, timedelta
from .dashboard import (
    load_dashboards, save_dashboards, select_all, deselect_all,
    refresh_dashboard_list, get_groups
)
from .credentials import save_credentials, load_credentials
from .settings import load_settings, save_settings
from .utils import ensure_dirs, archive_and_clean_tmp, purge_old_archives
from .time_range import TimeRangeDialog
from .splunk_automation import process_single_dashboard
from .logging_setup import logger
from .config import Config
import webbrowser
from playwright.async_api import async_playwright

class SplunkAutomatorApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Splunk Dashboard Automator")
        self.status_message = tk.StringVar(value="Ready")
        self.progress_var = tk.IntVar()
        self.progress_max = tk.IntVar(value=100)
        
        # Session data
        self.session = {
            "dashboards": [],
            "username": None,
            "password": None
        }
        
        # Threading control
        self.cancel_flag = threading.Event()
        self.current_thread = None
        
        # Schedule data
        self.schedule_config = None
        self.schedule_thread = None
        self.schedule_active = False
        
        # Group filter
        self.group_filter_var = tk.StringVar(value="All")
        
        # Initialize
        ensure_dirs()
        self._setup_ui()
        self._load_initial_data()
        self.start_schedule_if_exists()

    def _setup_ui(self):
        """Set up all main GUI widgets and layout."""
        # Create menu bar
        self._create_menu_bar()
        
        # Main container with padding
        main_container = ttk.Frame(self.master, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Toolbar frame
        toolbar_frame = ttk.Frame(main_container)
        toolbar_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Left toolbar buttons
        left_toolbar = ttk.Frame(toolbar_frame)
        left_toolbar.pack(side=tk.LEFT)
        
        ttk.Button(left_toolbar, text="Add Dashboard", command=self.add_dashboard).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(left_toolbar, text="Delete Selected", command=self.delete_dashboard).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(left_toolbar, text="Select All", command=self.select_all_dashboards).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(left_toolbar, text="Deselect All", command=self.deselect_all_dashboards).pack(side=tk.LEFT, padx=(0, 5))
        
        # Group filter
        ttk.Label(left_toolbar, text="Group:").pack(side=tk.LEFT, padx=(10, 5))
        self.group_filter = ttk.Combobox(left_toolbar, textvariable=self.group_filter_var, 
                                        state="readonly", width=15)
        self.group_filter.pack(side=tk.LEFT, padx=(0, 5))
        self.group_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh_dashboard_list())
        
        # Right toolbar buttons  
        right_toolbar = ttk.Frame(toolbar_frame)
        right_toolbar.pack(side=tk.RIGHT)
        
        ttk.Button(right_toolbar, text="Run Analysis", command=self.run_analysis_thread).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(right_toolbar, text="Screenshots Only", command=self.capture_screenshots_thread).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(right_toolbar, text="Export Results", command=self.export_results).pack(side=tk.LEFT)
        
        # Dashboard list frame
        list_frame = ttk.LabelFrame(main_container, text="Dashboards", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Treeview with scrollbars
        tree_container = ttk.Frame(list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        self.treeview = ttk.Treeview(tree_container, 
                                    columns=("Selected", "Name", "URL", "Group", "Status"), 
                                    show="headings", height=12)
        
        # Configure columns
        self.treeview.heading("Selected", text="✓")
        self.treeview.heading("Name", text="Dashboard Name")
        self.treeview.heading("URL", text="URL")
        self.treeview.heading("Group", text="Group")
        self.treeview.heading("Status", text="Status")
        
        self.treeview.column("Selected", width=40, minwidth=40)
        self.treeview.column("Name", width=250, minwidth=150)
        self.treeview.column("URL", width=300, minwidth=200)
        self.treeview.column("Group", width=100, minwidth=80)
        self.treeview.column("Status", width=100, minwidth=80)
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.treeview.yview)
        h_scrollbar = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.treeview.xview)
        self.treeview.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Pack treeview and scrollbars
        self.treeview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Bind click event for selection toggle
        self.treeview.bind("<Button-1>", self.toggle_selection)
        self.treeview.bind("<Double-1>", self._on_double_click)
        
        # Progress frame
        progress_frame = ttk.Frame(main_container)
        progress_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(progress_frame, text="Progress:").pack(side=tk.LEFT)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, 
                                          maximum=100, length=300, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, padx=(10, 10), fill=tk.X, expand=True)
        
        self.progress_label = ttk.Label(progress_frame, text="0/0")
        self.progress_label.pack(side=tk.RIGHT)
        
        # Status bar
        status_frame = ttk.Frame(main_container)
        status_frame.pack(fill=tk.X)
        
        self.statusbar = ttk.Label(status_frame, textvariable=self.status_message, relief=tk.SUNKEN)
        self.statusbar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Cancel button (initially hidden)
        self.cancel_button = ttk.Button(status_frame, text="Cancel", command=self._cancel_operation)
        
        # Schedule indicator
        self.schedule_indicator = ttk.Label(status_frame, text="", foreground="green")
        self.schedule_indicator.pack(side=tk.RIGHT, padx=(10, 0))

    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Import Dashboards...", command=self._import_dashboards)
        file_menu.add_command(label="Export Dashboards...", command=self._export_dashboards)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Manage Credentials", command=self.manage_credentials)
        tools_menu.add_command(label="Schedule Analysis...", command=self.configure_schedule)
        tools_menu.add_command(label="Cancel Schedule", command=self.cancel_scheduled_analysis)
        tools_menu.add_separator()
        tools_menu.add_command(label="Clean Archives", command=self._clean_archives)
        tools_menu.add_command(label="Open Logs Folder", command=self._open_logs_folder)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _load_initial_data(self):
        """Load initial application data."""
        # Load dashboards
        self.session["dashboards"] = load_dashboards()
        
        # Load credentials
        username, password = load_credentials()
        if username and password:
            self.session["username"] = username
            self.session["password"] = password
        
        # Load settings
        settings = load_settings()
        if settings:
            # Restore window geometry
            if "geometry" in settings:
                try:
                    self.master.geometry(settings["geometry"])
                except:
                    pass
            
            # Restore group filter
            if "last_group" in settings:
                self.group_filter_var.set(settings["last_group"])
        
        # Update UI
        self.update_group_filter()
        self.refresh_dashboard_list()
        self.update_status("Application loaded successfully")

    def update_status(self, msg: str, level: str = "info"):
        """Update the status bar and log."""
        self.status_message.set(msg)
        getattr(logger, level, logger.info)(msg)

    def manage_credentials(self):
        """Dialog for entering/updating Splunk credentials securely."""
        dlg = tk.Toplevel(self.master)
        dlg.title("Manage Credentials")
        dlg.geometry("400x200")
        dlg.transient(self.master)
        dlg.grab_set()
        dlg.resizable(False, False)
        
        # Center the dialog
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() // 2) - (dlg.winfo_width() // 2)
        y = (dlg.winfo_screenheight() // 2) - (dlg.winfo_height() // 2)
        dlg.geometry(f"+{x}+{y}")
        
        frm = ttk.Frame(dlg, padding=20)
        frm.pack(fill=tk.BOTH, expand=True)
        
        # Username field
        ttk.Label(frm, text="Splunk Username:").grid(row=0, column=0, sticky="e", pady=5, padx=(0, 10))
        user_var = tk.StringVar(value=self.session.get("username", ""))
        user_entry = ttk.Entry(frm, textvariable=user_var, width=25)
        user_entry.grid(row=0, column=1, pady=5, columnspan=2, sticky="ew")
        user_entry.focus_set()
        
        # Password field
        ttk.Label(frm, text="Splunk Password:").grid(row=1, column=0, sticky="e", pady=5, padx=(0, 10))
        pass_var = tk.StringVar(value=self.session.get("password", ""))
        pass_entry = ttk.Entry(frm, textvariable=pass_var, show="*", width=25)
        pass_entry.grid(row=1, column=1, pady=5, sticky="ew")
        
        # Show password checkbox
        show_pw_var = tk.BooleanVar()
        def toggle_pw():
            pass_entry.config(show="" if show_pw_var.get() else "*")
        show_pw = ttk.Checkbutton(frm, text="Show", variable=show_pw_var, command=toggle_pw)
        show_pw.grid(row=1, column=2, padx=(5, 0))
        
        # Configure grid weights
        frm.columnconfigure(1, weight=1)
        
        # Buttons frame
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=(20, 0), sticky="ew")
        
        def save_and_close():
            username = user_var.get().strip()
            password = pass_var.get().strip()
            if not username or not password:
                messagebox.showerror("Input Error", "Both username and password are required.", parent=dlg)
                return
            
            self.session["username"] = username
            self.session["password"] = password
            if save_credentials(username, password):
                messagebox.showinfo("Success", "Credentials saved successfully!", parent=dlg)
                dlg.destroy()
            else:
                messagebox.showerror("Error", "Failed to save credentials.", parent=dlg)
        
        def test_credentials():
            username = user_var.get().strip()
            password = pass_var.get().strip()
            if not username or not password:
                messagebox.showerror("Input Error", "Enter both username and password to test.", parent=dlg)
                return
            
            # Simple validation - in real app you might test against Splunk
            messagebox.showinfo("Test", "Credentials format appears valid.", parent=dlg)
        
        ttk.Button(btn_frame, text="Save", command=save_and_close).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="Test", command=test_credentials).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        
        # Bind Enter key
        dlg.bind('<Return>', lambda e: save_and_close())
        dlg.wait_window()

    def add_dashboard(self):
        """Dialog to add a new dashboard entry."""
        dlg = tk.Toplevel(self.master)
        dlg.title("Add Dashboard")
        dlg.geometry("500x300")
        dlg.transient(self.master)
        dlg.grab_set()
        dlg.resizable(False, False)
        
        # Center dialog
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() // 2) - (dlg.winfo_width() // 2)
        y = (dlg.winfo_screenheight() // 2) - (dlg.winfo_height() // 2)
        dlg.geometry(f"+{x}+{y}")
        
        frm = ttk.Frame(dlg, padding=20)
        frm.pack(fill=tk.BOTH, expand=True)
        
        # Form fields
        ttk.Label(frm, text="Dashboard Name:").grid(row=0, column=0, sticky="e", pady=5, padx=(0, 10))
        name_var = tk.StringVar()
        name_entry = ttk.Entry(frm, textvariable=name_var, width=35)
        name_entry.grid(row=0, column=1, pady=5, sticky="ew")
        name_entry.focus_set()
        
        ttk.Label(frm, text="Dashboard URL:").grid(row=1, column=0, sticky="e", pady=5, padx=(0, 10))
        url_var = tk.StringVar()
        url_entry = ttk.Entry(frm, textvariable=url_var, width=35)
        url_entry.grid(row=1, column=1, pady=5, sticky="ew")
        
        ttk.Label(frm, text="Group:").grid(row=2, column=0, sticky="e", pady=5, padx=(0, 10))
        group_var = tk.StringVar()
        existing_groups = [g for g in get_groups(self.session['dashboards']) if g != "All"]
        group_combo = ttk.Combobox(frm, textvariable=group_var, values=existing_groups, width=32)
        group_combo.grid(row=2, column=1, pady=5, sticky="ew")
        if existing_groups:
            group_combo.set(existing_groups[0] if existing_groups[0] != "Default" else "")
        
        ttk.Label(frm, text="Description:").grid(row=3, column=0, sticky="ne", pady=5, padx=(0, 10))
        desc_text = tk.Text(frm, width=35, height=4)
        desc_text.grid(row=3, column=1, pady=5, sticky="ew")
        
        # Configure grid
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(3, weight=1)
        
        # Buttons
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(15, 0), sticky="ew")
        
        def add_and_close():
            name = name_var.get().strip()
            url = url_var.get().strip()
            group = group_var.get().strip() or "Default"
            description = desc_text.get("1.0", tk.END).strip()
            
            # Validation
            if not name:
                messagebox.showerror("Validation Error", "Dashboard name is required.", parent=dlg)
                return
            
            if not url:
                messagebox.showerror("Validation Error", "Dashboard URL is required.", parent=dlg)
                return
            
            # Check for duplicates
            existing_names = [d['name'].lower() for d in self.session['dashboards']]
            if name.lower() in existing_names:
                messagebox.showerror("Duplicate Error", f"A dashboard named '{name}' already exists.", parent=dlg)
                return
            
            # Add dashboard
            new_dashboard = {
                "name": name,
                "url": url,
                "group": group,
                "description": description,
                "selected": True,
                "status": "Pending"
            }
            
            self.session['dashboards'].append(new_dashboard)
            save_dashboards(self.session['dashboards'])
            self.update_group_filter()
            self.refresh_dashboard_list()
            self.update_status(f"Added dashboard: {name}")
            dlg.destroy()
        
        ttk.Button(btn_frame, text="Add Dashboard", command=add_and_close).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        
        # Bind Enter to add
        dlg.bind('<Return>', lambda e: add_and_close())
        dlg.wait_window()

    def delete_dashboard(self):
        """Delete selected dashboards from the list."""
        selected_items = self.treeview.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "Please select dashboards to delete.")
            return
        
        # Get dashboard names
        dashboards_to_delete = []
        for item_id in selected_items:
            try:
                idx = int(item_id)
                dashboards_to_delete.append(self.session['dashboards'][idx]['name'])
            except (ValueError, IndexError):
                continue
        
        if not dashboards_to_delete:
            return
        
        # Confirm deletion
        names_str = "\n".join(f"• {name}" for name in dashboards_to_delete)
        if not messagebox.askyesno("Confirm Deletion", 
                                  f"Delete {len(dashboards_to_delete)} dashboard(s)?\n\n{names_str}"):
            return
        
        # Delete dashboards (in reverse order to maintain indices)
        indices_to_delete = sorted([int(item_id) for item_id in selected_items], reverse=True)
        for idx in indices_to_delete:
            try:
                del self.session['dashboards'][idx]
            except IndexError:
                continue
        
        # Save and refresh
        save_dashboards(self.session['dashboards'])
        self.update_group_filter()
        self.refresh_dashboard_list()
        self.update_status(f"Deleted {len(dashboards_to_delete)} dashboard(s)")

    def select_all_dashboards(self):
        """Mark all dashboards as selected."""
        select_all(self.session['dashboards'])
        self.refresh_dashboard_list()
        self.update_status("Selected all dashboards")

    def deselect_all_dashboards(self):
        """Deselect all dashboards."""
        deselect_all(self.session['dashboards'])
        self.refresh_dashboard_list()
        self.update_status("Deselected all dashboards")

    def toggle_selection(self, event):
        """Toggle selection state for a dashboard from treeview click."""
        item_id = self.treeview.identify_row(event.y)
        column = self.treeview.identify_column(event.x)
        
        # Only toggle if clicking on the selection column
        if not item_id or column != "#1":
            return
        
        try:
            db = self.session['dashboards'][int(item_id)]
            db["selected"] = not db.get("selected", False)
            self.refresh_dashboard_list()
        except (IndexError, ValueError):
            pass

    def _on_double_click(self, event):
        """Handle double-click on dashboard to open URL."""
        item_id = self.treeview.identify_row(event.y)
        if not item_id:
            return
        
        try:
            db = self.session['dashboards'][int(item_id)]
            webbrowser.open(db['url'])
        except (IndexError, ValueError):
            pass

    def refresh_dashboard_list(self):
        """Update the treeview to show current dashboards."""
        refresh_dashboard_list(self.treeview, self.session['dashboards'], self.group_filter_var)

    def update_group_filter(self):
        """Update the group filter dropdown based on current dashboard groups."""
        groups = get_groups(self.session['dashboards'])
        self.group_filter['values'] = groups
        if self.group_filter_var.get() not in groups:
            self.group_filter_var.set("All")

    def export_results(self):
        """Export dashboard names, URLs, groups, and statuses as a CSV file."""
        if not self.session['dashboards']:
            messagebox.showinfo("Nothing to Export", "No dashboards loaded.")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Export Dashboard Results"
        )
        
        if not file_path:
            return
        
        try:
            import csv
            with open(file_path, "w", newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Selected", "Name", "URL", "Group", "Status", "Description"])
                for db in self.session['dashboards']:
                    writer.writerow([
                        "Yes" if db.get("selected") else "No",
                        db.get("name", ""),
                        db.get("url", ""),
                        db.get("group", "Default"),
                        db.get("status", "Pending"),
                        db.get("description", "")
                    ])
            
            self.update_status(f"Exported results to {file_path}")
            messagebox.showinfo("Export Successful", f"Results exported to:\n{file_path}")
            
        except Exception as e:
            self.update_status(f"Export failed: {e}", "error")
            messagebox.showerror("Export Error", f"Failed to export results:\n{e}")

    def load_settings(self):
        """Load settings using settings module."""
        return load_settings()

    def save_settings(self, settings: dict = None):
        """Save settings using settings module."""
        if settings is None:
            settings = {}
        
        # Add current window geometry
        try:
            settings["geometry"] = self.master.geometry()
        except:
            pass
        
        # Add current group filter
        settings["last_group"] = self.group_filter_var.get()
        
        # Add dashboard selection states
        settings["dashboard_selections"] = {
            db["name"]: db.get("selected", False) 
            for db in self.session["dashboards"]
        }
        
        save_settings(settings)

    def run_analysis_thread(self, scheduled_run=False, schedule_config=None):
        """Start dashboard analysis workflow in a new thread."""
        if self.current_thread and self.current_thread.is_alive():
            messagebox.showwarning("Analysis Running", "An analysis is already in progress.")
            return
        
        # Check credentials
        if not self.session.get("username") or not self.session.get("password"):
            if messagebox.askyesno("Missing Credentials", 
                                  "Splunk credentials are required. Open credentials dialog?"):
                self.manage_credentials()
                if not self.session.get("username") or not self.session.get("password"):
                    return
            else:
                return
        
        # Get selected dashboards
        selected_dashboards = [db for db in self.session['dashboards'] if db.get('selected')]
        if not selected_dashboards:
            messagebox.showwarning("No Selection", "Please select at least one dashboard to analyze.")
            return
        
        # Get time range if not scheduled
        time_range = None
        if not scheduled_run:
            time_dialog = TimeRangeDialog(self.master)
            self.master.wait_window(time_dialog)
            time_range = getattr(time_dialog, 'result', None)
            
            if not time_range:
                return
        else:
            time_range = schedule_config.get('time_range', {'start': '-24h', 'end': 'now'})
        
        # Archive old tmp files
        try:
            archive_and_clean_tmp()
        except Exception as e:
            logger.warning(f"Failed to archive tmp files: {e}")
        
        # Start analysis thread
        self.cancel_flag.clear()
        self.current_thread = threading.Thread(
            target=self._run_analysis_wrapper,
            args=(selected_dashboards, time_range),
            daemon=True
        )
        self.current_thread.start()
        
        # Update UI
        self.cancel_button.pack(side=tk.RIGHT, padx=(10, 0))
        self.update_status(f"Starting analysis of {len(selected_dashboards)} dashboards...")

    def _run_analysis_wrapper(self, dashboards, time_range):
        """Wrapper to run async analysis in thread."""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run analysis
            loop.run_until_complete(
                self.analyze_dashboards_async(dashboards, time_range['start'], time_range['end'])
            )
            
        except Exception as e:
            logger.error(f"Analysis thread error: {e}", exc_info=True)
            self.master.after(0, lambda: self.update_status(f"Analysis failed: {e}", "error"))
        finally:
            # Clean up UI
            self.master.after(0, self._analysis_complete)

    async def analyze_dashboards_async(self, dashboards, start_dt, end_dt, retries=3):
        """Coroutine: Run browser sessions, process dashboards in parallel with retries."""
        total_dashboards = len(dashboards)
        completed = 0
        
        # Update progress
        def update_ui_progress():
            self.master.after(0, lambda: self.update_progress(completed, total_dashboards))
        
        async with async_playwright() as playwright:
            # Process dashboards with limited concurrency
            semaphore = asyncio.Semaphore(3)  # Max 3 concurrent browsers
            
            async def process_with_semaphore(db):
                nonlocal completed
                async with semaphore:
                    if self.cancel_flag.is_set():
                        return
                    
                    # Update status
                    self.master.after(0, lambda name=db['name']: 
                                    self.update_dashboard_status(name, "Processing"))
                    
                    # Try processing with retries
                    for attempt in range(retries):
                        if self.cancel_flag.is_set():
                            return
                        
                        try:
                            success = await process_single_dashboard(
                                playwright, db, start_dt, end_dt,
                                self.session['username'], self.session['password']
                            )
                            
                            if success:
                                self.master.after(0, lambda name=db['name']: 
                                                self.update_dashboard_status(name, "Failed"))
                    
                    completed += 1
                    update_ui_progress()
            
            # Run all dashboard processing tasks
            tasks = [process_with_semaphore(db) for db in dashboards]
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Final status update
        if not self.cancel_flag.is_set():
            self.master.after(0, lambda: self.update_status(f"Analysis complete! Processed {total_dashboards} dashboards"))
            self.master.after(0, self.post_run_cleanup)

    def update_dashboard_status(self, name: str, status: str):
        """Update dashboard status in treeview and memory."""
        # Update in memory
        for db in self.session['dashboards']:
            if db['name'] == name:
                db['status'] = status
                break
        
        # Update UI
        self._update_status_in_ui(name, status)

    def _update_status_in_ui(self, name: str, status: str):
        """Helper to update status in the treeview UI."""
        for item in self.treeview.get_children():
            values = self.treeview.item(item, 'values')
            if len(values) > 1 and values[1] == name:
                # Update the status column (index 4)
                new_values = list(values)
                new_values[4] = status
                self.treeview.item(item, values=new_values)
                break

    def update_progress(self, value: int, maximum: int = None):
        """Update the progress bar."""
        if maximum is not None:
            self.progress_max.set(maximum)
            self.progress_bar.configure(maximum=maximum)
        
        self.progress_var.set(value)
        self.progress_label.configure(text=f"{value}/{self.progress_max.get()}")

    def _update_progress_in_ui(self, value: int, maximum: int = None):
        """Helper for progress bar update (direct UI call)."""
        self.update_progress(value, maximum)

    def handle_login_failure(self):
        """Prompt for login if failure detected."""
        if messagebox.askyesno("Login Failed", 
                              "Splunk login failed. Update credentials?"):
            self.manage_credentials()
            return self.session.get("username") and self.session.get("password")
        return False

    def configure_schedule(self):
        """Open dialog to configure scheduled analysis."""
        dlg = tk.Toplevel(self.master)
        dlg.title("Schedule Analysis")
        dlg.geometry("500x400")
        dlg.transient(self.master)
        dlg.grab_set()
        dlg.resizable(False, False)
        
        # Center dialog
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() // 2) - (dlg.winfo_width() // 2)
        y = (dlg.winfo_screenheight() // 2) - (dlg.winfo_height() // 2)
        dlg.geometry(f"+{x}+{y}")
        
        notebook = ttk.Notebook(dlg)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Basic settings tab
        basic_frame = ttk.Frame(notebook, padding=10)
        notebook.add(basic_frame, text="Basic Settings")
        
        # Enable scheduling
        enable_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(basic_frame, text="Enable Scheduled Analysis", 
                       variable=enable_var).pack(anchor="w", pady=5)
        
        # Frequency
        ttk.Label(basic_frame, text="Run every:").pack(anchor="w", pady=(10, 0))
        freq_frame = ttk.Frame(basic_frame)
        freq_frame.pack(fill=tk.X, pady=5)
        
        interval_var = tk.StringVar(value="1")
        interval_entry = ttk.Entry(freq_frame, textvariable=interval_var, width=5)
        interval_entry.pack(side=tk.LEFT)
        
        unit_var = tk.StringVar(value="hours")
        unit_combo = ttk.Combobox(freq_frame, textvariable=unit_var, 
                                 values=["minutes", "hours", "days", "weeks"], 
                                 state="readonly", width=10)
        unit_combo.pack(side=tk.LEFT, padx=(5, 0))
        
        # Time range for scheduled runs
        ttk.Label(basic_frame, text="Default Time Range:").pack(anchor="w", pady=(15, 0))
        time_frame = ttk.Frame(basic_frame)
        time_frame.pack(fill=tk.X, pady=5)
        
        time_range_var = tk.StringVar(value="Last 24 hours")
        time_ranges = ["Last 15 minutes", "Last 60 minutes", "Last 4 hours", 
                      "Last 24 hours", "Last 7 days", "Last 30 days"]
        time_combo = ttk.Combobox(time_frame, textvariable=time_range_var,
                                 values=time_ranges, state="readonly", width=20)
        time_combo.pack(side=tk.LEFT)
        
        # Email notifications tab
        email_frame = ttk.Frame(notebook, padding=10)
        notebook.add(email_frame, text="Notifications")
        
        email_enable_var = tk.BooleanVar()
        ttk.Checkbutton(email_frame, text="Send email notifications", 
                       variable=email_enable_var).pack(anchor="w", pady=5)
        
        ttk.Label(email_frame, text="Email recipients (comma-separated):").pack(anchor="w", pady=(10, 0))
        email_var = tk.StringVar()
        email_entry = ttk.Entry(email_frame, textvariable=email_var, width=50)
        email_entry.pack(fill=tk.X, pady=5)
        
        # Dashboard selection tab
        dash_frame = ttk.Frame(notebook, padding=10)
        notebook.add(dash_frame, text="Dashboards")
        
        ttk.Label(dash_frame, text="Dashboards to include in scheduled runs:").pack(anchor="w")
        
        # Listbox for dashboard selection
        list_frame = ttk.Frame(dash_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        dashboard_listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, height=10)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=dashboard_listbox.yview)
        dashboard_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Populate dashboard list
        for db in self.session['dashboards']:
            dashboard_listbox.insert(tk.END, db['name'])
            if db.get('selected'):
                dashboard_listbox.selection_set(tk.END)
        
        dashboard_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Buttons
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def save_schedule():
            if not enable_var.get():
                messagebox.showinfo("Schedule Disabled", "Scheduled analysis is disabled.")
                dlg.destroy()
                return
            
            try:
                interval = int(interval_var.get())
                if interval <= 0:
                    raise ValueError("Interval must be positive")
            except ValueError:
                messagebox.showerror("Invalid Input", "Please enter a valid interval.")
                return
            
            # Get selected dashboards
            selected_indices = dashboard_listbox.curselection()
            selected_dashboards = [self.session['dashboards'][i]['name'] for i in selected_indices]
            
            if not selected_dashboards:
                messagebox.showwarning("No Dashboards", "Please select at least one dashboard.")
                return
            
            # Create schedule config
            schedule_config = {
                "enabled": True,
                "interval": interval,
                "unit": unit_var.get(),
                "time_range": self._parse_time_range_preset(time_range_var.get()),
                "dashboards": selected_dashboards,
                "email_enabled": email_enable_var.get(),
                "email_recipients": [email.strip() for email in email_var.get().split(',') if email.strip()],
                "created": datetime.now().isoformat()
            }
            
            # Save schedule
            try:
                with open(Config.SCHEDULE_FILE, 'w') as f:
                    json.dump(schedule_config, f, indent=4)
                
                self.schedule_config = schedule_config
                self.start_schedule_if_exists()
                messagebox.showinfo("Schedule Saved", "Scheduled analysis has been configured and started.")
                dlg.destroy()
                
            except Exception as e:
                messagebox.showerror("Save Error", f"Failed to save schedule: {e}")
        
        ttk.Button(btn_frame, text="Save Schedule", command=save_schedule).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Cancel", command=dlg.destroy).pack(side=tk.RIGHT)
        
        dlg.wait_window()

    def _parse_time_range_preset(self, preset):
        """Convert time range preset to Splunk format."""
        preset_map = {
            "Last 15 minutes": {"start": "-15m", "end": "now"},
            "Last 60 minutes": {"start": "-60m", "end": "now"},
            "Last 4 hours": {"start": "-4h", "end": "now"},
            "Last 24 hours": {"start": "-24h", "end": "now"},
            "Last 7 days": {"start": "-7d", "end": "now"},
            "Last 30 days": {"start": "-30d", "end": "now"}
        }
        return preset_map.get(preset, {"start": "-24h", "end": "now"})

    def start_schedule_if_exists(self):
        """Load and start scheduled analysis if a schedule config file exists."""
        if not os.path.exists(Config.SCHEDULE_FILE):
            return
        
        try:
            with open(Config.SCHEDULE_FILE, 'r') as f:
                self.schedule_config = json.load(f)
            
            if self.schedule_config.get('enabled'):
                self.run_scheduled_analysis(self.schedule_config)
                self.schedule_indicator.configure(text="🕒 Scheduled")
                
        except Exception as e:
            logger.error(f"Failed to load schedule: {e}")

    def run_scheduled_analysis(self, schedule_config=None):
        """Run scheduled analysis as a background thread based on config."""
        if not schedule_config:
            schedule_config = self.schedule_config
        
        if not schedule_config or self.schedule_active:
            return
        
        self.schedule_active = True
        
        def schedule_worker():
            interval = schedule_config['interval']
            unit = schedule_config['unit']
            
            # Convert to seconds
            multipliers = {
                'minutes': 60,
                'hours': 3600,
                'days': 86400,
                'weeks': 604800
            }
            sleep_time = interval * multipliers.get(unit, 3600)
            
            while self.schedule_active:
                try:
                    # Wait for the interval (checking every 10 seconds for cancellation)
                    for _ in range(0, sleep_time, 10):
                        if not self.schedule_active:
                            return
                        threading.Event().wait(min(10, sleep_time))
                    
                    if not self.schedule_active:
                        return
                    
                    # Run analysis
                    logger.info("Running scheduled analysis")
                    
                    # Select scheduled dashboards
                    scheduled_names = schedule_config.get('dashboards', [])
                    for db in self.session['dashboards']:
                        db['selected'] = db['name'] in scheduled_names
                    
                    # Update UI
                    self.master.after(0, self.refresh_dashboard_list)
                    
                    # Run analysis
                    self.master.after(0, lambda: self.run_analysis_thread(
                        scheduled_run=True, schedule_config=schedule_config))
                    
                except Exception as e:
                    logger.error(f"Scheduled analysis error: {e}")
        
        self.schedule_thread = threading.Thread(target=schedule_worker, daemon=True)
        self.schedule_thread.start()

    def schedule_analysis(self):
        """Initiate the schedule configuration workflow."""
        self.configure_schedule()

    def cancel_scheduled_analysis(self):
        """Cancel any scheduled analysis and delete the schedule file."""
        if self.schedule_active:
            self.schedule_active = False
            if self.schedule_thread:
                self.schedule_thread = None
            
            # Remove schedule file
            if os.path.exists(Config.SCHEDULE_FILE):
                try:
                    os.remove(Config.SCHEDULE_FILE)
                except Exception as e:
                    logger.error(f"Failed to remove schedule file: {e}")
            
            self.schedule_config = None
            self.schedule_indicator.configure(text="")
            messagebox.showinfo("Schedule Cancelled", "Scheduled analysis has been cancelled.")
        else:
            messagebox.showinfo("No Schedule", "No scheduled analysis is currently active.")

    def post_run_cleanup(self):
        """Purge old screenshot archives after a run."""
        try:
            purge_old_archives()
            logger.info("Completed post-run cleanup")
        except Exception as e:
            logger.warning(f"Post-run cleanup failed: {e}")

    def capture_screenshots_thread(self):
        """Start threaded screenshot capture (no analysis), prompts for time range."""
        if self.current_thread and self.current_thread.is_alive():
            messagebox.showwarning("Operation Running", "Another operation is already in progress.")
            return
        
        # Check credentials
        if not self.session.get("username") or not self.session.get("password"):
            if messagebox.askyesno("Missing Credentials", 
                                  "Splunk credentials are required. Open credentials dialog?"):
                self.manage_credentials()
                if not self.session.get("username") or not self.session.get("password"):
                    return
            else:
                return
        
        # Get selected dashboards
        selected_dashboards = [db for db in self.session['dashboards'] if db.get('selected')]
        if not selected_dashboards:
            messagebox.showwarning("No Selection", "Please select at least one dashboard.")
            return
        
        # Get time range
        time_dialog = TimeRangeDialog(self.master)
        self.master.wait_window(time_dialog)
        time_range = getattr(time_dialog, 'result', None)
        
        if not time_range:
            return
        
        # Archive old tmp files
        try:
            archive_and_clean_tmp()
        except Exception as e:
            logger.warning(f"Failed to archive tmp files: {e}")
        
        # Start screenshot thread
        self.cancel_flag.clear()
        self.current_thread = threading.Thread(
            target=self._capture_screenshots_wrapper,
            args=(selected_dashboards, time_range),
            daemon=True
        )
        self.current_thread.start()
        
        # Update UI
        self.cancel_button.pack(side=tk.RIGHT, padx=(10, 0))
        self.update_status(f"Capturing screenshots for {len(selected_dashboards)} dashboards...")

    def _capture_screenshots_wrapper(self, dashboards, time_range):
        """Wrapper to run async screenshot capture in thread."""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run screenshot capture
            loop.run_until_complete(
                self._capture_screenshots_async(dashboards, time_range['start'], time_range['end'])
            )
            
        except Exception as e:
            logger.error(f"Screenshot thread error: {e}", exc_info=True)
            self.master.after(0, lambda: self.update_status(f"Screenshot capture failed: {e}", "error"))
        finally:
            # Clean up UI
            self.master.after(0, self._analysis_complete)

    async def _capture_screenshots_async(self, dashboards, start_dt, end_dt):
        """Async screenshot capture for dashboards."""
        total_dashboards = len(dashboards)
        completed = 0
        
        # Update progress
        def update_ui_progress():
            self.master.after(0, lambda: self.update_progress(completed, total_dashboards))
        
        async with async_playwright() as playwright:
            # Process dashboards with limited concurrency
            semaphore = asyncio.Semaphore(2)  # Max 2 concurrent browsers for screenshots
            
            async def capture_with_semaphore(db):
                nonlocal completed
                async with semaphore:
                    if self.cancel_flag.is_set():
                        return
                    
                    # Update status
                    self.master.after(0, lambda name=db['name']: 
                                    self.update_dashboard_status(name, "Capturing"))
                    
                    try:
                        success = await process_single_dashboard(
                            playwright, db, start_dt, end_dt,
                            self.session['username'], self.session['password'],
                            capture_only=True
                        )
                        
                        if success:
                            self.master.after(0, lambda name=db['name']: 
                                            self.update_dashboard_status(name, "Captured"))
                        else:
                            self.master.after(0, lambda name=db['name']: 
                                            self.update_dashboard_status(name, "Failed"))
                    
                    except Exception as e:
                        logger.error(f"Error capturing {db['name']}: {e}")
                        self.master.after(0, lambda name=db['name']: 
                                        self.update_dashboard_status(name, "Error"))
                    
                    completed += 1
                    update_ui_progress()
            
            # Run all screenshot tasks
            tasks = [capture_with_semaphore(db) for db in dashboards]
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Final status update
        if not self.cancel_flag.is_set():
            self.master.after(0, lambda: self.update_status(f"Screenshot capture complete! {total_dashboards} dashboards processed"))

    def format_time_for_url(self, base_url, start_dt, end_dt, is_studio=False):
        """Format dashboard URL with time parameters for Classic or Studio."""
        try:
            # Handle string time formats (Splunk relative time)
            if isinstance(start_dt, str) and isinstance(end_dt, str):
                param_prefix = "form.global_time" if is_studio else "form.time_field"
                params = {
                    f"{param_prefix}.earliest": start_dt,
                    f"{param_prefix}.latest": end_dt
                }
            else:
                # Handle datetime objects
                param_prefix = "form.global_time" if is_studio else "form.time_field"
                params = {
                    f"{param_prefix}.earliest": int(start_dt.timestamp()) if hasattr(start_dt, 'timestamp') else start_dt,
                    f"{param_prefix}.latest": int(end_dt.timestamp()) if hasattr(end_dt, 'timestamp') else end_dt
                }
            
            # Remove existing query parameters
            base_url = base_url.split('?')[0]
            
            # Add new parameters
            param_string = '&'.join(f'{k}={v}' for k, v in params.items())
            return f"{base_url}?{param_string}"
            
        except Exception as e:
            logger.error(f"Error formatting URL: {e}")
            return base_url

    async def _wait_for_splunk_dashboard_to_load(self, page, name):
        """Wait for Splunk dashboard panels to load and stabilize."""
        try:
            # Check if it's a Studio dashboard
            is_studio = False
            try:
                await page.wait_for_selector("splunk-dashboard-view", timeout=5000)
                is_studio = True
                logger.info(f"Detected Studio dashboard: {name}")
            except:
                logger.info(f"Detected Classic dashboard: {name}")
            
            if is_studio:
                # Wait for Studio dashboard elements
                await page.wait_for_selector("splunk-dashboard-view", timeout=30000)
                
                # Wait for panels to load
                await page.wait_for_function("""
                    () => {
                        const panels = document.querySelectorAll('splunk-viz, splunk-single-value, splunk-table');
                        return panels.length > 0;
                    }
                """, timeout=30000)
                
                # Wait for data to load (look for loading indicators to disappear)
                try:
                    await page.wait_for_function("""
                        () => {
                            const loadingElements = document.querySelectorAll('[data-test="loading"], .loading, .spinner');
                            return loadingElements.length === 0 || 
                                   Array.from(loadingElements).every(el => el.style.display === 'none');
                        }
                    """, timeout=60000)
                except:
                    logger.warning(f"Timeout waiting for loading indicators to disappear: {name}")
                
            else:
                # Wait for Classic dashboard elements
                await page.wait_for_selector(".dashboard-body, #dashboard", timeout=30000)
                
                # Wait for panels
                await page.wait_for_selector(".dashboard-panel, .panel", timeout=30000)
                
                # Wait for search completion
                try:
                    await page.wait_for_function("""
                        () => {
                            const searchElements = document.querySelectorAll('.shared-searchbar, .search-status');
                            return searchElements.length === 0 || 
                                   !document.querySelector('.search-status[data-status="running"]');
                        }
                    """, timeout=60000)
                except:
                    logger.warning(f"Timeout waiting for searches to complete: {name}")
            
            # Additional stabilization wait
            await page.wait_for_timeout(3000)
            
            return True
            
        except Exception as e:
            logger.error(f"Error waiting for dashboard to load ({name}): {e}")
            return False

    def _cancel_operation(self):
        """Cancel the current operation."""
        if messagebox.askyesno("Cancel Operation", "Are you sure you want to cancel the current operation?"):
            self.cancel_flag.set()
            self.update_status("Cancelling operation...")

    def _analysis_complete(self):
        """Clean up UI after analysis completion."""
        self.cancel_button.pack_forget()
        self.update_progress(0, 100)
        self.current_thread = None

    def on_closing(self):
        """Handles window close event."""
        # Save settings before closing
        try:
            self.save_settings()
        except Exception as e:
            logger.error(f"Failed to save settings on close: {e}")
        
        # Cancel any running operations
        if self.current_thread and self.current_thread.is_alive():
            if messagebox.askyesno("Operation Running", 
                                  "An operation is currently running. Cancel and quit?"):
                self.cancel_flag.set()
                # Give a moment for cleanup
                self.master.after(1000, self.master.destroy)
                return
            else:
                return
        
        # Cancel scheduled analysis
        if self.schedule_active:
            self.schedule_active = False
        
        # Confirm quit
        if messagebox.askokcancel("Quit", "Do you want to quit Splunk Automator?"):
            self.master.destroy()

    # Additional helper methods for menu actions
    def _import_dashboards(self):
        """Import dashboards from a JSON file."""
        file_path = filedialog.askopenfilename(
            title="Import Dashboards",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_dashboards = json.load(f)
            
            if not isinstance(imported_dashboards, list):
                messagebox.showerror("Import Error", "File does not contain a valid dashboard list.")
                return
            
            # Add imported dashboards (avoid duplicates)
            existing_names = {db['name'].lower() for db in self.session['dashboards']}
            added_count = 0
            
            for db in imported_dashboards:
                if isinstance(db, dict) and 'name' in db and 'url' in db:
                    if db['name'].lower() not in existing_names:
                        # Ensure required fields
                        db.setdefault('group', 'Default')
                        db.setdefault('selected', True)
                        db.setdefault('status', 'Pending')
                        db.setdefault('description', '')
                        
                        self.session['dashboards'].append(db)
                        existing_names.add(db['name'].lower())
                        added_count += 1
            
            if added_count > 0:
                save_dashboards(self.session['dashboards'])
                self.update_group_filter()
                self.refresh_dashboard_list()
                self.update_status(f"Imported {added_count} dashboards")
                messagebox.showinfo("Import Successful", f"Imported {added_count} new dashboards.")
            else:
                messagebox.showinfo("Import Complete", "No new dashboards were imported (duplicates skipped).")
        
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import dashboards:\n{e}")

    def _export_dashboards(self):
        """Export dashboards to a JSON file."""
        if not self.session['dashboards']:
            messagebox.showinfo("Nothing to Export", "No dashboards to export.")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Export Dashboards",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            # Export without transient fields
            export_data = []
            for db in self.session['dashboards']:
                export_db = {k: v for k, v in db.items() if k not in ['status', 'selected']}
                export_data.append(export_db)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=4)
            
            self.update_status(f"Exported {len(export_data)} dashboards")
            messagebox.showinfo("Export Successful", f"Exported {len(export_data)} dashboards to:\n{file_path}")
        
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export dashboards:\n{e}")

    def _clean_archives(self):
        """Manually clean old archives."""
        try:
            purge_old_archives()
            messagebox.showinfo("Cleanup Complete", "Old screenshot archives have been cleaned.")
        except Exception as e:
            messagebox.showerror("Cleanup Error", f"Failed to clean archives:\n{e}")

    def _open_logs_folder(self):
        """Open the logs folder in file explorer."""
        try:
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                subprocess.run(["explorer", Config.LOG_DIR])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", Config.LOG_DIR])
            else:  # Linux
                subprocess.run(["xdg-open", Config.LOG_DIR])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open logs folder:\n{e}")

    def _show_about(self):
        """Show about dialog."""
        about_text = """Splunk Dashboard Automator v2.0

A tool for automated Splunk dashboard screenshot capture and analysis.

Features:
• Automated screenshot capture
• Support for Classic and Studio dashboards
• Flexible time range selection
• Scheduled analysis
• Group-based organization
• Secure credential storage

Created with Python, Tkinter, and Playwright."""
        
        messagebox.showinfo("About Splunk Automator", about_text)after(0, lambda name=db['name']: 
                                                self.update_dashboard_status(name, "Complete"))
                                break
                            else:
                                if attempt < retries - 1:
                                    self.master.after(0, lambda name=db['name']: 
                                                    self.update_dashboard_status(name, f"Retry {attempt + 1}"))
                                    await asyncio.sleep(2)  # Wait before retry
                                else:
                                    self.master.after(0, lambda name=db['name']: 
                                                    self.update_dashboard_status(name, "Failed"))
                        
                        except Exception as e:
                            logger.error(f"Error processing {db['name']}: {e}")
                            if attempt < retries - 1:
                                self.master.after(0, lambda name=db['name']: 
                                                self.update_dashboard_status(name, f"Error - Retry {attempt + 1}"))
                                await asyncio.sleep(2)
                            else:
                                self.master.
