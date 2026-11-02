// SPDX-License-Identifier: GPL-2.0-only
// A Jekyll project site can be mounted at /repo/ instead of the origin root.
export function withBase(root, path = '') {
  return `${root.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
}
