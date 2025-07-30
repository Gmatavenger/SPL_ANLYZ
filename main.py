#!/usr/bin/env python3
"""
Splunk Dashboard Automator - Enhanced Main Entry Point
Provides comprehensive error handling and system checks.
"""

import sys
import tkinter as tk
from tkinter import messagebox
import logging
import traceback
import os

# Version information
__version__ = "2.1.0"
__author__ = "Splunk Automator Team"

def check_dependencies():
    """Check for required dependencies before starting the application."""
    missing_deps = []
    
    try:
        import playwright
    except ImportError:
        missing_deps.append("playwright")
    
    try:
        from PIL import Image
    except ImportError:
        missing_deps.append("Pillow")
    
    try:
        import cryptography
    except ImportError:
        missing_deps.append("cryptography")
    
    if missing_deps:
        error_msg = f"Missing required dependencies: {', '.join(missing_deps)}\n\n"
        error_msg += "Please install them using:\n"
        error_msg += f"pip install {' '.join(missing_deps)}"
        
        if '--no-gui' in sys.argv:
            print(error_msg)
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Missing Dependencies", error_msg)
        sys.exit(1)

def setup_exception_handling():
    """Set up global exception handling."""
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        error_msg = f"An unexpected error occurred:\n\n"
        error_msg += f"Error Type: {exc_type.__name__}\n"
        error_msg += f"Error Message: {str(exc_value)}\n\n"
        error_msg += "Full traceback has been logged to the application logs."
        
        # Log the full traceback
        logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
        
        # Show user-friendly error
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Application Error", error_msg)
        except:
            print(error_msg)
    
    sys.excepthook = handle_exception

def create_directories():
    """Create necessary directories if they don't exist."""
    from splunk_automator.config import Config
    
    directories = [
        Config.DATA_DIR,
        Config.LOG_DIR,
        Config.TMP_DIR,
        Config.ARCHIVE_DIR
    ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create directory {directory}: {e}")

def setup_logging():
    """Configure application logging."""
    from splunk_automator.config import Config
    
    # Ensure log directory exists
    os.makedirs(Config.LOG_DIR, exist_ok=True)
    
    # Configure root logger
    log_file = os.path.join(Config.LOG_DIR, "app.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific log levels for external libraries
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)

def main():
    """Main application entry point with comprehensive error handling."""
    try:
        # Check dependencies first
        check_dependencies()
        
        # Set up exception handling
        setup_exception_handling()
        
        # Create directories
        create_directories()
        
        # Set up logging
        setup_logging()
        
        logger = logging.getLogger(__name__)
        logger.info(f"Starting Splunk Dashboard Automator v{__version__}")
        
        # Import and initialize the GUI
        try:
            from splunk_automator.gui import SplunkAutomatorApp
        except ImportError as e:
            error_msg = f"Failed to import SplunkAutomatorApp: {e}\n\n"
            error_msg += "Please ensure all application files are present and properly installed."
            
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Import Error", error_msg)
            sys.exit(1)
        
        # Create and configure main window
        root = tk.Tk()
        root.title(f"Splunk Dashboard Automator v{__version__}")
        root.minsize(800, 600)
        
        # Set application icon if available
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "assets", "icon.ico")
            if os.path.exists(icon_path):
                root.iconbitmap(icon_path)
        except Exception:
            pass  # Icon is optional
        
        # Initialize the application
        app = SplunkAutomatorApp(root)
        
        # Set up proper window closing
        def on_closing():
            try:
                app.on_closing()
            except Exception as e:
                logger.error(f"Error during application shutdown: {e}")
                root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_closing)
        
        # Center window on screen
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")
        
        logger.info("Application initialized successfully")
        
        # Start the main event loop
        root.mainloop()
        
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
        sys.exit(0)
    except Exception as e:
        error_msg = f"Fatal error starting application: {e}\n\n"
        error_msg += "Please check the logs for more details."
        
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Fatal Error", error_msg)
        except:
            print(error_msg)
        
        logging.error(f"Fatal startup error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
