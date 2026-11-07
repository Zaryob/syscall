// SPDX-License-Identifier: GPL-2.0-only
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { searchSyscalls, diffSyscalls, availableArchitectures } from '../public/catalog.mjs';
import { snapshotPath, withBase } from '../public/paths.mjs';
import { createApp } from '../server.mjs';

const manifest = JSON.parse(await readFile(new URL('../public/data/manifest.json', import.meta.url)));
const snapshotFile = (version, file) => new URL('../public/' + snapshotPath(manifest, version, file), import.meta.url);
const dataset = async (version, arch) => JSON.parse(await readFile(snapshotFile(version, arch + '.json'), 'utf8'));

test('all current MIPS n64 snapshots include the common 5450 call with source identity', async () => {
  for (const version of ['v5.19', 'v6.6', 'v6.12', 'v6.18', 'v7.3']) {
    const data = await dataset(version, 'mips-n64');
    const row = data.syscalls.find(row => row.number === 5450);
    assert.equal(row.name, 'set_mempolicy_home_node');
    assert.equal(row.abi, 'common');
    assert.equal(row.entry, 'sys_set_mempolicy_home_node');
    const source = await readFile(snapshotFile(version, `sources/${row.source.path}`), 'utf8');
    assert.match(source.split('\n')[row.source.line - 1], /450\s+common\s+set_mempolicy_home_node/);
  }
});

test('PowerPC plain prototypes resolve from their bundled architecture headers', async () => {
  for (const arch of ['ppc', 'ppc64']) {
    const data = await dataset('v7.3', arch);
    for (const name of ['mmap', 'rt_sigreturn', 'swapcontext', 'rtas', 'subpage_prot']) {
      const row = data.syscalls.find(row => row.name === name);
      assert.ok(Array.isArray(row.arguments), `${arch}/${name}`);
      assert.equal(row.signature_source.path, 'arch/powerpc/include/asm/syscalls.h');
      const source = await readFile(snapshotFile('v7.3', `sources/${row.signature_source.path}`), 'utf8');
      assert.ok(source.split('\n')[row.signature_source.line - 1].includes(row.entry));
    }
  }
});

test('every active manual link is a cataloged page, including time64 and section 3 aliases', async () => {
  const catalog = JSON.parse(await readFile(new URL('../sources/manual-pages.json', import.meta.url)));
  for (const version of manifest.versions) {
    for (const arch of availableArchitectures(manifest, version)) {
      for (const row of (await dataset(version, arch)).syscalls) {
        if (row.man_url === null) continue;
        const url = new URL(row.man_url);
        assert.equal(url.origin, 'https://man7.org');
        const match = url.pathname.match(/^\/linux\/man-pages\/man([23])\/([^/]+)\.\1\.html$/);
        assert.ok(match, row.man_url);
        assert.ok(catalog.sections[match[1]].includes(match[2]), row.man_url);
      }
    }
  }
  const x86 = await dataset('v7.3', 'x86');
  assert.match(x86.syscalls.find(row => row.name === 'clock_gettime64').man_url, /clock_gettime\.2\.html$/);
  assert.equal(x86.syscalls.find(row => row.status === 'unimplemented').man_url, null);
});

test('search finds exact decimal/hex numbers and matches declaration text', () => {
  const rows = [
    { number: 0, name: 'read', entry: 'sys_read', arguments: ['unsigned int fd', 'char *buf'] },
    { number: 59, name: 'execve', entry: 'sys_execve', arguments: ['const char *filename'] },
    { number: 159, name: 'adjtimex', entry: 'sys_adjtimex', arguments: null },
  ];
  assert.deepEqual(searchSyscalls(rows, '0'), [rows[0]]);
  assert.deepEqual(searchSyscalls(rows, '0X3B'), [rows[1]]);
  assert.deepEqual(searchSyscalls(rows, '59'), [rows[1]]);
  assert.deepEqual(searchSyscalls(rows, ' FileName '), [rows[1]]);
  assert.deepEqual(searchSyscalls(rows, 'sys_read'), [rows[0]]);
  assert.deepEqual(searchSyscalls(rows, 'nosuchcall'), []);
});

test('diff detects number reuse, removed entries, and ABI signature changes', () => {
  const old = [{ number: 1, name: 'old', arguments: [] }, { number: 2, name: 'stable', arguments: ['int x'] }];
  const next = [{ number: 1, name: 'new', arguments: [] }, { number: 2, name: 'stable', arguments: ['long x'] }];
  const diff = diffSyscalls(old, next);
  assert.deepEqual(diff.added, [next[0]]);
  assert.deepEqual(diff.removed, [old[0]]);
  assert.deepEqual(diff.changed, [{ before: old[1], after: next[1], reasons: ['argument_types'] }]);
  assert.deepEqual(diffSyscalls(next, next), { added: [], removed: [], changed: [] });
  const before = { ...next[1], declaration: 'asmlinkage int sys_stable(long x);' };
  const after = { ...next[1], declaration: 'asmlinkage long sys_stable(long x);' };
  assert.deepEqual(diffSyscalls([before], [after]).changed, [{ before, after, reasons: ['declaration'] }]);
  assert.deepEqual(diffSyscalls([next[1]], [after]).changed, []);
});

test('diff distinguishes parameter names, implementation changes and table flags', async () => {
  const old = await dataset('v4.15', 'x86');
  const next = await dataset('v5.19', 'x86');
  const { reasons } = diffSyscalls(old.syscalls, next.syscalls).changed.find(change => change.after.name === 'sigpending');
  assert.deepEqual(reasons, ['argument_names']);
  const slot = { name: 'readdir', number: 89, status: 'unimplemented', arguments: null };
  assert.deepEqual(diffSyscalls([{ ...slot, entry: '-' }], [{ ...slot, entry: 'sys_ni_syscall' }]).changed, []);
  const call = { name: 'example', number: 1, entry: 'sys_example', status: 'defined', arguments: ['int fd'] };
  const updated = { ...call, compat_entry: 'compat_sys_example', noreturn: true, arguments: ['int fd', 'int count'] };
  assert.deepEqual(diffSyscalls([call], [updated]).changed[0].reasons, ['compat_entry', 'noreturn', 'argument_count']);
});

test('published snapshots retain availability, table flags, and reviewed mmap sources', async () => {
  for (const version of ['v5.19', 'v6.6', 'v6.12', 'v6.18', 'v7.3']) {
    const s390x = await dataset(version, 's390x');
    assert.equal(s390x.syscalls.find(row => row.name === 'readdir').status, 'unimplemented');
    assert.ok(s390x.syscalls.every(row => row.status !== 'defined' || row.entry !== '-'));
    const x64 = await dataset(version, 'x64');
    const mmap = x64.syscalls.find(row => row.name === 'mmap');
    assert.equal(mmap.arguments.length, 6);
    assert.equal(mmap.signature_source.kind, 'syscall_macro');
    const source = await readFile(snapshotFile(version, 'sources/' + mmap.signature_source.path), 'utf8');
    assert.match(source.split('\n')[mmap.signature_source.line - 1], /^SYSCALL_DEFINE6\(mmap,/);
  }
  const x86 = await dataset('v7.3', 'x86');
  assert.equal(x86.syscalls.find(row => row.name === 'open').compat_entry, 'compat_sys_open');
  assert.equal(x86.syscalls.find(row => row.name === 'exit').noreturn, true);
  const historical = await dataset('v1.0', 'x86');
  const table = await readFile(snapshotFile('v1.0', 'sources/kernel/sched.c'), 'utf8');
  for (const [name, symbol] of [['read', 'sys_read'], ['write', 'sys_write'], ['bdflush', 'sys_bdflush']]) {
    const row = historical.syscalls.find(row => row.name === name);
    assert.match(table.split('\n')[row.source.line - 1], new RegExp(`\\b${symbol}\\b`));
  }
});

test('purpose search matches original English and Turkish summaries', () => {
  const rows = ['splice', 'futex', 'io_uring_enter'].map(name => ({ name, status: 'defined' }));
  assert.deepEqual(searchSyscalls(rows, 'wait for completions'), [rows[2]]);
  assert.deepEqual(searchSyscalls(rows, 'is PARCACIGINI UYUTUR'), [rows[1]]);
  assert.deepEqual(searchSyscalls([{ ...rows[0], status: 'unimplemented' }], 'userspace'), []);
});

test('all shipped snapshots have unique numbers, provenance, and known architecture-specific read numbers', async () => {
  const readNumbers = {
    x64: 0, x86: 3, arm64: 63, arm: 3, riscv64: 63, loongarch64: 63,
    ppc64: 3, ppc: 3, s390x: 3, 'mips-o32': 4003, 'mips-n32': 6000, 'mips-n64': 5000,
  };
  for (const version of manifest.versions) {
    for (const archId of availableArchitectures(manifest, version)) {
      const data = await dataset(version, archId);
      assert.equal(data.kernel, version);
      assert.equal(new Set(data.syscalls.map(r => r.number)).size, data.syscalls.length);
      const read = data.syscalls.find(r => r.name === 'read');
      assert.equal(read.number, readNumbers[archId]);
      if (read.arguments !== null) {
        assert.equal(read.arguments.length, 3);
      }
      const getpid = data.syscalls.find(r => r.name === 'getpid');
      if (getpid && getpid.arguments !== null) {
        assert.equal(getpid.arguments.length, 0);
      }
      assert.ok(data.provenance.files.every(f => /^[a-f\d]{64}$/.test(f.sha256)));
      assert.equal(data.license, 'GPL-2.0-only');
      for (const row of data.syscalls) {
        assert.ok(row.arguments === null || row.arguments.length <= 6);
        assert.ok(row.source.line > 0);
        if (row.status === 'unimplemented') assert.equal(row.arguments, null);
        if (row.arguments === null) assert.equal(row.declaration, null);
        else assert.match(row.declaration, new RegExp(`\\b${row.entry}\\s*\\(`));
      }
    }
  }
});

test('every bundled kernel input retains its exact hash, notices, and source license', async () => {
  for (const version of manifest.versions) {
    const sources = JSON.parse(await readFile(snapshotFile(version, 'sources.json')));
    assert.equal(sources.license, 'GPL-2.0-only');
    for (const file of sources.files) {
      const bytes = await readFile(snapshotFile(version, file.bundled_path));
      assert.equal(createHash('sha256').update(bytes).digest('hex'), file.sha256, file.path);
      const license = file.spdx_license_identifier || file.license_identifier;
      if (file.role !== 'license-notice') assert.ok(license && license.startsWith('GPL-2.0'), file.path);
    }
    const hasSyscallsH = sources.files.some(f => f.path === 'include/linux/syscalls.h' && f.spdx_license_identifier);
    if (hasSyscallsH) {
      const header = await readFile(snapshotFile(version, 'sources/include/linux/syscalls.h'), 'utf8');
      assert.match(header, /Copyright \(c\) 2004 Randy Dunlap/);
      assert.match(header, /SPDX-License-Identifier: GPL-2.0-only/);
    }
    const hasNote = sources.files.some(f => f.path === 'LICENSES/exceptions/Linux-syscall-note');
    if (hasNote) {
      const note = await readFile(snapshotFile(version, 'sources/LICENSES/exceptions/Linux-syscall-note'), 'utf8');
      assert.match(note, /SPDX-Exception-Identifier: Linux-syscall-note/);
    }
  }
});

test('site paths keep assets, searches and downloads under the Jekyll baseurl', () => {
  for (const base of ['/', '/syscall/', '/nested/syscall/']) {
    assert.equal(withBase(base, '/data/v7.3/x64.json'), base + 'data/v7.3/x64.json');
    assert.equal(withBase(base, ''), base);
  }
  assert.equal(withBase('/syscall', 'api/v1/index.json'), '/syscall/api/v1/index.json');
  assert.equal(snapshotPath({}, 'v6.12', 'x64.json'), 'data/v6.12/x64.json');
  assert.equal(snapshotPath({ version_paths: { 'v6.12': 'revisions/v6.12/abc' } }, 'v6.12', 'x64.json'), 'data/revisions/v6.12/abc/x64.json');
});

test('optional HTTP API serves snapshots, exact lookups, search, diff, and errors', async t => {
  const server = createApp();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const base = `http://127.0.0.1:${server.address().port}`;
  const get = route => fetch(base + route);
  for (const route of ['/catalog.mjs', '/data/manifest.json', '/licenses/GPL-2.0-only.txt', '/licenses/Linux-syscall-note.txt', '/data/v7.3/sources.json', '/data/v7.3/sources/include/linux/syscalls.h']) {
    const response = await get(route);
    assert.equal(response.status, 200, route);
    assert.ok((await response.text()).length > 100);
  }
  const read = await (await get('/api/v1/syscalls/arm64/read?version=v6.12')).json();
  assert.equal(read.number, 63);
  assert.equal(read.kernel, 'v6.12');
  assert.equal(read.license, 'GPL-2.0-only');
  assert.ok(read.provenance.files.length > 0);
  const hex = await (await get('/api/v1/syscalls/x64/0x3b')).json();
  assert.equal(hex.name, 'execve');
  for (const key of ['0X003B', '059']) {
    assert.equal((await (await get(`/api/v1/syscalls/x64/${key}`)).json()).name, 'execve');
    assert.equal((await (await get(`/api/v1/syscalls/x64?q=${key}`)).json()).syscalls[0].name, 'execve');
  }
  const index = await (await get('/api/v1')).json();
  const docs = await get(index.documentation);
  assert.equal(docs.status, 200);
  assert.ok((await docs.json()).endpoints.some(({ path }) => path.endsWith('/diff')));
  const notes = await get('/notes.mjs');
  assert.equal(notes.status, 200);
  const asModule = text => 'data:text/javascript;base64,' + Buffer.from(text).toString('base64');
  const catalog = (await (await get('/catalog.mjs')).text()).replace('./notes.mjs', asModule(await notes.text()));
  assert.equal(typeof (await import(asModule(catalog))).searchSyscalls, 'function');
  for (const [version, name, number] of [['v2.6.12', 'keyctl', 250], ['v2.6.16', 'unshare', 272]]) {
    const row = await (await get(`/api/v1/syscalls/x64/${name}?version=${version}`)).json();
    assert.equal(row.number, number);
    assert.equal((await (await get(`/api/v1/syscalls/x64/${number}?version=${version}`)).json()).name, name);
  }
  const search = await (await get('/api/v1/syscalls/x64?q=59')).json();
  assert.deepEqual(search.syscalls.map(r => r.name), ['execve']);
  const diff = await (await get('/api/v1/syscalls/x64/diff?from=v6.12&version=v7.3')).json();
  assert.ok(diff.added.length > 0);
  assert.equal(diff.to, 'v7.3');
  assert.equal((await get('/api/v1/syscalls/x64/diff')).status, 400);
  assert.equal((await get('/api/v1/syscalls/unknown')).status, 404);
  assert.equal((await get('/api/v1/syscalls/x64?version=nonexistent')).status, 404);
  assert.equal((await get('/api/v1/syscalls/x64/not-a-syscall')).status, 404);
  assert.equal((await get('/%ZZ')).status, 400);
  assert.equal((await get('/data/..%2f..%2fpackage.json')).status, 403);
  assert.equal((await fetch(base + '/', { method: 'POST' })).status, 405);
  const head = await fetch(base + '/data/manifest.json', { method: 'HEAD' });
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
});
