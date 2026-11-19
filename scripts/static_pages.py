#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate crawlable HTML pages from the bundled syscall snapshots.

One page per ABI (arch/<id>/), one per syscall name (call/<name>/) and an
index (call/), in English and under tr/ in Turkish. Every fact comes from
public/data/ and the summaries in notes.mjs; the pages are Jekyll documents
that use the default layout, so the header and theme stay in one place.

The output is not committed: prepare_site.py calls generate() before every
build, the same way it writes public/api/ and public/downloads/.
"""
from html import escape
import json
from pathlib import Path
import re
import shutil
from urllib.parse import quote

LANGUAGES = ['en', 'tr']
# Directories this script owns under public/; each is removed and rewritten.
OUTPUT_DIRS = ['arch', 'call', 'tr/arch', 'tr/call']
SAFE_NAME = re.compile(r'[A-Za-z0-9_]+')

TEXT = {
    'en': {
        'site': 'Linux System Call Reference',
        'index_crumb': 'All system calls',
        'other_language': 'Türkçe',
        'breadcrumb': 'Breadcrumb',
        'abi_title': '{label} Linux system call table (Linux {release}) — numbers, signatures, registers',
        'abi_h1': '{label} Linux system call table',
        'abi_description': 'Every {label} system call number in Linux {release}, in decimal and hex, with kernel C parameters, the syscall instruction and the argument registers. {defined} calls, generated from {table}.',
        'abi_lede': 'The {label} system call table of Linux {release}: {defined} implemented calls{reserved}. Numbers and entry points come from {table}; C parameters come from the kernel headers and sources.',
        'abi_reserved': ' and {count} reserved slots without an implementation',
        'interactive_abi': 'Open the interactive {label} table →',
        'interactive_help': 'Search, compare kernel releases, see the register of each argument and download C examples.',
        'convention': 'Calling convention',
        'instruction': 'Instruction',
        'nr': 'System call number (NR)',
        'result': 'Return value',
        'arguments_locations': 'Arguments (ARG1–ARG6)',
        'error_flag': 'Error flag',
        'stack': 'Stack',
        'raw': 'These are the raw kernel conventions. The C library provides its own wrappers.',
        'convention_more': 'Second result register, clobbered registers and PowerPC notes',
        'bits32': 'On 32-bit ABIs, 64-bit values may occupy multiple registers and require alignment; assembly wrappers may reorder them. See',
        'table_caption': '{label} system calls in Linux {release}',
        'table_region': 'System call table; scroll horizontally on narrow screens',
        'no': 'No.',
        'hex': 'Hex',
        'call': 'System call',
        'arguments': 'Arguments',
        'what': 'What it does',
        'unresolved': 'not resolved',
        'unimplemented': 'unimplemented',
        'other_abis': 'Other ABIs',
        'json': 'This table as JSON',
        'jump': 'Jump to',
        'jump_nav': 'Jump to a system call number range',
        'filter': 'Search',
        'filter_more': ' this table',
        'filter_hint': 'name or number, e.g. openat or 257',
        'filter_count': '{shown} / {total} rows',
        'sections': 'Reference sections',
        'tables': 'Interactive system call tables',
        'errno': 'errno values',
        'signals': 'Signals',
        'ioctl': 'ioctl requests',
        'call_title': '{name} — Linux system call numbers by architecture (Linux {release})',
        'call_title_reserved': '{name} — reserved Linux system call table slot (Linux {release})',
        'call_title_earlier': '{name} — Linux system call in earlier kernel releases',
        'call_kind': 'Linux system call',
        'summary': 'In Linux {release}, {name} is defined in the system call table of {count} of the {total} bundled ABIs.',
        'summary_missing': 'It has no table entry on: {list}.',
        'summary_reserved': 'Its number is a reserved slot without an implementation on: {list}.',
        'call_description_numbers': 'Linux {release} numbers: {pairs}{more}.',
        'call_description_more': ' and {count} more ABIs',
        'call_description_tail': 'Signature, entry point and argument registers on each ABI.',
        'call_description_absent': '{name} has no implemented entry in the Linux {release} system call tables of the {total} bundled ABIs.',
        'numbers': 'Number on each ABI',
        'numbers_caption': '{name} in the Linux {release} system call tables',
        'entry': 'Entry point',
        'nr_short': 'NR',
        'locations': 'Argument locations',
        'kernel_table': 'Kernel table',
        'interactive': 'Interactive view',
        'open': 'Open',
        'open_label': 'Open {name} in the interactive {label} table',
        'missing': 'Not in the Linux {release} table for this ABI.',
        'reserved': 'Reserved slot; no implementation.',
        'enosys': 'No implementation for this ABI in this release; the call returns ENOSYS.',
        'compat': 'compat:',
        'noreturn': 'does not return',
        'locations_note': 'Argument locations are the ABI’s calling convention for ARG1–ARG6 in order, not an assignment made for this call.',
        'availability': 'A table entry does not mean the call exists in every kernel: most optional calls return ENOSYS when the matching configuration option or architecture support is not built.',
        'declaration': 'Kernel declaration',
        'declaration_source': 'Declaration:',
        'definition_source': 'Syscall definition:',
        'configuration': 'The architecture’s Kconfig selections determine the declaration for this ABI:',
        'libc': 'Signatures are kernel declarations and may differ from the C library wrappers.',
        'unresolved_configuration_dependent': 'The C declaration depends on the kernel configuration.',
        'unresolved_wrapper_entry': 'The kernel table points to a wrapper. Its C declaration is unavailable.',
        'unresolved_not_found': 'C declaration not found in the imported kernel sources.',
        'unresolved_default': 'C declaration not resolved in the imported headers.',
        'no_declaration': 'No ABI defines this call in Linux {release}, so there is no declaration to show.',
        'releases': 'Bundled kernel releases',
        'releases_caption': 'Bundled releases whose tables define {name}',
        'release': 'Release',
        'bundled': 'ABIs bundled',
        'defined_on': 'Defined in the table of',
        'all': 'all {count}',
        'none': 'none',
        'first_appeared': 'First appeared:',
        'introduced_summary': 'Introduced in {version}.',
        'version_1_0_or_earlier': 'Linux 1.0 (or earlier)',
        'releases_note': 'Each release is a separate snapshot, and older releases bundle fewer ABIs. This table does not claim the release in which the call first appeared. Numbers are listed where a release differs from Linux {release}.',
        'releases_note_introduced': 'Each release is a separate snapshot, and older releases bundle fewer ABIs. Numbers are listed where a release differs from Linux {release}.',
        'manual': 'Manual page',
        'no_manual': 'No manual link is available for this entry.',
        'index_title': 'Linux system calls A–Z — {count} calls on {abis} ABIs (Linux {release})',
        'index_h1': 'Linux system calls A–Z',
        'index_description': 'Index of {count} Linux system call names with their numbers on {abis} ABIs, and one plain HTML table per ABI for Linux {release}: {labels}.',
        'index_lede': 'Every system call name in the bundled Linux {release} tables. Each name leads to its numbers, entry points and registers on all {abis} ABIs.',
        'by_abi': 'Tables by ABI',
        'calls_count': '{count} calls',
        'by_name': 'System calls by name',
        'letters': 'Jump to a letter',
        'leftovers': 'Reserved slots and calls from earlier releases',
        'leftovers_note': 'These names have no implemented entry in Linux {release}: reserved table slots, and calls that only earlier bundled releases define.',
    },
    'tr': {
        'site': 'Linux Sistem Çağrıları Referansı',
        'index_crumb': 'Tüm sistem çağrıları',
        'other_language': 'English',
        'breadcrumb': 'Sayfa yolu',
        'abi_title': '{label} Linux sistem çağrısı tablosu (Linux {release}) — numaralar, bildirimler, yazmaçlar',
        'abi_h1': '{label} Linux sistem çağrısı tablosu',
        'abi_description': 'Linux {release} için {label} sistem çağrısı numaralarının tamamı: onluk ve onaltılık numaralar, çekirdek C parametreleri, sistem çağrısı komutu ve argüman yazmaçları. {defined} çağrı; kaynak: {table}.',
        'abi_lede': 'Linux {release} sürümünün {label} sistem çağrısı tablosu: {defined} tanımlı çağrı{reserved}. Numaralar ve giriş noktaları {table} dosyasından, C parametreleri çekirdek başlıklarından ve kaynaklarından alınmıştır.',
        'abi_reserved': ' ve gerçeklenmemiş {count} ayrılmış yuva',
        'interactive_abi': 'Etkileşimli {label} tablosunu aç →',
        'interactive_help': 'Arama yapın, çekirdek sürümlerini karşılaştırın, her argümanın yazmacını görün ve C örneklerini indirin.',
        'convention': 'Çağrı kuralı',
        'instruction': 'Komut',
        'nr': 'Sistem çağrısı numarası (NR)',
        'result': 'Dönüş değeri',
        'arguments_locations': 'Argümanlar (ARG1–ARG6)',
        'error_flag': 'Hata bayrağı',
        'stack': 'Yığın',
        'raw': 'Bunlar doğrudan çekirdek kurallarıdır. C kütüphanesi kendi sarmalayıcılarını sunar.',
        'convention_more': 'İkinci sonuç yazmacı, bozulan yazmaçlar ve PowerPC notları',
        'bits32': '32 bit ABI’lerde 64 bit değerler birden fazla yazmaç ve hizalama gerektirebilir; assembly sarmalayıcıları sırayı değiştirebilir. Ayrıntılar:',
        'table_caption': 'Linux {release} sürümünde {label} sistem çağrıları',
        'table_region': 'Sistem çağrısı tablosu; dar ekranlarda yatay kaydırın',
        'no': 'No.',
        'hex': 'Onaltılık',
        'call': 'Sistem çağrısı',
        'arguments': 'Argümanlar',
        'what': 'Ne yapar',
        'unresolved': 'çözümlenemedi',
        'unimplemented': 'gerçeklenmemiş',
        'other_abis': 'Diğer ABI’ler',
        'json': 'Bu tablonun JSON hâli',
        'jump': 'Atla',
        'jump_nav': 'Sistem çağrısı numarası aralığına atla',
        'filter': 'Ara',
        'filter_more': ' (bu tabloda)',
        'filter_hint': 'ad ya da numara, ör. openat veya 257',
        'filter_count': '{shown} / {total} satır',
        'sections': 'Referans bölümleri',
        'tables': 'Etkileşimli sistem çağrısı tabloları',
        'errno': 'errno değerleri',
        'signals': 'Sinyaller',
        'ioctl': 'ioctl istekleri',
        'call_title': '{name} — mimarilere göre Linux sistem çağrısı numaraları (Linux {release})',
        'call_title_reserved': '{name} — ayrılmış Linux sistem çağrısı tablo yuvası (Linux {release})',
        'call_title_earlier': '{name} — önceki çekirdek sürümlerindeki Linux sistem çağrısı',
        'call_kind': 'Linux sistem çağrısı',
        'summary': 'Linux {release} sürümünde {name} çağrısının sistem çağrısı tablosunda tanımlı olduğu ABI sayısı: {count} / {total}.',
        'summary_missing': 'Tabloda yer almadığı ABI’ler: {list}.',
        'summary_reserved': 'Numarasının gerçeklenmemiş ayrılmış yuva olduğu ABI’ler: {list}.',
        'call_description_numbers': 'Linux {release} numaraları: {pairs}{more}.',
        'call_description_more': ' ve {count} ABI daha',
        'call_description_tail': 'Her ABI için bildirim, giriş noktası ve argüman yazmaçları.',
        'call_description_absent': '{name}, kayıtlı {total} ABI’nin Linux {release} sistem çağrısı tablolarında tanımlı değildir.',
        'numbers': 'Her ABI’deki numara',
        'numbers_caption': 'Linux {release} sistem çağrısı tablolarında {name}',
        'entry': 'Giriş noktası',
        'nr_short': 'NR',
        'locations': 'Argüman konumları',
        'kernel_table': 'Çekirdek tablosu',
        'interactive': 'Etkileşimli görünüm',
        'open': 'Aç',
        'open_label': '{name} çağrısını etkileşimli {label} tablosunda aç',
        'missing': 'Bu ABI’nin Linux {release} tablosunda yok.',
        'reserved': 'Ayrılmış yuva; gerçeklenmemiş.',
        'enosys': 'Bu sürümde bu ABI için tanımı yok; çağrı ENOSYS döner.',
        'compat': 'uyumluluk:',
        'noreturn': 'geri dönmez',
        'locations_note': 'Argüman konumları, ABI’nin ARG1–ARG6 için sırasıyla kullandığı çağrı kuralıdır; bu çağrıya özel bir atama değildir.',
        'availability': 'Tabloda yer almak, çağrının her çekirdekte bulunduğu anlamına gelmez: isteğe bağlı çağrıların çoğu, ilgili yapılandırma seçeneği veya mimari desteği derlenmemişse ENOSYS döner.',
        'declaration': 'Çekirdek bildirimi',
        'declaration_source': 'Bildirim:',
        'definition_source': 'Sistem çağrısının tanımı:',
        'configuration': 'Bu ABI için bildirimi mimarinin Kconfig seçimleri belirler:',
        'libc': 'Bildirimler çekirdeğe aittir; C kütüphanesi sarmalayıcılarından farklı olabilir.',
        'unresolved_configuration_dependent': 'C bildirimi çekirdek yapılandırmasına bağlı.',
        'unresolved_wrapper_entry': 'Çekirdek tablosu bir sarmalayıcıya işaret ediyor. C bildirimi bulunamadı.',
        'unresolved_not_found': 'C bildirimi içe aktarılan çekirdek kaynaklarında bulunamadı.',
        'unresolved_default': 'İçe aktarılan başlıklarda C bildirimi çözümlenemedi.',
        'no_declaration': 'Linux {release} sürümünde bu çağrıyı tanımlayan ABI olmadığı için gösterilecek bildirim yok.',
        'releases': 'Kayıtlı çekirdek sürümleri',
        'releases_caption': 'Tablolarında {name} tanımlı olan kayıtlı sürümler',
        'release': 'Sürüm',
        'bundled': 'Kayıtlı ABI sayısı',
        'defined_on': 'Tablosunda tanımlı olduğu ABI’ler',
        'all': 'tümü ({count})',
        'none': 'yok',
        'first_appeared': 'İlk kez eklendiği sürüm:',
        'introduced_summary': 'İlk olarak {version} sürümünde eklendi.',
        'version_1_0_or_earlier': 'Linux 1.0 (veya öncesi)',
        'releases_note': 'Her sürüm ayrı bir veri kümesidir ve eski sürümlerde daha az ABI kayıtlıdır. Bu tablo, çağrının ilk kez hangi sürümde eklendiğini iddia etmez. Numaralar, sürümün Linux {release} ile farklılaştığı yerlerde yazılır.',
        'releases_note_introduced': 'Her sürüm ayrı bir veri kümesidir ve eski sürümlerde daha az ABI kayıtlıdır. Numaralar, sürümün Linux {release} ile farklılaştığı yerlerde yazılır.',
        'manual': 'Kılavuz sayfası',
        'no_manual': 'Bu girdi için man sayfası bağlantısı yok.',
        'index_title': 'A’dan Z’ye Linux sistem çağrıları — {abis} ABI, {count} çağrı (Linux {release})',
        'index_h1': 'A’dan Z’ye Linux sistem çağrıları',
        'index_description': '{abis} ABI’deki numaralarıyla {count} Linux sistem çağrısı adının dizini ve Linux {release} için her ABI’nin düz HTML tablosu: {labels}.',
        'index_lede': 'Kayıtlı Linux {release} tablolarındaki bütün sistem çağrısı adları. Her ad, {abis} ABI’nin tamamındaki numaralara, giriş noktalarına ve yazmaçlara götürür.',
        'by_abi': 'ABI’ye göre tablolar',
        'calls_count': '{count} çağrı',
        'by_name': 'Ada göre sistem çağrıları',
        'letters': 'Harfe git',
        'leftovers': 'Ayrılmış yuvalar ve önceki sürümlerdeki çağrılar',
        'leftovers_note': 'Bu adların Linux {release} sürümünde tanımlı bir girdisi yok: ayrılmış tablo yuvaları ve yalnızca önceki kayıtlı sürümlerin tanımladığı çağrılar.',
    },
}


def defined(row):
    return row.get('status') != 'unimplemented'


def load(public):
    """Read the manifest and every bundled table; nothing else feeds the pages."""
    manifest = json.loads((public / 'data/manifest.json').read_bytes())
    paths = manifest.get('version_paths', {})
    ids = [arch['id'] for arch in manifest['architectures']]
    availability = manifest.get('version_architectures', {})
    tables = {}
    for version in manifest['versions']:
        for arch in availability.get(version, ids):
            path = public / 'data' / paths.get(version, version) / (arch + '.json')
            if path.is_file():
                tables[version, arch] = json.loads(path.read_bytes())
    latest = manifest['latest']
    architectures = [arch for arch in manifest['architectures'] if (latest, arch['id']) in tables]
    # name -> ABI -> rows of the latest release, in table order.
    current = {}
    # name -> release -> ABI -> numbers of the implemented entries.
    history = {}
    for (version, arch), table in tables.items():
        for row in table.get('syscalls', []):
            name = row.get('name')
            if not name:
                continue
            if not SAFE_NAME.fullmatch(name):
                raise ValueError('Syscall name is not usable as a URL path: {!r}'.format(name))
            if version == latest:
                current.setdefault(name, {}).setdefault(arch, []).append(row)
            if defined(row):
                history.setdefault(name, {}).setdefault(version, {}).setdefault(arch, []).append(row['number'])
    names = sorted(set(current) | set(history))
    return {
        'manifest': manifest, 'latest': latest, 'tables': tables, 'architectures': architectures,
        'current': current, 'history': history, 'names': names,
        'bundled': {version: [arch for arch in ids if (version, arch) in tables] for version in manifest['versions']},
    }


def page_paths(data):
    """Site-relative directory of every generated page, per language."""
    relative = ['call/'] + ['arch/{}/'.format(arch['id']) for arch in data['architectures']] + ['call/{}/'.format(name) for name in data['names']]
    return {lang: [('tr/' if lang == 'tr' else '') + path for path in relative] for lang in LANGUAGES}


def source_file(path):
    """Where a page's Jekyll document is written. Jekyll skips names that begin with an
    underscore (_llseek, _sysctl), so the address comes from the permalink, not the file name."""
    folder, _, leaf = path.rstrip('/').rpartition('/')
    if leaf == 'call':
        return path + 'index.html'
    return '{}/{}{}.html'.format(folder, 'sys_' if folder.endswith('call') else '', leaf)


class Writer:
    def __init__(self, data, notes, output, introductions=None):
        self.data, self.notes, self.output = data, notes, output
        self.introductions = introductions or {}
        self.latest = data['latest']
        self.release = self.latest[1:]
        self.labels = {arch['id']: arch.get('label', arch['id']) for arch in data['manifest']['architectures']}
        self.count = 0
        self.bytes = 0

    def format_introduced(self, name, lang):
        intro = self.introductions.get(name)
        if not intro or not intro.get('version'):
            return None
        version = intro['version']
        note = intro.get('note_tr' if lang == 'tr' else 'note')
        if version == '1.0':
            label = TEXT[lang]['version_1_0_or_earlier']
        else:
            label = f'Linux {version}'
        if note:
            return f'{label} ({note})'
        return label

    # --- helpers -------------------------------------------------------
    def convention(self, arch):
        return self.data['tables'][self.latest, arch].get('calling_convention') or next(a for a in self.data['architectures'] if a['id'] == arch)

    def locations(self, arch, lang):
        c = self.convention(arch)
        return list(c.get('registers', [])) + ['{} ({})'.format(TEXT[lang]['stack'], slot) for slot in c.get('stack_slots', [])]

    def source_url(self, root, version, source):
        """Same rule as the application: bundled inputs when the snapshot has them, else the upstream tag."""
        provenance = next(table for (v, _), table in self.data['tables'].items() if v == version).get('provenance', {})
        if provenance.get('archive') or provenance.get('kind') == 'local':
            return root + 'data/{}/sources/{}'.format(version, source['path'])
        return 'https://github.com/torvalds/linux/blob/{}/{}#L{}'.format(quote(version, safe=''), source['path'], source.get('line', 1))

    def source_link(self, root, source, short=False):
        if not source or not source.get('path'):
            return ''
        text = (source['path'].rsplit('/', 1)[-1] if short else source['path']) + (':{}'.format(source['line']) if source.get('line') else '')
        return '<a href="{}">{}</a>'.format(escape(self.source_url(root, self.latest, source)), escape(text))

    def interactive(self, root, lang, arch, row=None, version=None):
        kernel = version or self.latest
        query = 'arch={}&kernel={}'.format(quote(arch, safe=''), quote(kernel, safe=''))
        home = root + ('tr/' if lang == 'tr' else '')
        if row is None:
            return home + '?' + query + '#reference'
        if not defined(row):
            query += '&all=1'
        return home + '?' + query + '#sys-' + quote('{}:{}:{}'.format(kernel, row['number'], row['name']), safe='')

    def write(self, lang, path, title, description, crumbs, body):
        """One Jekyll document. JSON strings are valid YAML; Liquid is off for the generated body."""
        other = 'en' if lang == 'tr' else 'tr'
        relative = path[len('tr/'):] if lang == 'tr' else path
        urls = {'en': '/' + relative, 'tr': '/tr/' + relative}
        t = TEXT[lang]
        depth = path.count('/')
        root = '../' * depth
        home = root + ('tr/' if lang == 'tr' else '')
        trail = ''.join(
            '<li><a href="{}">{}</a></li>'.format(escape(home + target), escape(name))
            for name, target in crumbs[:-1]
        ) + '<li aria-current="page">{}</li>'.format(escape(crumbs[-1][0]))
        front = {
            'layout': 'default', 'permalink': '/' + path, 'title': title, 'description': description, 'lang': lang,
            'static_page': True, 'sitemap': True, 'render_with_liquid': False,
            'alternates': [{'lang': code, 'url': urls[code]} for code in LANGUAGES],
            'breadcrumbs': [{'name': name, 'url': ('/tr/' if lang == 'tr' else '/') + target} for name, target in crumbs],
        }
        # data-translation-lang: console/i18n.js opens this link when the reader selects that language.
        text = '---\n' + ''.join('{}: {}\n'.format(key, json.dumps(value, ensure_ascii=False)) for key, value in front.items()) + '---\n' + \
            '<!-- SPDX-License-Identifier: GPL-2.0-only -->\n<!-- Generated by scripts/static_pages.py from public/data/; do not edit. -->\n' + \
            '<article class="static-page">\n' + \
            '<div class="static-top"><nav class="static-crumbs" aria-label="{}"><ol>{}</ol></nav>'.format(escape(t['breadcrumb']), trail) + \
            '<a class="static-language" data-translation-lang="{}" href="{}" hreflang="{}" lang="{}">{}</a></div>\n'.format(
                other, escape(root + urls[other][1:]), other, other, escape(t['other_language'])) + \
            body + self.sections(home, lang) + '</article>\n'
        target = self.output / source_file(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = text.encode()
        target.write_bytes(encoded)
        self.count += 1
        self.bytes += len(encoded)

    def sections(self, home, lang):
        t = TEXT[lang]
        return '<nav class="reference-links static-sections" aria-label="{}">'.format(escape(t['sections'])) + ''.join(
            '<a href="{}">{}</a>'.format(escape(href), escape(label)) for href, label in [
                (home + '#architectures', t['tables']), (home + 'call/', t['index_crumb']),
                (home + 'errno/', t['errno']), (home + 'signals/', t['signals']), (home + 'ioctl/', t['ioctl']),
            ]) + '</nav>\n'

    def arguments(self, row, lang):
        if not defined(row):
            return '<span class="muted">—</span>'
        if row.get('arguments') is None:
            return '<span class="muted">{}</span>'.format(escape(TEXT[lang]['unresolved']))
        return '<code>{}</code>'.format(escape(', '.join(row['arguments']) or 'void'))

    # --- ABI pages -----------------------------------------------------
    def abi_page(self, lang, arch):
        t = TEXT[lang]
        arch_id, label = arch['id'], self.labels[arch['id']]
        path = ('tr/' if lang == 'tr' else '') + 'arch/{}/'.format(arch_id)
        root = '../' * path.count('/')
        home = root + ('tr/' if lang == 'tr' else '')
        table = self.data['tables'][self.latest, arch_id]
        rows = table.get('syscalls', [])
        c = self.convention(arch_id)
        implemented = sum(1 for row in rows if defined(row))
        reserved = len(rows) - implemented
        table_source = {'path': c['table']} if c.get('table') else None
        values = {'label': label, 'release': self.release, 'defined': implemented}
        lede = escape(t['abi_lede']).format(
            reserved=escape(t['abi_reserved'].format(count=reserved)) if reserved else '',
            table=self.source_link(root, table_source) or escape(t['kernel_table']), **{k: escape(str(v)) for k, v in values.items()})
        convention = [(t['instruction'], c.get('instruction')), (t['nr'], c.get('nr')), (t['result'], c.get('result')),
                      (t['arguments_locations'], ', '.join(self.locations(arch_id, lang))), (t['error_flag'], c.get('error_flag'))]
        body = ['<h1>{} <span class="normal static-release">Linux {}</span></h1>\n'.format(escape(t['abi_h1'].format(label=label)), escape(self.release))]
        body.append('<p class="abi-lede">{}</p>\n'.format(lede))
        body.append('<p class="static-cta"><a href="{}"><strong>{}</strong></a> <span class="small">{}</span></p>\n'.format(
            escape(self.interactive(root, lang, arch_id)), escape(t['interactive_abi'].format(label=label)), escape(t['interactive_help'])))
        body.append('<section aria-labelledby="convention-title"><h2 id="convention-title">{}</h2>\n<dl class="static-facts">{}</dl>\n'.format(
            escape(t['convention']), ''.join('<div><dt>{}</dt><dd><code>{}</code></dd></div>'.format(escape(name), escape(value)) for name, value in convention if value)))
        body.append('<p class="small">{} <a href="{}#conventions">{}</a>.{}</p></section>\n'.format(
            escape(t['raw']), escape(home), escape(t['convention_more']),
            ' {} <a href="https://man7.org/linux/man-pages/man2/syscall.2.html">syscall(2)</a>.'.format(escape(t['bits32'])) if c.get('bits') == 32 else ''))
        caption = t['table_caption'].format(label=label, release=self.release)
        body.append('<section aria-labelledby="table-heading"><h2 id="table-heading">{}</h2>\n'.format(escape(caption)))
        # Jump aids: a row filter that static-page.js reveals, and plain number-range links that work without a script.
        # The first row of each hundred carries the range's fragment.
        ranges = {}
        for row in rows:
            ranges.setdefault(row['number'] // 100 * 100, []).append(row['number'])
        body.append('<form class="static-filter" role="search" hidden data-count="{count}"><label for="static-filter">{label}<span class="console-sr-only">{more}</span><span aria-hidden="true">:</span></label>'
                    '<input id="static-filter" type="search" autocomplete="off" spellcheck="false" placeholder="{hint}" aria-describedby="static-filter-count">'
                    '<span id="static-filter-count" class="small" role="status"></span></form>\n'.format(
                        count=escape(t['filter_count']), label=escape(t['filter']), more=escape(t['filter_more']), hint=escape(t['filter_hint'])))
        body.append('<nav class="static-ranges" aria-label="{nav}"><span aria-hidden="true">{jump}:</span><div class="static-ranges-scroll"><ul>{links}</ul>'
                    '<a class="static-filter-link" href="#static-filter" hidden>{label}<span class="console-sr-only">{more}</span><span aria-hidden="true"> ↑</span></a></div></nav>\n'.format(
                        nav=escape(t['jump_nav']), jump=escape(t['jump']), label=escape(t['filter']), more=escape(t['filter_more']),
                        links=''.join('<li><a href="#n-{}">{}–{}</a></li>'.format(start, start, max(numbers)) for start, numbers in ranges.items())))
        body.append('<div class="table-scroll static-scroll" tabindex="0" role="region" aria-label="{}"><table class="abi-table static-table static-calls"><caption class="console-sr-only">{}</caption>'.format(escape(t['table_region']), escape(caption)))
        body.append('<thead><tr>' + ''.join('<th scope="col">{}</th>'.format(escape(t[key])) for key in ['no', 'hex', 'call', 'arguments', 'what']) + '</tr></thead>\n<tbody>\n')
        seen, range_rows = set(), set()
        for row in rows:
            name = row['name']
            start = row['number'] // 100 * 100
            range_id = '' if start in range_rows else ' id="n-{}"'.format(start)
            range_rows.add(start)
            note = self.notes.get(name, {}).get(lang) if defined(row) else None
            # The first row of a name carries the fragment that the syscall page links to.
            anchor = '' if name in seen else ' id="{}"'.format(escape(name))
            seen.add(name)
            badge = '' if defined(row) else ' <span class="badge unimplemented">{}</span>'.format(escape(t['unimplemented']))
            body.append('<tr{}><td class="abi-number">{}</td><td class="abi-number">0x{:x}</td><th scope="row"{}><a href="{}call/{}/"><code>{}</code></a>{}</th><td>{}</td><td>{}</td></tr>\n'.format(
                range_id, row['number'], row['number'], anchor, escape(home), escape(name), escape(name), badge,
                self.arguments(row, lang), escape(note) if note else '<span class="muted">—</span>'))
        body.append('</tbody></table></div>\n')
        body.append('<p class="small">{} <a href="{}data/{}/{}.json">{}</a></p></section>\n'.format(
            escape(t['availability']), escape(root), escape(self.latest), escape(arch_id), escape(t['json'])))
        body.append('<nav class="static-abis" aria-labelledby="other-abis"><h2 id="other-abis">{}</h2><ul class="architecture-links">{}</ul></nav>\n'.format(
            escape(t['other_abis']), ''.join('<li><a href="{}arch/{}/">{}</a></li>'.format(escape(home), escape(other['id']), escape(self.labels[other['id']]))
                                             for other in self.data['architectures'] if other['id'] != arch_id)))
        self.write(lang, path, t['abi_title'].format(**values),
                   t['abi_description'].format(table=c.get('table', 'the kernel table'), **values),
                   [(t['site'], ''), (t['index_crumb'], 'call/'), (label, 'arch/{}/'.format(arch_id))], ''.join(body))

    # --- syscall pages -------------------------------------------------
    def declarations(self, root, lang, name, rows):
        t = TEXT[lang]
        groups = {}
        for arch, row in rows:
            if not defined(row):
                continue
            source = row.get('signature_source') or {}
            key = (row.get('declaration'), source.get('path'), source.get('line'), source.get('kind'), None if row.get('declaration') else row.get('signature_status'))
            groups.setdefault(key, []).append((arch, row))
        if not groups:
            return '<p class="muted">{}</p>\n'.format(escape(t['no_declaration'].format(release=self.release)))
        parts = []
        for (declaration, path, line, kind, status), members in groups.items():
            abis = ', '.join(escape(self.labels[arch]) for arch, _ in members)
            if declaration:
                block = '<p class="static-declaration"><code>{}</code></p>'.format(escape(declaration))
            else:
                block = '<p class="muted">{}</p>'.format(escape(t.get('unresolved_' + str(status), t['unresolved_default'])))
            origin = ''
            if path:
                origin = ' · {} {}'.format(escape(t['definition_source'] if kind == 'syscall_macro' else t['declaration_source']), self.source_link(root, {'path': path, 'line': line}))
            selections = []
            for arch, row in members:
                selection = (row.get('signature_source') or {}).get('configuration')
                if selection:
                    selections.append('{}: {} <a href="{}">{}</a>'.format(
                        escape(self.labels[arch]),
                        ' '.join('<code>{}={}</code>'.format(escape(symbol), 'y' if enabled else 'n') for symbol, enabled in selection['symbols'].items()),
                        escape(self.source_url(root, self.latest, {'path': selection['path'], 'line': 1})), escape(selection['path'])))
            parts.append('<div class="static-declaration-group">{}<p class="small"><strong>{}</strong>{}</p>{}</div>\n'.format(
                block, abis, origin,
                '<p class="small">{} {}</p>'.format(escape(t['configuration']), ' · '.join(selections)) if selections else ''))
        return ''.join(parts) + '<p class="small">{}</p>\n'.format(escape(t['libc']))

    def release_rows(self, lang, name, root=None):
        if root is None:
            path = ('tr/' if lang == 'tr' else '') + 'call/{}/'.format(name)
            root = '../' * path.count('/')
        t = TEXT[lang]
        current = self.data['history'].get(name, {}).get(self.latest, {})
        out = []
        for version in self.data['manifest']['versions']:
            bundled = self.data['bundled'][version]
            present = self.data['history'].get(name, {}).get(version, {})
            if not present:
                cell = '<span class="muted">{}</span>'.format(escape(t['none']))
            else:
                items = []
                for arch in bundled:
                    if arch in present:
                        numbers = present[arch]
                        row = {'number': numbers[0], 'name': name}
                        href = self.interactive(root, lang, arch, row, version=version)
                        suffix = '' if numbers == current.get(arch) else ' <code>{}</code>'.format(', '.join(str(number) for number in numbers))
                        items.append('<a href="{}">{}{}</a>'.format(escape(href), escape(self.labels[arch]), suffix))
                cell = ' · '.join(items)
            out.append('<tr><th scope="row">Linux {}</th><td class="abi-number">{}</td><td>{}</td></tr>\n'.format(escape(version[1:]), len(bundled), cell))
        return ''.join(out)

    def call_page(self, lang, name):
        t = TEXT[lang]
        path = ('tr/' if lang == 'tr' else '') + 'call/{}/'.format(name)
        root = '../' * path.count('/')
        home = root + ('tr/' if lang == 'tr' else '')
        architectures = [arch['id'] for arch in self.data['architectures']]
        current = self.data['current'].get(name, {})
        rows = [(arch, row) for arch in architectures for row in current.get(arch, [])]
        implemented = [arch for arch in architectures if any(defined(row) for row in current.get(arch, []))]
        reserved = [arch for arch in architectures if current.get(arch) and arch not in implemented]
        missing = [arch for arch in architectures if not current.get(arch)]
        note = self.notes.get(name, {}).get(lang) if implemented else None
        intro_text = self.format_introduced(name, lang)
        values = {'name': name, 'release': self.release, 'total': len(architectures), 'count': len(implemented)}
        names = lambda ids: ', '.join(self.labels[arch] for arch in ids)
        summary = [t['summary'].format(**{**values, 'name': '\0'})]
        if missing:
            summary.append(t['summary_missing'].format(list=names(missing)))
        if reserved:
            summary.append(t['summary_reserved'].format(list=names(reserved)))
        if intro_text:
            summary.append(t['introduced_summary'].format(version=intro_text))
        if implemented:
            title = t['call_title'].format(**values)
            pairs = ['{} {}'.format(self.labels[arch], next(row['number'] for row in current[arch] if defined(row))) for arch in implemented]
            shown = 6
            description = ' '.join(part for part in [
                '{}: {}'.format(name, note) if note else None,
                t['call_description_numbers'].format(release=self.release, pairs=', '.join(pairs[:shown]),
                                                     more=t['call_description_more'].format(count=len(pairs) - shown) if len(pairs) > shown else ''),
                t['call_description_tail'],
            ] if part)
        else:
            title = t['call_title_reserved' if reserved else 'call_title_earlier'].format(**values)
            description = t['call_description_absent'].format(**values)
        body = ['<h1><code>{}</code> <span class="normal static-release">{}</span></h1>\n'.format(escape(name), escape(t['call_kind']))]
        if note:
            body.append('<p class="abi-lede static-note">{}</p>\n'.format(escape(note)))
        body.append('<p>{}</p>\n'.format(escape(' '.join(summary)).replace('\0', '<code>{}</code>'.format(escape(name)))))

        caption = t['numbers_caption'].format(**values)
        body.append('<section aria-labelledby="numbers-title"><h2 id="numbers-title">{} <span class="normal static-release">Linux {}</span></h2>\n'.format(escape(t['numbers']), escape(self.release)))
        body.append('<div class="table-scroll static-scroll" tabindex="0" role="region" aria-label="{}"><table class="abi-table static-table static-numbers"><caption class="console-sr-only">{}</caption>'.format(escape(caption), escape(caption)))
        body.append('<thead><tr><th scope="col">ABI</th>' + ''.join('<th scope="col">{}</th>'.format(escape(t[key])) for key in ['no', 'hex', 'entry', 'instruction', 'nr_short', 'locations', 'kernel_table', 'interactive']) + '</tr></thead>\n<tbody>\n')
        for arch in architectures:
            label = self.labels[arch]
            head = '<th scope="row"><a href="{}arch/{}/{}">{}</a></th>'.format(escape(home), escape(arch), '#' + escape(name) if current.get(arch) else '', escape(label))
            if not current.get(arch):
                body.append('<tr class="static-absent">{}<td colspan="8" class="muted">{}</td></tr>\n'.format(head, escape(t['missing'].format(release=self.release))))
                continue
            c = self.convention(arch)
            for row in current[arch]:
                if defined(row):
                    entry = '<code>{}</code>'.format(escape(row.get('entry') or '—'))
                    for key, prefix in [('compat_entry', t['compat']), ('oabi_entry', 'OABI:')]:
                        if row.get(key):
                            entry += ' <span class="small">{} <code>{}</code></span>'.format(escape(prefix), escape(row[key]))
                    if row.get('noreturn'):
                        entry += ' <span class="small">{}</span>'.format(escape(t['noreturn']))
                    fallback = row.get('enosys_fallback')
                    # Only where the importer checked every definition site and found none for this ABI.
                    if fallback and 'implementation' in fallback and fallback['implementation'] is None:
                        entry += ' <span class="small">{}</span>'.format(escape(t['enosys']))
                else:
                    entry = '<span class="muted">{}</span>'.format(escape(t['reserved']))
                body.append('<tr>{}<td class="abi-number">{}</td><td class="abi-number">0x{:x}</td><td>{}</td><td><code>{}</code></td><td><code>{}</code></td><td><code>{}</code></td><td class="abi-source">{}</td><td><a href="{}" aria-label="{}">{}</a></td></tr>\n'.format(
                    head, row['number'], row['number'], entry, escape(c.get('instruction', '')), escape(c.get('nr', '')),
                    escape(', '.join(self.locations(arch, lang))), self.source_link(root, row.get('source'), short=True),
                    escape(self.interactive(root, lang, arch, row)), escape(t['open_label'].format(name=name, label=label)), escape(t['open'])))
        body.append('</tbody></table></div>\n')
        body.append('<p class="small">{} {} <a href="https://man7.org/linux/man-pages/man2/syscall.2.html">syscall(2)</a>. {}</p></section>\n'.format(
            escape(t['locations_note']), escape(t['bits32']), escape(t['availability'])))

        body.append('<section aria-labelledby="declaration-title"><h2 id="declaration-title">{}</h2>\n{}</section>\n'.format(
            escape(t['declaration']), self.declarations(root, lang, name, rows)))

        manuals = []
        for _, row in rows:
            if row.get('man_url') and row['man_url'] not in manuals:
                manuals.append(row['man_url'])
        links = []
        for url in manuals:
            match = re.search(r'/([^/]+)\.(\d[a-z]*)\.html$', url)
            links.append('<a href="{}">{}</a>'.format(escape(url), escape('{}({})'.format(*match.groups()) if match else url)))
        body.append('<section aria-labelledby="manual-title"><h2 id="manual-title">{}</h2>\n<p>{}</p></section>\n'.format(
            escape(t['manual']), ' · '.join(links) if links else '<span class="muted">{}</span>'.format(escape(t['no_manual']))))

        caption = t['releases_caption'].format(**values)
        body.append('<section aria-labelledby="releases-title"><h2 id="releases-title">{}</h2>\n'.format(escape(t['releases'])))
        if intro_text:
            body.append('<p class="static-introduced"><strong>{}</strong> {}</p>\n'.format(escape(t['first_appeared']), escape(intro_text)))
        body.append('<div class="table-scroll static-scroll" tabindex="0" role="region" aria-label="{}"><table class="abi-table static-table static-releases"><caption class="console-sr-only">{}</caption>'.format(escape(caption), escape(caption)))
        body.append('<thead><tr>' + ''.join('<th scope="col">{}</th>'.format(escape(t[key])) for key in ['release', 'bundled', 'defined_on']) + '</tr></thead>\n<tbody>\n')
        body.append(self.release_rows(lang, name, root=root))
        note_template = t['releases_note_introduced'] if intro_text else t['releases_note']
        body.append('</tbody></table></div>\n<p class="small">{}</p></section>\n'.format(escape(note_template.format(release=self.release))))
        self.write(lang, path, title, description, [(t['site'], ''), (t['index_crumb'], 'call/'), (name, 'call/{}/'.format(name))], ''.join(body))

    # --- index ---------------------------------------------------------
    def index_page(self, lang):
        t = TEXT[lang]
        path = ('tr/' if lang == 'tr' else '') + 'call/'
        root = '../' * path.count('/')
        home = root + ('tr/' if lang == 'tr' else '')
        architectures = self.data['architectures']
        implemented = [name for name in self.data['names'] if any(defined(row) for rows in self.data['current'].get(name, {}).values() for row in rows)]
        leftovers = [name for name in self.data['names'] if name not in set(implemented)]
        values = {'count': len(implemented), 'abis': len(architectures), 'release': self.release,
                  'labels': ', '.join(self.labels[arch['id']] for arch in architectures)}
        link = lambda name: '<li><a href="{}call/{}/"><code>{}</code></a></li>'.format(escape(home), escape(name), escape(name))
        body = ['<h1>{} <span class="normal static-release">Linux {}</span></h1>\n'.format(escape(t['index_h1']), escape(self.release))]
        body.append('<p class="abi-lede">{}</p>\n'.format(escape(t['index_lede'].format(**values))))
        body.append('<section aria-labelledby="by-abi"><h2 id="by-abi">{}</h2>\n<ul class="architecture-links static-abi-list">{}</ul></section>\n'.format(
            escape(t['by_abi']), ''.join('<li><a href="{}arch/{}/"><span>{}</span> <span class="small">{}</span></a></li>'.format(
                escape(home), escape(arch['id']), escape(self.labels[arch['id']]),
                escape(t['calls_count'].format(count=sum(1 for row in self.data['tables'][self.latest, arch['id']].get('syscalls', []) if defined(row)))))
                for arch in architectures)))
        groups = {}
        for name in implemented:
            groups.setdefault(name[0].upper(), []).append(name)
        letters = sorted(groups, key=lambda letter: (letter == '_', letter))
        fragment = lambda letter: 'letter-' + ('underscore' if letter == '_' else letter.lower())
        body.append('<section aria-labelledby="by-name"><h2 id="by-name">{} <span class="normal static-release">{}</span></h2>\n'.format(escape(t['by_name']), len(implemented)))
        body.append('<nav class="static-letters" aria-label="{}">{}</nav>\n'.format(
            escape(t['letters']), ''.join('<a href="#{}">{}</a>'.format(fragment(letter), escape(letter)) for letter in letters)))
        for letter in letters:
            body.append('<h3 id="{}">{}</h3>\n<ul class="static-names">{}</ul>\n'.format(fragment(letter), escape(letter), ''.join(link(name) for name in groups[letter])))
        body.append('</section>\n')
        if leftovers:
            body.append('<section aria-labelledby="leftovers"><h2 id="leftovers">{}</h2>\n<p class="small">{}</p>\n<ul class="static-names">{}</ul></section>\n'.format(
                escape(t['leftovers']), escape(t['leftovers_note'].format(release=self.release)), ''.join(link(name) for name in leftovers)))
        self.write(lang, path, t['index_title'].format(**values), t['index_description'].format(**values),
                   [(t['site'], ''), (t['index_crumb'], 'call/')], ''.join(body))


def load_introductions(root=None):
    candidates = []
    if root is not None:
        candidates.append(Path(root) / 'sources/introductions.json')
    candidates.append(Path(__file__).resolve().parents[1] / 'sources/introductions.json')
    for path in candidates:
        if path.is_file():
            data = json.loads(path.read_bytes())
            return data.get('introductions', data)
    return {}


def generate(public, notes, output=None, introductions=None):
    """Write every page under output (default: public) and return what was written."""
    public = Path(public)
    output = Path(output) if output else public
    data = load(public)
    if introductions is None:
        introductions = load_introductions(public.parent)
    for folder in OUTPUT_DIRS:
        shutil.rmtree(output / folder, ignore_errors=True)
    writer = Writer(data, notes, output, introductions)
    for lang in LANGUAGES:
        writer.index_page(lang)
        for arch in data['architectures']:
            writer.abi_page(lang, arch)
        for name in data['names']:
            writer.call_page(lang, name)
    paths = page_paths(data)
    assert writer.count == sum(len(listed) for listed in paths.values())
    return {'pages': writer.count, 'bytes': writer.bytes, 'paths': paths,
            'architectures': len(data['architectures']), 'names': len(data['names'])}


if __name__ == '__main__':
    import importlib.util
    spec = importlib.util.spec_from_file_location('prepare_site', Path(__file__).resolve().parent / 'prepare_site.py')
    prepare_site = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare_site)
    result = generate(prepare_site.PUBLIC, prepare_site.editorial_notes())
    print('Generated {} static pages ({} ABIs, {} syscall names, {} languages, {:.1f} MB before the layout).'.format(
        result['pages'], result['architectures'], result['names'], len(LANGUAGES), result['bytes'] / 1e6))
