"""
Enhanced Screenshot Management Module
Provides comprehensive screenshot capture, processing, and storage capabilities.
"""

import os
import io
import hashlib
from datetime import datetime
from typing import Optional, Tuple, Dict, List
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from .config import Config
from .logging_setup import logger

class ScreenshotProcessor:
    """Enhanced screenshot processing with multiple format support and optimization."""
    
    def __init__(self):
        self.supported_formats = ['PNG', 'JPEG', 'WEBP', 'BMP']
        self.default_quality = 85
        self.watermark_settings = {
            'position': 'bottom_right',
            'opacity': 0.7,
            'font_size': 24
        }
    
    def save_screenshot_to_tmp(self, screenshot_bytes: bytes, filename: str, 
                              dashboard_name: str = None, metadata: Dict = None) -> str:
        """Enhanced screenshot saving with metadata and optimization."""
        try:
            # Create directory structure
            today_str = datetime.now().strftime("%Y-%m-%d")
            day_tmp_dir = os.path.join(Config.TMP_DIR, today_str)
            os.makedirs(day_tmp_dir, exist_ok=True)
            
            # Process the image
            image = Image.open(io.BytesIO(screenshot_bytes))
            
            # Add timestamp watermark
            image = self._add_timestamp_watermark(image, dashboard_name)
            
            # Add metadata overlay if provided
            if metadata:
                image = self._add_metadata_overlay(image, metadata)
            
            # Optimize image
            image = self._optimize_image(image)
            
            # Save the processed image
            file_path = os.path.join(day_tmp_dir, filename)
            image.save(file_path, format='PNG', optimize=True)
            
            # Save metadata file
            self._save_metadata_file(file_path, dashboard_name, metadata)
            
            # Calculate and log file size
            file_size = os.path.getsize(file_path)
            logger.info(f"Saved screenshot to {file_path} ({self._format_file_size(file_size)})")
            
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving screenshot: {e}")
            raise
    
    def _add_timestamp_watermark(self, image: Image.Image, dashboard_name: str = None) -> Image.Image:
        """Add timestamp and dashboard name watermark to the image."""
        try:
            # Create a copy to avoid modifying the original
            img_copy = image.copy()
            draw = ImageDraw.Draw(img_copy)
            
            # Get timezone-aware timestamp
            timestamp = datetime.now(Config.EST).strftime("%Y-%m-%d %H:%M:%S %Z")
            
            # Try to load a better font
            font = self._get_watermark_font()
            
            # Prepare watermark text
            watermark_lines = [f"Captured: {timestamp}"]
            if dashboard_name:
                watermark_lines.append(f"Dashboard: {dashboard_name}")
            
            # Calculate text positioning
            img_width, img_height = img_copy.size
            line_height = 30
            total_height = len(watermark_lines) * line_height
            
            # Position at top-left with some padding
            x, y = 15, 15
            
            # Add semi-transparent background for better readability
            for i, line in enumerate(watermark_lines):
                text_y = y + (i * line_height)
                
                # Get text bounding box
                bbox = draw.textbbox((x, text_y), line, font=font)
                
                # Draw semi-transparent background
                bg_padding = 5
                draw.rectangle([
                    bbox[0] - bg_padding, bbox[1] - bg_padding,
                    bbox[2] + bg_padding, bbox[3] + bg_padding
                ], fill=(0, 0, 0, 128))
                
                # Draw text
                draw.text((x, text_y), line, fill="white", font=font)
            
            return img_copy
            
        except Exception as e:
            logger.warning(f"Error adding watermark: {e}")
            return image
    
    def _add_metadata_overlay(self, image: Image.Image, metadata: Dict) -> Image.Image:
        """Add metadata information overlay to the image."""
        try:
            if not metadata:
                return image
            
            img_copy = image.copy()
            draw = ImageDraw.Draw(img_copy)
            font = self._get_metadata_font()
            
            # Prepare metadata text
            meta_lines = []
            if 'time_range' in metadata:
                meta_lines.append(f"Time Range: {metadata['time_range']}")
            if 'search_count' in metadata:
                meta_lines.append(f"Searches: {metadata['search_count']}")
            if 'panel_count' in metadata:
                meta_lines.append(f"Panels: {metadata['panel_count']}")
            
            if not meta_lines:
                return img_copy
            
            # Position at bottom-right
            img_width, img_height = img_copy.size
            line_height = 25
            padding = 15
            
            for i, line in enumerate(reversed(meta_lines)):
                text_y = img_height - padding - ((i + 1
