#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check a built Jekyll site's links, baseurl, source archive and input hashes."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tarfile
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

import static_pages  # scripts/static_pages.py, beside this file


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.site_root = None
        self.canonical = None
        self.language = None
        self.alternates = {}
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for attr in ['href', 'src']:
            if attr in attrs:
                self.urls.append(attrs[attr])
        if tag == 'meta' and attrs.get('name') == 'site-root':
            self.site_root = attrs.get('content')
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical = attrs.get('href')
        if tag == 'link' and attrs.get('rel') == 'alternate' and attrs.get('hreflang'):
            self.alternates[attrs['hreflang']] = attrs.get('href')
        if tag == 'html':
            self.language = attrs.get('lang')
        if tag == 'script' and attrs.get('src'):
            self.scripts.append(attrs['src'])


# Pages besides the site root, each with its own canonical URL and sitemap entry.
SECTION_PAGES = ['errno/', 'signals/', 'ioctl/']
APPLICATION_PAGES = ['errno/', 'signals/', 'ioctl/', 'tr/', 'tr/errno/', 'tr/signals/', 'tr/ioctl/']


def check_page(site, base, relative):
    """Check one built HTML page: templates rendered, site-root set, local links resolve."""
    folder = site / relative
    text = (folder / 'index.html').read_text()
    assert not text.startswith('---'), 'Unprocessed Jekyll front matter: ' + relative
    assert '{{' not in text and '{%' not in text, 'Unprocessed Liquid template: ' + relative
    parser = Links()
    parser.feed(text)
    assert parser.site_root == base, 'Incorrect site-root: {}'.format(parser.site_root)
    for url in parser.urls:
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        pathname = unquote(parsed.path)
        if pathname.startswith('/'):
            assert pathname.startswith(base), 'URL escapes baseurl: ' + url
            target = (site / pathname[len(base):]).resolve()
        else:
            target = (folder / pathname).resolve()
        assert target.is_relative_to(site), 'URL escapes site: ' + url
        if target.is_dir():
            target = target / 'index.html'
        assert target.is_file(), 'Broken local link: ' + url
    return parser


def check_static(site, base, root_canonical):
    """The generated pages: one per ABI and per syscall name of the built data, in each language."""
    paths = static_pages.page_paths(static_pages.load(site))
    built = {}
    for lang, listed in paths.items():
        for index, relative in enumerate(listed):
            page = built[relative] = check_page(site, base, relative)
            assert page.language == lang, 'Wrong content language: ' + relative
            # Each page names itself and its translation, and English is the default.
            expected = {code: root_canonical + other[index] for code, other in paths.items()}
            expected['x-default'] = expected['en']
            assert page.alternates == expected, 'Wrong hreflang alternates: ' + relative
            assert not any(script.endswith('/app.js') for script in page.scripts), 'Static page loads the application: ' + relative
    on_disk = {p.parent.relative_to(site).as_posix() + '/' for folder in static_pages.OUTPUT_DIRS for p in (site / folder).rglob('index.html')}
    assert on_disk == built.keys(), 'Static pages differ from the built data: {}'.format(sorted(on_disk ^ built.keys())[:5])
    return built


def check_abi(site):
    """The errno, signal and ioctl data: documents present, bundled inputs unmodified."""
    manifest = json.loads((site / 'data/abi/manifest.json').read_text())
    assert manifest['latest'] == manifest['versions'][0], 'ABI manifest does not name its newest release'
    for version in manifest['versions']:
        folder = site / 'data/abi' / version
        sources = json.loads((folder / 'sources.json').read_text())
        assert sources['kernel'] == version and sources['documents'] == manifest['documents'], 'ABI release differs from its manifest: ' + version
        for name in sources['documents']:
            document = json.loads((folder / name).read_text())
            assert document['kernel'] == version and document['provenance']['files'] == sources['files'], 'ABI document without matching provenance: ' + name
        for source in sources['files']:
            data = (folder / source['bundled_path']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == source['sha256'], 'Modified kernel source: ' + source['path']
        bundled = {p.relative_to(folder).as_posix() for p in (folder / 'sources').rglob('*') if p.is_file()}
        assert bundled == {source['bundled_path'] for source in sources['files']}, 'Unrecorded file among the ABI sources: ' + version
    return manifest


def check(site, baseurl):
    site = site.resolve()
    base = '/' + baseurl.strip('/') + '/' if baseurl.strip('/') else '/'
    parser = check_page(site, base, '')
    sections = {relative: check_page(site, base, relative) for relative in APPLICATION_PAGES}
    link_count = len(parser.urls) + sum(len(section.urls) for section in sections.values())
    for module in ['app.js', 'catalog.mjs', 'paths.mjs', 'examples.mjs', 'abi.js', 'abi.mjs', 'abi-copy.mjs']:
        text = (site / module).read_text()
        for imported in re.findall(r"from ['\"]([^'\"]+)['\"]", text):
            assert imported.startswith('./'), 'Module import must be relative: ' + imported
            assert (site / imported).is_file(), 'Missing module: ' + imported
    assert '/api/v1/syscalls/' not in (site / 'app.js').read_text(), 'Frontend still depends on the Node API'
    manifest = json.loads((site / 'data/manifest.json').read_text())
    paths = manifest.get('version_paths', {})
    availability = manifest.get('version_architectures', {})
    architectures = [arch['id'] for arch in manifest['architectures']]
    sitemap = ET.parse(site / 'sitemap.xml')
    locations = [element.text for element in sitemap.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
    # Every page declares one canonical URL; the sitemap lists exactly those
    # pages, once each, and never a query-string view of one.
    assert locations, 'Empty sitemap'
    assert len(locations) == len(set(locations)), 'Duplicate sitemap URL'
    static = check_static(site, base, parser.canonical or '')
    link_count += sum(len(page.urls) for page in static.values())
    pages = {base: parser, **{base + relative: section for relative, section in {**sections, **static}.items()}}
    root_canonical = urlsplit(parser.canonical or '')
    for path, built in pages.items():
        relative = path[len(base):]
        canonical = urlsplit(built.canonical or '')
        assert built.canonical and not canonical.query and not canonical.fragment, 'Missing or parameterized canonical URL: ' + path
        assert built.canonical == parser.canonical + relative, 'Canonical URL is not this page: ' + built.canonical
    for url in locations:
        parsed = urlsplit(url)
        assert parsed.path in pages and not parsed.query and not parsed.fragment, 'Sitemap URL contradicts the canonical URL: ' + url
        if root_canonical.path == base:
            assert url == pages[parsed.path].canonical, 'Sitemap URL differs from the canonical URL: ' + url
    assert {urlsplit(url).path for url in locations} == pages.keys(), 'Sitemap does not list every page'
    # The landing page must lead to every section.
    for relative in SECTION_PAGES + ['call/'] + [path for path in static if path.startswith('arch/')]:
        assert any(urlsplit(url).path == base + relative for url in parser.urls), 'Landing page does not link to ' + relative
    parser_tr = sections['tr/']
    for relative in ['tr/' + p for p in SECTION_PAGES] + ['tr/call/'] + [path for path in static if path.startswith('tr/arch/')]:
        assert any(urlsplit(url).path == base + relative for url in parser_tr.urls), 'Turkish landing page does not link to ' + relative
    assert '/api/v1/syscalls/' not in (site / 'abi.js').read_text(), 'Section pages depend on the Node API'
    abi = check_abi(site)
    api_index = json.loads((site / 'api/v1/index.json').read_text())
    expected_tables = {
        (version, arch): '../../data/{}/{}.json'.format(paths.get(version, version), arch)
        for version in manifest['versions']
        for arch in availability.get(version, architectures)
    }
    assert {(item['version'], item['architecture']): item['url'] for item in api_index['tables']} == expected_tables, 'Static API index differs from the built manifest'
    for item in api_index['tables']:
        assert (site / 'api/v1' / item['url']).is_file(), 'Missing static API table'
    for version in manifest['versions']:
        folder = site / 'data' / paths.get(version, version)
        sources = json.loads((folder / 'sources.json').read_text())
        for source in sources['files']:
            data = (folder / source['bundled_path']).read_bytes()
            assert hashlib.sha256(data).hexdigest() == source['sha256'], 'Modified kernel source: ' + source['path']
    notice = (site / 'licensing.txt').read_text()
    assert '{{' not in notice and not notice.startswith('---'), 'Unprocessed license notices'
    with tarfile.open(site / 'downloads/syscall-reference-source.tar.gz') as archive:
        members = archive.getmembers()
        names = {m.name for m in members}
        for required in ['LICENSE', 'LICENSING.md', 'Gemfile.lock', '_config.yml', 'scripts/sync_kernel.py', 'scripts/sync_abi.py', 'scripts/prepare_site.py', 'public/data/abi/manifest.json', 'sources/manual-pages.json', 'sources/introductions.json', 'public/_layouts/default.html']:
            assert 'syscall-reference/' + required in names, 'Source archive missing ' + required
        for member in members:
            assert member.isfile(), 'Archive contains a non-file entry'
            parts = Path(member.name).parts
            assert not any(p in {'.git', '.cache', '.bundle', 'vendor', '_site', '__pycache__'} or p.startswith('.env') for p in parts), 'Local state in source archive'
    print('Verified Jekyll output at {} (baseurl {}, {} pages, {} local links, ABI data for {}, {} source files in archive).'.format(site, base, len(pages), link_count, ', '.join(abi['versions']), len(names)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=Path('_site'))
    parser.add_argument('--baseurl', default='')
    args = parser.parse_args()
    check(args.site, args.baseurl)
