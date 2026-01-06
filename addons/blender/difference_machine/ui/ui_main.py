"""
Main UI module for Difference Machine add-on.
Contains panels and menus registration.
"""
import bpy
import logging
from .ui_panels import (
    DF_PT_commit_panel,
    DF_PT_history_panel,
    DF_PT_branch_panel,
    DF_PT_stash_panel,
)
from .ui_lists import (
    DF_UL_branch_list,
    DF_UL_commit_list,
    DF_UL_stash_list,
)
from ..operators.mesh_io import update_blender_node_tree

# Forester Python bindings are optional; the add-on primarily uses the CLI.
# If bindings are missing, we disable the material update hook gracefully.
try:
    from ..forester.commands.mesh_commit import (
        register_material_update_hook,
        unregister_material_update_hook,
    )
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

    def register_material_update_hook(*_args, **_kwargs):
        logger.warning("Forester Python bindings not found; material hook disabled")

    def unregister_material_update_hook(*_args, **_kwargs):
        return

logger = logging.getLogger(__name__)

# Classes list for registration
classes = [
    # UI Lists
    DF_UL_branch_list,
    DF_UL_commit_list,
    DF_UL_stash_list,
    # Panels
    DF_PT_commit_panel,
    DF_PT_history_panel,
    DF_PT_branch_panel,
    DF_PT_stash_panel,
]


def register():
    """Register UI classes and properties"""
    try:
        # Register UI classes
        for cls in classes:
            bpy.utils.register_class(cls)
        
        # Register material update hook for Blender node_tree
        register_material_update_hook(update_blender_node_tree)
        logger.debug("Registered Blender material update hook")
    except Exception as e:
        logger.error(f"Error registering UI classes: {e}", exc_info=True)
        raise


def unregister():
    try:
        # Unregister material update hook
        try:
            unregister_material_update_hook(update_blender_node_tree)
            logger.debug("Unregistered Blender material update hook")
        except Exception as e:
            logger.warning(f"Error unregistering material update hook: {e}", exc_info=True)
        
        # Unregister UI classes
        for cls in reversed(classes):
            bpy.utils.unregister_class(cls)
    except Exception as e:
        logger.error(f"Error unregistering UI classes: {e}", exc_info=True)
        raise
