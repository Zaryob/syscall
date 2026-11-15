#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare static JSON API indexes and a source archive for Jekyll publishing."""
import gzip
import io
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'
ARCHIVE = PUBLIC / 'downloads/syscall-reference-source.tar.gz'
ROOT_FILES = ['.gitignore', '.ruby-version', '_config.yml', 'Gemfile', 'Gemfile.lock', 'package.json', 'package-lock.json', 'server.mjs', 'LICENSE', 'LICENSING.md', 'README.md', 'README.tr.md', 'THIRD_PARTY_NOTICES.md']
SOURCE_DIRS = ['public', 'scripts', 'sources', 'tests', 'LICENSES', '.github']


def editorial_notes():
    """Read the summaries in notes.mjs without requiring Node.js."""
    path = PUBLIC / 'notes.mjs'
    if not path.is_file():
        return {}
    text = path.read_text()
    literal = r"'([^'\\]*)'"
    rows = re.findall(r"^\s*\[{0},\s*{0},\s*{0}(?:,\s*{0})?\],?\s*$".format(literal), text, re.M)
    if len(rows) != len(re.findall(r"^\s*\['", text, re.M)):
        raise ValueError('Unrecognized entry in notes.mjs')
    return {name: {'en': english, 'tr': turkish} for name, english, turkish, _ in rows}


def prepare():
    manifest_path = PUBLIC / 'data/manifest.json'
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    paths = manifest.get('version_paths', {})
    availability = manifest.get('version_architectures', {})
    architectures = [arch['id'] for arch in manifest['architectures']]
    latest = manifest['latest']
    latest_path = paths.get(latest, latest)
    release_data = PUBLIC / '_data/syscall_release.json'
    release_data.parent.mkdir(parents=True, exist_ok=True)
    release = {'latest': latest, 'latest_path': latest_path}
    sources_path = PUBLIC / 'data' / latest_path / 'sources.json'
    if sources_path.is_file():
        # Date of the active latest snapshot, used as the sitemap's lastmod.
        release['updated'] = json.loads(sources_path.read_bytes())['licensing']['generated_at'][:10]
    release['architectures'] = manifest['architectures']
    release_data.write_text(json.dumps(release, indent=2, ensure_ascii=False) + '\n')
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
            'version_architectures': availability,
            'tables': [
                {'version': version, 'architecture': arch, 'url': '../../data/{}/{}.json'.format(paths.get(version, version), arch)}
                for version in manifest['versions']
                for arch in availability.get(version, architectures)
            ],
        },
    }
    for filename, data in indexes.items():
        (api / filename).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')

    x64_path = PUBLIC / 'data' / latest_path / 'x64.json'
    if not x64_path.is_file():
        raise ValueError('Latest x64 snapshot missing: ' + str(x64_path))
    notes = editorial_notes()
    labels = {arch['id']: arch.get('label', arch['id']) for arch in manifest['architectures']}
    fallback = {'en': '{label} system call {number}', 'tr': '{label} sistem çağrısı {number}'}
    search_entries = []
    listed = set()
    # x86-64 first; other ABIs add the calls it lacks (mmap2, socketcall, _llseek, ...).
    for arch in sorted(availability.get(latest, architectures), key=lambda arch: arch != 'x64'):
        table_path = PUBLIC / 'data' / latest_path / (arch + '.json')
        if not table_path.is_file():
            continue
        for s in json.loads(table_path.read_bytes()).get('syscalls', []):
            if not s.get('name') or s.get('status') == 'unimplemented' or s['name'] in listed:
                continue
            name = s['name']
            listed.add(name)
            decl = s.get('declaration') or ', '.join(s.get('arguments') or [])
            for lang in ['tr', 'en']:
                summary = notes.get(name, {}).get(lang)
                search_entries.append({
                    'lang': lang,
                    'title': f'sys_{name}',
                    'url': '?' + urlencode({'arch': arch, 'kernel': latest, 'q': name, 'highlight': name}) + f'#sys-{latest}:{s["number"]}:{name}',
                    'type': 'syscall/',
                    'description': ' — '.join(part for part in [summary, decl] if part) or fallback[lang].format(label=labels.get(arch, arch), number=s['number']),
                })
    (PUBLIC / 'search.json').write_text(json.dumps(search_entries, indent=2, ensure_ascii=False) + '\n')

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
                    body = manifest_bytes if path == manifest_path else path.read_bytes()
                    info = tarfile.TarInfo(name)
                    info.size = len(body)
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(body))
    os.replace(temporary, ARCHIVE)
    print('Prepared static API and source archive ({} files, {} bytes).'.format(len(selected), ARCHIVE.stat().st_size))


if __name__ == '__main__':
    prepare()
