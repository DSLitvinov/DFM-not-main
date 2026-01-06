"""
Operators for stash operations and uncommitted changes dialog.
"""

import bpy
import time
import random
from bpy.types import Operator
from pathlib import Path
from datetime import datetime
from ..utils.forester_cli import get_cli
from ..utils.helpers import get_repository_path


class DF_OT_stash_and_checkout(Operator):
    """Stash changes and proceed with checkout."""
    bl_idname = "df.stash_and_checkout"
    bl_label = "Stash and Checkout"
    bl_description = "Stash uncommitted changes and proceed with checkout"
    bl_options = {'REGISTER', 'UNDO'}

    target_type: bpy.props.StringProperty(default="")
    target_value: bpy.props.StringProperty(default="")

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        cli = get_cli()
        
        # Save stash with timestamp to ensure unique hash
        # Use microseconds to ensure uniqueness even if called multiple times in the same second
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        stash_message = f"Auto-stash before checkout ({timestamp})"
        success, stash_hash, error_msg = cli.stash(repo_path, action="save", message=stash_message)
        
        if not success:
            # If error is about unique constraint, try with a more unique message
            if "UNIQUE constraint" in error_msg or "stashes.hash" in error_msg:
                # Add random component to ensure uniqueness
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                random_suffix = random.randint(1000, 9999)
                stash_message = f"Auto-stash before checkout ({timestamp}-{random_suffix})"
                success, stash_hash, error_msg = cli.stash(repo_path, action="save", message=stash_message)
            
            if not success:
                self.report({'ERROR'}, f"Failed to stash changes: {error_msg}")
                return {'CANCELLED'}

        self.report({'INFO'}, f"Stashed changes: {stash_hash[:16] + '...' if stash_hash else 'unknown'}")

        # Now proceed with checkout (bypassing change check since we just stashed)
        if self.target_type == "commit":
            # Normalize commit hash to standard format (8 chars)
            from ..utils.helpers import normalize_commit_hash
            import logging
            logger = logging.getLogger(__name__)
            
            commit_hash = normalize_commit_hash(self.target_value)
            if not commit_hash:
                self.report({'ERROR'}, f"Invalid commit hash: {self.target_value[:16] if self.target_value else 'empty'}...")
                return {'CANCELLED'}
            
            logger.debug(f"Stash and checkout: using normalized commit hash {commit_hash}")
            
            # Call checkout_commit operator with skip_change_check flag
            try:
                result = bpy.ops.df.checkout_commit(
                    commit_hash=commit_hash,
                    skip_change_check=True
                )
            except RuntimeError as e:
                # Catch RuntimeError from operator execution
                error_msg = str(e)
                logger.error(f"Checkout operator failed: {error_msg}")
                
                # Extract error message from RuntimeError
                if "Commit not found" in error_msg or "commit not found" in error_msg.lower():
                    self.report({'ERROR'}, f"Commit not found: {commit_hash}\nPlease check the commit hash in the history panel.")
                else:
                    self.report({'ERROR'}, f"Failed to checkout commit: {error_msg}")
                return {'CANCELLED'}
            
            # Check if checkout succeeded
            if result != {'FINISHED'}:
                logger.error(f"Checkout failed: {result}")
                self.report({'ERROR'}, f"Failed to checkout commit after stashing.\nPlease check the commit hash in the history panel.")
                return {'CANCELLED'}
        elif self.target_type == "branch":
            # Call switch_branch operator with skip_change_check flag
            bpy.ops.df.switch_branch(
                branch_name=self.target_value,
                skip_change_check=True
            )
        
        return {'FINISHED'}


class DF_OT_save_stash(Operator):
    """Save current changes to stash."""
    bl_idname = "df.save_stash"
    bl_label = "Save Stash"
    bl_description = "Save current uncommitted changes to stash"
    bl_options = {'REGISTER', 'UNDO'}

    message: bpy.props.StringProperty(
        name="Message",
        description="Stash message",
        default="Stash"
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        cli = get_cli()
        success, stash_hash, error_msg = cli.stash(
            repo_path, 
            action="save", 
            message=self.message.strip() if self.message.strip() else "Stash"
        )

        if success:
            self.report({'INFO'}, f"Saved stash: {stash_hash[:16] + '...' if stash_hash else 'unknown'}")
            # Refresh stash list to update UI
            bpy.ops.df.refresh_stashes()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to save stash: {error_msg}")
            return {'CANCELLED'}


class DF_OT_list_stashes(Operator):
    """List all stashes."""
    bl_idname = "df.list_stashes"
    bl_label = "List Stashes"
    bl_description = "List all stashes"
    bl_options = {'REGISTER'}

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        cli = get_cli()
        success, stashes, error_msg = cli.stash(repo_path, action="list")

        if success:
            if stashes:
                stash_list = "\n".join([f"  {s['hash'][:16]}...: {s['message']}" for s in stashes])
                self.report({'INFO'}, f"Stashes:\n{stash_list}")
            else:
                self.report({'INFO'}, "No stashes found")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to list stashes: {error_msg}")
            return {'CANCELLED'}


class DF_OT_apply_stash(Operator):
    """Apply a stash."""
    bl_idname = "df.apply_stash"
    bl_label = "Apply Stash"
    bl_description = "Apply a stash (keep stash)"
    bl_options = {'REGISTER', 'UNDO'}

    stash_hash: bpy.props.StringProperty(
        name="Stash Hash",
        description="Stash hash to apply (leave empty for latest)",
        default=""
    )

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        cli = get_cli()
        success, error_msg = cli.stash_apply(
            repo_path, 
            stash_hash=self.stash_hash if self.stash_hash else None
        )

        if success:
            self.report({'INFO'}, "Applied stash")
            # Refresh stash list to update UI
            bpy.ops.df.refresh_stashes()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to apply stash: {error_msg}")
            return {'CANCELLED'}


class DF_OT_pop_stash(Operator):
    """Pop a stash (apply and remove)."""
    bl_idname = "df.pop_stash"
    bl_label = "Pop Stash"
    bl_description = "Apply and remove a stash"
    bl_options = {'REGISTER', 'UNDO'}

    stash_hash: bpy.props.StringProperty(
        name="Stash Hash",
        description="Stash hash to pop (leave empty for latest)",
        default=""
    )

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        cli = get_cli()
        success, error_msg = cli.stash_pop(
            repo_path, 
            stash_hash=self.stash_hash if self.stash_hash else None
        )

        if success:
            self.report({'INFO'}, "Popped stash")
            # Refresh stash list to update UI (stash was removed)
            bpy.ops.df.refresh_stashes()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to pop stash: {error_msg}")
            return {'CANCELLED'}


class DF_OT_refresh_stashes(Operator):
    """Refresh stash list."""
    bl_idname = "df.refresh_stashes"
    bl_label = "Refresh Stashes"
    bl_description = "Refresh the list of stashes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        cli = get_cli()
        success, stashes, error_msg = cli.stash(repo_path, action="list")

        if not success:
            self.report({'ERROR'}, f"Failed to list stashes: {error_msg}")
            return {'CANCELLED'}

        # Update stash list
        scene = context.scene
        scene.df_stashes.clear()

        for stash_data in stashes:
            stash = scene.df_stashes.add()
            stash.hash = stash_data.get("hash", "")
            stash.message = stash_data.get("message", "")
            # Note: created_at might not be available from CLI output
            stash.created_at = 0

        # Reset selection index if it's out of bounds
        if hasattr(scene, 'df_stash_list_index'):
            if scene.df_stash_list_index >= len(scene.df_stashes):
                scene.df_stash_list_index = max(0, len(scene.df_stashes) - 1)

        self.report({'INFO'}, f"Refreshed {len(stashes)} stashes")
        return {'FINISHED'}


class DF_OT_stash_drop(Operator):
    """Drop a stash (delete without applying)."""
    bl_idname = "df.stash_drop"
    bl_label = "Drop Stash"
    bl_description = "Delete a stash without applying"
    bl_options = {'REGISTER', 'UNDO'}

    stash_hash: bpy.props.StringProperty(
        name="Stash Hash",
        description="Stash hash to drop",
        default=""
    )

    def invoke(self, context, event):
        # Show confirmation dialog
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        if not self.stash_hash:
            self.report({'ERROR'}, "Stash hash required")
            return {'CANCELLED'}

        cli = get_cli()
        success, _, error_msg = cli.stash(repo_path, action="drop", message=self.stash_hash)

        if success:
            self.report({'INFO'}, f"Dropped stash: {self.stash_hash[:16]}...")
            # Refresh stash list
            bpy.ops.df.refresh_stashes()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to drop stash: {error_msg}")
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(DF_OT_stash_and_checkout)
    bpy.utils.register_class(DF_OT_save_stash)
    bpy.utils.register_class(DF_OT_list_stashes)
    bpy.utils.register_class(DF_OT_apply_stash)
    bpy.utils.register_class(DF_OT_pop_stash)
    bpy.utils.register_class(DF_OT_refresh_stashes)
    bpy.utils.register_class(DF_OT_stash_drop)


def unregister():
    bpy.utils.unregister_class(DF_OT_stash_drop)
    bpy.utils.unregister_class(DF_OT_refresh_stashes)
    bpy.utils.unregister_class(DF_OT_pop_stash)
    bpy.utils.unregister_class(DF_OT_apply_stash)
    bpy.utils.unregister_class(DF_OT_list_stashes)
    bpy.utils.unregister_class(DF_OT_save_stash)
    bpy.utils.unregister_class(DF_OT_stash_and_checkout)

