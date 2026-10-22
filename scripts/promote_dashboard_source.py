"""Promote a scoped dashboard source archive, with an exclusive private backup."""
from pathlib import Path, PurePosixPath
import tarfile

ROOT = (Path.home() / 'apps/brandflow').resolve()
BUNDLE = Path.home() / 'apps/brandflow-pr67-check.IxKv2K/funzug-pr67-source.tar'
BACKUP = ROOT / '.backups/source-pre-pr67-20261014.tar.gz'
PREFIXES = ('app/api/integrations/funzug/', 'app/api/social-drafts/', 'app/social-drafts/', 'components/', 'lib/')
FILES = {'Dockerfile','middleware.ts','scripts/reviewed_media.py','scripts/validate_ordered_media.py'}


def main():
    with tarfile.open(BUNDLE) as archive:
        members = archive.getmembers()
        for member in members:
            if member.name == 'social-drafts-page.tsx':
                member.name = 'app/social-drafts/page.tsx'
            name = member.name.rstrip('/')
            parts = PurePosixPath(name).parts
            if not name or name.startswith('/') or '..' in parts or any(p.startswith('.') for p in parts) or not (member.isfile() or member.isdir()):
                raise RuntimeError('Unsafe source archive member')
            allowed = name in FILES or any(name.startswith(prefix) for prefix in PREFIXES)
            # tar includes intermediate directory entries, not their unrelated files.
            directory = member.isdir() and any(prefix.startswith(name + '/') for prefix in PREFIXES)
            directory = directory or (member.isdir() and name == 'scripts')
            if not allowed and not directory:
                raise RuntimeError('Archive contains unrelated source')
            (ROOT / name).resolve().relative_to(ROOT)
        backup_dir = BACKUP.parent
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        backup_dir.chmod(0o700)
        with tarfile.open(BACKUP, 'x:gz') as backup:
            BACKUP.chmod(0o600)
            for member in members:
                path = ROOT / member.name
                if member.isfile() and path.exists():
                    backup.add(path, arcname=member.name, recursive=False)
        archive.extractall(ROOT, members=members, filter='data')
        print(f'Promoted {sum(m.isfile() for m in members)} scoped source files; private backup retained')


if __name__ == '__main__':
    main()
