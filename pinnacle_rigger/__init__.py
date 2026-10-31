bl_info = {
    'name': 'Pinnacle Rigger', 'author': 'Pinnacle Rigger contributors',
    'version': (1, 0, 0), 'blender': (4, 2, 0), 'location': '3D View > Sidebar > Pinnacle-Rigger',
    'description': 'Place landmarks and generate a local humanoid rig',
    'category': 'Rigging',
}

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Vector, Quaternion
from . import core
from bpy.app.handlers import persistent


def symmetry_changed(settings, context):
    core.sync_symmetry(context, scene=settings.id_data)
    core.update_marker_constraints(settings.id_data)


@persistent
def maintain_markers(scene, depsgraph):
    core.update_marker_constraints(scene)


@persistent
def marker_file_loaded(_):
    core._marker_positions.clear()
    for scene in bpy.data.scenes:
        core.update_marker_constraints(scene)


def initialize_markers():
    # addon_utils.enable() registers under RestrictBlend: bpy.data.scenes is
    # deliberately unavailable until registration has returned to Blender.
    if not hasattr(bpy.data, 'scenes'):
        return 0.1
    marker_file_loaded(None)
    return None


class MRSettings(bpy.types.PropertyGroup):
    symmetry: BoolProperty(name='左右対称', default=True, update=symmetry_changed)
    hair_enabled: BoolProperty(name='髪', default=False)
    hair_bones: IntProperty(name='髪のボーン数', default=3, min=3, max=6)
    skirt_bones: IntProperty(name='スカートの分割数', default=3, min=3, max=6)
    breasts_enabled: BoolProperty(name='胸', default=False)
    skirt_enabled: BoolProperty(name='スカート', default=False)
    finger_level: EnumProperty(
        name='指', default='0',
        items=[('0', 'No Fingers (25)', '指ボーンなし'),
               ('2', '2 Chain Fingers (41)', '親指と共通指チェーン'),
               ('3', '3 Chain Fingers (49)', '親指・人差し指・小指のチェーン'),
               ('5', 'Standard Skeleton (65)', '5本の指チェーン')])
    status: StringProperty(default='対象メッシュを選択してください')
    session: StringProperty()
    rig: PointerProperty(type=bpy.types.Object)


class MRMarkers(bpy.types.Operator):
    bl_idname = 'pr.create_markers'
    bl_label = '選択メッシュからマーカーを作成'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            core.create_markers(context)
            if context.space_data.type == 'VIEW_3D':
                region = context.space_data.region_3d
                region.view_rotation = Quaternion((1, 0, 0), 1.5707963267948966)
                region.view_perspective = 'ORTHO'
                center, height = core.session_bounds(context.scene.mr_settings.session)
                region.view_location = center
                region.view_distance = height * 1.8
                bpy.ops.pr.place_markers('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class MRPlace(bpy.types.Operator):
    bl_idname = 'pr.place_markers'
    bl_label = 'マーカーをドラッグで配置'
    bl_description = '色付きの輪を自由な順番でドラッグ。Enterで完了、Escでドラッグを取り消し'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    def invoke(self, context, event):
        if not context.area or context.area.type != 'VIEW_3D':
            return {'CANCELLED'}
        core.update_marker_constraints(context.scene)
        self.points = core.markers(context.scene.mr_settings.session)
        if not any(not obj.hide_get() for obj in self.points.values()):
            self.report({'ERROR'}, '先にマーカーを作成してください')
            return {'CANCELLED'}
        self.area = context.area
        self.region = next(r for r in self.area.regions if r.type == 'WINDOW')
        self.drag_key = None
        self.snapshot = None
        self.low, self.high = core.bounds(core.sources(context.scene.mr_settings.session))
        self.area.header_text_set('輪をドラッグ（順番自由） / Enter: 完了 / Esc: 移動を取消・終了')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        self.area.header_text_set(None)
        self.area.tag_redraw()
        context.scene.mr_settings.status = '配置完了。側面から奥行きも確認してください'
        return {'FINISHED'}

    def modal(self, context, event):
        from bpy_extras import view3d_utils
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            if self.drag_key is not None:
                for key, location in self.snapshot.items():
                    self.points[key].location = location
                self.drag_key = None
                self.snapshot = None
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            return self.finish(context)
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            return self.finish(context)
        coord = Vector((event.mouse_x - self.region.x, event.mouse_y - self.region.y))
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if not (0 <= coord.x < self.region.width and 0 <= coord.y < self.region.height):
                return {'PASS_THROUGH'}
            hits = []
            for key, obj in self.points.items():
                if obj.hide_get():
                    continue
                pos = view3d_utils.location_3d_to_region_2d(self.region, self.area.spaces.active.region_3d, obj.location)
                if pos is not None and (coord - pos).length <= 20:
                    hits.append(((coord - pos).length, key))
            if hits:
                self.drag_key = min(hits)[1]
                self.snapshot = {key: obj.location.copy() for key, obj in self.points.items()}
                self.start_location = self.points[self.drag_key].location.copy()
                self.start_mouse_world = view3d_utils.region_2d_to_location_3d(
                    self.region, self.area.spaces.active.region_3d, coord, self.start_location)
                return {'RUNNING_MODAL'}
            # Let Blender's native selection and transform tools receive clicks
            # that did not start a custom marker drag.
            return {'PASS_THROUGH'}
        if event.type == 'MOUSEMOVE' and self.drag_key is not None:
            position = view3d_utils.region_2d_to_location_3d(
                self.region, self.area.spaces.active.region_3d, coord, self.start_location)
            location = self.start_location + position - self.start_mouse_world
            core.move_landmark(self.points, self.drag_key, location,
                               context.scene.mr_settings.symmetry, (self.low.x + self.high.x) / 2)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.drag_key is None:
                return {'PASS_THROUGH'}
            self.drag_key = None
            self.snapshot = None
            return {'RUNNING_MODAL'}
        if self.drag_key is None and (event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
                                                   'TRACKPADPAN', 'TRACKPADZOOM'} or event.type.startswith('NUMPAD_')):
            return {'PASS_THROUGH'}
        if self.drag_key is None:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}


class MRClearMarkers(bpy.types.Operator):
    bl_idname = 'pr.clear_markers'
    bl_label = 'マーカーを全消去'
    bl_description = '現在のセッションのマーカーを消し、対象メッシュを選び直します'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.mr_settings
        session = settings.session
        points = core.markers(session, context.scene)
        source_meshes = core.sources(session, context.scene)
        marker_collections = {collection for marker in points.values() for collection in marker.users_collection}
        if not points:
            self.report({'INFO'}, '消去するマーカーはありません')
            return {'CANCELLED'}
        for marker in points.values():
            bpy.data.objects.remove(marker, do_unlink=True)
        for source in source_meshes:
            source.pop('mr_source', None)
            source.hide_set(False)
        for collection in marker_collections:
            if collection.users == 0 or (not collection.objects and not collection.children):
                bpy.data.collections.remove(collection)
        settings.session = ''
        settings.rig = None
        settings.status = 'マーカーを消去しました。オプションを選び直して再作成できます'
        meshes = source_meshes
        if meshes:
            core.select_only(meshes)
        return {'FINISHED'}


class MRBuild(bpy.types.Operator):
    bl_idname = 'pr.build_rig'
    bl_label = 'リグを生成（自動ウェイト）'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            rig, report = core.build(context)
            context.scene.mr_settings.rig = rig
            context.scene.mr_settings.status = report
            self.report({'INFO'}, report)
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class MRPanel(bpy.types.Panel):
    bl_label = 'Pinnacle-Rigger'
    bl_idname = 'PR_PT_main'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Pinnacle-Rigger'

    def draw(self, context):
        layout = self.layout
        settings = context.scene.mr_settings
        layout.label(text='01 / モデル', icon='MESH_DATA')
        layout.label(text='Tポーズ / Z上 / 正面は −Y')
        layout.label(text='対象メッシュをすべて選択')
        header, options = layout.panel('mr_optional_rig_options', default_closed=True)
        header.label(text='オプション', icon='OUTLINER_OB_ARMATURE')
        if options:
            options.prop(settings, 'hair_enabled', text='Hair')
            hair_row = options.row()
            hair_row.enabled = settings.hair_enabled
            hair_row.prop(settings, 'hair_bones', text='Start〜End')
            options.prop(settings, 'breasts_enabled', text='Breast')
            options.prop(settings, 'skirt_enabled', text='Skirt Front / Back')
            skirt_row = options.row()
            skirt_row.enabled = settings.skirt_enabled
            skirt_row.prop(settings, 'skirt_bones', text='Front / Back')
            options.prop(settings, 'finger_level', text='指')
        layout.operator('pr.create_markers')
        layout.operator('pr.clear_markers', icon='TRASH')
        box = layout.box()
        box.label(text='02 / マーカー', icon='EMPTY_AXIS')
        box.prop(settings, 'symmetry')
        box.label(text='輪をドラッグ / Enterで完了')
        box.label(text='顎 / 手首 / 肘 / 膝 / 股')
        box.label(text='対称ON: 通常の移動でも左右が追従')
        box.label(text='Chin / Groin は常に X = 0')
        layout.label(text='03 / 骨格 + ウェイト', icon='ARMATURE_DATA')
        layout.label(text=f'{int(settings.finger_level) * 8 + 25} bones + オプション')
        layout.operator('pr.build_rig', icon='MOD_ARMATURE')
        layout.separator()
        for part in settings.status.split(' / '):
            layout.label(text=part)
        layout.label(text='Pinnacle Rigger · ver1.0')


classes = (MRSettings, MRMarkers, MRPlace, MRClearMarkers, MRBuild, MRPanel)


_draw_handle = None


def draw_landmarks():
    import gpu
    import blf
    import math
    from gpu_extras.batch import batch_for_shader
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    context = bpy.context
    if not context.region_data or not hasattr(context.scene, 'mr_settings'):
        return
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(2.5)
    try:
        for key, obj in core.markers(context.scene.mr_settings.session).items():
            if obj.hide_get():
                continue
            pos = location_3d_to_region_2d(context.region, context.region_data, obj.location)
            if pos is None:
                continue
            coords = [(pos.x + 13 * math.cos(i * math.tau / 40), pos.y + 13 * math.sin(i * math.tau / 40)) for i in range(41)]
            color = core.COLORS[key.split('.')[0]]
            batch = batch_for_shader(shader, 'LINE_STRIP', {'pos': coords})
            shader.bind()
            shader.uniform_float('color', color)
            batch.draw(shader)
            blf.position(0, pos.x + 17, pos.y - 4, 0)
            blf.size(0, 12)
            blf.color(0, *color)
            blf.draw(0, key)
    finally:
        gpu.state.line_width_set(1)
        gpu.state.blend_set('NONE')


def register():
    global _draw_handle
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mr_settings = PointerProperty(type=MRSettings)
    bpy.app.handlers.depsgraph_update_post.append(maintain_markers)
    bpy.app.handlers.load_post.append(marker_file_loaded)
    bpy.app.timers.register(initialize_markers, first_interval=0.0)
    if not bpy.app.background:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(draw_landmarks, (), 'WINDOW', 'POST_PIXEL')


def unregister():
    global _draw_handle
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW')
        _draw_handle = None
    if maintain_markers in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(maintain_markers)
    if marker_file_loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(marker_file_loaded)
    if bpy.app.timers.is_registered(initialize_markers):
        bpy.app.timers.unregister(initialize_markers)
    core._marker_positions.clear()
    del bpy.types.Scene.mr_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
