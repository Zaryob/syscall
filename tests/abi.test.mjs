// SPDX-License-Identifier: GPL-2.0-only
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import {
  abiURL, archTable, commandTexts, decodeIoctl, defaultAction, hex, ioctlFields, magicTexts, matchingCommands,
  matchingMagic, normalizeArch, parseNumber, parseRequest, readAbiRoute, searchRows, sourceURL, tableRows,
} from '../public/abi.mjs';
import { abiCopy } from '../public/abi-copy.mjs';

const file = path => new URL('../public/' + path, import.meta.url);
const json = async path => JSON.parse(await readFile(file(path), 'utf8'));
const manifest = await json('data/abi/manifest.json');
const site = await json('data/manifest.json');
const release = manifest.latest;
const [errno, signals, ioctl, registry, sources] = await Promise.all(
  ['errno', 'signals', 'ioctl', 'ioctl-numbers', 'sources'].map(name => json(`data/abi/${release}/${name}.json`)));

test('the ABI manifest covers the latest release and every architecture of the site', () => {
  assert.equal(release, site.latest);
  assert.deepEqual(manifest.architectures.map(a => a.id), site.version_architectures[release]);
  assert.deepEqual(manifest.architectures.map(a => a.label), site.architectures.map(a => a.label));
  for (const document of [errno, signals, ioctl]) assert.deepEqual(Object.keys(document.architectures), site.version_architectures[release]);
});

test('every bundled ABI input keeps its exact hash and a recorded GPL-2.0 licence', async () => {
  assert.equal(sources.license, 'GPL-2.0-only');
  for (const record of sources.files) {
    const bytes = await readFile(file(`data/abi/${release}/${record.bundled_path}`));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), record.sha256, record.path);
    const license = record.spdx_license_identifier || record.license_identifier;
    if (record.role !== 'license-notice') assert.ok(license && license.startsWith('GPL-2.0'), record.path);
  }
  for (const document of [errno, signals, ioctl, registry]) {
    assert.equal(document.license, 'GPL-2.0-only');
    assert.equal(document.licensing.generator, 'scripts/sync_abi.py');
    assert.deepEqual(document.provenance.files, sources.files);
    assert.equal(document.provenance.ref, release);
  }
  const unmarked = sources.files.filter(record => record.license_basis);
  assert.deepEqual(unmarked.map(record => record.path), ['Documentation/userspace-api/ioctl/ioctl-number.rst']);
});

test('rows are ordered by number, keep aliases after their target, and report other architectures', () => {
  const rows = tableRows(errno, 'x64');
  assert.deepEqual(rows.slice(0, 2).map(row => [row.number, row.name]), [[1, 'EPERM'], [2, 'ENOENT']]);
  const at = name => rows.findIndex(row => row.name === name);
  assert.ok(at('EAGAIN') < at('EWOULDBLOCK'));
  assert.equal(rows[at('EWOULDBLOCK')].alias_of, 'EAGAIN');
  assert.deepEqual(rows[at('ENOENT')].elsewhere, []);
  assert.deepEqual(rows[at('EDEADLK')].elsewhere, [{ number: 45, architectures: ['mips-o32', 'mips-n32', 'mips-n64'] }]);
  assert.deepEqual(rows[at('EDEADLOCK')].elsewhere, [{ number: 58, architectures: ['ppc64', 'ppc'] }, { number: 56, architectures: ['mips-o32', 'mips-n32', 'mips-n64'] }]);
  const mips = tableRows(signals, 'mips-n64');
  const emt = mips.find(row => row.name === 'SIGEMT');
  assert.equal(emt.number, 7);
  assert.deepEqual(emt.elsewhere, [{ number: null, architectures: Object.keys(signals.architectures).filter(arch => !arch.startsWith('mips')) }]);
  assert.equal(mips.find(row => row.name === 'SIGBUS').elsewhere[0].number, 7);
  assert.equal(archTable(signals, 'riscv64').header, 'include/uapi/asm-generic/signal.h');
  assert.equal(normalizeArch(errno, 'sparc'), 'x64');
  assert.equal(normalizeArch(errno, 's390x'), 's390x');
});

test('search matches names, kernel comments and exact decimal or hexadecimal numbers', () => {
  const rows = tableRows(errno, 'x64');
  assert.deepEqual(searchRows(rows, '0x2').map(row => row.name), ['ENOENT']);
  assert.deepEqual(searchRows(rows, '11').map(row => row.name), ['EAGAIN', 'EWOULDBLOCK']);
  assert.ok(searchRows(rows, 'no such file').some(row => row.name === 'ENOENT'));
  assert.deepEqual(searchRows(rows, ' enoent ').map(row => row.name), ['ENOENT']);
  assert.equal(searchRows(rows, '').length, rows.length);
  assert.equal(searchRows(rows, 'zzzz').length, 0);
  const commands = archTable(ioctl, 'x64', 'commands', 'commands').entries;
  assert.deepEqual(searchRows(commands, '0x5401', commandTexts, row => row.value).map(row => row.name), ['TCGETS']);
  assert.ok(searchRows(commands, 'termios2', commandTexts, row => row.value).some(row => row.name === 'TCGETS2'));
  assert.ok(searchRows(registry.rows, 'if_tun', magicTexts, row => row.value).length >= 1);
  assert.ok(searchRows(registry.rows, '0x54', magicTexts, row => row.value).every(row => row.value === 0x54));
});

test('default actions come from the kernel table, also for names defined as another signal', () => {
  const mips = archTable(signals, 'mips-o32').entries;
  const by = name => mips.find(entry => entry.name === name);
  assert.equal(defaultAction(signals, by('SIGKILL')).action, 'terminate');
  assert.deepEqual(defaultAction(signals, by('SIGSTOP')).markers, ['*', '+']);
  assert.equal(by('SIGCLD').alias_of, 'SIGCHLD');
  assert.equal(defaultAction(signals, by('SIGCLD')).action, 'ignore');
  assert.equal(defaultAction(signals, { name: 'SIGSWI' }), null);
  for (const action of new Set(Object.values(signals.default_actions.signals).map(record => record.action))) {
    assert.ok(signals.default_actions.definitions[action], action);
    for (const language of ['en', 'tr']) assert.ok(abiCopy(language).actions[action], action);
  }
});

test('request numbers decode with the layout of the selected architecture', () => {
  const generic = archTable(ioctl, 'x64', 'encoding', 'encodings');
  const powerpc = archTable(ioctl, 'ppc64', 'encoding', 'encodings');
  assert.deepEqual(ioctlFields(generic).map(f => [f.name, f.high, f.low]), [['dir', 31, 30], ['size', 29, 16], ['type', 15, 8], ['nr', 7, 0]]);
  assert.deepEqual(ioctlFields(powerpc).map(f => [f.name, f.high, f.low]), [['dir', 31, 29], ['size', 28, 16], ['type', 15, 8], ['nr', 7, 0]]);
  assert.deepEqual(decodeIoctl(0x80045430, generic), { value: 0x80045430, dir: { value: 2, names: ['read'] }, size: 4, type: { value: 0x54, character: 'T' }, nr: 0x30 });
  assert.deepEqual(decodeIoctl(0x40045430, powerpc).dir, { value: 2, names: ['read'] });
  assert.deepEqual(decodeIoctl(0x5401, generic).dir, { value: 0, names: ['none'] });
  assert.deepEqual(decodeIoctl(0x5401, powerpc).dir, { value: 0, names: [] });
  assert.deepEqual(decodeIoctl(0x20005441, powerpc).dir, { value: 1, names: ['none'] });
  assert.deepEqual(decodeIoctl(0xFFFFFFFF, generic), { value: 0xFFFFFFFF, dir: { value: 3, names: ['read', 'write'] }, size: 0x3FFF, type: { value: 0xFF, character: null }, nr: 0xFF });
  assert.deepEqual(decodeIoctl(0xC0000000, powerpc).dir, { value: 6, names: ['read', 'write'] });
  // Every command the headers fix decodes back to the fields the generator recorded.
  for (const arch of Object.keys(ioctl.architectures)) {
    const encoding = archTable(ioctl, arch, 'encoding', 'encodings');
    for (const entry of archTable(ioctl, arch, 'commands', 'commands').entries) {
      if (!entry.macro || entry.value === null) continue;
      const decoded = decodeIoctl(entry.value, encoding);
      assert.deepEqual([decoded.dir.value, decoded.type.value, decoded.nr, decoded.size], [entry.direction, entry.type.value, entry.nr, entry.size], `${arch} ${entry.name}`);
    }
  }
  assert.equal(parseRequest('0x5401'), 0x5401);
  assert.equal(parseRequest(' 21505 '), 0x5401);
  assert.equal(parseRequest('0xFFFFFFFF'), 0xFFFFFFFF);
  for (const invalid of ['0x100000000', '-1', 'TCGETS', '', '0x', '1e3']) assert.equal(parseRequest(invalid), null, invalid);
  assert.equal(parseNumber('0x100000000'), 0x100000000);
  assert.equal(hex(0x5401), '0x5401');
  assert.equal(hex(7, 2), '0x07');
});

test('a decoded request finds its command and the registered magic numbers', () => {
  const commands = archTable(ioctl, 'x64', 'commands', 'commands').entries;
  assert.deepEqual(matchingCommands(commands, 0x541B).map(row => row.name), ['FIONREAD', 'TIOCINQ', 'SIOCINQ']);
  assert.deepEqual(matchingCommands(commands, 0x80045430).map(row => row.name), ['TIOCGPTN']);
  assert.deepEqual(matchingCommands(commands, 1), []);
  assert.ok(!matchingCommands(commands, null).length || matchingCommands(commands, null).every(row => row.value === null));
  const tun = matchingMagic(registry.rows, 0x54, 0xCA).map(row => row.includes.join(' '));
  assert.ok(tun.includes('linux/if_tun.h'));
  assert.ok(!matchingMagic(registry.rows, 0x54, 0x30).some(row => row.includes.includes('linux/if_tun.h')));
  assert.ok(matchingMagic(registry.rows, 0x54, 0x30).every(row => row.code === "'T'"));
});

test('URL state round-trips, keeps the language and leaves the default address clean', () => {
  const address = 'https://example.org/syscall-test/ioctl/?lang=tr&arch=ppc64&q=TCGET&req=0x40147417&magic=tun#decoder';
  const state = readAbiRoute(address);
  assert.deepEqual(state, { arch: 'ppc64', query: 'TCGET', request: '0x40147417', magic: 'tun' });
  const url = new URL(abiURL(address, state), address);
  assert.deepEqual(readAbiRoute(url.href), state);
  assert.equal(url.searchParams.get('lang'), 'tr');
  assert.equal(url.pathname + url.hash, '/syscall-test/ioctl/#decoder');
  assert.equal(abiURL('https://example.org/syscall/errno/', readAbiRoute('https://example.org/syscall/errno/')), '/syscall/errno/');
  assert.equal(abiURL('https://example.org/errno/?arch=x64&q=a+b', readAbiRoute('https://example.org/errno/?arch=x64&q=a+b')), '/errno/?q=a+b');
  assert.equal(readAbiRoute('https://example.org/errno/?highlight=EIO').query, 'EIO');
});

test('source links point at the tagged upstream line, or the bundled file for a local import', () => {
  const source = { path: 'include/uapi/asm-generic/errno-base.h', line: 6 };
  assert.equal(sourceURL(errno, source, '/data/abi/x/'), `https://github.com/torvalds/linux/blob/${release}/include/uapi/asm-generic/errno-base.h#L6`);
  assert.equal(sourceURL({ ...errno, provenance: { kind: 'local' } }, source, '/data/abi/x/'), '/data/abi/x/sources/include/uapi/asm-generic/errno-base.h');
});

test('both languages define the same copy, and every UI key of the new pages is translated', async () => {
  const shape = value => typeof value === 'object' ? Object.keys(value).sort() : typeof value;
  const [en, tr] = [abiCopy('en'), abiCopy('tr')];
  assert.deepEqual(Object.keys(tr).sort(), Object.keys(en).sort());
  for (const key of Object.keys(en)) assert.deepEqual(shape(tr[key]), shape(en[key]), key);
  const dictionary = await readFile(file('assets/console/i18n.js'), 'utf8');
  const translated = new Set([...dictionary.matchAll(/^  "((?:[^"\\]|\\.)*)":/gm)].map(match => JSON.parse(`"${match[1]}"`)));
  const decode = text => text.replace(/&amp;/g, '&');
  const pages = ['errno/index.html', 'signals/index.html', 'ioctl/index.html',
    ...(await readdir(file('_includes'))).filter(name => name.startsWith('abi-')).map(name => `_includes/${name}`)];
  const used = new Set(['Find an error number', 'Find a signal', 'Find a command']);
  for (const page of pages) {
    const html = await readFile(file(page), 'utf8');
    for (const match of html.matchAll(/data-i18n(?:-aria-label|-placeholder)?="([^"{]+)"/g)) used.add(decode(match[1]));
    for (const match of html.matchAll(/data-abi-copy="([^"]+)"/g)) assert.ok(match[1] in en, `${page}: ${match[1]}`);
  }
  const script = await readFile(file('abi.js'), 'utf8');
  for (const match of script.matchAll(/\bt\('([^']+)'/g)) used.add(match[1]);
  assert.ok(used.size > 40);
  for (const key of used) assert.ok(translated.has(key), `Missing Turkish UI string: ${key}`);
  // The landing page leads to every section from both of its section navigations.
  const landing = await readFile(file('index.html'), 'utf8');
  for (const section of ['errno', 'signals', 'ioctl']) assert.equal(landing.split(`{{ '/${section}/' | relative_url }}`).length - 1, 2, section);
});
