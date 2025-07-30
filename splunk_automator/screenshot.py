import os
import io
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from .config import Config
from .logging_setup import logger, timing_context

class ScreenshotProcessor:
    """Enhanced screenshot processing with advanced features."""
    
    def __init__(self):
        self.font_cache = {}
        self._load_fonts()
    
    def _load_fonts(self):
        """Load and cache fonts for annotations."""
        font_paths = [
            # Windows fonts
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            # macOS fonts
            "/System/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            # Linux fonts
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        
        font_sizes = [12, 16, 20, 24, 28, 32]
        
        for size in font_sizes:
            font_found = False
            for font_path in font_paths:
                try:
                    if os.path.exists(font_path):
                        self.font_cache[size] = ImageFont.truetype(font_path, size)
                        font_found = True
                        break
                except Exception:
                    continue
            
            if not font_found:
                try:
                    # Fallback to default font
                    self.font_cache[size] = ImageFont.load_default()
                except Exception:
                    self.font_cache[size] = None
    
    def save_screenshot_to_tmp(self, screenshot_bytes: bytes, filename: str, 
                              dashboard_name: str = "", annotations: Dict[str, Any] = None) -> str:
        """Save screenshot with enhanced annotations and metadata."""
        with timing_context("save_screenshot", dashboard_name):
            try:
                # Create directory structure
                today_str = datetime.now().strftime("%Y-%m-%d")
                day_tmp_dir = Config.get_temp_dir_for_date(today_str)
                os.makedirs(day_tmp_dir, exist_ok=True)
                
                file_path = os.path.join(day_tmp_dir, filename)
                
                # Process image
                image = self._process_screenshot(screenshot_bytes, dashboard_name, annotations)
                
                # Save with optimization
                self._save_optimized_image(image, file_path)
                
                logger.info(f"Saved screenshot to {file_path}")
                return file_path
                
            except Exception as e:
                logger.error(f"Error saving screenshot: {e}")
                raise
    
    def _process_screenshot(self, screenshot_bytes: bytes, dashboard_name: str, 
                          annotations: Dict[str, Any] = None) -> Image.Image:
        """Process screenshot with annotations and enhancements."""
        # Load image
        image = Image.open(io.BytesIO(screenshot_bytes))
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Apply enhancements if requested
        if annotations and annotations.get('enhance', False):
            image = self._enhance_image(image, annotations.get('enhancement_settings', {}))
        
        # Add annotations
        image = self._add_annotations(image, dashboard_name, annotations)
        
        return image
    
    def _enhance_image(self, image: Image.Image, settings: Dict) -> Image.Image:
        """Apply image enhancements."""
        try:
            # Brightness adjustment
            brightness = settings.get('brightness', 1.0)
            if brightness != 1.0:
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(brightness)
            
            # Contrast adjustment
            contrast = settings.get('contrast', 1.0)
            if contrast != 1.0:
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(contrast)
            
            # Sharpness adjustment
            sharpness = settings.get('sharpness', 1.0)
            if sharpness != 1.0:
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(sharpness)
            
            # Blur filter
            if settings.get('blur', False):
                blur_radius = settings.get('blur_radius', 1)
                image = image.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            
            return image
            
        except Exception as e:
            logger.warning(f"Error enhancing image: {e}")
            return image
    
    def _add_annotations(self, image: Image.Image, dashboard_name: str, 
                        annotations: Dict[str, Any] = None) -> Image.Image:
        """Add annotations to the screenshot."""
        try:
            draw = ImageDraw.Draw(image)
            
            # Basic timestamp annotation
            timestamp = datetime.now(Config.EST).strftime("%Y-%m-%d %H:%M:%S %Z")
            
            # Prepare annotation settings
            if not annotations:
                annotations = {}
            
            font_size = annotations.get('font_size', 24)
            text_color = annotations.get('text_color', 'white')
            bg_color = annotations.get('bg_color', 'black')
            position = annotations.get('position', 'top-left')
            include_dashboard_name = annotations.get('include_dashboard_name', True)
            
            # Get font
            font = self.font_cache.get(font_size)
            
            # Prepare text
            lines = [f"Captured: {timestamp}"]
            if include_dashboard_name and dashboard_name:
                lines.append(f"Dashboard: {dashboard_name}")
            
            # Add custom annotations
            custom_annotations = annotations.get('custom_text', [])
            if isinstance(custom_annotations, str):
                custom_annotations = [custom_annotations]
            lines.extend(custom_annotations)
            
            # Calculate text dimensions
            text_bbox = self._calculate_text_bbox(draw, lines, font)
            
            # Determine position
            x, y = self._get_annotation_position(image, text_bbox, position)
            
            # Draw background rectangle
            if bg_color and bg_color.lower() != 'transparent':
                padding = 10
                bg_bbox = (
                    x - padding,
                    y - padding,
                    x + text_bbox[2] + padding,
                    y + text_bbox[3] + padding
                )
                draw.rectangle(bg_bbox, fill=bg_color, outline=None)
            
            # Draw text lines
            current_y = y
            for line in lines:
                draw.text((x, current_y), line, fill=text_color, font=font)
                line_height = draw.textbbox((0, 0), line, font=font)[3]
                current_y += line_height + 2
            
            # Add watermark if requested
            if annotations.get('watermark'):
                self._add_watermark(draw, image, annotations.get('watermark'))
            
            # Add border if requested
            if annotations.get('border'):
                self._add_border(draw, image, annotations.get('border'))
            
            return image
            
        except Exception as e:
            logger.warning(f"Error adding annotations: {e}")
            return image
    
    def _calculate_text_bbox(self, draw: ImageDraw.Draw, lines: list, font) -> Tuple[int, int, int, int]:
        """Calculate bounding box for multiple lines of text."""
        max_width = 0
        total_height = 0
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            
            max_width = max(max_width, width)
            total_height += height + 2  # Add line spacing
        
        return (0, 0, max_width, total_height)
    
    def _get_annotation_position(self, image: Image.Image, text_bbox: Tuple[int, int, int, int], 
                               position: str) -> Tuple[int, int]:
        """Calculate annotation position based on image size and preference."""
        img_width, img_height = image.size
        text_width, text_height = text_bbox[2], text_bbox[3]
        
        margin = 10
        
        position_map = {
            'top-left': (margin, margin),
            'top-right': (img_width - text_width - margin, margin),
            'top-center': ((img_width - text_width) // 2, margin),
            'bottom-left': (margin, img_height - text_height - margin),
            'bottom-right': (img_width - text_width - margin, img_height - text_height - margin),
            'bottom-center': ((img_width - text_width) // 2, img_height - text_height - margin),
            'center': ((img_width - text_width) // 2, (img_height - text_height) // 2)
        }
        
        return position_map.get(position, position_map['top-left'])
    
    def _add_watermark(self, draw: ImageDraw.Draw, image: Image.Image, watermark_config: Dict):
        """Add watermark to the image."""
        try:
            text = watermark_config.get('text', 'Splunk Automator')
            opacity = watermark_config.get('opacity', 0.3)
            font_size = watermark_config.get('font_size', 48)
            color = watermark_config.get('color', 'gray')
            
            # Create watermark overlay
            watermark = Image.new('RGBA', image.size, (0, 0, 0, 0))
            watermark_draw = ImageDraw.Draw(watermark)
            
            font = self.font_cache.get(font_size)
            
            # Position watermark in center
            bbox = watermark_draw.textbbox((0, 0), text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (image.size[0] - text_width) // 2
            y = (image.size[1] - text_height) // 2
            
            # Draw watermark text
            watermark_draw.text((x, y), text, font=font, fill=(*self._parse_color(color), int(255 * opacity)))
            
            # Composite with original image
            image.paste(watermark, (0, 0), watermark)
            
        except Exception as e:
            logger.warning(f"Error adding watermark: {e}")
    
    def _add_border(self, draw: ImageDraw.Draw, image: Image.Image, border_config: Dict):
        """Add border to the image."""
        try:
            width = border_config.get('width', 2)
            color = border_config.get('color', 'black')
            style = border_config.get('style', 'solid')
            
            img_width, img_height = image.size
            
            if style == 'solid':
                # Draw solid border
                for i in range(width):
                    draw.rectangle(
                        [(i, i), (img_width - 1 - i, img_height - 1 - i)],
                        outline=color,
                        width=1
                    )
            elif style == 'dashed':
                # Draw dashed border (simplified)
                dash_length = 10
                gap_length = 5
                
                # Top and bottom borders
                for y in [0, img_height - width]:
                    x = 0
                    while x < img_width:
                        draw.rectangle(
                            [(x, y), (min(x + dash_length, img_width), y + width)],
                            fill=color
                        )
                        x += dash_length + gap_length
                
                # Left and right borders
                for x in [0, img_width - width]:
                    y = 0
                    while y < img_height:
                        draw.rectangle(
                            [(x, y), (x + width, min(y + dash_length, img_height))],
                            fill=color
                        )
                        y += dash_length + gap_length
            
        except Exception as e:
            logger.warning(f"Error adding border: {e}")
    
    def _parse_color(self, color_str: str) -> Tuple[int, int, int]:
        """Parse color string to RGB tuple."""
        color_map = {
            'white': (255, 255, 255),
            'black': (0, 0, 0),
            'red': (255, 0, 0),
            'green': (0, 255, 0),
            'blue': (0, 0, 255),
            'yellow': (255, 255, 0),
            'cyan': (0, 255, 255),
            'magenta': (255, 0, 255),
            'gray': (128, 128, 128),
            'grey': (128, 128, 128)
        }
        
        if color_str.lower() in color_map:
            return color_map[color_str.lower()]
        
        # Try to parse hex color
        if color_str.startswith('#') and len(color_str) == 7:
            try:
                return tuple(int(color_str[i:i+2], 16) for i in (1, 3, 5))
            except ValueError:
                pass
        
        # Default to black
        return (0, 0, 0)
    
    def _save_optimized_image(self, image: Image.Image, file_path: str):
        """Save image with optimization."""
        try:
            # Determine format and optimization settings
            format_type = 'PNG'
            save_kwargs = {'format': format_type}
            
            # PNG optimization
            if format_type == 'PNG':
                save_kwargs.update({
                    'optimize': True,
                    'compress_level': 6  # Good balance of size and speed
                })
            
            # Save image
            image.save(file_path, **save_kwargs)
            
            # Set file permissions
            os.chmod(file_path, Config.SECURE_FILE_PERMISSIONS)
            
        except Exception as e:
            logger.error(f"Error saving optimized image: {e}")
            # Fallback to basic save
            image.save(file_path)
    
    def create_thumbnail(self, image_path: str, thumbnail_path: str, size: Tuple[int, int] = (200, 150)) -> bool:
        """Create a thumbnail from an existing image."""
        try:
            with Image.open(image_path) as image:
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Create thumbnail maintaining aspect ratio
                image.thumbnail(size, Image.Resampling.LANCZOS)
                
                # Save thumbnail
                image.save(thumbnail_path, 'PNG', optimize=True)
                
                logger.debug(f"Created thumbnail: {thumbnail_path}")
                return True
                
        except Exception as e:
            logger.error(f"Error creating thumbnail: {e}")
            return False
    
    def create_contact_sheet(self, image_paths: list, output_path: str, 
                           cols: int = 3, thumbnail_size: Tuple[int, int] = (200, 150)) -> bool:
        """Create a contact sheet from multiple images."""
        try:
            if not image_paths:
                return False
            
            rows = (len(image_paths) + cols - 1) // cols
            
            # Calculate contact sheet dimensions
            margin = 10
            sheet_width = cols * thumbnail_size[0] + (cols + 1) * margin
            sheet_height = rows * thumbnail_size[1] + (rows + 1) * margin
            
            # Create contact sheet
            contact_sheet = Image.new('RGB', (sheet_width, sheet_height), 'white')
            
            for idx, image_path in enumerate(image_paths):
                try:
                    with Image.open(image_path) as img:
                        # Create thumbnail
                        img.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                        
                        # Calculate position
                        col = idx % cols
                        row = idx // cols
                        
                        x = margin + col * (thumbnail_size[0] + margin)
                        y = margin + row * (thumbnail_size[1] + margin)
                        
                        # Paste thumbnail
                        contact_sheet.paste(img, (x, y))
                        
                except Exception as e:
                    logger.warning(f"Error processing image {image_path} for contact sheet: {e}")
                    continue
            
            # Save contact sheet
            contact_sheet.save(output_path, 'PNG', optimize=True)
            logger.info(f"Created contact sheet: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating contact sheet: {e}")
            return False
    
    def add_comparison_annotations(self, image_paths: list, output_path: str, 
                                 titles: list = None) -> bool:
        """Create a side-by-side comparison of multiple images."""
        try:
            if len(image_paths) < 2:
                return False
            
            images = []
            max_height = 0
            total_width = 0
            
            # Load and process images
            for i, image_path in enumerate(image_paths):
                try:
                    img = Image.open(image_path)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    images.append(img)
                    max_height = max(max_height, img.height)
                    total_width += img.width
                    
                except Exception as e:
                    logger.warning(f"Error loading image {image_path}: {e}")
                    continue
            
            if not images:
                return False
            
            # Create comparison image
            margin = 20
            title_height = 50 if titles else 0
            comparison_width = total_width + margin * (len(images) + 1)
            comparison_height = max_height + margin * 2 + title_height
            
            comparison = Image.new('RGB', (comparison_width, comparison_height), 'white')
            draw = ImageDraw.Draw(comparison)
            
            # Paste images
            current_x = margin
            for i, img in enumerate(images):
                y = margin + title_height
                comparison.paste(img, (current_x, y))
                
                # Add title if provided
                if titles and i < len(titles):
                    font = self.font_cache.get(16)
                    title_y = margin
                    draw.text((current_x, title_y), titles[i], fill='black', font=font)
                
                current_x += img.width + margin
            
            # Save comparison
            comparison.save(output_path, 'PNG', optimize=True)
            logger.info(f"Created comparison image: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating comparison image: {e}")
            return False
        finally:
            # Clean up loaded images
            for img in images:
                try:
                    img.close()
                except:
                    pass

class ScreenshotMetadata:
    """Manage screenshot metadata and EXIF information."""
    
    @staticmethod
    def extract_metadata(image_path: str) -> Dict[str, Any]:
        """Extract metadata from screenshot."""
        try:
            with Image.open(image_path) as image:
                metadata = {
                    'filename': os.path.basename(image_path),
                    'size': image.size,
                    'mode': image.mode,
                    'format': image.format,
                    'file_size': os.path.getsize(image_path),
                    'created': datetime.fromtimestamp(os.path.getctime(image_path)).isoformat(),
                    'modified': datetime.fromtimestamp(os.path.getmtime(image_path)).isoformat()
                }
                
                # Extract EXIF data if available
                if hasattr(image, '_getexif') and image._getexif():
                    exif_data = image._getexif()
                    metadata['exif'] = exif_data
                
                return metadata
                
        except Exception as e:
            logger.warning(f"Error extracting metadata from {image_path}: {e}")
            return {}
    
    @staticmethod
    def add_custom_metadata(image_path: str, metadata: Dict[str, Any]) -> bool:
        """Add custom metadata to image file."""
        try:
            # For PNG files, we can use text chunks
            # This is a simplified implementation
            logger.debug(f"Custom metadata would be added to {image_path}: {metadata}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding custom metadata: {e}")
            return False

class ScreenshotArchiver:
    """Manage screenshot archiving and compression."""
    
    def __init__(self):
        self.processor = ScreenshotProcessor()
    
    def archive_screenshots_by_date(self, date_str: str, compression_level: int = 6) -> Optional[str]:
        """Archive all screenshots for a specific date."""
        try:
            date_dir = Config.get_temp_dir_for_date(date_str)
            if not os.path.exists(date_dir) or not os.listdir(date_dir):
                logger.info(f"No screenshots found for date {date_str}")
                return None
            
            # Create archive directory
            archive_dir = Config.get_archive_dir_for_date(date_str)
            os.makedirs(os.path.dirname(archive_dir), exist_ok=True)
            
            archive_path = f"{archive_dir}.zip"
            
            import zipfile
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, 
                               compresslevel=compression_level) as zipf:
                
                for root, dirs, files in os.walk(date_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_name = os.path.relpath(file_path, date_dir)
                        zipf.write(file_path, arc_name)
            
            logger.info(f"Archived screenshots to {archive_path}")
            return archive_path
            
        except Exception as e:
            logger.error(f"Error archiving screenshots for {date_str}: {e}")
            return None
    
    def create_summary_report(self, date_str: str, output_path: str) -> bool:
        """Create a summary report with all screenshots for a date."""
        try:
            date_dir = Config.get_temp_dir_for_date(date_str)
            if not os.path.exists(date_dir):
                return False
            
            # Find all screenshot files
            screenshot_files = []
            for file in os.listdir(date_dir):
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    screenshot_files.append(os.path.join(date_dir, file))
            
            if not screenshot_files:
                return False
            
            # Create contact sheet
            return self.processor.create_contact_sheet(
                screenshot_files, output_path, cols=2, thumbnail_size=(400, 300)
            )
            
        except Exception as e:
            logger.error(f"Error creating summary report: {e}")
            return False

# Backward compatibility functions
def save_screenshot_to_tmp(screenshot_bytes: bytes, filename: str) -> str:
    """Backward compatible function for saving screenshots."""
    processor = ScreenshotProcessor()
    return processor.save_screenshot_to_tmp(screenshot_bytes, filename)

def save_screenshot_with_annotations(screenshot_bytes: bytes, filename: str, 
                                   dashboard_name: str, custom_annotations: Dict = None) -> str:
    """Save screenshot with custom annotations."""
    processor = ScreenshotProcessor()
    return processor.save_screenshot_to_tmp(screenshot_bytes, filename, dashboard_name, custom_annotations)

def create_dashboard_comparison(image_paths: list, output_path: str, 
                              dashboard_names: list = None) -> bool:
    """Create a comparison image of multiple dashboard screenshots."""
    processor = ScreenshotProcessor()
    return processor.add_comparison_annotations(image_paths, output_path, dashboard_names)
