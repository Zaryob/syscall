// SPDX-License-Identifier: GPL-2.0-only
export function searchSyscalls(rows, query = '') {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  if (/^(?:0x[\da-f]+|\d+)$/.test(q)) {
    const nr = q.startsWith('0x') ? Number.parseInt(q.slice(2), 16) : Number(q);
    return rows.filter(row => row.number === nr);
  }
  return rows.filter(row => [row.name, row.entry, ...(row.arguments ?? [])].join(' ').toLowerCase().includes(q));
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
