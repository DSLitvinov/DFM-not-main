"""
UI panels for Difference Machine add-on.
"""

import bpy
from bpy.types import Panel, Context
from pathlib import Path
from typing import Optional, Any

def get_current_branch_name(context: Context) -> str:
    """Get current branch name from repository or return default."""
    try:
        blend_file = Path(bpy.data.filepath)
        if not blend_file:
            return "main"
        
        from ..utils.helpers import find_repository_root
        from ..utils.forester_cli import get_cli
        
        project_root = blend_file.parent
        repo_path = find_repository_root(project_root)
        if repo_path:
            cli = get_cli()
            success, status_data, _ = cli.status(repo_path)
            if success and status_data:
                return status_data.get("branch", "main")
    except (AttributeError, RuntimeError, ValueError, KeyError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Error getting current branch name: {e}")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Unexpected error getting current branch name: {e}")
    
    # Fallback to props or default
    try:
        props = context.scene.df_commit_props
        return props.branch if props and props.branch else "main"
    except (AttributeError, KeyError):
        return "main"


class DF_PT_commit_panel(Panel):
    """Panel for creating commits."""
    bl_label = "Create Commit"
    bl_idname = "DF_PT_commit_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Difference Machine"
    bl_order = 2

    @classmethod
    def poll(cls, context):
        """Show panel only if repository is initialized."""
        from ..utils.helpers import is_repository_initialized
        if not is_repository_initialized(context):
            return False
        
        # Hide panel if comparison object "compare" is selected
        active_obj = context.active_object
        if active_obj:
            scene = context.scene
            comparison_obj_name = getattr(scene, 'df_object_comparison_object_name', '')
            if comparison_obj_name == 'compare' and active_obj.name == 'compare':
                return False
        
        return True

    def draw(self, context: Context) -> None:
        """Draw the panel UI."""
        layout = self.layout
        props = context.scene.df_commit_props
        
        # Проверяем, является ли активный объект объектом сравнения
        active_obj = context.active_object
        scene = context.scene
        comparison_obj_name = getattr(scene, 'df_comparison_object_name', None)
        is_comparison_object = (active_obj and 
                               active_obj.type == 'MESH' and 
                               comparison_obj_name and 
                               active_obj.name == comparison_obj_name)
        
        if is_comparison_object:
            # Если активен объект сравнения, показываем только информационное сообщение
            box = layout.box()
            box.label(text="Comparison mode active", icon='INFO')
            box.label(text="Only viewing is available")
            return
        
        # Asset saving section (if any object is selected)
        active_obj = context.active_object
        if active_obj:
            box = layout.box()
            box.label(text="Save as Asset", icon='PACKAGE')
            row = box.row()
            row.scale_y = 1.2
            row.operator("df.save_asset", text="Save Selected Object", icon='EXPORT')
            obj_type_label = active_obj.type.lower().replace('_', ' ').title()
            box.label(text=f"Save {obj_type_label} as separate .blend file", icon='INFO')
            layout.separator()
        
        # Show working directory status (if available)
        box = layout.box()
        box.label(text="Full Project Commit", icon='FILE_FOLDER')
        # Note: File count and changes can be displayed here in future versions
        
        # Common fields
        layout.separator()
        
        # Branch (display as text)
        row = layout.row()
        row.label(text="Branch:")
        current_branch = get_current_branch_name(context)
        row.label(text=current_branch)
        
        # Message (required)
        layout.prop(props, "message", text="Message")
        
        # Tag (optional)
        layout.prop(props, "commit_tag", text="Tag", icon='BOOKMARKS')
        
        # Validate field: Message must not be empty
        message_text = props.message if props.message else ""
        message_valid = bool(message_text and message_text.strip())
        
        # Create commit button (disabled if message is empty)
        layout.separator()
        row = layout.row()
        row.enabled = message_valid
        row.operator("df.create_project_commit", text="Create Commit", icon='EXPORT')
        
        # Show validation message if message is empty
        if not message_valid:
            box = layout.box()
            box.label(text="Message is required", icon='ERROR')



class DF_PT_branch_panel(Panel):
    """Panel for branch management."""
    bl_label = "Branch Management"
    bl_idname = "DF_PT_branch_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Difference Machine"
    bl_order = 1
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        """Hide panel if comparison object 'compare' is selected."""
        active_obj = context.active_object
        if active_obj:
            scene = context.scene
            comparison_obj_name = getattr(scene, 'df_object_comparison_object_name', '')
            if comparison_obj_name == 'compare' and active_obj.name == 'compare':
                return False
        return True

    def draw(self, context: Context) -> None:
        """Draw the panel UI."""
        layout = self.layout
        scene = context.scene
        props = context.scene.df_commit_props
        
        # Проверяем, является ли активный объект объектом сравнения
        active_obj = context.active_object
        comparison_obj_name = getattr(scene, 'df_comparison_object_name', None)
        is_comparison_object = (active_obj and 
                               active_obj.type == 'MESH' and 
                               comparison_obj_name and 
                               active_obj.name == comparison_obj_name)
        
        # Check repository state
        from ..utils.helpers import is_repository_initialized
        repo_initialized = is_repository_initialized(context)
        file_saved = bool(bpy.data.filepath)
        
        # Refresh button (всегда доступен для просмотра)
        row = layout.row()
        row.operator("df.refresh_branches", text="Refresh Branches", icon='FILE_REFRESH')
        
        # Init project button (show only if repository not initialized)
        if not repo_initialized:
            layout.separator()
            row = layout.row()
            row.scale_y = 1.2
            row.operator("df.init_project", text="Init Project", icon='FILE_NEW')
        
        # Show error message only if file not saved
        if not file_saved:
            layout.separator()
            box = layout.box()
            box.label(text="Please save the Blender file first", icon='ERROR')
        
        # Auto-refresh if list is empty and file is saved and repo initialized
        branches = scene.df_branches
        if len(branches) == 0 and bpy.data.filepath and repo_initialized:
            # Try to auto-load
            try:
                bpy.ops.df.refresh_branches()
            except (RuntimeError, AttributeError, KeyError) as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Failed to auto-refresh branches: {e}")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Unexpected error auto-refreshing branches: {e}")
        
        # List branches using UIList (only if repo initialized)
        if repo_initialized:
            if len(branches) == 0:
                # Auto-refresh if list is empty (branch "main" should exist after init)
                box = layout.box()
                box.label(text="Loading branches...", icon='INFO')
                # Try to auto-load
                try:
                    bpy.ops.df.refresh_branches()
                except (RuntimeError, AttributeError, KeyError) as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"Failed to auto-refresh branches: {e}")
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Unexpected error auto-refreshing branches: {e}")
            else:
                # UIList for branches (stretchable)
                row = layout.row()
                row.template_list(
                    "DF_UL_branch_list", "",
                    scene, "df_branches",
                    scene, "df_branch_list_index",
                    rows=6  # Default 6 rows, stretchable
                )
        
        # Branch operations (скрываем для объекта сравнения, показываем только если repo initialized)
        if not is_comparison_object and repo_initialized:
            layout.separator()
            
            col = layout.column(align=True)
            # Buttons always enabled (no disabled states)
            create_row = col.row()
            create_row.operator("df.create_branch", text="Create New Branch", icon='ADD')
            
            switch_row = col.row()
            switch_row.operator("df.switch_branch", text="Switch Branch", icon='ARROW_LEFTRIGHT')
            
            # Delete branch button (only if branch is selected)
            if (branches and 
                hasattr(scene, 'df_branch_list_index') and
                scene.df_branch_list_index >= 0 and 
                scene.df_branch_list_index < len(branches)):
                layout.separator()
                selected_branch = branches[scene.df_branch_list_index]
                
                # Can delete if more than one branch and not current
                can_delete = (len(branches) > 1 and not selected_branch.is_current)
                
                row = layout.row()
                row.enabled = can_delete
                row.scale_y = 1.2
                op = row.operator("df.delete_branch", text="Delete Branch", icon='TRASH')
                op.branch_name = selected_branch.name
                
                if not can_delete:
                    layout.separator()
                    info_row = layout.row()
                    if len(branches) <= 1:
                        info_row.label(text="Cannot delete the last branch", icon='INFO')
                    elif selected_branch.is_current:
                        info_row.label(text="Cannot delete current branch", icon='INFO')
        
        else:
            # Показываем информационное сообщение для объекта сравнения
            layout.separator()
            box = layout.box()
            box.label(text="Comparison mode active", icon='INFO')
            box.label(text="Only viewing is available")


class DF_PT_history_panel(Panel):
    """Panel for viewing commit history."""
    bl_label = "Load Commit"
    bl_idname = "DF_PT_history_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Difference Machine"
    bl_order = 3

    @classmethod
    def poll(cls, context: Context) -> bool:
        """Show panel only if repository is initialized."""
        from ..utils.helpers import is_repository_initialized
        return is_repository_initialized(context)
    
    def _is_compare_object_selected(self, context: Context) -> bool:
        """Check if comparison object 'compare' is selected."""
        active_obj = context.active_object
        if not active_obj:
            return False
        scene = context.scene
        comparison_obj_name = getattr(scene, 'df_object_comparison_object_name', '')
        return comparison_obj_name == 'compare' and active_obj.name == 'compare'

    def draw(self, context: Context) -> None:
        """Draw the panel UI."""
        layout = self.layout
        
        # Check if comparison object "compare" is selected
        is_compare_selected = self._is_compare_object_selected(context)
        
        if is_compare_selected:
            # Show only Compare Settings and Compare button
            scene = context.scene
            props = context.scene.df_commit_props
            comparison_commit_hash = getattr(scene, 'df_object_comparison_commit_hash', '')
            
            if comparison_commit_hash:
                # Compare settings
                box = layout.box()
                box.label(text="Compare Settings:", icon='SETTINGS')
                row = box.row()
                row.prop(props, "compare_object_axis", expand=True)
                row = box.row()
                row.prop(props, "compare_object_offset")
                
                # Compare button (will remove the comparison object)
                layout.separator()
                row = layout.row()
                row.scale_y = 1.2
                op = row.operator("df.compare_object", text="Compare", icon='SPLIT_HORIZONTAL', depress=True)
                op.commit_hash = comparison_commit_hash
                op.axis = props.compare_object_axis
                op.offset = props.compare_object_offset
            return
        
        # Normal panel content
        # Проверяем, является ли активный объект объектом сравнения
        active_obj = context.active_object
        scene = context.scene
        comparison_obj_name = getattr(scene, 'df_comparison_object_name', None)
        is_comparison_object = (active_obj and 
                               active_obj.type == 'MESH' and 
                               comparison_obj_name and 
                               active_obj.name == comparison_obj_name)
        
        # Refresh button (всегда доступен для просмотра)
        row = layout.row()
        row.operator("df.refresh_history", icon='FILE_REFRESH')
        
        # Tag search filter
        props = context.scene.df_commit_props
        layout.separator()
        box = layout.box()
        row = box.row()
        row.label(text="Search by Tag:", icon='VIEWZOOM')
        row = box.row()
        row.prop(props, "tag_search_filter", text="", icon='BOOKMARKS')
        if props.tag_search_filter:
            # Clear filter button
            row = box.row()
            row.operator("df.clear_tag_filter", text="Clear Filter", icon='X')
        
        # Branch (display as text)
        layout.separator()
        row = layout.row()
        row.label(text="Branch:")
        current_branch = get_current_branch_name(context)
        row.label(text=current_branch)
        
        # Tab switcher (сегментированный контрол)
        layout.separator()
        props = context.scene.df_commit_props
        row = layout.row()
        row.prop(props, "load_commit_tab", expand=True)
        
        # Auto-refresh if list is empty and file is saved
        commits = context.scene.df_commits
        if len(commits) == 0 and bpy.data.filepath:
            # Try to auto-load
            try:
                bpy.ops.df.refresh_history()
            except (RuntimeError, AttributeError, KeyError) as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Failed to auto-refresh history: {e}")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Unexpected error auto-refreshing history: {e}")
        
        # Selected commit details
        commit_list_index = context.scene.df_commit_list_index
        
        # Show content based on selected tab
        if props.load_commit_tab == 'SELECTED':
            # Selected Object tab
            self._draw_selected_object_tab(context, layout, props, commits, commit_list_index)
        else:
            # Project tab (existing functionality)
            self._draw_project_tab(context, layout, commits, commit_list_index)

    def _draw_project_tab(self, context: Context, layout: Any, commits: Any, commit_list_index: int) -> None:
        """Draw Project tab content."""
        # List commits using UIList
        if len(commits) == 0:
            box = layout.box()
            box.label(text="No commits found", icon='INFO')
            box.label(text="Click Refresh to load")
        else:
            # UIList for commits
            row = layout.row()
            row.template_list(
                "DF_UL_commit_list", "",
                context.scene, "df_commits",
                context.scene, "df_commit_list_index",
                rows=5
            )
            
            # Selected commit details
            if commits and len(commits) > 0 and 0 <= commit_list_index < len(commits):
                commit = commits[commit_list_index]
                
                # Проверяем, что коммит валиден (имеет хеш)
                if commit and commit.hash:
                    box = layout.box()
                    
                    # Commit details: Author, Hash, Message, Tag, HEAD (if exists)
                    box.label(text=f"Author: {commit.author}")
                    box.label(text=f"Hash: {commit.hash}")
                    box.label(text=f"Message: {commit.message}")
                    # Always show Tag (even if empty)
                    tag_value = commit.tag if commit.tag else "(нет)"
                    box.label(text=f"Tag: {tag_value}")
                    is_head_commit = getattr(commit, 'is_head', False)
                    if is_head_commit:
                        box.label(text="HEAD: true", icon='BOOKMARKS')
                    
                    # Проверяем, является ли активный объект объектом сравнения
                    scene = context.scene
                    active_obj = context.active_object
                    comparison_obj_name = getattr(scene, 'df_comparison_object_name', None)
                    comparison_commit_hash = getattr(scene, 'df_comparison_commit_hash', None)
                    is_comparison_object = (active_obj and 
                                           active_obj.type == 'MESH' and 
                                           comparison_obj_name and 
                                           active_obj.name == comparison_obj_name)
                    
                    # Action buttons - для обычных коммитов - Checkout, Compare и Delete
                    # Скрываем кнопки, если активен объект сравнения
                    if not is_comparison_object:
                        # Checkout button
                        layout.separator()
                        row = layout.row()
                        row.scale_y = 1.5
                        op = row.operator("df.checkout_commit", text="Checkout", icon='CHECKMARK')
                        op.commit_hash = commit.hash
                        
                        # Compare button
                        layout.separator()
                        row = layout.row()
                        row.scale_y = 1.2
                        
                        # Check if project comparison is active for this commit
                        is_project_comparison_active = (
                            getattr(scene, 'df_project_comparison_active', False) and
                            getattr(scene, 'df_project_comparison_commit_hash', '') == commit.hash
                        )
                        
                        op = row.operator("df.compare_project", text="Compare", icon='SPLIT_HORIZONTAL', depress=is_project_comparison_active)
                        op.commit_hash = commit.hash
                        
                        # Delete button
                        layout.separator()
                        row = layout.row()
                        row.scale_y = 1.2
                        op = row.operator("df.delete_commit", text="Delete This Version", icon='TRASH')
                        op.commit_hash = commit.hash

    def _draw_selected_object_tab(self, context: Context, layout: Any, props: Any, commits: Any, commit_list_index: int) -> None:
        """Draw Selected Object tab content."""
        active_obj = context.active_object
        
        # Show selected object name
        layout.separator()
        box = layout.box()
        if active_obj:
            # Get icon based on object type
            icon_map = {
                'MESH': 'MESH_DATA',
                'LIGHT': 'LIGHT',
                'CAMERA': 'CAMERA',
                'ARMATURE': 'ARMATURE_DATA',
                'CURVE': 'CURVE_DATA',
                'SURFACE': 'SURFACE_DATA',
                'META': 'META_DATA',
                'FONT': 'FONT_DATA',
                'LATTICE': 'LATTICE_DATA',
                'GPENCIL': 'GREASEPENCIL',
                'VOLUME': 'VOLUME_DATA',
            }
            icon = icon_map.get(active_obj.type, 'OBJECT_DATA')
            obj_type_label = active_obj.type.lower().replace('_', ' ').title()
            box.label(text=f"Selected {obj_type_label}: {active_obj.name}", icon=icon)
            has_selected_object = True
        else:
            box.label(text="No object selected", icon='ERROR')
            has_selected_object = False
        
        # Show commit list
        if len(commits) == 0:
            box = layout.box()
            box.label(text="No commits found", icon='INFO')
            box.label(text="Click Refresh to load")
            return
        
        # UIList for commits
        row = layout.row()
        row.template_list(
            "DF_UL_commit_list", "",
            context.scene, "df_commits",
            context.scene, "df_commit_list_index",
            rows=5
        )
        
        # Check if commit is selected
        commit = None
        if commits and len(commits) > 0 and 0 <= commit_list_index < len(commits):
            commit = commits[commit_list_index]
        
        # Action buttons
        if has_selected_object and commit and commit.hash:
            layout.separator()
            
            # Показываем информацию о коммите и объекте
            info_box = layout.box()
            info_box.label(text=f"Commit: {commit.hash[:16]}...", icon='COMMUNITY')
            info_box.label(text=f"Object: {active_obj.name} ({active_obj.type})", icon='OBJECT_DATA')
            
            layout.separator()
            
            # Replace Object button
            row = layout.row()
            row.scale_y = 1.5
            op = row.operator("df.replace_mesh", text="Replace Object", icon='FILE_REFRESH')
            op.commit_hash = commit.hash
            
            # Compare settings
            layout.separator()
            box = layout.box()
            box.label(text="Compare Settings:", icon='SETTINGS')
            row = box.row()
            row.prop(props, "compare_object_axis", expand=True)
            row = box.row()
            row.prop(props, "compare_object_offset")
            
            # Compare button
            layout.separator()
            row = layout.row()
            row.scale_y = 1.2
            
            # Check if comparison is active
            # Compare is active if:
            # 1. Comparison is marked as active
            # 2. Commit hash matches
            # 3. Original object name matches (to handle cases where user selects different object)
            # 4. Comparison object exists in scene
            scene = context.scene
            comparison_active = getattr(scene, 'df_object_comparison_active', False)
            comparison_commit_hash = getattr(scene, 'df_object_comparison_commit_hash', '')
            comparison_obj_name = getattr(scene, 'df_object_comparison_object_name', '')
            original_obj_name = getattr(scene, 'df_object_comparison_original_name', '')
            
            # Check if comparison object exists in scene
            comparison_obj_exists = (
                comparison_obj_name and 
                comparison_obj_name in bpy.data.objects
            )
            
            # Check if current active object matches original object
            # If original_obj_name is not set, allow any object (for backward compatibility)
            current_obj_matches = (
                active_obj and 
                (not original_obj_name or original_obj_name == active_obj.name)
            )
            
            # Comparison is active if all conditions are met
            is_comparison_active = (
                comparison_active and
                comparison_commit_hash == commit.hash and
                comparison_obj_exists and
                current_obj_matches
            )
            
            # Debug logging (can be removed later)
            if comparison_active:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Comparison check: active={comparison_active}, "
                           f"commit_match={comparison_commit_hash == commit.hash}, "
                           f"obj_exists={comparison_obj_exists}, "
                           f"obj_matches={current_obj_matches}, "
                           f"result={is_comparison_active}")
            
            op = row.operator("df.compare_object", text="Compare", icon='SPLIT_HORIZONTAL', depress=is_comparison_active)
            op.commit_hash = commit.hash
            op.axis = props.compare_object_axis
            op.offset = props.compare_object_offset
            
            if is_comparison_active:
                layout.separator()
                box = layout.box()
                box.label(text="Comparison active", icon='INFO')
                box.label(text="Press Compare again to remove")
        elif not has_selected_object:
            layout.separator()
            box = layout.box()
            box.label(text="Select an object to use this feature", icon='INFO')
        elif not commit:
            layout.separator()
            box = layout.box()
            box.label(text="Select a commit from the list", icon='INFO')


class DF_PT_lock_panel(Panel):
    """Panel for file lock management."""
    bl_label = "File Locks"
    bl_idname = "DF_PT_lock_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Difference Machine"
    bl_order = 4
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        """Show panel only if repository is initialized."""
        from ..utils.helpers import is_repository_initialized
        if not is_repository_initialized(context):
            return False
        
        # Hide panel if comparison object 'compare' is selected
        active_obj = context.active_object
        if active_obj:
            scene = context.scene
            comparison_obj_name = getattr(scene, 'df_object_comparison_object_name', '')
            if comparison_obj_name == 'compare' and active_obj.name == 'compare':
                return False
        return True

    def draw(self, context: Context) -> None:
        """Draw the panel UI."""
        layout = self.layout
        scene = context.scene
        
        # Check repository state
        from ..utils.helpers import is_repository_initialized, get_repository_path, check_locked_files
        repo_initialized = is_repository_initialized(context)
        
        if not repo_initialized:
            box = layout.box()
            box.label(text="Repository not initialized", icon='ERROR')
            return
        
        # Check locks button
        row = layout.row()
        row.scale_y = 1.2
        row.operator("df.check_locks", text="Check Current Files", icon='VIEWZOOM')
        
        # Lock/Unlock files buttons
        layout.separator()
        col = layout.column(align=True)
        row = col.row()
        row.scale_y = 1.2
        row.enabled = bool(bpy.data.filepath)
        op = row.operator("df.lock_current_blend", text="Lock Files", icon='LOCKED')
        
        row = col.row()
        row.scale_y = 1.2
        row.enabled = bool(bpy.data.filepath)
        op = row.operator("df.unlock_current_blend", text="Unlock Files", icon='UNLOCKED')
        
        # List all locks button
        layout.separator()
        row = layout.row()
        row.operator("df.list_locks", text="List All Locks", icon='FILE_TEXT')
        
        # Show locked files info
        layout.separator()
        repo_path, error = get_repository_path()
        if repo_path:
            locked_files = check_locked_files(repo_path)
            
            if locked_files:
                box = layout.box()
                box.label(text=f"⚠️ {len(locked_files)} file(s) locked:", icon='ERROR')
                
                for file_path, lock_info in list(locked_files.items())[:5]:  # Show first 5
                    lock_type = lock_info.get('lock_type', 'exclusive')
                    user = lock_info.get('user', 'Unknown')
                    expires_at = lock_info.get('expires_at')
                    
                    row = box.row()
                    row.scale_y = 0.8
                    file_name = file_path.name
                    lock_msg = f"{file_name} ({lock_type}) by {user}"
                    if expires_at:
                        from datetime import datetime
                        try:
                            exp_dt = datetime.fromtimestamp(expires_at)
                            lock_msg += f" until {exp_dt.strftime('%Y-%m-%d %H:%M')}"
                        except (ValueError, OSError, OverflowError) as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.debug(f"Failed to format expiration date: {e}")
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Unexpected error formatting expiration date: {e}")
                    row.label(text=lock_msg, icon='LOCKED')
                
                if len(locked_files) > 5:
                    box.label(text=f"... and {len(locked_files) - 5} more", icon='DOT')
            else:
                box = layout.box()
                box.label(text="No locked files", icon='CHECKMARK')


class DF_PT_stash_panel(Panel):
    """Panel for stash management."""
    bl_label = "Stash Management"
    bl_idname = "DF_PT_stash_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Difference Machine"
    bl_order = 5
    
    @classmethod
    def poll(cls, context: Context) -> bool:
        """Show panel only if repository is initialized."""
        from ..utils.helpers import is_repository_initialized
        if not is_repository_initialized(context):
            return False
        
        # Hide panel if comparison object 'compare' is selected
        active_obj = context.active_object
        if active_obj:
            scene = context.scene
            comparison_obj_name = getattr(scene, 'df_object_comparison_object_name', '')
            if comparison_obj_name == 'compare' and active_obj.name == 'compare':
                return False
        return True

    def draw(self, context: Context) -> None:
        """Draw the panel UI."""
        layout = self.layout
        scene = context.scene
        
        # Check repository state
        from ..utils.helpers import is_repository_initialized
        repo_initialized = is_repository_initialized(context)
        
        if not repo_initialized:
            layout.label(text="Repository not initialized", icon='ERROR')
            return
        
        # Refresh button
        row = layout.row()
        row.operator("df.refresh_stashes", text="Refresh Stashes", icon='FILE_REFRESH')
        
        # Save stash button
        layout.separator()
        row = layout.row()
        row.scale_y = 1.2
        row.operator("df.save_stash", text="Save Stash", icon='PACKAGE')
        
        # Stash list
        layout.separator()
        stashes = scene.df_stashes
        
        # Auto-refresh if list is empty
        if len(stashes) == 0:
            try:
                bpy.ops.df.refresh_stashes()
            except (RuntimeError, AttributeError, KeyError) as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Failed to auto-refresh stashes: {e}")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Unexpected error auto-refreshing stashes: {e}")
        
        if len(stashes) == 0:
            box = layout.box()
            box.label(text="No stashes found", icon='INFO')
        else:
            # UIList for stashes
            row = layout.row()
            row.template_list(
                "DF_UL_stash_list", "",
                scene, "df_stashes",
                scene, "df_stash_list_index",
                rows=6
            )
            
            # Selected stash operations
            if (hasattr(scene, 'df_stash_list_index') and 
                scene.df_stash_list_index >= 0 and 
                scene.df_stash_list_index < len(stashes)):
                selected_stash = stashes[scene.df_stash_list_index]
                
                layout.separator()
                box = layout.box()
                box.label(text=f"Hash: {selected_stash.hash[:16] + '...' if selected_stash.hash else 'unknown'}")
                box.label(text=f"Message: {selected_stash.message}")
                
                # Action buttons
                layout.separator()
                row = layout.row()
                row.scale_y = 1.2
                op = row.operator("df.apply_stash", text="Apply", icon='IMPORT')
                op.stash_hash = selected_stash.hash
                
                row = layout.row()
                row.scale_y = 1.2
                op = row.operator("df.pop_stash", text="Pop", icon='IMPORT')
                op.stash_hash = selected_stash.hash
                
                row = layout.row()
                row.scale_y = 1.2
                op = row.operator("df.stash_drop", text="Drop", icon='TRASH')
                op.stash_hash = selected_stash.hash


def register():
    """Register all panel classes."""
    bpy.utils.register_class(DF_PT_commit_panel)
    bpy.utils.register_class(DF_PT_branch_panel)
    bpy.utils.register_class(DF_PT_history_panel)
    bpy.utils.register_class(DF_PT_lock_panel)
    bpy.utils.register_class(DF_PT_stash_panel)


def unregister():
    """Unregister all panel classes."""
    bpy.utils.unregister_class(DF_PT_stash_panel)
    bpy.utils.unregister_class(DF_PT_lock_panel)
    bpy.utils.unregister_class(DF_PT_history_panel)
    bpy.utils.unregister_class(DF_PT_branch_panel)
    bpy.utils.unregister_class(DF_PT_commit_panel)

