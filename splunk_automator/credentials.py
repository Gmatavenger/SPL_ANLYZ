import os
import json
from cryptography.fernet import Fernet
from .logging_setup import logger

def get_key():
    key_file = ".secrets.key"
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(key_file, "wb") as f:
        f.write(key)
    return key

def save_credentials(username: str, password: str) -> bool:
    try:
        key = get_key()
        f = Fernet(key)
        creds = json.dumps({"username": username, "password": password}).encode()
        encrypted = f.encrypt(creds)
        with open(".secrets", "wb") as f2:
            f2.write(encrypted)
        logger.info("Credentials saved securely (encrypted).")
        return True
    except Exception as e:
        logger.error(f"Failed to save credentials: {e}")
        return False

def load_credentials():
    if not os.path.exists(".secrets"):
        return None, None
    try:
        key = get_key()
        f = Fernet(key)
        with open(".secrets", "rb") as f2:
            decrypted = f.decrypt(f2.read())
        data = json.loads(decrypted.decode())
        return data.get("username"), data.get("password")
    except Exception as e:
        logger.error(f"Error loading credentials: {e}")
        return None, None