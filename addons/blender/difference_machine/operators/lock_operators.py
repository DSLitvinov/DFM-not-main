"""
Lock operators for Difference Machine addon.
Provides operators for checking and managing file locks.
"""

import bpy
from bpy.types import Operator
from pathlib import Path
from typing import Dict, Any, List
import os

from ..utils.helpers import get_repository_path, get_blender_files, check_locked_files
from ..utils.forester_cli import get_cli
from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class DF_OT_check_locks(Operator):
    """Check if current Blender files are locked."""
    bl_idname = "df.check_locks"
    bl_label = "Check File Locks"
    bl_description = "Check if current .blend file and textures are locked"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        repo_path, error = get_repository_path()
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        locked_files = check_locked_files(repo_path)
        
        if not locked_files:
            self.report({'INFO'}, "No locked files found")
            return {'FINISHED'}
        
        # Формируем сообщение о заблокированных файлах
        locked_count = len(locked_files)
        file_list = []
        for file_path, lock_info in locked_files.items():
            lock_type = lock_info.get('lock_type', 'exclusive')
            user = lock_info.get('user', 'Unknown')
            expires_at = lock_info.get('expires_at')
            
            file_name = file_path.name
            lock_msg = f"{file_name} ({lock_type}) by {user}"
            if expires_at:
                from datetime import datetime
                try:
                    exp_dt = datetime.fromtimestamp(expires_at)
                    lock_msg += f" expires: {exp_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                except:
                    pass
            
            file_list.append(lock_msg)
        
        message = f"Found {locked_count} locked file(s):\n" + "\n".join(file_list)
        self.report({'WARNING'}, message)
        
        # Сохраняем информацию в контексте для UI
        if not hasattr(context.scene, 'df_lock_info'):
            from bpy.props import StringProperty
            bpy.types.Scene.df_lock_info = StringProperty()
        
        context.scene.df_lock_info = message
        
        return {'FINISHED'}


class DF_OT_lock_file(Operator):
    """Lock a file."""
    bl_idname = "df.lock_file"
    bl_label = "Lock File"
    bl_description = "Lock a file (exclusive or shared)"
    bl_options = {'REGISTER', 'UNDO'}

    file_path: bpy.props.StringProperty(
        name="File Path",
        description="Path to file to lock",
        default=""
    )
    
    exclusive: bpy.props.BoolProperty(
        name="Exclusive",
        description="Exclusive lock (only one user can lock)",
        default=True
    )
    
    expire_hours: bpy.props.IntProperty(
        name="Expire Hours",
        description="Lock expiration time in hours (0 = never expires)",
        default=0,
        min=0
    )

    def execute(self, context):
        repo_path, error = get_repository_path()
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        if not self.file_path:
            self.report({'ERROR'}, "File path required")
            return {'CANCELLED'}
        
        try:
            cli = get_cli()
            success, error_msg = cli.lock_file(
                repo_path,
                self.file_path,
                exclusive=self.exclusive,
                expire_hours=self.expire_hours if self.expire_hours > 0 else None
            )
            
            if success:
                lock_type = "exclusive" if self.exclusive else "shared"
                self.report({'INFO'}, f"Locked {Path(self.file_path).name} ({lock_type})")
                return {'FINISHED'}
            else:
                error_text = error_msg or "Failed to lock file. File may be already locked."
                self.report({'ERROR'}, error_text)
                return {'CANCELLED'}
        except Exception as e:
            logger.error(f"Error locking file: {e}", exc_info=True)
            self.report({'ERROR'}, f"Error locking file: {str(e)}")
            return {'CANCELLED'}


class DF_OT_unlock_file(Operator):
    """Unlock a file."""
    bl_idname = "df.unlock_file"
    bl_label = "Unlock File"
    bl_description = "Unlock a file"
    bl_options = {'REGISTER', 'UNDO'}

    file_path: bpy.props.StringProperty(
        name="File Path",
        description="Path to file to unlock",
        default=""
    )

    def execute(self, context):
        repo_path, error = get_repository_path()
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        if not self.file_path:
            self.report({'ERROR'}, "File path required")
            return {'CANCELLED'}
        
        try:
            cli = get_cli()
            success, error_msg = cli.unlock_file(repo_path, self.file_path)
            
            if success:
                self.report({'INFO'}, f"Unlocked {Path(self.file_path).name}")
                return {'FINISHED'}
            else:
                error_text = error_msg or "Failed to unlock file"
                self.report({'ERROR'}, error_text)
                return {'CANCELLED'}
        except Exception as e:
            logger.error(f"Error unlocking file: {e}", exc_info=True)
            self.report({'ERROR'}, f"Error unlocking file: {str(e)}")
            return {'CANCELLED'}


class DF_OT_lock_current_blend(Operator):
    """Lock current .blend file and all textures."""
    bl_idname = "df.lock_current_blend"
    bl_label = "Lock Files"
    bl_description = "Lock the current .blend file and all textures used in materials"
    bl_options = {'REGISTER', 'UNDO'}

    exclusive: bpy.props.BoolProperty(
        name="Exclusive",
        description="Exclusive lock",
        default=True
    )
    
    expire_hours: bpy.props.IntProperty(
        name="Expire Hours",
        description="Lock expiration time in hours (0 = never expires)",
        default=0,
        min=0
    )

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Please save the file first")
            return {'CANCELLED'}
        
        repo_path, error = get_repository_path()
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        cli = get_cli()
        locked_files = []
        failed_files = []
        
        # 1. Блокируем текущий .blend файл
        blend_path = Path(bpy.data.filepath).resolve()
        repo_path_resolved = repo_path.resolve()
        try:
            file_path = blend_path.relative_to(repo_path_resolved)
            file_path_str = file_path.as_posix()
        except ValueError:
            file_path_str = blend_path.name
        
        success, error_msg = cli.lock_file(
            repo_path,
            file_path_str,
            exclusive=self.exclusive,
            expire_hours=self.expire_hours if self.expire_hours > 0 else None
        )
        
        if success:
            locked_files.append(blend_path.name)
        else:
            failed_files.append(f"{blend_path.name}: {error_msg or 'Already locked'}")
        
        # 2. Блокируем все текстуры
        texture_files = []
        for image in bpy.data.images:
            if image.packed_file:
                continue  # Пропускаем упакованные текстуры
            
            if image.filepath:
                try:
                    abs_path = Path(bpy.path.abspath(image.filepath))
                    if abs_path.exists() and abs_path.is_file():
                        texture_files.append(abs_path)
                except Exception as e:
                    logger.debug(f"Failed to resolve texture path {image.filepath}: {e}")
        
        for texture_path in texture_files:
            try:
                try:
                    file_path = texture_path.relative_to(repo_path_resolved)
                    file_path_str = file_path.as_posix()
                except ValueError:
                    file_path_str = texture_path.name
                
                success, error_msg = cli.lock_file(
                    repo_path,
                    file_path_str,
                    exclusive=self.exclusive,
                    expire_hours=self.expire_hours if self.expire_hours > 0 else None
                )
                
                if success:
                    locked_files.append(texture_path.name)
                else:
                    failed_files.append(f"{texture_path.name}: {error_msg or 'Already locked'}")
            except Exception as e:
                failed_files.append(f"{texture_path.name}: {str(e)}")
                logger.error(f"Error locking texture {texture_path}: {e}", exc_info=True)
        
        # Формируем отчет
        lock_type = "exclusive" if self.exclusive else "shared"
        if locked_files:
            msg = f"Locked {len(locked_files)} file(s) ({lock_type})"
            if failed_files:
                msg += f", {len(failed_files)} failed"
            self.report({'INFO'}, msg)
        elif failed_files:
            self.report({'WARNING'}, f"Failed to lock files: {failed_files[0]}")
        else:
            self.report({'INFO'}, "No files to lock")
        
        return {'FINISHED'}


class DF_OT_unlock_current_blend(Operator):
    """Unlock current .blend file and all textures."""
    bl_idname = "df.unlock_current_blend"
    bl_label = "Unlock Files"
    bl_description = "Unlock the current .blend file and all textures used in materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not bpy.data.filepath:
            self.report({'ERROR'}, "Please save the file first")
            return {'CANCELLED'}
        
        repo_path, error = get_repository_path()
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        cli = get_cli()
        unlocked_files = []
        failed_files = []
        
        # 1. Разблокируем текущий .blend файл
        blend_path = Path(bpy.data.filepath).resolve()
        repo_path_resolved = repo_path.resolve()
        try:
            file_path = blend_path.relative_to(repo_path_resolved)
            file_path_str = file_path.as_posix()
        except ValueError:
            file_path_str = blend_path.name
        
        success, error_msg = cli.unlock_file(repo_path, file_path_str)
        if success:
            unlocked_files.append(blend_path.name)
        else:
            failed_files.append(f"{blend_path.name}: {error_msg or 'Not locked'}")
        
        # 2. Разблокируем все текстуры
        texture_files = []
        for image in bpy.data.images:
            if image.packed_file:
                continue  # Пропускаем упакованные текстуры
            
            if image.filepath:
                try:
                    abs_path = Path(bpy.path.abspath(image.filepath))
                    if abs_path.exists() and abs_path.is_file():
                        texture_files.append(abs_path)
                except Exception as e:
                    logger.debug(f"Failed to resolve texture path {image.filepath}: {e}")
        
        for texture_path in texture_files:
            try:
                try:
                    file_path = texture_path.relative_to(repo_path_resolved)
                    file_path_str = file_path.as_posix()
                except ValueError:
                    file_path_str = texture_path.name
                
                success, error_msg = cli.unlock_file(repo_path, file_path_str)
                if success:
                    unlocked_files.append(texture_path.name)
                else:
                    # Не считаем ошибкой, если файл не был заблокирован
                    if error_msg and "not locked" not in error_msg.lower():
                        failed_files.append(f"{texture_path.name}: {error_msg}")
            except Exception as e:
                failed_files.append(f"{texture_path.name}: {str(e)}")
                logger.error(f"Error unlocking texture {texture_path}: {e}", exc_info=True)
        
        # Формируем отчет
        if unlocked_files:
            msg = f"Unlocked {len(unlocked_files)} file(s)"
            if failed_files:
                msg += f", {len(failed_files)} failed"
            self.report({'INFO'}, msg)
        elif failed_files:
            self.report({'WARNING'}, f"Failed to unlock files: {failed_files[0]}")
        else:
            self.report({'INFO'}, "No files to unlock")
        
        return {'FINISHED'}


class DF_OT_lock_current_textures(Operator):
    """Lock all textures used in current file."""
    bl_idname = "df.lock_current_textures"
    bl_label = "Lock All Textures"
    bl_description = "Lock all textures used in materials of current file"
    bl_options = {'REGISTER', 'UNDO'}

    exclusive: bpy.props.BoolProperty(
        name="Exclusive",
        description="Exclusive lock",
        default=True
    )
    
    expire_hours: bpy.props.IntProperty(
        name="Expire Hours",
        description="Lock expiration time in hours (0 = never expires)",
        default=0,
        min=0
    )

    def execute(self, context):
        repo_path, error = get_repository_path()
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        # Получаем список всех текстур
        texture_files = []
        for image in bpy.data.images:
            if image.packed_file:
                continue  # Пропускаем упакованные текстуры
            
            if image.filepath:
                try:
                    abs_path = Path(bpy.path.abspath(image.filepath))
                    if abs_path.exists() and abs_path.is_file():
                        texture_files.append(abs_path)
                except Exception as e:
                    logger.debug(f"Failed to resolve texture path {image.filepath}: {e}")
        
        if not texture_files:
            self.report({'INFO'}, "No external textures found")
            return {'FINISHED'}
        
        # Блокируем каждую текстуру
        cli = get_cli()
        locked_count = 0
        failed_count = 0
        
        for texture_path in texture_files:
            try:
                # Получаем относительный путь от корня репозитория
                repo_path_resolved = repo_path.resolve()
                try:
                    file_path = texture_path.relative_to(repo_path_resolved)
                    file_path_str = file_path.as_posix()
                except ValueError:
                    # Если текстура вне репозитория, используем имя файла
                    file_path_str = texture_path.name
                
                success, error_msg = cli.lock_file(
                    repo_path,
                    file_path_str,
                    exclusive=self.exclusive,
                    expire_hours=self.expire_hours if self.expire_hours > 0 else None
                )
                
                if success:
                    locked_count += 1
                else:
                    failed_count += 1
                    logger.debug(f"Failed to lock {texture_path.name}: {error_msg}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Error locking texture {texture_path}: {e}", exc_info=True)
        
        if locked_count > 0:
            lock_type = "exclusive" if self.exclusive else "shared"
            self.report({'INFO'}, f"Locked {locked_count} texture(s) ({lock_type})")
        if failed_count > 0:
            self.report({'WARNING'}, f"Failed to lock {failed_count} texture(s)")
        
        return {'FINISHED'}


class DF_OT_list_locks(Operator):
    """List all file locks in repository."""
    bl_idname = "df.list_locks"
    bl_label = "List Locks"
    bl_description = "List all file locks in current branch"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        repo_path, error = get_repository_path()
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        
        try:
            cli = get_cli()
            success, locks, error_msg = cli.list_locks(repo_path)
            
            if not success:
                error_text = error_msg or "Failed to list locks"
                self.report({'ERROR'}, error_text)
                return {'CANCELLED'}
            
            if not locks:
                self.report({'INFO'}, "No locks found")
                return {'FINISHED'}
            
            # Формируем сообщение
            lock_list = []
            for lock in locks:
                file_path = lock.get('file_path', 'Unknown')
                lock_type = lock.get('lock_type', 'exclusive')
                user = lock.get('user', 'Unknown')
                expires_at = lock.get('expires_at')
                
                lock_msg = f"{file_path} ({lock_type}) by {user}"
                if expires_at:
                    from datetime import datetime
                    try:
                        exp_dt = datetime.fromtimestamp(expires_at)
                        lock_msg += f" expires: {exp_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                    except:
                        pass
                
                lock_list.append(lock_msg)
            
            message = f"Found {len(locks)} lock(s):\n" + "\n".join(lock_list)
            self.report({'INFO'}, message)
            
            return {'FINISHED'}
        except Exception as e:
            logger.error(f"Error listing locks: {e}", exc_info=True)
            self.report({'ERROR'}, f"Error listing locks: {str(e)}")
            return {'CANCELLED'}


# Регистрация классов
classes = [
    DF_OT_check_locks,
    DF_OT_lock_file,
    DF_OT_unlock_file,
    DF_OT_lock_current_blend,
    DF_OT_unlock_current_blend,
    DF_OT_lock_current_textures,
    DF_OT_list_locks,
]


def register():
    """Register lock operators."""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister lock operators."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

