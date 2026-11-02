<!-- SPDX-License-Identifier: GPL-2.0-only -->
# Third-party sources

The generated files in `public/data/` contain Linux syscall table facts and
C interface declarations extracted from Linux source. Every snapshot records
its release tag, source paths, original SPDX identifiers, and SHA-256 file hashes.
The exact input text is bundled in `public/data/<release>/sources/`; its complete
original copyright and license notices have not been edited. The file listing
is `public/data/<release>/sources.json`. Linux is maintained by
Linus Torvalds and its contributors: https://github.com/torvalds/linux.

Original source notices:

- `include/linux/syscalls.h`: GPL-2.0-only; original credits include Randy
  Dunlap (2004) and Open Source Development Labs (2004).
- `include/linux/compat.h`: GPL-2.0. Architecture syscall headers:
  GPL-2.0-only, including the original Jaswinder Singh Rajput (2008) notice
  in `arch/x86/include/asm/syscalls.h`.
- Linux syscall `.tbl` files: GPL-2.0 WITH Linux-syscall-note, as stated in
  the respective source files. The syscall note is available at
  https://github.com/torvalds/linux/blob/v7.3/LICENSES/exceptions/Linux-syscall-note.
- Kernel Makefiles: GPL-2.0.

The full upstream `COPYING`, `LICENSES/preferred/GPL-2.0`, and
`LICENSES/exceptions/Linux-syscall-note` accompany each snapshot. Reference
copies of the two license documents are also in this repository's `LICENSES/`
directory. The application's GPL version 2 text is in `LICENSE`.

The kernel's historical `GPL-2.0` identifier means version 2 only. The exception
is preserved where upstream grants it; it is not attached to internal headers
or the entire application. The generated JSON compilation is GPL-2.0-only,
with upstream permissions preserved. No exclusive rights over syscall facts
are claimed. See [LICENSING.md](LICENSING.md) for scope and distribution.

Modification notice: syscall-reference parses and filters upstream tables and
declarations by ABI and converts the results to JSON. The bundled Linux input
text is unchanged; symlinks returned by the raw upstream endpoint are stored
as target-path text and identified in the manifest. The generation source is
`scripts/sync_kernel.py`.

Register calling conventions are factual reference information checked against
Linux man-pages `syscall(2)`: https://man7.org/linux/man-pages/man2/syscall.2.html.
Manual-page prose is not bundled. Links use the corresponding syscall name and
may not exist for entries without a dedicated manual page.

## Shared console theme assets

The common Zaryob theme code in `public/assets/console/theme.css`, `theme.js`
and `public/_includes/console-header.html` is GPL-2.0-or-later. IBM Plex Mono
Regular and Medium are Copyright © 2017 IBM Corp., with Reserved Font Name
"Plex", and are distributed unmodified under SIL OFL 1.1; the full notice is
`public/assets/console/fonts/OFL.txt`. The Font Awesome Free regular icon sprite
retains its upstream license notice; see
`public/assets/console/ICONS-LICENSE.txt`. These assets retain their own licenses.
