"""Short-lived original media files for the native Meta file chooser."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import tempfile

from scheduler.native_worker import NativeFailure


@contextmanager
def stage_reviewed_media(packet, assets, workdir):
    media_format = packet.get('format', 'image')
    manifest = [packet.get('image', {})] if media_format == 'image' else packet.get('media', [])
    blobs = [assets] if isinstance(assets, bytes) else assets
    expected_count = (1, 1) if media_format in {'image', 'reel'} else (2, 10)
    if media_format not in {'image', 'carousel', 'reel'} or not isinstance(blobs, list) or not expected_count[0] <= len(blobs) <= expected_count[1] or len(blobs) != len(manifest):
        raise NativeFailure('invalid_reviewed_media_files')
    suffixes = {'image/png': '.png', 'image/jpeg': '.jpg', 'video/mp4': '.mp4'}
    prepared = []
    for asset, blob in zip(manifest, blobs):
        mime = asset.get('mimeType')
        if mime not in suffixes or (mime == 'video/mp4') != (media_format == 'reel') or not isinstance(blob, bytes) or not blob:
            raise NativeFailure('invalid_reviewed_media_files')
        prepared.append((suffixes[mime], blob))
    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='reviewed-', dir=root) as directory:
        paths, hashes = [], []
        for index, (suffix, blob) in enumerate(prepared):
            path = Path(directory) / f'{index:02d}{suffix}'
            with path.open('xb') as stream:
                path.chmod(0o600)
                stream.write(blob)
            digest = hashlib.sha256(blob).hexdigest()
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise NativeFailure('reviewed_media_file_changed')
            paths.append(path)
            hashes.append(digest)
        yield paths, hashes
