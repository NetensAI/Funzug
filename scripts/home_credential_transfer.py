"""One-time authenticated-encryption transfer. Never prints credential values."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import time
import zipfile

CONTEXT = b'NetensAI/Funzug home credential migration v1'
NAMES = ('FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL', 'FUNZUG_FACEBOOK_PAGE_TOKEN', 'FUNZUG_META_APP_SECRET')


def encrypt(values, private_pem, now=None):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from instagram_credentials import decode_bundle
    decode_bundle(values.get(NAMES[0], ''))
    if set(values) - set(NAMES):
        raise ValueError('unexpected credential name')
    key = serialization.load_pem_private_key(private_pem, password=None)
    public = key.public_key()
    public_der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    session = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    issued = int(time.time() if now is None else now)
    clear = json.dumps({'issued_at': issued, 'values': values}, separators=(',', ':')).encode()
    wrap = public.encrypt(session, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=CONTEXT))
    encode = lambda data: base64.b64encode(data).decode()
    return {'version': 1, 'key_id': hashlib.sha256(public_der).hexdigest(),
            'wrapped_key': encode(wrap), 'nonce': encode(nonce),
            'ciphertext': encode(AESGCM(session).encrypt(nonce, clear, CONTEXT))}


def decrypt(envelope, private_pem, now=None):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from instagram_credentials import decode_bundle
    if envelope.get('version') != 1:
        raise ValueError('invalid envelope')
    key = serialization.load_pem_private_key(private_pem, password=None)
    public_der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if envelope.get('key_id') != hashlib.sha256(public_der).hexdigest():
        raise ValueError('recipient key mismatch')
    decode = lambda field: base64.b64decode(envelope[field], validate=True)
    session = key.decrypt(decode('wrapped_key'), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=CONTEXT))
    clear = json.loads(AESGCM(session).decrypt(decode('nonce'), decode('ciphertext'), CONTEXT))
    current = int(time.time() if now is None else now)
    if not current - 3600 <= clear['issued_at'] <= current + 300:
        raise ValueError('migration envelope expired')
    values = clear['values']
    if not isinstance(values, dict) or set(values) - set(NAMES):
        raise ValueError('invalid names')
    decode_bundle(values.get(NAMES[0], ''), current)
    return values


def export():
    values = {name: os.environ[name] for name in NAMES if os.environ.get(name)}
    pem = os.environ['FUNZUG_GH_APP_PRIVATE_KEY'].replace('\\n', '\n').encode()
    envelope = encrypt(values, pem)
    target = Path(os.environ['RUNNER_TEMP']) / 'funzug-home-envelope.json'
    with target.open('x') as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(envelope, handle)
    print('Encrypted migration envelope prepared; no plaintext artifact created')


def import_latest():
    """Runs only inside existing worker with private key/state runtime mounts."""
    from urllib.request import Request, build_opener
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    from instagram_credentials import NoRedirect
    from scripts.renew_instagram_credential import github, installation_token
    config = json.loads(Path('/run/secrets/config.json').read_text())
    pem = Path(config['key_file']).read_bytes()
    os.environ['FUNZUG_GH_APP_ID'] = '5281589'
    os.environ['FUNZUG_GH_APP_PRIVATE_KEY'] = pem.decode()
    try:
        token = installation_token({'actions': 'write'})
    finally:
        os.environ.pop('FUNZUG_GH_APP_PRIVATE_KEY', None)
    repo = '/repos/NetensAI/Funzug'
    runs = github('GET', repo + '/actions/workflows/home-credential-transfer.yml/runs?branch=main&event=workflow_dispatch&per_page=10', token)['workflow_runs']
    runs = [run for run in runs if run.get('status') == 'completed' and run.get('conclusion') == 'success'
            and run.get('event') == 'workflow_dispatch' and run.get('head_branch') == 'main']
    if not runs:
        raise RuntimeError('successful transfer run unavailable')
    run = runs[0]
    artifacts = github('GET', repo + '/actions/runs/' + str(run['id']) + '/artifacts', token)['artifacts']
    matches = [a for a in artifacts if a.get('name') == 'funzug-encrypted-home-credential' and not a.get('expired')]
    if len(matches) != 1 or matches[0].get('size_in_bytes', 0) > 65536:
        raise RuntimeError('migration artifact unavailable')
    url = 'https://api.github.com' + repo + '/actions/artifacts/' + str(matches[0]['id']) + '/zip'
    try:
        build_opener(NoRedirect()).open(Request(url, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'}), timeout=25)
        raise RuntimeError('artifact redirect required')
    except HTTPError as error:
        if error.code != 302:
            raise RuntimeError('artifact download unavailable') from None
        destination = error.headers.get('Location', '')
    parsed = urlsplit(destination)
    if parsed.scheme != 'https' or parsed.username or parsed.password or not parsed.hostname or not parsed.hostname.endswith(('.blob.core.windows.net', '.actions.githubusercontent.com')):
        raise RuntimeError('unexpected artifact origin')
    # Signed download URL gets no GitHub Authorization header.
    with build_opener(NoRedirect()).open(Request(destination), timeout=30) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise RuntimeError('artifact size invalid')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if archive.namelist() != ['funzug-home-envelope.json'] or archive.getinfo('funzug-home-envelope.json').file_size > 32768:
            raise RuntimeError('artifact manifest invalid')
        values = decrypt(json.loads(archive.read('funzug-home-envelope.json')), pem)
    target = Path('/state/home-secrets.json')
    if target.exists() or target.is_symlink():
        raise RuntimeError('existing local credentials preserved')
    with target.open('x') as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(values, handle)
    print(json.dumps({'result': 'credentials_provisioned', 'report_id': str(run['id'])}))


if __name__ == '__main__':
    try:
        export()
    except Exception:
        raise SystemExit('Credential export failed; sensitive details omitted')
