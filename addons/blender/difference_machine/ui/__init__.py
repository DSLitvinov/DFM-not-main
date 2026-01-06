"""
UI module for Difference Machine addon.
"""

from . import ui_panels
from . import ui_lists

__all__ = ['ui_panels', 'ui_lists']


def register():
    """Register all UI classes."""
    ui_lists.register()
    ui_panels.register()


def unregister():
    """Unregister all UI classes."""
    ui_panels.unregister()
    ui_lists.unregister()
