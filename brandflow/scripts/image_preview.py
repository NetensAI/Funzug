"""Generate a display preview only. Publication bytes are never modified."""
import io
import sys
from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 20_000_000
data = sys.stdin.buffer.read(12 * 1024 * 1024 + 1)
if not data or len(data) > 12 * 1024 * 1024:
    raise ValueError('Invalid preview input')
with Image.open(io.BytesIO(data)) as original:
    if original.format not in ('PNG', 'JPEG'):
        raise ValueError('Unsupported preview input')
    original.load()
    image = ImageOps.exif_transpose(original).convert('RGB')
    image.thumbnail((560, 700), Image.Resampling.LANCZOS)
    image.save(sys.stdout.buffer, 'WEBP', quality=82, method=4)
