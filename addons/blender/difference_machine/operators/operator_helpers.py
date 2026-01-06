"""
Helper functions for operators to reduce code duplication.
"""

import bpy
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, Set

# Constants
GC_SCHEDULE_WINDOW_SECONDS: int = 300  # 5 minutes window for scheduled GC execution
SECONDS_PER_DAY: int = 86400  # Number of seconds in a day

# Forester Python bindings are optional; fall back to CLI when unavailable.
try:
    from ..forester.commands import find_repository, list_branches, init_repository
    from ..forester.core.refs import get_branch_ref, get_current_branch
    from ..forester.core.database import ForesterDB
    _FORESTER_BINDINGS_AVAILABLE = True
except ImportError:
    find_repository = None
    list_branches = None
    init_repository = None
    get_branch_ref = None
    get_current_branch = None
    ForesterDB = None
    _FORESTER_BINDINGS_AVAILABLE = False

logger = logging.getLogger(__name__)


def get_addon_preferences(context):
    """Get addon preferences with fallback to default values."""
    # Import from utils.helpers to avoid duplication
    from ..utils.helpers import get_addon_preferences as _get_addon_preferences
    return _get_addon_preferences(context)


def cleanup_old_preview_temp(repo_path: Path, keep_current: Optional[str] = None) -> None:
    """
    Clean up old preview_temp directories, optionally keeping a specific one.
    
    Args:
        repo_path: Path to repository root
        keep_current: Optional path to current preview directory to keep (as string)
    """
    import shutil
    
    dfm_dir = repo_path / ".DFM"
    if not dfm_dir.exists():
        return
    
    temp_dir = dfm_dir / "preview_temp"
    if not temp_dir.exists():
        return
    
    try:
        # Get current directory path as Path if provided
        keep_path = None
        if keep_current:
            keep_path = Path(keep_current)
            if not keep_path.exists():
                keep_path = None  # If path doesn't exist, don't try to keep it
        
        # Find all commit directories in preview_temp
        removed_count = 0
        total_size = 0
        
        for item in temp_dir.iterdir():
            if not item.is_dir():
                continue
            
            # Skip if this is the current preview directory
            if keep_path and item.resolve() == keep_path.resolve():
                continue
            
            # Remove old preview directory
            try:
                # Calculate size before removal
                size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                shutil.rmtree(item)
                removed_count += 1
                total_size += size
                logger.debug(f"Removed old preview_temp directory: {item.name} ({size / (1024*1024):.1f} MB)")
            except Exception as e:
                logger.warning(f"Failed to remove preview_temp directory {item.name}: {e}")
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old preview_temp directories ({total_size / (1024*1024):.1f} MB freed)")
    
    except Exception as e:
        logger.warning(f"Failed to clean up preview_temp directories: {e}", exc_info=True)


def cleanup_old_compare_temp(repo_path: Path, keep_current: Optional[str] = None) -> None:
    """
    Clean up old compare_temp directories, optionally keeping a specific one.

    This prevents accumulation of stale compare commits under .DFM/compare_temp.

    Args:
        repo_path: Path to repository root
        keep_current: Optional path to current compare directory to keep (as string)
    """
    import shutil

    dfm_dir = repo_path / ".DFM"
    if not dfm_dir.exists():
        return

    temp_dir = dfm_dir / "compare_temp"
    if not temp_dir.exists():
        return

    try:
        keep_path = None
        if keep_current:
            keep_path = Path(keep_current)
            if not keep_path.exists():
                keep_path = None

        removed_count = 0
        total_size = 0

        for item in temp_dir.iterdir():
            if not item.is_dir():
                continue

            if keep_path and item.resolve() == keep_path.resolve():
                continue

            try:
                size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                shutil.rmtree(item)
                removed_count += 1
                total_size += size
                logger.debug(
                    f"Removed old compare_temp directory: {item.name} ({size / (1024 * 1024):.1f} MB)"
                )
            except Exception as e:
                logger.warning(f"Failed to remove compare_temp directory {item.name}: {e}")

        if removed_count > 0:
            logger.info(
                f"Cleaned up {removed_count} old compare_temp directories "
                f"({total_size / (1024 * 1024):.1f} MB freed)"
            )
    except Exception as e:
        logger.warning("Failed to clean up compare_temp directories: %s", e, exc_info=True)


def copy_project_textures_for_compare(source_root: Path, compare_root: Path) -> None:
    """
    Copy texture files from project root to compare_temp for project comparison.

    This ensures that when .blend is opened from compare_temp, image textures
    that lived alongside the original .blend (or in its subfolders) are available.

    Args:
        source_root: Original project root (typically the directory with the .blend file)
        compare_root: Root of compare_temp for this commit (compare_temp/commit_xxx)
    """
    import shutil

    if not source_root.exists():
        return

    # Common image extensions used for textures
    texture_extensions: Set[str] = {
        ".png",
        ".jpg",
        ".jpeg",
        ".tga",
        ".tif",
        ".tiff",
        ".bmp",
        ".exr",
        ".hdr",
        ".dds",
        ".webp",
    }

    for path in source_root.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in texture_extensions:
            continue

        try:
            rel_path = path.relative_to(source_root)
        except ValueError:
            # Should not happen, but be safe
            rel_path = path.name

        dest_path = compare_root / rel_path
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            if not dest_path.exists():
                shutil.copy2(path, dest_path)
                logger.debug(f"Copied project texture for compare: {path} -> {dest_path}")
        except Exception as e:
            logger.warning(f"Failed to copy project texture {path}: {e}", exc_info=True)


def check_and_run_garbage_collect(context, repo_path: Path) -> None:
    """
    Check if scheduled garbage collection should run and execute it if needed.
    
    Args:
        context: Blender context
        repo_path: Path to repository root
    """
    try:
        prefs = get_addon_preferences(context)
        
        if not getattr(prefs, 'gc_schedule_enabled', False):
            return
        
        import time
        from datetime import datetime, timedelta
        
        current_time = time.time()
        last_run = getattr(prefs, 'gc_last_run', 0.0)
        
        # Get schedule settings
        schedule_hour = getattr(prefs, 'gc_schedule_hour', 2)
        schedule_minute = getattr(prefs, 'gc_schedule_minute', 0)
        interval_days = getattr(prefs, 'gc_schedule_interval_days', 7)
        
        # Calculate next scheduled time
        now = datetime.now()
        scheduled_time = now.replace(hour=schedule_hour, minute=schedule_minute, second=0, microsecond=0)
        
        # If scheduled time has passed today, move to next interval
        if scheduled_time < now:
            scheduled_time += timedelta(days=interval_days)
        
        scheduled_timestamp = scheduled_time.timestamp()
        
        # Check if we should run now (within GC_SCHEDULE_WINDOW_SECONDS of scheduled time)
        time_diff = abs(current_time - scheduled_timestamp)
        interval_seconds = interval_days * SECONDS_PER_DAY
        
        # Run if:
        # 1. Never run before, OR
        # 2. Last run was more than interval_days ago, OR
        # 3. We're within GC_SCHEDULE_WINDOW_SECONDS of scheduled time and haven't run today
        should_run = False
        if last_run == 0.0:
            # First run - check if we're past scheduled time today
            if current_time >= scheduled_timestamp:
                should_run = True
        elif (current_time - last_run) >= interval_seconds:
            # Enough time has passed since last run
            should_run = True
        elif time_diff <= GC_SCHEDULE_WINDOW_SECONDS:
            # We're near scheduled time and haven't run today
            last_run_date = datetime.fromtimestamp(last_run).date()
            if now.date() > last_run_date:
                should_run = True
        
        if should_run:
            # Run garbage collection using CLI
            from ..utils.forester_cli import get_cli
            
            logger.info("Running scheduled garbage collection...")
            cli = get_cli()
            # Используем настройку периода хранения reflog из preferences
            reflog_expire_days = getattr(prefs, 'reflog_expire_days', 90)
            success, stats, error = cli.gc(repo_path, dry_run=False, reflog_expire_days=reflog_expire_days)
            
            if success and stats:
                # Update last run time
                prefs.gc_last_run = current_time
                logger.info(f"Garbage collection completed: {stats.get('commits_deleted', 0)} commits, "
                          f"{stats.get('trees_deleted', 0)} trees, {stats.get('blobs_deleted', 0)} blobs deleted")
            else:
                error_msg = error if error else "Unknown error"
                logger.warning(f"Garbage collection failed: {error_msg}")
    except Exception as e:
        logger.error(f"Error in scheduled garbage collection: {e}", exc_info=True)


def get_repository_path(operator=None) -> Tuple[Optional[Path], Optional[str]]:
    """
    Get repository path from current Blender file.
    
    Args:
        operator: Optional operator instance for error reporting
        
    Returns:
        Tuple of (repo_path, error_message)
        If successful: (Path, None)
        If error: (None, error_message)
    """
    if not bpy.data.filepath:
        error_msg = "Please save the Blender file first"
        if operator:
            operator.report({'ERROR'}, error_msg)
        return None, error_msg
    
    blend_file = Path(bpy.data.filepath)

    # Prefer bindings if available, otherwise use filesystem heuristic
    repo_path = None
    if _FORESTER_BINDINGS_AVAILABLE and find_repository:
        repo_path = find_repository(blend_file.parent)
    if not repo_path:
        from ..utils.helpers import find_repository_root
        repo_path = find_repository_root(blend_file.parent)
    if not repo_path:
        error_msg = "Not a Forester repository"
        if operator:
            operator.report({'ERROR'}, error_msg)
        return None, error_msg
    
    return repo_path, None


# Re-export get_repository_path from utils.helpers for backward compatibility
# This avoids duplication while maintaining the operator-specific error reporting
def get_repository_path_simple() -> Tuple[Optional[Path], Optional[str]]:
    """Simple version without operator error reporting."""
    from ..utils.helpers import get_repository_path as _get_repository_path
    return _get_repository_path()


def is_repository_initialized(context) -> bool:
    """
    Check if repository is initialized (has .DFM folder and database).
    
    Args:
        context: Blender context
        
    Returns:
        True if .DFM folder and forester.db exist, False otherwise
    """
    if not bpy.data.filepath:
        return False
    
    blend_file = Path(bpy.data.filepath)
    project_root = blend_file.parent
    dfm_dir = project_root / ".DFM"
    db_path = dfm_dir / "forester.db"
    
    return dfm_dir.exists() and db_path.exists()


def check_repository_state(context) -> Tuple[bool, bool, bool, Optional[str]]:
    """
    Check repository state: file saved, repository exists, branches exist.
    
    Args:
        context: Blender context
        
    Returns:
        Tuple of (file_saved, repo_exists, has_branches, error_message)
    """
    # Check if file is saved
    if not bpy.data.filepath:
        return (False, False, False, "Please save the Blender file first")
    
    blend_file = Path(bpy.data.filepath)
    
    # Check if repository exists
    project_root = blend_file.parent
    repo_path = None
    if _FORESTER_BINDINGS_AVAILABLE and find_repository:
        repo_path = find_repository(project_root)
    if not repo_path:
        from ..utils.helpers import find_repository_root
        repo_path = find_repository_root(project_root)
    if not repo_path:
        # Check if .DFM directory exists
        dfm_dir = project_root / ".DFM"
        if not dfm_dir.exists():
            return (True, False, False, "Repository not initialized. Please create a project folder and save the Blender file in it.")
        return (True, False, False, "Repository not found")
    
    # Check if branches exist
    try:
        if _FORESTER_BINDINGS_AVAILABLE and list_branches:
            branches = list_branches(repo_path)
            has_branches = len(branches) > 0
            return (True, True, has_branches, None if has_branches else "No branches found. Please create a branch first.")
        else:
            from ..utils.forester_cli import get_cli
            cli = get_cli()
            success, branches, error = cli.branch(repo_path, action="list")
            if not success:
                return (True, True, False, f"Error checking branches: {error}")
            has_branches = len(branches) > 0
            return (True, True, has_branches, None if has_branches else "No branches found. Please create a branch first.")
    except Exception as e:
        return (True, True, False, f"Error checking branches: {str(e)}")


def get_active_mesh_object(operator=None) -> Tuple[Optional[bpy.types.Object], Optional[str]]:
    """
    Get active mesh object from context.
    
    Args:
        operator: Optional operator instance for error reporting
        
    Returns:
        Tuple of (mesh_object, error_message)
        If successful: (Object, None)
        If error: (None, error_message)
    """
    active_obj = bpy.context.active_object
    if not active_obj or active_obj.type != 'MESH':
        error_msg = "Please select a mesh object"
        if operator:
            operator.report({'ERROR'}, error_msg)
        return None, error_msg
    
    return active_obj, None


def process_meshes_sequentially(selected_objects, process_func, *args, **kwargs):
    """
    Process multiple meshes sequentially using a single-mesh processing function.
    
    Args:
        selected_objects: List of mesh objects to process
        process_func: Function that processes a single mesh object
                     Should accept (obj, *args, **kwargs) and return (success, result)
        *args, **kwargs: Additional arguments to pass to process_func
        
    Returns:
        List of results for successfully processed meshes
    """
    results = []
    for obj in selected_objects:
        try:
            success, result = process_func(obj, *args, **kwargs)
            if success:
                results.append(result)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to process {obj.name}: {e}")
            continue
    return results


def ensure_repository_and_branch(context, operator) -> Tuple[Optional[Path], Optional[str]]:
    """
    Ensure repository exists and branch is ready for commit operations.
    
    Args:
        context: Blender context
        operator: Operator instance for error reporting
        
    Returns:
        Tuple of (repo_path, error_message)
        If successful: (Path, None)
        If error: (None, error_message)
    """
    # Check if file is saved
    if not bpy.data.filepath:
        error_msg = "Please save the Blender file first"
        operator.report({'ERROR'}, error_msg)
        return None, error_msg
    
    blend_file = Path(bpy.data.filepath)
    project_root = blend_file.parent
    
    # Check if repository exists
    repo_path = None
    if _FORESTER_BINDINGS_AVAILABLE and find_repository:
        repo_path = find_repository(project_root)
    if not repo_path:
        from ..utils.helpers import find_repository_root
        repo_path = find_repository_root(project_root)

    if not repo_path:
        # Initialize repository via CLI
        try:
            from ..utils.forester_cli import get_cli
            cli = get_cli()
            success, error_msg = cli.init(project_root)
            if not success:
                operator.report({'ERROR'}, f"Failed to initialize repository: {error_msg}")
                return None, error_msg
            repo_path = project_root
            operator.report({'INFO'}, "Repository initialized")
        except Exception as e:
            error_msg = f"Failed to initialize repository: {str(e)}"
            operator.report({'ERROR'}, error_msg)
            logger.error(f"Unexpected error initializing repository: {e}", exc_info=True)
            return None, error_msg
    
    # Check if branches exist
    try:
        from ..utils.forester_cli import get_cli
        cli = get_cli()
        success, branches, error_msg = cli.branch(repo_path, action="list")
        if not success:
            error = error_msg or "Failed to list branches"
            operator.report({'ERROR'}, error)
            return None, error
        if len(branches) == 0:
            error_msg = (
                "No branches found. Please create a branch first.\n"
                "Go to Branch Management panel and click 'Create New Branch'."
            )
            operator.report({'ERROR'}, error_msg)
            return None, error_msg

        # Ensure current branch exists
        current = next((b for b in branches if b.get("is_current")), None)
        branch_name = current["name"] if current else branches[0]["name"]
    except Exception as e:
        error_msg = f"Error checking branches: {str(e)}"
        operator.report({'ERROR'}, error_msg)
        logger.error(f"Error checking branches: {e}", exc_info=True)
        return None, error_msg
    
    return repo_path, None


def validate_branch_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate branch name according to git-like rules.
    
    Args:
        name: Branch name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
        If valid: (True, None)
        If invalid: (False, error_message)
    """
    if name is None:
        return False, "Branch name cannot be None"
    if not name or not name.strip():
        return False, "Branch name cannot be empty"
    
    name = name.strip()
    
    # Constants for branch name validation
    MAX_BRANCH_NAME_LENGTH: int = 255  # Maximum branch name length (git limit)
    FORBIDDEN_BRANCH_PATTERNS: Set[str] = {'..', '~', '^', ':', '?', '*', '[', '\\'}
    
    if len(name) > MAX_BRANCH_NAME_LENGTH:
        return False, f"Branch name too long (max {MAX_BRANCH_NAME_LENGTH} characters)"
    
    # Check for forbidden patterns (git-like branch name rules)
    for pattern in FORBIDDEN_BRANCH_PATTERNS:
        if pattern in name:
            return False, f"Branch name cannot contain '{pattern}'"
    
    # Check for leading/trailing dots or spaces
    if name.startswith('.') or name.endswith('.'):
        return False, "Branch name cannot start or end with '.'"
    
    if name.startswith(' ') or name.endswith(' '):
        return False, "Branch name cannot start or end with space"
    
    # Check for control characters
    if any(ord(c) < 32 for c in name):
        return False, "Branch name cannot contain control characters"
    
    return True, None

