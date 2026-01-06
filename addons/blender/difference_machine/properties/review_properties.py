"""
Review properties for Difference Machine add-on.
"""

import bpy
from bpy.props import StringProperty, IntProperty, FloatProperty, BoolProperty, CollectionProperty


class DFCommentItem(bpy.types.PropertyGroup):
    """Property group for comment item."""
    comment_id: IntProperty(name="Comment ID")
    asset_hash: StringProperty(name="Asset Hash")
    asset_type: StringProperty(name="Asset Type")
    author: StringProperty(name="Author")
    text: StringProperty(name="Text")
    created_at: IntProperty(name="Created At")
    x: FloatProperty(name="X")
    y: FloatProperty(name="Y")
    resolved: BoolProperty(name="Resolved", default=False)


class DFApprovalItem(bpy.types.PropertyGroup):
    """Property group for approval item."""
    asset_hash: StringProperty(name="Asset Hash")
    asset_type: StringProperty(name="Asset Type")
    status: StringProperty(name="Status")  # 'approved', 'rejected', 'pending'
    approver: StringProperty(name="Approver")
    comment: StringProperty(name="Comment")
    created_at: IntProperty(name="Created At")


def register_review_properties():
    """Register review properties."""
    if not hasattr(bpy.types.Scene, 'df_comments'):
        bpy.types.Scene.df_comments = CollectionProperty(type=DFCommentItem)
        bpy.types.Scene.df_approvals = CollectionProperty(type=DFApprovalItem)
        bpy.types.Scene.df_review_asset_hash = StringProperty(name="Review Asset Hash", default="")
        bpy.types.Scene.df_review_asset_type = StringProperty(name="Review Asset Type", default="")


def register():
    """Register review property classes."""
    bpy.utils.register_class(DFCommentItem)
    bpy.utils.register_class(DFApprovalItem)
    register_review_properties()


def unregister():
    """Unregister review property classes."""
    if hasattr(bpy.types.Scene, 'df_comments'):
        del bpy.types.Scene.df_comments
        del bpy.types.Scene.df_approvals
        del bpy.types.Scene.df_review_asset_hash
        del bpy.types.Scene.df_review_asset_type
    
    bpy.utils.unregister_class(DFCommentItem)
    bpy.utils.unregister_class(DFApprovalItem)

