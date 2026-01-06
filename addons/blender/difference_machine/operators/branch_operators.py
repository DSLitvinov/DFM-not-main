"""
Operators for branch management.
"""

import bpy
from bpy.types import Operator
from pathlib import Path
from ..utils.forester_cli import get_cli, ForesterCLIError
from ..utils.helpers import get_repository_path


class DF_OT_refresh_branches(Operator):
    """Refresh branch list."""
    bl_idname = "df.refresh_branches"
    bl_label = "Refresh Branches"
    bl_description = "Refresh the list of branches"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        cli = get_cli()
        success, branches, error_msg = cli.branch(repo_path, action="list")
        
        if not success:
            self.report({'ERROR'}, f"Failed to list branches: {error_msg}")
            return {'CANCELLED'}
        
        # Update branch list
        scene = context.scene
        scene.df_branches.clear()
        
        # First pass: collect all branches with their HEAD commit hashes
        branch_heads = {}  # branch_name -> head_commit_hash
        for branch_data in branches:
            branch_name = branch_data["name"]
            # Get HEAD commit hash for this branch
            success_status, status_data, _ = cli.status(repo_path)
            # Get commits to find HEAD
            success, commits, _ = cli.log(repo_path, branch=branch_name, limit=1)
            if success and commits and len(commits) > 0:
                branch_heads[branch_name] = commits[0].get("hash", "").strip()
            else:
                branch_heads[branch_name] = ""
        
        # Second pass: create branch items and determine parent branches
        for branch_data in branches:
            branch = scene.df_branches.add()
            branch.name = branch_data["name"]
            branch.is_current = branch_data["is_current"]
            
            # Get commit count for this branch
            # Limit history depth to avoid UI freezes on large repos
            success, commits, _ = cli.log(repo_path, branch=branch_data["name"], limit=200)
            branch.commit_count = len(commits) if success and commits else 0
            
            # Determine parent branch: find branch with same HEAD commit_hash that was created earlier
            # (or is "main" if this is the first branch)
            current_head = branch_heads.get(branch_data["name"], "")
            parent_branch = ""
            
            if current_head:
                # Find other branches with the same HEAD commit_hash
                for other_branch_name, other_head in branch_heads.items():
                    if (other_branch_name != branch_data["name"] and 
                        other_head == current_head and 
                        other_head):
                        # This could be the parent - prefer "main" if it exists
                        if other_branch_name == "main":
                            parent_branch = "main"
                            break
                        elif not parent_branch:
                            parent_branch = other_branch_name
            
            branch.parent_branch = parent_branch
        
        # IMPORTANT: Refresh commit history AFTER branch list is updated
        # This ensures refresh_history gets the correct current branch from status
        # We need to refresh history to show commits for the CURRENT branch
        try:
            # Get current branch explicitly to ensure we refresh for the right branch
            success_status, status_data, _ = cli.status(repo_path)
            if success_status and status_data:
                current_branch = status_data.get("branch")
                # Refresh history will use this current branch
                bpy.ops.df.refresh_history()
            else:
                # Fallback: try to refresh anyway
                bpy.ops.df.refresh_history()
        except Exception as e:
            # Database might be outdated (missing reflog table), but branches are still refreshed
            # User can run rebuild to fix the database
            pass
        
        self.report({'INFO'}, f"Refreshed {len(branches)} branches")
        return {'FINISHED'}


class DF_OT_create_branch(Operator):
    """Create a new branch."""
    bl_idname = "df.create_branch"
    bl_label = "Create Branch"
    bl_description = "Create a new branch"
    bl_options = {'REGISTER', 'UNDO'}

    branch_name: bpy.props.StringProperty(
        name="Branch Name",
        description="Name of the new branch",
        default="",
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if not self.branch_name or not self.branch_name.strip():
            self.report({'ERROR'}, "Branch name cannot be empty")
            return {'CANCELLED'}
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        cli = get_cli()
        success, _, error_msg = cli.branch(repo_path, action="create", branch_name=self.branch_name.strip())
        
        if success:
            self.report({'INFO'}, f"Created branch '{self.branch_name}'")
            # IMPORTANT: Refresh branch list (this will also refresh commit history)
            # The new branch points to the same commit as current branch, so commits are the same
            # But we need to refresh to ensure UI shows correct state
            bpy.ops.df.refresh_branches()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to create branch: {error_msg}")
            return {'CANCELLED'}


class DF_OT_switch_branch(Operator):
    """Switch to a different branch."""
    bl_idname = "df.switch_branch"
    bl_label = "Switch Branch"
    bl_description = "Switch to a different branch"
    bl_options = {'REGISTER', 'UNDO'}

    branch_name: bpy.props.StringProperty(
        name="Branch Name",
        description="Name of the branch to switch to",
        default="",
    )
    
    skip_change_check: bpy.props.BoolProperty(
        name="Skip Change Check",
        description="Skip checking for uncommitted changes",
        default=False,
        options={'HIDDEN', 'SKIP_SAVE'}
    )

    def invoke(self, context, event):
        # Get selected branch from list
        scene = context.scene
        if hasattr(scene, 'df_branch_list_index') and scene.df_branch_list_index >= 0:
            if scene.df_branch_list_index < len(scene.df_branches):
                self.branch_name = scene.df_branches[scene.df_branch_list_index].name
        
        if not self.branch_name:
            return context.window_manager.invoke_props_dialog(self)
        
        # Skip change check if flag is set (e.g., called from stash_and_checkout)
        if self.skip_change_check:
            return self.execute(context)
        
        # Check for uncommitted changes
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        cli = get_cli()
        success, status_data, _ = cli.status(repo_path)
        
        if success and status_data:
            # Check if there are uncommitted changes
            # If clean is True, no changes; otherwise check lists
            is_clean = status_data.get("clean", False)
            has_changes = (
                not is_clean or
                len(status_data.get("modified", [])) > 0 or
                len(status_data.get("deleted", [])) > 0 or
                len(status_data.get("untracked", [])) > 0
            )
            
            if has_changes:
                # Show dialog with Cancel and Stash options
                return context.window_manager.invoke_props_dialog(self, width=400)
        
        return self.execute(context)

    def draw(self, context):
        """Draw dialog content for uncommitted changes."""
        layout = self.layout
        layout.label(text="There are uncommitted changes.", icon='ERROR')
        layout.separator()
        layout.label(text="Please commit or stash your changes", icon='INFO')
        layout.label(text="before switching branch.")
        layout.separator()
        
        # Custom buttons
        row = layout.row()
        row.scale_y = 1.5
        op = row.operator("df.stash_and_checkout", text="Stash", icon='PACKAGE')
        op.target_type = "branch"
        op.target_value = self.branch_name
        
        # Note: Cancel button is automatically provided by invoke_props_dialog

    def execute(self, context):
        if not self.branch_name:
            self.report({'ERROR'}, "Branch name required")
            return {'CANCELLED'}
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Check if there are still uncommitted changes
        # (user might have clicked OK instead of Stash)
        # Skip this check if skip_change_check is set
        if not self.skip_change_check:
            cli = get_cli()
            success, status_data, _ = cli.status(repo_path)
            if success and status_data:
                is_clean = status_data.get("clean", False)
                has_changes = (
                    not is_clean or
                    len(status_data.get("modified", [])) > 0 or
                    len(status_data.get("deleted", [])) > 0 or
                    len(status_data.get("untracked", [])) > 0
                )
                if has_changes:
                    # Still has changes, user should use Stash button
                    self.report({'INFO'}, "Please use Stash button to save changes before switching branch")
                    return {'CANCELLED'}
        
        cli = get_cli()
        success, error_msg = cli.checkout(repo_path, self.branch_name)
        
        if success:
            self.report({'INFO'}, f"Switched to branch '{self.branch_name}'")
            # IMPORTANT: Refresh branch list (this will also refresh commit history)
            # refresh_branches calls refresh_history at the end, which will get commits
            # for the NEW current branch (which was just switched to)
            bpy.ops.df.refresh_branches()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to switch branch: {error_msg}")
            return {'CANCELLED'}


class DF_OT_delete_branch(Operator):
    """Delete a branch."""
    bl_idname = "df.delete_branch"
    bl_label = "Delete Branch"
    bl_description = "Delete a branch (with confirmation dialog)"
    bl_options = {'REGISTER', 'UNDO'}

    branch_name: bpy.props.StringProperty(
        name="Branch Name",
        description="Name of the branch to delete",
        default="",
    )

    def invoke(self, context, event):
        # Show confirmation dialog
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        if not self.branch_name:
            self.report({'ERROR'}, "Branch name required")
            return {'CANCELLED'}
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Check if this is the current branch
        cli = get_cli()
        success, branches, _ = cli.branch(repo_path, action="list")
        if success:
            for branch_data in branches:
                if branch_data["name"] == self.branch_name and branch_data.get("is_current", False):
                    self.report({'ERROR'}, f"Cannot delete current branch '{self.branch_name}'. Switch to another branch first.")
                    return {'CANCELLED'}
        
        cli = get_cli()
        success, _, error_msg = cli.branch(repo_path, action="delete", branch_name=self.branch_name)
        
        if success:
            self.report({'INFO'}, f"Deleted branch '{self.branch_name}'")
            # Refresh branch list
            bpy.ops.df.refresh_branches()
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to delete branch: {error_msg}")
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(DF_OT_refresh_branches)
    bpy.utils.register_class(DF_OT_create_branch)
    bpy.utils.register_class(DF_OT_switch_branch)
    bpy.utils.register_class(DF_OT_delete_branch)


def unregister():
    bpy.utils.unregister_class(DF_OT_delete_branch)
    bpy.utils.unregister_class(DF_OT_switch_branch)
    bpy.utils.unregister_class(DF_OT_create_branch)
    bpy.utils.unregister_class(DF_OT_refresh_branches)
