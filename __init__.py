import bpy
import json
import os
import mathutils

bl_info = {
    "name": "Beyond Rig Tools",
    "author": "Tyler Walker (Beyond Dev)",
    "version": (0, 8),
    "blender": (2, 80, 0),
    "location": "Properties > Data > Bone Collections",
    "description": "Convert rig between VROID, Mixamo, and Move-One hierarchies",
    "warning": "",
    "category": "Rigging",
}


def load_json_file(file_name):
    addon_dir = os.path.dirname(__file__)
    file_path = os.path.join(addon_dir, file_name)
    try:
        with open(file_path, "r") as file:
            data = json.load(file)
        return data
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return {}
    except RecursionError:
        print(
            "RecursionError: JSON file is too deeply nested. Please check the structure of your bone_mappings.json file."
        )
        return {}


def get_bone_mapping(source, target):
    mappings = load_json_file("bone_mappings.json")
    print(f"Loaded mappings: {mappings}")  # Debug print

    if source == "MIXAMO":
        if target == "MOVEONE":
            mapping = mappings["mixamo_moveone_mapping"]
        elif target == "VROID":
            mapping = mappings["mixamo_vroid_mapping"]
    elif target == "MIXAMO":
        if source == "MOVEONE":
            mapping = {
                v: k
                for k, v in mappings["mixamo_moveone_mapping"].items()
                if k != "delete"
            }
        elif source == "VROID":
            mapping = {
                v: k
                for k, v in mappings["mixamo_vroid_mapping"].items()
                if k != "delete"
            }
    elif source == "MOVEONE" and target == "VROID":
        mixamo_to_moveone = {
            v: k for k, v in mappings["mixamo_moveone_mapping"].items() if k != "delete"
        }
        mixamo_to_vroid = {
            k: v for k, v in mappings["mixamo_vroid_mapping"].items() if k != "delete"
        }
        mapping = {
            mixamo_to_moveone[k]: v
            for k, v in mixamo_to_vroid.items()
            if k in mixamo_to_moveone
        }
    elif source == "VROID" and target == "MOVEONE":
        mixamo_to_vroid = {
            v: k for k, v in mappings["mixamo_vroid_mapping"].items() if k != "delete"
        }
        mixamo_to_moveone = {
            k: v for k, v in mappings["mixamo_moveone_mapping"].items() if k != "delete"
        }
        mapping = {
            mixamo_to_vroid[k]: v
            for k, v in mixamo_to_moveone.items()
            if k in mixamo_to_vroid
        }
    else:
        mapping = {}

    # Handle 'delete' separately
    if "delete" in mappings.get("mixamo_vroid_mapping", {}):
        mapping["delete"] = mappings["mixamo_vroid_mapping"]["delete"]

    print(f"Selected mapping for {source} to {target}: {mapping}")  # Debug print
    return mapping


def detect_rig_type(armature):
    mappings = load_json_file("bone_mappings.json")
    bone_names = set(bone.name for bone in armature.bones)

    mixamo_bones = set(
        k for k in mappings["mixamo_moveone_mapping"].keys() if k != "delete"
    )
    moveone_bones = set(
        v for k, v in mappings["mixamo_moveone_mapping"].items() if k != "delete"
    )
    vroid_bones = set(
        v for k, v in mappings["mixamo_vroid_mapping"].items() if k != "delete"
    )

    mixamo_match = len(bone_names.intersection(mixamo_bones)) / len(mixamo_bones)
    moveone_match = len(bone_names.intersection(moveone_bones)) / len(moveone_bones)
    vroid_match = len(bone_names.intersection(vroid_bones)) / len(vroid_bones)

    if mixamo_match > 0.8:
        return "MIXAMO"
    elif moveone_match > 0.8:
        return "MOVEONE"
    elif vroid_match > 0.8:
        return "VROID"
    else:
        return "UNKNOWN"


class RigConverter(bpy.types.Operator):
    bl_idname = "object.rig_converter"
    bl_label = "Convert Rig"

    @classmethod
    def poll(cls, context):
        active_object = context.active_object
        return (
            active_object
            and active_object.type == "ARMATURE"
            and context.scene.rig_converter_target != "NONE"
        )

    def execute(self, context):
        active_object = bpy.context.active_object
        if active_object.type == "ARMATURE":
            rig = active_object.data
            source_format = detect_rig_type(rig)
            target_format = context.scene.rig_converter_target

            bone_mapping = get_bone_mapping(source_format, target_format)
            self.convert_rig(rig, bone_mapping, source_format, target_format)

        return {"FINISHED"}

    def convert_rig(self, armature, bone_mapping, source_format, target_format):
        bpy.ops.object.mode_set(mode="EDIT")

        # Delete bones first
        delete_bones = bone_mapping.get("delete", {})
        print(f"Delete bones: {delete_bones}")

        if not delete_bones:
            print(
                "Warning: delete_bones is empty. Check if 'delete' key exists in the mapping."
            )

        bones_to_delete = [
            bone.name for bone in armature.edit_bones if bone.name in delete_bones
        ]
        print(f"Bones to delete: {bones_to_delete}")

        for bone_name in bones_to_delete:
            bone = armature.edit_bones.get(bone_name)
            if bone:
                armature.edit_bones.remove(bone)
                print(f"Deleted bone: {bone_name}")

        # Rename bones
        for bone in armature.edit_bones:
            if bone.name in bone_mapping and bone.name != "delete":
                bone.name = bone_mapping[bone.name]
            else:
                print(f"Unmapped bone: {bone.name}")

        bpy.ops.object.mode_set(mode="OBJECT")


class MatchRigPose(bpy.types.Operator):
    bl_idname = "object.match_rig_pose"
    bl_label = "Match Rig Pose"

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) == 2 and all(
            obj.type == "ARMATURE" for obj in context.selected_objects
        )

    def execute(self, context):
        active_obj = context.active_object
        target_obj = next(
            (obj for obj in context.selected_objects if obj != active_obj), None
        )

        if not active_obj or active_obj.type != "ARMATURE" or not target_obj:
            self.report({"ERROR"}, "Please select two armatures")
            return {"CANCELLED"}

        print(f"Active object: {active_obj.name}")
        print(f"Target object: {target_obj.name}")

        # Calculate the offset between the two armatures
        armature_offset = (
            active_obj.matrix_world.translation - target_obj.matrix_world.translation
        )

        def align_single_bone(bone_name):
            if (
                bone_name not in active_obj.pose.bones
                or bone_name not in target_obj.pose.bones
            ):
                print(f"Bone {bone_name} not found in both armatures. Skipping.")
                return

            # Select the bone
            bpy.ops.pose.select_all(action="DESELECT")
            active_obj.data.bones[bone_name].select = True
            active_obj.data.bones.active = active_obj.data.bones[bone_name]

            active_pose_bone = active_obj.pose.bones[bone_name]
            target_pose_bone = target_obj.pose.bones[bone_name]

            print(f"Aligning bone: {bone_name}")

            try:
                # Get the world space matrices for both bones
                target_world_matrix = target_obj.matrix_world @ target_pose_bone.matrix
                active_world_matrix = active_obj.matrix_world @ active_pose_bone.matrix

                # Apply the armature offset to the target world matrix
                target_world_matrix.translation += armature_offset

                # Calculate the difference in world space
                world_diff = target_world_matrix @ active_world_matrix.inverted()

                # Convert the world difference to local space of the active armature
                local_diff = (
                    active_obj.matrix_world.inverted()
                    @ world_diff
                    @ active_obj.matrix_world
                )

                # Apply the local difference to the active pose bone
                active_pose_bone.matrix = local_diff @ active_pose_bone.matrix

                # Calculate and apply the roll
                target_y_axis = (
                    target_world_matrix.to_3x3() @ mathutils.Vector((0, 1, 0))
                ).normalized()
                active_y_axis = (
                    active_world_matrix.to_3x3() @ mathutils.Vector((0, 1, 0))
                ).normalized()

                roll_quat = target_y_axis.rotation_difference(active_y_axis)

                # Apply the roll rotation
                # Uncomment the following lines if you want to apply the roll
                # active_pose_bone.rotation_mode = 'QUATERNION'
                # active_pose_bone.rotation_quaternion = roll_quat @ active_pose_bone.rotation_quaternion

                # Update the view to ensure changes are applied
                context.view_layer.update()

            except Exception as e:
                print(f"Error aligning bone {bone_name}: {str(e)}")

        def align_bone_chain(bone):
            align_single_bone(bone.name)

            # Align all children recursively
            for child in bone.children:
                align_bone_chain(child)

        def align_armature():
            # Start with all root bones
            root_bones = [bone for bone in active_obj.data.bones if not bone.parent]
            for root_bone in root_bones:
                align_bone_chain(root_bone)

        # Align the entire armature
        align_armature()

        print("All bones aligned")
        self.report({"INFO"}, "Rig pose matched successfully")
        return {"FINISHED"}


def rig_converter_target_items(self, context):
    items = [
        ("NONE", "None", "No conversion"),
        ("MOVEONE", "Move-One", "Convert to Move-One rig"),
        ("MIXAMO", "Mixamo", "Convert to Mixamo rig"),
        ("VROID", "VRoid", "Convert to VRoid rig"),
    ]

    active_object = context.active_object
    if active_object and active_object.type == "ARMATURE":
        try:
            current_rig_type = detect_rig_type(active_object.data)
            return [item for item in items if item[0] != current_rig_type]
        except Exception as e:
            print(f"Error detecting rig type: {e}")
            return items
    return [("NONE", "None", "No conversion")]


def draw_rig_converter(self, context):
    layout = self.layout
    scene = context.scene

    row = layout.row()
    row.prop(scene, "rig_converter_target")

    row = layout.row()
    row.operator("object.rig_converter")
    row.enabled = scene.rig_converter_target != "NONE"

    row = layout.row()
    row.operator("object.match_rig_pose")


def update_rig_converter_target(self, context):
    # This function is intentionally left empty to avoid the infinite recursion error
    pass


def register():
    bpy.utils.register_class(RigConverter)
    bpy.utils.register_class(MatchRigPose)
    bpy.types.Scene.rig_converter_target = bpy.props.EnumProperty(
        name="Convert To",
        items=rig_converter_target_items,
        update=update_rig_converter_target,
    )
    bpy.types.DATA_PT_bone_collections.prepend(draw_rig_converter)


def unregister():
    bpy.utils.unregister_class(RigConverter)
    bpy.utils.unregister_class(MatchRigPose)
    del bpy.types.Scene.rig_converter_target
    bpy.types.DATA_PT_bone_collections.remove(draw_rig_converter)


if __name__ == "__main__":
    register()
