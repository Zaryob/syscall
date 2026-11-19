# SPDX-License-Identifier: GPL-2.0-only
"""The generated pages per ABI and per syscall name, checked against the bundled data."""
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public'


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


prepare = module('prepare_site')
static_pages = module('static_pages')


class Page(HTMLParser):
    """Links, element ids and table rows (as lists of cell texts) of one generated document."""
    def __init__(self, text):
        super().__init__()
        self.links, self.ids, self.rows, self.cell = [], set(), [], None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'tr':
            self.rows.append([])
        if tag in ('td', 'th') and self.rows:
            self.rows[-1].append('')
            self.cell = True

    def handle_endtag(self, tag):
        if tag in ('td', 'th'):
            self.cell = None

    def handle_data(self, data):
        if self.cell and self.rows and self.rows[-1]:
            self.rows[-1][-1] += data


def front_matter(text):
    head = text.split('---\n')[1]
    return {key: json.loads(value) for key, value in (line.split(': ', 1) for line in head.splitlines())}


class StaticPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.output = Path(cls.directory.name)
        cls.result = static_pages.generate(PUBLIC, prepare.editorial_notes(), cls.output)
        cls.manifest = json.loads((PUBLIC / 'data/manifest.json').read_bytes())
        cls.latest = cls.manifest['latest']
        folder = PUBLIC / 'data' / cls.manifest['version_paths'][cls.latest]
        cls.tables = {arch: json.loads((folder / (arch + '.json')).read_bytes())
                      for arch in cls.manifest['version_architectures'][cls.latest]}
        cls.labels = {arch['id']: arch['label'] for arch in cls.manifest['architectures']}

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def read(self, path):
        return (self.output / static_pages.source_file(path)).read_text()

    def number(self, arch, name):
        return next(row['number'] for row in self.tables[arch]['syscalls'] if row['name'] == name)

    def test_page_count_matches_the_data(self):
        names = set()
        for version in self.manifest['versions']:
            for arch in self.manifest['version_architectures'][version]:
                table = json.loads((PUBLIC / 'data' / self.manifest['version_paths'][version] / (arch + '.json')).read_bytes())
                names.update(row['name'] for row in table['syscalls'])
        expected = {'call/'} | {'arch/{}/'.format(arch) for arch in self.tables} | {'call/{}/'.format(name) for name in names}
        self.assertEqual(set(self.result['paths']['en']), expected)
        self.assertEqual(set(self.result['paths']['tr']), {'tr/' + path for path in expected})
        self.assertEqual(self.result['pages'], 2 * len(expected))
        written = [path for path in self.output.rglob('*') if path.is_file()]
        self.assertEqual(len(written), 2 * len(expected))
        # Jekyll ignores names with a leading underscore, so no source file may carry one.
        self.assertFalse([path for path in written if any(part.startswith('_') for part in path.relative_to(self.output).parts)])
        self.assertIn('call/_llseek/', expected)
        for lang, paths in self.result['paths'].items():
            for path in paths:
                front = front_matter(self.read(path))
                self.assertEqual((front['permalink'], front['lang'], front['layout']), ('/' + path, lang, 'default'))
                self.assertEqual({alternate['lang'] for alternate in front['alternates']}, {'en', 'tr'})
                self.assertIn({'lang': lang, 'url': '/' + path}, front['alternates'])
                self.assertEqual(front['breadcrumbs'][-1]['url'], '/' + path)
                self.assertTrue(front['title'] and front['description'])
        titles = [front_matter(self.read(path))['title'] for paths in self.result['paths'].values() for path in paths]
        self.assertEqual(len(titles), len(set(titles)))

    def test_openat_shows_the_numbers_of_the_data_on_each_abi(self):
        self.assertEqual({arch: self.number(arch, 'openat') for arch in ['x64', 'arm64', 'riscv64']}, {'x64': 257, 'arm64': 56, 'riscv64': 56})
        for lang in ['en', 'tr']:
            text = self.read(('tr/' if lang == 'tr' else '') + 'call/openat/')
            rows = {row[0]: row for row in Page(text).rows if row}
            for arch, table in self.tables.items():
                entry = next(row for row in table['syscalls'] if row['name'] == 'openat')
                row = rows[self.labels[arch]]
                self.assertEqual(row[1:3], [str(entry['number']), hex(entry['number'])])
                self.assertIn(entry['entry'], row[3])
                convention = table['calling_convention']
                self.assertEqual(row[4:6], [convention['instruction'], convention['nr']])
                for register in convention['registers']:
                    self.assertIn(register, row[6])
            self.assertIn('asmlinkage long sys_openat(int dfd, const char __user *filename, int flags, umode_t mode);', text)
            self.assertIn('https://man7.org/linux/man-pages/man2/openat.2.html', text)
            self.assertIn('{}?arch=arm64&amp;kernel={}#sys-{}%3A56%3Aopenat'.format('tr/' if lang == 'tr' else '', self.latest, self.latest), text)
        front = front_matter(self.read('call/openat/'))
        self.assertIn('x86-64 257', front['description'])
        self.assertIn(prepare.editorial_notes()['openat']['en'], front['description'])
        self.assertIn(prepare.editorial_notes()['openat']['tr'], self.read('tr/call/openat/'))
        self.assertIn('Introduced in Linux 2.6.16.', self.read('call/openat/'))
        self.assertIn('<strong>First appeared:</strong> Linux 2.6.16', self.read('call/openat/'))
        self.assertIn('İlk olarak Linux 2.6.16 sürümünde eklendi.', self.read('tr/call/openat/'))
        self.assertIn('<strong>İlk kez eklendiği sürüm:</strong> Linux 2.6.16', self.read('tr/call/openat/'))
        page = Page(self.read('call/openat/'))
        release_rows = {row[0]: row[2] for row in page.rows if len(row) == 3 and row[0].startswith('Linux ')}
        self.assertEqual(release_rows['Linux 7.3'], 'x86-64 · i386 · AArch64 · ARM EABI · RISC-V 64 · LoongArch 64 · PowerPC 64 · PowerPC 32 · IBM Z (s390x) · MIPS o32 · MIPS n32 · MIPS n64')
        self.assertEqual(release_rows['Linux 4.15'], 'x86-64 · i386 · AArch64 · ARM EABI · RISC-V 64')
        self.assertEqual(release_rows['Linux 2.6.16'], 'x86-64 · i386')
        self.assertNotIn('all 12', self.read('call/openat/'))
        self.assertNotIn('tümü (12)', self.read('tr/call/openat/'))
        self.assertIn('<a href="../../?arch=x86&amp;kernel=v3.0#sys-v3.0%3A295%3Aopenat">i386</a>', self.read('call/openat/'))
        self.assertIn('<a href="../../../tr/?arch=x86&amp;kernel=v3.0#sys-v3.0%3A295%3Aopenat">i386</a>', self.read('tr/call/openat/'))
        self.assertIn('<a href="../../?arch=x86&amp;kernel=v3.0#sys-v3.0%3A328%3Aeventfd2">i386</a>', self.read('call/eventfd2/'))
        self.assertIn('<a href="../../../tr/?arch=x86&amp;kernel=v3.0#sys-v3.0%3A328%3Aeventfd2">i386</a>', self.read('tr/call/eventfd2/'))

    def test_introduction_version_is_rendered(self):
        self.assertIn('Introduced in Linux 1.0 (or earlier).', self.read('call/read/'))
        self.assertIn('İlk olarak Linux 1.0 (veya öncesi) sürümünde eklendi.', self.read('tr/call/read/'))
        self.assertIn('Introduced in Linux 5.3.', self.read('call/clone3/'))
        self.assertIn('<strong>First appeared:</strong> Linux 5.3', self.read('call/clone3/'))
        self.assertIn('İlk olarak Linux 5.3 sürümünde eklendi.', self.read('tr/call/clone3/'))
        self.assertIn('<strong>İlk kez eklendiği sürüm:</strong> Linux 5.3', self.read('tr/call/clone3/'))
        self.assertIn('First appeared:</strong> Linux 2.6 (x86-64; i386 since 4.12)', self.read('call/arch_prctl/'))
        self.assertIn('İlk kez eklendiği sürüm:</strong> Linux 2.6 (x86-64; i386 için 4.12 sürümünden beri)', self.read('tr/call/arch_prctl/'))
        self.assertNotIn('First appeared:', self.read('call/reserved82/'))

    def test_a_call_absent_from_an_abi_says_so(self):
        absent = [arch for arch, table in self.tables.items() if not any(row['name'] == 'open' for row in table['syscalls'])]
        self.assertIn('arm64', absent)
        rows = {row[0]: row for row in Page(self.read('call/open/')).rows if row}
        for arch in self.tables:
            row = rows[self.labels[arch]]
            if arch in absent:
                self.assertEqual(row[1], 'Not in the Linux {} table for this ABI.'.format(self.latest[1:]))
            else:
                self.assertEqual(row[1], str(self.number(arch, 'open')))
        self.assertIn('It has no table entry on: ' + ', '.join(self.labels[arch] for arch in self.tables if arch in absent), self.read('call/open/'))
        # A reserved slot is not presented as an available call.
        reserved = next(row for row in self.tables['x64']['syscalls'] if row['status'] == 'unimplemented')
        rows = {row[0]: row for row in Page(self.read('call/{}/'.format(reserved['name']))).rows if row}
        self.assertEqual(rows['x86-64'][1:4], [str(reserved['number']), hex(reserved['number']), 'Reserved slot; no implementation.'])

    def test_abi_table_lists_every_entry_with_decimal_and_hex_numbers(self):
        for arch, table in self.tables.items():
            page = Page(self.read('arch/{}/'.format(arch)))
            rows = [row for row in page.rows if len(row) == 5 and row[0].isdigit()]
            self.assertEqual([(row[0], row[1]) for row in rows], [(str(entry['number']), hex(entry['number'])) for entry in table['syscalls']])
            self.assertEqual([row[2].split(' ')[0] for row in rows], [entry['name'] for entry in table['syscalls']])
            for row, entry in zip(rows, table['syscalls']):
                if entry['status'] != 'unimplemented' and entry['arguments']:
                    self.assertEqual(row[3], ', '.join(entry['arguments']))
            for link in ['../../call/{}/'.format(entry['name']) for entry in table['syscalls']]:
                self.assertIn(link, page.links)
        text = self.read('arch/x64/')
        self.assertIn('?arch=x64&amp;kernel={}#reference'.format(self.latest), text)
        for value in ['syscall', 'rax', 'rdi, rsi, rdx, r10, r8, r9']:
            self.assertIn('<code>{}</code>'.format(value), text)

    def test_abi_pages_link_each_number_range_to_its_first_row(self):
        for lang, prefix in [('en', ''), ('tr', 'tr/')]:
            for arch, table in self.tables.items():
                text = self.read('{}arch/{}/'.format(prefix, arch))
                numbers = [entry['number'] for entry in table['syscalls']]
                starts = sorted({number // 100 * 100 for number in numbers})
                links = re.findall(r'<li><a href="#n-(\d+)">(\d+)–(\d+)</a></li>', text)
                self.assertEqual([(int(a), int(b), int(c)) for a, b, c in links],
                                 [(start, start, max(n for n in numbers if n // 100 * 100 == start)) for start in starts], arch)
                for start in starts:
                    first = next(number for number in numbers if number // 100 * 100 == start)
                    self.assertIn('<tr id="n-{}"><td class="abi-number">{}</td>'.format(start, first), text)
                # The filter needs the script, so the page ships it hidden; the range links work without it.
                self.assertIn('<form class="static-filter" role="search" hidden', text)
                self.assertIn('<a class="static-filter-link" href="#static-filter" hidden>{}<span'.format('Search' if lang == 'en' else 'Ara'), text)

    def test_every_internal_link_resolves(self):
        pages = {path for paths in self.result['paths'].values() for path in paths}
        ids = {path: Page(self.read(path)).ids for path in pages}
        checked = 0
        for path in sorted(pages):
            for link in Page(self.read(path)).links:
                url = urlsplit(link)
                if url.scheme or url.netloc:
                    self.assertEqual(url.scheme, 'https', link)
                    continue
                parts = []
                for part in (path + unquote(url.path)).split('/')[:-1]:
                    if part == '..':
                        self.assertTrue(parts, 'Link leaves the site: {} on {}'.format(link, path))
                        parts.pop()
                    elif part != '.':
                        parts.append(part)
                target = '/'.join(parts) + '/' if parts else ''
                leaf = unquote(url.path).rsplit('/', 1)[-1]
                if leaf:
                    self.assertTrue((PUBLIC / target / leaf).is_file(), 'Broken link {} on {}'.format(link, path))
                elif target in pages:
                    if url.fragment:
                        self.assertIn(url.fragment, ids[target], 'Missing fragment {} on {}'.format(link, path))
                else:
                    # The application and its sections are hand-written documents in public/.
                    self.assertTrue((PUBLIC / target / 'index.html').is_file(), 'Broken link {} on {}'.format(link, path))
                checked += 1
        self.assertGreater(checked, 30000)

    def test_generation_replaces_stale_output_and_stays_out_of_the_source_archive(self):
        stale = self.output / 'call/sys_gone.html'
        stale.write_text('stale')
        static_pages.generate(PUBLIC, prepare.editorial_notes(), self.output)
        self.assertFalse(stale.exists())
        ignored = (ROOT / '.gitignore').read_text().splitlines()
        for folder in static_pages.OUTPUT_DIRS:
            self.assertIn('/public/{}/'.format(folder), ignored)

    def test_names_that_are_not_url_safe_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)
            (public / 'data/v9.0').mkdir(parents=True)
            (public / 'data/manifest.json').write_text(json.dumps({'latest': 'v9.0', 'versions': ['v9.0'], 'architectures': [{'id': 'x64', 'label': 'x86-64'}]}))
            (public / 'data/v9.0/x64.json').write_text(json.dumps({'syscalls': [{'number': 0, 'name': '../x', 'status': 'defined'}]}))
            with self.assertRaises(ValueError):
                static_pages.generate(public, {}, public / 'out')


if __name__ == '__main__':
    unittest.main()
