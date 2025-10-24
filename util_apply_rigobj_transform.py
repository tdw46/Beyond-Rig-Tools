import bpy
from bpy.props import PointerProperty, CollectionProperty, StringProperty, IntProperty
from bpy.types import Operator, PropertyGroup, UIList, Menu
import mathutils

# Custom poll function to filter for armature objects
def armature_poll(self, object):
    return object.type == 'ARMATURE'

class TRANSFORM_OT_apply(Operator):
    bl_idname = "object.transform_apply_custom"
    bl_label = "Apply Transforms"

    def execute(self, context):
        armature = context.window_manager.armature
        animations = context.window_manager.animations

        if armature.type != 'ARMATURE':
            self.report({'ERROR'}, "Selected object is not an armature!")
            return {'CANCELLED'}

        # Store original matrix
        original_matrix = armature.matrix_world.copy()

        # Scale root-bone location keys by the original object scale to preserve world motion after applying transforms
        if not armature.pose.bones:
            self.report({'WARNING'}, 'No pose bones on armature')
        else:
            root_bone_name = armature.pose.bones[0].name
            scale_vec = armature.scale.copy()

            def fcurve_for(action, path, index):
                for fc in action.fcurves:
                    if fc.data_path == path and fc.array_index == index:
                        return fc
                return None

            def frames_union(curves):
                frames = set()
                for c in curves:
                    if c is None:
                        continue
                    for kp in c.keyframe_points:
                        frames.add(kp.co[0])
                return sorted(frames)

            for anim in animations:
                action = bpy.data.actions.get(anim.name)
                if not action:
                    continue

                path = f'pose.bones["{root_bone_name}"].location'
                cx = fcurve_for(action, path, 0)
                cy = fcurve_for(action, path, 1)
                cz = fcurve_for(action, path, 2)

                if not (cx or cy or cz):
                    continue

                def eval_axis(fc, frame):
                    return fc.evaluate(frame) if fc else 0.0

                for frame in frames_union([cx, cy, cz]):
                    x = eval_axis(cx, frame)
                    y = eval_axis(cy, frame)
                    z = eval_axis(cz, frame)
                    new_vals = (x * scale_vec[0], y * scale_vec[1], z * scale_vec[2])

                    for i, fc in enumerate([cx, cy, cz]):
                        if fc is None:
                            continue
                        # Find an existing key at this frame
                        target_kp = None
                        for kp in fc.keyframe_points:
                            if kp.co[0] == frame:
                                target_kp = kp
                                break
                        if target_kp is None:
                            fc.keyframe_points.insert(frame, new_vals[i], options={'FAST'})
                        else:
                            target_kp.co[1] = new_vals[i]

        # Apply transformation in world space
        armature.matrix_world = original_matrix

        # Apply current pose transforms as the default for the armature object
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

        return {'FINISHED'}


class TRANSFORM_MT_add(Menu):
    bl_idname = "TRANSFORM_MT_add"
    bl_label = "Add Animation"

    def draw(self, context):
        layout = self.layout
        armature = context.window_manager.armature
        animations = context.window_manager.animations

        for action in collect_actions_for_object(armature):
            if not any(anim.name == action.name for anim in animations):
                layout.operator("object.add_anim", text=action.name).action = action.name

class TRANSFORM_MT_edit(Menu):
    bl_idname = "TRANSFORM_MT_edit"
    bl_label = "Edit Animations"

    def draw(self, context):
        layout = self.layout
        layout.operator("object.add_all_anims")
        layout.operator("object.remove_all_anims")

def collect_actions_for_object(obj):
    actions = []
    if not obj or not getattr(obj, 'animation_data', None):
        return actions

    ad = obj.animation_data
    # Blender 4.4+ slotted actions
    if hasattr(ad, 'action_slots') and ad.action_slots:
        for slot in ad.action_slots:
            if slot and slot.action and slot.action not in actions:
                actions.append(slot.action)

    # Single action (pre-4.4 also present in 4.4+)
    if getattr(ad, 'action', None) and ad.action not in actions:
        actions.append(ad.action)

    # NLA strips referencing actions
    if getattr(ad, 'nla_tracks', None):
        for track in ad.nla_tracks:
            for strip in getattr(track, 'strips', []):
                act = getattr(strip, 'action', None)
                if act and act not in actions:
                    actions.append(act)

    return actions


def update_animations(self, context):
    wm = context.window_manager
    armature = wm.armature
    for action in collect_actions_for_object(armature):
        if not any(anim.name == action.name for anim in wm.animations):
            item = wm.animations.add()
            item.name = action.name

class TRANSFORM_OT_add_anim(Operator):
    bl_idname = "object.add_anim"
    bl_label = "Add Animation"
    action: StringProperty()

    def execute(self, context):
        wm = context.window_manager
        item = wm.animations.add()
        item.name = self.action
        update_animations(self, context)
        return {'FINISHED'}

class TRANSFORM_OT_remove_anim(Operator):
    bl_idname = "object.remove_anim"
    bl_label = "Remove Animation"

    def execute(self, context):
        wm = context.window_manager
        wm.animations.remove(wm.active_animation_index)
        update_animations(self, context)
        return {'FINISHED'}

class TRANSFORM_OT_add_all_anims(Operator):
    bl_idname = "object.add_all_anims"
    bl_label = "Add All Animations"

    def execute(self, context):
        armature = context.window_manager.armature
        animations = context.window_manager.animations
        for action in collect_actions_for_object(armature):
            item = animations.add()
            item.name = action.name
        update_animations(self, context)
        return {'FINISHED'}

class TRANSFORM_OT_remove_all_anims(Operator):
    bl_idname = "object.remove_all_anims"
    bl_label = "Remove All Animations"

    def execute(self, context):
        context.window_manager.animations.clear()
        return {'FINISHED'}


class TRANSFORM_OT_popup(Operator):
    bl_idname = "object.transform_popup"
    bl_label = "Select Armature and Animation"

    def execute(self, context):
        bpy.ops.object.transform_apply_custom()
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.armature = context.active_object

        # Clear the animations list and add actions used by this armature
        wm.animations.clear()
        for action in collect_actions_for_object(wm.armature):
            item = wm.animations.add()
            item.name = action.name

        return context.window_manager.invoke_props_dialog(self, width=400)
    
    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        layout.prop_search(wm, "armature", bpy.data, "objects", text="Armature", icon='ARMATURE_DATA')

        row = layout.row()
        row.template_list("ANIM_UL_list", "", wm, "animations", wm, "active_animation_index")

        col = row.column(align=True)
        col.menu("TRANSFORM_MT_add", icon='ADD', text="")
        col.operator("object.remove_anim", icon='REMOVE', text="")
        col.menu("TRANSFORM_MT_edit", icon='DOWNARROW_HLT', text="")

class TRANSFORM_MT_add(Menu):
    bl_idname = "TRANSFORM_MT_add"
    bl_label = "Add Animation"

    def draw(self, context):
        layout = self.layout
        armature = context.window_manager.armature
        animations = context.window_manager.animations

        if armature and armature.animation_data:
            for action in bpy.data.actions:
                if not any(anim.name == action.name for anim in animations):
                    layout.operator("object.add_anim", text=action.name).action = action.name

class ANIM_UL_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "name", text="", emboss=False, translate=False)

class AnimationItem(PropertyGroup):
    name: StringProperty()

def register():
    bpy.utils.register_class(AnimationItem)
    bpy.utils.register_class(TRANSFORM_OT_apply)
    bpy.utils.register_class(TRANSFORM_MT_add)
    bpy.utils.register_class(TRANSFORM_MT_edit)
    bpy.utils.register_class(TRANSFORM_OT_add_anim)
    bpy.utils.register_class(TRANSFORM_OT_remove_anim)
    bpy.utils.register_class(TRANSFORM_OT_add_all_anims)
    bpy.utils.register_class(TRANSFORM_OT_remove_all_anims)
    bpy.utils.register_class(TRANSFORM_OT_popup)
    bpy.utils.register_class(ANIM_UL_list)
    bpy.types.WindowManager.armature = PointerProperty(
        type=bpy.types.Object,
        poll=armature_poll
    )
    bpy.types.WindowManager.animations = CollectionProperty(type=AnimationItem)
    bpy.types.WindowManager.active_animation_index = IntProperty()

def unregister():
    bpy.utils.unregister_class(AnimationItem)
    bpy.utils.unregister_class(TRANSFORM_OT_apply)
    bpy.utils.unregister_class(TRANSFORM_MT_add)
    bpy.utils.unregister_class(TRANSFORM_MT_edit)
    bpy.utils.unregister_class(TRANSFORM_OT_add_anim)
    bpy.utils.unregister_class(TRANSFORM_OT_remove_anim)
    bpy.utils.unregister_class(TRANSFORM_OT_add_all_anims)
    bpy.utils.unregister_class(TRANSFORM_OT_remove_all_anims)
    bpy.utils.unregister_class(TRANSFORM_OT_popup)
    bpy.utils.unregister_class(ANIM_UL_list)
    del bpy.types.WindowManager.armature
    del bpy.types.WindowManager.animations
    del bpy.types.WindowManager.active_animation_index

if __name__ == "__main__":
    register()

    bpy.ops.object.transform_popup('INVOKE_DEFAULT')
