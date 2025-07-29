import tkinter as tk
from tkinter import ttk, messagebox, Toplevel
from datetime import datetime, time as dt_time
import pytz

try:
    from tkcalendar import DateEntry
except ImportError:
    raise ImportError("tkcalendar is required for TimeRangeDialog.")

class TimeRangeDialog(Toplevel):
    def __init__(self, parent, timezone="America/New_York"):
        super().__init__(parent)
        self.title("Select Time Range (EST)")
        self.geometry("700x500")
        self.result = {}
        self.est = pytz.timezone(timezone)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame, width=150)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        options = ["Presets", "Relative", "Date Range", "Date & Time Range", "Advanced"]
        self.option_var = tk.StringVar(value=options[0])

        for option in options:
            rb = ttk.Radiobutton(left_frame, text=option, variable=self.option_var, value=option, command=self.show_selected_frame)
            rb.pack(anchor="w", pady=5)

        self.content_frame = ttk.Frame(main_frame)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.frames = {option: ttk.Frame(self.content_frame) for option in options}
        self.build_presets_frame(self.frames["Presets"])
        self.build_relative_frame(self.frames["Relative"])
        self.build_date_range_frame(self.frames["Date Range"])
        self.build_datetime_range_frame(self.frames["Date & Time Range"])
        self.build_advanced_frame(self.frames["Advanced"])

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btn_frame, text="Apply", command=self.on_apply).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)

        self.show_selected_frame()
        self.focus_set()

    def show_selected_frame(self):
        for frame in self.frames.values():
            frame.pack_forget()
        self.frames[self.option_var.get()].pack(fill=tk.BOTH, expand=True)

    def build_presets_frame(self, parent):
        self.preset_splunk_ranges = {
            "Last 15 minutes": ("-15m@m", "now"),
            "Last 60 minutes": ("-60m@m", "now"),
            "Last 4 hours": ("-4h@h", "now"),
            "Last 24 hours": ("-24h@h", "now"),
            "Last 7 days": ("-7d@d", "now"),
            "Last 30 days": ("-30d@d", "now"),
            "Today": ("@d", "now"),
            "Yesterday": ("-1d@d", "@d"),
            "Previous week": ("-1w@w", "@w"),
            "Previous month": ("-1mon@mon", "@mon"),
            "Previous year": ("-1y@y", "@y"),
            "Week to date": ("@w", "now"),
            "Month to date": ("@mon", "now"),
            "Year to date": ("@y", "now"),
            "All time": ("0", "now"),
        }
        presets = list(self.preset_splunk_ranges.keys())
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        for i, preset in enumerate(presets):
            btn = ttk.Button(
                scrollable_frame, 
                text=preset, 
                width=20,
                command=lambda p=preset: self.select_preset(p)
            )
            btn.pack(pady=2, padx=10, fill=tk.X)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def build_relative_frame(self, parent):
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Time range from now back to:").pack(anchor="w")
        options_frame = ttk.Frame(frame)
        options_frame.pack(fill=tk.X, pady=5)
        self.relative_amount = ttk.Entry(options_frame, width=5)
        self.relative_amount.pack(side=tk.LEFT, padx=2)
        self.relative_amount.insert(0, "1")
        units = ["minutes", "hours", "days", "weeks", "months", "years"]
        self.relative_unit = ttk.Combobox(options_frame, values=units, state="readonly", width=8)
        self.relative_unit.current(1)
        self.relative_unit.pack(side=tk.LEFT, padx=2)
        ttk.Label(options_frame, text="ago until now").pack(side=tk.LEFT, padx=5)

    def build_date_range_frame(self, parent):
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Date Range").pack(anchor="w")
        controls_frame = ttk.Frame(frame)
        controls_frame.pack(fill=tk.X, pady=10)
        ttk.Label(controls_frame, text="Between").pack(side=tk.LEFT)
        self.start_date = DateEntry(controls_frame)
        self.start_date.pack(side=tk.LEFT, padx=5)
        ttk.Label(controls_frame, text="and").pack(side=tk.LEFT, padx=5)
        self.end_date = DateEntry(controls_frame)
        self.end_date.pack(side=tk.LEFT, padx=5)
        ttk.Label(controls_frame, text="(00:00:00 to 23:59:59)").pack(side=tk.LEFT, padx=5)

    def build_datetime_range_frame(self, parent):
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Date & Time Range").pack(anchor="w")
        start_frame = ttk.Frame(frame)
        start_frame.pack(fill=tk.X, pady=5)
        ttk.Label(start_frame, text="Earliest:").pack(side=tk.LEFT)
        self.dt_start_date = DateEntry(start_frame)
        self.dt_start_date.pack(side=tk.LEFT, padx=5)
        self.dt_start_time = ttk.Entry(start_frame, width=12)
        self.dt_start_time.insert(0, "00:00:00")
        self.dt_start_time.pack(side=tk.LEFT, padx=5)
        end_frame = ttk.Frame(frame)
        end_frame.pack(fill=tk.X, pady=5)
        ttk.Label(end_frame, text="Latest:").pack(side=tk.LEFT)
        self.dt_end_date = DateEntry(end_frame)
        self.dt_end_date.pack(side=tk.LEFT, padx=5)
        self.dt_end_time = ttk.Entry(end_frame, width=12)
        self.dt_end_time.insert(0, "23:59:59")
        self.dt_end_time.pack(side=tk.LEFT, padx=5)

    def build_advanced_frame(self, parent):
        frame = ttk.Frame(parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Advanced Time Range").pack(anchor="w")
        epoch_frame = ttk.Frame(frame)
        epoch_frame.pack(fill=tk.X, pady=10)
        ttk.Label(epoch_frame, text="Earliest (epoch):").grid(row=0, column=0, sticky="w")
        self.earliest_epoch = ttk.Entry(epoch_frame)
        self.earliest_epoch.grid(row=0, column=1, padx=5)
        ttk.Label(epoch_frame, text="Latest (epoch):").grid(row=1, column=0, sticky="w", pady=5)
        self.latest_epoch = ttk.Entry(epoch_frame)
        self.latest_epoch.grid(row=1, column=1, padx=5)

    def select_preset(self, preset):
        splunk_range = self.preset_splunk_ranges.get(preset)
        if splunk_range:
            self.result = {"start": splunk_range[0], "end": splunk_range[1]}
        self.destroy()

    def on_apply(self):
        try:
            now = datetime.now(self.est)
            option = self.option_var.get()
            if option == "Relative":
                amount_str = self.relative_amount.get()
                if not amount_str.isdigit() or int(amount_str) < 1:
                    raise ValueError("Relative amount must be a positive integer.")
                amount = int(amount_str)
                unit = self.relative_unit.get()
                unit_map = {
                    "minutes": "m",
                    "hours": "h",
                    "days": "d",
                    "weeks": "w",
                    "months": "mon",
                    "years": "y",
                }
                if unit not in unit_map:
                    raise ValueError("Invalid unit selected.")
                splunk_unit = unit_map[unit]
                earliest = f"-{amount}{splunk_unit}"
                self.result = {"start": earliest, "end": "now"}
            elif option == "Date Range":
                start_date = self.start_date.get_date()
                end_date = self.end_date.get_date()
                start = self.est.localize(datetime.combine(start_date, dt_time.min))
                end = self.est.localize(datetime.combine(end_date, dt_time(23, 59, 59, 999999)))
                if end < start:
                    raise ValueError("End date cannot be before start date.")
                self.result = {"start": start, "end": end}
            elif option == "Date & Time Range":
                start_date = self.dt_start_date.get_date()
                end_date = self.dt_end_date.get_date()
                start_time = self.parse_time(self.dt_start_time.get())
                end_time = self.parse_time(self.dt_end_time.get())
                start = self.est.localize(datetime.combine(start_date, start_time))
                end = self.est.localize(datetime.combine(end_date, end_time))
                if end <= start:
                    raise ValueError("Latest time must be after earliest time.")
                self.result = {"start": start, "end": end}
            elif option == "Advanced":
                earliest_str = self.earliest_epoch.get()
                latest_str = self.latest_epoch.get()
                if not earliest_str.isdigit() or not latest_str.isdigit():
                    raise ValueError("Epoch values must be valid integer timestamps.")
                earliest = int(earliest_str)
                latest = int(latest_str)
                start = datetime.fromtimestamp(earliest, tz=self.est)
                end = datetime.fromtimestamp(latest, tz=self.est)
                if end <= start:
                    raise ValueError("Latest epoch must be after earliest epoch.")
                self.result = {"start": start, "end": end}
            self.destroy()
        except Exception as e:
            messagebox.showerror("Input Error", f"Invalid time range: {e}", parent=self)

    def parse_time(self, time_str: str) -> dt_time:
        try:
            parts = time_str.strip().split(':')
            if len(parts) not in (2, 3):
                raise ValueError
            hour = int(parts[0])
            minute = int(parts[1])
            second = int(parts[2]) if len(parts) == 3 else 0
            if not (0 <= hour < 24 and 0 <= minute < 60 and 0 <= second < 60):
                raise ValueError
            return dt_time(hour, minute, second)
        except Exception:
            raise ValueError("Time must be in HH:MM or HH:MM:SS format and within valid time ranges.")