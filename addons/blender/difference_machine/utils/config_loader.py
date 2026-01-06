"""
Configuration loader for Difference Machine addon.
Loads forester CLI executable path from setup.cfg.
"""

import configparser
from pathlib import Path
from typing import Optional


def get_forester_path() -> Optional[str]:
    """
    Get forester CLI executable path from setup.cfg.
    
    Returns:
        Path to forester executable, or None if not found
    """
    setup_cfg_path = Path.home() / ".dfm-setup" / "setup.cfg"
    
    if not setup_cfg_path.exists():
        return None
    
    try:
        config = configparser.ConfigParser()
        config.read(setup_cfg_path)
        
        if "forester" in config and "path" in config["forester"]:
            forester_path = config["forester"]["path"]
            forester_path_obj = Path(forester_path)
            
            # Check if path exists and is executable
            if forester_path_obj.exists() and forester_path_obj.is_file():
                return str(forester_path_obj.absolute())
            
            # Try to find executable in the directory
            if forester_path_obj.is_dir():
                import os
                # Common executable names (add .exe for Windows)
                exe_names = ["forester", "Forester", "FORESTER"]
                if os.name == 'nt':  # Windows
                    exe_names = [name + ".exe" for name in exe_names] + exe_names
                
                # First, check in the directory itself
                for exe_name in exe_names:
                    exe_path = forester_path_obj / exe_name
                    if exe_path.exists() and exe_path.is_file():
                        return str(exe_path.absolute())
                
                # Then, check in common subdirectories (bin, bin64, etc.)
                for subdir in ["bin", "bin64", "Bin", "BIN"]:
                    subdir_path = forester_path_obj / subdir
                    if subdir_path.exists() and subdir_path.is_dir():
                        for exe_name in exe_names:
                            exe_path = subdir_path / exe_name
                            if exe_path.exists() and exe_path.is_file():
                                return str(exe_path.absolute())
        
        return None
    except Exception:
        return None


def validate_forester_path(forester_path: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Validate that forester executable exists and is executable.
    
    Args:
        forester_path: Path to forester executable
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not forester_path:
        setup_cfg_path = Path.home() / ".dfm-setup" / "setup.cfg"
        if not setup_cfg_path.exists():
            return False, (
                f"Forester path not configured. "
                f"Please create {setup_cfg_path} with [forester] section and path setting."
            )
        else:
            return False, (
                f"Forester path not configured in {setup_cfg_path}. "
                f"Please check the [forester] section and path setting."
            )
    
    path_obj = Path(forester_path)
    
    if not path_obj.exists():
        return False, f"Forester executable not found: {forester_path}"
    
    if not path_obj.is_file():
        return False, f"Forester path is not a file: {forester_path}"
    
    # On Unix-like systems, check if file is executable
    import os
    if os.name != 'nt' and not os.access(path_obj, os.X_OK):
        return False, f"Forester executable is not executable: {forester_path}"
    
    return True, None
