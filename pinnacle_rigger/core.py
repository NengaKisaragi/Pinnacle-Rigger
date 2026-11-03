"""World-space landmark rigging. No network, external models or reference-rig dependency."""
import uuid
import math
import bpy
from mathutils import Vector

PREFIX = 'mixamorig:'
COLORS = {'Chin': (0, .85, .85, 1), 'Wrist': (.55, .9, .15, 1),
          'Elbow': (1, .85, .2, 1), 'Knee': (1, .45, .1, 1), 'Groin': (1, .2, .5, 1),
          'Hair': (.25, .75, 1, 1), 'Breast': (1, .35, .65, 1),
          'SkirtFront': (1, .55, .18, 1), 'SkirtBack': (.75, .4, 1, 1)}


def object_mode():
    if bpy.context.object and bpy.context.object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def select_only(objects, active=None):
    object_mode()
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active or objects[0]


def import_blend(path, context):
    if not path.lower().endswith('.blend'):
        raise ValueError('.blend ファイルを選択してください')
    # Append rather than open: the user's current scene is preserved.
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = src.objects
    objects = [o for o in dst.objects if o]
    meshes = [o for o in objects if o.type == 'MESH' and len(o.data.vertices)]
    if not meshes:
        for obj in objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        raise ValueError('メッシュが含まれていません')
    collection = bpy.data.collections.new('AutoRig · Imported')
    context.scene.collection.children.link(collection)
    for obj in objects:
        collection.objects.link(obj)
        for key in list(obj.keys()):
            if key.startswith('mr_'):
                del obj[key]
        obj.hide_set(obj.type != 'MESH')
    select_only(meshes)
    return meshes


def sources(session, scene=None):
    return [o for o in (scene or bpy.context.scene).objects if o.get('mr_source') == session]


def markers(session, scene=None):
    return {o['mr_landmark']: o for o in (scene or bpy.context.scene).objects
            if o.get('mr_session') == session and 'mr_landmark' in o}


def bounds(objects):
    points = [o.matrix_world @ Vector(p) for o in objects for p in o.bound_box]
    low = Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in points) for i in range(3)))
    return low, high


def session_bounds(session):
    low, high = bounds(sources(session))
    return (low + high) * .5, high.z - low.z


def create_markers(context):
    object_mode()
    meshes = [o for o in context.selected_objects if o.type == 'MESH' and len(o.data.vertices)]
    if not meshes:
        raise ValueError('対象メッシュを選択してください')
    if any(o.get('mr_output') for o in meshes):
        raise ValueError('生成済みのモデルではなく元モデルを選択してください')
    # Existing sessions remain editable; starting one twice on the same source
    # would otherwise orphan its marker set.
    if any(o.get('mr_source') for o in meshes):
        session_ids = {o.get('mr_source') for o in meshes}
        if len(session_ids) == 1 and None not in session_ids and markers(next(iter(session_ids))):
            context.scene.mr_settings.session = next(iter(session_ids))
            context.scene.mr_settings.status = '既存のマーカーを再使用します'
            return
        raise ValueError('異なるセッションのメッシュが含まれています')
    low, high = bounds(meshes)
    width, depth, height = high - low
    if height <= 1e-6 or width <= 1e-6:
        raise ValueError('高さまたは幅がありません')
    if width / height > 1.6 or width / height < .35:
        raise ValueError('Z上向きのTポーズにしてください。回転を適用して再実行してください')
    session = uuid.uuid4().hex
    context.scene.mr_settings.session = session
    collection = bpy.data.collections.new('AutoRig · Markers')
    context.scene.collection.children.link(collection)
    cx, cy = (low.x + high.x) / 2, (low.y + high.y) / 2
    initial = {'Chin': (0, .79), 'Groin': (0, .50), 'Wrist.L': (.39, .73),
               'Elbow.L': (.255, .73), 'Knee.L': (.08, .27)}
    initial.update({key.replace('.L', '.R'): (-x, z) for key, (x, z) in list(initial.items()) if key.endswith('.L')})
    for name, (x, z) in initial.items():
        obj = bpy.data.objects.new('MR · ' + name, None)
        collection.objects.link(obj)
        obj.location = (x * width, cy, low.z + z * height)
        if name in {'Chin', 'Groin'}:
            obj.lock_location[0] = True
        obj.empty_display_type = 'SPHERE'
        obj.empty_display_size = height * .018
        obj.show_in_front = True
        obj.show_name = False
        obj.color = COLORS[name.split('.')[0]]
        obj['mr_session'] = session
        obj['mr_landmark'] = name
    settings = context.scene.mr_settings
    optional = {}
    if settings.hair_enabled:
        optional.update({'Hair.Start': (0, .90, .08), 'Hair.End': (0, .76, .30)})
    if settings.breasts_enabled:
        optional.update({'Breast.L': (.105, .68, -.22), 'Breast.R': (-.105, .68, -.22)})
    if settings.skirt_enabled:
        optional.update({'SkirtFront.L': (.10, .50, -.22), 'SkirtFront.R': (-.10, .50, -.22),
                         'SkirtBack.L': (.10, .50, .22), 'SkirtBack.R': (-.10, .50, .22)})
    for name, (x, z, depth_fraction) in optional.items():
        obj = bpy.data.objects.new('MR · ' + name, None)
        collection.objects.link(obj)
        obj.location = (x * width, cy + depth_fraction * depth, low.z + z * height)
        if name.startswith('Hair.'):
            obj.lock_location[0] = True
        obj.empty_display_type = 'SPHERE'
        obj.empty_display_size = height * .018
        obj.show_in_front = True
        obj.show_name = False
        obj.color = COLORS[name.split('.')[0]]
        obj['mr_session'] = session
        obj['mr_landmark'] = name
    for obj in meshes:
        obj['mr_source'] = session
    select_only([markers(session)['Chin']])
    context.scene.mr_settings.status = 'マーカーを体の関節中心へ配置 / 側面から奥行きも確認'


def move_landmark(points, key, location, symmetry, center_x):
    """Drag either side while preserving depth and mirroring the other side."""
    location = Vector(location)
    if key in {'Chin', 'Groin'}:
        location.x = 0.0
        points[key].lock_location[0] = True
    points[key].location = location
    if symmetry and key.endswith(('.L', '.R')):
        other = key[:-2] + ('.R' if key.endswith('.L') else '.L')
        points[other].location = Vector((-location.x, location.y, location.z))


def constrain_center(points):
    for key in ('Chin', 'Groin', 'Hair.Start', 'Hair.End'):
        if key in points:
            obj = points[key]
            if not obj.lock_location[0]:
                obj.lock_location[0] = True
            if abs(obj.location.x) > 0:
                obj.location.x = 0.0


def sync_symmetry(context, force=False, scene=None):
    scene = scene or context.scene
    points = markers(scene.mr_settings.session, scene)
    constrain_center(points)
    if not (force or scene.mr_settings.symmetry):
        return
    for name, obj in points.items():
        if name.endswith('.L'):
            other = points.get(name.replace('.L', '.R'))
            if other:
                other.location = (-obj.location.x, obj.location.y, obj.location.z)


# Observe native Blender G/gizmo/numeric transforms as well as custom dragging.
# Keep values, never RNA object references, so Undo/deletion/file loading is safe.
_marker_positions = {}
_syncing = False


def update_marker_constraints(scene):
    global _syncing
    if _syncing or not hasattr(scene, 'mr_settings'):
        return
    _syncing = True
    try:
        settings = scene.mr_settings
        points = markers(settings.session, scene)
        cache_key = (scene.as_pointer(), settings.session)
        previous = _marker_positions.get(cache_key, {})
        constrain_center(points)
        if settings.symmetry:
            active = scene.view_layers[0].objects.active
            for base in ('Wrist', 'Elbow', 'Knee', 'Breast', 'SkirtFront', 'SkirtBack'):
                left, right = base + '.L', base + '.R'
                if left not in points or right not in points:
                    continue
                changed = [key for key in (left, right) if key in previous and
                           (points[key].location - Vector(previous[key])).length > 1e-7]
                if not changed:
                    continue
                key = next((k for k in changed if points[k] == active), changed[0])
                move_landmark(points, key, points[key].location.copy(), True, 0.0)
        _marker_positions[cache_key] = {key: tuple(obj.location) for key, obj in points.items()}
    finally:
        _syncing = False


def skeleton(points, low, high, settings=None):
    h = high.z - low.z
    chin, hips = points['Chin'], points['Groin']
    if not low.z < hips.z < chin.z < high.z:
        raise ValueError('股・顎はモデルの内側で、股より顎が上に来るよう配置してください')
    chest = hips.lerp(chin, .72)
    neck = hips.lerp(chin, .93)
    specs = []

    def add(name, head, tail, parent=None):
        if (Vector(tail) - Vector(head)).length < h * .001:
            raise ValueError(name + ': ボーンが短すぎます。マーカーを確認してください')
        specs.append((PREFIX + name, Vector(head), Vector(tail), PREFIX + parent if parent else None))

    spine = hips.lerp(chest, .28)
    spine1 = hips.lerp(chest, .58)
    add('Hips', hips, spine)
    add('Spine', spine, spine1, 'Hips')
    add('Spine1', spine1, chest, 'Spine')
    add('Spine2', chest, neck, 'Spine1')
    add('Neck', neck, chin, 'Spine2')
    top = Vector((chin.x, chin.y, high.z - h * .035))
    add('Head', chin, top, 'Neck')
    add('HeadTop_End', top, top + Vector((0, 0, h * .025)), 'Head')
    for suffix, side, sign in (('.L', 'Left', 1), ('.R', 'Right', -1)):
        wrist, elbow, knee = [points[k + suffix] for k in ('Wrist', 'Elbow', 'Knee')]
        if not (sign * (wrist.x - hips.x) > sign * (elbow.x - hips.x) > 0):
            raise ValueError('手首と肘の左右・順序を確認してください（左は +X）')
        if not low.z < knee.z < hips.z or sign * (knee.x - hips.x) <= 0:
            raise ValueError('膝は股の下、対応する左右に配置してください')
        shoulder = Vector((hips.x + sign * h * .045, neck.y, neck.z - h * .015))
        arm = Vector((hips.x + sign * h * .12, elbow.y, elbow.z + h * .008))
        hand = wrist + Vector((sign * h * .07, 0, 0))
        add(side + 'Shoulder', shoulder, arm, 'Spine2')
        add(side + 'Arm', arm, elbow, side + 'Shoulder')
        add(side + 'ForeArm', elbow, wrist, side + 'Arm')
        add(side + 'Hand', wrist, hand, side + 'ForeArm')
        finger_level = int(settings.finger_level) if settings else 0
        fingers = {
            2: ('Thumb', 'Middle'),
            3: ('Thumb', 'Index', 'Pinky'),
            5: ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'),
        }.get(finger_level, ())
        finger_offsets = {
            'Thumb': (0, -h * .012), 'Index': (-h * .018, h * .008),
            'Middle': (-h * .006, 0), 'Ring': (h * .008, -h * .004),
            'Pinky': (h * .020, -h * .009),
        }
        for finger in fingers:
            offset_y, offset_z = finger_offsets[finger]
            start = hand + Vector((0, offset_y, offset_z))
            previous = side + 'Hand'
            joint_count = 2 if finger == 'Thumb' else 3
            for joint in range(1, joint_count + 1):
                head = start + Vector((sign * h * .05 * (joint - 1) / joint_count, 0, 0))
                tail = start + Vector((sign * h * .05 * joint / joint_count, 0, 0))
                name = side + 'Hand' + finger + str(joint)
                add(name, head, tail, previous)
                previous = name
        thigh = Vector((hips.x + sign * max(abs(knee.x - hips.x) * .72, h * .04), hips.y, hips.z - h * .025))
        ankle = Vector((knee.x, knee.y + h * .01, low.z + h * .055))
        toe = Vector((knee.x, knee.y - h * .095, low.z + h * .025))
        add(side + 'UpLeg', thigh, knee, 'Hips')
        add(side + 'Leg', knee, ankle, side + 'UpLeg')
        add(side + 'Foot', ankle, toe, side + 'Leg')
        add(side + 'ToeBase', toe, toe + Vector((0, -h * .025, 0)), side + 'Foot')
        add(side + 'Toe_End', toe + Vector((0, -h * .025, 0)), toe + Vector((0, -h * .035, 0)), side + 'ToeBase')
    if settings and settings.hair_enabled:
        start, end = points['Hair.Start'], points['Hair.End']
        add('Hairs', start, start + Vector((0, 0, h * .025)), 'Head')
        count = settings.hair_bones
        previous = 'Hairs'
        for index in range(count):
            head = start.lerp(end, index / count)
            tail = start.lerp(end, (index + 1) / count)
            name = f'Hair{index + 1}'
            add(name, head, tail, previous)
            previous = name
    if settings and settings.breasts_enabled:
        chest = points['Groin'].lerp(points['Chin'], .72)
        add('Breasts', Vector((0, chest.y, chest.z)), Vector((0, chest.y, chest.z + h * .025)), 'Spine2')
        for suffix, side in (('.L', 'Left'), ('.R', 'Right')):
            anchor = Vector((chest.x + (.055 if suffix == '.L' else -.055) * (high.x-low.x), chest.y, chest.z))
            add('Breast.' + side, anchor, points['Breast' + suffix], 'Breasts')
    if settings and settings.skirt_enabled:
        add('Skirts', points['Groin'], points['Groin'] + Vector((0, 0, h * .025)), 'Hips')
        for part in ('SkirtFront', 'SkirtBack'):
            for suffix, side in (('.L', 'Left'), ('.R', 'Right')):
                start, end = points['Groin'], points[part + suffix]
                previous = 'Skirts'
                for index in range(settings.skirt_bones):
                    head = start.lerp(end, index / settings.skirt_bones)
                    tail = start.lerp(end, (index + 1) / settings.skirt_bones)
                    name = f'{part}.{side}{index + 1}'
                    add(name, head, tail, previous)
                    previous = name
    return specs


def segment_distance(p, head, tail):
    v = tail - head
    t = max(0., min(1., (p - head).dot(v) / v.length_squared))
    return (p - (head + v * t)).length


def bind_fallback(obj, rig, specs, height):
    """Distance skinning for vertices that bone heat could not bind. Explicitly reported."""
    repaired = 0
    bone_names = {name for name, *_ in specs}
    deform_indices = {g.index for g in obj.vertex_groups if g.name in bone_names and not g.name.endswith((':Hairs', ':Breasts', ':Skirts'))}
    for vertex in obj.data.vertices:
        if sum(g.weight for g in vertex.groups if g.group in deform_indices) > 1e-6:
            continue
        candidates = sorted((segment_distance(vertex.co, a, b), name) for name, a, b, _ in specs
                            if not name.endswith(('_End', 'Top_End')))
        candidates = candidates[:3]
        # Sharply local weights reduce cross-limb leakage on loose clothing.
        values = [(name, 1 / max(d, height * .007) ** 4) for d, name in candidates]
        total = sum(w for _, w in values)
        for name, value in values:
            group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
            group.add([vertex.index], value / total, 'REPLACE')
        repaired += 1
    return repaired


def build(context):
    object_mode()
    session = context.scene.mr_settings.session
    meshes, landmark_objects = sources(session), markers(session)
    required = {'Chin', 'Groin', 'Wrist.L', 'Wrist.R', 'Elbow.L', 'Elbow.R', 'Knee.L', 'Knee.R'}
    if not session or not meshes or not required.issubset(landmark_objects):
        raise ValueError('基本マーカーがありません。「マーカー消去」を押して再作成してください')
    settings = context.scene.mr_settings
    expected_optional = set()
    if settings.hair_enabled:
        expected_optional.update({'Hair.Start', 'Hair.End'})
    if settings.breasts_enabled:
        expected_optional.update({'Breast.L', 'Breast.R'})
        # Migrate markers created by the earlier plural label.
        for side in ('L', 'R'):
            old = landmark_objects.pop('Breasts.' + side, None)
            if old and 'Breast.' + side not in landmark_objects:
                old['mr_landmark'] = 'Breast.' + side
                landmark_objects['Breast.' + side] = old
    if settings.skirt_enabled:
        expected_optional.update({f'Skirt{part}.{side}' for part in ('Front', 'Back') for side in ('L', 'R')})
    missing_optional = expected_optional - landmark_objects.keys()
    if missing_optional:
        raise ValueError('選択中のオプション用マーカーがありません。「マーカー消去」を押して再作成してください')
    sync_symmetry(context)
    low, high = bounds(meshes)
    specs = skeleton({k: o.location.copy() for k, o in landmark_objects.items()}, low, high, context.scene.mr_settings)
    marker_collection = next((c for c in bpy.data.collections if c.name.startswith('AutoRig · Markers') and any(o.get('mr_session') == session for o in c.objects)), None)
    created = []
    hidden_states = [(o, o.hide_get()) for o in meshes]
    try:
        armature = bpy.data.armatures.new('Pinnacle-Rigger Skeleton')
        rig = bpy.data.objects.new('Pinnacle-Rigger', armature)
        context.scene.collection.objects.link(rig)
        created.append(rig)
        rig.show_in_front = True
        rig['mr_session'] = session
        rig['mr_version'] = '1.01'
        select_only([rig])
        bpy.ops.object.mode_set(mode='EDIT')
        for name, head, tail, parent in specs:
            bone = armature.edit_bones.new(name)
            bone.head, bone.tail = head, tail
            bone.use_deform = name not in {PREFIX + 'Hairs', PREFIX + 'Breasts', PREFIX + 'Skirts'}
            if parent:
                bone.parent = armature.edit_bones[parent]
            bone.use_connect = bool(parent and (bone.parent.tail - bone.head).length < 1e-5)
        bpy.ops.object.mode_set(mode='OBJECT')
        outputs, repaired = [], 0
        depsgraph = context.evaluated_depsgraph_get()
        for source in meshes:
            # Evaluate modifiers and bake transforms only on a new mesh.
            data = bpy.data.meshes.new_from_object(source.evaluated_get(depsgraph), depsgraph=depsgraph, preserve_all_data_layers=True)
            data.transform(source.matrix_world)
            data.update()
            obj = bpy.data.objects.new(source.name + ' · Pinnacle-Rigger', data)
            context.scene.collection.objects.link(obj)
            created.append(obj)
            obj['mr_output'] = rig.name
            # Discard copied vertex deform indices, which refer to source groups.
            if len(data.vertices):
                import bmesh
                bm = bmesh.new()
                bm.from_mesh(data)
                layer = bm.verts.layers.deform.active
                if layer:
                    bm.verts.layers.deform.remove(layer)
                bm.to_mesh(data)
                bm.free()
            select_only([obj, rig], rig)
            try:
                bpy.ops.object.parent_set(type='ARMATURE_AUTO')
            except RuntimeError:
                pass  # Bone heat may fail for disconnected/non-manifold clothing.
            obj.parent = rig
            if not any(m.type == 'ARMATURE' and m.object == rig for m in obj.modifiers):
                obj.modifiers.new('Pinnacle-Rigger', 'ARMATURE').object = rig
            repaired += bind_fallback(obj, rig, specs, high.z - low.z)
            # Normalize all weights, including bone heat output.
            select_only([obj])
            bpy.ops.object.vertex_group_normalize_all(lock_active=False)
            outputs.append(obj)
        old_rigs = {o.name for o in context.scene.objects if o != rig and o.type == 'ARMATURE' and o.get('mr_session') == session}
        for obj in context.scene.objects:
            if obj.name in old_rigs or obj.get('mr_output') in old_rigs:
                obj.hide_set(True)
        # Do all potentially failing selection work before removing originals.
        select_only([rig])
        # Keep only the generated rig and meshes in the scene hierarchy.
        for marker in landmark_objects.values():
            bpy.data.objects.remove(marker, do_unlink=True)
        if marker_collection and not marker_collection.objects and not marker_collection.children:
            bpy.data.collections.remove(marker_collection)
        for source in meshes:
            old_mesh = source.data if source.type == 'MESH' else None
            bpy.data.objects.remove(source, do_unlink=True)
            if old_mesh and old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
        settings = context.scene.mr_settings
        settings.session = ''
        _marker_positions.clear()
        total = sum(len(o.data.vertices) for o in outputs)
        report = f'{len(specs)}ボーン / {total:,}頂点 / 距離補完 {repaired:,}頂点'
        rig['mr_report'] = report
        rig['mr_fallback_vertices'] = repaired
        return rig, report
    except Exception:
        object_mode()
        for obj in reversed(created):
            bpy.data.objects.remove(obj, do_unlink=True)
        for obj, hidden in hidden_states:
            obj.hide_set(hidden)
        raise
