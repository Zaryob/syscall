// SPDX-License-Identifier: GPL-2.0-only
// Generated pages are plain HTML in one language each (scripts/static_pages.py).
// The header's language selector opens the translation through the page's
// data-translation-lang link (console/i18n.js); this only keeps the footer notice
// in the interface language.
import { referenceCopy } from './reference.mjs';

function renderCopy() {
  const copy = referenceCopy(window.ZaryobLanguage.language);
  document.querySelectorAll('[data-syscall-copy]').forEach(node => { node.innerHTML = copy[node.dataset.syscallCopy] ?? node.innerHTML; });
}
renderCopy();
window.ZaryobLanguage.subscribe(renderCopy);
