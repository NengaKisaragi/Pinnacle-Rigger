"""Exercise real viewport projection and the modal drag event sequence in Blender."""
import sys
from pathlib import Path
from types import SimpleNamespace
import bpy
from mathutils import Vector, Quaternion, Matrix
from bpy_extras import view3d_utils
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mixamo_rigger
from mixamo_rigger import core
mixamo_rigger.register()
bpy.ops.wm.open_mainfile(filepath=str(Path(__import__('tempfile').gettempdir()) / 'mixamo-rigger-tests' / 'noufu_autorig.blend'))
bpy.ops.mr.edit_markers()
scene = bpy.context.scene
points = core.markers(scene.mr_settings.session)
# Explicit viewport matrices let headless Blender exercise the real projection
# helpers without requiring an OpenGL RegionView3D.update().
region = SimpleNamespace(type='WINDOW', x=0, y=0, width=1000, height=1000)
view = SimpleNamespace(is_perspective=False, view_perspective='ORTHO')
def orient(rotation):
    view.view_matrix = rotation.to_matrix().to_4x4().inverted() @ Matrix.Translation((0,0,-.87))
    view.perspective_matrix = Matrix.Diagonal((1.,1.,-.1,1.)) @ view.view_matrix
orient(Quaternion((1,0,0), 1.5707963267948966))
area = SimpleNamespace(type='VIEW_3D', regions=[region],
    spaces=SimpleNamespace(active=SimpleNamespace(region_3d=view)),
    header_text_set=lambda _: None, tag_redraw=lambda: None)
class Harness:
    invoke = mixamo_rigger.MRPlace.invoke
    modal = mixamo_rigger.MRPlace.modal
    finish = mixamo_rigger.MRPlace.finish
    def report(self, *_): pass
ctx = SimpleNamespace(area=area, scene=scene,
                      window_manager=SimpleNamespace(modal_handler_add=lambda _: None))
operator = Harness()
assert operator.invoke(ctx, None) == {'RUNNING_MODAL'}
def event(kind, pos, value='PRESS'):
    return SimpleNamespace(type=kind,value=value,mouse_x=pos.x+region.x,mouse_y=pos.y+region.y)
def pixel(key):
    return view3d_utils.location_3d_to_region_2d(region, view, points[key].location)
# Start with a right knee, rather than the old mandatory chin-first sequence.
key = 'Knee.R'
start = points[key].location.copy()
press = pixel(key) + Vector((6,3))
assert operator.modal(ctx,event('LEFTMOUSE',press)) == {'RUNNING_MODAL'}
assert operator.drag_key == key
assert points[key].location == start  # no snapping when grabbing off-center
operator.modal(ctx,event('MOUSEMOVE',press + Vector((-20,25)), 'NOTHING'))
assert (points[key].location-start).length > .001
assert abs(points[key].location.y-start.y) < 1e-5
low,high=core.bounds(core.sources(scene.mr_settings.session))
cx=0.0
assert abs(points['Knee.L'].location.x+points['Knee.R'].location.x-2*cx)<1e-6
assert abs(points['Knee.L'].location.z-points['Knee.R'].location.z)<1e-6
operator.modal(ctx,event('LEFTMOUSE',press,'RELEASE'))
committed=points[key].location.copy()
# A later drag can be cancelled without losing the committed previous drag.
press=pixel(key)
operator.modal(ctx,event('LEFTMOUSE',press))
operator.modal(ctx,event('MOUSEMOVE',press+Vector((15,20)),'NOTHING'))
assert operator.modal(ctx,event('ESC',press))=={'RUNNING_MODAL'}
assert (points[key].location-committed).length<1e-6
# Disable symmetry and verify independent editing.
scene.mr_settings.symmetry=False
opposite=points['Wrist.R'].location.copy()
press=pixel('Wrist.L')
operator.modal(ctx,event('LEFTMOUSE',press))
operator.modal(ctx,event('MOUSEMOVE',press+Vector((12,10)),'NOTHING'))
operator.modal(ctx,event('LEFTMOUSE',press,'RELEASE'))
assert points['Wrist.R'].location==opposite
# Changing to a side view lets a marker move in depth.
orient(Quaternion((0.5,0.5,0.5,0.5)))
start=points['Chin'].location.copy()
press=pixel('Chin')
operator.modal(ctx,event('LEFTMOUSE',press))
assert operator.drag_key=='Chin'
operator.modal(ctx,event('MOUSEMOVE',press+Vector((30,0)),'NOTHING'))
assert abs(points['Chin'].location.y-start.y)>.001
operator.modal(ctx,event('LEFTMOUSE',press,'RELEASE'))
assert operator.modal(ctx,event('RET',press))=={'FINISHED'}
print('DRAG_PASS: arbitrary order, grab offset, right-side symmetry, cancel, independent sides, side-view depth, finish')

# Native transforms must mirror through the depsgraph, outside MRPlace.
scene.mr_settings.symmetry=True
core.update_marker_constraints(scene)
core.select_only([points['Elbow.R']])
points['Elbow.R'].location = (-.30,.04,1.10)
bpy.context.view_layer.update()
assert (points['Elbow.L'].location-Vector((.30,.04,1.10))).length<1e-6
# Exercise Blender's transform operator (the path used by G and the gizmo).
core.select_only([points['Wrist.L']])
bpy.ops.transform.translate(value=(.05,.02,.03))
bpy.context.view_layer.update()
l,r=points['Wrist.L'].location,points['Wrist.R'].location
assert (r-Vector((-l.x,l.y,l.z))).length<1e-6
# Right-side native movement must also work with no selected marker.
core.select_only([points['Knee.R']])
points['Knee.R'].location.z += .1
bpy.context.view_layer.update()
assert abs(points['Knee.L'].location.z-points['Knee.R'].location.z)<1e-6
scene.mr_settings.symmetry=False
right=points['Knee.R'].location.copy()
points['Knee.L'].location.z+=.1
bpy.context.view_layer.update()
assert points['Knee.R'].location==right
for key in ('Chin','Groin'):
    points[key].location.x=.25
bpy.context.view_layer.update()
for key in ('Chin','Groin'):
    assert points[key].location.x==0.0
    assert points[key].lock_location[0]
    core.move_landmark(points,key,(.3,.02,.8),False,4.0)
    assert points[key].location.x==0.0
# Clean registration lifecycle must never accumulate duplicate handlers.
assert bpy.app.handlers.depsgraph_update_post.count(mixamo_rigger.maintain_markers)==1
mixamo_rigger.unregister()
assert mixamo_rigger.maintain_markers not in bpy.app.handlers.depsgraph_update_post
mixamo_rigger.register()
assert bpy.app.handlers.depsgraph_update_post.count(mixamo_rigger.maintain_markers)==1
print('NATIVE_SYMMETRY_PASS: direct transforms, Blender translate, right-side changes, symmetry off, unconditional center locks, handler lifecycle')
