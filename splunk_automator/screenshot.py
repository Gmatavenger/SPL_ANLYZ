import os
import io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from .splunk_automator.config import Config
from .logging_setup import logger

def save_screenshot_to_tmp(screenshot_bytes: bytes, filename: str) -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")
    day_tmp_dir = os.path.join(Config.TMP_DIR, today_str)
    os.makedirs(day_tmp_dir, exist_ok=True)
    file_path = os.path.join(day_tmp_dir, filename)
    image = Image.open(io.BytesIO(screenshot_bytes))
    draw = ImageDraw.Draw(image)
    timestamp = datetime.now(Config.EST).strftime("%Y-%m-%d %H:%M:%S %Z")
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except Exception:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
    draw.text((10, 10), f"Captured: {timestamp}", fill="white", font=font)
    image.save(file_path)
    logger.info(f"Saved screenshot to {file_path}")
    return file_path