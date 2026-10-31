"""Run with blender -b --factory-startup --python tests/blender_smoke.py."""
import sys
from pathlib import Path
import json
import math
import os
import tempfile
import bpy
from mathutils import Vector
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mixamo_rigger
from mixamo_rigger import core
mixamo_rigger.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
REFERENCE = Path(os.environ.get('MIXAMO_RIGGER_REFERENCE', ROOT / 'tests' / 'fixtures'))
OUTPUT_DIR = Path(tempfile.gettempdir()) / 'mixamo-rigger-tests'
OUTPUT_DIR.mkdir(exist_ok=True)
bpy.ops.import_scene.fbx(filepath=str(REFERENCE / 'noufu.fbx'))
source = next(o for o in bpy.context.selected_objects if o.type == 'MESH')
source_positions = [source.matrix_world @ v.co for v in source.data.vertices]
core.create_markers(bpy.context)
rig, report = core.build(bpy.context)
bpy.context.scene.mr_settings.rig = rig
bpy.context.scene.mr_settings.status = report
assert len(rig.data.bones) == 25
assert len(source.modifiers) == 0
assert all((p - source.matrix_world @ v.co).length < 1e-7 for p, v in zip(source_positions, source.data.vertices))
output = next(o for o in bpy.context.scene.objects if o.get('mr_output') == rig.name)
assert len(output.data.vertices) == 1487
assert all(abs(sum(g.weight for g in v.groups) - 1) < 1e-4 for v in output.data.vertices)
assert all(v.groups for v in output.data.vertices)
# Rest pose remains at its input world position.
assert max((p - v.co).length for p, v in zip(source_positions, output.data.vertices)) < 1e-5
rest = [v.co.copy() for v in output.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
# Raise/lower one arm; the opposite hand and lower legs should stay put.
bone = rig.pose.bones['mixamorig:LeftArm']
bone.rotation_mode = 'XYZ'
bone.rotation_euler.z = math.radians(35)
bpy.context.view_layer.update()
evaluated = output.evaluated_get(bpy.context.evaluated_depsgraph_get())
deltas = [(v.co - p).length for v, p in zip(evaluated.data.vertices, rest)]
low, high = core.bounds([source])
h = high.z - low.z
left_hand = [d for p, d in zip(rest, deltas) if p.x > (low.x + high.x) / 2 + .35 * (high.x - low.x)]
right_hand = [d for p, d in zip(rest, deltas) if p.x < (low.x + high.x) / 2 - .35 * (high.x - low.x)]
feet = [d for p, d in zip(rest, deltas) if p.z < low.z + h * .15]
assert max(left_hand) > h * .04, max(left_hand)
assert max(right_hand) < h * .03, max(right_hand)
assert max(feet) < h * .03, max(feet)
bone.rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()
# Store a useful default view in the example.
from mathutils import Quaternion
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_rotation = Quaternion((1,0,0), math.pi/2)
            area.spaces.active.region_3d.view_perspective = 'ORTHO'
            area.spaces.active.region_3d.view_location = Vector((0,0,.87))
            area.spaces.active.region_3d.view_distance = 3.2
            area.spaces.active.overlay.show_floor = False
            area.spaces.active.show_region_ui = True
# Save actual ready-to-inspect example; imported references are never overwritten.
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / 'noufu_autorig.blend'))
# Save the editable working copy produced by the UI, without changing current path.
portable = OUTPUT_DIR / 'noufu_working_copy.blend'
if portable.exists():
    portable.unlink()
result = bpy.ops.mr.save_result(filepath=str(portable))
assert result == {'FINISHED'}
try:
    bpy.ops.mr.save_result(filepath=str(portable))
except RuntimeError as exc:
    assert '上書き防止' in str(exc)
else:
    raise AssertionError('overwrite was allowed')
# Compare reference names and weight coverage, without copying any weights.
bpy.ops.import_scene.fbx(filepath=str(REFERENCE / 'T-Pose.fbx'))
reference_rig = next(o for o in bpy.context.selected_objects if o.type == 'ARMATURE')
common = set(rig.data.bones.keys()) & set(reference_rig.data.bones.keys())
assert len(common) == 25
bpy.ops.wm.read_factory_settings(use_empty=True)
imported = core.import_blend(str(portable), bpy.context)
assert len(imported) == 2
assert len(imported[0].data.vertices) == 1487
assert any(m.type == 'ARMATURE' and m.object and len(m.object.data.bones) == 25 for o in imported for m in o.modifiers)
# Native .blend importer and transformed/multiple-mesh input.
bpy.ops.wm.read_factory_settings(use_empty=True)
imported = core.import_blend(str(OUTPUT_DIR / 'noufu_autorig.blend'), bpy.context)
assert len(imported) == 2
# Reject invalid landmarks without leaving partial results.
core.select_only(imported[:1])
for o in imported:
    if 'mr_source' in o:
        del o['mr_source']
    if 'mr_output' in o:
        del o['mr_output']
core.create_markers(bpy.context)
points = core.markers(bpy.context.scene.mr_settings.session)
points['Chin'].location.z = points['Groin'].location.z - 1
before = len(bpy.data.objects)
try:
    core.build(bpy.context)
except ValueError:
    pass
else:
    raise AssertionError('invalid landmarks accepted')
assert len(bpy.data.objects) == before
print('SMOKE_PASS', json.dumps({'bones': 25, 'vertices': 1487, 'matching_reference_names': len(common), 'report': report,
      'left_hand_motion': max(left_hand), 'opposite_hand_motion': max(right_hand), 'foot_motion': max(feet)}, ensure_ascii=False))
