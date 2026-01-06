"""
Custom properties for Difference Machine add-on.
"""

import bpy
from bpy.props import (
    EnumProperty,
    StringProperty,
    BoolProperty,
    IntProperty,
)


def _update_comparison_object_position(prop_group, context):
    """
    Update callback for compare_object_axis and compare_object_offset.
    Updates comparison object position when axis or offset changes.
    """
    prop_group.update_comparison_object_position(context)


def _update_tag_search_filter(prop_group, context):
    """
    Update callback for tag_search_filter.
    Filters the commit list based on the tag search filter.
    """
    scene = context.scene
    tag_filter = prop_group.tag_search_filter.strip().lower() if prop_group.tag_search_filter else ""
    
    # Get all commits from backup collection
    if not hasattr(scene, 'df_commits_all'):
        # If backup doesn't exist yet (e.g., before first refresh), do nothing
        # The filter will be applied when refresh_history populates df_commits_all
        return
    
    # Clear current filtered list
    scene.df_commits.clear()
    
    # If df_commits_all is empty, there's nothing to filter
    if len(scene.df_commits_all) == 0:
        return
    
    # Filter commits based on tag
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


class DFCommitProperties(bpy.types.PropertyGroup):
    """Properties for commit operations."""
    
    def update_comparison_object_position(self, context):
        """
        Update comparison object position when axis or offset changes.
        This callback is called when compare_object_axis or compare_object_offset changes.
        """
        scene = context.scene
        
        # Check if comparison is active
        if not getattr(scene, 'df_object_comparison_active', False):
            return
        
        # Get comparison object name and original object name
        comparison_obj_name = getattr(scene, 'df_object_comparison_object_name', None)
        original_obj_name = getattr(scene, 'df_object_comparison_original_name', None)
        
        if not comparison_obj_name or not original_obj_name:
            return
        
        # Check if objects exist
        if comparison_obj_name not in bpy.data.objects:
            return
        
        if original_obj_name not in bpy.data.objects:
            return
        
        try:
            # Get objects
            comparison_obj = bpy.data.objects[comparison_obj_name]
            original_obj = bpy.data.objects[original_obj_name]
            
            # Get base location from original object
            base_location = list(original_obj.location.copy())
            
            # Get axis and offset from properties
            axis = self.compare_object_axis
            offset = self.compare_object_offset
            
            # Calculate offset vector based on axis
            offset_vector = [0.0, 0.0, 0.0]
            
            if axis == 'X':
                offset_vector[0] = float(offset)
            elif axis == 'Y':
                offset_vector[1] = float(offset)
            elif axis == 'Z':
                offset_vector[2] = float(offset)
            
            # Calculate new location
            new_location = (
                base_location[0] + offset_vector[0],
                base_location[1] + offset_vector[1],
                base_location[2] + offset_vector[2]
            )
            
            # Update comparison object location
            comparison_obj.location = new_location
            
        except (KeyError, AttributeError, ReferenceError) as e:
            # Silently fail if objects are invalid
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to update comparison object position: {e}")
    
    # Branch
    branch: StringProperty(
        name="Branch",
        description="Branch name",
        default="main",
    )
    
    # Commit message
    message: StringProperty(
        name="Message",
        description="Commit message",
        default="",
    )
    
    # Commit tag
    commit_tag: StringProperty(
        name="Tag",
        description="Optional tag for this commit",
        default="",
    )
    
    # Tag search filter
    tag_search_filter: StringProperty(
        name="Tag Search",
        description="Filter commits by tag name",
        default="",
        options={'TEXTEDIT_UPDATE'},
        update=_update_tag_search_filter,
    )
    
    # Branch search filter
    branch_search_filter: StringProperty(
        name="Branch Search",
        description="Filter branches by name",
        default="",
        options={'TEXTEDIT_UPDATE'},
    )
    
    # Load Commit tab selection
    load_commit_tab: EnumProperty(
        name="Load Commit Tab",
        description="Select tab in Load Commit panel",
        items=[
            ('PROJECT', "Project", "Project operations"),
            ('SELECTED', "Selected Object", "Selected object operations"),
        ],
        default='PROJECT',
    )
    
    # Object comparison properties
    compare_object_axis: EnumProperty(
        name="Compare Axis",
        description="Axis to offset comparison object",
        items=[
            ('X', "X", "X axis"),
            ('Y', "Y", "Y axis"),
            ('Z', "Z", "Z axis"),
        ],
        default='X',
        update=_update_comparison_object_position,
    )
    
    compare_object_offset: bpy.props.FloatProperty(
        name="Compare Offset",
        description="Distance to offset comparison object (negative values move in opposite direction)",
        default=2.0,
        update=_update_comparison_object_position,
    )


def register():
    """Register custom properties."""
    from . import commit_item
    from .commit_item import DFCommitItem, DFBranchItem, DFStashItem
    
    # Register item classes first
    commit_item.register()
    
    # Register main properties class
    bpy.utils.register_class(DFCommitProperties)
    bpy.types.Scene.df_commit_props = bpy.props.PointerProperty(type=DFCommitProperties)
    
    # Register collections for commits, branches, and stashes
    bpy.types.Scene.df_commits = bpy.props.CollectionProperty(type=DFCommitItem)
    bpy.types.Scene.df_commits_all = bpy.props.CollectionProperty(type=DFCommitItem)  # Backup collection for all commits
    bpy.types.Scene.df_branches = bpy.props.CollectionProperty(type=DFBranchItem)
    bpy.types.Scene.df_stashes = bpy.props.CollectionProperty(type=DFStashItem)
    
    # Index properties for UIList
    bpy.types.Scene.df_branch_list_index = bpy.props.IntProperty(name="Branch List Index", default=0)
    bpy.types.Scene.df_commit_list_index = bpy.props.IntProperty(
        name="Commit List Index", 
        default=0,
    )
    bpy.types.Scene.df_stash_list_index = bpy.props.IntProperty(name="Stash List Index", default=0)
    
    # Project comparison properties
    bpy.types.Scene.df_project_comparison_active = bpy.props.BoolProperty(
        name="Project Comparison Active",
        description="Whether project comparison is currently active",
        default=False,
    )
    
    bpy.types.Scene.df_project_comparison_commit_hash = bpy.props.StringProperty(
        name="Project Comparison Commit Hash",
        description="Hash of commit being compared",
        default="",
    )
    
    # Object comparison properties
    bpy.types.Scene.df_object_comparison_active = bpy.props.BoolProperty(
        name="Object Comparison Active",
        description="Whether object comparison is currently active",
        default=False,
    )
    
    bpy.types.Scene.df_object_comparison_object_name = bpy.props.StringProperty(
        name="Object Comparison Object Name",
        description="Name of comparison object",
        default="",
    )
    
    bpy.types.Scene.df_object_comparison_commit_hash = bpy.props.StringProperty(
        name="Object Comparison Commit Hash",
        description="Hash of commit being compared",
        default="",
    )
    
    bpy.types.Scene.df_object_comparison_original_name = bpy.props.StringProperty(
        name="Object Comparison Original Name",
        description="Name of the original object that was compared",
        default="",
    )


def unregister():
    """Unregister custom properties."""
    from . import commit_item
    
    # Unregister collections and index properties
    import logging
    logger = logging.getLogger(__name__)
    
    if hasattr(bpy.types.Scene, 'df_commits'):
        try:
            del bpy.types.Scene.df_commits
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_commits: {e}")
    
    if hasattr(bpy.types.Scene, 'df_commits_all'):
        try:
            del bpy.types.Scene.df_commits_all
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_commits_all: {e}")
    
    if hasattr(bpy.types.Scene, 'df_branches'):
        try:
            del bpy.types.Scene.df_branches
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_branches: {e}")
    
    if hasattr(bpy.types.Scene, 'df_branch_list_index'):
        try:
            del bpy.types.Scene.df_branch_list_index
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_branch_list_index: {e}")
    
    if hasattr(bpy.types.Scene, 'df_commit_list_index'):
        try:
            del bpy.types.Scene.df_commit_list_index
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_commit_list_index: {e}")
    
    if hasattr(bpy.types.Scene, 'df_stashes'):
        try:
            del bpy.types.Scene.df_stashes
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_stashes: {e}")
    
    if hasattr(bpy.types.Scene, 'df_stash_list_index'):
        try:
            del bpy.types.Scene.df_stash_list_index
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_stash_list_index: {e}")
    
    if hasattr(bpy.types.Scene, 'df_project_comparison_active'):
        try:
            del bpy.types.Scene.df_project_comparison_active
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_project_comparison_active: {e}")
    
    if hasattr(bpy.types.Scene, 'df_project_comparison_commit_hash'):
        try:
            del bpy.types.Scene.df_project_comparison_commit_hash
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_project_comparison_commit_hash: {e}")
    
    if hasattr(bpy.types.Scene, 'df_object_comparison_active'):
        try:
            del bpy.types.Scene.df_object_comparison_active
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_object_comparison_active: {e}")
    
    if hasattr(bpy.types.Scene, 'df_object_comparison_object_name'):
        try:
            del bpy.types.Scene.df_object_comparison_object_name
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_object_comparison_object_name: {e}")
    
    if hasattr(bpy.types.Scene, 'df_object_comparison_commit_hash'):
        try:
            del bpy.types.Scene.df_object_comparison_commit_hash
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_object_comparison_commit_hash: {e}")
    
    if hasattr(bpy.types.Scene, 'df_object_comparison_original_name'):
        try:
            del bpy.types.Scene.df_object_comparison_original_name
        except (ValueError, KeyError, RuntimeError) as e:
            import logging
            logging.debug(f"Error removing df_object_comparison_original_name: {e}")
    
    if hasattr(bpy.types.Scene, 'df_commit_props'):
        try:
            del bpy.types.Scene.df_commit_props
        except (ValueError, KeyError, RuntimeError) as e:
            logger.debug(f"Error removing df_commit_props: {e}")
    
    # Unregister classes
    try:
        bpy.utils.unregister_class(DFCommitProperties)
    except (RuntimeError, ValueError):
        pass
    
    # Unregister item classes
    commit_item.unregister()
