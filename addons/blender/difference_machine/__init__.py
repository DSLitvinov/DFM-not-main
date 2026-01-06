"""
Difference Machine - Version control for Blender projects.
"""

bl_info = {
    "name": "Difference Machine",
    "author": "Dmitry Litvinov",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Difference Machine",
    "description": "Version control for Blender projects using Forester CLI",
    "category": "Object",
    "doc_url": "https://gitflic.ru/project/nopomuk/difference-machine",
}

import bpy
import logging
from pathlib import Path

# Setup logging to file for debugging
from .utils.logging_config import setup_logging, get_logger
log_file = Path.home() / "blender_addon.log"
setup_logging(log_level=logging.DEBUG, log_file=log_file)
logger = get_logger(__name__)

# Import modules
from . import preferences
from . import properties
from . import operators
from . import ui

# Module references for reload
_modules = [
    preferences,
    properties,
    operators,
    ui,
]


def check_scheduled_gc():
    """Timer callback to check and run scheduled garbage collection."""
    try:
        # Only check if Blender is in a valid state
        if not bpy.context or not bpy.data.filepath:
            return 5.0  # Check again in 5 seconds
        
        from .utils.helpers import find_repository_root, get_addon_preferences
        from .operators.operator_helpers import check_and_run_garbage_collect
        
        blend_file = Path(bpy.data.filepath)
        repo_path = find_repository_root(blend_file.parent)
        
        if repo_path:
            prefs = get_addon_preferences(bpy.context)
            if getattr(prefs, 'gc_schedule_enabled', False):
                check_and_run_garbage_collect(bpy.context, repo_path)
        
        # Check every 60 seconds (1 minute)
        return 60.0
    except (AttributeError, RuntimeError, ValueError) as e:
        # If error occurs, log and check again in 60 seconds
        logger.debug(f"Error in scheduled GC check: {e}")
        return 60.0
    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Unexpected error in scheduled GC check: {e}", exc_info=True)
        return 60.0


def register():
    """Register all addon classes."""
    # Register in order
    preferences.register()
    properties.register()
    operators.register()
    ui.register()
    
    # Register timer for scheduled garbage collection
    bpy.app.timers.register(check_scheduled_gc, first_interval=60.0)
    
    logger.info("Difference Machine addon registered")


def unregister():
    """Unregister all addon classes."""
    # Unregister timer
    try:
        bpy.app.timers.unregister(check_scheduled_gc)
    except (ValueError, KeyError):
        pass  # Timer not registered
    
    # Unregister in reverse order
    ui.unregister()
    operators.unregister()
    properties.unregister()
    preferences.unregister()
    
    logger.info("Difference Machine addon unregistered")


if __name__ == "__main__":
    register()