"""
Example operator for Difference Machine add-on.
"""

import bpy
from bpy.props import StringProperty
from bpy.types import Operator


class EXAMPLE_OT_operator_name(Operator):
    """Example operator description."""
    bl_idname = "example.operator_name"
    bl_label = "Example Operator"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        """Execute the operator."""
        self.report({'INFO'}, "Example operator executed")
        return {'FINISHED'}


def register():
    """Register operators."""
    bpy.utils.register_class(EXAMPLE_OT_operator_name)


def unregister():
    """Unregister operators."""
    bpy.utils.unregister_class(EXAMPLE_OT_operator_name)

