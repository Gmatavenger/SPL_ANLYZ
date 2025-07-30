import os
import logging
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from .config import Config

class ColoredFormatter(logging.Formatter):
    """Colored console output formatter."""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record):
        if hasattr(record, 'levelname'):
            color = self.COLORS.get(record.levelname, '')
            record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)

class SplunkAutomatorLogger:
    """Enhanced logging setup with rotation, filtering, and performance monitoring."""
    
    def __init__(self, name: str = "SplunkAutomator", level: int = logging.INFO):
        self.name = name
        self.level = level
        self.logger = None
        self._setup_logger()
    
    def _setup_logger(self):
        """Set up logger with multiple handlers and proper formatting."""
        # Ensure log directory exists
        Config.ensure_directories()
        
        # Create logger
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self.level)
        
        # Clear existing handlers to avoid duplicates
        self.logger.handlers.clear()
        
        # File handler with rotation
        self._add_file_handler()
        
        # Console handler
        self._add_console_handler()
        
        # Error file handler for errors and above
        self._add_error_file_handler()
        
        # Performance handler for timing logs
        self._add_performance_handler()
        
        # Prevent propagation to root logger
        self.logger.propagate = False
        
        self.logger.info(f"Logger initialized: {self.name}")
    
    def _add_file_handler(self):
        """Add rotating file handler for general logs."""
        log_file = Config.get_log_file_path()
        
        # Use RotatingFileHandler for size-based rotation
        handler = RotatingFileHandler(
            log_file,
            maxBytes=Config.MAX_LOG_SIZE_MB * 1024 * 1024,  # Convert MB to bytes
            backupCount=7,  # Keep 7 backup files
            encoding='utf-8'
        )
        
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s] [%(threadName)-12s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        
        self.logger.addHandler(handler)
    
    def _add_console_handler(self):
        """Add colored console handler."""
        handler = logging.StreamHandler(sys.stdout)
        
        # Use colored formatter for console
        formatter = ColoredFormatter(
            '%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)  # Only INFO and above to console
        
        self.logger.addHandler(handler)
    
    def _add_error_file_handler(self):
        """Add separate handler for errors and critical messages."""
        error_log_file = os.path.join(Config.LOG_DIR, "errors.log")
        
        handler = RotatingFileHandler(
            error_log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)-8s] [%(threadName)-12s] %(name)s:%(lineno)d: %(message)s\n'
            'Function: %(funcName)s\n'
            'Path: %(pathname)s\n'
            '%(exc_text)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        handler.setLevel(logging.ERROR)
        
        self.logger.addHandler(handler)
    
    def _add_performance_handler(self):
        """Add handler for performance metrics."""
        perf_log_file = os.path.join(Config.LOG_DIR, "performance.log")
        
        handler = TimedRotatingFileHandler(
            perf_log_file,
            when='midnight',
            interval=1,
            backupCount=30,  # Keep 30 days
            encoding='utf-8'
        )
        
        formatter = logging.Formatter(
            '%(asctime)s,%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        # Create a filter for performance logs
        class PerformanceFilter(logging.Filter):
            def filter(self, record):
                return hasattr(record, 'performance') and record.performance
        
        handler.addFilter(PerformanceFilter())
        handler.setLevel(logging.INFO)
        
        self.logger.addHandler(handler)
    
    def log_performance(self, operation: str, duration: float, 
                       dashboard_name: Optional[str] = None, **kwargs):
        """Log performance metrics."""
        extra_data = {
            'performance': True,
            'operation': operation,
            'duration_seconds': duration,
            'dashboard': dashboard_name or 'N/A'
        }
        extra_data.update(kwargs)
        
        message = f"{operation},{duration:.3f},{dashboard_name or 'N/A'}"
        if kwargs:
            message += "," + ",".join(f"{k}={v}" for k, v in kwargs.items())
        
        self.logger.info(message, extra=extra_data)
    
    def log_dashboard_status(self, dashboard_name: str, status: str, 
                           details: Optional[str] = None):
        """Log dashboard processing status."""
        message = f"Dashboard '{dashboard_name}' status: {status}"
        if details:
            message += f" - {details}"
        
        if status.lower() in ['failed', 'error']:
            self.logger.error(message)
        elif status.lower() in ['warning', 'timeout']:
            self.logger.warning(message)
        else:
            self.logger.info(message)
    
    def cleanup_old_logs(self, days_to_keep: int = None):
        """Clean up old log files."""
        if days_to_keep is None:
            days_to_keep = Config.DAYS_TO_KEEP
        
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        log_dir = Path(Config.LOG_DIR)
        
        cleaned_count = 0
        for log_file in log_dir.glob("*.log*"):
            try:
                if log_file.stat().st_mtime < cutoff_date.timestamp():
                    log_file.unlink()
                    cleaned_count += 1
            except Exception as e:
                self.logger.warning(f"Failed to delete old log file {log_file}: {e}")
        
        if cleaned_count > 0:
            self.logger.info(f"Cleaned up {cleaned_count} old log files")
    
    def get_recent_errors(self, hours: int = 24) -> list:
        """Get recent error messages from logs."""
        error_log_file = os.path.join(Config.LOG_DIR, "errors.log")
        if not os.path.exists(error_log_file):
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_errors = []
        
        try:
            with open(error_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            # Extract timestamp from log line
                            timestamp_str = line.split(' [')[0]
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                            
                            if timestamp > cutoff_time:
                                recent_errors.append(line.strip())
                        except (ValueError, IndexError):
                            # Skip lines that don't match expected format
                            continue
        except Exception as e:
            self.logger.warning(f"Failed to read error log: {e}")
        
        return recent_errors[-50:]  # Return last 50 errors
    
    def get_logger(self):
        """Get the configured logger instance."""
        return self.logger
    
    def set_level(self, level: int):
        """Change logging level."""
        self.logger.setLevel(level)
        self.level = level
        self.logger.info(f"Logging level changed to {logging.getLevelName(level)}")

# Context manager for timing operations
class TimingContext:
    """Context manager for timing operations and logging performance."""
    
    def __init__(self, logger_instance, operation: str, dashboard_name: str = None):
        self.logger = logger_instance
        self.operation = operation
        self.dashboard_name = dashboard_name
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.debug(f"Starting {self.operation}" + 
                         (f" for {self.dashboard_name}" if self.dashboard_name else ""))
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            self.logger.log_performance(self.operation, duration, self.dashboard_name)
            self.logger.debug(f"Completed {self.operation} in {duration:.3f}s" +
                            (f" for {self.dashboard_name}" if self.dashboard_name else ""))
        else:
            self.logger.error(f"Failed {self.operation} after {duration:.3f}s" +
                            (f" for {self.dashboard_name}" if self.dashboard_name else "") +
                            f": {exc_val}")

# Global logger setup
def setup_logger(name: str = "SplunkAutomator", level: int = logging.INFO) -> logging.Logger:
    """Set up and return a configured logger."""
    logger_manager = SplunkAutomatorLogger(name, level)
    return logger_manager.get_logger()

# Create default logger instance
_logger_manager = SplunkAutomatorLogger()
logger = _logger_manager.get_logger()

# Export timing context for easy use
def timing_context(operation: str, dashboard_name: str = None):
    """Create a timing context for performance logging."""
    return TimingContext(_logger_manager, operation, dashboard_name)
