// SPDX-License-Identifier: GPL-2.0-only
import { syscallNote } from './notes.mjs';

export function availableArchitectures(manifest, version) {
  return manifest.version_architectures?.[version] ?? manifest.architectures.map(a => a.id);
}

export function normalizeSelection(manifest, state) {
  if (!manifest.versions.includes(state.kernel)) state.kernel = manifest.latest;
  const available = availableArchitectures(manifest, state.kernel);
  if (!available.includes(state.arch)) state.arch = available.includes('x64') ? 'x64' : available[0];
  if (!manifest.versions.includes(state.compare) || state.compare === state.kernel || !availableArchitectures(manifest, state.compare).includes(state.arch)) state.compare = '';
  return state;
}

export function searchSyscalls(rows, query = '') {
  const normalize = text => text.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').replace(/ı/g, 'i');
  const q = normalize(query.trim());
  if (!q) return rows;
  if (/^(?:0x[\da-f]+|\d+)$/.test(q)) {
    const nr = q.startsWith('0x') ? Number.parseInt(q.slice(2), 16) : Number(q);
    return rows.filter(row => row.number === nr);
  }
  return rows.filter(row => {
    const note = row.status === 'unimplemented' ? undefined : syscallNote(row.name);
    return [row.name, row.entry, ...(row.arguments ?? []), note?.en, note?.tr]
      .some(text => text && normalize(text).includes(q));
  });
}

export function diffSyscalls(before, after) {
  const key = row => `${row.number}:${row.name}`;
  const old = new Map(before.map(row => [key(row), row]));
  const current = new Map(after.map(row => [key(row), row]));
  const signature = row => JSON.stringify([row.entry, row.status, row.arguments]);
  return {
    added: after.filter(row => !old.has(key(row))),
    removed: before.filter(row => !current.has(key(row))),
    changed: after.filter(row => old.has(key(row)) && signature(row) !== signature(old.get(key(row))))
      .map(row => ({ before: old.get(key(row)), after: row })),
  };
}
