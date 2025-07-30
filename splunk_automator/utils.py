import os
import shutil
import threading
import queue
from datetime import datetime, timedelta
from pathlib import Path
import zipfile
import json
from .config import Config
from .logging_setup import logger

def ensure_dirs():
    """Ensure required directories exist."""
    directories = [
        Config.LOG_DIR,
        Config.TMP_DIR,
        Config.SCREENSHOT_ARCHIVE_DIR
    ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")
        except Exception as e:
            logger.error(f"Failed to create directory {directory}: {e}")
            raise

def archive_and_clean_tmp():
    """Move old tmp subfolders to archive and clean up stray files."""
    ensure_dirs()
    
    if not os.path.exists(Config.TMP_DIR):
        logger.warning(f"Tmp directory does not exist: {Config.TMP_DIR}")
        return
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    archived_count = 0
    cleaned_count = 0
    
    try:
        # Archive old date folders
        for item in os.listdir(Config.TMP_DIR):
            item_path = os.path.join(Config.TMP_DIR, item)
            
            if os.path.isdir(item_path) and item != today_str:
                # This is an old date folder - archive it
                archive_path = os.path.join(Config.SCREENSHOT_ARCHIVE_DIR, item)
                
                # Remove existing archive if it exists
                if os.path.exists(archive_path):
                    shutil.rmtree(archive_path)
                    logger.debug(f"Removed existing archive: {archive_path}")
                
                # Move folder to archive
                shutil.move(item_path, archive_path)
                logger.info(f"Archived old tmp folder: {item} -> {archive_path}")
                archived_count += 1
        
        # Clean up stray files in tmp root
        for item in os.listdir(Config.TMP_DIR):
            item_path = os.path.join(Config.TMP_DIR, item)
            if os.path.isfile(item_path):
                try:
                    os.remove(item_path)
                    logger.debug(f"Removed stray file: {item_path}")
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"Failed to remove file {item_path}: {e}")
        
        logger.info(f"Archive cleanup complete: {archived_count} folders archived, {cleaned_count} files cleaned")
        
    except Exception as e:
        logger.error(f"Error during archive and cleanup: {e}")
        raise

def purge_old_archives():
    """Delete screenshot archives older than retention period."""
    if not os.path.exists(Config.SCREENSHOT_ARCHIVE_DIR):
        logger.debug("Screenshot archive directory does not exist")
        return
    
    now = datetime.now()
    cutoff_date = now - timedelta(days=Config.DAYS_TO_KEEP)
    purged_count = 0
    
    try:
        for folder in os.listdir(Config.SCREENSHOT_ARCHIVE_DIR):
            folder_path = os.path.join(Config.SCREENSHOT_ARCHIVE_DIR, folder)
            
            if not os.path.isdir(folder_path):
                continue
            
            try:
                # Parse folder name as date (YYYY-MM-DD format)
                folder_date = datetime.strptime(folder, "%Y-%m-%d")
                
                if folder_date < cutoff_date:
                    shutil.rmtree(folder_path)
                    logger.info(f"Purged old archive: {folder}")
                    purged_count += 1
                    
            except ValueError:
                # Folder name is not in expected date format, skip it
                logger.warning(f"Skipping folder with invalid date format: {folder}")
                continue
        
        logger.info(f"Archive purge complete: {purged_count} old archives removed")
        
    except Exception as e:
        logger.error(f"Error during archive purge: {e}")

def save_screenshot_to_tmp(screenshot_bytes: bytes, filename: str) -> str:
    """Save screenshot with timestamp overlay to tmp directory."""
    from PIL import Image, ImageDraw, ImageFont
    import io
    
    try:
        # Create today's tmp directory
        today_str = datetime.now().strftime("%Y-%m-%d")
        day_tmp_dir = os.path.join(Config.TMP_DIR, today_str)
        os.makedirs(day_tmp_dir, exist_ok=True)
        
        # Full file path
        file_path = os.path.join(day_tmp_dir, filename)
        
        # Load image from bytes
        image = Image.open(io.BytesIO(screenshot_bytes))
        
        # Add timestamp overlay
        draw = ImageDraw.Draw(image)
        timestamp = datetime.now(Config.EST).strftime("%Y-%m-%d %H:%M:%S %Z")
        
        # Try to load a font, fall back to default if needed
        try:
            # Try common font locations
            font_paths = [
                "arial.ttf",
                "/System/Library/Fonts/Arial.ttf",  # macOS
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
                "C:/Windows/Fonts/arial.ttf"  # Windows
            ]
            
            font = None
            for font_path in font_paths:
                try:
                    font = ImageFont.truetype(font_path, 24)
                    break
                except:
                    continue
                    
            if not font:
                font = ImageFont.load_default()
                
        except Exception:
            font = None
        
        # Add timestamp with background for better visibility
        text_bbox = draw.textbbox((0, 0), f"Captured: {timestamp}", font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        
        # Draw semi-transparent background
        padding = 5
        bg_bbox = (5, 5, text_width + 15, text_height + 15)
        bg_img = Image.new('RGBA', (text_width + 2*padding, text_height + 2*padding), (0, 0, 0, 128))
        image.paste(bg_img, (5, 5), bg_img)
        
        # Draw text
        draw.text((10, 10), f"Captured: {timestamp}", fill="white", font=font)
        
        # Save image
        image.save(file_path, "PNG", optimize=True)
        logger.info(f"Screenshot saved: {file_path}")
        
        return file_path
        
    except Exception as e:
        logger.error(f"Error saving screenshot {filename}: {e}")
        raise

def compress_archive_folder(folder_path: str, output_path: str = None) -> str:
    """Compress an archive folder into a ZIP file."""
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")
    
    if not output_path:
        output_path = f"{folder_path}.zip"
    
    try:
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            folder_name = os.path.basename(folder_path)
            
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Create relative path for archive
                    rel_path = os.path.relpath(file_path, folder_path)
                    archive_path = os.path.join(folder_name, rel_path)
                    zipf.write(file_path, archive_path)
        
        logger.info(f"Compressed archive: {folder_path} -> {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error compressing folder {folder_path}: {e}")
        raise

def get_directory_size(directory: str) -> int:
    """Get total size of directory in bytes."""
    if not os.path.exists(directory):
        return 0
    
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, IOError):
                    pass  # Skip files that can't be accessed
        return total_size
    except Exception as e:
        logger.error(f"Error calculating directory size for {directory}: {e}")
        return 0

def format_bytes(bytes_value: int) -> str:
    """Format bytes into human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"

def get_disk_usage_info() -> dict:
    """Get disk usage information for application directories."""
    info = {}
    
    directories = {
        'logs': Config.LOG_DIR,
        'tmp': Config.TMP_DIR,
        'archives': Config.SCREENSHOT_ARCHIVE_DIR
    }
    
    for name, path in directories.items():
        if os.path.exists(path):
            size = get_directory_size(path)
            info[name] = {
                'path': path,
                'size_bytes': size,
                'size_human': format_bytes(size),
                'file_count': count_files_in_directory(path)
            }
        else:
            info[name] = {
                'path': path,
                'size_bytes': 0,
                'size_human': '0 B',
                'file_count': 0
            }
    
    return info

def count_files_in_directory(directory: str) -> int:
    """Count total number of files in directory recursively."""
    if not os.path.exists(directory):
        return 0
    
    count = 0
    try:
        for root, dirs, files in os.walk(directory):
            count += len(files)
        return count
    except Exception as e:
        logger.error(f"Error counting files in {directory}: {e}")
        return 0

def cleanup_empty_directories(root_dir: str):
    """Remove empty directories recursively."""
    if not os.path.exists(root_dir):
        return
    
    removed_count = 0
    try:
        # Walk from bottom up to handle nested empty directories
        for root, dirs, files in os.walk(root_dir, topdown=False):
            if root == root_dir:  # Don't remove the root directory
                continue
                
            if not dirs and not files:  # Directory is empty
                try:
                    os.rmdir(root)
                    logger.debug(f"Removed empty directory: {root}")
                    removed_count += 1
                except OSError as e:
                    logger.warning(f"Could not remove empty directory {root}: {e}")
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} empty directories")
            
    except Exception as e:
        logger.error(f"Error during empty directory cleanup: {e}")

def validate_file_permissions():
    """Validate and fix file permissions for application files."""
    issues = []
    
    # Check critical files
    critical_files = [
        Config.DASHBOARD_FILE,
        Config.SETTINGS_FILE,
        Config.SCHEDULE_FILE,
        ".secrets",
        ".secrets.key"
    ]
    
    for filename in critical_files:
        if os.path.exists(filename):
            try:
                # Check if file is readable/writable
                if not os.access(filename, os.R_OK):
                    issues.append(f"File not readable: {filename}")
                if not os.access(filename, os.W_OK):
                    issues.append(f"File not writable: {filename}")
                
                # Set secure permissions for sensitive files
                if filename in [".secrets", ".secrets.key"]:
                    os.chmod(filename, 0o600)
                else:
                    os.chmod(filename, 0o644)
                    
            except Exception as e:
                issues.append(f"Permission error for {filename}: {e}")
    
    # Check directories
    directories = [Config.LOG_DIR, Config.TMP_DIR, Config.SCREENSHOT_ARCHIVE_DIR]
    for directory in directories:
        if os.path.exists(directory):
            try:
                if not os.access(directory, os.R_OK | os.W_OK | os.X_OK):
                    issues.append(f"Directory access issue: {directory}")
                os.chmod(directory, 0o755)
            except Exception as e:
                issues.append(f"Directory permission error for {directory}: {e}")
    
    return issues

class BackgroundTaskManager:
    """Manages background tasks with threading and progress tracking."""
    
    def __init__(self):
        self.tasks = {}
        self.task_counter = 0
        self.lock = threading.Lock()
    
    def start_task(self, target_func, args=(), kwargs=None, callback=None):
        """Start a background task and return task ID."""
        if kwargs is None:
            kwargs = {}
        
        with self.lock:
            task_id = self.task_counter
            self.task_counter += 1
        
        def task_wrapper():
            try:
                result = target_func(*args, **kwargs)
                if callback:
                    callback(task_id, True, result)
            except Exception as e:
                logger.error(f"Background task {task_id} failed: {e}")
                if callback:
                    callback(task_id, False, str(e))
            finally:
                with self.lock:
                    if task_id in self.tasks:
                        del self.tasks[task_id]
        
        thread = threading.Thread(target=task_wrapper, daemon=True)
        
        with self.lock:
            self.tasks[task_id] = {
                'thread': thread,
                'start_time': datetime.now(),
                'status': 'starting'
            }
        
        thread.start()
        
        with self.lock:
            self.tasks[task_id]['status'] = 'running'
        
        return task_id
    
    def get_task_status(self, task_id):
        """Get status of a background task."""
        with self.lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                return {
                    'status': task['status'],
                    'start_time': task['start_time'],
                    'running_time': datetime.now() - task['start_time'],
                    'is_alive': task['thread'].is_alive()
                }
        return None
    
    def cancel_all_tasks(self):
        """Cancel all running background tasks."""
        with self.lock:
            task_ids = list(self.tasks.keys())
        
        for task_id in task_ids:
            # Note: This is a graceful approach - threads will finish naturally
            # For true cancellation, tasks would need to check a cancellation flag
            pass
        
        logger.info(f"Requested cancellation of {len(task_ids)} background tasks")

def create_error_report(error: Exception, context: str = "") -> str:
    """Create a detailed error report for debugging."""
    import traceback
    import sys
    import platform
    
    report_lines = [
        "=" * 60,
        "SPLUNK AUTOMATOR ERROR REPORT",
        "=" * 60,
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Context: {context}",
        "",
        "System Information:",
        f"  Platform: {platform.platform()}",
        f"  Python Version: {sys.version}",
        f"  Working Directory: {os.getcwd()}",
        "",
        "Error Details:",
        f"  Type: {type(error).__name__}",
        f"  Message: {str(error)}",
        "",
        "Traceback:",
    ]
    
    # Add traceback
    tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
    report_lines.extend(f"  {line.rstrip()}" for line in tb_lines)
    
    # Add application state
    report_lines.extend([
        "",
        "Application State:",
        f"  Log Directory: {Config.LOG_DIR} (exists: {os.path.exists(Config.LOG_DIR)})",
        f"  Tmp Directory: {Config.TMP_DIR} (exists: {os.path.exists(Config.TMP_DIR)})",
        f"  Archive Directory: {Config.SCREENSHOT_ARCHIVE_DIR} (exists: {os.path.exists(Config.SCREENSHOT_ARCHIVE_DIR)})",
        "",
        "Disk Usage:",
    ])
    
    # Add disk usage info
    try:
        usage_info = get_disk_usage_info()
        for name, info in usage_info.items():
            report_lines.append(f"  {name.title()}: {info['size_human']} ({info['file_count']} files)")
    except Exception as e:
        report_lines.append(f"  Could not get disk usage: {e}")
    
    report_lines.append("=" * 60)
    
    return "\n".join(report_lines)

def save_error_report(error: Exception, context: str = "", filename: str = None) -> str:
    """Save error report to file and return filename."""
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"error_report_{timestamp}.txt"
    
    report_content = create_error_report(error, context)
    
    try:
        # Save to logs directory
        ensure_dirs()
        report_path = os.path.join(Config.LOG_DIR, filename)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        logger.info(f"Error report saved: {report_path}")
        return report_path
        
    except Exception as e:
        logger.error(f"Failed to save error report: {e}")
        # Fallback to current directory
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report_content)
            return filename
        except Exception as e2:
            logger.error(f"Failed to save error report to fallback location: {e2}")
            return None

def export_application_data(export_path: str) -> bool:
    """Export all application data to a ZIP file."""
    try:
        with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Export configuration files
            config_files = [
                Config.DASHBOARD_FILE,
                Config.SETTINGS_FILE,
                Config.SCHEDULE_FILE
            ]
            
            for config_file in config_files:
                if os.path.exists(config_file):
                    zipf.write(config_file, f"config/{config_file}")
            
            # Export logs (recent ones only)
            if os.path.exists(Config.LOG_DIR):
                cutoff_date = datetime.now() - timedelta(days=7)
                for log_file in os.listdir(Config.LOG_DIR):
                    log_path = os.path.join(Config.LOG_DIR, log_file)
                    if os.path.isfile(log_path):
                        # Check file modification time
                        mod_time = datetime.fromtimestamp(os.path.getmtime(log_path))
                        if mod_time > cutoff_date:
                            zipf.write(log_path, f"logs/{log_file}")
            
            # Export recent screenshots (last 3 days)
            if os.path.exists(Config.TMP_DIR):
                recent_cutoff = datetime.now() - timedelta(days=3)
                for item in os.listdir(Config.TMP_DIR):
                    item_path = os.path.join(Config.TMP_DIR, item)
                    if os.path.isdir(item_path):
                        try:
                            folder_date = datetime.strptime(item, "%Y-%m-%d")
                            if folder_date > recent_cutoff:
                                for root, dirs, files in os.walk(item_path):
                                    for file in files:
                                        file_path = os.path.join(root, file)
                                        rel_path = os.path.relpath(file_path, Config.TMP_DIR)
                                        zipf.write(file_path, f"screenshots/{rel_path}")
                        except ValueError:
                            pass  # Skip non-date folders
            
            # Add metadata
            metadata = {
                'export_time': datetime.now().isoformat(),
                'version': '2.0',
                'platform': platform.platform(),
                'python_version': sys.version
            }
            
            zipf.writestr('metadata.json', json.dumps(metadata, indent=4))
        
        logger.info(f"Application data exported to: {export_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to export application data: {e}")
        return False

# Background task manager instance
task_manager = BackgroundTaskManager()

# Utility function for safe file operations
def safe_file_operation(operation, *args, **kwargs):
    """Perform file operation with error handling and logging."""
    try:
        return operation(*args, **kwargs)
    except Exception as e:
        context = f"File operation: {operation.__name__}"
        error_report_path = save_error_report(e, context)
        logger.error(f"File operation failed - error report: {error_report_path}")
        raise

# Function to monitor directory changes
def monitor_directory_changes(directory: str, callback, interval: int = 30):
    """Monitor directory for changes and call callback when changes detected."""
    def monitor_worker():
        last_state = {}
        
        while True:
            try:
                current_state = {}
                if os.path.exists(directory):
                    for root, dirs, files in os.walk(directory):
                        for file in files:
                            file_path = os.path.join(root, file)
                            try:
                                stat = os.stat(file_path)
                                current_state[file_path] = {
                                    'size': stat.st_size,
                                    'mtime': stat.st_mtime
                                }
                            except (OSError, IOError):
                                pass
                
                # Check for changes
                if last_state and current_state != last_state:
                    changes = {
                        'added': set(current_state.keys()) - set(last_state.keys()),
                        'removed': set(last_state.keys()) - set(current_state.keys()),
                        'modified': set()
                    }
                    
                    for file_path in set(current_state.keys()) & set(last_state.keys()):
                        if current_state[file_path] != last_state[file_path]:
                            changes['modified'].add(file_path)
                    
                    if any(changes.values()):
                        callback(changes)
                
                last_state = current_state
                threading.Event().wait(interval)
                
            except Exception as e:
                logger.error(f"Directory monitoring error: {e}")
                threading.Event().wait(interval)
    
    monitor_thread = threading.Thread(target=monitor_worker, daemon=True)
    monitor_thread.start()
    return monitor_thread
