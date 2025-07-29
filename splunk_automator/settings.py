import json
import os
from .config import Config

def load_settings():
    """Load app settings from file."""
    if os.path.exists(Config.SETTINGS_FILE):
        try:
            with open(Config.SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_settings(settings: dict):
    """Save settings to file."""
    with open(Config.SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
    os.chmod(Config.SETTINGS_FILE, 0o600)
