import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
import re
from .config import Config
from .logging_setup import logger

class TimeRangeDialog:
    """Enhanced time range selection dialog with presets and validation."""
    
    def __init__(self, parent):
        self.parent = parent
        self.result = None
        self.dialog = None
        self._create_dialog()
    
    def _create_dialog(self):
        """Create the time range selection dialog."""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Select Time Range")
        self.dialog.geometry("450x500")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        self.dialog.resizable(False, False)
        
        # Center the dialog
        self._center_dialog()
        
        # Set up the UI
        self._setup_ui()
        
        # Set default values
        self._set_defaults()
        
        # Bind events
        self._bind_events()
    
    def _center_dialog(self):
        """Center the dialog on the parent window."""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
    
    def _setup_ui(self):
        """Set up the dialog UI components."""
        main_frame = ttk.Frame(self.dialog, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Quick presets tab
        self._create_presets_tab(notebook)
        
        # Custom range tab
        self._create_custom_tab(notebook)
        
        # Advanced tab
        self._create_advanced_tab(notebook)
        
        # Buttons frame
        self._create_buttons_frame(main_frame)
        
        # Status frame
        self._create_status_frame(main_frame)
    
    def _create_presets_tab(self, notebook):
        """Create the quick presets tab."""
        presets_frame = ttk.Frame(notebook, padding="10")
        notebook.add(presets_frame, text="Quick Presets")
        
        ttk.Label(presets_frame, text="Select a predefined time range:", 
                 font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 10))
        
        # Preset options
        self.preset_var = tk.StringVar(value="Last 24 hours")
        
        preset_options = [
            ("Last 15 minutes", "-15m@m", "now"),
            ("Last 30 minutes", "-30m@m", "now"),
            ("Last 1 hour", "-1h@h", "now"),
            ("Last 4 hours", "-4h@h", "now"),
            ("Last 24 hours", "-24h@h", "now"),
            ("Last 2 days", "-2d@d", "now"),
            ("Last 7 days", "-7d@d", "now"),
            ("Last 30 days", "-30d@d", "now"),
            ("This week", "@w0", "now"),
            ("Last week", "-1w@w0", "-0w@w0"),
            ("This month", "@mon", "now"),
            ("Last month", "-1mon@mon", "-0mon@mon"),
            ("This year", "@y", "now"),
            ("Yesterday", "-1d@d", "-0d@d"),
            ("Today", "@d", "now")
        ]
        
        self.preset_data = {}
        
        for display_name, earliest, latest in preset_options:
            rb = ttk.Radiobutton(presets_frame, text=display_name, 
                               variable=self.preset_var, value=display_name)
            rb.pack(anchor="w", pady=2)
            self.preset_data[display_name] = {"start": earliest, "end": latest}
        
        # Description frame
        desc_frame = ttk.LabelFrame(presets_frame, text="Description", padding="10")
        desc_frame.pack(fill=tk.X, pady=(20, 0))
        
        self.preset_description = tk.Text(desc_frame, height=3, wrap=tk.WORD, 
                                        state=tk.DISABLED, bg=presets_frame.cget('bg'))
        self.preset_description.pack(fill=tk.X)
        
        # Bind preset selection change
        self.preset_var.trace('w', self._on_preset_change)
    
    def _create_custom_tab(self, notebook):
        """Create the custom time range tab."""
        custom_frame = ttk.Frame(notebook, padding="10")
        notebook.add(custom_frame, text="Custom Range")
        
        # Custom range type selection
        ttk.Label(custom_frame, text="Custom Range Type:", 
                 font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 10))
        
        self.custom_type_var = tk.StringVar(value="relative")
        
        type_frame = ttk.Frame(custom_frame)
        type_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Radiobutton(type_frame, text="Relative Time", 
                       variable=self.custom_type_var, value="relative").pack(anchor="w")
        ttk.Radiobutton(type_frame, text="Absolute Time", 
                       variable=self.custom_type_var, value="absolute").pack(anchor="w")
        
        # Relative time frame
        self.relative_frame = ttk.LabelFrame(custom_frame, text="Relative Time", padding="10")
        self.relative_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Start time
        start_frame = ttk.Frame(self.relative_frame)
        start_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(start_frame, text="Start time:").pack(side=tk.LEFT)
        self.relative_start_var = tk.StringVar(value="-24h")
        ttk.Entry(start_frame, textvariable=self.relative_start_var, width=15).pack(side=tk.LEFT, padx=(10, 5))
        ttk.Label(start_frame, text="(e.g., -24h, -7d, -1w)").pack(side=tk.LEFT)
        
        # End time
        end_frame = ttk.Frame(self.relative_frame)
        end_frame.pack(fill=tk.X)
        
        ttk.Label(end_frame, text="End time:").pack(side=tk.LEFT)
        self.relative_end_var = tk.StringVar(value="now")
        ttk.Entry(end_frame, textvariable=self.relative_end_var, width=15).pack(side=tk.LEFT, padx=(10, 5))
        ttk.Label(end_frame, text="(e.g., now, -1h, -0d@d)").pack(side=tk.LEFT)
        
        # Absolute time frame
        self.absolute_frame = ttk.LabelFrame(custom_frame, text="Absolute Time", padding="10")
        self.absolute_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Start datetime
        start_abs_frame = ttk.Frame(self.absolute_frame)
        start_abs_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(start_abs_frame, text="Start date/time:").pack(anchor="w")
        start_dt_frame = ttk.Frame(start_abs_frame)
        start_dt_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.start_date_var = tk.StringVar()
        self.start_time_var = tk.StringVar(value="00:00:00")
        
        ttk.Entry(start_dt_frame, textvariable=self.start_date_var, width=12).pack(side=tk.LEFT)
        ttk.Label(start_dt_frame, text="Date (YYYY-MM-DD)").pack(side=tk.LEFT, padx=(5, 20))
        ttk.Entry(start_dt_frame, textvariable=self.start_time_var, width=10).pack(side=tk.LEFT)
        ttk.Label(start_dt_frame, text="Time (HH:MM:SS)").pack(side=tk.LEFT, padx=(5, 0))
        
        # End datetime
        end_abs_frame = ttk.Frame(self.absolute_frame)
        end_abs_frame.pack(fill=tk.X)
        
        ttk.Label(end_abs_frame, text="End date/time:").pack(anchor="w")
        end_dt_frame = ttk.Frame(end_abs_frame)
        end_dt_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.end_date_var = tk.StringVar()
        self.end_time_var = tk.StringVar(value="23:59:59")
        
        ttk.Entry(end_dt_frame, textvariable=self.end_date_var, width=12).pack(side=tk.LEFT)
        ttk.Label(end_dt_frame, text="Date (YYYY-MM-DD)").pack(side=tk.LEFT, padx=(5, 20))
        ttk.Entry(end_dt_frame, textvariable=self.end_time_var, width=10).pack(side=tk.LEFT)
        ttk.Label(end_dt_frame, text="Time (HH:MM:SS)").pack(side=tk.LEFT, padx=(5, 0))
        
        # Bind custom type change
        self.custom_type_var.trace('w', self._on_custom_type_change)
    
    def _create_advanced_tab(self, notebook):
        """Create the advanced options tab."""
        advanced_frame = ttk.Frame(notebook, padding="10")
        notebook.add(advanced_frame, text="Advanced")
        
        # Timezone selection
        tz_frame = ttk.LabelFrame(advanced_frame, text="Timezone", padding="10")
        tz_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(tz_frame, text="Timezone:").pack(anchor="w")
        self.timezone_var = tk.StringVar(value="EST")
        
        timezone_combo = ttk.Combobox(tz_frame, textvariable=self.timezone_var,
                                    values=["UTC", "EST", "PST", "CST", "MST"], 
                                    state="readonly", width=10)
        timezone_combo.pack(anchor="w", pady=(5, 0))
        
        # Snap to options
        snap_frame = ttk.LabelFrame(advanced_frame, text="Snap To", padding="10")
        snap_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.snap_to_var = tk.StringVar(value="none")
        
        snap_options = [
            ("No snapping", "none"),
            ("Snap to minute", "@m"),
            ("Snap to hour", "@h"),
            ("Snap to day", "@d"),
            ("Snap to week", "@w"),
            ("Snap to month", "@mon")
        ]
        
        for display_name, value in snap_options:
            ttk.Radiobutton(snap_frame, text=display_name, 
                          variable=self.snap_to_var, value=value).pack(anchor="w")
        
        # Time format options
        format_frame = ttk.LabelFrame(advanced_frame, text="Time Format", padding="10")
        format_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.time_format_var = tk.StringVar(value="splunk")
        
        ttk.Radiobutton(format_frame, text="Splunk relative time (e.g., -24h, now)", 
                       variable=self.time_format_var, value="splunk").pack(anchor="w")
        ttk.Radiobutton(format_frame, text="Unix timestamp (epoch)", 
                       variable=self.time_format_var, value="epoch").pack(anchor="w")
        ttk.Radiobutton(format_frame, text="ISO format (YYYY-MM-DD HH:MM:SS)", 
                       variable=self.time_format_var, value="iso").pack(anchor="w")
    
    def _create_buttons_frame(self, parent):
        """Create the buttons frame."""
        buttons_frame = ttk.Frame(parent)
        buttons_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Left side buttons
        left_buttons = ttk.Frame(buttons_frame)
        left_buttons.pack(side=tk.LEFT)
        
        ttk.Button(left_buttons, text="Validate", command=self._validate_time_range).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(left_buttons, text="Reset", command=self._reset_to_defaults).pack(side=tk.LEFT)
        
        # Right side buttons
        right_buttons = ttk.Frame(buttons_frame)
        right_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(right_buttons, text="OK", command=self._ok_clicked).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(right_buttons, text="Cancel", command=self._cancel_clicked).pack(side=tk.LEFT)
    
    def _create_status_frame(self, parent):
        """Create the status display frame."""
        status_frame = ttk.LabelFrame(parent, text="Preview", padding="10")
        status_frame.pack(fill=tk.X)
        
        self.status_text = tk.Text(status_frame, height=2, wrap=tk.WORD, 
                                 state=tk.DISABLED, bg=status_frame.cget('bg'))
        self.status_text.pack(fill=tk.X)
    
    def _set_defaults(self):
        """Set default values."""
        # Set default absolute dates to yesterday and today
        yesterday = datetime.now() - timedelta(days=1)
        today = datetime.now()
        
        self.start_date_var.set(yesterday.strftime('%Y-%m-%d'))
        self.end_date_var.set(today.strftime('%Y-%m-%d'))
        
        # Update initial state
        self._on_custom_type_change()
        self._on_preset_change()
    
    def _bind_events(self):
        """Bind events for real-time updates."""
        # Bind Enter key to OK
        self.dialog.bind('<Return>', lambda e: self._ok_clicked())
        self.dialog.bind('<Escape>', lambda e: self._cancel_clicked())
        
        # Bind variable changes for real-time preview
        for var in [self.relative_start_var, self.relative_end_var, 
                   self.start_date_var, self.start_time_var,
                   self.end_date_var, self.end_time_var]:
            var.trace('w', self._update_preview)
    
    def _on_preset_change(self, *args):
        """Handle preset selection change."""
        selected = self.preset_var.get()
        if selected in self.preset_data:
            data = self.preset_data[selected]
            description = self._get_preset_description(selected, data)
            
            self.preset_description.config(state=tk.NORMAL)
            self.preset_description.delete(1.0, tk.END)
            self.preset_description.insert(1.0, description)
            self.preset_description.config(state=tk.DISABLED)
        
        self._update_preview()
    
    def _on_custom_type_change(self, *args):
        """Handle custom type selection change."""
        if self.custom_type_var.get() == "relative":
            self.relative_frame.pack(fill=tk.X, pady=(0, 10))
            self.absolute_frame.pack_forget()
        else:
            self.absolute_frame.pack(fill=tk.X, pady=(0, 10))
            self.relative_frame.pack_forget()
        
        self._update_preview()
    
    def _get_preset_description(self, preset_name: str, data: Dict) -> str:
        """Get description for a preset."""
        descriptions = {
            "Last 15 minutes": "Data from 15 minutes ago to now",
            "Last 30 minutes": "Data from 30 minutes ago to now",
            "Last 1 hour": "Data from 1 hour ago to now",
            "Last 4 hours": "Data from 4 hours ago to now",
            "Last 24 hours": "Data from 24 hours ago to now",
            "Last 2 days": "Data from 2 days ago to now",
            "Last 7 days": "Data from 7 days ago to now",
            "Last 30 days": "Data from 30 days ago to now",
            "This week": "Data from the start of this week to now",
            "Last week": "Data from the entire previous week",
            "This month": "Data from the start of this month to now",
            "Last month": "Data from the entire previous month",
            "This year": "Data from the start of this year to now",
            "Yesterday": "Data from the entire previous day",
            "Today": "Data from the start of today to now"
        }
        
        base_desc = descriptions.get(preset_name, "Custom time range")
        splunk_format = f"Earliest: {data['start']}, Latest: {data['end']}"
        
        return f"{base_desc}\n\nSplunk format: {splunk_format}"
    
    def _update_preview(self, *args):
        """Update the preview display."""
        try:
            result = self._get_current_time_range()
            if result:
                preview_text = f"Start: {result['start']}\nEnd: {result['end']}"
            else:
                preview_text = "Invalid time range configuration"
        except Exception as e:
            preview_text = f"Error: {str(e)}"
        
        self.status_text.config(state=tk.NORMAL)
        self.status_text.delete(1.0, tk.END)
        self.status_text.insert(1.0, preview_text)
        self.status_text.config(state=tk.DISABLED)
    
    def _get_current_time_range(self) -> Optional[Dict[str, str]]:
        """Get the current time range configuration."""
        notebook = self.dialog.nametowidget(self.dialog.winfo_children()[0].winfo_children()[0])
        current_tab = notebook.index(notebook.select())
        
        if current_tab == 0:  # Presets tab
            selected = self.preset_var.get()
            if selected in self.preset_data:
                data = self.preset_data[selected]
                return {"start": data["start"], "end": data["end"]}
        
        elif current_tab == 1:  # Custom tab
            if self.custom_type_var.get() == "relative":
                start = self.relative_start_var.get().strip()
                end = self.relative_end_var.get().strip()
                
                if self._validate_relative_time(start) and self._validate_relative_time(end):
                    return {"start": start, "end": end}
            
            else:  # Absolute time
                try:
                    start_date = self.start_date_var.get().strip()
                    start_time = self.start_time_var.get().strip()
                    end_date = self.end_date_var.get().strip()
                    end_time = self.end_time_var.get().strip()
                    
                    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M:%S")
                    end_dt = datetime.strptime(f"{end_date} {end_time}", "%Y-%m-%d %H:%M:%S")
                    
                    if start_dt >= end_dt:
                        return None
                    
                    # Format based on selected format
                    format_type = self.time_format_var.get()
                    if format_type == "epoch":
                        start_str = str(int(start_dt.timestamp()))
                        end_str = str(int(end_dt.timestamp()))
                    elif format_type == "iso":
                        start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                        end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:  # splunk format
                        start_str = str(int(start_dt.timestamp()))
                        end_str = str(int(end_dt.timestamp()))
                    
                    return {"start": start_str, "end": end_str}
                
                except ValueError:
                    return None
        
        return None
    
    def _validate_relative_time(self, time_str: str) -> bool:
        """Validate relative time format."""
        if not time_str:
            return False
        
        if time_str.lower() == "now":
            return True
        
        # Pattern for relative time: -<number><unit>[@<snap>]
        pattern = r'^-?\d+[smhdwMy](@[smhdwMy](\d+)?)?
            
        if re.match(pattern, time_str):
            return True
        
        # Pattern for snap to beginning: @<unit>
        snap_pattern = r'^@[smhdwMy](\d+)?
            
        if re.match(snap_pattern, time_str):
            return True
        
        return False
    
    def _validate_time_range(self):
        """Validate the current time range configuration."""
        result = self._get_current_time_range()
        
        if result:
            messagebox.showinfo("Validation Result", 
                               f"Time range is valid!\n\nStart: {result['start']}\nEnd: {result['end']}", 
                               parent=self.dialog)
        else:
            messagebox.showerror("Validation Error", 
                               "Invalid time range configuration. Please check your inputs.", 
                               parent=self.dialog)
    
    def _reset_to_defaults(self):
        """Reset all fields to default values."""
        # Reset preset
        self.preset_var.set("Last 24 hours")
        
        # Reset custom relative
        self.relative_start_var.set("-24h")
        self.relative_end_var.set("now")
        
        # Reset custom absolute
        yesterday = datetime.now() - timedelta(days=1)
        today = datetime.now()
        
        self.start_date_var.set(yesterday.strftime('%Y-%m-%d'))
        self.start_time_var.set("00:00:00")
        self.end_date_var.set(today.strftime('%Y-%m-%d'))
        self.end_time_var.set("23:59:59")
        
        # Reset advanced options
        self.timezone_var.set("EST")
        self.snap_to_var.set("none")
        self.time_format_var.set("splunk")
        self.custom_type_var.set("relative")
        
        # Update UI
        self._on_custom_type_change()
        self._on_preset_change()
    
    def _ok_clicked(self):
        """Handle OK button click."""
        result = self._get_current_time_range()
        
        if result:
            self.result = result
            logger.info(f"Time range selected: {result['start']} to {result['end']}")
            self.dialog.destroy()
        else:
            messagebox.showerror("Invalid Time Range", 
                               "Please enter a valid time range configuration.", 
                               parent=self.dialog)
    
    def _cancel_clicked(self):
        """Handle Cancel button click."""
        self.result = None
        self.dialog.destroy()

class TimeRangeValidator:
    """Utility class for validating and parsing time ranges."""
    
    @staticmethod
    def validate_splunk_time(time_str: str) -> Tuple[bool, str]:
        """Validate Splunk time format."""
        if not time_str or not isinstance(time_str, str):
            return False, "Time string cannot be empty"
        
        time_str = time_str.strip()
        
        # "now" is always valid
        if time_str.lower() == "now":
            return True, "Valid"
        
        # Relative time patterns
        relative_patterns = [
            r'^-\d+[smhdwMy]
            ,           # -24h, -7d, etc.
            r'^-\d+[smhdwMy]@[smhdwMy]
            , # -24h@h, -7d@d, etc.
            r'^@[smhdwMy]
            ,              # @h, @d, etc.
            r'^@[smhdwMy]\d+
                        # @w0, @w1, etc.
        ]
        
        for pattern in relative_patterns:
            if re.match(pattern, time_str):
                return True, "Valid relative time format"
        
        # Epoch timestamp
        try:
            timestamp = int(time_str)
            if 0 <= timestamp <= 2147483647:  # Valid Unix timestamp range
                return True, "Valid epoch timestamp"
        except ValueError:
            pass
        
        return False, f"Invalid time format: {time_str}"
    
    @staticmethod
    def parse_relative_time(time_str: str) -> Optional[timedelta]:
        """Parse relative time string to timedelta."""
        if not time_str or time_str.lower() == "now":
            return timedelta(0)
        
        # Extract number and unit
        match = re.match(r'^-?(\d+)([smhdwMy])', time_str)
        if not match:
            return None
        
        value = int(match.group(1))
        unit = match.group(2)
        
        unit_multipliers = {
            's': timedelta(seconds=1),
            'm': timedelta(minutes=1),
            'h': timedelta(hours=1),
            'd': timedelta(days=1),
            'w': timedelta(weeks=1),
            'M': timedelta(days=30),  # Approximate month
            'y': timedelta(days=365)  # Approximate year
        }
        
        if unit in unit_multipliers:
            return value * unit_multipliers[unit]
        
        return None
    
    @staticmethod
    def format_time_for_display(time_str: str) -> str:
        """Format time string for user display."""
        try:
            # Try to parse as epoch timestamp
            timestamp = int(time_str)
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            pass
        
        # Return as-is for relative times
        return time_str
    
    @staticmethod
    def get_time_range_duration(start: str, end: str) -> Optional[str]:
        """Calculate and format the duration of a time range."""
        try:
            if start.lower() == "now" or end.lower() == "now":
                return "Duration includes 'now' - cannot calculate exact duration"
            
            # Try parsing as epoch timestamps
            try:
                start_ts = int(start)
                end_ts = int(end)
                duration_seconds = end_ts - start_ts
                
                if duration_seconds < 0:
                    return "Invalid: End time is before start time"
                
                return TimeRangeValidator._format_duration(duration_seconds)
            except ValueError:
                pass
            
            # Try parsing relative times
            start_delta = TimeRangeValidator.parse_relative_time(start)
            end_delta = TimeRangeValidator.parse_relative_time(end)
            
            if start_delta is not None and end_delta is not None:
                duration = abs(end_delta - start_delta)
                return TimeRangeValidator._format_duration(duration.total_seconds())
            
            return "Cannot calculate duration for this time range format"
            
        except Exception as e:
            return f"Error calculating duration: {e}"
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in seconds to human readable format."""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''}"
        else:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''}"

class TimeRangePresets:
    """Predefined time range presets for common use cases."""
    
    COMMON_PRESETS = {
        "realtime": {
            "name": "Real-time (last 30 seconds)",
            "start": "-30s",
            "end": "now",
            "description": "Continuously updated data from the last 30 seconds"
        },
        "last_5min": {
            "name": "Last 5 minutes",
            "start": "-5m@m",
            "end": "now",
            "description": "Data from 5 minutes ago to now"
        },
        "last_hour": {
            "name": "Last hour",
            "start": "-1h@h",
            "end": "now",
            "description": "Data from 1 hour ago to now"
        },
        "business_hours": {
            "name": "Today's business hours",
            "start": "@d+9h",
            "end": "@d+17h",
            "description": "Today from 9 AM to 5 PM"
        },
        "last_business_day": {
            "name": "Last business day",
            "start": "-1d@d+9h",
            "end": "-1d@d+17h",
            "description": "Previous day from 9 AM to 5 PM"
        }
    }
    
    @classmethod
    def get_preset(cls, preset_key: str) -> Optional[Dict]:
        """Get a preset configuration by key."""
        return cls.COMMON_PRESETS.get(preset_key)
    
    @classmethod
    def get_all_presets(cls) -> Dict:
        """Get all available presets."""
        return cls.COMMON_PRESETS.copy()
    
    @classmethod
    def add_custom_preset(cls, key: str, name: str, start: str, end: str, description: str = ""):
        """Add a custom preset."""
        cls.COMMON_PRESETS[key] = {
            "name": name,
            "start": start,
            "end": end,
            "description": description
        }

# Utility functions for backward compatibility
def create_time_range_dialog(parent) -> Optional[Dict[str, str]]:
    """Create and show time range dialog, return selected range or None."""
    dialog = TimeRangeDialog(parent)
    parent.wait_window(dialog.dialog)
    return dialog.result

def validate_time_range(start: str, end: str) -> Tuple[bool, str]:
    """Validate a time range."""
    start_valid, start_msg = TimeRangeValidator.validate_splunk_time(start)
    if not start_valid:
        return False, f"Invalid start time: {start_msg}"
    
    end_valid, end_msg = TimeRangeValidator.validate_splunk_time(end)
    if not end_valid:
        return False, f"Invalid end time: {end_msg}"
    
    return True, "Time range is valid"
