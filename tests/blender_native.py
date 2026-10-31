import sys, math
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import mixamo_rigger
from mixamo_rigger import core
mixamo_rigger.register()
bpy.ops.wm.read_factory_settings(use_empty=True)
source_path=str(REFERENCE / 'noufu_R04.blend')
objects=core.import_blend(source_path,bpy.context)
print('NATIVE_INPUT',[(o.name,len(o.data.vertices),list(o.dimensions)) for o in objects], flush=True)
core.create_markers(bpy.context)
rig,report=core.build(bpy.context)
print('NATIVE_PASS',report,flush=True)
assert len(rig.data.bones)==25
# Multiple transformed meshes, non-uniform scale, translated away from origin.
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(REFERENCE / 'noufu.fbx'))
obj=bpy.context.selected_objects[0]
obj.location=(3,2,1)
obj.scale=(1.2,.8,1.1)
bpy.context.view_layer.update()
# Split the actual model into two disjoint objects at the waist.
import bmesh
for upper in (False,True):
    data=obj.data.copy()
    bm=bmesh.new();bm.from_mesh(data)
    remove=[v for v in bm.verts if (v.co.z>.9)==upper]
    bmesh.ops.delete(bm,geom=remove,context='VERTS')
    bm.to_mesh(data);bm.free()
    part=bpy.data.objects.new('split_model',data)
    bpy.context.scene.collection.objects.link(part)
    part.matrix_world=obj.matrix_world.copy()
bpy.data.objects.remove(obj,do_unlink=True)
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
original={o.name:[o.matrix_world@v.co for v in o.data.vertices] for o in meshes}
core.select_only(meshes)
core.create_markers(bpy.context)
rig,report=core.build(bpy.context)
outputs=[o for o in bpy.context.scene.objects if o.get('mr_output')==rig.name]
assert len(outputs)==2
assert all(v.groups and abs(sum(g.weight for g in v.groups)-1)<1e-4 for o in outputs for v in o.data.vertices)
for o in outputs:
    name=o.name.split(' · Rigged')[0]
    assert max((p-v.co).length for p,v in zip(original[name],o.data.vertices))<1e-5
# Force uncovered vertices to exercise explicit fallback, not just bone heat.
for o in outputs:
    for g in list(o.vertex_groups):o.vertex_groups.remove(g)
low,high=core.bounds(meshes)
points={k:o.location.copy() for k,o in core.markers(bpy.context.scene.mr_settings.session).items()}
specs=core.skeleton(points,low,high)
repaired=sum(core.bind_fallback(o,rig,specs,high.z-low.z) for o in outputs)
assert repaired==sum(len(o.data.vertices) for o in outputs)
assert all(abs(sum(g.weight for g in v.groups)-1)<1e-4 for o in outputs for v in o.data.vertices)
print('TRANSFORM_MULTI_FALLBACK_PASS',report,'forced fallback',repaired,flush=True)
