"""
Operators for repository initialization.
"""

import bpy
from bpy.types import Operator
from pathlib import Path
from ..utils.forester_cli import get_cli, ForesterCLIError
from ..utils.helpers import find_repository_root


class DF_OT_init_project(Operator):
    """Initialize a new Forester repository."""
    bl_idname = "df.init_project"
    bl_label = "Init Project"
    bl_description = "Initialize a new Forester repository in the current directory"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Please save the Blender file first")
            return {'CANCELLED'}
        
        blend_file = Path(bpy.data.filepath)
        project_root = blend_file.parent
        
        # Check if repository already exists
        repo_path = find_repository_root(project_root)
        if repo_path:
            self.report({'WARNING'}, f"Repository already exists at {repo_path}")
            return {'CANCELLED'}
        
        # Check if forester CLI is configured
        from ..utils.config_loader import get_forester_path, validate_forester_path
        
        forester_path = get_forester_path()
        is_valid, validation_error = validate_forester_path(forester_path)
        
        if not is_valid:
            self.report({'ERROR'}, validation_error)
            return {'CANCELLED'}
        
        # Initialize repository
        cli = get_cli()
        success, error_msg = cli.init(project_root)
        
        if success:
            # Automatically refresh branches after initialization
            # (CLI now creates "main" branch automatically)
            try:
                bpy.ops.df.refresh_branches()
            except (RuntimeError, AttributeError, KeyError) as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Failed to refresh branches after init: {e}")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Unexpected error refreshing branches after init: {e}")
            
            self.report({'INFO'}, f"Repository initialized in {project_root}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to initialize repository: {error_msg}")
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(DF_OT_init_project)


def unregister():
    bpy.utils.unregister_class(DF_OT_init_project)
