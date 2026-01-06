"""
Review tools operators for Difference Machine add-on.
"""

import bpy
import logging
from bpy.props import StringProperty, FloatProperty, IntProperty
from bpy.types import Operator
from pathlib import Path
from ..operators.operator_helpers import get_repository_path

# Forester Python bindings are optional; if unavailable, disable review ops gracefully.
try:
    from ..forester.commands.review import (
        add_comment,
        get_comments,
        resolve_comment,
        delete_comment,
        set_approval,
        get_approval,
        get_all_approvals,
    )
    _REVIEW_AVAILABLE = True
except ImportError:
    _REVIEW_AVAILABLE = False

    def _review_unavailable(*_args, **_kwargs):
        raise RuntimeError("Forester Python bindings not found; review features are disabled.")

    add_comment = _review_unavailable
    get_comments = _review_unavailable
    resolve_comment = _review_unavailable
    delete_comment = _review_unavailable
    set_approval = _review_unavailable
    get_approval = _review_unavailable
    get_all_approvals = _review_unavailable

logger = logging.getLogger(__name__)


class DF_OT_add_comment(Operator):
    """Add comment to commit/mesh/blob."""
    bl_idname = "df.add_comment"
    bl_label = "Add Comment"
    bl_description = "Add a comment to the selected asset"
    bl_options = {'REGISTER'}

    asset_hash: StringProperty(name="Asset Hash")
    asset_type: StringProperty(name="Asset Type")  # 'commit', 'mesh', 'blob'
    comment_text: StringProperty(name="Comment", description="Comment text")
    x: FloatProperty(name="X", default=0.0, description="X coordinate for annotation")
    y: FloatProperty(name="Y", default=0.0, description="Y coordinate for annotation")

    def invoke(self, context, event):
        """Show text input dialog."""
        return context.window_manager.invoke_props_dialog(self, width=400)

    def execute(self, context):
        """Add comment."""
        if not _REVIEW_AVAILABLE:
            self.report({'ERROR'}, "Review features unavailable: Forester Python bindings not found.")
            return {'CANCELLED'}
        if not self.comment_text.strip():
            self.report({'ERROR'}, "Comment text cannot be empty")
            return {'CANCELLED'}

        repo_path, error = get_repository_path(self)
        if not repo_path:
            return {'CANCELLED'}

        # Get author from addon preferences or use default
        from ..operators.operator_helpers import get_addon_preferences
        prefs = get_addon_preferences(context)
        author = (
            getattr(prefs, "default_author", None)
            or getattr(prefs, "author_name", None)
            or "Unknown"
        )

        try:
            comment_id = add_comment(
                repo_path,
                self.asset_hash,
                self.asset_type,
                author,
                self.comment_text.strip(),
                self.x if self.x != 0.0 else None,
                self.y if self.y != 0.0 else None
            )
            self.report({'INFO'}, f"Comment added (ID: {comment_id})")
            
            # Refresh comments in UI
            bpy.ops.df.refresh_comments(asset_hash=self.asset_hash, asset_type=self.asset_type)
            
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to add comment: {str(e)}")
            logger.error(f"Failed to add comment: {e}", exc_info=True)
            return {'CANCELLED'}


class DF_OT_resolve_comment(Operator):
    """Mark comment as resolved."""
    bl_idname = "df.resolve_comment"
    bl_label = "Resolve Comment"
    bl_description = "Mark comment as resolved"
    bl_options = {'REGISTER'}

    comment_id: IntProperty(name="Comment ID")

    def execute(self, context):
        """Resolve comment."""
        if not _REVIEW_AVAILABLE:
            self.report({'ERROR'}, "Review features unavailable: Forester Python bindings not found.")
            return {'CANCELLED'}
        repo_path, error = get_repository_path(self)
        if not repo_path:
            return {'CANCELLED'}

        try:
            if resolve_comment(repo_path, self.comment_id):
                self.report({'INFO'}, "Comment resolved")
                # Refresh comments
                asset_hash = getattr(context.scene, 'df_review_asset_hash', '')
                asset_type = getattr(context.scene, 'df_review_asset_type', '')
                if asset_hash and asset_type:
                    bpy.ops.df.refresh_comments(asset_hash=asset_hash, asset_type=asset_type)
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Failed to resolve comment")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to resolve comment: {str(e)}")
            logger.error(f"Failed to resolve comment: {e}", exc_info=True)
            return {'CANCELLED'}


class DF_OT_delete_comment(Operator):
    """Delete comment."""
    bl_idname = "df.delete_comment"
    bl_label = "Delete Comment"
    bl_description = "Delete a comment"
    bl_options = {'REGISTER'}

    comment_id: IntProperty(name="Comment ID")

    def invoke(self, context, event):
        """Show confirmation dialog."""
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        """Delete comment."""
        if not _REVIEW_AVAILABLE:
            self.report({'ERROR'}, "Review features unavailable: Forester Python bindings not found.")
            return {'CANCELLED'}
        repo_path, error = get_repository_path(self)
        if not repo_path:
            return {'CANCELLED'}

        try:
            if delete_comment(repo_path, self.comment_id):
                self.report({'INFO'}, "Comment deleted")
                # Refresh comments
                asset_hash = getattr(context.scene, 'df_review_asset_hash', '')
                asset_type = getattr(context.scene, 'df_review_asset_type', '')
                if asset_hash and asset_type:
                    bpy.ops.df.refresh_comments(asset_hash=asset_hash, asset_type=asset_type)
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Failed to delete comment")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to delete comment: {str(e)}")
            logger.error(f"Failed to delete comment: {e}", exc_info=True)
            return {'CANCELLED'}


class DF_OT_set_approval(Operator):
    """Set approval status for asset."""
    bl_idname = "df.set_approval"
    bl_label = "Set Approval"
    bl_description = "Approve or reject the selected asset"
    bl_options = {'REGISTER'}

    asset_hash: StringProperty(name="Asset Hash")
    asset_type: StringProperty(name="Asset Type")
    status: StringProperty(name="Status", default="approved")  # 'approved', 'rejected', 'pending'
    comment: StringProperty(name="Comment", description="Optional approval comment", default="")

    def execute(self, context):
        """Set approval."""
        if not _REVIEW_AVAILABLE:
            self.report({'ERROR'}, "Review features unavailable: Forester Python bindings not found.")
            return {'CANCELLED'}
        repo_path, error = get_repository_path(self)
        if not repo_path:
            return {'CANCELLED'}

        # Get approver from addon preferences
        from ..operators.operator_helpers import get_addon_preferences
        prefs = get_addon_preferences(context)
        approver = (
            getattr(prefs, "default_author", None)
            or getattr(prefs, "author_name", None)
            or "Unknown"
        )

        try:
            set_approval(
                repo_path,
                self.asset_hash,
                self.asset_type,
                approver,
                self.status,
                self.comment.strip() if self.comment else None
            )
            status_text = "approved" if self.status == "approved" else "rejected" if self.status == "rejected" else "pending"
            self.report({'INFO'}, f"Asset {status_text}")
            
            # Refresh approvals in UI
            bpy.ops.df.refresh_approvals(asset_hash=self.asset_hash, asset_type=self.asset_type)
            
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to set approval: {str(e)}")
            logger.error(f"Failed to set approval: {e}", exc_info=True)
            return {'CANCELLED'}


class DF_OT_refresh_comments(Operator):
    """Refresh comments for asset."""
    bl_idname = "df.refresh_comments"
    bl_label = "Refresh Comments"
    bl_description = "Reload comments for the selected asset"
    bl_options = {'REGISTER', 'INTERNAL'}

    asset_hash: StringProperty(name="Asset Hash")
    asset_type: StringProperty(name="Asset Type")

    def execute(self, context):
        """Refresh comments."""
        if not _REVIEW_AVAILABLE:
            self.report({'ERROR'}, "Review features unavailable: Forester Python bindings not found.")
            return {'CANCELLED'}
        repo_path, error = get_repository_path(self)
        if not repo_path:
            return {'CANCELLED'}

        try:
            comments = get_comments(repo_path, self.asset_hash, self.asset_type, include_resolved=False)
            
            # Store comments in scene property
            if not hasattr(context.scene, 'df_comments'):
                from ..properties.review_properties import register_review_properties
                register_review_properties()
            
            comments_list = context.scene.df_comments
            comments_list.clear()
            
            for comment in comments:
                item = comments_list.add()
                item.comment_id = comment['id']
                item.asset_hash = comment['asset_hash']
                item.asset_type = comment['asset_type']
                item.author = comment['author']
                item.text = comment['text']
                item.created_at = comment['created_at']
                item.x = comment.get('x', 0.0) if comment.get('x') is not None else 0.0
                item.y = comment.get('y', 0.0) if comment.get('y') is not None else 0.0
                item.resolved = comment.get('resolved', 0) == 1
            
            # Store asset info for refresh operations
            context.scene.df_review_asset_hash = self.asset_hash
            context.scene.df_review_asset_type = self.asset_type
            
            return {'FINISHED'}
        except Exception as e:
            logger.error(f"Failed to refresh comments: {e}", exc_info=True)
            return {'CANCELLED'}


class DF_OT_refresh_approvals(Operator):
    """Refresh approvals for asset."""
    bl_idname = "df.refresh_approvals"
    bl_label = "Refresh Approvals"
    bl_description = "Reload approvals for the selected asset"
    bl_options = {'REGISTER', 'INTERNAL'}

    asset_hash: StringProperty(name="Asset Hash")
    asset_type: StringProperty(name="Asset Type")

    def execute(self, context):
        """Refresh approvals."""
        if not _REVIEW_AVAILABLE:
            self.report({'ERROR'}, "Review features unavailable: Forester Python bindings not found.")
            return {'CANCELLED'}
        repo_path, error = get_repository_path(self)
        if not repo_path:
            return {'CANCELLED'}

        try:
            approvals = get_all_approvals(repo_path, self.asset_hash, self.asset_type)
            
            # Store approvals in scene property
            if not hasattr(context.scene, 'df_approvals'):
                from ..properties.review_properties import register_review_properties
                register_review_properties()
            
            approvals_list = context.scene.df_approvals
            approvals_list.clear()
            
            for approval in approvals:
                item = approvals_list.add()
                item.asset_hash = approval['asset_hash']
                item.asset_type = approval['asset_type']
                item.status = approval['status']
                item.approver = approval['approver']
                item.comment = approval.get('comment', '') or ''
                item.created_at = approval['created_at']
            
            return {'FINISHED'}
        except Exception as e:
            logger.error(f"Failed to refresh approvals: {e}", exc_info=True)
            return {'CANCELLED'}


# === Registration helpers ===
classes = [
    DF_OT_add_comment,
    DF_OT_resolve_comment,
    DF_OT_delete_comment,
    DF_OT_set_approval,
    DF_OT_refresh_comments,
    DF_OT_refresh_approvals,
]


def register():
    """Register review-related operators."""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister review-related operators."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

