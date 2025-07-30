import pytz
import os
from pathlib import Path

class Config:
    # Base directories
    BASE_DIR = Path.cwd()
    LOG_DIR = "logs"
    TMP_DIR = "tmp"
    SCREENSHOT_ARCHIVE_DIR = "screenshots"
    
    # Configuration files
    DASHBOARD_FILE = "dashboards.json"
    SCHEDULE_FILE = "schedule.json"
    SETTINGS_FILE = "settings.json"
    CREDENTIALS_FILE = ".secrets"
    CREDENTIALS_KEY_FILE = ".secrets.key"
    
    # Retention settings
    DAYS_TO_KEEP = 3
    MAX_LOG_SIZE_MB = 10
    MAX_ARCHIVE_SIZE_GB = 5
    
    # Timezone settings
    EST = pytz.timezone("America/New_York")
    UTC = pytz.timezone("UTC")
    
    # Browser settings
    BROWSER_TIMEOUT = 120_000  # 2 minutes
    PAGE_LOAD_TIMEOUT = 60_000  # 1 minute
    SCREENSHOT_TIMEOUT = 30_000  # 30 seconds
    MAX_CONCURRENT_BROWSERS = 3
    
    # UI settings
    DEFAULT_WINDOW_WIDTH = 1200
    DEFAULT_WINDOW_HEIGHT = 800
    TREEVIEW_HEIGHT = 12
    
    # File permissions (Unix-style)
    SECURE_FILE_PERMISSIONS = 0o600
    DIRECTORY_PERMISSIONS = 0o755
    
    # Network settings
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    
    # Dashboard detection timeouts
    STUDIO_LOAD_TIMEOUT = 60_000
    CLASSIC_LOAD_TIMEOUT = 45_000
    STABILIZATION_WAIT = 3000  # milliseconds
    
    # Screenshot settings
    DEFAULT_VIEWPORT_WIDTH = 1280
    DEFAULT_VIEWPORT_HEIGHT = 720
    MAX_SCREENSHOT_HEIGHT = 10000
    
    @classmethod
    def ensure_directories(cls):
        """Ensure all required directories exist with proper permissions."""
        directories = [
            cls.LOG_DIR,
            cls.TMP_DIR,
            cls.SCREENSHOT_ARCHIVE_DIR
        ]
        
        for directory in directories:
            os.makedirs(directory, mode=cls.DIRECTORY_PERMISSIONS, exist_ok=True)
    
    @classmethod
    def get_log_file_path(cls, date_str=None):
        """Get log file path for specific date."""
        if date_str is None:
            from datetime import datetime
            date_str = datetime.now().strftime('%Y%m%d')
        return os.path.join(cls.LOG_DIR, f"analysis_{date_str}.log")
    
    @classmethod
    def get_temp_dir_for_date(cls, date_str=None):
        """Get temp directory for specific date."""
        if date_str is None:
            from datetime import datetime
            date_str = datetime.now().strftime('%Y-%m-%d')
        return os.path.join(cls.TMP_DIR, date_str)
    
    @classmethod
    def get_archive_dir_for_date(cls, date_str=None):
        """Get archive directory for specific date."""
        if date_str is None:
            from datetime import datetime
            date_str = datetime.now().strftime('%Y-%m-%d')
        return os.path.join(cls.SCREENSHOT_ARCHIVE_DIR, date_str)
