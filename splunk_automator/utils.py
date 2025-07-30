import os
import shutil
import zipfile
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from .config import Config
from .logging_setup import logger, timing_context

def ensure_dirs():
    """Ensure all required directories exist."""
    Config.ensure_directories()
    logger.info("All required directories ensured")

def calculate_directory_size(directory: str) -> int:
    """Calculate total size of directory in bytes."""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, IOError):
                    continue
    except Exception as e:
        logger.warning(f"Error calculating directory size for {directory}: {e}")
    return total_size

def format_file_size(size_bytes: int) -> str:
    """Format file size in human readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024**2:
        return f"{size_bytes/1024:.1f} KB"
    elif size_bytes < 1024**3:
        return f"{size_bytes/(1024**2):.1f} MB"
    else:
        return f"{size_bytes/(1024**3):.1f} GB"

def archive_and_clean_tmp():
    """Archive temporary files and clean up old archives."""
    with timing_context("archive_and_clean_tmp"):
        try:
            tmp_dirs = []
            if os.path.exists(Config.TMP_DIR):
                tmp_dirs = [d for d in os.listdir(Config.TMP_DIR) if os.path.isdir(os.path.join(Config.TMP_DIR, d))]
            
            if not tmp_dirs:
                logger.info("No temp directories to archive")
                return
            
            # Create archive directory
            os.makedirs(Config.SCREENSHOT_ARCHIVE_DIR, exist_ok=True)
            
            for tmp_dir in tmp_dirs:
                tmp_path = os.path.join(Config.TMP_DIR, tmp_dir)
                
                # Skip if directory is empty
                if not os.listdir(tmp_path):
                    shutil.rmtree(tmp_path)
                    continue
                
                # Create archive
                archive_name = f"screenshots_{tmp_dir}.zip"
                archive_path = os.path.join(Config.SCREENSHOT_ARCHIVE_DIR, archive_name)
                
                try:
                    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        for root, dirs, files in os.walk(tmp_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, tmp_path)
                                zipf.write(file_path, arcname)
                    
                    # Verify archive was created successfully
                    if os.path.exists(archive_path) and os.path.getsize(archive_path) > 0:
                        # Remove temp directory after successful archival
                        shutil.rmtree(tmp_path)
                        archive_size = format_file_size(os.path.getsize(archive_path))
                        logger.info(f"Archived {tmp_dir} to {archive_name} ({archive_size})")
                    else:
                        logger.error(f"Failed to create archive for {tmp_dir}")
                        
                except Exception as e:
                    logger.error(f"Error archiving {tmp_dir}: {e}")
                    # Don't remove temp directory if archiving failed
            
            logger.info("Temp directory archiving completed")
            
        except Exception as e:
            logger.error(f"Error in archive_and_clean_tmp: {e}")

def purge_old_archives(days_to_keep: int = None):
    """Remove old archived files based on retention policy."""
    if days_to_keep is None:
        days_to_keep = Config.DAYS_TO_KEEP
    
    with timing_context("purge_old_archives"):
        try:
            if not os.path.exists(Config.SCREENSHOT_ARCHIVE_DIR):
                return
            
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            removed_count = 0
            total_size_removed = 0
            
            for filename in os.listdir(Config.SCREENSHOT_ARCHIVE_DIR):
                file_path = os.path.join(Config.SCREENSHOT_ARCHIVE_DIR, filename)
                
                try:
                    # Check file modification time
                    file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    
                    if file_mtime < cutoff_date:
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        removed_count += 1
                        total_size_removed += file_size
                        logger.debug(f"Removed old archive: {filename}")
                        
                except Exception as e:
                    logger.warning(f"Error removing file {filename}: {e}")
            
            if removed_count > 0:
                logger.info(f"Purged {removed_count} old archives, freed {format_file_size(total_size_removed)}")
            else:
                logger.info("No old archives to purge")
                
        except Exception as e:
            logger.error(f"Error purging old archives: {e}")

def check_disk_space_and_cleanup():
    """Check available disk space and perform cleanup if needed."""
    with timing_context("disk_space_cleanup"):
        try:
            # Check archive directory size
            archive_size = calculate_directory_size(Config.SCREENSHOT_ARCHIVE_DIR)
            max_size = Config.MAX_ARCHIVE_SIZE_GB * 1024**3  # Convert GB to bytes
            
            if archive_size > max_size:
                logger.warning(f"Archive size ({format_file_size(archive_size)}) exceeds limit ({Config.MAX_ARCHIVE_SIZE_GB}GB)")
                
                # Get list of archive files sorted by modification time (oldest first)
                archive_files = []
                for filename in os.listdir(Config.SCREENSHOT_ARCHIVE_DIR):
                    file_path = os.path.join(Config.SCREENSHOT_ARCHIVE_DIR, filename)
                    if os.path.isfile(file_path):
                        mtime = os.path.getmtime(file_path)
                        size = os.path.getsize(file_path)
                        archive_files.append((file_path, mtime, size))
                
                archive_files.sort(key=lambda x: x[1])  # Sort by modification time
                
                # Remove oldest files until under limit
                removed_size = 0
                removed_count = 0
                
                for file_path, mtime, size in archive_files:
                    if archive_size - removed_size <= max_size:
                        break
                    
                    try:
                        os.remove(file_path)
                        removed_size += size
                        removed_count += 1
                        logger.info(f"Removed archive due to size limit: {os.path.basename(file_path)}")
                    except Exception as e:
                        logger.warning(f"Failed to remove {file_path}: {e}")
                
                if removed_count > 0:
                    logger.info(f"Cleanup completed: removed {removed_count} files, freed {format_file_size(removed_size)}")
                    
        except Exception as e:
            logger.error(f"Error in disk space cleanup: {e}")

def safe_file_operation(operation_func, *args, max_retries: int = 3, **kwargs):
    """Safely perform file operations with retry logic."""
    for attempt in range(max_retries):
        try:
            return operation_func(*args, **kwargs)
        except (OSError, IOError, PermissionError) as e:
            if attempt < max_retries - 1:
                logger.warning(f"File operation failed (attempt {attempt + 1}/{max_retries}): {e}")
                import time
                time.sleep(0.5)  # Brief delay before retry
            else:
                logger.error(f"File operation failed after {max_retries} attempts: {e}")
                raise

def create_backup(file_path: str, backup_suffix: str = ".backup") -> Optional[str]:
    """Create a backup of a file before modifying it."""
    try:
        if not os.path.exists(file_path):
            return None
        
        backup_path = file_path + backup_suffix
        shutil.copy2(file_path, backup_path)
        logger.debug(f"Created backup: {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.warning(f"Failed to create backup for {file_path}: {e}")
        return None

def restore_from_backup(original_path: str, backup_path: str) -> bool:
    """Restore a file from its backup."""
    try:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, original_path)
            logger.info(f"Restored {original_path} from backup")
            return True
        return False
    except Exception as e:
        logger.error(f"Failed to restore from backup: {e}")
        return False

def validate_json_file(file_path: str) -> Tuple[bool, Optional[str]]:
    """Validate that a file contains valid JSON."""
    try:
        if not os.path.exists(file_path):
            return False, "File does not exist"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            json.load(f)
        return True, None
        
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    except Exception as e:
        return False, f"Error reading file: {e}"

def get_file_age_days(file_path: str) -> Optional[int]:
    """Get the age of a file in days."""
    try:
        if not os.path.exists(file_path):
            return None
        
        file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        age = datetime.now() - file_time
        return age.days
        
    except Exception as e:
        logger.warning(f"Error getting file age for {file_path}: {e}")
        return None

def cleanup_empty_directories(root_dir: str):
    """Remove empty directories recursively."""
    try:
        for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
            if not dirnames and not filenames:
                try:
                    os.rmdir(dirpath)
                    logger.debug(f"Removed empty directory: {dirpath}")
                except OSError:
                    pass  # Directory not empty or permission denied
                    
    except Exception as e:
        logger.warning(f"Error cleaning up empty directories: {e}")

def get_system_info() -> Dict[str, str]:
    """Get basic system information for debugging."""
    try:
        import platform
        import psutil
        
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "architecture": platform.architecture()[0],
            "cpu_count": str(os.cpu_count()),
            "memory_total": format_file_size(psutil.virtual_memory().total),
            "memory_available": format_file_size(psutil.virtual_memory().available),
            "disk_free": format_file_size(psutil.disk_usage('.').free)
        }
    except ImportError:
        # psutil not available
        import platform
        return {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "architecture": platform.architecture()[0],
            "cpu_count": str(os.cpu_count())
        }
    except Exception as e:
        logger.warning(f"Error getting system info: {e}")
        return {"error": str(e)}

def export_logs_for_support(output_file: str, days: int = 7) -> bool:
    """Export recent logs and system info for support purposes."""
    try:
        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add recent log files
            cutoff_date = datetime.now() - timedelta(days=days)
            
            if os.path.exists(Config.LOG_DIR):
                for log_file in os.listdir(Config.LOG_DIR):
                    log_path = os.path.join(Config.LOG_DIR, log_file)
                    if os.path.isfile(log_path):
                        try:
                            file_time = datetime.fromtimestamp(os.path.getmtime(log_path))
                            if file_time > cutoff_date:
                                zipf.write(log_path, f"logs/{log_file}")
                        except Exception as e:
                            logger.warning(f"Failed to add log file {log_file}: {e}")
            
            # Add system information
            system_info = get_system_info()
            system_info_json = json.dumps(system_info, indent=2)
            zipf.writestr("system_info.json", system_info_json)
            
            # Add configuration info (without sensitive data)
            config_info = {
                "log_dir": Config.LOG_DIR,
                "tmp_dir": Config.TMP_DIR,
                "archive_dir": Config.SCREENSHOT_ARCHIVE_DIR,
                "days_to_keep": Config.DAYS_TO_KEEP,
                "max_concurrent_browsers": Config.MAX_CONCURRENT_BROWSERS,
                "browser_timeout": Config.BROWSER_TIMEOUT
            }
            zipf.writestr("config_info.json", json.dumps(config_info, indent=2))
        
        logger.info(f"Support export created: {output_file}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create support export: {e}")
        return False

def monitor_resource_usage():
    """Monitor and log resource usage."""
    try:
        import psutil
        
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Disk usage for current directory
        disk = psutil.disk_usage('.')
        disk_percent = (disk.used / disk.total) * 100
        
        logger.info(f"Resource usage - CPU: {cpu_percent:.1f}%, "
                   f"Memory: {memory_percent:.1f}%, "
                   f"Disk: {disk_percent:.1f}%")
        
        # Log performance metrics
        from .logging_setup import timing_context
        logger.log_performance("resource_monitoring", 0, None,
                             cpu_percent=cpu_percent,
                             memory_percent=memory_percent,
                             disk_percent=disk_percent)
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "disk_percent": disk_percent
        }
        
    except ImportError:
        logger.debug("psutil not available for resource monitoring")
        return None
    except Exception as e:
        logger.warning(f"Error monitoring resource usage: {e}")
        return None

def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """Sanitize filename by removing invalid characters."""
    import re
    
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove control characters
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
    
    # Trim whitespace and dots from ends
    filename = filename.strip(' .')
    
    # Ensure not empty
    if not filename:
        filename = "unnamed"
    
    # Truncate if too long
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        if ext:
            max_name_length = max_length - len(ext)
            filename = name[:max_name_length] + ext
        else:
            filename = filename[:max_length]
    
    return filename

def check_file_permissions(file_path: str, required_permissions: str = 'rw') -> bool:
    """Check if file has required permissions."""
    try:
        if not os.path.exists(file_path):
            return False
        
        checks = {
            'r': os.R_OK,
            'w': os.W_OK,
            'x': os.X_OK
        }
        
        for perm in required_permissions:
            if perm in checks and not os.access(file_path, checks[perm]):
                return False
        
        return True
        
    except Exception as e:
        logger.warning(f"Error checking permissions for {file_path}: {e}")
        return False
