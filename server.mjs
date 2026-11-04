// SPDX-License-Identifier: GPL-2.0-only
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { diffSyscalls, searchSyscalls, availableArchitectures, parseSyscallNumber } from './public/catalog.mjs';
import { snapshotPath } from './public/paths.mjs';

const ROOT = path.resolve(fileURLToPath(new URL('./public/', import.meta.url)));
const modules = new Set(['/catalog.mjs', '/notes.mjs']);
const documentation = '/api/v1/docs';
const mime = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.txt': 'text/plain; charset=utf-8' };
const json = (res, status, body) => {
  res.writeHead(status, { 'Content-Type': mime['.json'] });
  res.end(JSON.stringify(body, null, 2) + '\n');
};
async function load(version, arch, manifest) {
  if (!manifest.versions.includes(version) || !availableArchitectures(manifest, version).includes(arch)) return null;
  return JSON.parse(await readFile(path.join(ROOT, snapshotPath(manifest, version, arch + '.json')), 'utf8'));
}

export function createApp() {
  return createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (!['GET', 'HEAD'].includes(req.method)) {
      res.setHeader('Allow', 'GET, HEAD');
      return json(res, 405, { error: 'Method not allowed' });
    }
    try {
      const url = new URL(req.url, 'http://localhost');
      const pathname = decodeURIComponent(url.pathname);
      if (pathname.startsWith('/api/')) {
        if (pathname === documentation) {
          return json(res, 200, {
            index: '/api/v1',
            methods: ['GET', 'HEAD'],
            endpoints: [
              { path: '/api/v1/architectures', description: 'List available ABIs and calling conventions.' },
              { path: '/api/v1/versions', description: 'List bundled kernel releases.' },
              { path: '/api/v1/syscalls/{arch}', query: ['version', 'q'], description: 'Search a release table. The default version is the latest release.' },
              { path: '/api/v1/syscalls/{arch}/{nameOrNumber}', query: ['version'], description: 'Look up a syscall by name, decimal number or hexadecimal number.' },
              { path: '/api/v1/syscalls/{arch}/diff', query: ['from (required)', 'version'], description: 'Compare two releases for one ABI. Changed entries include a list of reasons.' },
            ],
          });
        }
        const manifest = JSON.parse(await readFile(path.join(ROOT, 'data/manifest.json'), 'utf8'));
        const parts = pathname.split('/').filter(Boolean);
        if (pathname === '/api/v1') return json(res, 200, { ...manifest, documentation });
        if (pathname === '/api/v1/architectures') return json(res, 200, manifest.architectures);
        if (pathname === '/api/v1/versions') return json(res, 200, manifest.versions);
        if (parts[0] !== 'api' || parts[1] !== 'v1' || parts[2] !== 'syscalls' || parts.length < 4 || parts.length > 5) return json(res, 404, { error: 'Unknown endpoint' });
        const version = url.searchParams.get('version') || manifest.latest;
        const snapshot = await load(version, parts[3], manifest);
        if (!snapshot) return json(res, 404, { error: 'Unknown architecture or kernel version' });
        const from = url.searchParams.get('from');
        if (parts[4] === 'diff') {
          if (!from) return json(res, 400, { error: 'Supply ?from=v6.12&version=v7.3' });
          const previous = await load(from, parts[3], manifest);
          if (!previous) return json(res, 404, { error: 'Unknown comparison version' });
          return json(res, 200, { license: snapshot.license, licensing: snapshot.licensing, provenance: snapshot.provenance, from_provenance: previous.provenance, architecture: parts[3], from, to: version, ...diffSyscalls(previous.syscalls, snapshot.syscalls) });
        }
        if (parts.length === 5) {
          const key = parts[4];
          const number = parseSyscallNumber(key);
          const row = snapshot.syscalls.find(r => number === null ? r.name === key : r.number === number);
          return row ? json(res, 200, { license: snapshot.license, licensing: snapshot.licensing, provenance: snapshot.provenance, kernel: version, architecture: parts[3], calling_convention: snapshot.calling_convention, ...row }) : json(res, 404, { error: 'Syscall not found' });
        }
        return json(res, 200, { ...snapshot, syscalls: searchSyscalls(snapshot.syscalls, url.searchParams.get('q') || '') });
      }
      // Optional dynamic API only. The published frontend is built by Jekyll.
      if (!pathname.startsWith('/data/') && !pathname.startsWith('/licenses/') && !modules.has(pathname)) return json(res, 404, { error: 'Use Jekyll on port 5173 for the website; this process serves the optional JSON API.' });
      const file = path.resolve(ROOT, '.' + pathname);
      if (!file.startsWith(ROOT + path.sep) && file !== ROOT) return json(res, 403, { error: 'Forbidden' });
      const body = await readFile(file);
      res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream', 'Cache-Control': 'no-cache' });
      res.end(req.method === 'HEAD' ? undefined : body);
    } catch (error) {
      if (error instanceof URIError) return json(res, 400, { error: 'Invalid URL encoding' });
      if (['ENOENT', 'EISDIR', 'ENOTDIR'].includes(error.code)) return json(res, 404, { error: 'Not found' });
      console.error(error);
      json(res, 500, { error: 'Unable to read reference data' });
    }
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.env.PORT || 5174);
  const host = process.env.HOST || '127.0.0.1';
  createApp().listen(port, host, () => console.log(`Optional syscall API: http://${host}:${port}/api/v1`));
}
