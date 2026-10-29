"""Package the existing trained models and current firmware without credentials.
Run from this integrated workspace before build. A standalone CareLink checkout
uses the already-packaged sensor_core and does not need the parent workspace.
"""
from pathlib import Path
import shutil
root = Path(__file__).resolve().parents[1]
source = root.parent / 'server'
if not (source / 'fall_service.py').exists():
    print('Using packaged sensor_core.')
    raise SystemExit(0)
core = root / 'sensor_core'
core.mkdir(exist_ok=True)
(core / '__init__.py').touch()
for name in ['classification_service.py', 'fall_service.py']:
    shutil.copy2(source / name, core / name)
shutil.copytree(source / 'ml', core / 'ml', dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
shutil.copytree(source / 'tests/fixtures', core / 'tests/fixtures', dirs_exist_ok=True)
# Backend requirements include account dependencies; do not overwrite them.
firmware = root.parent / 'esp32/elder_sensors'
for name in ['elder_sensors.ino', 'heart_rate_processor.h', 'motion_stream.h', 'secrets.example.h']:
    if (firmware / name).exists():
        shutil.copy2(firmware / name, root / 'firmware/elder_sensors' / name)
(root / 'firmware/tests').mkdir(exist_ok=True)
shutil.copy2(root.parent / 'esp32/tests/heart_rate_test.cpp', root / 'firmware/tests/heart_rate_test.cpp')
print('Synced model runtime, training evidence and firmware; secrets excluded.')
