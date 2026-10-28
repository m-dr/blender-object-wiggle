import bpy
import bpy_extras.anim_utils
import math
import random
from mathutils import noise, Vector
from bpy.app.handlers import persistent

bl_info = {
    "name": "Object Wiggle (DEV)",
    "author": "m-dr",
    "version": (0, 1, 4),
    "blender": (5, 2, 0),
    "location": "View3D > Sidebar > Wiggle",
    "description": "Procedural noise transforms for objects with seamless loops, frame ranges, spatial offsets, multi-object editing and Blender 5.2 slotted action support",
    "category": "Animation",
}

WIGGLE_ROTATION_MOD = "Wiggle Rotation"
WIGGLE_LOCATION_MOD = "Wiggle Location"
WIGGLE_CYCLES_MOD = "Wiggle Cycles"
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
    Finds a modifier created by Object Wiggle on an fcurve.
    """
    if not fcu:
        return None
    for mod in fcu.modifiers:
        if mod.name.startswith(name_prefix):
            return mod
    return None


def has_wiggle_modifiers(ob):
    """
    Checks if an object currently has any active Wiggle modifiers or loop animation.
    """
    fcurves = get_object_fcurves(ob)
    for fc in fcurves:
        if fc.data_path in ("delta_rotation_euler", "delta_location"):
            if find_wiggle_modifier(fc) or len(fc.keyframe_points) > 1:
                return True
    return False


def calculate_spatial_offset(ob, props):
    """
    Computes base phase offset using Random/Name Hash, Linear Directional Wave, or Radial Ripple.
    Accounts for resting base positions across parent hierarchies.
    """
    seed_base = props.seed * 1000.0

    if props.offset_mode == 'RANDOM':
        obj_hash = (abs(hash(ob.name)) % 100000) * 13.37
        return seed_base + (obj_hash if props.use_unique_seed else 0.0)

    world_pos = ob.matrix_world.translation - Vector(ob.delta_location)
    guide = props.guide_object

    if props.offset_mode == 'LINEAR':
        if guide and guide != ob:
            try:
                rel_pos = guide.matrix_world.inverted_safe() @ world_pos
            except Exception:
                guide_pos = guide.matrix_world.translation - Vector(guide.delta_location)
                rel_pos = world_pos - guide_pos
        else:
            rel_pos = world_pos

        axis = props.offset_axis.lower()
        axis_coord = getattr(rel_pos, axis, 0.0)
        return seed_base + (axis_coord * props.spatial_scale)

    if props.offset_mode == 'RADIAL':
        if guide and guide != ob:
            origin = guide.matrix_world.translation - Vector(guide.delta_location)
        else:
            origin = Vector((0.0, 0.0, 0.0))
        dist = (world_pos - origin).length
        return seed_base + (dist * props.spatial_scale)

    return seed_base


def evaluate_circular_noise(frame, f_start, f_end, speed, strength, seed_z, phase_offset=0.0):
    """
    Evaluates 2D/3D circular periodic noise for seamless looping without NLA.
    """
    length = max(f_end - f_start, 1.0)
    angle = 2.0 * math.pi * (frame - f_start) / length + (phase_offset * 0.02)
    freq = max(50.0 / max(speed, 0.001), 0.1)
    nx = math.cos(angle) * freq
    ny = math.sin(angle) * freq
    nz = seed_z * 0.01
    val = noise.turbulence_vector(Vector((nx, ny, nz)), 3, False).x
    return val * strength


def apply_wiggle_to_object(ob, props=None):
    """
    Applies or updates Wiggle noise or seamless circular loop on an object's delta transforms.
    """
    if not ob:
        return
    if props is None:
        props = ob.wiggle_props

    spatial_offset = calculate_spatial_offset(ob, props)

    if props.enable_loop:
        # --- Seamless Loop Mode (Circular Noise + Cycles Modifier) ---
        f_start = int(props.loop_start)
        f_end = int(props.loop_end)
        if f_end <= f_start:
            f_end = f_start + 1
        count = f_end - f_start + 1

        # Rotation Loop
        if props.enable_rotation:
            for idx in range(3):
                fc = ensure_fcurve(ob, "delta_rotation_euler", idx, frame=f_start)
                if not fc:
                    continue
                # Remove noise modifiers
                for m in list(fc.modifiers):
                    if m.name.startswith(WIGGLE_MOD_PREFIX) and m.type == 'NOISE':
                        fc.modifiers.remove(m)

                # Populate loop keyframe points
                fc.keyframe_points.clear()
                fc.keyframe_points.add(count)
                seed_z = (props.seed * 1000.0) + spatial_offset + (idx * 1731.5)
                eff_strength = props.rot_strength * props.rot_influence

                for i, f in enumerate(range(f_start, f_end + 1)):
                    v = evaluate_circular_noise(f, f_start, f_end, props.rot_speed, eff_strength, seed_z, props.rot_phase)
                    kp = fc.keyframe_points[i]
                    kp.co = (f, v)
                    kp.handle_left_type = 'AUTO'
                    kp.handle_right_type = 'AUTO'
                fc.update()

                # Cycles modifier for repeat
                if props.loop_repeat:
                    cyc = next((m for m in fc.modifiers if m.type == 'CYCLES' and m.name == WIGGLE_CYCLES_MOD), None)
                    if not cyc:
                        cyc = fc.modifiers.new(type='CYCLES')
                        cyc.name = WIGGLE_CYCLES_MOD
                    cyc.mode_before = 'REPEAT'
                    cyc.mode_after = 'REPEAT'
                else:
                    for m in list(fc.modifiers):
                        if m.type == 'CYCLES' and m.name == WIGGLE_CYCLES_MOD:
                            fc.modifiers.remove(m)
        else:
            fcurves = get_object_fcurves(ob)
            for fc in fcurves:
                if fc.data_path == "delta_rotation_euler":
                    for m in list(fc.modifiers):
                        if m.name.startswith(WIGGLE_MOD_PREFIX):
                            fc.modifiers.remove(m)
                    if len(fc.keyframe_points) > 1:
                        fc.keyframe_points.clear()
                        fc.keyframe_points.add(1)
                        fc.keyframe_points[0].co = (1.0, 0.0)

        # Location Loop
        if props.enable_location:
            for idx in range(3):
                fc = ensure_fcurve(ob, "delta_location", idx, frame=f_start)
                if not fc:
                    continue
                # Remove noise modifiers
                for m in list(fc.modifiers):
                    if m.name.startswith(WIGGLE_MOD_PREFIX) and m.type == 'NOISE':
                        fc.modifiers.remove(m)

                # Populate loop keyframe points
                fc.keyframe_points.clear()
                fc.keyframe_points.add(count)
                seed_z = (props.seed * 1000.0) + spatial_offset + 50000.0 + (idx * 1731.5)
                eff_strength = props.loc_strength * props.loc_influence

                for i, f in enumerate(range(f_start, f_end + 1)):
                    v = evaluate_circular_noise(f, f_start, f_end, props.loc_speed, eff_strength, seed_z, props.loc_phase)
                    kp = fc.keyframe_points[i]
                    kp.co = (f, v)
                    kp.handle_left_type = 'AUTO'
                    kp.handle_right_type = 'AUTO'
                fc.update()

                if props.loop_repeat:
                    cyc = next((m for m in fc.modifiers if m.type == 'CYCLES' and m.name == WIGGLE_CYCLES_MOD), None)
                    if not cyc:
                        cyc = fc.modifiers.new(type='CYCLES')
                        cyc.name = WIGGLE_CYCLES_MOD
                    cyc.mode_before = 'REPEAT'
                    cyc.mode_after = 'REPEAT'
                else:
                    for m in list(fc.modifiers):
                        if m.type == 'CYCLES' and m.name == WIGGLE_CYCLES_MOD:
                            fc.modifiers.remove(m)
        else:
            fcurves = get_object_fcurves(ob)
            for fc in fcurves:
                if fc.data_path == "delta_location":
                    for m in list(fc.modifiers):
                        if m.name.startswith(WIGGLE_MOD_PREFIX):
                            fc.modifiers.remove(m)
                    if len(fc.keyframe_points) > 1:
                        fc.keyframe_points.clear()
                        fc.keyframe_points.add(1)
                        fc.keyframe_points[0].co = (1.0, 0.0)

    else:
        # --- Procedural F-Curve Noise Modifier Mode ---
        fcurves = get_object_fcurves(ob)
        for fc in fcurves:
            if fc.data_path in ("delta_rotation_euler", "delta_location"):
                for m in list(fc.modifiers):
                    if m.type == 'CYCLES' and m.name == WIGGLE_CYCLES_MOD:
                        fc.modifiers.remove(m)
                if len(fc.keyframe_points) > 1:
                    fc.keyframe_points.clear()
                    fc.keyframe_points.add(1)
                    fc.keyframe_points[0].co = (1.0, 0.0)

        # Rotation Wiggle
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
                mod.phase = props.rot_phase + spatial_offset + (idx * 1731.5)
                mod.use_influence = True
                mod.influence = props.rot_influence

                mod.use_restricted_range = props.use_restricted_range
                if props.use_restricted_range:
                    mod.frame_start = props.frame_start
                    mod.frame_end = props.frame_end
                    mod.blend_in = max(props.blend_in, 0.0)
                    mod.blend_out = max(props.blend_out, 0.0)
        else:
            fcurves = get_object_fcurves(ob)
            for fc in fcurves:
                if fc.data_path == "delta_rotation_euler":
                    mod = find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
                    if mod:
                        fc.modifiers.remove(mod)

        # Location Wiggle
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
                mod.phase = props.loc_phase + spatial_offset + 50000.0 + (idx * 1731.5)
                mod.use_influence = True
                mod.influence = props.loc_influence

                mod.use_restricted_range = props.use_restricted_range
                if props.use_restricted_range:
                    mod.frame_start = props.frame_start
                    mod.frame_end = props.frame_end
                    mod.blend_in = max(props.blend_in, 0.0)
                    mod.blend_out = max(props.blend_out, 0.0)
        else:
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
            wiggle_mods = [m for m in fc.modifiers if m.name.startswith(WIGGLE_MOD_PREFIX)]
            for m in wiggle_mods:
                fc.modifiers.remove(m)
            # If no modifiers left, clear multi-keyframes or mark for removal
            if len(fc.modifiers) == 0:
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
        # Check if cycles loop is active
        has_cycles = any(m.type == 'CYCLES' and m.name == WIGGLE_CYCLES_MOD for fc in fcurves for m in fc.modifiers)
        if has_cycles:
            props.enable_loop = True
            for fc in fcurves:
                if len(fc.keyframe_points) > 1:
                    props.loop_start = fc.keyframe_points[0].co[0]
                    props.loop_end = fc.keyframe_points[-1].co[0]
                    break

        has_rot = False
        for fc in fcurves:
            if fc.data_path == "delta_rotation_euler":
                mod = find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
                if mod and mod.type == 'NOISE':
                    props.rot_speed = mod.scale
                    props.rot_strength = mod.strength
                    props.rot_influence = mod.influence
                    if mod.use_restricted_range:
                        props.use_restricted_range = True
                        props.frame_start = mod.frame_start
                        props.frame_end = mod.frame_end
                        props.blend_in = mod.blend_in
                        props.blend_out = mod.blend_out
                    has_rot = True
                    break
        if not has_cycles:
            props.enable_rotation = has_rot

        has_loc = False
        for fc in fcurves:
            if fc.data_path == "delta_location":
                mod = find_wiggle_modifier(fc, WIGGLE_MOD_PREFIX)
                if mod and mod.type == 'NOISE':
                    props.loc_speed = mod.scale
                    props.loc_strength = mod.strength
                    props.loc_influence = mod.influence
                    if mod.use_restricted_range and not has_rot:
                        props.use_restricted_range = True
                        props.frame_start = mod.frame_start
                        props.frame_end = mod.frame_end
                        props.blend_in = mod.blend_in
                        props.blend_out = mod.blend_out
                    has_loc = True
                    break
        if not has_cycles:
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
        source_ob = getattr(self, "id_data", None)
        if source_ob and isinstance(source_ob, bpy.types.Object):
            if has_wiggle_modifiers(source_ob):
                apply_wiggle_to_object(source_ob, self)

        if context:
            active_ob = context.active_object
            selected_obs = context.selected_objects

            # Propagate to other selected objects if user adjusted the active object
            if source_ob == active_ob and selected_obs and len(selected_obs) > 1:
                for ob in selected_obs:
                    if ob != active_ob and has_wiggle_modifiers(ob):
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

                        ob_props.offset_mode = self.offset_mode
                        ob_props.offset_axis = self.offset_axis
                        ob_props.guide_object = self.guide_object
                        ob_props.spatial_scale = self.spatial_scale
                        ob_props.seed = self.seed
                        ob_props.use_unique_seed = self.use_unique_seed

                        ob_props.use_restricted_range = self.use_restricted_range
                        ob_props.frame_start = self.frame_start
                        ob_props.frame_end = self.frame_end
                        ob_props.blend_in = self.blend_in
                        ob_props.blend_out = self.blend_out

                        ob_props.enable_loop = self.enable_loop
                        ob_props.loop_start = self.loop_start
                        ob_props.loop_end = self.loop_end
                        ob_props.loop_repeat = self.loop_repeat

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

    # Restrict Frame Range Settings
    use_restricted_range: bpy.props.BoolProperty(
        name="Restrict Frame Range",
        description="Limit procedural wiggle noise to a specific frame range",
        default=False,
        update=on_prop_update,
    )
    frame_start: bpy.props.FloatProperty(
        name="Start",
        description="First frame to apply procedural wiggle noise",
        default=1.0,
        update=on_prop_update,
    )
    frame_end: bpy.props.FloatProperty(
        name="End",
        description="Last frame to apply procedural wiggle noise",
        default=250.0,
        update=on_prop_update,
    )
    blend_in: bpy.props.FloatProperty(
        name="Blend In",
        description="Number of frames to smoothly blend in wiggle from 0 to full strength",
        default=0.0,
        min=0.0,
        update=on_prop_update,
    )
    blend_out: bpy.props.FloatProperty(
        name="Blend Out",
        description="Number of frames to smoothly blend out wiggle from full strength to 0",
        default=0.0,
        min=0.0,
        update=on_prop_update,
    )

    # Seamless Loop Settings (No NLA required)
    enable_loop: bpy.props.BoolProperty(
        name="Seamless Loop",
        description="Generate a mathematically seamless looping noise cycle without NLA",
        default=False,
        update=on_prop_update,
    )
    loop_start: bpy.props.FloatProperty(
        name="Loop Start",
        description="First frame of the seamless loop cycle",
        default=1.0,
        update=on_prop_update,
    )
    loop_end: bpy.props.FloatProperty(
        name="Loop End",
        description="End frame of the seamless loop cycle (where cycle repeats)",
        default=100.0,
        update=on_prop_update,
    )
    loop_repeat: bpy.props.BoolProperty(
        name="Repeat Cycle",
        description="Repeat the loop cycle indefinitely before and after with an F-Curve Cycles modifier",
        default=True,
        update=on_prop_update,
    )

    # Offset & Spatial Mode Settings
    offset_mode: bpy.props.EnumProperty(
        name="Offset Mode",
        description="Spatial distribution method for noise phase offsets across objects",
        items=[
            ('RANDOM', "Per-Object (Random)", "Individual random phase offset per object (uncorrelated motion)"),
            ('LINEAR', "Directional Wave", "Wave offset travelling along a spatial axis (world or guide object)"),
            ('RADIAL', "Radial Ripple", "Expanding ripple waves based on distance from world origin or guide object"),
        ],
        default='RANDOM',
        update=on_prop_update,
    )
    offset_axis: bpy.props.EnumProperty(
        name="Axis",
        description="Direction axis for directional wave offset",
        items=[
            ('X', "X", "Wave along X axis"),
            ('Y', "Y", "Wave along Y axis"),
            ('Z', "Z", "Wave along Z axis"),
        ],
        default='X',
        update=on_prop_update,
    )
    guide_object: bpy.props.PointerProperty(
        type=bpy.types.Object,
        name="Guide / Origin Object",
        description="Optional reference object (e.g. Empty) to define the center or orientation of spatial waves",
        update=on_prop_update,
    )
    spatial_scale: bpy.props.FloatProperty(
        name="Spatial Scale",
        description="Controls wave density/frequency across distance (higher = tighter waves)",
        default=10.0,
        soft_min=-100.0,
        soft_max=100.0,
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
        name="Per-Object Variation",
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
        targets = [o for o in (context.selected_objects if context.selected_objects else [context.active_object]) if o is not None]
        if not targets:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        active_props = context.active_object.wiggle_props if context.active_object else None

        for ob in targets:
            if active_props and ob != context.active_object:
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

                ob_props.offset_mode = active_props.offset_mode
                ob_props.offset_axis = active_props.offset_axis
                ob_props.guide_object = active_props.guide_object
                ob_props.spatial_scale = active_props.spatial_scale
                ob_props.seed = active_props.seed
                ob_props.use_unique_seed = active_props.use_unique_seed

                ob_props.use_restricted_range = active_props.use_restricted_range
                ob_props.frame_start = active_props.frame_start
                ob_props.frame_end = active_props.frame_end
                ob_props.blend_in = active_props.blend_in
                ob_props.blend_out = active_props.blend_out

                ob_props.enable_loop = active_props.enable_loop
                ob_props.loop_start = active_props.loop_start
                ob_props.loop_end = active_props.loop_end
                ob_props.loop_repeat = active_props.loop_repeat

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
        targets = [o for o in (context.selected_objects if context.selected_objects else [context.active_object]) if o is not None]
        if not targets:
            self.report({'WARNING'}, "No objects selected")
            return {'CANCELLED'}

        count = 0
        for ob in targets:
            remove_wiggle_from_object(ob)
            count += 1

        self.report({'INFO'}, f"Wiggle removed from {count} object(s)")
        return {'FINISHED'}


class OBJECT_OT_wiggle_match_scene_range(bpy.types.Operator):
    """Match loop range to scene playback frame range"""
    bl_idname = "object.wiggle_match_scene_range"
    bl_label = "Match Scene Range"
    bl_description = "Set loop start and end frames from current scene playback range"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        targets = [o for o in (context.selected_objects if context.selected_objects else [context.active_object]) if o is not None]
        scene = context.scene
        for ob in targets:
            ob.wiggle_props.loop_start = scene.frame_start
            ob.wiggle_props.loop_end = scene.frame_end
            if ob.wiggle_props.enable_loop and has_wiggle_modifiers(ob):
                apply_wiggle_to_object(ob, ob.wiggle_props)

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
        targets = [o for o in (context.selected_objects if context.selected_objects else [context.active_object]) if o is not None]
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

        # Seamless Looping Box (Without NLA)
        loop_box = layout.box()
        loop_header = loop_box.row(align=True)
        loop_header.prop(props, "enable_loop", text="Seamless Looping (No NLA)", icon='FILE_REFRESH')

        if props.enable_loop:
            col = loop_box.column(align=True)
            row = col.row(align=True)
            row.prop(props, "loop_start")
            row.prop(props, "loop_end")
            row2 = col.row(align=True)
            row2.prop(props, "loop_repeat")
            row2.operator("object.wiggle_match_scene_range", text="Match Scene", icon='TIME')

        # Restrict Frame Range Box (Only if not looping)
        if not props.enable_loop:
            range_box = layout.box()
            range_header = range_box.row(align=True)
            range_header.prop(props, "use_restricted_range", text="Restrict Frame Range", icon='TIME')

            if props.use_restricted_range:
                col = range_box.column(align=True)
                row = col.row(align=True)
                row.prop(props, "frame_start")
                row.prop(props, "frame_end")
                row2 = col.row(align=True)
                row2.prop(props, "blend_in")
                row2.prop(props, "blend_out")

        # Variation & Spatial Offsets Box
        var_box = layout.box()
        var_box.label(text="Variation & Spatial Offsets", icon='RNDCURVE')
        col = var_box.column(align=True)
        col.prop(props, "offset_mode", text="")

        if props.offset_mode == 'RANDOM':
            seed_row = col.row(align=True)
            seed_row.prop(props, "seed")
            seed_row.operator("object.wiggle_reroll_seed", text="", icon='FILE_REFRESH')
            col.prop(props, "use_unique_seed")

        elif props.offset_mode == 'LINEAR':
            axis_row = col.row(align=True)
            axis_row.label(text="Direction Axis:")
            axis_row.prop(props, "offset_axis", expand=True)

            col.prop(props, "guide_object", text="Guide / Empty")
            col.prop(props, "spatial_scale")

            seed_row = col.row(align=True)
            seed_row.prop(props, "seed")
            seed_row.operator("object.wiggle_reroll_seed", text="", icon='FILE_REFRESH')

        elif props.offset_mode == 'RADIAL':
            col.prop(props, "guide_object", text="Origin / Empty")
            col.prop(props, "spatial_scale")

            seed_row = col.row(align=True)
            seed_row.prop(props, "seed")
            seed_row.operator("object.wiggle_reroll_seed", text="", icon='FILE_REFRESH')


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
    OBJECT_OT_wiggle_match_scene_range,
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
