"""
Operators for commit operations.
"""

import bpy
from bpy.types import Operator
from pathlib import Path
from ..utils.forester_cli import get_cli, ForesterCLIError
from ..utils.helpers import get_repository_path, get_addon_preferences


class DF_OT_create_project_commit(Operator):
    """Create a full project commit."""
    bl_idname = "df.create_project_commit"
    bl_label = "Create Project Commit"
    bl_description = "Create a commit for the entire project"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.df_commit_props
        
        if not props.message or not props.message.strip():
            self.report({'ERROR'}, "Commit message is required")
            return {'CANCELLED'}
        
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Get author from preferences
        prefs = get_addon_preferences(context)
        author = prefs.default_author
        
        cli = get_cli()
        
        # Automatically stage all files before committing
        # This ensures files are staged even if user hasn't explicitly run 'forester add'
        success, error_msg = cli.add(repo_path, files=None)  # None means add all files
        if not success:
            self.report({'ERROR'}, f"Failed to stage files: {error_msg}")
            return {'CANCELLED'}
        
        success, commit_hash, error_msg = cli.commit(
            repo_path,
            message=props.message.strip(),
            author=author,
            tag=props.commit_tag if props.commit_tag else None,
            no_verify=True  # Skip hooks by default (hooks may not be executable)
        )
        
        if success:
            self.report({'INFO'}, f"Created commit: {commit_hash[:16] + '...' if commit_hash else 'unknown'}")
            
            # IMPORTANT: Clear message and tag fields after successful commit
            # This ensures the UI fields are reset for the next commit
            props.message = ""
            props.commit_tag = ""
            
            # Force UI update to reflect cleared fields
            # This ensures the text fields in the UI are visually cleared
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            
            # IMPORTANT: Refresh branch list to update commit counts
            # This ensures the commit count in branch list is updated after creating a commit
            import logging
            logger = logging.getLogger(__name__)
            try:
                bpy.ops.df.refresh_branches()
            except (RuntimeError, AttributeError, KeyError) as e:
                # If refresh_branches fails, at least try to refresh history
                logger.debug(f"Failed to refresh branches: {e}")
                try:
                    bpy.ops.df.refresh_history()
                except (RuntimeError, AttributeError, KeyError) as e2:
                    logger.debug(f"Failed to refresh history: {e2}")
                except Exception as e2:
                    logger.warning(f"Unexpected error refreshing history: {e2}")
            except Exception as e:
                logger.warning(f"Unexpected error refreshing branches: {e}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to create commit: {error_msg}")
            return {'CANCELLED'}


class DF_OT_select_assets_directory(Operator):
    """Select assets directory using file browser."""
    bl_idname = "df.select_assets_directory"
    bl_label = "Select Assets Directory"
    bl_description = "Select assets directory using file browser"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Filepath property for directory selection
    filepath: bpy.props.StringProperty(
        name="Directory",
        description="Full path to assets directory",
        subtype='DIR_PATH',
        default="",
    )
    
    def invoke(self, context, event):
        """Open file browser for directory selection."""
        # Get repository path as default directory
        repo_path, error_msg = get_repository_path()
        if repo_path:
            # Try to get current assets_dir from window_manager
            if 'df_current_assets_dir' in context.window_manager:
                current_dir = context.window_manager['df_current_assets_dir']
                if current_dir:
                    full_path = repo_path / current_dir
                    if full_path.exists():
                        self.filepath = str(full_path.resolve())
                        context.window_manager.fileselect_add(self)
                        return {'RUNNING_MODAL'}
            
            # Default to repo_path/assets if exists, else repo_path
            default_dir = repo_path / "assets"
            if default_dir.exists():
                self.filepath = str(default_dir.resolve())
            else:
                self.filepath = str(repo_path.resolve())
        else:
            # Fallback to home directory
            self.filepath = str(Path.home())
        
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        """Set selected directory to save_asset operator."""
        if not self.filepath:
            return {'CANCELLED'}
        
        # Get repository path to make path relative
        repo_path, error_msg = get_repository_path()
        if repo_path:
            try:
                dir_path = Path(self.filepath)
                repo_path_resolved = repo_path.resolve()
                dir_path_resolved = dir_path.resolve()
                
                # Try to make path relative to repo
                try:
                    relative_path = dir_path_resolved.relative_to(repo_path_resolved)
                    # Store relative path as string (use forward slashes)
                    assets_dir_name = relative_path.as_posix()
                except ValueError:
                    # Not relative to repo, use directory name only
                    assets_dir_name = dir_path.name
                
                # Store in window_manager for save_asset operator to pick up
                context.window_manager['df_selected_assets_dir'] = assets_dir_name
            except Exception as e:
                self.report({'WARNING'}, f"Could not process directory: {e}")
        
        return {'FINISHED'}


class DF_OT_save_asset(Operator):
    """Save selected object as separate .blend asset file."""
    bl_idname = "df.save_asset"
    bl_label = "Save as Asset"
    bl_description = "Save selected object as a separate .blend file in assets directory"
    bl_options = {'REGISTER', 'UNDO'}
    
    # Property for asset name
    asset_name: bpy.props.StringProperty(
        name="Asset Name",
        description="Name for the asset file (without .blend extension)",
        default="",
    )
    
    # Property for asset category (subdirectory)
    asset_category: bpy.props.StringProperty(
        name="Category",
        description="Asset category/subdirectory (e.g., 'props', 'characters', 'lights', 'cameras')",
        default="objects",
    )
    
    # Property for assets directory name (can be relative path from repo root)
    assets_dir: bpy.props.StringProperty(
        name="Assets Directory",
        description="Name of the assets directory (relative to repository root)",
        default="assets",
    )

    def invoke(self, context, event):
        """Show dialog to set asset name and category."""
        active_obj = context.active_object
        
        if not active_obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        # Store current assets_dir in window_manager for select operator
        context.window_manager['df_current_assets_dir'] = self.assets_dir
        
        # Check if directory was selected from file browser (before showing dialog)
        if 'df_selected_assets_dir' in context.window_manager:
            self.assets_dir = context.window_manager['df_selected_assets_dir']
            del context.window_manager['df_selected_assets_dir']
        
        # Set default asset name from object name
        if not self.asset_name:
            self.asset_name = active_obj.name
        
        # Set default category based on object type
        if not self.asset_category or self.asset_category == "objects":
            obj_type = active_obj.type.lower()
            # Map object types to common categories
            category_map = {
                'mesh': 'props',
                'light': 'lights',
                'camera': 'cameras',
                'armature': 'rigs',
                'curve': 'curves',
                'surface': 'surfaces',
                'meta': 'metaballs',
                'font': 'text',
                'lattice': 'lattices',
                'gpencil': 'grease_pencil',
                'volume': 'volumes',
            }
            self.asset_category = category_map.get(obj_type, 'objects')
        
        # Show dialog
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        """Draw dialog UI."""
        layout = self.layout
        active_obj = context.active_object
        if active_obj:
            obj_type_label = active_obj.type.lower().replace('_', ' ').title()
            layout.label(text=f"Object type: {obj_type_label}", icon='OBJECT_DATA')
            layout.separator()
        
        # Assets Directory row with browse button
        row = layout.row(align=True)
        row.prop(self, "assets_dir", text="Assets Directory")
        row.operator("df.select_assets_directory", text="", icon='FILEBROWSER')
        
        # Check if directory was selected from file browser (during dialog redraw)
        if 'df_selected_assets_dir' in context.window_manager:
            self.assets_dir = context.window_manager['df_selected_assets_dir']
            del context.window_manager['df_selected_assets_dir']
        
        layout.prop(self, "asset_category")
        layout.prop(self, "asset_name")

    def execute(self, context):
        """Save selected object as asset."""
        active_obj = context.active_object
        
        if not active_obj:
            self.report({'ERROR'}, "Please select an object")
            return {'CANCELLED'}
        
        # Get repository path
        repo_path, error_msg = get_repository_path()
        if not repo_path:
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}
        
        # Validate asset name
        if not self.asset_name or not self.asset_name.strip():
            self.report({'ERROR'}, "Asset name is required")
            return {'CANCELLED'}
        
        # Sanitize asset name (remove invalid characters)
        asset_name = self.asset_name.strip()
        # Replace invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            asset_name = asset_name.replace(char, '_')
        
        # Build asset directory path
        assets_dir_name = self.assets_dir.strip() if self.assets_dir.strip() else "assets"
        
        # Handle relative paths - if path contains separators, it's already a path
        # Otherwise treat it as a directory name under repo root
        assets_dir_path = Path(assets_dir_name)
        if assets_dir_path.is_absolute():
            # Absolute path provided - check if it's within repo
            repo_path_resolved = repo_path.resolve()
            assets_dir_resolved = assets_dir_path.resolve()
            try:
                # Try to make it relative to repo
                relative_path = assets_dir_resolved.relative_to(repo_path_resolved)
                assets_base = repo_path / relative_path
            except ValueError:
                # Not within repo, use as-is but warn
                assets_base = assets_dir_path
                self.report({'WARNING'}, f"Using absolute path outside repository: {assets_base}")
        else:
            # Relative path - treat as subdirectory of repo
            assets_base = repo_path / assets_dir_name
        
        asset_category = self.asset_category.strip() if self.asset_category.strip() else "objects"
        asset_dir = assets_base / asset_category
        
        # Create directory if it doesn't exist
        try:
            asset_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create asset directory: {e}")
            return {'CANCELLED'}
        
        # Build output file path
        output_path = asset_dir / f"{asset_name}.blend"
        
        # Check if file already exists
        if output_path.exists():
            self.report({'WARNING'}, f"File {output_path.name} already exists. It will be overwritten.")
        
        # Save object to .blend file
        try:
            from ..operators.mesh_io import _save_object_to_blend
            _save_object_to_blend(active_obj, output_path)
            
            # Report success
            relative_path = output_path.relative_to(repo_path)
            obj_type = active_obj.type.lower().replace('_', ' ').title()
            self.report({'INFO'}, f"{obj_type} asset saved: {relative_path}")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to save asset: {e}")
            return {'CANCELLED'}


class DF_OT_clear_tag_filter(Operator):
    """Clear tag search filter in history panel."""
    bl_idname = "df.clear_tag_filter"
    bl_label = "Clear Tag Filter"
    bl_description = "Clear the tag search filter"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = getattr(context.scene, "df_commit_props", None)
        if props and hasattr(props, "tag_search_filter"):
            props.tag_search_filter = ""
            # The update callback will automatically restore all commits
            return {'FINISHED'}
        self.report({'WARNING'}, "Commit properties are not available")
        return {'CANCELLED'}


def register():
    bpy.utils.register_class(DF_OT_create_project_commit)
    bpy.utils.register_class(DF_OT_select_assets_directory)
    bpy.utils.register_class(DF_OT_save_asset)
    bpy.utils.register_class(DF_OT_clear_tag_filter)


def unregister():
    bpy.utils.unregister_class(DF_OT_clear_tag_filter)
    bpy.utils.unregister_class(DF_OT_save_asset)
    bpy.utils.unregister_class(DF_OT_select_assets_directory)
    bpy.utils.unregister_class(DF_OT_create_project_commit)
