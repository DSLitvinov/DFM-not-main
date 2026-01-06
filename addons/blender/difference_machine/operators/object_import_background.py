"""
Background script for importing objects from .blend files in commits.
Runs in separate Blender process to avoid affecting current scene.

This script is called via subprocess from history_operators.py to import objects
from commit files without modifying the user's current project.
"""
import bpy
import sys
import argparse
from pathlib import Path


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Import object from .blend file in background')
    
    parser.add_argument('--source_blend', required=True,
                       help='Path to source .blend file (from tmp_review)')
    parser.add_argument('--obj_name', required=True,
                       help='Name of object to import')
    parser.add_argument('--obj_type', required=True,
                       help='Type of object (MESH, LIGHT, CAMERA, ARMATURE, etc.)')
    parser.add_argument('--output_file', required=True,
                       help='Path to temporary output .blend file with object')
    
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:])


def import_object_from_commit(args):
    """
    Import object from commit's .blend file and save to temporary file.
    
    Args:
        args: Parsed command line arguments
    """
    source_path = Path(args.source_blend)
    if not source_path.exists():
        raise FileNotFoundError(f"Source blend file not found: {source_path}")
    
    # Open source .blend file
    bpy.ops.wm.open_mainfile(filepath=str(source_path))
    
    # Find object by name
    obj = None
    if args.obj_name in bpy.data.objects:
        obj = bpy.data.objects[args.obj_name]
        # Verify type
        if obj.type != args.obj_type:
            raise ValueError(
                f"Object '{args.obj_name}' has type {obj.type}, expected {args.obj_type}"
            )
    else:
        # Try to find by partial name match
        for obj_name in bpy.data.objects.keys():
            if (obj_name == args.obj_name or 
                obj_name.lower() == args.obj_name.lower() or
                args.obj_name in obj_name or
                obj_name in args.obj_name):
                candidate = bpy.data.objects[obj_name]
                if candidate.type == args.obj_type:
                    obj = candidate
                    break
        
        if not obj:
            raise ValueError(
                f"Object '{args.obj_name}' (type: {args.obj_type}) not found in {source_path}"
            )
    
    # CRITICAL: Remove all other objects to ensure only the target object is saved
    # This prevents importing wrong objects (like Light, Camera, etc.)
    obj_name_to_keep = obj.name
    objects_to_remove = []
    for o in bpy.data.objects:
        if o.name != obj_name_to_keep:
            objects_to_remove.append(o)
    
    # Remove all other objects
    for o in objects_to_remove:
        # Unlink from all collections
        for collection in o.users_collection:
            collection.objects.unlink(o)
        # Remove object
        bpy.data.objects.remove(o)
    
    # Deselect all objects
    bpy.ops.object.select_all(action='DESELECT')
    
    # Select only the target object
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    # Make sure object is in a collection
    if not obj.users_collection:
        bpy.context.collection.objects.link(obj)
    
    # Save to temporary file (now contains only the target object)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    bpy.ops.wm.save_as_mainfile(
        filepath=str(output_path),
        check_existing=False
    )
    
    # Note: This is a background script, print is acceptable for console output
    # but we log for consistency with the rest of the codebase
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info(f"Successfully exported object '{obj.name}' to {output_path}")
    print(f"Successfully exported object '{obj.name}' to {output_path}")  # Keep for console visibility


if __name__ == "__main__":
    try:
        args = parse_args()
        import_object_from_commit(args)
    except Exception as e:
        import logging
        import traceback
        logging.basicConfig(level=logging.ERROR)
        logger = logging.getLogger(__name__)
        logger.error(f"Error in background import: {e}", exc_info=True)
        print(f"Error in background import: {e}", file=sys.stderr)  # Keep for console visibility
        traceback.print_exc()
        sys.exit(1)






