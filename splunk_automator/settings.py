"""
Enhanced Settings Management Module
Provides comprehensive application settings with validation, encryption, and backup.
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, Any, Optional, List
from cryptography.fernet import Fernet
from .config import Config
from .logging_setup import logger

class SettingsManager:
    """Enhanced settings management with encryption and validation."""
    
    def __init__(self):
        self.settings_schema = self._get_settings_schema()
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher_suite = Fernet(self.encryption_key) if self.encryption_key else None
        
    def _get_settings_schema(self) -> Dict:
        """Define the settings schema with types and defaults."""
        return {
            # UI Settings
            "geometry": {"type": str, "default": "800x600+100+100"},
            "theme": {"type": str, "default": "default", "choices": ["default", "dark", "light"]},
            "font_size": {"type": int, "default": 10, "min": 8, "max": 16},
            "auto_save": {"type": bool, "default": True},
            
            # Dashboard Settings
            "last_group": {"type": str, "default": "All"},
            "dashboard_selections": {"type": dict, "default": {}},
            "default_timeout": {"type": int, "default": 60, "min": 10, "max": 300},
            "default_retry_count": {"type": int, "default": 3, "min": 1, "max": 10},
            
            # Screenshot Settings
            "screenshot_quality": {"type": int, "default": 85, "min": 50, "max": 100},
            "screenshot_format": {"type": str, "default": "PNG", "choices": ["PNG", "JPEG", "WEBP"]},
            "add_watermark": {"type": bool, "default": True},
            "optimize_images": {"type": bool, "default": True},
            "max_image_width": {"type": int, "default": 1920, "min": 800, "max": 4096},
            "max_image_height": {"type": int, "default": 1080, "min": 600, "max": 2160},
            
            # Browser Settings
            "browser_type": {"type": str, "default": "chromium", "choices": ["chromium", "firefox", "webkit"]},
            "headless_mode": {"type": bool, "default": True},
            "page_load_timeout": {"type": int, "default": 30, "min": 10, "max": 120},
            "wait_for_network_idle": {"type": bool, "default": True},
            "viewport_width": {"type": int, "default": 1920, "min": 800, "max": 4096},
            "viewport_height": {"type": int, "default": 1080, "min": 600, "max": 2160},
            
            # Analysis Settings
            "max_concurrent_browsers": {"type": int, "default": 3, "min": 1, "max": 10},
            "analysis_delay": {"type": int, "default": 2, "min": 0, "max": 10},
            "enable_panel_detection": {"type": bool, "default": True},
            "enable_error_detection": {"type": bool, "default": True},
            
            # Archive Settings
            "auto_archive": {"type": bool, "default": True},
            "archive_retention_days": {"type": int, "default": 30, "min": 1, "max": 365},
            "compression_level": {"type": int, "default": 6, "min": 1, "max": 9},
            
            # Email Settings (encrypted)
            "email_settings": {
                "type": dict, 
                "default": {}, 
                "encrypted": True,
                "schema": {
                    "smtp_server": {"type": str, "default": ""},
                    "smtp_port": {"type": int, "default": 587},
                    "use_tls": {"type": bool, "default": True},
                    "username": {"type": str, "default": ""},
                    "password": {"type": str, "default": ""},
                    "from_address": {"type": str, "default": ""}
                }
            },
            
            # Advanced Settings
            "debug_mode": {"type": bool, "default": False},
            "log_level": {"type": str, "default": "INFO", "choices": ["DEBUG", "INFO", "WARNING", "ERROR"]},
            "performance_monitoring": {"type": bool, "default": False},
            "backup_settings": {"type": bool, "default": True},
            
            # Version and metadata
            "settings_version": {"type": str, "default": "2.1.0"},
            "last_updated": {"type": str, "default": ""},
            "install_date": {"type": str, "default": ""}
        }
    
    def _get_or_create_encryption_key(self) -> Optional[bytes]:
        """Get or create encryption key for sensitive settings."""
        key_file = os.path.join(Config.DATA_DIR, '.settings_key')
        
        try:
            if os.path.exists(key_file):
                with open(key_file, 'rb') as f:
                    return f.read()
            else:
                # Generate new key
                key = Fernet.generate_key()
                with open(key_file, 'wb') as f:
                    f.write(key)
                os.chmod(key_file, 0o600)  # Secure permissions
                logger.info("Generated new encryption key")
                return key
                
        except Exception as e:
            logger.warning(f"Failed to handle encryption key: {e}")
            return None
    
    def load_settings(self) -> Dict[str, Any]:
        """Load settings with validation and migration."""
        if os.path.exists(Config.SETTINGS_FILE):
            try:
                with open(Config.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    raw_settings = json.load(f)
                
                # Migrate settings if needed
                settings = self._migrate_settings(raw_settings)
                
                # Validate and apply defaults
                settings = self._validate_and_apply_defaults(settings)
                
                # Decrypt encrypted settings
                settings = self._decrypt_sensitive_settings(settings)
                
                logger.info("Settings loaded successfully")
                return settings
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error in settings file: {e}")
                return self._attempt_backup_recovery()
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
                return self._attempt_backup_recovery()
        
        logger.info("No settings file found, using defaults")
        return self._get_default_settings()
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """Save settings with validation, encryption, and backup."""
        try:
            # Create backup before saving
            if settings.get("backup_settings", True):
                self._create_backup()
            
            # Validate settings
            validated_settings = self._validate_settings(settings)
            
            # Update metadata
            validated_settings["last_updated"] = datetime.now().isoformat()
            if "install_date" not in validated_settings or not validated_settings["install_date"]:
                validated_settings["install_date"] = datetime.now().isoformat()
            
            # Encrypt sensitive settings
            settings_to_save = self._encrypt_sensitive_settings(validated_settings.copy())
            
            # Write to temporary file first
            temp_file = Config.SETTINGS_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
            
            # Atomic move to final location
            shutil.move(temp_file, Config.SETTINGS_FILE)
            
            # Set secure permissions
            os.chmod(Config.SETTINGS_FILE, 0o600)
            
            logger.info("Settings saved successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            # Clean up temp file if it exists
            temp_file = Config.SETTINGS_FILE + '.tmp'
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            return False
    
    def _validate_and_apply_defaults(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Validate settings against schema and apply defaults."""
        validated = {}
        
        for key, schema in self.settings_schema.items():
            if key in settings:
                value = settings[key]
                
                # Type validation
                expected_type = schema["type"]
                if expected_type == dict and isinstance(value, dict):
                    if "schema" in schema:
                        # Nested validation
                        validated[key] = self._validate_nested_dict(value, schema["schema"])
                    else:
                        validated[key] = value
                elif isinstance(value, expected_type):
                    # Range validation
                    if expected_type == int:
                        if "min" in schema and value < schema["min"]:
                            value = schema["min"]
                        if "max" in schema and value > schema["max"]:
                            value = schema["max"]
                    
                    # Choice validation
                    if "choices" in schema and value not in schema["choices"]:
                        value = schema["default"]
                    
                    validated[key] = value
                else:
                    # Type mismatch, use default
                    logger.warning(f"Type mismatch for setting '{key}', using default")
                    validated[key] = schema["default"]
            else:
                # Missing setting, use default
                validated[key] = schema["default"]
        
        return validated
    
    def _validate_nested_dict(self, value: Dict, schema: Dict) -> Dict:
        """Validate nested dictionary settings."""
        validated = {}
        
        for nested_key, nested_schema in schema.items():
            if nested_key in value:
                nested_value = value[nested_key]
                expected_type = nested_schema["type"]
                
                if isinstance(nested_value, expected_type):
                    validated[nested_key] = nested_value
                else:
                    validated[nested_key] = nested_schema["default"]
            else:
                validated[nested_key] = nested_schema["default"]
        
        return validated
    
    def _validate_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Validate settings before saving."""
        return self._validate_and_apply_defaults(settings)
    
    def _get_default_settings(self) -> Dict[str, Any]:
        """Get default settings based on schema."""
        defaults = {}
        for key, schema in self.settings_schema.items():
            if schema["type"] == dict and "schema" in schema:
                # Handle nested defaults
                nested_defaults = {}
                for nested_key, nested_schema in schema["schema"].items():
                    nested_defaults[nested_key] = nested_schema["default"]
                defaults[key] = nested_defaults
            else:
                defaults[key] = schema["default"]
        
        # Set initial timestamps
        now = datetime.now().isoformat()
        defaults["last_updated"] = now
        defaults["install_date"] = now
        
        return defaults
    
    def _encrypt_sensitive_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive settings before saving."""
        if not self.cipher_suite:
            return settings
        
        settings_copy = settings.copy()
        
        for key, schema in self.settings_schema.items():
            if schema.get("encrypted", False) and key in settings_copy:
                try:
                    # Convert to JSON string and encrypt
                    json_str = json.dumps(settings_copy[key])
                    encrypted_data = self.cipher_suite.encrypt(json_str.encode())
                    settings_copy[key] = encrypted_data.decode()
                except Exception as e:
                    logger.warning(f"Failed to encrypt setting '{key}': {e}")
        
        return settings_copy
    
    def _decrypt_sensitive_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive settings after loading."""
        if not self.cipher_suite:
            return settings
        
        settings_copy = settings.copy()
        
        for key, schema in self.settings_schema.items():
            if schema.get("encrypted", False) and key in settings_copy:
                try:
                    # Decrypt and parse JSON
                    encrypted_data = settings_copy[key].encode()
                    decrypted_data = self.cipher_suite.decrypt(encrypted_data)
                    settings_copy[key] = json.loads(decrypted_data.decode())
                except Exception as e:
                    logger.warning(f"Failed to decrypt setting '{key}': {e}")
                    # Use default value if decryption fails
                    settings_copy[key] = schema["default"]
        
        return settings_copy
    
    def _migrate_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate settings from older versions."""
        current_version = settings.get("settings_version", "1.0.0")
        
        if current_version < "2.0.0":
            # Migration from v1.x to v2.x
            logger.info("Migrating settings from v1.x to v2.x")
            
            # Rename old settings
            if "window_geometry" in settings:
                settings["geometry"] = settings.pop("window_geometry")
            
            # Convert old boolean values
            if "enable_debug" in settings:
                settings["debug_mode"] = settings.pop("enable_debug")
        
        if current_version < "2.1.0":
            # Migration from v2.0.x to v2.1.
