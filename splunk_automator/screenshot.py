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
                text_y = img_height - padding - ((i + 1) * line_height)
                
                # Get text dimensions
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                text_x = img_width - text_width - padding
                
                # Draw semi-transparent background
                bg_padding = 3
                draw.rectangle([
                    text_x - bg_padding, text_y - bg_padding,
                    text_x + text_width + bg_padding, text_y + line_height - bg_padding
                ], fill=(0, 0, 0, 100))
                
                # Draw text
                draw.text((text_x, text_y), line, fill="lightgray", font=font)
            
            return img_copy
            
        except Exception as e:
            logger.warning(f"Error adding metadata overlay: {e}")
            return image
    
    def _get_watermark_font(self):
        """Get the best available font for watermarks."""
        font_size = self.watermark_settings['font_size']
        
        # Try different font paths
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",  # Windows
            "/System/Library/Fonts/Arial.ttf",  # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
            "/usr/share/fonts/TTF/arial.ttf",  # Some Linux distributions
        ]
        
        for font_path in font_paths:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, font_size)
            except Exception:
                continue
        
        # Fallback to default font
        try:
            return ImageFont.load_default()
        except Exception:
            return None
    
    def _get_metadata_font(self):
        """Get font for metadata overlay."""
        try:
            font = self._get_watermark_font()
            if font and hasattr(font, 'size'):
                # Use smaller font for metadata
                return font.font_variant(size=18)
            return font
        except Exception:
            return self._get_watermark_font()
    
    def _optimize_image(self, image: Image.Image) -> Image.Image:
        """Optimize image for storage and display."""
        try:
            # Convert to RGB if necessary (for JPEG compatibility)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Create white background for transparency
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # Resize if image is too large
            max_width, max_height = 1920, 1080
            if image.width > max_width or image.height > max_height:
                image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                logger.info(f"Resized image to {image.width}x{image.height}")
            
            return image
            
        except Exception as e:
            logger.warning(f"Error optimizing image: {e}")
            return image
    
    def _save_metadata_file(self, image_path: str, dashboard_name: str = None, metadata: Dict = None):
        """Save metadata as a separate JSON file."""
        try:
            metadata_path = image_path.replace('.png', '.meta.json')
            
            meta_data = {
                'timestamp': datetime.now().isoformat(),
                'dashboard_name': dashboard_name,
                'image_path': image_path,
                'file_size': os.path.getsize(image_path),
                'image_dimensions': None
            }
            
            # Add image dimensions
            try:
                with Image.open(image_path) as img:
                    meta_data['image_dimensions'] = {'width': img.width, 'height': img.height}
            except Exception:
                pass
            
            # Add custom metadata
            if metadata:
                meta_data.update(metadata)
            
            import json
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(meta_data, f, indent=2)
                
        except Exception as e:
            logger.warning(f"Error saving metadata file: {e}")
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def create_screenshot_comparison(self, screenshot_paths: List[str], output_path: str) -> bool:
        """Create a comparison image from multiple screenshots."""
        try:
            if not screenshot_paths:
                return False
            
            images = []
            for path in screenshot_paths:
                if os.path.exists(path):
                    img = Image.open(path)
                    images.append(img)
            
            if not images:
                return False
            
            # Calculate layout
            cols = min(2, len(images))
            rows = (len(images) + cols - 1) // cols
            
            # Get maximum dimensions
            max_width = max(img.width for img in images)
            max_height = max(img.height for img in images)
            
            # Create comparison image
            comparison_width = max_width * cols + 20 * (cols - 1)
            comparison_height = max_height * rows + 20 * (rows - 1)
            
            comparison = Image.new('RGB', (comparison_width, comparison_height), 'white')
            
            # Paste images
            for i, img in enumerate(images):
                row = i // cols
                col = i % cols
                x = col * (max_width + 20)
                y = row * (max_height + 20)
                comparison.paste(img, (x, y))
            
            comparison.save(output_path, format='PNG', optimize=True)
            logger.info(f"Created comparison image: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating screenshot comparison: {e}")
            return False
    
    def apply_image_filters(self, image_path: str, filters: List[str]) -> str:
        """Apply image filters and save the result."""
        try:
            with Image.open(image_path) as img:
                processed_img = img.copy()
                
                for filter_name in filters:
                    if filter_name == 'sharpen':
                        processed_img = processed_img.filter(ImageFilter.SHARPEN)
                    elif filter_name == 'blur':
                        processed_img = processed_img.filter(ImageFilter.BLUR)
                    elif filter_name == 'enhance_contrast':
                        enhancer = ImageEnhance.Contrast(processed_img)
                        processed_img = enhancer.enhance(1.2)
                    elif filter_name == 'enhance_brightness':
                        enhancer = ImageEnhance.Brightness(processed_img)
                        processed_img = enhancer.enhance(1.1)
                    elif filter_name == 'grayscale':
                        processed_img = processed_img.convert('L').convert('RGB')
                
                # Save processed image
                base_name, ext = os.path.splitext(image_path)
                processed_path = f"{base_name}_processed{ext}"
                processed_img.save(processed_path, format='PNG', optimize=True)
                
                return processed_path
                
        except Exception as e:
            logger.error(f"Error applying image filters: {e}")
            return image_path
    
    def generate_thumbnail(self, image_path: str, thumbnail_size: Tuple[int, int] = (200, 150)) -> str:
        """Generate a thumbnail for the screenshot."""
        try:
            with Image.open(image_path) as img:
                # Create thumbnail
                img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                
                # Save thumbnail
                base_name, ext = os.path.splitext(image_path)
                thumbnail_path = f"{base_name}_thumb{ext}"
                img.save(thumbnail_path, format='PNG', optimize=True)
                
                logger.debug(f"Generated thumbnail: {thumbnail_path}")
                return thumbnail_path
                
        except Exception as e:
            logger.warning(f"Error generating thumbnail: {e}")
            return image_path

class ScreenshotArchiver:
    """Handles screenshot archiving and cleanup operations."""
    
    def __init__(self):
        self.archive_formats = ['zip', 'tar.gz']
        self.default_format = 'zip'
    
    def archive_screenshots(self, source_dir: str, archive_path: str, 
                          compression_level: int = 6) -> bool:
        """Archive screenshots with compression."""
        try:
            import shutil
            
            if not os.path.exists(source_dir):
                logger.warning(f"Source directory not found: {source_dir}")
                return False
            
            # Count files to archive
            file_count = sum(1 for root, dirs, files in os.walk(source_dir) for file in files)
            
            if file_count == 0:
                logger.info("No files to archive")
                return True
            
            # Create archive
            archive_base = os.path.splitext(archive_path)[0]
            shutil.make_archive(archive_base, 'zip', source_dir)
            
            # Verify archive was created
            final_archive_path = f"{archive_base}.zip"
            if os.path.exists(final_archive_path):
                archive_size = os.path.getsize(final_archive_path)
                logger.info(f"Archived {file_count} files to {final_archive_path} "
                           f"({self._format_file_size(archive_size)})")
                return True
            else:
                logger.error("Archive was not created")
                return False
                
        except Exception as e:
            logger.error(f"Error archiving screenshots: {e}")
            return False
    
    def cleanup_old_screenshots(self, days_to_keep: int = 7) -> Dict[str, int]:
        """Clean up old screenshots and return statistics."""
        stats = {'files_deleted': 0, 'bytes_freed': 0, 'errors': 0}
        
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            for root, dirs, files in os.walk(Config.TMP_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    try:
                        # Check file age
                        file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                        
                        if file_mtime < cutoff_date:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            stats['files_deleted'] += 1
                            stats['bytes_freed'] += file_size
                            
                    except Exception as e:
                        logger.warning(f"Error processing file {file_path}: {e}")
                        stats['errors'] += 1
            
            # Remove empty directories
            self._remove_empty_dirs(Config.TMP_DIR)
            
            logger.info(f"Cleanup completed: {stats['files_deleted']} files deleted, "
                       f"{self._format_file_size(stats['bytes_freed'])} freed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            stats['errors'] += 1
        
        return stats
    
    def _remove_empty_dirs(self, path: str):
        """Remove empty directories recursively."""
        try:
            for root, dirs, files in os.walk(path, topdown=False):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        if not os.listdir(dir_path):  # Directory is empty
                            os.rmdir(dir_path)
                            logger.debug(f"Removed empty directory: {dir_path}")
                    except Exception:
                        pass  # Directory not empty or permission error
        except Exception as e:
            logger.warning(f"Error removing empty directories: {e}")
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

# Global instances
screenshot_processor = ScreenshotProcessor()
screenshot_archiver = ScreenshotArchiver()

# Legacy function for backward compatibility
def save_screenshot_to_tmp(screenshot_bytes: bytes, filename: str) -> str:
    """Legacy function - use ScreenshotProcessor.save_screenshot_to_tmp instead."""
    return screenshot_processor.save_screenshot_to_tmp(screenshot_bytes, filename)

# Enhanced utility functions
def create_screenshot_with_metadata(screenshot_bytes: bytes, filename: str, 
                                  dashboard_name: str, time_range: str = None,
                                  panel_count: int = None) -> str:
    """Create screenshot with enhanced metadata."""
    metadata = {}
    if time_range:
        metadata['time_range'] = time_range
    if panel_count:
        metadata['panel_count'] = panel_count
    
    return screenshot_processor.save_screenshot_to_tmp(
        screenshot_bytes, filename, dashboard_name, metadata
    )

def batch_process_screenshots(screenshot_dir: str, operations: List[str]) -> List[str]:
    """Batch process multiple screenshots with specified operations."""
    processed_files = []
    
    try:
        for filename in os.listdir(screenshot_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(screenshot_dir, filename)
                
                # Apply operations
                processed_path = file_path
                if 'thumbnail' in operations:
                    processed_path = screenshot_processor.generate_thumbnail(processed_path)
                
                if any(op in operations for op in ['sharpen', 'blur', 'enhance_contrast']):
                    filters = [op for op in operations if op in ['sharpen', 'blur', 'enhance_contrast']]
                    processed_path = screenshot_processor.apply_image_filters(processed_path, filters)
                
                processed_files.append(processed_path)
                
    except Exception as e:
        logger.error(f"Error in batch processing: {e}")
    
    return processed_files

def get_screenshot_statistics(directory: str) -> Dict:
    """Get statistics about screenshots in a directory."""
    stats = {
        'total_files': 0,
        'total_size': 0,
        'by_extension': {},
        'by_date': {},
        'average_size': 0
    }
    
    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                    file_path = os.path.join(root, file)
                    file_size = os.path.getsize(file_path)
                    file_ext = os.path.splitext(file)[1].lower()
                    
                    # Update statistics
                    stats['total_files'] += 1
                    stats['total_size'] += file_size
                    stats['by_extension'][file_ext] = stats['by_extension'].get(file_ext, 0) + 1
                    
                    # Date statistics
                    try:
                        file_date = datetime.fromtimestamp(os.path.getmtime(file_path)).date()
                        date_str = file_date.strftime('%Y-%m-%d')
                        stats['by_date'][date_str] = stats['by_date'].get(date_str, 0) + 1
                    except Exception:
                        pass
        
        # Calculate average size
        if stats['total_files'] > 0:
            stats['average_size'] = stats['total_size'] / stats['total_files']
            
    except Exception as e:
        logger.error(f"Error calculating screenshot statistics: {e}")
    
    return stats
