"""
Operators module for Difference Machine addon.
"""

from . import init_operators
from . import branch_operators
from . import commit_operators
from . import history_operators
from . import gc_operators
from . import review_operators
from . import stash_operators
from . import lock_operators

__all__ = [
    'init_operators',
    'branch_operators',
    'commit_operators',
    'history_operators',
    'gc_operators',
    'review_operators',
    'stash_operators',
    'lock_operators',
]


def register():
    """Register all operator classes."""
    init_operators.register()
    branch_operators.register()
    commit_operators.register()
    history_operators.register()
    gc_operators.register()
    review_operators.register()
    stash_operators.register()
    lock_operators.register()


def unregister():
    """Unregister all operator classes."""
    lock_operators.unregister()
    stash_operators.unregister()
    review_operators.unregister()
    gc_operators.unregister()
    history_operators.unregister()
    commit_operators.unregister()
    branch_operators.unregister()
    init_operators.unregister()
