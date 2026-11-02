// SPDX-License-Identifier: GPL-2.0-only
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { searchSyscalls, diffSyscalls, availableArchitectures } from '../public/catalog.mjs';
import { withBase } from '../public/paths.mjs';
import { createApp } from '../server.mjs';

const dataset = async (version, arch) => JSON.parse(await readFile(new URL(`../public/data/${version}/${arch}.json`, import.meta.url), 'utf8'));

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
  assert.deepEqual(diff.changed, [{ before: old[1], after: next[1] }]);
  assert.deepEqual(diffSyscalls(next, next), { added: [], removed: [], changed: [] });
});

test('all shipped snapshots have unique numbers, provenance, and known architecture-specific read numbers', async () => {
  const manifest = JSON.parse(await readFile(new URL('../public/data/manifest.json', import.meta.url)));
  const readNumbers = { x64: 0, x86: 3, arm64: 63, arm: 3, riscv64: 63, loongarch64: 63 };
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
      }
    }
  }
});

test('every bundled kernel input retains its exact hash, notices, and source license', async () => {
  const manifest = JSON.parse(await readFile(new URL('../public/data/manifest.json', import.meta.url)));
  for (const version of manifest.versions) {
    const sources = JSON.parse(await readFile(new URL(`../public/data/${version}/sources.json`, import.meta.url)));
    assert.equal(sources.license, 'GPL-2.0-only');
    for (const file of sources.files) {
      const bytes = await readFile(new URL(`../public/data/${version}/${file.bundled_path}`, import.meta.url));
      assert.equal(createHash('sha256').update(bytes).digest('hex'), file.sha256, file.path);
      const license = file.spdx_license_identifier || file.license_identifier;
      if (file.role !== 'license-notice') assert.ok(license && license.startsWith('GPL-2.0'), file.path);
    }
    const hasSyscallsH = sources.files.some(f => f.path === 'include/linux/syscalls.h' && f.spdx_license_identifier);
    if (hasSyscallsH) {
      const header = await readFile(new URL(`../public/data/${version}/sources/include/linux/syscalls.h`, import.meta.url), 'utf8');
      assert.match(header, /Copyright \(c\) 2004 Randy Dunlap/);
      assert.match(header, /SPDX-License-Identifier: GPL-2.0-only/);
    }
    const hasNote = sources.files.some(f => f.path === 'LICENSES/exceptions/Linux-syscall-note');
    if (hasNote) {
      const note = await readFile(new URL(`../public/data/${version}/sources/LICENSES/exceptions/Linux-syscall-note`, import.meta.url), 'utf8');
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
