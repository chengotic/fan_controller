import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_config_dir() -> Path:
    """Get the configuration directory, creating it if needed."""
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        # Allow overriding config directory for testing
        return Path(sys.argv[1])
    
    config_dir = Path.home() / ".config" / "fan_controller"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    new_config_path = config_dir / "config.json"
    
    # If a config already exists in the new location, we're done.
    if new_config_path.exists():
        return config_dir
        
    # For backward compatibility, check the CWD
    old_config_path = Path.cwd() / "config.json"
    if old_config_path.exists():
        import shutil
        shutil.copy(old_config_path, new_config_path)
        return config_dir
        
    # If no config is found, the load_config function will create a default one.
    return config_dir

def main_cli():
    """Entry point for the CLI daemon."""
    from .core import FanController
    
    config_dir = get_config_dir()
    config_path = config_dir / "config.json"
    status_path = config_dir / ".fan_controller_status.json"
    
    controller = FanController(config_path, status_path)
    controller.run()

def main_gui():
    """Entry point for the GUI."""
    from .gui import main as gui_main
    gui_main()

if __name__ == "__main__":
    main_cli()
