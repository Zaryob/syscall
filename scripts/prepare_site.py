#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare static JSON API indexes and a source archive for Jekyll publishing."""
import gzip
import io
import json
import os
from pathlib import Path
import re
import sys
import tarfile
import tempfile
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))

import static_pages  # scripts/static_pages.py, beside this file

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


def abi_release():
    """Provenance record of the latest errno/signal/ioctl release, if one is published."""
    manifest_path = PUBLIC / 'data/abi/manifest.json'
    if not manifest_path.is_file():
        return None
    return json.loads((PUBLIC / 'data/abi' / json.loads(manifest_path.read_bytes())['latest'] / 'sources.json').read_bytes())


def abi_search_entries(abi):
    """One search result per errno, signal and ioctl command name, linking to its page."""
    if not abi:
        return []
    folder = PUBLIC / 'data/abi' / abi['kernel']
    release = abi['kernel'][1:]
    templates = {
        'errno': {'en': 'errno {number} on {scope}, Linux {release}', 'tr': '{scope} üzerinde errno {number}, Linux {release}'},
        'signals': {'en': 'Signal {number} on {scope}, Linux {release}', 'tr': '{scope} üzerinde sinyal {number}, Linux {release}'},
        'ioctl': {'en': 'ioctl command {number} on {scope}, Linux {release}', 'tr': '{scope} üzerinde ioctl komutu {number}, Linux {release}'},
    }
    unfixed = {'en': 'defined with a size-dependent macro', 'tr': 'boyuta bağlı bir makroyla tanımlı'}
    entries = []
    for kind, page, group in [('errno', 'errno/', 'tables'), ('signals', 'signals/', 'tables'), ('ioctl', 'ioctl/', 'commands')]:
        document = json.loads((folder / (kind + '.json')).read_bytes())
        key = 'commands' if kind == 'ioctl' else 'table'
        listed = set()
        # x86-64 first; other ABIs add the names it lacks (SIGEMT, TIOCGETP, ...).
        for arch in sorted(document['architectures'], key=lambda arch: arch != 'x64'):
            for entry in document[group][document['architectures'][arch][key]]['entries']:
                name = entry['name']
                if name in listed:
                    continue
                listed.add(name)
                # Every ABI with the same number as this one, so the text stays true off x86-64.
                same = [document['architectures'][other]['label'] for other in document['architectures']
                        if any(e['name'] == name and e.get('value', e.get('number')) == entry.get('value', entry.get('number'))
                               for e in document[group][document['architectures'][other][key]]['entries'])]
                value = entry.get('value', entry.get('number'))
                for lang in ['tr', 'en']:
                    number = unfixed[lang] if value is None else hex(value) if kind == 'ioctl' else str(value)
                    text = templates[kind][lang].format(number=number, scope=', '.join(same), release=release)
                    entries.append({
                        'lang': lang, 'title': name,
                        'url': page + '?' + urlencode({**({} if arch == 'x64' else {'arch': arch}), 'q': name}) + '#' + name,
                        'type': 'syscall/',
                        'description': ' — '.join(part for part in [entry.get('comment'), text] if part),
                    })
    return entries


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
    # The errno, signal and ioctl pages follow their own manifest (scripts/sync_abi.py).
    abi = abi_release()
    if abi:
        release.update(abi_latest=abi['kernel'], abi_updated=abi['licensing']['generated_at'][:10])
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
    search_entries.extend(abi_search_entries(abi))
    (PUBLIC / 'search.json').write_text(json.dumps(search_entries, indent=2, ensure_ascii=False) + '\n')
    # Crawlable pages per ABI and per syscall name; build output like api/, never committed.
    pages = static_pages.generate(PUBLIC, notes)

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
        # Reproducible from scripts/static_pages.py and the bundled data.
        if relative.parts[0] == 'public' and relative.parts[1] in static_pages.OUTPUT_DIRS:
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
    print('Prepared static API, {} static pages and source archive ({} files, {} bytes).'.format(pages['pages'], len(selected), ARCHIVE.stat().st_size))


if __name__ == '__main__':
    prepare()
