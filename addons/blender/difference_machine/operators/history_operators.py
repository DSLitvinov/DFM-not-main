"""
Operators for commit history operations.
"""

import bpy
import subprocess
import shutil
import os
import re
from bpy.types import Operator
from pathlib import Path
from typing import Optional, Tuple
from ..utils.forester_cli import get_cli, ForesterCLIError
from ..utils.helpers import get_repository_path, wait_for_path
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class DF_OT_refresh_history(Operator):
    """Refresh commit history."""
    bl_idname = "df.refresh_history"
    bl_label = "Refresh History"
    bl_description = "Refresh the commit history list"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        cli = get_cli()
        # IMPORTANT: Get current branch from status to ensure we query the correct branch
        # This is critical after branch switches to avoid showing commits from wrong branch
        current_branch = None
        success_status, status_data, _ = cli.status(repo_path)
        if success_status and status_data:
            current_branch = status_data.get("branch")
            # Ensure branch name is not empty
            if current_branch:
                current_branch = current_branch.strip()
                if not current_branch:
                    current_branch = None
        
        # Always explicitly pass current branch to log command if we have it
        # This ensures we get commits for the correct branch, not a stale cached value
        # If branch is None, forester log will use current branch from refs (which should be the same)
        branch_to_query = current_branch if current_branch else None
        success, commits, error_msg = cli.log(repo_path, branch=branch_to_query, limit=100)
        
        if not success:
            # Check if error is about missing reflog table or other database schema issues
            if "reflog" in error_msg.lower() or "no such table" in error_msg.lower():
                self.report({'WARNING'}, 
                    "Database schema is outdated. Please run 'Rebuild Database' in Preferences to fix this.")
                # Try to continue with empty list so UI doesn't break
                commits = []
            else:
                self.report({'ERROR'}, f"Failed to load history: {error_msg}")
                return {'CANCELLED'}
        
        # Get current HEAD as fallback (if log doesn't provide is_head)
        current_head = None
        success_status, status_data, _ = cli.status(repo_path)
        if success_status and status_data:
            current_head = status_data.get("head")
            if current_head:
                current_head = current_head.strip().lower()
        
        # Update commit list - first save to backup collection (df_commits_all)
        scene = context.scene
        scene.df_commits_all.clear()
        
        for commit_data in commits:
            commit_all = scene.df_commits_all.add()
            commit_hash_raw = commit_data.get("hash", "").strip()
            # Normalize commit hash to standard format (64 chars)
            from ..utils.helpers import normalize_commit_hash
            commit_hash = normalize_commit_hash(commit_hash_raw)
            if not commit_hash:
                logger.warning(f"Invalid commit hash skipped: {commit_hash_raw[:16]}...")
                continue
            commit_all.hash = commit_hash
            commit_all.message = commit_data.get("message", "")
            commit_all.author = commit_data.get("author", "")
            commit_all.tag = commit_data.get("tag", "") or ""
            # Parse date string to timestamp if needed
            # Parse date string to timestamp
            # Note: Currently using 0 as placeholder. Date parsing can be added when needed.
            commit_all.timestamp = 0
            # Mark HEAD commit - use is_head from log output if available, otherwise fallback to status
            is_head = commit_data.get("is_head", False)
            if not is_head and current_head:
                # Fallback: compare with current HEAD from status
                commit_hash_normalized = commit_hash.lower() if commit_hash else ""
                is_head = (commit_hash_normalized == current_head)
            commit_all.is_head = is_head
        
        # Now apply tag filter to populate df_commits
        # Get current tag filter
        props = scene.df_commit_props
        tag_filter = props.tag_search_filter.strip().lower() if props.tag_search_filter else ""
        
        scene.df_commits.clear()
        
        if tag_filter:
            # Filter commits where tag matches (case-insensitive partial match)
            for commit_all in scene.df_commits_all:
                commit_tag = (commit_all.tag or "").strip().lower()
                if tag_filter in commit_tag:
                    # Copy commit to filtered list
                    commit = scene.df_commits.add()
                    commit.hash = commit_all.hash
                    commit.message = commit_all.message
                    commit.author = commit_all.author
                    commit.tag = commit_all.tag
                    commit.timestamp = commit_all.timestamp
                    commit.commit_type = commit_all.commit_type
                    commit.selected_mesh_names = commit_all.selected_mesh_names
                    commit.screenshot_hash = commit_all.screenshot_hash
                    commit.is_selected = commit_all.is_selected
                    commit.is_head = commit_all.is_head
        else:
            # No filter - copy all commits
            for commit_all in scene.df_commits_all:
                commit = scene.df_commits.add()
                commit.hash = commit_all.hash
                commit.message = commit_all.message
                commit.author = commit_all.author
                commit.tag = commit_all.tag
                commit.timestamp = commit_all.timestamp
                commit.commit_type = commit_all.commit_type
                commit.selected_mesh_names = commit_all.selected_mesh_names
                commit.screenshot_hash = commit_all.screenshot_hash
                commit.is_selected = commit_all.is_selected
                commit.is_head = commit_all.is_head
        
        # Reset selection index if it's out of bounds
        if scene.df_commit_list_index >= len(scene.df_commits):
            scene.df_commit_list_index = max(0, len(scene.df_commits) - 1)
        
        self.report({'INFO'}, f"Loaded {len(scene.df_commits_all)} commits" + (f" (filtered: {len(scene.df_commits)})" if tag_filter else ""))
        return {'FINISHED'}


class DF_OT_show_commit(Operator):
    """Show commit details."""
    bl_idname = "df.show_commit"
    bl_label = "Show Commit"
    bl_description = "Show details of a commit"
    bl_options = {'REGISTER', 'UNDO'}

    commit_hash: bpy.props.StringProperty(
        name="Commit Hash",
        description="Hash of the commit to show",
        default="",
    )

    def execute(self, context):
        if not self.commit_hash:
            self.report({'ERROR'}, "Commit hash required")
            return {'CANCELLED'}
        
        # Normalize commit hash to standard format (8 chars)
        from ..utils.helpers import normalize_commit_hash
        commit_hash = normalize_commit_hash(self.commit_hash)
        if not commit_hash:
            self.report({'ERROR'}, f"Invalid commit hash: {self.commit_hash[:16] if self.commit_hash else 'empty'}...")
            return {'CANCELLED'}
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        cli = get_cli()
        success, commit_data, error_msg = cli.show(repo_path, commit_hash)
        
        if not success:
            self.report({'ERROR'}, f"Failed to show commit: {error_msg}")
            return {'CANCELLED'}
        
        # Display commit details via report (UI popup is shown via operator report)
        message = commit_data.get("message", "No message")
        self.report({'INFO'}, f"Commit {commit_hash}: {message}")
        return {'FINISHED'}


class DF_OT_checkout_commit(Operator):
    """Checkout a commit to working directory and reopen Blender."""
    bl_idname = "df.checkout_commit"
    bl_label = "Checkout"
    bl_description = "Checkout a commit to working directory and reopen Blender"
    bl_options = {'REGISTER', 'UNDO'}

    commit_hash: bpy.props.StringProperty(
        name="Commit Hash",
        description="Hash of the commit to checkout",
        default="",
    )
    
    skip_change_check: bpy.props.BoolProperty(
        name="Skip Change Check",
        description="Skip checking for uncommitted changes",
        default=False,
        options={'HIDDEN', 'SKIP_SAVE'}
    )

    def invoke(self, context, event):
        """Check for uncommitted changes before checkout."""
        if not self.commit_hash:
            self.report({'ERROR'}, "Commit hash required")
            return {'CANCELLED'}
        
        # Skip change check if flag is set (e.g., called from stash_and_checkout)
        if self.skip_change_check:
            return self.execute(context)
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Check for uncommitted changes
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
        
        # No changes, proceed directly
        return self.execute(context)

    def draw(self, context):
        """Draw dialog content for uncommitted changes."""
        layout = self.layout
        layout.label(text="There are uncommitted changes.", icon='ERROR')
        layout.separator()
        layout.label(text="Please commit or stash your changes", icon='INFO')
        layout.label(text="before checking out.")
        layout.separator()
        
        # Custom buttons
        row = layout.row()
        row.scale_y = 1.5
        op = row.operator("df.stash_and_checkout", text="Stash", icon='PACKAGE')
        op.target_type = "commit"
        op.target_value = self.commit_hash
        
        # Note: Cancel button is automatically provided by invoke_props_dialog

    def execute(self, context):
        if not self.commit_hash:
            self.report({'ERROR'}, "Commit hash required")
            return {'CANCELLED'}
        
        # Normalize commit hash to standard format (8 chars)
        from ..utils.helpers import normalize_commit_hash
        commit_hash = normalize_commit_hash(self.commit_hash)
        if not commit_hash:
            self.report({'ERROR'}, f"Invalid commit hash: {self.commit_hash[:16] if self.commit_hash else 'empty'}...")
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
                    self.report({'INFO'}, "Please use Stash button to save changes before checkout")
                    return {'CANCELLED'}
        
        # Save current file if it's modified
        current_file = bpy.data.filepath
        if current_file and bpy.data.is_dirty:
            try:
                bpy.ops.wm.save_mainfile()
            except RuntimeError as e:
                logger.warning(f"Failed to save file before checkout: {e}")
        
        cli = get_cli()
        
        # Log the commit hash being used for debugging
        logger.debug(f"Attempting to checkout commit: {commit_hash} (normalized from {len(self.commit_hash) if self.commit_hash else 0} chars)")
        
        # Verify commit exists using show command
        success_show, commit_data, show_error = cli.show(repo_path, commit_hash)
        if not success_show:
            # Commit doesn't exist - provide helpful error message
            error_detail = show_error if show_error else "Commit not found"
            logger.error(f"Commit {commit_hash} does not exist: {error_detail}")
            
            # Try to get list of available commits to help user
            available_msg = ""
            try:
                success_log, commits, _ = cli.log(repo_path, limit=10)
                if success_log and commits:
                    from ..utils.helpers import normalize_commit_hash
                    available_hashes = [normalize_commit_hash(c.get('hash', '')) for c in commits[:5]]
                    available_hashes = [h for h in available_hashes if h]  # Filter None values
                    if available_hashes:
                        available_msg = f"\nAvailable commits: {', '.join(available_hashes)}"
                        logger.info(f"Available commits: {available_hashes}")
            except Exception as e:
                logger.debug(f"Failed to get commit list: {e}")
            
            # Provide helpful error message
            error_text = f"Commit '{commit_hash}' not found in repository.{available_msg}\nPlease select a commit from the history panel."
            self.report({'ERROR'}, error_text)
            return {'CANCELLED'}
        
        logger.debug(f"Using normalized hash for checkout: {commit_hash}")
        
        # Now attempt checkout with the normalized hash
        success, error_msg = cli.checkout(repo_path, commit_hash)
        
        if not success:
            # Provide more helpful error message
            error_detail = error_msg if error_msg else "Unknown error"
            logger.error(f"Checkout failed for commit {commit_hash}: {error_detail}")
            self.report({'ERROR'}, f"Failed to checkout commit: {error_detail}")
            return {'CANCELLED'}
        
        # Reopen Blender file if it exists
        if current_file and os.path.exists(current_file):
            try:
                bpy.ops.wm.open_mainfile(filepath=current_file)
            except RuntimeError as e:
                logger.warning(f"Failed to open file after checkout: {e}")
                # If open_mainfile fails, try revert
                try:
                    bpy.ops.wm.revert_mainfile()
                except RuntimeError as e2:
                    logger.warning(f"Failed to revert file: {e2}")
        
        # Refresh history to update HEAD marker
        bpy.ops.df.refresh_history()
        
        self.report({'INFO'}, f"Checked out commit {commit_hash[:16]}... Blender file reloaded.")
        return {'FINISHED'}


class DF_OT_compare_project(Operator):
    """Compare project by checking out commit to temporary folder and opening new Blender instance."""
    bl_idname = "df.compare_project"
    bl_label = "Compare"
    bl_description = "Checkout commit to temporary folder and open in new Blender instance"
    bl_options = {'REGISTER', 'UNDO'}

    commit_hash: bpy.props.StringProperty(
        name="Commit Hash",
        description="Hash of the commit to compare with",
        default="",
    )

    def execute(self, context):
        if not self.commit_hash:
            self.report({'ERROR'}, "Commit hash required")
            return {'CANCELLED'}
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Normalize commit hash to standard format (8 chars)
        from ..utils.helpers import normalize_commit_hash
        commit_hash = normalize_commit_hash(self.commit_hash)
        if not commit_hash:
            self.report({'ERROR'}, f"Invalid commit hash: {self.commit_hash[:16] if self.commit_hash else 'empty'}...")
            return {'CANCELLED'}
        
        # Check if comparison is already active for this commit
        is_active = (
            getattr(context.scene, 'df_project_comparison_active', False) and
            getattr(context.scene, 'df_project_comparison_commit_hash', '') == commit_hash
        )
        
        # If comparison is active, deactivate it and clean up
        if is_active:
            # Use CLI to clean up
            cli = get_cli()
            success, error_msg = cli.compare(repo_path, commit_hash, cleanup=True)
            if not success:
                self.report({'WARNING'}, f"Could not clean up: {error_msg}")
            
            # Deactivate comparison state
            context.scene.df_project_comparison_active = False
            context.scene.df_project_comparison_commit_hash = ""
            return {'FINISHED'}
        
        # Activate comparison: use CLI command
        cli = get_cli()
        
        # Get Blender executable path
        blender_exe = bpy.app.binary_path
        
        if not blender_exe:
            self.report({'ERROR'}, "Could not find Blender executable")
            return {'CANCELLED'}
        
        # Use CLI compare command with editor path
        success, error_msg = cli.compare(repo_path, commit_hash, editor_path=blender_exe)
        
        if not success:
            self.report({'ERROR'}, f"Failed to compare commit: {error_msg}")
            return {'CANCELLED'}
        
        # Store comparison state
        context.scene.df_project_comparison_active = True
        context.scene.df_project_comparison_commit_hash = commit_hash
        
        self.report({'INFO'}, f"Opened commit {commit_hash} for comparison")
        return {'FINISHED'}


class DF_OT_delete_commit(Operator):
    """Delete a commit."""
    bl_idname = "df.delete_commit"
    bl_label = "Delete Commit"
    bl_description = "Delete a commit from repository"
    bl_options = {'REGISTER', 'UNDO'}

    commit_hash: bpy.props.StringProperty(
        name="Commit Hash",
        description="Hash of the commit to delete",
        default="",
    )

    def execute(self, context):
        if not self.commit_hash:
            self.report({'ERROR'}, "Commit hash required")
            return {'CANCELLED'}
        
        # Normalize commit hash to standard format (8 chars)
        from ..utils.helpers import normalize_commit_hash
        commit_hash = normalize_commit_hash(self.commit_hash)
        if not commit_hash:
            self.report({'ERROR'}, f"Invalid commit hash: {self.commit_hash[:16] if self.commit_hash else 'empty'}...")
            return {'CANCELLED'}
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        cli = get_cli()
        
        # Check if commit is HEAD before attempting deletion
        # But allow deletion if it's the only commit (no parent)
        # Go code will handle this properly, but we can provide better feedback
        show_success, commit_data, _ = cli.show(repo_path, commit_hash)
        if show_success and commit_data:
            parent_hash = commit_data.get("parent")
            is_only_commit = not parent_hash or parent_hash.strip() == ""
            
            # If it's the only commit, it can be deleted (will make branch orphan)
            # Go code handles this case properly
        
        # Try to delete commit
        success, error_msg = cli.delete_commit(repo_path, commit_hash)
        
        if not success:
            # Check if error is about tag reference - automatically delete the tag
            if "referenced by tag" in error_msg:
                # Parse tag name from error message
                # Format: "cannot delete commit X - it is referenced by tag 'TAG_NAME'"
                tag_match = re.search(r"tag '([^']+)'", error_msg)
                if tag_match:
                    tag_name = tag_match.group(1)
                    # Automatically delete the tag
                    tag_success, tag_error = cli.delete_tag(repo_path, tag_name)
                    if tag_success:
                        # Retry commit deletion after tag removal
                        success, error_msg = cli.delete_commit(repo_path, commit_hash)
                        if success:
                            # Refresh history after deletion
                            bpy.ops.df.refresh_history()
                            self.report({'INFO'}, 
                                f"Deleted tag '{tag_name}' and commit {commit_hash}")
                            return {'FINISHED'}
                        else:
                            # Tag deleted but commit deletion still failed
                            self.report({'WARNING'}, 
                                f"Deleted tag '{tag_name}' but failed to delete commit: {error_msg}")
                            return {'CANCELLED'}
                    else:
                        self.report({'ERROR'}, 
                            f"Cannot delete commit {commit_hash} - it is referenced by tag '{tag_name}'. "
                            f"Failed to delete tag: {tag_error}")
                        return {'CANCELLED'}
                else:
                    # Could not parse tag name
                    self.report({'ERROR'}, 
                        f"Cannot delete commit {commit_hash} - it is referenced by a tag. "
                        f"Delete the tag first.")
                    return {'CANCELLED'}
            
            # Provide more user-friendly error messages for other cases
            if "HEAD of branch" in error_msg or "HEAD of branches" in error_msg:
                # Check if it's the only commit - Go code should allow this, but double-check
                if show_success and commit_data:
                    parent_hash = commit_data.get("parent")
                    is_only_commit = not parent_hash or parent_hash.strip() == ""
                    if is_only_commit:
                        # This should not happen if Go code is correct, but provide helpful message
                        self.report({'ERROR'}, 
                            f"Cannot delete commit {commit_hash} - unexpected error. "
                            f"Please try again or use 'forester commit --delete {commit_hash}' from command line.")
                    else:
                        self.report({'ERROR'}, 
                            f"Cannot delete commit {commit_hash} - it is HEAD of a branch. "
                            f"Please checkout another commit first.")
            elif "has child commit" in error_msg or "child commit" in error_msg:
                self.report({'ERROR'}, 
                    f"Cannot delete commit {commit_hash} - it has child commits. "
                    f"Delete child commits first, or use 'forester gc' to clean up orphaned commits.")
            else:
                self.report({'ERROR'}, f"Failed to delete commit: {error_msg}")
            return {'CANCELLED'}
        
        # Refresh history after deletion
        bpy.ops.df.refresh_history()
        
        # Check if it was the only commit (orphan branch case)
        if show_success and commit_data:
            parent_hash = commit_data.get("parent")
            is_only_commit = not parent_hash or parent_hash.strip() == ""
            if is_only_commit:
                self.report({'INFO'}, 
                    f"Deleted commit {self.commit_hash[:16]}... (was the only commit, branch is now orphan)")
            else:
                self.report({'INFO'}, f"Deleted commit {self.commit_hash[:16]}...")
        else:
            self.report({'INFO'}, f"Deleted commit {self.commit_hash[:16]}...")
        
        return {'FINISHED'}


def _get_object_library_info(obj: bpy.types.Object) -> Optional[dict]:
    """
    Get library information for linked/append object.
    
    Args:
        obj: Blender object
    
    Returns:
        Dict with 'library_path' and 'library_name' or None if not linked
    """
    if not obj:
        return None
    
    # Check if object data is from library
    if obj.data and hasattr(obj.data, 'library'):
        if obj.data.library:
            return {
                'library_path': obj.data.library.filepath,
                'library_name': obj.data.library.name,
                'is_linked': True
            }
    
    # Check if object itself is from library
    if hasattr(obj, 'library') and obj.library:
        return {
            'library_path': obj.library.filepath,
            'library_name': obj.library.name,
            'is_linked': True
        }
    
    return None


def _find_object_in_scene_file_from_commit(
    repo_path: Path,
    commit_hash: str,
    scene_file_name: str,
    object_name: str,
    object_type: str = None
) -> Optional[Tuple[str, Path, Optional[str]]]:
    """
    Find scene file in commit and extract object from it.
    
    Args:
        repo_path: Repository root path
        commit_hash: Commit hash
        scene_file_name: Name of the scene file (e.g., "2B.blend")
        object_name: Object name to search for
        object_type: Optional object type (MESH, LIGHT, etc.)
    
    Returns:
        Tuple of (blob_hash, blend_path, object_name_in_file) or None
    """
    from ..operators.mesh_io import _find_object_in_blend_file
    
    logger.debug(f"_find_object_in_scene_file_from_commit: Looking for '{scene_file_name}' in commit {commit_hash[:8]}")
    logger.debug(f"Searching for object '{object_name}' (type: {object_type})")
    
    import json
    import re
    
    # Read commit
    # Note: Commits are stored by hash of JSON content, not by commit hash
    # We need to search for commit by hash in file contents
    dfm_path = repo_path / ".DFM"
    commits_path = dfm_path / "objects" / "commits" / "sha256"
    
    # First try direct path (in case commit hash matches file hash)
    hash_path = commit_hash[:2] + "/" + commit_hash[2:]
    commit_file = commits_path / hash_path
    
    if not commit_file.exists():
        # Search for commit by hash in file contents
        logger.debug(f"Commit file not found at direct path: {commit_file}")
        logger.debug(f"Searching for commit hash '{commit_hash[:8]}' in commit files...")
        
        commit_file = None
        for commit_file_path in commits_path.rglob("*"):
            if commit_file_path.is_file():
                try:
                    with open(commit_file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Check if this file contains our commit hash
                        if commit_hash in content:
                            # Parse to verify it's the right commit
                            try:
                                commit_json = json.loads(content)
                                if commit_json.get("hash") == commit_hash:
                                    commit_file = commit_file_path
                                    logger.debug(f"Found commit file: {commit_file}")
                                    break
                            except (json.JSONDecodeError, KeyError) as e:
                                logger.debug(f"Error parsing JSON from {commit_file_path}: {e}")
                                # Try regex
                                if f'"hash":"{commit_hash}"' in content:
                                    commit_file = commit_file_path
                                    logger.debug(f"Found commit file (regex): {commit_file}")
                                    break
                except Exception as e:
                    logger.debug(f"Error reading {commit_file_path}: {e}")
                    continue
        
        if not commit_file or not commit_file.exists():
            logger.warning(f"Commit '{commit_hash[:8]}' not found in repository")
            return None
    
    # Parse commit to get tree_hash
    tree_hash = None
    try:
        with open(commit_file, 'r', encoding='utf-8') as f:
            commit_content = f.read()
        
        try:
            commit_json = json.loads(commit_content)
            tree_hash = commit_json.get("tree_hash", "")
        except:
            # Regex fallback
            tree_hash_match = re.search(r'"tree_hash"\s*:\s*"([^"]+)"', commit_content)
            if tree_hash_match:
                tree_hash = tree_hash_match.group(1)
    except Exception as e:
        logger.error(f"Failed to parse commit file: {e}", exc_info=True)
        return None
    
    if not tree_hash:
        logger.warning(f"No tree_hash in commit {commit_hash[:8]}")
        return None
    
    logger.debug(f"Tree hash: {tree_hash[:8]}")
    
    # Read tree
    trees_path = dfm_path / "objects" / "trees" / "sha256"
    tree_hash_path = tree_hash[:2] + "/" + tree_hash[2:]
    tree_file = trees_path / tree_hash_path
    
    if not tree_file.exists():
        logger.warning(f"Tree file not found: {tree_file}")
        return None
    
    logger.debug(f"Reading tree file: {tree_file}")
    
    # Parse tree to find scene file
    try:
        with open(tree_file, 'r', encoding='utf-8') as f:
            tree_content = f.read()
        
        try:
            tree_json = json.loads(tree_content)
            entries = tree_json.get("entries", [])
        except:
            # Regex fallback
            entries_match = re.search(r'"entries"\s*:\s*\[(.*?)\]', tree_content, re.DOTALL)
            if entries_match:
                entries_str = entries_match.group(1)
                entries = []
                entry_matches = re.finditer(
                    r'\{"hash":"([^"]+)","name":"([^"]+)","type":"([^"]+)"',
                    entries_str
                )
                for match in entry_matches:
                    entries.append({
                        "hash": match.group(1),
                        "name": match.group(2),
                        "type": match.group(3)
                    })
            else:
                entries = []
        
        logger.debug(f"Found {len(entries)} entries in tree")
        
        # Log all .blend files found in tree
        blend_files = [e for e in entries if e.get("type") == "blob" and e.get("name", "").endswith(".blend")]
        logger.debug(f"Found {len(blend_files)} .blend files in tree")
        for bf in blend_files[:10]:  # Log first 10
            logger.debug(f"  - {bf.get('name')} (hash: {bf.get('hash', '')[:8] if bf.get('hash') else 'N/A'})")
        
        # Find scene file by name
        blobs_path = dfm_path / "objects" / "blobs" / "sha256"
        
        for entry in entries:
            if entry.get("type") == "blob" and entry.get("name", "").endswith(".blend"):
                entry_name = Path(entry.get("name", "")).name
                entry_path = entry.get("name", "")
                
                logger.debug(f"Checking entry: name='{entry_name}', path='{entry_path}'")
                
                # Check if this is the scene file we're looking for
                if entry_name == scene_file_name or entry_path.endswith(scene_file_name):
                    blob_hash = entry.get("hash")
                    if blob_hash:
                        blob_hash_path = blob_hash[:2] + "/" + blob_hash[2:]
                        blob_file = blobs_path / blob_hash_path
                        
                        logger.debug(f"Matched scene file! Checking blob file: {blob_file}")
                        
                        if blob_file.exists():
                            logger.debug(f"Found scene file '{scene_file_name}' at {blob_file} (hash: {blob_hash[:8]})")
                            
                            # Check if object exists in this blend file
                            logger.debug(f"Searching for object '{object_name}' (type: {object_type}) in {blob_file}")
                            found_name = _find_object_in_blend_file(
                                blob_file, 
                                object_name, 
                                object_type
                            )
                            
                            if found_name:
                                logger.debug(f"✓ Found object '{found_name}' in scene file")
                                return (blob_hash, blob_file, found_name)
                            else:
                                logger.warning(f"✗ Object '{object_name}' (type: {object_type}) not found in scene file {scene_file_name}")
                        else:
                            logger.warning(f"Blob file not found: {blob_file}")
        
        logger.warning(f"Scene file '{scene_file_name}' not found in commit {commit_hash[:8]}")
        logger.debug(f"Searched through {len(blend_files)} .blend files")
        
    except Exception as e:
        logger.error(f"Error searching tree: {e}", exc_info=True)
    
    return None


def _get_object_source_info(obj: bpy.types.Object, repo_path: Path) -> dict:
    from ..utils.logging_config import get_logger
    logger = get_logger(__name__)
    """
    Определяет источник объекта: файл сцены или ассет.
    
    Args:
        obj: Blender object
        repo_path: Repository root path
    
    Returns:
        {
            'source_type': 'scene_file' | 'asset' | 'unknown',
            'source_file': Path или None,
            'library_path': str или None (для ассетов)
        }
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # Проверяем, является ли объект ассетом
    library_info = _get_object_library_info(obj)
    if library_info:
        # Это ассет - используем library_path
        library_path = Path(library_info['library_path'])
        logger.debug(f"Object '{obj.name}' is from library: {library_path}")
        # Нормализуем путь относительно репозитория
        if library_path.is_absolute():
            # Пытаемся найти относительный путь
            try:
                library_path = library_path.relative_to(repo_path)
                logger.debug(f"Library path relative to repo: {library_path}")
            except ValueError:
                # Путь вне репозитория - используем имя файла
                library_path = Path(library_path.name)
                logger.debug(f"Library path outside repo, using filename: {library_path}")
        
        return {
            'source_type': 'asset',
            'source_file': library_path,
            'library_path': str(library_path)
        }
    
    # Объект из текущего файла сцены
    if bpy.data.filepath:
        scene_file = Path(bpy.data.filepath)
        logger.debug(f"Object '{obj.name}' is from scene file: {scene_file}")
        try:
            # Получаем относительный путь от репозитория
            scene_file_rel = scene_file.relative_to(repo_path)
            logger.debug(f"Scene file relative to repo: {scene_file_rel}")
            return {
                'source_type': 'scene_file',
                'source_file': scene_file_rel,
                'library_path': None
            }
        except ValueError:
            # Файл вне репозитория - используем имя файла
            logger.debug(f"Scene file outside repo, using filename: {scene_file.name}")
            return {
                'source_type': 'scene_file',
                'source_file': Path(scene_file.name),
                'library_path': None
            }
    
    logger.warning(f"Could not determine source for object '{obj.name}'")
    return {
        'source_type': 'unknown',
        'source_file': None,
        'library_path': None
    }


def _find_object_in_commit_by_name(
    repo_path: Path, 
    commit_hash: str, 
    object_name: str,
    object_type: str = None,
    source_info: dict = None
) -> Optional[Tuple[str, Path, Optional[str]]]:
    """
    Find object in commit by name with smart source detection. Supports:
    1. Objects in .blend scene files from tree (searches in specific file if source_info provided)
    2. Objects in asset .blend files from assets directory
    
    Args:
        repo_path: Repository root path
        commit_hash: Commit hash
        object_name: Object name to search for
        object_type: Optional object type (MESH, LIGHT, etc.)
        source_info: Optional dict with source info from _get_object_source_info
    
    Returns:
        Tuple of (hash, blend_path, object_name_in_file) or None
        object_name_in_file may differ from object_name if found in scene file
    """
    from ..operators.mesh_io import _find_object_in_blend_file
    from ..utils.logging_config import get_logger
    
    logger = get_logger(__name__)
    logger.debug(f"_find_object_in_commit_by_name: Searching for '{object_name}' (type: {object_type}) in commit {commit_hash[:8]}")
    logger.debug(f"Source info: {source_info}")
    
    import json
    import re
    
    # Read commit
    dfm_path = repo_path / ".DFM"
    commits_path = dfm_path / "objects" / "commits" / "sha256"
    hash_path = commit_hash[:2] + "/" + commit_hash[2:]
    commit_file = commits_path / hash_path
    
    if not commit_file.exists():
        logger.warning(f"Commit file not found: {commit_file}")
        return None
    
    logger.debug(f"Reading commit file: {commit_file}")
    
    # Parse commit
    tree_hash = None
    
    try:
        with open(commit_file, 'r', encoding='utf-8') as f:
            commit_content = f.read()
        
        try:
            commit_json = json.loads(commit_content)
            tree_hash = commit_json.get("tree_hash", "")
        except:
            # Regex fallback
            tree_hash_match = re.search(r'"tree_hash"\s*:\s*"([^"]+)"', commit_content)
            if tree_hash_match:
                tree_hash = tree_hash_match.group(1)
    except Exception as e:
        logger.error(f"Failed to parse commit file: {e}", exc_info=True)
        return None
    
    logger.debug(f"Commit parsed: tree_hash={tree_hash[:8] if tree_hash else None}")
    
    # Method 1: Search in tree - .blend scene files
    if tree_hash:
        logger.debug(f"Searching in tree: {tree_hash[:8]}")
        trees_path = dfm_path / "objects" / "trees" / "sha256"
        tree_hash_path = tree_hash[:2] + "/" + tree_hash[2:]
        tree_file = trees_path / tree_hash_path
        
        if tree_file.exists():
            logger.debug(f"Reading tree file: {tree_file}")
            try:
                with open(tree_file, 'r', encoding='utf-8') as f:
                    tree_content = f.read()
                
                try:
                    tree_json = json.loads(tree_content)
                    entries = tree_json.get("entries", [])
                except:
                    # Regex fallback
                    entries_match = re.search(r'"entries"\s*:\s*\[(.*?)\]', tree_content, re.DOTALL)
                    if entries_match:
                        entries_str = entries_match.group(1)
                        entries = []
                        entry_matches = re.finditer(
                            r'\{"hash":"([^"]+)","name":"([^"]+)","type":"([^"]+)"',
                            entries_str
                        )
                        for match in entry_matches:
                            entries.append({
                                "hash": match.group(1),
                                "name": match.group(2),
                                "type": match.group(3)
                            })
                    else:
                        entries = []
                
                logger.debug(f"Found {len(entries)} entries in tree")
                
                blobs_path = dfm_path / "objects" / "blobs" / "sha256"
                
                # Если есть информация об источнике, ищем конкретный файл
                target_file_name = None
                target_file_path = None
                if source_info:
                    logger.debug(f"Source info: {source_info}")
                    if source_info['source_type'] == 'scene_file' and source_info['source_file']:
                        # Ищем файл сцены
                        target_file_name = source_info['source_file'].name
                        target_file_path = str(source_info['source_file'])
                        logger.debug(f"Looking for scene file: {target_file_name} (path: {target_file_path})")
                    elif source_info['source_type'] == 'asset' and source_info['source_file']:
                        # Ищем файл ассета
                        target_file_name = source_info['source_file'].name
                        target_file_path = str(source_info['source_file'])
                        logger.debug(f"Looking for asset file: {target_file_name} (path: {target_file_path})")
                
                # Сначала ищем нужный файл, если знаем его имя
                if target_file_name:
                    for entry in entries:
                        if entry.get("type") == "blob" and entry.get("name", "").endswith(".blend"):
                            entry_name = Path(entry.get("name", "")).name
                            entry_path = entry.get("name", "")
                            
                            # Проверяем совпадение по имени файла или полному пути
                            # Используем нормализованные пути для сравнения
                            entry_path_normalized = Path(entry_path).as_posix() if entry_path else None
                            target_path_normalized = target_file_path.as_posix() if target_file_path else None
                            
                            if (entry_name == target_file_name or 
                                entry_path == target_file_path or
                                (target_path_normalized and entry_path_normalized.endswith(target_path_normalized)) or
                                entry_path_normalized.endswith(target_file_name)):
                                blob_hash = entry.get("hash")
                                if blob_hash:
                                    blob_hash_path = blob_hash[:2] + "/" + blob_hash[2:]
                                    blob_file = blobs_path / blob_hash_path
                                    
                                    if blob_file.exists():
                                        logger.debug(f"Checking target file: {blob_file} (hash: {blob_hash[:8]})")
                                        # Ищем объект в этом файле
                                        found_name = _find_object_in_blend_file(
                                            blob_file, 
                                            object_name, 
                                            object_type
                                        )
                                        if found_name:
                                            logger.debug(f"Found object '{found_name}' in target file: {blob_file}")
                                            return (blob_hash, blob_file, found_name)
                                        else:
                                            logger.debug(f"Object '{object_name}' not found in {blob_file}")
                
                # Fallback: перебираем все .blend файлы (если не нашли по имени файла)
                # Но сначала попробуем найти файл сцены (обычно это .blend файл в корне)
                if source_info and source_info['source_type'] == 'scene_file':
                    # Ищем .blend файлы, которые могут быть файлами сцен
                    for entry in entries:
                        if entry.get("type") == "blob" and entry.get("name", "").endswith(".blend"):
                            entry_path = entry.get("name", "")
                            # Проверяем, не является ли это файлом в корне или похожим путем
                            entry_path_normalized = Path(entry_path).as_posix() if entry_path else None
                            # Если путь короткий (вероятно файл в корне) или содержит имя файла
                            if (len(Path(entry_path).parts) <= 2 or  # Файл в корне или одной подпапке
                                target_file_name in entry_path_normalized):
                                blob_hash = entry.get("hash")
                                if blob_hash:
                                    blob_hash_path = blob_hash[:2] + "/" + blob_hash[2:]
                                    blob_file = blobs_path / blob_hash_path
                                    
                                    if blob_file.exists():
                                        found_name = _find_object_in_blend_file(
                                            blob_file, 
                                            object_name, 
                                            object_type
                                        )
                                        if found_name:
                                            return (blob_hash, blob_file, found_name)
                
                # Если не нашли, перебираем все .blend файлы
                logger.debug(f"Searching in all {len([e for e in entries if e.get('name', '').endswith('.blend')])} .blend files")
                for entry in entries:
                    if entry.get("type") == "blob" and entry.get("name", "").endswith(".blend"):
                        blob_hash = entry.get("hash")
                        if blob_hash:
                            blob_hash_path = blob_hash[:2] + "/" + blob_hash[2:]
                            blob_file = blobs_path / blob_hash_path
                            
                            if blob_file.exists():
                                # Check if object exists in this blend file
                                found_name = _find_object_in_blend_file(
                                    blob_file, 
                                    object_name, 
                                    object_type
                                )
                                if found_name:
                                    logger.debug(f"Found object '{found_name}' in {entry.get('name')} (hash: {blob_hash[:8]})")
                                    return (blob_hash, blob_file, found_name)
            except Exception as e:
                logger.error(f"Error searching tree: {e}", exc_info=True)
    else:
        logger.debug("No tree_hash in commit")
    
    logger.warning(f"Object '{object_name}' (type: {object_type}) not found in commit {commit_hash[:8]}")
    return None


def _find_mesh_in_commit_by_object_name(repo_path: Path, commit_hash: str, object_name: str) -> Optional[Tuple[str, Path]]:
    """
    Find mesh in commit by object_name.
    
    Меши хранятся в tree как blob'ы (полные коммиты проекта).
    
    Args:
        repo_path: Repository root path
        commit_hash: Commit hash
        object_name: Object name to search for
        
    Returns:
        Tuple of (blob_hash, blend_path) or None if not found
    """
    import json
    import re
    
    # Read commit JSON from storage
    dfm_path = repo_path / ".DFM"
    commits_path = dfm_path / "objects" / "commits" / "sha256"
    
    # Convert hash to path (first 2 chars / rest)
    hash_path = commit_hash[:2] + "/" + commit_hash[2:]
    commit_file = commits_path / hash_path
    
    if not commit_file.exists():
        return None
    
    commit_json = None
    tree_hash = None
    
    try:
        with open(commit_file, 'r', encoding='utf-8') as f:
            commit_content = f.read()
        
        # Try to parse as JSON first
        try:
            commit_json = json.loads(commit_content)
            tree_hash = commit_json.get("tree_hash", "")
        except:
            # If not valid JSON, try regex parsing
            tree_hash_match = re.search(r'"tree_hash"\s*:\s*"([^"]+)"', commit_content)
            if tree_hash_match:
                tree_hash = tree_hash_match.group(1)
    except Exception as e:
        return None
    
    # Search in tree (for full project commits)
    # Меши могут быть сохранены как .blend файлы в tree
    if tree_hash:
        trees_path = dfm_path / "objects" / "trees" / "sha256"
        tree_hash_path = tree_hash[:2] + "/" + tree_hash[2:]
        tree_file = trees_path / tree_hash_path
        
        if tree_file.exists():
            try:
                with open(tree_file, 'r', encoding='utf-8') as f:
                    tree_content = f.read()
                
                # Parse tree JSON
                try:
                    tree_json = json.loads(tree_content)
                    entries = tree_json.get("entries", [])
                except:
                    # Try regex parsing
                    entries_match = re.search(r'"entries"\s*:\s*\[(.*?)\]', tree_content, re.DOTALL)
                    if entries_match:
                        entries_str = entries_match.group(1)
                        # Extract entries
                        entries = []
                        entry_matches = re.finditer(r'\{"hash":"([^"]+)","name":"([^"]+)","type":"([^"]+)"', entries_str)
                        for match in entry_matches:
                            entries.append({
                                "hash": match.group(1),
                                "name": match.group(2),
                                "type": match.group(3)
                            })
                    else:
                        entries = []
                
                # Search for .blend files in tree
                blobs_path = dfm_path / "objects" / "blobs" / "sha256"
                
                for entry in entries:
                    # Check if it's a .blend file
                    if entry.get("type") == "blob" and entry.get("name", "").endswith(".blend"):
                        # Check if filename matches object_name (exact or partial)
                        file_name = Path(entry.get("name", "")).stem
                        
                        # Try exact match first
                        if file_name == object_name or entry.get("name") == object_name:
                            # Load blob and check if it contains the mesh
                            blob_hash = entry.get("hash")
                            if blob_hash:
                                blob_hash_path = blob_hash[:2] + "/" + blob_hash[2:]
                                blob_file = blobs_path / blob_hash_path
                                
                                if blob_file.exists():
                                    # Try to import and check object name
                                    # For now, return the blob file as blend path
                                    # (We'll check the object name when importing)
                                    return (blob_hash, blob_file)
                        
            except Exception as e:
                pass
    
    # Method 2: Try to find by filename pattern (if object_name looks like a filename)
    # This is a fallback - try to match object_name with .blend filenames in tree
    if tree_hash:
        trees_path = dfm_path / "objects" / "trees"
        tree_hash_path = tree_hash[:2] + "/" + tree_hash[2:]
        tree_file = trees_path / tree_hash_path
        
        if tree_file.exists():
            try:
                with open(tree_file, 'r', encoding='utf-8') as f:
                    tree_content = f.read()
                
                # Try to find .blend files that might contain the mesh
                # Look for files where object_name matches or is part of filename
                blend_file_matches = re.findall(r'\{"hash":"([^"]+)","name":"([^"]+\.blend)","type":"blob"', tree_content)
                
                blobs_path = dfm_path / "objects" / "blobs" / "sha256"
                
                for blob_hash, file_name in blend_file_matches:
                    # Check if object_name matches filename (without extension)
                    file_stem = Path(file_name).stem
                    if object_name == file_stem or object_name in file_stem or file_stem in object_name:
                        blob_hash_path = blob_hash[:2] + "/" + blob_hash[2:]
                        blob_file = blobs_path / blob_hash_path
                        
                        if blob_file.exists():
                            # Try to verify by loading and checking objects inside
                            # For now, return the first match
                            return (blob_hash, blob_file)
            except:
                pass
    
    return None


def _extract_commit_to_tmp_review(
    repo_path: Path, 
    commit_hash: str, 
    cleanup_old: bool = True,
    current_commit: Optional[str] = None
) -> Tuple[bool, Path, Optional[str]]:
    """
    Extract commit to tmp_review directory.
    
    Args:
        repo_path: Repository root path
        commit_hash: Commit hash to extract
        cleanup_old: Whether to cleanup old tmp_review if it exists
        current_commit: Current commit hash (for comparison, only cleanup if different)
    
    Returns:
        Tuple of (success, tmp_review_path, error_message)
        If successful: (True, Path, None)
        If error: (False, Path, error_message)
    """
    cli = get_cli()
    tmp_review_path = repo_path / ".DFM" / "tmp_review"
    logger.debug(f"tmp_review path: {tmp_review_path}")
    
    # Очищаем старую папку если есть
    if cleanup_old and tmp_review_path.exists():
        # Only cleanup if it's a different commit
        if current_commit and current_commit == commit_hash:
            logger.debug("tmp_review already exists for this commit, skipping cleanup")
        else:
            logger.debug("Cleaning up old tmp_review directory")
            cleanup_commit = current_commit if current_commit else commit_hash
            cli.compare(repo_path, cleanup_commit, cleanup=True)
            # Wait for cleanup to complete
            wait_for_path(tmp_review_path, timeout=1.0, interval=0.1)
            # Check if directory was removed (it should be)
            if tmp_review_path.exists():
                logger.debug("tmp_review still exists after cleanup, will be overwritten")
    
    success, error_msg = cli.compare(repo_path, commit_hash)
    if not success:
        logger.error(f"forester compare failed: {error_msg}")
        return False, tmp_review_path, error_msg
    
    logger.debug(f"forester compare completed, checking tmp_review...")
    
    # Wait for directory to be created
    if not wait_for_path(tmp_review_path, timeout=5.0, interval=0.1):
        error_msg = f"tmp_review directory was not created after 5s"
        logger.error(f"{error_msg}: {tmp_review_path}")
        return False, tmp_review_path, error_msg
    
    logger.debug(f"tmp_review directory exists: {tmp_review_path}")
    try:
        contents = list(tmp_review_path.iterdir())
        logger.debug(f"Contents: {[str(c.name) for c in contents]}")
    except (OSError, PermissionError) as e:
        logger.debug(f"Error listing contents: {e}")
    
    return True, tmp_review_path, None


def _find_scene_file_in_tmp_review(tmp_review_path: Path, blend_file_name: str) -> Optional[Path]:
    """
    Find scene file in tmp_review directory.
    
    Args:
        tmp_review_path: Path to tmp_review directory
        blend_file_name: Name of the blend file to find (e.g., "2B.blend")
    
    Returns:
        Path to scene file if found, None otherwise
    """
    scene_file_path = tmp_review_path / blend_file_name
    
    if scene_file_path.exists():
        logger.debug(f"Found scene file at: {scene_file_path}")
        return scene_file_path
    
    # Try recursive search
    found_files = list(tmp_review_path.rglob(blend_file_name))
    if found_files:
        scene_file_path = found_files[0]
        logger.debug(f"Found scene file recursively at: {scene_file_path}")
        return scene_file_path
    
    logger.debug(f"Scene file '{blend_file_name}' not found in tmp_review")
    return None


def _find_object_in_tmp_review_blend_files(
    tmp_review_path: Path,
    scene_file_path: Path,
    object_name: str,
    object_type: Optional[str] = None
) -> Optional[Tuple[Path, str]]:
    """
    Find object in .blend files within tmp_review directory.
    
    Args:
        tmp_review_path: Path to tmp_review directory
        scene_file_path: Path to scene file (already checked)
        object_name: Name of object to find
        object_type: Optional object type (MESH, LIGHT, etc.)
    
    Returns:
        Tuple of (blend_file_path, object_name_in_file) if found, None otherwise
    """
    from ..operators.mesh_io import _find_object_in_blend_file
    
    # First check scene file
    logger.debug(f"Checking scene file {scene_file_path} for object '{object_name}' (type: {object_type})")
    found_name = _find_object_in_blend_file(scene_file_path, object_name, object_type)
    if found_name:
        logger.debug(f"✓ Found object '{found_name}' in scene file")
        return scene_file_path, found_name
    
    logger.debug(f"Object not found in {scene_file_path.name}, searching all .blend files in tmp_review...")
    
    # Find all .blend files (excluding backups)
    all_blend_files = []
    all_blend_files.extend(tmp_review_path.rglob("*.blend"))
    
    # Also check manually (in case rglob misses some)
    try:
        for item in tmp_review_path.iterdir():
            if item.is_file() and item.name.endswith('.blend') and not item.name.endswith(('.blend1', '.blend2', '.blend3', '.blend4', '.blend5')):
                if item.name.count('.blend') == 1:  # Only one occurrence of .blend
                    if item not in all_blend_files:
                        all_blend_files.append(item)
                        logger.debug(f"Found .blend file via iterdir: {item.name}")
    except (OSError, PermissionError) as e:
        logger.debug(f"Error listing files: {e}")
    
    # Filter out backups
    all_blend_files = [bf for bf in all_blend_files if not bf.name.endswith(('.blend1', '.blend2', '.blend3', '.blend4', '.blend5'))]
    
    logger.debug(f"Found {len(all_blend_files)} .blend files in tmp_review (excluding backups)")
    for bf in all_blend_files:
        logger.debug(f"  - {bf.name} (exists: {bf.exists()}, is_file: {bf.is_file()})")
    
    # Check each blend file
    for blend_file in all_blend_files:
        if blend_file == scene_file_path:
            logger.debug(f"Skipping {blend_file.name} (already checked)")
            continue
        
        if not blend_file.exists():
            logger.debug(f"Skipping {blend_file.name} (does not exist)")
            continue
        
        logger.debug(f"Checking {blend_file.name} for object '{object_name}'...")
        found_name = _find_object_in_blend_file(blend_file, object_name, object_type)
        if found_name:
            logger.debug(f"✓ Found object '{found_name}' in {blend_file.name}")
            return blend_file, found_name
        else:
            logger.debug(f"  Object '{object_name}' not found in {blend_file.name}")
    
    logger.debug(f"Object '{object_name}' (type: {object_type}) not found in any .blend file")
    return None


class DF_OT_replace_mesh(Operator):
    """Replace selected object with object from commit."""
    bl_idname = "df.replace_mesh"
    bl_label = "Replace Mesh"
    bl_description = "Replace selected object with object from commit by object name"
    bl_options = {'REGISTER', 'UNDO'}

    commit_hash: bpy.props.StringProperty(
        name="Commit Hash",
        description="Hash of the commit",
        default="",
    )

    def execute(self, context):
        if not self.commit_hash:
            self.report({'ERROR'}, "Commit hash required")
            return {'CANCELLED'}
        
        # Normalize commit hash to standard format (8 chars)
        from ..utils.helpers import normalize_commit_hash
        commit_hash = normalize_commit_hash(self.commit_hash)
        if not commit_hash:
            self.report({'ERROR'}, f"Invalid commit hash: {self.commit_hash[:16] if self.commit_hash else 'empty'}...")
            return {'CANCELLED'}
        
        active_obj = context.active_object
        if not active_obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        logger.debug(f"Replace called with commit_hash: {commit_hash}, object: {active_obj.name} ({active_obj.type})")
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Get current Blender file name
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Please save the Blender file first")
            return {'CANCELLED'}
        
        current_blend_file = Path(bpy.data.filepath)
        blend_file_name = current_blend_file.name  # e.g., "2B.blend"
        
        logger.debug(f"Current Blender file: {blend_file_name}")
        logger.debug(f"Full path: {current_blend_file}")
        
        # Find object in commit by name
        object_name = active_obj.name
        object_type = active_obj.type
        
        # Store collections early (before any operations that might invalidate the object)
        obj_collections_backup = []
        try:
            obj_collections_backup = list(active_obj.users_collection)
            logger.debug(f"Object '{object_name}' is in {len(obj_collections_backup)} collection(s)")
        except (ReferenceError, AttributeError) as e:
            logger.warning(f"Could not store object collections early: {e}")
        
        # Extract commit to tmp_review
        self.report({'INFO'}, f"Extracting commit {commit_hash} to tmp_review...")
        
        success, tmp_review_path, error_msg = _extract_commit_to_tmp_review(repo_path, commit_hash)
        if not success:
            self.report({'ERROR'}, f"Failed to extract commit: {error_msg}")
            return {'CANCELLED'}
        
        # Find scene file
        scene_file_path = _find_scene_file_in_tmp_review(tmp_review_path, blend_file_name)
        if not scene_file_path:
            self.report({'ERROR'}, 
                f"Scene file '{blend_file_name}' not found in commit {self.commit_hash[:8]}")
            return {'CANCELLED'}
        
        logger.debug(f"Reading scene file from: {scene_file_path}")
        
        # Find object in blend files
        result = _find_object_in_tmp_review_blend_files(
            tmp_review_path, scene_file_path, object_name, object_type
        )
        if not result:
            self.report({'ERROR'}, 
                f"Object '{object_name}' (type: {object_type}) not found in any .blend file from commit {self.commit_hash[:8]}")
            return {'CANCELLED'}
        
        blend_path, obj_name_in_file = result
        logger.debug(f"Found object '{obj_name_in_file}' in {blend_path.name}")
        
        # Verify object still exists before import
        if object_name not in bpy.data.objects:
            self.report({'ERROR'}, 
                f"Original object '{object_name}' was removed before import")
            return {'CANCELLED'}
        logger.debug(f"Object '{object_name}' exists before import")
        
        # Import object from blend file
        from ..operators.mesh_io import import_object_from_blend, import_mesh_from_blend
        
        try:
            # Use background import for commit files (safer, avoids StructRNA errors)
            logger.debug(f"Starting background import of object '{obj_name_in_file or object_name}'")
            imported_obj = import_object_from_blend(
                blend_path, 
                obj_name_in_file or object_name, 
                object_type,
                context,
                use_background=True  # Use background process for commit files
            )
            
            if not imported_obj:
                # Fallback: try old mesh-specific import
                if object_type == 'MESH':
                    logger.debug(f"Background import failed, trying mesh-specific import")
                    imported_obj = import_mesh_from_blend(blend_path, obj_name_in_file or object_name, context)
                
                if not imported_obj:
                    self.report({'ERROR'}, 
                        f"Failed to import {object_type} object '{object_name}' from commit")
                    return {'CANCELLED'}
            
            logger.debug(f"Successfully imported object '{imported_obj.name}' (type: {imported_obj.type})")
            
            # Simple replacement: delete original object and rename imported one
            try:
                # Verify original object exists
                if object_name not in bpy.data.objects:
                    self.report({'ERROR'}, 
                        f"Original object '{object_name}' was removed or is no longer available")
                    try:
                        bpy.data.objects.remove(imported_obj)
                    except:
                        pass
                    return {'CANCELLED'}
                
                # Get original object and store its collections
                original_obj = bpy.data.objects[object_name]
                if obj_collections_backup:
                    obj_collections = obj_collections_backup
                else:
                    obj_collections = list(original_obj.users_collection)
                
                logger.debug(f"Original object '{object_name}' was in {len(obj_collections)} collection(s)")
                
                # Verify types match
                if original_obj.type != object_type:
                    self.report({'ERROR'}, 
                        f"Object type mismatch: original is {original_obj.type}, imported is {object_type}")
                    try:
                        bpy.data.objects.remove(imported_obj)
                    except:
                        pass
                    return {'CANCELLED'}
                
                # Store imported object name (it might have been auto-renamed by Blender)
                imported_obj_original_name = imported_obj.name
                logger.debug(f"Imported object name: '{imported_obj_original_name}', target name: '{object_name}'")
                
                # Temporarily rename original object to avoid name conflict
                # This ensures we can safely rename imported object
                temp_name = f"{object_name}_temp_delete_{id(original_obj)}"
                original_obj.name = temp_name
                logger.debug(f"Temporarily renamed original object to '{temp_name}'")
                
                # Now rename imported object to target name (should work now)
                imported_obj.name = object_name
                logger.debug(f"Renamed imported object from '{imported_obj_original_name}' to '{object_name}'")
                
                # Verify imported object has correct name before deleting original
                if imported_obj.name != object_name:
                    logger.error(f"Imported object name mismatch: expected '{object_name}', got '{imported_obj.name}'")
                    raise RuntimeError(f"Cannot rename imported object to '{object_name}'")
                
                # Now delete original object (using temp name)
                if temp_name in bpy.data.objects:
                    bpy.data.objects.remove(bpy.data.objects[temp_name])
                    logger.debug(f"Deleted original object '{temp_name}'")
                else:
                    logger.warning(f"Original object '{temp_name}' not found for deletion (might have been deleted already)")
                
                # Verify imported object still exists after deleting original
                if object_name not in bpy.data.objects:
                    raise RuntimeError(f"Imported object '{object_name}' was removed when deleting original object")
                
                # Get fresh reference to imported object
                imported_obj = bpy.data.objects[object_name]
                
                # Link imported object to all collections where original was
                for coll in obj_collections:
                    if imported_obj.name not in coll.objects:
                        coll.objects.link(imported_obj)
                        logger.debug(f"Linked object '{imported_obj.name}' to collection '{coll.name}'")
                
                # Ensure object is in context collection
                if imported_obj.name not in context.collection.objects:
                    context.collection.objects.link(imported_obj)
                
                # Make it active and selected
                imported_obj.select_set(True)
                context.view_layer.objects.active = imported_obj
                logger.debug(f"Replacement complete: object '{imported_obj.name}' is active and selected")
                
            except Exception as e:
                error_msg = f"Failed to replace object: {str(e)}"
                logger.error(error_msg, exc_info=True)
                # Try to clean up imported object
                try:
                    if imported_obj and imported_obj.name in bpy.data.objects:
                        bpy.data.objects.remove(imported_obj)
                except:
                    pass
                self.report({'ERROR'}, error_msg)
                return {'CANCELLED'}
            
            self.report({'INFO'}, f"Replaced {object_type.lower()} '{object_name}' with version from commit {self.commit_hash[:16]}...")
            
            # Очищаем tmp_review после успешной замены (объект успешно загружен)
            cli = get_cli()
            success, error_msg = cli.compare(repo_path, self.commit_hash, cleanup=True)
            if not success:
                logger.warning(f"Could not clean up tmp_review after Replace: {error_msg}")
            else:
                logger.debug("✓ Cleaned up tmp_review directory after successful Replace")
            
            return {'FINISHED'}
        except Exception as e:
            # НЕ очищаем tmp_review при ошибке - пусть остается для отладки
            logger.error(f"Failed to replace object: {str(e)}", exc_info=True)
            self.report({'ERROR'}, f"Failed to replace object: {str(e)}")
            return {'CANCELLED'}


class DF_OT_compare_object(Operator):
    """Compare selected object with object from commit."""
    bl_idname = "df.compare_object"
    bl_label = "Compare"
    bl_description = "Load object from commit for comparison"
    bl_options = {'REGISTER', 'UNDO'}

    commit_hash: bpy.props.StringProperty(
        name="Commit Hash",
        description="Hash of the commit",
        default="",
    )
    
    axis: bpy.props.StringProperty(
        name="Axis",
        description="Axis for offset",
        default="X",
    )
    
    offset: bpy.props.FloatProperty(
        name="Offset",
        description="Offset distance",
        default=2.0,
    )

    def execute(self, context):
        if not self.commit_hash:
            self.report({'ERROR'}, "Commit hash required")
            return {'CANCELLED'}
        
        # Normalize commit hash to standard format (8 chars)
        from ..utils.helpers import normalize_commit_hash
        commit_hash = normalize_commit_hash(self.commit_hash)
        if not commit_hash:
            self.report({'ERROR'}, f"Invalid commit hash: {self.commit_hash[:16] if self.commit_hash else 'empty'}...")
            return {'CANCELLED'}
        
        active_obj = context.active_object
        if not active_obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        # Добавить отладку
        from ..utils.logging_config import get_logger
        logger = get_logger(__name__)
        logger.debug(f"Compare called with commit_hash: {commit_hash}, object: {active_obj.name} ({active_obj.type})")
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Get current Blender file name
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Please save the Blender file first")
            return {'CANCELLED'}
        
        current_blend_file = Path(bpy.data.filepath)
        blend_file_name = current_blend_file.name  # e.g., "2B.blend"
        
        logger.debug(f"Current Blender file: {blend_file_name}")
        logger.debug(f"Full path: {current_blend_file}")
        
        # Check if comparison is already active
        scene = context.scene
        is_active = (
            getattr(scene, 'df_object_comparison_active', False) and
            getattr(scene, 'df_object_comparison_commit_hash', '') == commit_hash
        )
        
        # If active, remove comparison object and cleanup (как на Project tab)
        if is_active:
            logger.debug("Deactivating comparison - removing object and cleaning up tmp_review")
            
            comparison_obj_name = getattr(scene, 'df_object_comparison_object_name', None)
            if comparison_obj_name and comparison_obj_name in bpy.data.objects:
                comparison_obj = bpy.data.objects[comparison_obj_name]
                logger.debug(f"Removing comparison object: {comparison_obj_name} (type: {comparison_obj.type})")
                
                # Remove object and all its data completely
                obj_type = comparison_obj.type
                obj_data = comparison_obj.data
                
                # Remove from all collections
                for collection in bpy.data.collections:
                    if comparison_obj in collection.objects.values():
                        collection.objects.unlink(comparison_obj)
                
                # Remove object
                bpy.data.objects.remove(comparison_obj)
                
                # Remove data if no other users
                if obj_data and obj_data.users == 0:
                    try:
                        data_name = obj_data.name
                        if obj_type == 'MESH' and data_name in bpy.data.meshes:
                            bpy.data.meshes.remove(bpy.data.meshes[data_name])
                            logger.debug("Removed mesh data")
                        elif obj_type == 'LIGHT' and data_name in bpy.data.lights:
                            bpy.data.lights.remove(bpy.data.lights[data_name])
                            logger.debug("Removed light data")
                        elif obj_type == 'CAMERA' and data_name in bpy.data.cameras:
                            bpy.data.cameras.remove(bpy.data.cameras[data_name])
                            logger.debug("Removed camera data")
                        elif obj_type == 'ARMATURE' and data_name in bpy.data.armatures:
                            bpy.data.armatures.remove(bpy.data.armatures[data_name])
                            logger.debug("Removed armature data")
                        elif obj_type == 'FONT' and data_name in bpy.data.curves:
                            bpy.data.curves.remove(bpy.data.curves[data_name])
                            logger.debug("Removed font/curve data")
                        # Add other types as needed
                    except (KeyError, AttributeError) as e:
                        logger.debug(f"Could not remove data block: {e}")
            
            # Очищаем tmp_review ПЕРЕД деактивацией (как на Project tab)
            cli = get_cli()
            success, error_msg = cli.compare(repo_path, commit_hash, cleanup=True)
            if not success:
                logger.warning(f"Could not clean up tmp_review: {error_msg}")
            else:
                logger.debug("✓ Cleaned up tmp_review directory on Compare deactivation")
            
            # Deactivate comparison state
            scene.df_object_comparison_active = False
            scene.df_object_comparison_object_name = ""
            scene.df_object_comparison_commit_hash = ""
            if hasattr(scene, 'df_object_comparison_original_name'):
                scene.df_object_comparison_original_name = ""
            
            self.report({'INFO'}, "Comparison removed")
            return {'FINISHED'}
        
        # Prepare object import: save name, type, position, and calculate offset
        object_name = active_obj.name
        object_type = active_obj.type
        active_obj_data_name_before_import = active_obj.data.name if active_obj.data else None
        
        # Get original object location for offset calculation
        try:
            base_location = list(active_obj.location.copy())
            logger.debug(f"Base location: {base_location}, axis: {self.axis}, offset: {self.offset}")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to get active object location: {str(e)}")
            logger.error(f"Failed to get location: {e}", exc_info=True)
            return {'CANCELLED'}
        
        # Calculate offset vector based on axis
        offset_vector = [0.0, 0.0, 0.0]
        if self.axis == 'X':
            offset_vector[0] = float(self.offset)
        elif self.axis == 'Y':
            offset_vector[1] = float(self.offset)
        elif self.axis == 'Z':
            offset_vector[2] = float(self.offset)
        
        # Extract commit to tmp_review
        self.report({'INFO'}, f"Extracting commit {commit_hash} to tmp_review...")
        
        current_commit = getattr(scene, 'df_object_comparison_commit_hash', '')
        success, tmp_review_path, error_msg = _extract_commit_to_tmp_review(
            repo_path, commit_hash, cleanup_old=True, current_commit=current_commit
        )
        if not success:
            self.report({'ERROR'}, f"Failed to extract commit: {error_msg}")
            return {'CANCELLED'}
        
        # Find scene file
        scene_file_path = _find_scene_file_in_tmp_review(tmp_review_path, blend_file_name)
        if not scene_file_path:
            self.report({'ERROR'}, 
                f"Scene file '{blend_file_name}' not found in commit {commit_hash}")
            return {'CANCELLED'}
        
        logger.debug(f"Reading scene file from: {scene_file_path}")
        
        # Find object in blend files
        result = _find_object_in_tmp_review_blend_files(
            tmp_review_path, scene_file_path, object_name, object_type
        )
        if not result:
            self.report({'ERROR'}, 
                f"Object '{object_name}' (type: {object_type}) not found in any .blend file from commit {commit_hash}")
            return {'CANCELLED'}
        
        blend_path, obj_name_in_file = result
        logger.debug(f"Found object '{obj_name_in_file}' in {blend_path.name}")
        
        # Create Compare collection if it doesn't exist
        try:
            compare_coll = bpy.data.collections.get("Compare")
            if compare_coll is None:
                compare_coll = bpy.data.collections.new("Compare")
                context.scene.collection.children.link(compare_coll)
                logger.debug("Created 'Compare' collection for object comparison")
            elif compare_coll.name not in context.scene.collection.children:
                context.scene.collection.children.link(compare_coll)
                logger.debug("Linked existing 'Compare' collection to scene")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to prepare 'Compare' collection: {str(e)}")
            logger.error(f"Failed to prepare 'Compare' collection: {e}", exc_info=True)
            return {'CANCELLED'}
        
        # Link object from blend file (creates a reference, not a copy)
        # IMPORTANT: This is COMPARE operation - we ADD a new linked object, NOT replace active object
        from ..operators.mesh_io import link_object_from_blend
        
        try:
            # Link object from commit file (creates a reference, not a copy)
            imported_obj = link_object_from_blend(
                blend_path, 
                obj_name_in_file or object_name, 
                object_type,
                context
            )
            
            if not imported_obj:
                self.report({'ERROR'}, 
                    f"Failed to link {object_type} object '{object_name}' from commit")
                return {'CANCELLED'}
            
            # Get linked object name
            try:
                imported_obj_name = imported_obj.name
            except (AttributeError, ReferenceError) as e:
                self.report({'ERROR'}, f"Linked object is invalid: {str(e)}")
                logger.error(f"Failed to get linked object name: {e}", exc_info=True)
                return {'CANCELLED'}
            
            # Verify linked object exists
            if not imported_obj_name or imported_obj_name not in bpy.data.objects:
                self.report({'ERROR'}, "Linked object was removed before it could be used")
                logger.error(f"Linked object '{imported_obj_name}' is not in bpy.data.objects")
                return {'CANCELLED'}

            # Rename linked object to "compare" immediately to avoid name conflicts
            comparison_name = "compare"
            try:
                imported_obj = bpy.data.objects[imported_obj_name]
                imported_obj.name = comparison_name
                logger.debug(f"Renamed linked object from '{imported_obj_name}' to '{comparison_name}'")
            except (KeyError, AttributeError, ReferenceError) as e:
                self.report({'ERROR'}, f"Failed to rename linked object: {str(e)}")
                logger.error(f"Failed to rename object: {e}", exc_info=True)
                # Try to clean up
                try:
                    if imported_obj_name in bpy.data.objects:
                        bpy.data.objects.remove(bpy.data.objects[imported_obj_name])
                except:
                    pass
                return {'CANCELLED'}
            
            # Get fresh reference to renamed object
            if comparison_name not in bpy.data.objects:
                self.report({'ERROR'}, f"Comparison object '{comparison_name}' not found after renaming")
                logger.error(f"Object '{comparison_name}' not in bpy.data.objects")
                return {'CANCELLED'}
            
            imported_obj = bpy.data.objects[comparison_name]
            
            # Link object to Compare collection
            try:
                if imported_obj.name not in [obj.name for obj in compare_coll.objects]:
                    compare_coll.objects.link(imported_obj)
                    logger.debug(f"Linked comparison object '{comparison_name}' to 'Compare' collection")
            except Exception as e:
                self.report({'ERROR'}, f"Failed to link comparison object to 'Compare' collection: {str(e)}")
                logger.error(f"Failed to link object to 'Compare' collection: {e}", exc_info=True)
                # Clean up
                try:
                    bpy.data.objects.remove(imported_obj)
                except:
                    pass
                return {'CANCELLED'}
            
            # Verify active object still exists
            if object_name not in bpy.data.objects:
                self.report({'ERROR'}, "Selected object was removed during link operation")
                logger.error(f"Active object '{object_name}' is not in bpy.data.objects")
                # Clean up
                try:
                    bpy.data.objects.remove(imported_obj)
                except:
                    pass
                return {'CANCELLED'}
            
            # Position comparison object with offset
            try:
                new_location = (
                    base_location[0] + offset_vector[0],
                    base_location[1] + offset_vector[1],
                    base_location[2] + offset_vector[2]
                )
                imported_obj.location = new_location
                logger.debug(f"Set comparison object location: {imported_obj.location} (base: {base_location}, offset: {offset_vector})")
            except (KeyError, AttributeError, ReferenceError) as e:
                self.report({'ERROR'}, f"Failed to set comparison object location: {str(e)}")
                logger.error(f"Failed to set location: {e}", exc_info=True)
                # Clean up
                try:
                    bpy.data.objects.remove(imported_obj)
                except:
                    pass
                return {'CANCELLED'}
            
            # Restore focus to original object
            try:
                active_obj = bpy.data.objects[object_name]
                
                # Deselect all objects first
                bpy.ops.object.select_all(action='DESELECT')
                
                # Select and activate original object
                active_obj.select_set(True)
                context.view_layer.objects.active = active_obj
                
                # Make sure comparison object is NOT selected
                imported_obj.select_set(False)
                
                logger.debug(f"Restored focus to original object: {active_obj.name}")
            except (KeyError, AttributeError, ReferenceError) as e:
                self.report({'ERROR'}, f"Failed to restore focus: {str(e)}")
                logger.error(f"Failed to restore focus: {e}", exc_info=True)
                # Clean up
                try:
                    bpy.data.objects.remove(imported_obj)
                except:
                    pass
                return {'CANCELLED'}
            
            # Store comparison state
            scene.df_object_comparison_active = True
            scene.df_object_comparison_object_name = comparison_name
            scene.df_object_comparison_commit_hash = commit_hash
            scene.df_object_comparison_original_name = object_name
            
            logger.debug(f"Comparison state set: active={scene.df_object_comparison_active}, "
                        f"commit={commit_hash}, comparison_obj={comparison_name}, "
                        f"original_obj={object_name}")
            
            logger.debug(f"Comparison activated. tmp_review will remain until Compare is deactivated.")
            logger.debug(f"tmp_review path: {tmp_review_path}")
            
            self.report({'INFO'}, f"Loaded {object_type.lower()} for comparison from commit {commit_hash}")
            return {'FINISHED'}
        except (AttributeError, ReferenceError, KeyError) as e:
            # Handle StructRNA errors more gracefully
            error_msg = str(e)
            if "StructRNA" in error_msg or "has been removed" in error_msg:
                self.report({'ERROR'}, f"Object was removed during import. Please try again.")
                logger.error(f"StructRNA error during import: {e}", exc_info=True)
            else:
                self.report({'ERROR'}, f"Failed to load object for comparison: {error_msg}")
                logger.error(f"Error during import: {e}", exc_info=True)
            return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load object for comparison: {str(e)}")
            logger.error(f"Unexpected error during import: {e}", exc_info=True)
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(DF_OT_refresh_history)
    bpy.utils.register_class(DF_OT_show_commit)
    bpy.utils.register_class(DF_OT_checkout_commit)
    bpy.utils.register_class(DF_OT_compare_project)
    bpy.utils.register_class(DF_OT_delete_commit)
    bpy.utils.register_class(DF_OT_replace_mesh)
    bpy.utils.register_class(DF_OT_compare_object)


def unregister():
    bpy.utils.unregister_class(DF_OT_compare_object)
    bpy.utils.unregister_class(DF_OT_replace_mesh)
    bpy.utils.unregister_class(DF_OT_delete_commit)
    bpy.utils.unregister_class(DF_OT_compare_project)
    bpy.utils.unregister_class(DF_OT_checkout_commit)
    bpy.utils.unregister_class(DF_OT_show_commit)
    bpy.utils.unregister_class(DF_OT_refresh_history)
