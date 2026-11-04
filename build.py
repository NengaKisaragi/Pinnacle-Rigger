"""Build the Blender add-on ZIP with no external dependencies."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root = Path(__file__).resolve().parent
output = root / 'dist' / 'pinnacle_rigger-1.03.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for source in sorted((root / 'pinnacle_rigger').glob('*.py')):
        archive.write(source, source.relative_to(root))
print(output)
