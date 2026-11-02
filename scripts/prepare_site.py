#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare static JSON API indexes and a source archive for Jekyll publishing."""
import gzip
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'
ARCHIVE = PUBLIC / 'downloads/syscall-reference-source.tar.gz'
ROOT_FILES = ['.gitignore', '.ruby-version', '_config.yml', 'Gemfile', 'Gemfile.lock', 'package.json', 'server.mjs', 'LICENSE', 'LICENSING.md', 'README.md', 'README.tr.md', 'THIRD_PARTY_NOTICES.md']
SOURCE_DIRS = ['public', 'scripts', 'tests', 'LICENSES', '.github']


def prepare():
    manifest = json.loads((PUBLIC / 'data/manifest.json').read_text())
    api = PUBLIC / 'api/v1'
    api.mkdir(parents=True, exist_ok=True)
    indexes = {
        'architectures.json': manifest['architectures'],
        'versions.json': manifest['versions'],
        'index.json': {
            'license': 'GPL-2.0-only', 'schema_version': 1, 'kind': 'static',
            # Relative to this API index, so a project-site baseurl also works.
            'manifest': '../../data/manifest.json',
            'architectures': 'architectures.json', 'versions': 'versions.json',
            'version_architectures': manifest.get('version_architectures', {}),
            'tables': [{'version': version, 'architecture': arch['id'], 'url': '../../data/{}/{}.json'.format(version, arch['id'])} for version in manifest['versions'] for arch in manifest['architectures'] if arch['id'] in manifest.get('version_architectures', {}).get(version, [a['id'] for a in manifest['architectures']])],
        },
    }
    for filename, data in indexes.items():
        (api / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')

    paths = [ROOT / p for p in ROOT_FILES]
    paths.append(ROOT / 'docs/reference-preview.png')
    for folder in SOURCE_DIRS:
        paths.extend((ROOT / folder).rglob('*'))
    # Deliberate allowlist: never publish .git, .cache, environment files,
    # credentials, installed gems, local build output, or the archive itself.
    selected = []
    for path in sorted(set(paths)):
        relative = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink():
            continue
        if any(p in {'__pycache__', 'downloads'} or p.startswith('.') and p not in {'.github', '.gitignore', '.ruby-version'} for p in relative.parts):
            continue
        if path.suffix in {'.pyc', '.pem', '.key'} or path.name.startswith('.env'):
            continue
        selected.append(path)
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    # Normalize metadata so identical sources produce identical archives.
    # Publish only a complete gzip: Jekyll's watcher can otherwise copy a
    # partially written archive while a local preview is running.
    with tempfile.NamedTemporaryFile(mode='wb', prefix='.source-', dir=ARCHIVE.parent, delete=False) as output:
        temporary = Path(output.name)
        with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as archive:
                for path in selected:
                    name = 'syscall-reference/' + path.relative_to(ROOT).as_posix()
                    body = path.read_bytes()
                    info = tarfile.TarInfo(name)
                    info.size = len(body)
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(body))
    os.replace(temporary, ARCHIVE)
    print('Prepared static API and source archive ({} files, {} bytes).'.format(len(selected), ARCHIVE.stat().st_size))


if __name__ == '__main__':
    prepare()
