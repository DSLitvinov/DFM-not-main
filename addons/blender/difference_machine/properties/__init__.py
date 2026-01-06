"""
Properties module for Difference Machine addon.
"""

from . import commit_item
from . import properties

__all__ = ['commit_item', 'properties']


def register():
    """Register all property classes."""
    commit_item.register()
    properties.register()


def unregister():
    """Unregister all property classes."""
    properties.unregister()
    commit_item.unregister()
