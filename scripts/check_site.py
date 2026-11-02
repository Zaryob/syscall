#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check a built Jekyll site's links, baseurl, source archive and input hashes."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tarfile
from urllib.parse import unquote, urlsplit


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.site_root = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attr in ['href', 'src']:
            if attr in attrs:
                self.urls.append(attrs[attr])
        if tag == 'meta' and attrs.get('name') == 'site-root':
            self.site_root = attrs.get('content')


def check(site, baseurl):
    site = site.resolve()
    base = '/' + baseurl.strip('/') + '/' if baseurl.strip('/') else '/'
    index = (site / 'index.html').read_text()
    assert not index.startswith('---'), 'Unprocessed Jekyll front matter'
    assert '{{' not in index and '{%' not in index, 'Unprocessed Liquid template'
    parser = Links()
    parser.feed(index)
    assert parser.site_root == base, 'Incorrect site-root: {}'.format(parser.site_root)
    for url in parser.urls:
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        pathname = unquote(parsed.path)
        if pathname.startswith('/'):
            assert pathname.startswith(base), 'URL escapes baseurl: ' + url
            pathname = pathname[len(base):]
        target = (site / pathname).resolve()
        assert target.is_relative_to(site), 'URL escapes site: ' + url
        if target.is_dir():
            target = target / 'index.html'
        assert target.is_file(), 'Broken local link: ' + url
    for module in ['app.js', 'catalog.mjs', 'paths.mjs', 'examples.mjs']:
        text = (site / module).read_text()
        for imported in re.findall(r"from ['\"]([^'\"]+)['\"]", text):
            assert imported.startswith('./'), 'Module import must be relative: ' + imported
            assert (site / imported).is_file(), 'Missing module: ' + imported
    assert '/api/v1/syscalls/' not in (site / 'app.js').read_text(), 'Frontend still depends on the Node API'
    api_index = json.loads((site / 'api/v1/index.json').read_text())
    for item in api_index['tables']:
        assert (site / 'api/v1' / item['url']).is_file(), 'Missing static API table'
    manifest = json.loads((site / 'data/manifest.json').read_text())
    for version in manifest['versions']:
        sources = json.loads((site / 'data' / version / 'sources.json').read_text())
        for source in sources['files']:
            data = (site / 'data' / version / source['bundled_path']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == source['sha256'], 'Modified kernel source: ' + source['path']
    notice = (site / 'licensing.txt').read_text()
    assert '{{' not in notice and not notice.startswith('---'), 'Unprocessed license notices'
    with tarfile.open(site / 'downloads/syscall-reference-source.tar.gz') as archive:
        members = archive.getmembers()
        names = {m.name for m in members}
        for required in ['LICENSE', 'LICENSING.md', 'Gemfile.lock', '_config.yml', 'scripts/sync_kernel.py', 'scripts/prepare_site.py', 'public/_layouts/default.html']:
            assert 'syscall-reference/' + required in names, 'Source archive missing ' + required
        for member in members:
            assert member.isfile(), 'Archive contains a non-file entry'
            parts = Path(member.name).parts
            assert not any(p in {'.git', '.cache', '.bundle', 'vendor', '_site', '__pycache__'} or p.startswith('.env') for p in parts), 'Local state in source archive'
    print('Verified Jekyll output at {} (baseurl {}, {} local links, {} source files in archive).'.format(site, base, len(parser.urls), len(names)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=Path('_site'))
    parser.add_argument('--baseurl', default='')
    args = parser.parse_args()
    check(args.site, args.baseurl)
