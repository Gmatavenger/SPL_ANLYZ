import os
import shutil
from datetime import datetime
from .config import Config

def ensure_dirs():
    """Ensure required directories exist."""
    for d in [Config.LOG_DIR, Config.TMP_DIR, Config.SCREENSHOT_ARCHIVE_DIR]:
        os.makedirs(d, exist_ok=True)

def archive_and_clean_tmp():
    """Move old tmp subfolders to archive and clean up stray files."""
    ensure_dirs()
    today_str = datetime.now().strftime("%Y-%m-%d")
    for folder in os.listdir(Config.TMP_DIR):
        folder_path = os.path.join(Config.TMP_DIR, folder)
        if os.path.isdir(folder_path) and folder != today_str:
            archive_path = os.path.join(Config.SCREENSHOT_ARCHIVE_DIR, folder)
            if os.path.exists(archive_path):
                shutil.rmtree(archive_path)
            shutil.move(folder_path, archive_path)
    for fname in os.listdir(Config.TMP_DIR):
        fpath = os.path.join(Config.TMP_DIR, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)

def purge_old_archives():
    """Delete screenshot archives older than retention period."""
    now = datetime.now()
    for folder in os.listdir(Config.SCREENSHOT_ARCHIVE_DIR):
        folder_path = os.path.join(Config.SCREENSHOT_ARCHIVE_DIR, folder)
        if not os.path.isdir(folder_path): continue
        try:
            folder_date = datetime.strptime(folder, "%Y-%m-%d")
            if (now - folder_date).days > Config.DAYS_TO_KEEP:
                shutil.rmtree(folder_path)
        except ValueError:
            continue
