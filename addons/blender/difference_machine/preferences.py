"""
Preferences for Difference Machine addon.
"""

import bpy
from bpy.types import AddonPreferences
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty
from pathlib import Path


class DifferenceMachinePreferences(AddonPreferences):
    bl_idname = __package__

    default_author: StringProperty(
        name="Default Author",
        description="Default author name for commits",
        default="Unknown",
    )
    
    # Reflog settings
    reflog_expire_days: IntProperty(
        name="Reflog Expiration (Days)",
        description="Number of days to keep commits in reflog before they can be deleted (like git reflog expire)",
        default=90,
        min=1,
        max=3650,  # 10 years
    )
    
    # Garbage collection schedule settings
    gc_schedule_enabled: BoolProperty(
        name="Enable Scheduled GC",
        description="Enable automatic garbage collection at specified time",
        default=False,
    )
    
    gc_schedule_hour: IntProperty(
        name="Hour",
        description="Hour of day to run garbage collection (0-23)",
        default=2,
        min=0,
        max=23,
    )
    
    gc_schedule_minute: IntProperty(
        name="Minute",
        description="Minute of hour to run garbage collection (0-59)",
        default=0,
        min=0,
        max=59,
    )
    
    gc_schedule_interval_days: IntProperty(
        name="Interval (Days)",
        description="Run garbage collection every N days",
        default=7,
        min=1,
        max=365,
    )
    
    gc_last_run: bpy.props.FloatProperty(
        name="Last Run",
        description="Timestamp of last garbage collection run",
        default=0.0,
    )

    def draw(self, context):
        layout = self.layout

        # Основные настройки
        box = layout.box()
        box.label(text="Commit Settings", icon='SETTINGS')
        box.prop(self, "default_author")
        
        # Garbage collection settings
        box = layout.box()
        box.label(text="Garbage Collection", icon='BRUSH_DATA')
        
        # Check if repository exists using CLI
        blend_file = Path(bpy.data.filepath) if bpy.data.filepath else None
        repo_exists = False
        if blend_file:
            try:
                from .utils.forester_cli import get_cli
                from .utils.helpers import find_repository_root
                
                repo_path = find_repository_root(blend_file.parent)
                if repo_path:
                    # Check if repository is valid by trying status
                    cli = get_cli()
                    success, _, _ = cli.status(repo_path)
                    repo_exists = success
            except Exception:
                pass
        
        if repo_exists:
            # Manual garbage collect button
            row = box.row()
            row.scale_y = 1.5
            try:
                op = row.operator("df.garbage_collect", text="Garbage Collect Now", icon='BRUSH_DATA')
                if op:
                    op.dry_run = False
            except (AttributeError, KeyError, RuntimeError) as e:
                # Operator not registered
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Garbage collect operator not available: {e}")
                row.enabled = False
                row.label(text="Garbage Collect (operator not available)", icon='ERROR')
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Unexpected error accessing garbage collect operator: {e}")
                row.enabled = False
                row.label(text="Garbage Collect (operator not available)", icon='ERROR')
            
            # Note: dry-run not yet supported by CLI
            # row = box.row()
            # row.scale_y = 1.2
            # op = row.operator("df.garbage_collect", text="Dry Run (Preview)", icon='VIEWZOOM')
            # if op:
            #     op.dry_run = True
            
            box.separator()
            
            # Reflog expiration settings
            box.prop(self, "reflog_expire_days", text="Keep Commits in Reflog (days)")
            box.label(text="Commits older than this will be removed during GC", icon='INFO')
            
            box.separator()
            
            # Scheduled garbage collection settings
            box.prop(self, "gc_schedule_enabled", text="Enable Scheduled GC")
            
            if self.gc_schedule_enabled:
                row = box.row()
                row.label(text="Run at:")
                row.prop(self, "gc_schedule_hour", text="Hour")
                row.prop(self, "gc_schedule_minute", text="Min")
                
                box.prop(self, "gc_schedule_interval_days", text="Every (days)")
                
                # Show last run time if available
                if self.gc_last_run > 0:
                    import time
                    last_run_time = time.ctime(self.gc_last_run)
                    box.label(text=f"Last run: {last_run_time}", icon='TIME')
        else:
            box.label(text="Save Blender file to enable", icon='INFO')
            box.label(text="garbage collection tools")
        
        # Database maintenance
        box = layout.box()
        box.label(text="Database Maintenance", icon='TOOL_SETTINGS')
        
        if repo_exists:
            row = box.row()
            row.scale_y = 1.5
            try:
                op = row.operator("df.rebuild_database", text="Rebuild Database", icon='FILE_REFRESH')
            except (AttributeError, KeyError, RuntimeError) as e:
                # Operator not registered
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"Rebuild database operator not available: {e}")
                row.enabled = False
                row.label(text="Rebuild Database (operator not available)", icon='ERROR')
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Unexpected error accessing rebuild database operator: {e}")
                row.enabled = False
                row.label(text="Rebuild Database (operator not available)", icon='ERROR')
            box.label(text="Rebuild database from storage", icon='INFO')
            box.label(text="(Use if database is corrupted)")
        else:
            box.label(text="Save Blender file to enable", icon='INFO')
            box.label(text="database maintenance tools")


def register():
    bpy.utils.register_class(DifferenceMachinePreferences)


def unregister():
    bpy.utils.unregister_class(DifferenceMachinePreferences)
