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
            
            if removed_count >
