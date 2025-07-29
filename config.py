import pytz

class Config:
    LOG_DIR = "logs"
    TMP_DIR = "tmp"
    SCREENSHOT_ARCHIVE_DIR = "screenshots"
    DASHBOARD_FILE = "dashboards.json"
    SCHEDULE_FILE = "schedule.json"
    SETTINGS_FILE = "settings.json"
    DAYS_TO_KEEP = 3
    EST = pytz.timezone("America/New_York")