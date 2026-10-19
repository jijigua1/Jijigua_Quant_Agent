"""Offline release verification and exclusive staging. Never switches global entries.

Public code is not a backup of papers, market releases, signing keys or SQLite.
An optional owner-held archive restores exact original bytes, after SHA checks.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(root):
    rows = json.loads((root / 'provenance/VER1_0_RELEASE_FILES.json').read_text('utf-8'))
    errors = [r['path'] for r in rows if not (root / r['path']).is_file()
              or (root / r['path']).is_symlink() or sha(root / r['path']) != r['sha256']]
    if errors:
        raise ValueError('RELEASE_CONTENT_MISMATCH: ' + ', '.join(errors))
    return len(rows)


def stage(output, archive=None, archive_sha=None, manifest=None):
    output = output.resolve()
    if output.exists() or output == ROOT or ROOT in output.parents:
        raise ValueError('OUTPUT_MUST_BE_NEW_AND_OUTSIDE_CHECKOUT')
    if archive:
        if not archive_sha or not manifest or sha(archive) != archive_sha:
            raise ValueError('PRIVATE_ARCHIVE_SHA_OR_MANIFEST_REQUIRED')
        expected = {r['path']: r for r in json.loads(manifest.read_text('utf-8'))}
        # Validate all member types, paths, bytes and names before writing any file.
        with tarfile.open(archive, 'r:gz') as t:
            names = set()
            for member in t:
                rel = PurePosixPath(member.name)
                if (not member.isfile() or rel.is_absolute() or '..' in rel.parts
                        or '\\' in member.name or ':' in member.name or member.name in names
                        or member.name not in expected):
                    raise ValueError('UNSAFE_OR_UNEXPECTED_ARCHIVE_MEMBER')
                data = t.extractfile(member).read()
                row = expected[member.name]
                if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                    raise ValueError('PRIVATE_FILE_SHA_MISMATCH')
                names.add(member.name)
            if names != set(expected):
                raise ValueError('PRIVATE_ARCHIVE_INCOMPLETE')
        output.mkdir(parents=True)
        with tarfile.open(archive, 'r:gz') as t:
            for member in t:
                target = output / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with t.extractfile(member) as source, target.open('xb') as dest:
                    shutil.copyfileobj(source, dest)
                target.chmod(member.mode & 0o777)
        return len(names), 'exact owner-held production snapshot'
    count = verify(ROOT)
    output.mkdir(parents=True)
    rows = json.loads((ROOT / 'provenance/VER1_0_RELEASE_FILES.json').read_text('utf-8'))
    for row in rows:
        target = output / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / row['path'], target)
        target.chmod(row.get('mode', 0o644))
    target = output / 'provenance/VER1_0_RELEASE_FILES.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'provenance/VER1_0_RELEASE_FILES.json', target)
    return count, 'public portable packaging; configure before activation'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('verify')
    s = sub.add_parser('stage')
    s.add_argument('--output', type=Path, required=True)
    s.add_argument('--private-archive', type=Path)
    s.add_argument('--archive-sha256')
    s.add_argument('--private-manifest', type=Path)
    a = p.parse_args()
    if a.command == 'verify':
        result = dict(status='PASS', files=verify(ROOT))
    else:
        count, mode = stage(a.output, a.private_archive, a.archive_sha256, a.private_manifest)
        result = dict(status='STAGED_NOT_ACTIVATED', files=count, mode=mode, output=str(a.output.resolve()))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
