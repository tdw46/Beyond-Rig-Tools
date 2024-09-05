import bpy
import json
import os

bl_info = {
    "name": "Beyond Rig Converter",
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


def update_rig_converter_target(self, context):
    # This function is intentionally left empty to avoid the infinite recursion error
    pass


def register():
    bpy.utils.register_class(RigConverter)
    bpy.types.Scene.rig_converter_target = bpy.props.EnumProperty(
        name="Convert To",
        items=rig_converter_target_items,
        update=update_rig_converter_target,
    )
    bpy.types.DATA_PT_bone_collections.prepend(draw_rig_converter)


def unregister():
    bpy.utils.unregister_class(RigConverter)
    del bpy.types.Scene.rig_converter_target
    bpy.types.DATA_PT_bone_collections.remove(draw_rig_converter)


if __name__ == "__main__":
    register()
