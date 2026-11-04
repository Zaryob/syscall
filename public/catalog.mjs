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

export function parseSyscallNumber(value) {
  const text = value.trim().toLowerCase();
  if (!/^(?:0x[\da-f]+|\d+)$/.test(text)) return null;
  return Number(text);
}

export function searchSyscalls(rows, query = '') {
  const normalize = text => text.toLowerCase().normalize('NFD').replace(/\p{M}/gu, '').replace(/ı/g, 'i');
  const q = normalize(query.trim());
  if (!q) return rows;
  const nr = parseSyscallNumber(q);
  if (nr !== null) return rows.filter(row => row.number === nr);
  return rows.filter(row => {
    const note = row.status === 'unimplemented' ? undefined : syscallNote(row.name);
    return [row.name, row.entry, ...(row.arguments ?? []), note?.en, note?.tr]
      .some(text => text && normalize(text).includes(q));
  });
}

const normalizeC = text => text.trim().replace(/\s+/g, ' ').replace(/\s*([*()[\],])\s*/g, '$1');
const absentEntry = entry => [undefined, null, '-', 'sys_ni_syscall', 'compat_sys_ni_syscall'].includes(entry) ? null : entry;
const typeWords = new Set('char short int long signed unsigned float double void _Bool bool const volatile restrict __user __kernel __force __iomem'.split(' '));

function namedParameter(parameter) {
  const match = /^(.+[\s*])([A-Za-z_]\w*)$/.exec(parameter);
  if (!match || typeWords.has(match[2])) return null;
  const type = normalizeC(match[1]);
  if (/(?:^|\s)(?:struct|union|enum)$/.test(type) || type.split(' ').every(word => ['const', 'volatile', '__user', '__kernel', '__force', '__iomem'].includes(word))) return null;
  return { type, name: match[2] };
}

function changeReasons(before, after) {
  const reasons = new Set();
  if (before.status !== after.status) reasons.add('status');
  if (absentEntry(before.entry) !== absentEntry(after.entry)) reasons.add('entry');
  for (const field of ['compat_entry', 'oabi_entry']) {
    if (absentEntry(before[field]) !== absentEntry(after[field])) reasons.add(field);
  }
  if (Boolean(before.noreturn) !== Boolean(after.noreturn)) reasons.add('noreturn');
  if (Boolean(before.arguments) !== Boolean(after.arguments)) reasons.add('signature_resolution');
  if (before.arguments && after.arguments) {
    if (before.arguments.length !== after.arguments.length) reasons.add('argument_count');
    for (const [index, argument] of before.arguments.entries()) {
      const next = after.arguments[index];
      if (next === undefined || normalizeC(argument) === normalizeC(next)) continue;
      const from = namedParameter(argument);
      const to = namedParameter(next);
      if (!from || !to) {
        reasons.add('parameters');
        continue;
      }
      if (from.type !== to.type) reasons.add('argument_types');
      if (from.name !== to.name) reasons.add('argument_names');
    }
  }
  if (before.declaration && after.declaration) {
    const prefix = row => normalizeC(row.declaration.split('(')[0]);
    if (prefix(before) !== prefix(after) && before.entry === after.entry) reasons.add('declaration');
  }
  return [...reasons];
}

export function diffSyscalls(before, after) {
  const key = row => `${row.number}:${row.name}`;
  const old = new Map(before.map(row => [key(row), row]));
  const current = new Map(after.map(row => [key(row), row]));
  const changed = [];
  for (const row of after) {
    const prior = old.get(key(row));
    if (!prior) continue;
    const reasons = changeReasons(prior, row);
    if (reasons.length) changed.push({ before: prior, after: row, reasons });
  }
  return {
    added: after.filter(row => !old.has(key(row))),
    removed: before.filter(row => !current.has(key(row))),
    changed,
  };
}
