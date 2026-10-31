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
import pinnacle_rigger
from pinnacle_rigger import core
pinnacle_rigger.register()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
REFERENCE = Path(os.environ.get('PINNACLE_RIGGER_REFERENCE', ROOT / 'tests' / 'fixtures'))
OUTPUT_DIR = Path(tempfile.gettempdir()) / 'pinnacle-rigger-tests'
OUTPUT_DIR.mkdir(exist_ok=True)
bpy.ops.import_scene.fbx(filepath=str(REFERENCE / 'noufu.fbx'))
source = next(o for o in bpy.context.selected_objects if o.type == 'MESH')
source_positions = [source.matrix_world @ v.co for v in source.data.vertices]
low, high = core.bounds([source])
core.create_markers(bpy.context)
rig, report = core.build(bpy.context)
bpy.context.scene.mr_settings.rig = rig
bpy.context.scene.mr_settings.status = report
assert len(rig.data.bones) == 25
output = next(o for o in bpy.context.scene.objects if o.get('mr_output') == rig.name)
assert not any(o.name == 'body' for o in bpy.context.scene.objects)
assert not bpy.context.scene.mr_settings.session
assert not any(c.name.startswith('AutoRig · Markers') for c in bpy.data.collections)
assert len(output.data.vertices) == 1487
assert all(abs(sum(g.weight for g in v.groups) - 1) < 1e-4 for v in output.data.vertices)
assert all(v.groups for v in output.data.vertices)
# Generated output retains the source mesh's rest pose after the source object is removed.
assert max((p - v.co).length for p, v in zip(source_positions, output.data.vertices)) < 1e-5
rest = [v.co.copy() for v in output.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]
# Raise/lower one arm; the opposite hand and lower legs should stay put.
bone = rig.pose.bones['mixamorig:LeftArm']
bone.rotation_mode = 'XYZ'
bone.rotation_euler.z = math.radians(35)
bpy.context.view_layer.update()
evaluated = output.evaluated_get(bpy.context.evaluated_depsgraph_get())
deltas = [(v.co - p).length for v, p in zip(evaluated.data.vertices, rest)]
h = high.z - low.z
left_hand = [d for p, d in zip(rest, deltas) if p.x > (low.x + high.x) / 2 + .35 * (high.x - low.x)]
right_hand = [d for p, d in zip(rest, deltas) if p.x < (low.x + high.x) / 2 - .35 * (high.x - low.x)]
feet = [d for p, d in zip(rest, deltas) if p.z < low.z + h * .15]
assert max(left_hand) > h * .04, max(left_hand)
assert max(right_hand) < h * .03, max(right_hand)
assert max(feet) < h * .03, max(feet)
bone.rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()
# Save generated output only to a temp fixture for subsequent input coverage.
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / 'noufu_autorig.blend'))
# Compare reference names and weight coverage, without copying any weights.
bpy.ops.import_scene.fbx(filepath=str(REFERENCE / 'T-Pose.fbx'))
reference_rig = next(o for o in bpy.context.selected_objects if o.type == 'ARMATURE')
common = set(rig.data.bones.keys()) & set(reference_rig.data.bones.keys())
assert len(common) == 25
bpy.ops.wm.read_factory_settings(use_empty=True)
imported = core.import_blend(str(OUTPUT_DIR / 'noufu_autorig.blend'), bpy.context)
assert len(imported) == 1
assert len(imported[0].data.vertices) == 1487
assert any(m.type == 'ARMATURE' and m.object and len(m.object.data.bones) == 25 for m in imported[0].modifiers)
# Native .blend importer and transformed/multiple-mesh input.
bpy.ops.wm.read_factory_settings(use_empty=True)
imported = core.import_blend(str(OUTPUT_DIR / 'noufu_autorig.blend'), bpy.context)
assert len(imported) == 1
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
