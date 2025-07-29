import tkinter as tk
from tkinter import ttk, messagebox, Toplevel
from datetime import datetime, time as dt_time, timedelta
import pytz
import json
import os

try:
    from tkcalendar import DateEntry
except ImportError:
    raise ImportError("tkcalendar is required for TimeRangeDialog.")

class TimeRangeDialog(Toplevel):
    """Enhanced time range selection dialog with save/load presets functionality."""
    
    def __init__(self, parent, timezone="America/New_York", title="Select Time Range"):
        super().__init__(parent)
        self.title(title)
        self.geometry("750x550")
        self.result = {}
        self.est = pytz.timezone(timezone)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        
        # Center the dialog
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
        
        # Custom presets file
        self.custom_presets_file = "custom_time_presets.json"
        self.custom_presets = self._load_custom_presets()
        
        self._init_ui()
        self.focus_set()

    def _init_ui(self):
        """Initialize the user interface."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create left panel for options
        left_frame = ttk.Frame(main_frame, width=150)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)

        # Time range options
        options = ["Presets", "Relative", "Date Range", "Date & Time Range", "Advanced", "Custom Presets"]
        self.option_var = tk.StringVar(value=options[0])

        ttk.Label(left_frame, text="Time Range Type:", font=('TkDefaultFont', 9, 'bold')).pack(anchor="w", pady=(0, 5))
        
        for option in options:
            rb = ttk.Radiobutton(left_frame, text=option, variable=self.option_var, 
                               value=option, command=self.show_selected_frame)
            rb.pack(anchor="w", pady=2)

        # Add separator
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # Quick time buttons
        ttk.Label(left_frame, text="Quick Select:", font=('TkDefaultFont', 9, 'bold')).pack(anchor="w")
        
        quick_times = [
            ("Last Hour", "-1h@h", "now"),
            ("Today", "@d", "now"),
            ("Yesterday", "-1d@d", "@d"),
            ("This Week", "@w", "now"),
            ("Last Week", "-1w@w", "@w")
        ]
        
        for label, start, end in quick_times:
            btn = ttk.Button(left_frame, text=label, width=12,
                           command=lambda s=start, e=end: self._quick_select(s, e))
            btn.pack(pady=1, fill=tk.X)

        # Right panel for content
        self.content_frame = ttk.Frame(main_frame)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Create frames for each option
        self.frames = {}
        for option in options:
            frame = ttk.Frame(self.content_frame)
            self.frames[option] = frame
            
        # Build each frame
        self._build_presets_frame()
        self._build_relative_frame()
        self._build_date_range_frame()
        self._build_datetime_range_frame()
        self._build_advanced_frame()
        self._build_custom_presets_frame()

        # Button frame
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Left side buttons
        ttk.Button(btn_frame, text="Reset", command=self._reset_form).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Preview", command=self._preview_time_range).pack(side=tk.LEFT, padx=(10, 0))
        
        # Right side buttons
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Apply", command=self.on_apply).pack(side=tk.RIGHT, padx=(0, 10))

        # Show initial frame
        self.show_selected_frame()

    def _build_presets_frame(self):
        """Build the presets selection frame."""
        frame = self.frames["Presets"]
        
        # Standard Splunk time ranges
        self.preset_splunk_ranges = {
            "Last 15 minutes": ("-15m@m", "now"),
            "Last 30 minutes": ("-30m@m", "now"), 
            "Last 1 hour": ("-1h@h", "now"),
            "Last 4 hours": ("-4h@h", "now"),
            "Last 24 hours": ("-24h@h", "now"),
            "Last 7 days": ("-7d@d", "now"),
            "Last 30 days": ("-30d@d", "now"),
            "Today": ("@d", "now"),
            "Yesterday": ("-1d@d", "@d"),
            "This week": ("@w", "now"),
            "Previous week": ("-1w@w", "@w"),
            "This month": ("@mon", "now"),
            "Previous month": ("-1mon@mon", "@mon"),
            "This year": ("@y", "now"),
            "Previous year": ("-1y@y", "@y"),
            "Week to date": ("@w", "now"),
            "Month to date": ("@mon", "now"),
            "Year to date": ("@y", "now"),
            "All time": ("0", "now"),
        }
        
        # Search frame
        search_frame = ttk.Frame(frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(search_frame, text="Search presets:").pack(side=tk.LEFT)
        self.preset_search_var = tk.StringVar()
        self.preset_search_var.trace('w', self._filter_presets)
        search_entry = ttk.Entry(search_frame, textvariable=self.preset_search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=(10, 0), fill=tk.X, expand=True)
        
        # Scrollable preset list
        canvas = tk.Canvas(frame, height=300)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Populate preset buttons
        self.preset_buttons = []
        self._populate_preset_buttons()
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _populate_preset_buttons(self, filter_text=""):
        """Populate preset buttons with optional filtering."""
        # Clear existing buttons
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.preset_buttons.clear()
        
        # Filter presets
        filtered_presets = {}
        for name, value in self.preset_splunk_ranges.items():
            if filter_text.lower() in name.lower():
                filtered_presets[name] = value
        
        # Create buttons
        for i, (preset_name, preset_value) in enumerate(filtered_presets.items()):
            btn = ttk.Button(
                self.scrollable_frame,
                text=preset_name,
                width=25,
                command=lambda p=preset_name: self.select_preset(p)
            )
            btn.pack(pady=2, padx=10, fill=tk.X)
            self.preset_buttons.append(btn)

    def _filter_presets(self, *args):
        """Filter presets based on search text."""
        filter_text = self.preset_search_var.get()
        self._populate_preset_buttons(filter_text)

    def _build_relative_frame(self):
        """Build the relative time selection frame."""
        frame = self.frames["Relative"]
        
        # Title
        ttk.Label(frame, text="Relative Time Range", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 10))
        
        # Amount and unit selection
        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="Go back:").pack(side=tk.LEFT)
        
        self.relative_amount = ttk.Entry(input_frame, width=8)
        self.relative_amount.pack(side=tk.LEFT, padx=(10, 5))
        self.relative_amount.insert(0, "1")
        
        units = ["minutes", "hours", "days", "weeks", "months", "years"]
        self.relative_unit = ttk.Combobox(input_frame, values=units, state="readonly", width=10)
        self.relative_unit.current(1)  # Default to hours
        self.relative_unit.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(input_frame, text="from now").pack(side=tk.LEFT, padx=(5, 0))
        
        # Examples
        examples_frame = ttk.LabelFrame(frame, text="Examples", padding=10)
        examples_frame.pack(fill=tk.X, pady=(20, 0))
        
        example_text = """• 1 hour = Last 1 hour from now
• 24 hours = Last 24 hours from now  
• 7 days = Last 7 days from now
• 1 month = Last 1 month from now"""
        
        ttk.Label(examples_frame, text=example_text, justify=tk.LEFT).pack(anchor="w")

    def _build_date_range_frame(self):
        """Build the date range selection frame."""
        frame = self.frames["Date Range"]
        
        ttk.Label(frame, text="Date Range Selection", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 10))
        
        # Date selection
        date_frame = ttk.Frame(frame)
        date_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(date_frame, text="From:").pack(side=tk.LEFT)
        self.start_date = DateEntry(date_frame, width=12)
        self.start_date.pack(side=tk.LEFT, padx=(10, 20))
        
        ttk.Label(date_frame, text="To:").pack(side=tk.LEFT)
        self.end_date = DateEntry(date_frame, width=12)
        self.end_date.pack(side=tk.LEFT, padx=(10, 0))
        
        # Info
        info_frame = ttk.LabelFrame(frame, text="Information", padding=10)
        info_frame.pack(fill=tk.X, pady=(20, 0))
        
        info_text = """Time will be set automatically:
• Start date: 00:00:00 (beginning of day)
• End date: 23:59:59 (end of day)

This covers complete days in the selected range."""
        
        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).pack(anchor="w")

    def _build_datetime_range_frame(self):
        """Build the date and time range selection frame."""
        frame = self.frames["Date & Time Range"]
        
        ttk.Label(frame, text="Precise Date & Time Range", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 10))
        
        # Start datetime
        start_frame = ttk.LabelFrame(frame, text="Start Date & Time", padding=10)
        start_frame.pack(fill=tk.X, pady=(0, 10))
        
        start_controls = ttk.Frame(start_frame)
        start_controls.pack(fill=tk.X)
        
        ttk.Label(start_controls, text="Date:").pack(side=tk.LEFT)
        self.dt_start_date = DateEntry(start_controls, width=12)
        self.dt_start_date.pack(side=tk.LEFT, padx=(10, 20))
        
        ttk.Label(start_controls, text="Time:").pack(side=tk.LEFT)
        self.dt_start_time = ttk.Entry(start_controls, width=12)
        self.dt_start_time.insert(0, "00:00:00")
        self.dt_start_time.pack(side=tk.LEFT, padx=(10, 0))
        
        # End datetime
        end_frame = ttk.LabelFrame(frame, text="End Date & Time", padding=10)
        end_frame.pack(fill=tk.X, pady=(0, 10))
        
        end_controls = ttk.Frame(end_frame)
        end_controls.pack(fill=tk.X)
        
        ttk.Label(end_controls, text="Date:").pack(side=tk.LEFT)
        self.dt_end_date = DateEntry(end_controls, width=12)
        self.dt_end_date.pack(side=tk.LEFT, padx=(10, 20))
        
        ttk.Label(end_controls, text="Time:").pack(side=tk.LEFT)
        self.dt_end_time = ttk.Entry(end_controls, width=12)
        self.dt_end_time.insert(0, "23:59:59")
        self.dt_end_time.pack(side=tk.LEFT, padx=(10, 0))
        
        # Quick time buttons
        quick_frame = ttk.Frame(frame)
        quick_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(quick_frame, text="Quick times:").pack(side=tk.LEFT)
        
        time_buttons = [
            ("00:00:00", "00:00:00"),
            ("09:00:00", "09:00:00"),
            ("12:00:00", "12:00:00"),
            ("17:00:00", "17:00:00"),
            ("23:59:59", "23:59:59")
        ]
        
        for label, time_val in time_buttons:
            btn = ttk.Button(quick_frame, text=label, width=8,
                           command=lambda t=time_val: self._set_time_field(t))
            btn.pack(side=tk.LEFT, padx=2)

    def _build_advanced_frame(self):
        """Build the advanced (epoch) time selection frame."""
        frame = self.frames["Advanced"]
        
        ttk.Label(frame, text="Advanced Time Selection", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 10))
        
        # Epoch inputs
        epoch_frame = ttk.LabelFrame(frame, text="Epoch Timestamps", padding=10)
        epoch_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Earliest
        earliest_frame = ttk.Frame(epoch_frame)
        earliest_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(earliest_frame, text="Earliest (epoch):").pack(side=tk.LEFT, anchor="w")
        self.earliest_epoch = ttk.Entry(earliest_frame, width=15)
        self.earliest_epoch.pack(side=tk.RIGHT)
        
        # Latest  
        latest_frame = ttk.Frame(epoch_frame)
        latest_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(latest_frame, text="Latest (epoch):").pack(side=tk.LEFT, anchor="w")
        self.latest_epoch = ttk.Entry(latest_frame, width=15)
        self.latest_epoch.pack(side=tk.RIGHT)
        
        # Conversion tools
        tools_frame = ttk.LabelFrame(frame, text="Conversion Tools", padding=10)
        tools_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Current time
        current_frame = ttk.Frame(tools_frame)
        current_frame.pack(fill=tk.X, pady=2)
        
        current_epoch = int(datetime.now().timestamp())
        ttk.Label(current_frame, text=f"Current time: {current_epoch}").pack(side=tk.LEFT)
        ttk.Button(current_frame, text="Use as Latest", width=12,
                  command=lambda: self.latest_epoch.insert(0, str(current_epoch))).pack(side=tk.RIGHT)
        
        # 24 hours ago
        day_ago_frame = ttk.Frame(tools_frame)
        day_ago_frame.pack(fill=tk.X, pady=2)
        
        day_ago_epoch = int((datetime.now() - timedelta(days=1)).timestamp())
        ttk.Label(day_ago_frame, text=f"24 hours ago: {day_ago_epoch}").pack(side=tk.LEFT)
        ttk.Button(day_ago_frame, text="Use as Earliest", width=12,
                  command=lambda: self.earliest_epoch.insert(0, str(day_ago_epoch))).pack(side=tk.RIGHT)

    def _build_custom_presets_frame(self):
        """Build the custom presets management frame."""
        frame = self.frames["Custom Presets"]
        
        ttk.Label(frame, text="Custom Presets", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 10))
        
        # Custom preset list
        list_frame = ttk.LabelFrame(frame, text="Saved Presets", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Listbox with scrollbar
        listbox_frame = ttk.Frame(list_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True)
        
        self.custom_listbox = tk.Listbox(listbox_frame, height=8)
        custom_scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.custom_listbox.yview)
        self.custom_listbox.configure(yscrollcommand=custom_scrollbar.set)
        
        self.custom_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        custom_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Populate custom presets
        self._refresh_custom_presets_list()
        
        # Custom preset buttons
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Use Selected", command=self._use_custom_preset).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Delete Selected", command=self._delete_custom_preset).pack(side=tk.LEFT, padx=(10, 0))
        
        # Save current as preset
        save_frame = ttk.LabelFrame(frame, text="Save Current Selection", padding=5)
        save_frame.pack(fill=tk.X)
        
        save_input_frame = ttk.Frame(save_frame)
        save_input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(save_input_frame, text="Preset name:").pack(side=tk.LEFT)
        self.custom_name_var = tk.StringVar()
        custom_name_entry = ttk.Entry(save_input_frame, textvariable=self.custom_name_var, width=25)
        custom_name_entry.pack(side=tk.LEFT, padx=(10, 10), fill=tk.X, expand=True)
        
        ttk.Button(save_input_frame, text="Save", command=self._save_custom_preset).pack(side=tk.RIGHT)

    def show_selected_frame(self):
        """Show the selected time range input frame."""
        for frame in self.frames.values():
            frame.pack_forget()
        self.frames[self.option_var.get()].pack(fill=tk.BOTH, expand=True)

    def select_preset(self, preset):
        """Select a predefined time range preset."""
        splunk_range = self.preset_splunk_ranges.get(preset)
        if splunk_range:
            self.result = {"start": splunk_range[0], "end": splunk_range[1]}
            self.destroy()

    def _quick_select(self, start, end):
        """Quick select time range from left panel buttons."""
        self.result = {"start": start, "end": end}
        self.destroy()

    def _reset_form(self):
        """Reset all form fields to defaults."""
        # Reset relative
        self.relative_amount.delete(0, tk.END)
        self.relative_amount.insert(0, "1")
        self.relative_unit.current(1)
        
        # Reset dates to today
        today = datetime.now().date()
        self.start_date.set_date(today)
        self.end_date.set_date(today)
        self.dt_start_date.set_date(today)
        self.dt_end_date.set_date(today)
        
        # Reset times
        self.dt_start_time.delete(0, tk.END)
        self.dt_start_time.insert(0, "00:00:00")
        self.dt_end_time.delete(0, tk.END)
        self.dt_end_time.insert(0, "23:59:59")
        
        # Reset epoch fields
        self.earliest_epoch.delete(0, tk.END)
        self.latest_epoch.delete(0, tk.END)
        
        # Reset search
        self.preset_search_var.set("")

    def _preview_time_range(self):
        """Preview the selected time range."""
        try:
            preview_result = self._get_current_selection()
            if preview_result:
                start_str = self._format_time_display(preview_result['start'])
                end_str = self._format_time_display(preview_result['end'])
                
                preview_text = f"Time Range Preview:\n\nStart: {start_str}\nEnd: {end_str}"
                messagebox.showinfo("Time Range Preview", preview_text, parent=self)
            else:
                messagebox.showwarning("Preview Error", "Please configure a valid time range first.", parent=self)
        except Exception as e:
            messagebox.showerror("Preview Error", f"Error generating preview: {e}", parent=self)

    def _format_time_display(self, time_value):
        """Format time value for display."""
        if isinstance(time_value, str):
            return f"Splunk format: {time_value}"
        elif isinstance(time_value, datetime):
            return time_value.strftime("%Y-%m-%d %H:%M:%S %Z")
        else:
            return str(time_value)

    def _set_time_field(self, time_value):
        """Set time field based on current focus."""
        focused = self.focus_get()
        if focused == self.dt_start_time:
            self.dt_start_time.delete(0, tk.END)
            self.dt_start_time.insert(0, time_value)
        elif focused == self.dt_end_time:
            self.dt_end_time.delete(0, tk.END)
            self.dt_end_time.insert(0, time_value)

    def _load_custom_presets(self):
        """Load custom presets from file."""
        if os.path.exists(self.custom_presets_file):
            try:
                with open(self.custom_presets_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_custom_presets(self):
        """Save custom presets to file."""
        try:
            with open(self.custom_presets_file, 'w') as f:
                json.dump(self.custom_presets, f, indent=4)
            return True
        except Exception:
            return False

    def _refresh_custom_presets_list(self):
        """Refresh the custom presets listbox."""
        self.custom_listbox.delete(0, tk.END)
        for name in sorted(self.custom_presets.keys()):
            self.custom_listbox.insert(tk.END, name)

    def _use_custom_preset(self):
        """Use the selected custom preset."""
        selection = self.custom_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a custom preset to use.", parent=self)
            return
        
        preset_name = self.custom_listbox.get(selection[0])
        preset_data = self.custom_presets.get(preset_name)
        
        if preset_data:
            self.result = preset_data
            self.destroy()

    def _delete_custom_preset(self):
        """Delete the selected custom preset."""
        selection = self.custom_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a custom preset to delete.", parent=self)
            return
        
        preset_name = self.custom_listbox.get(selection[0])
        
        if messagebox.askyesno("Confirm Delete", f"Delete custom preset '{preset_name}'?", parent=self):
            del self.custom_presets[preset_name]
            self._save_custom_presets()
            self._refresh_custom_presets_list()

    def _save_custom_preset(self):
        """Save current selection as a custom preset."""
        name = self.custom_name_var.get().strip()
        if not name:
            messagebox.showwarning("Invalid Name", "Please enter a name for the custom preset.", parent=self)
            return
        
        try:
            current_selection = self._get_current_selection()
            if current_selection:
                self.custom_presets[name] = current_selection
                if self._save_custom_presets():
                    self._refresh_custom_presets_list()
                    self.custom_name_var.set("")
                    messagebox.showinfo("Preset Saved", f"Custom preset '{name}' saved successfully!", parent=self)
                else:
                    messagebox.showerror("Save Error", "Failed to save custom preset.", parent=self)
            else:
                messagebox.showwarning("Invalid Selection", "Please configure a valid time range first.", parent=self)
        except Exception as e:
            messagebox.showerror("Save Error", f"Error saving preset: {e}", parent=self)

    def _get_current_selection(self):
        """Get the current time range selection."""
        option = self.option_var.get()
        
        try:
            if option == "Relative":
                amount_str = self.relative_amount.get()
                if not amount_str.isdigit() or int(amount_str) < 1:
                    return None
                amount = int(amount_str)
                unit = self.relative_unit.get()
                unit_map = {
                    "minutes": "m", "hours": "h", "days": "d",
                    "weeks": "w", "months": "mon", "years": "y"
                }
                if unit not in unit_map:
                    return None
                earliest = f"-{amount}{unit_map[unit]}"
                return {"start": earliest, "end": "now"}
                
            elif option == "Date Range":
                start_date = self.start_date.get_date()
                end_date = self.end_date.get_date()
                start = self.est.localize(datetime.combine(start_date, dt_time.min))
                end = self.est.localize(datetime.combine(end_date, dt_time(23, 59, 59, 999999)))
                if end < start:
                    return None
                return {"start": start, "end": end}
                
            elif option == "Date & Time Range":
                start_date = self.dt_start_date.get_date()
                end_date = self.dt_end_date.get_date()
                start_time = self.parse_time(self.dt_start_time.get())
                end_time = self.parse_time(self.dt_end_time.get())
                start = self.est.localize(datetime.combine(start_date, start_time))
                end = self.est.localize(datetime.combine(end_date, end_time))
                if end <= start:
                    return None
                return {"start": start, "end": end}
                
            elif option == "Advanced":
                earliest_str = self.earliest_epoch.get()
                latest_str = self.latest_epoch.get()
                if not earliest_str.isdigit() or not latest_str.isdigit():
                    return None
                earliest = int(earliest_str)
                latest = int(latest_str)
                start = datetime.fromtimestamp(earliest, tz=self.est)
                end = datetime.fromtimestamp(latest, tz=self.est)
                if end <= start:
                    return None
                return {"start": start, "end": end}
                
        except Exception:
            return None
            
        return None

    def on_apply(self):
        """Validate and apply selected time range."""
        try:
            result = self._get_current_selection()
            if result:
                self.result = result
                self.destroy()
            else:
                messagebox.showerror("Invalid Input", "Please check your time range configuration.", parent=self)
        except Exception as e:
            messagebox.showerror("Input Error", f"Invalid time range: {e}", parent=self)

    def parse_time(self, time_str: str) -> dt_time:
        """Parse time string into time object."""
        try:
            parts = time_str.strip().split(':')
            if len(parts) not in (2, 3):
                raise ValueError("Invalid time format")
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2]) if len(parts) == 3 else 0
            if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
                raise ValueError("Time out of range")
            return dt_time(hour, minute, second)
        except Exception:
            raise ValueError("Time must be in HH:MM or HH:MM:SS format")

# Utility functions for time range manipulation
def splunk_time_to_datetime(splunk_time, timezone="America/New_York"):
    """Convert Splunk time string to datetime object."""
    tz = pytz.timezone(timezone)
    now = datetime.now(tz)
    
    if splunk_time == "now":
        return now
    elif splunk_time.startswith("-") and splunk_time.endswith(("m", "h", "d", "w")):
        # Parse relative time
        unit = splunk_time[-1]
        amount = int(splunk_time[1:-1])
        
        if unit == "m":
            return now - timedelta(minutes=amount)
        elif unit == "h":
            return now - timedelta(hours=amount)
        elif unit == "d":
            return now - timedelta(days=amount)
        elif unit == "w":
            return now - timedelta(weeks=amount)
    
    # Handle snap-to operations (@d, @h, etc.)
    # This is a simplified version - full implementation would be more complex
    return now

def format_time_range_display(start, end):
    """Format time range for display purposes."""
    if isinstance(start, str) and isinstance(end, str):
        return f"{start} to {end}"
    else:
        start_str = start.strftime("%Y-%m-%d %H:%M:%S") if hasattr(start, 'strftime') else str(start)
        end_str = end.strftime("%Y-%m-%d %H:%M:%S") if hasattr(end, 'strftime') else str(end)
        return f"{start_str} to {end_str}"
