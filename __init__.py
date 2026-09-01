import bpy
import bpy_extras.anim_utils
import random
from bpy.app.handlers import persistent

bl_info = {
    "name": "Object Wiggle",
    "author": "m-dr",
    "version": (1, 0, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Wiggle",
    "description": "Procedural noise transforms for objects with multi-object editing and Blender 5.2 slotted action support",
    "category": "Animation",
}

WIGGLE_ROTATION_MOD = "Wiggle Rotation"
WIGGLE_LOCATION_MOD = "Wiggle Location"
WIGGLE_MOD_PREFIX = "Wiggle"

_is_syncing_props = False
_is_updating_props = False
_last_active_object = None


def get_object_fcurves(ob, create_if_missing=False):
    """
    Retrieves fcurves from an object's action/channelbag.
    Compatible with Blender 5.0+ Slotted Actions and legacy actions.
    """
    if not ob:
        return []
    anim_data = ob.animation_data
    if not anim_data:
        if create_if_missing:
            anim_data = ob.animation_data_create()
        else:
            return []

    # Blender 5.0+ Slotted Actions (channelbag in assigned slot)
    if hasattr(bpy_extras, "anim_utils"):
        try:
            channelbag = bpy_extras.anim_utils.animdata_get_channelbag_for_assigned_slot(anim_data)
            if channelbag and hasattr(channelbag, "fcurves"):
                return channelbag.fcurves
        except Exception:
            pass

        if anim_data.action and hasattr(anim_data, "action_slot") and anim_data.action_slot:
            try:
                channelbag = bpy_extras.anim_utils.action_get_channelbag_for_slot(anim_data.action, anim_data.action_slot)
                if channelbag and hasattr(channelbag, "fcurves"):
                    return channelbag.fcurves
            except Exception:
                pass

    # Legacy / Unslotted action fallback
    if anim_data.action and hasattr(anim_data.action, "fcurves"):
        return anim_data.action.fcurves

    return []


def ensure_fcurve(ob, data_path, index, frame=1):
    """
    Ensures that an fcurve for the given data_path and array_index exists
    and has at least one keyframe point. Recreates if user manually deleted it.
    """
    if not ob.animation_data:
        ob.animation_data_create()

    fcurves = get_object_fcurves(ob, create_if_missing=True)
    target_fc = None
    for fc in fcurves:
        if fc.data_path == data_path and fc.array_index == index:
            target_fc = fc
            break

    if target_fc is None or len(target_fc.keyframe_points) == 0:
        ob.keyframe_insert(data_path=data_path, index=index, frame=frame)
        fcurves = get_object_fcurves(ob, create_if_missing=True)
        for fc in fcurves:
            if fc.data_path == data_path and fc.array_index == index:
                target_fc = fc
                break

    return target_fc


def find_wiggle_modifier(fcu, name_prefix=WIGGLE_MOD_PREFIX):
    """
    Finds a noise modifier created by Object Wiggle on an fcurve,
    distinguishing it from user-created noise modifiers.
    """
    if not fcu:
        return None
    for mod in fcu.modifiers:
        if mod.type == 'NOISE' and mod.name.startswith(name_prefix):
            return mod
    return None


def has_wiggle_modifiers(ob):
    """
    Checks if an object currently has any active Wiggle modifiers.
    """
    fcurves = get_object_fcurves(ob)
    for fc in fcurves:
        if fc.data_path in ("delta_rotation_euler", "delta_location"):
            if find_wiggle_modifier(fc):
                return True
    return False


def apply_wiggle_to_object(ob, props=None):
    """
    Applies or updates Wiggle noise modifiers on an object's delta transforms.
    """
    if not ob:
        return
    if props is None:
        props = ob.wiggle_props

    # Deterministic base seed per object and user seed
    obj_hash = (abs(hash(ob.name)) % 100000) * 13.37
    seed_offset = props.seed * 1000.0 + (obj_hash if props.use_unique_seed else 0.0)

    # --- Rotation Wiggle ---
    if props.enable_rotation:
        for idx in range(3):
            fc = ensure_fcurve(ob, "delta_rotation_euler", idx)
            if not fc:
                continue
            mod = find_wiggle_modifier(fc, WIGGLE_ROTATION_MOD) or find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
            if mod is None:
                mod = fc.modifiers.new(type='NOISE')
                mod.name = WIGGLE_ROTATION_MOD

            mod.scale = max(props.rot_speed, 0.001)
            mod.strength = props.rot_strength
            mod.phase = props.rot_phase + seed_offset + (idx * 1731.5)
            mod.use_influence = True
            mod.influence = props.rot_influence
    else:
        # Remove rotation wiggle if disabled
        fcurves = get_object_fcurves(ob)
        for fc in fcurves:
            if fc.data_path == "delta_rotation_euler":
                mod = find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
                if mod:
                    fc.modifiers.remove(mod)

    # --- Location Wiggle ---
    if props.enable_location:
        for idx in range(3):
            fc = ensure_fcurve(ob, "delta_location", idx)
            if not fc:
                continue
            mod = find_wiggle_modifier(fc, WIGGLE_LOCATION_MOD) or find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
            if mod is None:
                mod = fc.modifiers.new(type='NOISE')
                mod.name = WIGGLE_LOCATION_MOD

            mod.scale = max(props.loc_speed, 0.001)
            mod.strength = props.loc_strength
            mod.phase = props.loc_phase + seed_offset + 50000.0 + (idx * 1731.5)
            mod.use_influence = True
            mod.influence = props.loc_influence
    else:
        # Remove location wiggle if disabled
        fcurves = get_object_fcurves(ob)
        for fc in fcurves:
            if fc.data_path == "delta_location":
                mod = find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
                if mod:
                    fc.modifiers.remove(mod)

    ob.update_tag()


def remove_wiggle_from_object(ob):
    """
    Removes all Wiggle modifiers from delta transforms and cleans up empty curves.
    """
    if not ob:
        return
    fcurves = get_object_fcurves(ob)
    if not fcurves:
        ob.delta_rotation_euler = (0.0, 0.0, 0.0)
        ob.delta_location = (0.0, 0.0, 0.0)
        ob.update_tag()
        return

    to_remove_fcurves = []
    for fc in list(fcurves):
        if fc.data_path in ("delta_rotation_euler", "delta_location"):
            wiggle_mods = [m for m in fc.modifiers if m.type == 'NOISE' and m.name.startswith(WIGGLE_MOD_PREFIX)]
            for m in wiggle_mods:
                fc.modifiers.remove(m)
            # If no modifiers left and only 1 static keyframe, mark for removal
            if len(fc.modifiers) == 0 and len(fc.keyframe_points) <= 1:
                to_remove_fcurves.append(fc)

    if to_remove_fcurves:
        anim_data = ob.animation_data
        cb = None
        if hasattr(bpy_extras, "anim_utils"):
            cb = bpy_extras.anim_utils.animdata_get_channelbag_for_assigned_slot(anim_data)
        if cb:
            for fc in to_remove_fcurves:
                try:
                    cb.fcurves.remove(fc)
                except Exception:
                    pass
        elif anim_data and anim_data.action:
            for fc in to_remove_fcurves:
                try:
                    anim_data.action.fcurves.remove(fc)
                except Exception:
                    pass

    ob.delta_rotation_euler = (0.0, 0.0, 0.0)
    ob.delta_location = (0.0, 0.0, 0.0)
    ob.update_tag()


def sync_props_from_modifiers(ob):
    """
    Reads existing F-Curve modifier settings into the object's PropertyGroup.
    """
    global _is_syncing_props
    if not ob or _is_syncing_props:
        return
    fcurves = get_object_fcurves(ob)
    if not fcurves:
        return

    props = ob.wiggle_props
    _is_syncing_props = True
    try:
        has_rot = False
        for fc in fcurves:
            if fc.data_path == "delta_rotation_euler":
                mod = find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
                if mod:
                    props.rot_speed = mod.scale
                    props.rot_strength = mod.strength
                    props.rot_influence = mod.influence
                    has_rot = True
                    break
        props.enable_rotation = has_rot

        has_loc = False
        for fc in fcurves:
            if fc.data_path == "delta_location":
                mod = find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
                if mod:
                    props.loc_speed = mod.scale
                    props.loc_strength = mod.strength
                    props.loc_influence = mod.influence
                    has_loc = True
                    break
        props.enable_location = has_loc
    finally:
        _is_syncing_props = False


def on_prop_update(self, context):
    """
    Property update callback supporting multi-object adjustments.
    """
    global _is_syncing_props, _is_updating_props
    if _is_syncing_props or _is_updating_props:
        return

    _is_updating_props = True
    try:
        active_ob = context.active_object
        selected_obs = context.selected_objects

        if not selected_obs:
            if active_ob and has_wiggle_modifiers(active_ob):
                apply_wiggle_to_object(active_ob)
            return

        # If active object has wiggle or multiple objects are selected with wiggle active
        for ob in selected_obs:
            if ob == active_ob:
                if has_wiggle_modifiers(ob):
                    apply_wiggle_to_object(ob, ob.wiggle_props)
            else:
                # Copy settings from active object if other object has wiggle enabled
                if has_wiggle_modifiers(ob):
                    ob_props = ob.wiggle_props
                    ob_props.rot_speed = self.rot_speed
                    ob_props.rot_strength = self.rot_strength
                    ob_props.rot_phase = self.rot_phase
                    ob_props.rot_influence = self.rot_influence
                    ob_props.enable_rotation = self.enable_rotation

                    ob_props.loc_speed = self.loc_speed
                    ob_props.loc_strength = self.loc_strength
                    ob_props.loc_phase = self.loc_phase
                    ob_props.loc_influence = self.loc_influence
                    ob_props.enable_location = self.enable_location

                    apply_wiggle_to_object(ob, ob_props)
    finally:
        _is_updating_props = False


class WiggleObjectProperties(bpy.types.PropertyGroup):
    # Rotation Properties
    enable_rotation: bpy.props.BoolProperty(
        name="Rotation",
        description="Enable procedural rotation noise",
        default=True,
        update=on_prop_update,
    )
    rot_speed: bpy.props.FloatProperty(
        name="Speed",
        description="Noise speed/frequency for rotation (lower = faster, higher = slower)",
        default=50.0,
        min=0.01,
        soft_max=1000.0,
        update=on_prop_update,
    )
    rot_strength: bpy.props.FloatProperty(
        name="Strength",
        description="Noise amplitude for rotation",
        default=0.2,
        min=0.0,
        soft_max=10.0,
        update=on_prop_update,
    )
    rot_phase: bpy.props.FloatProperty(
        name="Phase Offset",
        description="Time/phase offset for rotation noise",
        default=0.0,
        soft_min=-1000.0,
        soft_max=1000.0,
        update=on_prop_update,
    )
    rot_influence: bpy.props.FloatProperty(
        name="Influence",
        description="Influence blend factor for rotation noise",
        subtype="FACTOR",
        default=1.0,
        min=0.0,
        max=1.0,
        update=on_prop_update,
    )

    # Location Properties
    enable_location: bpy.props.BoolProperty(
        name="Location",
        description="Enable procedural location noise",
        default=True,
        update=on_prop_update,
    )
    loc_speed: bpy.props.FloatProperty(
        name="Speed",
        description="Noise speed/frequency for location (lower = faster, higher = slower)",
        default=50.0,
        min=0.01,
        soft_max=1000.0,
        update=on_prop_update,
    )
    loc_strength: bpy.props.FloatProperty(
        name="Strength",
        description="Noise amplitude for location",
        default=0.2,
        min=0.0,
        soft_max=10.0,
        update=on_prop_update,
    )
    loc_phase: bpy.props.FloatProperty(
        name="Phase Offset",
        description="Time/phase offset for location noise",
        default=0.0,
        soft_min=-1000.0,
        soft_max=1000.0,
        update=on_prop_update,
    )
    loc_influence: bpy.props.FloatProperty(
        name="Influence",
        description="Influence blend factor for location noise",
        subtype="FACTOR",
        default=1.0,
        min=0.0,
        max=1.0,
        update=on_prop_update,
    )

    # Seed Settings
    seed: bpy.props.IntProperty(
        name="Seed",
        description="Random seed for procedural noise",
        default=0,
        update=on_prop_update,
    )
    use_unique_seed: bpy.props.BoolProperty(
        name="Per-Object Offset",
        description="Automatically offset noise phase per object so multiple objects do not wiggle identically",
        default=True,
        update=on_prop_update,
    )


class OBJECT_OT_wiggle_apply(bpy.types.Operator):
    """Apply procedural wiggle noise to selected objects"""
    bl_idname = "object.wiggle_apply"
    bl_label = "Wiggle it!"
    bl_description = "Apply procedural noise modifiers to delta transforms for active or selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None or len(context.selected_objects) > 0

    def execute(self, context):
        targets = context.selected_objects if context.selected_objects else ([context.active_object] if context.active_object else [])
        if not targets:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        active_props = context.active_object.wiggle_props if context.active_object else None

        for ob in targets:
            if active_props and ob != context.active_object:
                # Sync active settings to other selected objects
                ob_props = ob.wiggle_props
                ob_props.rot_speed = active_props.rot_speed
                ob_props.rot_strength = active_props.rot_strength
                ob_props.rot_phase = active_props.rot_phase
                ob_props.rot_influence = active_props.rot_influence
                ob_props.enable_rotation = active_props.enable_rotation

                ob_props.loc_speed = active_props.loc_speed
                ob_props.loc_strength = active_props.loc_strength
                ob_props.loc_phase = active_props.loc_phase
                ob_props.loc_influence = active_props.loc_influence
                ob_props.enable_location = active_props.enable_location
                ob_props.use_unique_seed = active_props.use_unique_seed

            apply_wiggle_to_object(ob, ob.wiggle_props)

        self.report({'INFO'}, f"Wiggle applied to {len(targets)} object(s)")
        return {'FINISHED'}


class OBJECT_OT_wiggle_remove(bpy.types.Operator):
    """Remove procedural wiggle noise from selected objects"""
    bl_idname = "object.wiggle_remove"
    bl_label = "Remove Wiggle"
    bl_description = "Remove procedural noise modifiers and delta animation from active or selected objects"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None or len(context.selected_objects) > 0

    def execute(self, context):
        targets = context.selected_objects if context.selected_objects else ([context.active_object] if context.active_object else [])
        if not targets:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        count = 0
        for ob in targets:
            remove_wiggle_from_object(ob)
            count += 1

        self.report({'INFO'}, f"Wiggle removed from {count} object(s)")
        return {'FINISHED'}


class OBJECT_OT_wiggle_reroll_seed(bpy.types.Operator):
    """Generate a new random seed for wiggle"""
    bl_idname = "object.wiggle_reroll_seed"
    bl_label = "Randomize Seed"
    bl_description = "Assign a new random seed to wiggle noise"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        targets = context.selected_objects if context.selected_objects else [context.active_object]
        new_seed = random.randint(0, 99999)
        for ob in targets:
            ob.wiggle_props.seed = new_seed
            if has_wiggle_modifiers(ob):
                apply_wiggle_to_object(ob, ob.wiggle_props)

        return {'FINISHED'}


class OBJECT_OT_wiggle_sync(bpy.types.Operator):
    """Sync UI settings from active object's F-Curve modifiers"""
    bl_idname = "object.wiggle_sync"
    bl_label = "Sync from Curves"
    bl_description = "Read current F-Curve modifier values into the panel"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        sync_props_from_modifiers(context.active_object)
        return {'FINISHED'}


class OBJECT_PT_wiggle_panel(bpy.types.Panel):
    bl_label = "Object Wiggle"
    bl_idname = "OBJECT_PT_wiggle_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Wiggle"

    def draw(self, context):
        layout = self.layout
        ob = context.active_object

        if not ob:
            layout.label(text="Select an object to add wiggle", icon='INFO')
            return

        props = ob.wiggle_props
        is_active = has_wiggle_modifiers(ob)
        sel_count = len(context.selected_objects)

        # Top Action Buttons
        main_col = layout.column(align=True)
        row = main_col.row(align=True)
        row.scale_y = 1.3
        btn_label = f"Wiggle ({sel_count} Selected)" if sel_count > 1 else "Wiggle it!"
        row.operator("object.wiggle_apply", text=btn_label, icon='PLAY')

        rem_label = f"Remove ({sel_count} Selected)" if sel_count > 1 else "Remove Wiggle"
        row.operator("object.wiggle_remove", text=rem_label, icon='X')

        # Status row
        status_row = layout.row(align=True)
        if is_active:
            status_row.label(text="Status: Wiggle Active", icon='CHECKMARK')
        else:
            status_row.label(text="Status: No Wiggle", icon='DOT')

        # Rotation Controls Box
        rot_box = layout.box()
        rot_header = rot_box.row(align=True)
        rot_header.prop(props, "enable_rotation", text="Rotation Wiggle", icon='ORIENTATION_GIMBAL')

        if props.enable_rotation:
            col = rot_box.column(align=True)
            col.prop(props, "rot_speed")
            col.prop(props, "rot_strength")
            col.prop(props, "rot_phase")
            col.prop(props, "rot_influence")

        # Location Controls Box
        loc_box = layout.box()
        loc_header = loc_box.row(align=True)
        loc_header.prop(props, "enable_location", text="Location Wiggle", icon='ORIENTATION_GLOBAL')

        if props.enable_location:
            col = loc_box.column(align=True)
            col.prop(props, "loc_speed")
            col.prop(props, "loc_strength")
            col.prop(props, "loc_phase")
            col.prop(props, "loc_influence")

        # Seed & Randomization Box
        seed_box = layout.box()
        seed_box.label(text="Randomization & Variation", icon='RNDCURVE')
        col = seed_box.column(align=True)
        seed_row = col.row(align=True)
        seed_row.prop(props, "seed")
        seed_row.operator("object.wiggle_reroll_seed", text="", icon='FILE_REFRESH')
        col.prop(props, "use_unique_seed")


@persistent
def on_active_object_changed(scene, depsgraph):
    """
    Syncs panel properties when switching active objects.
    """
    global _last_active_object
    try:
        active = bpy.context.view_layer.objects.active
        if active != _last_active_object:
            _last_active_object = active
            if active and has_wiggle_modifiers(active):
                sync_props_from_modifiers(active)
    except Exception:
        pass


classes = [
    WiggleObjectProperties,
    OBJECT_OT_wiggle_apply,
    OBJECT_OT_wiggle_remove,
    OBJECT_OT_wiggle_reroll_seed,
    OBJECT_OT_wiggle_sync,
    OBJECT_PT_wiggle_panel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.wiggle_props = bpy.props.PointerProperty(type=WiggleObjectProperties)
    if on_active_object_changed not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_active_object_changed)


def unregister():
    if on_active_object_changed in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_active_object_changed)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Object.wiggle_props


if __name__ == "__main__":
    register()
