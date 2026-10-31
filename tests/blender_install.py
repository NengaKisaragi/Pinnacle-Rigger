"""Test the built ZIP using Blender's real restricted addon registration path."""
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile
import bpy
import addon_utils
ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='pinnacle-addon-') as temporary:
    with ZipFile(ROOT / 'dist' / 'pinnacle_rigger-1.0.0.zip') as archive:
        archive.extractall(temporary)
    sys.path.insert(0, temporary)
    for cycle in range(2):
        failures = []
        module = addon_utils.enable('pinnacle_rigger', default_set=False,
                                   handle_error=lambda exc: failures.append(exc))
        assert module is not None and not failures, f'Addon enable failed: {failures}'
        assert hasattr(bpy.types.Scene, 'mr_settings')
        assert bpy.app.handlers.depsgraph_update_post.count(module.maintain_markers) == 1
        assert bpy.app.handlers.load_post.count(module.marker_file_loaded) == 1
        assert bpy.app.timers.is_registered(module.initialize_markers)
        # Registration has ended: deferred initialization may safely access scenes.
        assert module.initialize_markers() is None
        addon_utils.disable('pinnacle_rigger', default_set=False)
        assert not hasattr(bpy.types.Scene, 'mr_settings')
        assert module.maintain_markers not in bpy.app.handlers.depsgraph_update_post
        assert module.marker_file_loaded not in bpy.app.handlers.load_post
        assert not bpy.app.timers.is_registered(module.initialize_markers)
    print('INSTALL_PASS: built ZIP enabled/disabled twice through addon_utils; restricted registration; deferred initialization; clean handlers/timers')
