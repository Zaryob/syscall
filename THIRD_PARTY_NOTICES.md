<!-- SPDX-License-Identifier: GPL-2.0-only -->
# Third-party sources

The generated files in `public/data/` contain Linux syscall table facts and
C interface declarations extracted from Linux source. Every snapshot records
its release tag, source paths, original SPDX identifiers, and SHA-256 file hashes.
The exact input text is bundled in `public/data/<release>/sources/`; its complete
original copyright and license notices have not been edited. The file listing
is `public/data/<release>/sources.json`, and that per-file record is
authoritative: the summary below only restates it. Linux is maintained by
Linus Torvalds and its contributors: https://github.com/torvalds/linux.

Original source notices:

- `include/linux/syscalls.h`: SPDX `GPL-2.0-only` from v5.19; original credits
  include Randy Dunlap (2004) and Open Source Development Labs (2004).
- `include/linux/compat.h`, `kernel/sys_ni.c` and the top-level `Makefile`:
  SPDX `GPL-2.0` from v4.15.
- Architecture syscall headers: SPDX `GPL-2.0-only` for
  `arch/x86/include/asm/syscalls.h` (from v5.19, with the original Jaswinder
  Singh Rajput 2008 notice), `arch/arm/include/asm/syscalls.h`,
  `arch/mips/include/asm/syscalls.h` and the arm64 and RISC-V `asm/unistd.h`
  (v5.19 and v6.6); SPDX `GPL-2.0` for `arch/powerpc/include/asm/syscalls.h`;
  SPDX `GPL-2.0+` for `arch/loongarch/include/asm/unistd.h`.
- Syscall `.tbl` files: SPDX `GPL-2.0 WITH Linux-syscall-note` for the MIPS,
  PowerPC and s390 tables in every bundled release, and for the x86 and ARM
  tables, `scripts/syscall.tbl` and `arch/arm64/tools/syscall_64.tbl` from
  v6.12. The x86 tables in v3.7–v6.6 and the ARM table in v4.15–v6.6 have no
  SPDX line and are recorded with the `COPYING` fallback described below.
  UAPI `unistd.h` headers carry `GPL-2.0 WITH Linux-syscall-note` where they
  have an SPDX line. The syscall note is available at
  https://github.com/torvalds/linux/blob/v7.3/LICENSES/exceptions/Linux-syscall-note.
- `Makefile.syscalls` files and the architecture `Kconfig` files: SPDX
  `GPL-2.0`, except `arch/arm64/Kconfig` and `arch/riscv/Kconfig`, which are
  `GPL-2.0-only` from v5.19.
- C files read for `SYSCALL_DEFINE` signatures and definition sites:
  - SPDX `GPL-2.0`: in `arch/x86/kernel/`, `sys_x86_64.c`, `process.c`,
    `signal.c`, `signal_64.c`, `ioport.c`, `ldt.c`, `tls.c`, `shstk.c`,
    `sys_ia32.c` and `vm86_32.c`; in `arch/s390/kernel/`, `syscall.c`,
    `signal.c`, `runtime_instr.c`, `guarded_storage.c` and `sthyi.c`;
    `arch/s390/pci/pci_mmio.c`; `arch/mips/kernel/linux32.c`;
    `arch/riscv/kernel/usercfi.c`; `ipc/msg.c`, `ipc/sem.c` and `ipc/shm.c`.
  - SPDX `GPL-2.0-only`: `arch/x86/kernel/process_64.c`;
    `arch/arm64/kernel/sys.c`, `arch/arm64/kernel/signal.c` and
    `arch/arm64/mm/gcs.c`; `arch/riscv/kernel/sys_riscv.c` and
    `arch/riscv/kernel/sys_hwprobe.c`; `arch/powerpc/kernel/pci_32.c`;
    `fs/exec.c`.
  - SPDX `GPL-2.0+`: `arch/loongarch/kernel/syscall.c` and
    `arch/loongarch/kernel/signal.c`.
  - SPDX `GPL-2.0-or-later`: `arch/riscv/kernel/signal.c`,
    `arch/powerpc/kernel/pci_64.c` and
    `arch/powerpc/mm/book3s64/subpage_prot.c`.
  A candidate C file with neither an SPDX line nor the notice described next
  is not bundled and not used.
- Files without an SPDX line are recorded as `license_identifier:
  GPL-2.0-only` with `license_basis: COPYING`, which refers to the release's
  bundled `COPYING` and is not an upstream SPDX expression. This covers every
  input of v1.0–v3.7, the remaining pre-SPDX inputs of v4.15, the tables named
  above, and `arch/mips/kernel/signal.c`, `arch/mips/kernel/syscall.c` and
  `arch/mips/mm/cache.c` (v5.19–v7.3), whose own notices place them under the
  GNU General Public License and refer to `COPYING`.

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
Manual-page prose is not bundled. Links are resolved against the checked-in
page catalog; entries without a cataloged page have no manual link. Supplemental NR, RET2 and clobber notes
are editorial reference data in `public/reference.mjs`, not changes to imported
Linux snapshots. PowerPC error handling is checked against the kernel ABI
documentation and `arch/powerpc/kernel/interrupt.c`, preserving cr0.SO for sc.

## Shared console theme assets

The common Zaryob theme code in `public/assets/console/theme.css`, `theme.js`
and `public/_includes/console-header.html` is GPL-2.0-or-later. IBM Plex Mono
Regular and Medium, and IBM Plex Sans Regular, Italic, SemiBold and
SemiBoldItalic are Copyright © 2017 IBM Corp., with Reserved Font Name
"Plex", and are distributed unmodified under SIL OFL 1.1; the full notice is
`public/assets/console/fonts/OFL.txt`. The Font Awesome Free regular icon sprite
retains its upstream license notice; see
`public/assets/console/ICONS-LICENSE.txt`. These assets retain their own licenses.
