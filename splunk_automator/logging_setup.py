import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from .config import Config

def setup_logger():
    os.makedirs(Config.LOG_DIR, exist_ok=True)
    log_file = os.path.join(Config.LOG_DIR, f"analysis_{datetime.now().strftime('%Y%m%d')}.log")
    logger = logging.getLogger("SplunkAutomator")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())
    return logger

logger = setup_logger()