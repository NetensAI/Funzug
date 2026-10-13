"""Ordered approval fingerprints for future carousel and reel review.

This module does not enable ingestion or delivery of a new format.
Legacy single-image fingerprints remain byte-for-byte compatible.
"""
import base64
import hashlib
import json
import re

CONTENT_KEYS = ('headline', 'caption', 'claims', 'sources', 'platforms')


def approval_fingerprint(draft: dict) -> str:
    content = {key: draft[key] for key in CONTENT_KEYS}
    kind = draft.get('format', 'image')
    if kind == 'image':
        image = draft['image']
        data = base64.b64decode(image['data'], validate=True)
        content.update(imageMimeType=image['mimeType'], imageSha256=hashlib.sha256(data).hexdigest())
    else:
        assets = draft.get('media')
        if kind not in {'carousel', 'reel'} or not isinstance(assets, list):
            raise ValueError('Unsupported reviewed media format')
        if not (2 <= len(assets) <= 10 if kind == 'carousel' else len(assets) == 1):
            raise ValueError('Invalid reviewed media count')
        manifest = []
        for index, asset in enumerate(assets):
            if not isinstance(asset, dict):
                raise ValueError('Invalid reviewed media asset')
            mime = asset.get('mimeType')
            width, height = asset.get('width'), asset.get('height')
            if any(type(value) is not int or value <= 0 for value in (width, height)):
                raise ValueError('Invalid reviewed media dimensions')
            if width >= height or abs(width * 5 - height * 4) > 2:
                raise ValueError('Reviewed media must be portrait 4:5')
            if mime not in ({'image/png', 'image/jpeg'} if kind == 'carousel' else {'video/mp4'}):
                raise ValueError('Invalid reviewed media MIME type')
            encoded = asset.get('data')
            if not isinstance(encoded, str) or not re.fullmatch(r'(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?', encoded):
                raise ValueError('Invalid reviewed media encoding')
            data = base64.b64decode(encoded, validate=True)
            if not data or len(data) > (12 if kind == 'carousel' else 100) * 1024 * 1024:
                raise ValueError('Invalid reviewed media byte count')
            entry = dict(index=index, mimeType=mime, width=width, height=height, sha256=hashlib.sha256(data).hexdigest())
            if kind == 'reel':
                duration = asset.get('durationMs')
                if type(duration) is not int or not 1 <= duration <= 180000:
                    raise ValueError('Invalid reviewed reel duration')
                entry['durationMs'] = duration
            manifest.append(entry)
        if len({item['sha256'] for item in manifest}) != len(manifest):
            raise ValueError('Duplicate reviewed media assets')
        content.update(format=kind, media=manifest)
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
