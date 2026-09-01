# Object Wiggle

> [!NOTE]
> **This extension has been incorporated into [Noise Wiggler](https://github.com/m-dr/blender-noise-wiggler)** — a unified extension combining both Object Wiggle and Armature/Bone Wiggle into a single interface with hierarchy falloff curves, motion presets, and dual-mode editing.

A modern Blender 5.2+ extension that applies procedural noise transforms to object delta transforms, enabling dynamic, organic secondary motion for single or multiple objects with full Slotted Action compatibility, seamless loops (without NLA), frame ranges, and spatial wave offsets.

## Features

- **Blender 5.2+ Slotted Actions Support**: Fully compatible with Blender's animation architecture (`bpy_extras.anim_utils` slotted action channelbags and fallback support).
- **Multi-Object Editing**: Adjusting any slider or setting in the sidebar panel automatically updates and evaluates across all selected objects.
- **Seamless Looping (No NLA)**: Generates 100% mathematically seamless circular periodic noise loops between custom Start/End frames with optional continuous cycle repetition via F-Curve Cycles modifier.
- **Restrict Frame Range**: Limit procedural wiggle motion to a specific frame range with smooth **Blend In** and **Blend Out** transitions (unified across location and rotation).
- **Spatial & World-Space Offset Modes**:
  - **Per-Object (Random)**: Independent deterministic noise phase offset per object (prevents in-sync lockstep motion).
  - **Directional Wave**: Wave offset traveling along World X, Y, or Z (or relative to a chosen Guide Object/Empty).
  - **Radial Ripple**: Expanding circular/spherical ripple waves emanating outward from the World Origin `(0, 0, 0)` or a designated Guide Object.
- **Guide / Reference Object Support**: Pick an Empty or reference object to interactively orient or translate the epicenter of spatial waves across the scene (works across complex parent hierarchies).
- **Bi-Directional Property Sync**: Selecting an object dynamically updates the UI to reflect its existing F-Curve modifier settings.
- **Dedicated Remove Wiggle**: One-click removal of procedural noise modifiers and delta animations from active or selected objects.
- **Distinct Modifier Names**: Automatically tags modifiers as `Wiggle Rotation` / `Wiggle Location` / `Wiggle Cycles` so custom user noise modifiers are preserved and never overwritten or deleted.
- **Channel Recovery**: Automatically restores and re-keys missing delta channels if one or more axis channels were deleted in the Graph Editor.
- **Glitch-Free Scrubbing**: Deterministic per-object and per-channel phase calculation prevents random pops while dragging sliders.

## Installation

### As an Extension (Blender 4.2+)
1. Download the latest `.zip` release package from Releases.
2. In Blender, go to **Edit > Preferences > Get Extensions**.
3. Click the top-right dropdown menu and choose **Install from Disk...**.
4. Select the `.zip` file.

## Usage

1. Select one or more objects in the 3D Viewport.
2. Open the Sidebar (**N** panel) and navigate to the **Wiggle** tab.
3. Click **Wiggle it!** to apply procedural motion.
4. **Seamless Looping**:
   - Check **Seamless Looping (No NLA)** to generate a periodic cycle.
   - Adjust **Loop Start** and **Loop End** frames, or click **Match Scene** to fit the timeline.
   - Enable **Repeat Cycle** to loop indefinitely across the entire timeline.
5. **Frame Range**:
   - Enable **Restrict Frame Range** to specify **Start**, **End**, **Blend In**, and **Blend Out** frame limits.
6. Choose an **Offset Mode** under *Variation & Spatial Offsets*:
   - Use **Per-Object (Random)** for individual chaotic motion.
   - Use **Directional Wave** or **Radial Ripple** with an optional **Guide Empty** for spatial waves.
7. Tweak **Speed**, **Strength**, **Phase Offset**, and **Influence** for Rotation and Location.
8. Use **Remove Wiggle** to clear procedural noise modifiers from selected objects.

## License

GNU General Public License v3.0 or later.
