"""Decode private ordered media before ingestion. Never uploads or changes pixels."""
import base64
import io
import json
import math
import subprocess
import tempfile
import sys
from pathlib import Path

from PIL import Image
from scripts.reviewed_media import approval_fingerprint


def validate_ordered_media(draft, *, ffprobe='ffprobe', ffmpeg='ffmpeg'):
    fingerprint = approval_fingerprint(draft)
    if draft.get('format') not in {'carousel', 'reel'}:
        raise ValueError('Ordered media format required')
    for asset in draft['media']:
        if asset['width'] * asset['height'] > 20000000:
            raise ValueError('Decoded media exceeds 20 megapixels')
        data = base64.b64decode(asset['data'], validate=True)
        if draft['format'] == 'carousel':
            with Image.open(io.BytesIO(data)) as image:
                expected = {'image/png': 'PNG', 'image/jpeg': 'JPEG'}[asset['mimeType']]
                if image.format != expected or image.size != (asset['width'], asset['height']):
                    raise ValueError('Decoded image differs from reviewed metadata')
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Animated slides are not supported')
                if image.getexif().get(274, 1) != 1:
                    raise ValueError('Rotated image metadata is not supported')
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
            continue
        with tempfile.TemporaryDirectory(prefix='funzug-media-check-') as directory:
            path = Path(directory) / 'reviewed.mp4'
            path.write_bytes(data)
            try:
                result = subprocess.run([
                    ffprobe, '-v', 'error', '-protocol_whitelist', 'file',
                    '-show_streams', '-show_format', '-of', 'json', str(path),
                ], check=True, capture_output=True, timeout=30)
                info = json.loads(result.stdout)
                verify_video_metadata(info, asset)
                subprocess.run([
                    ffmpeg, '-v', 'error', '-xerror', '-nostdin',
                    '-protocol_whitelist', 'file', '-i', str(path),
                    '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-',
                ], check=True, capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
                raise ValueError('Reel decoder unavailable or media decoding failed') from error
    return fingerprint


def verify_video_metadata(info, asset):
    streams = info.get('streams', [])
    video = [stream for stream in streams if stream.get('codec_type') == 'video']
    audio = [stream for stream in streams if stream.get('codec_type') == 'audio']
    if len(video) != 1 or len(audio) > 1 or len(streams) != len(video) + len(audio):
        raise ValueError('Reel must contain one video and at most one audio stream')
    stream = video[0]
    if stream.get('codec_name') != 'h264' or stream.get('pix_fmt') != 'yuv420p':
        raise ValueError('Reel requires H.264 with yuv420p pixels')
    if audio and audio[0].get('codec_name') != 'aac':
        raise ValueError('Reel audio must use AAC')
    if (stream.get('width'), stream.get('height')) != (asset['width'], asset['height']):
        raise ValueError('Decoded video dimensions differ from reviewed metadata')
    if stream.get('sample_aspect_ratio') not in {'1:1', 'N/A', None}:
        raise ValueError('Reel requires square pixels')
    rotations = [stream.get('tags', {}).get('rotate', 0)]
    rotations.extend(item.get('rotation', 0) for item in stream.get('side_data_list', []))
    try:
        if any(float(rotation) != 0 for rotation in rotations):
            raise ValueError('Rotated video metadata is not supported')
        numerator, denominator = stream['avg_frame_rate'].split('/')
        rate = float(numerator) / float(denominator)
        duration = float(info['format']['duration']) * 1000
    except (KeyError, TypeError, ZeroDivisionError) as error:
        raise ValueError('Incomplete Reel metadata') from error
    if not math.isfinite(rate) or not 1 <= rate <= 60:
        raise ValueError('Invalid Reel frame rate')
    if not math.isfinite(duration) or not 1 <= duration <= 180000 or abs(duration - asset['durationMs']) > 1:
        raise ValueError('Decoded Reel duration differs from reviewed metadata')
    if 'mp4' not in info.get('format', {}).get('format_name', '').split(','):
        raise ValueError('Reel must use an MP4 container')


if __name__ == '__main__':
    try:
        packet = sys.stdin.buffer.read(140 * 1024 * 1024 + 1)
        if len(packet) > 140 * 1024 * 1024:
            raise ValueError('Media packet too large')
        print(validate_ordered_media(json.loads(packet)))
    except Exception:
        # Never return media bytes, metadata, paths or subprocess stderr.
        sys.stderr.write('Ordered media validation failed\n')
        sys.exit(1)
