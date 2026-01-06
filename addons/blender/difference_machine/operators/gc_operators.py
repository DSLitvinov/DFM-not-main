"""
Operators for garbage collection and database maintenance.
"""

import bpy
from bpy.types import Operator
from pathlib import Path
from ..utils.forester_cli import get_cli
from ..utils.helpers import get_repository_path, get_addon_preferences
import time


class DF_OT_garbage_collect(Operator):
    """Run garbage collection to remove unused objects."""
    bl_idname = "df.garbage_collect"
    bl_label = "Garbage Collect"
    bl_description = "Remove unused objects from repository"
    bl_options = {'REGISTER', 'UNDO'}

    dry_run: bpy.props.BoolProperty(
        name="Dry Run",
        description="Preview what would be deleted without actually deleting",
        default=False,
    )

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        cli = get_cli()
        # Note: dry_run parameter is ignored as CLI doesn't support it yet
        success, stats, error_msg = cli.gc(repo_path, dry_run=False)
        
        if not success:
            self.report({'ERROR'}, f"Garbage collection failed: {error_msg}")
            return {'CANCELLED'}
        
        # Update last run time in preferences
        prefs = get_addon_preferences(context)
        prefs.gc_last_run = time.time()
        
        if stats:
            msg = (
                f"Deleted: {stats.get('commits_deleted', 0)} commits, "
                f"{stats.get('trees_deleted', 0)} trees, "
                f"{stats.get('blobs_deleted', 0)} blobs"
            )
            self.report({'INFO'}, msg)
        else:
            self.report({'INFO'}, "Garbage collection completed")
        
        return {'FINISHED'}


class DF_OT_rebuild_database(Operator):
    """Rebuild database from storage."""
    bl_idname = "df.rebuild_database"
    bl_label = "Rebuild Database"
    bl_description = "Rebuild database from storage (use if database is corrupted)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Confirm action
        if not self.confirm_rebuild():
            return {'CANCELLED'}
        
        cli = get_cli()
        success, error_msg = cli.rebuild(repo_path)
        
        if success:
            self.report({'INFO'}, "Database rebuilt successfully")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to rebuild database: {error_msg}")
            return {'CANCELLED'}
    
    def confirm_rebuild(self):
        """Show confirmation dialog."""
        # For now, just return True
        # In the future, could use bpy.ops.wm.invoke_props_dialog
        return True


def register():
    bpy.utils.register_class(DF_OT_garbage_collect)
    bpy.utils.register_class(DF_OT_rebuild_database)


def unregister():
    bpy.utils.unregister_class(DF_OT_rebuild_database)
    bpy.utils.unregister_class(DF_OT_garbage_collect)
