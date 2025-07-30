import os
import json
import base64
import hashlib
from typing import Optional, Tuple, Dict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from .logging_setup import logger
from .config import Config

class CredentialsManager:
    """Secure credentials management with encryption and validation."""
    
    def __init__(self):
        self.key_file = Config.CREDENTIALS_KEY_FILE
        self.creds_file = Config.CREDENTIALS_FILE
    
    def _get_or_create_key(self) -> bytes:
        """Get existing key or create a new one."""
        try:
            if os.path.exists(self.key_file):
                with open(self.key_file, "rb") as f:
                    key = f.read()
                    # Validate key format
                    Fernet(key)  # This will raise an exception if invalid
                    return key
        except Exception as e:
            logger.warning(f"Existing key file invalid, creating new one: {e}")
            # Remove invalid key file
            if os.path.exists(self.key_file):
                os.remove(self.key_file)
        
        # Create new key
        key = Fernet.generate_key()
        try:
            with open(self.key_file, "wb") as f:
                f.write(key)
            os.chmod(self.key_file, Config.SECURE_FILE_PERMISSIONS)
            logger.info("Created new encryption key")
        except Exception as e:
            logger.error(f"Failed to save encryption key: {e}")
            raise
        
        return key
    
    def _derive_key_from_password(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def save_credentials(self, username: str, password: str, 
                        server_url: Optional[str] = None) -> bool:
        """Save credentials securely with encryption."""
        try:
            # Validate inputs
            if not username or not password:
                raise ValueError("Username and password cannot be empty")
            
            if len(username) > 255 or len(password) > 255:
                raise ValueError("Username or password too long")
            
            # Prepare credentials data
            creds_data = {
                "username": username,
                "password": password,
                "server_url": server_url or "",
                "created_at": self._get_timestamp(),
                "last_used": None,
                "version": "2.0"
            }
            
            # Encrypt credentials
            key = self._get_or_create_key()
            f = Fernet(key)
            
            json_data = json.dumps(creds_data).encode('utf-8')
            encrypted_data = f.encrypt(json_data)
            
            # Save to file
            with open(self.creds_file, "wb") as file:
                file.write(encrypted_data)
            
            os.chmod(self.creds_file, Config.SECURE_FILE_PERMISSIONS)
            logger.info("Credentials saved securely")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            return False
    
    def load_credentials(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Load and decrypt credentials."""
        if not os.path.exists(self.creds_file):
            return None, None, None
        
        try:
            key = self._get_or_create_key()
            f = Fernet(key)
            
            with open(self.creds_file, "rb") as file:
                encrypted_data = file.read()
            
            decrypted_data = f.decrypt(encrypted_data)
            creds_data = json.loads(decrypted_data.decode('utf-8'))
            
            # Update last used timestamp
            creds_data["last_used"] = self._get_timestamp()
            self._update_last_used(creds_data, f)
            
            username = creds_data.get("username")
            password = creds_data.get("password")
            server_url = creds_data.get("server_url", "")
            
            return username, password, server_url
            
        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            return None, None, None
    
    def _update_last_used(self, creds_data: Dict, fernet: Fernet) -> None:
        """Update last used timestamp in credentials file."""
        try:
            json_data = json.dumps(creds_data).encode('utf-8')
            encrypted_data = fernet.encrypt(json_data)
            
            with open(self.creds_file, "wb") as file:
                file.write(encrypted_data)
        except Exception as e:
            logger.warning(f"Failed to update last used timestamp: {e}")
    
    def validate_credentials(self, username: str, password: str) -> Tuple[bool, str]:
        """Validate credentials format and basic requirements."""
        if not username or not username.strip():
            return False, "Username cannot be empty"
        
        if not password or not password.strip():
            return False, "Password cannot be empty"
        
        if len(username) < 2:
            return False, "Username too short"
        
        if len(password) < 3:
            return False, "Password too short"
        
        # Check for potentially dangerous characters
        dangerous_chars = ['<', '>', '"', "'", '&', '\x00']
        for char in dangerous_chars:
            if char in username or char in password:
                return False, "Invalid characters in credentials"
        
        return True, "Credentials format valid"
    
    def credentials_exist(self) -> bool:
        """Check if credentials file exists."""
        return os.path.exists(self.creds_file)
    
    def delete_credentials(self) -> bool:
        """Securely delete stored credentials."""
        try:
            if os.path.exists(self.creds_file):
                # Overwrite file with random data before deletion (basic secure delete)
                file_size = os.path.getsize(self.creds_file)
                with open(self.creds_file, "r+b") as f:
                    f.write(os.urandom(file_size))
                    f.flush()
                    os.fsync(f.fileno())
                
                os.remove(self.creds_file)
                logger.info("Credentials deleted securely")
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete credentials: {e}")
            return False
    
    def change_password(self, old_password: str, new_password: str) -> bool:
        """Change password with verification."""
        try:
            # Load current credentials
            username, current_password, server_url = self.load_credentials()
            
            if not username or current_password != old_password:
                return False
            
            # Validate new password
            valid, message = self.validate_credentials(username, new_password)
            if not valid:
                logger.error(f"New password validation failed: {message}")
                return False
            
            # Save with new password
            return self.save_credentials(username, new_password, server_url)
            
        except Exception as e:
            logger.error(f"Failed to change password: {e}")
            return False
    
    def get_credentials_info(self) -> Optional[Dict]:
        """Get metadata about stored credentials without exposing them."""
        if not os.path.exists(self.creds_file):
            return None
        
        try:
            key = self._get_or_create_key()
            f = Fernet(key)
            
            with open(self.creds_file, "rb") as file:
                encrypted_data = file.read()
            
            decrypted_data = f.decrypt(encrypted_data)
            creds_data = json.loads(decrypted_data.decode('utf-8'))
            
            return {
                "username": creds_data.get("username", "").replace(creds_data.get("username", "")[1:-1], "*" * len(creds_data.get("username", "")[1:-1])) if len(creds_data.get("username", "")) > 2 else "***",
                "server_url": creds_data.get("server_url", ""),
                "created_at": creds_data.get("created_at", "Unknown"),
                "last_used": creds_data.get("last_used", "Never"),
                "version": creds_data.get("version", "1.0")
            }
            
        except Exception as e:
            logger.error(f"Error getting credentials info: {e}")
            return None
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now(Config.UTC).isoformat()

# Backward compatibility functions
def save_credentials(username: str, password: str) -> bool:
    """Backward compatible save function."""
    manager = CredentialsManager()
    return manager.save_credentials(username, password)

def load_credentials():
    """Backward compatible load function."""
    manager = CredentialsManager()
    username, password, _ = manager.load_credentials()
    return username, password

def get_key():
    """Backward compatible key function."""
    manager = CredentialsManager()
    return manager._get_or_create_key()
