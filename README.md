# Object Wiggle

A modern Blender 5.2+ extension that applies procedural noise modifiers to object delta transforms, enabling dynamic, organic secondary motion for single or multiple objects with full Slotted Action compatibility.

## Features

- **Blender 5.2+ Slotted Actions Support**: Fully compatible with Blender's animation architecture (`bpy_extras.anim_utils` slotted action channelbags and fallback support).
- **Multi-Object Editing**: Adjusting any slider or setting in the sidebar panel automatically updates and evaluates across all selected objects.
- **Bi-Directional Property Sync**: Selecting an object dynamically updates the UI to reflect its existing F-Curve modifier settings.
- **Dedicated Remove Wiggle**: One-click removal of procedural noise modifiers and delta animations from active or selected objects.
- **Distinct Modifier Names**: Automatically tags modifiers as `Wiggle Rotation` / `Wiggle Location` so custom user noise modifiers are preserved and never overwritten or deleted.
- **Channel Recovery**: Automatically restores and re-keys missing delta channels if one or more axis channels were deleted in the Graph Editor.
- **Glitch-Free Scrubbing**: Deterministic per-object and per-channel phase calculation prevents random pops while dragging sliders.
- **Per-Object Seed Variation**: Built-in per-object offsets ensure multiple selected objects wiggle independently without moving in identical unison.

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
4. Tweak **Speed**, **Strength**, **Phase Offset**, and **Influence** for Rotation and Location.
5. Use **Remove Wiggle** to clear procedural noise modifiers from selected objects.

## License

GNU General Public License v3.0 or later.
