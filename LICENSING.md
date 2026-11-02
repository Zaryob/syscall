<!-- SPDX-License-Identifier: GPL-2.0-only -->
# Licensing and source distribution

The original application code, importer, tests, documentation, and generated
JSON compilation are licensed under **GNU General Public License version 2
only (GPL-2.0-only)**. The full, unmodified license is in [LICENSE](LICENSE).
This project does not offer a GPL version 3 or an “or later” option.

The original C example templates in `public/examples.mjs` and the generated C
downloads are also GPL-2.0-only, with an SPDX notice in each generated file.
They are newly authored templates populated with syscall facts; Linux manual
page example code is not copied into them.

## Linux inputs retain their own terms

Files under `public/data/<release>/sources/` are imported Linux inputs, not
newly authored application files. Their original SPDX expressions, copyright
notices, license texts, and exceptions remain unchanged. In particular:

- Internal headers such as `include/linux/syscalls.h` are GPL-2.0-only.
- Some tables are `GPL-2.0 WITH Linux-syscall-note`.
- Linux's historical `GPL-2.0` identifier means GPL version 2 only, as explained
  in the bundled kernel license file. It is retained verbatim in input metadata.
- The syscall exception applies where upstream grants it. It is not a blanket
  exception for internal headers, generated JSON, or this application's code.

The JSON files mix table facts and extracted declarations. They are distributed
under GPL-2.0-only as a conservative project policy, without claiming exclusive
rights over facts or revoking permissions already granted by upstream. A
downstream user can rely on upstream permissions for the corresponding upstream
material; our application license does not replace them.

## What accompanies each release

`public/data/<release>/sources.json` and each architecture JSON record:

- The exact kernel tag, input paths, original SPDX expressions, and SHA-256 hashes.
- Paths to bundled, unmodified input files, with their complete original notices.
- The kernel `COPYING`, GPL version 2 text, and `Linux-syscall-note` exception.
- A modification notice identifying conversion to JSON and the importer path.

The importer transforms tables and declarations into JSON; it does not edit the
bundled Linux input files. A Git symlink returned by the raw upstream endpoint
is stored as its target-path text and identified as such in the source manifest.
`scripts/sync_kernel.py` is the source of the generation process and must be
included when distributing generated data. For a release, distribute this
repository's source with its license texts, notices, generator, and bundled
inputs; do not strip the license/provenance fields from downloadable JSON.

## Website delivery

The web footer links to the full GPL, syscall exception, and source notices.
The inputs for a snapshot are downloadable alongside the JSON, at
`/data/<release>/sources/<kernel-path>` (with the configured Jekyll `baseurl`
prepended on a project site). A source archive is linked from the footer:
`/downloads/syscall-reference-source.tar.gz`. It contains the application,
Jekyll configuration/templates, generator, tests, license notices, and kernel
inputs. Installed gems, caches, environment files and Git state are excluded.

Run `python3 scripts/prepare_site.py` before a direct Jekyll build, or use
`npm run build`, which includes preparation. The Pages workflow performs this
step automatically. Static JSON downloads and single-entry exports retain
licensing/provenance metadata; the optional local Node API is not part of the
published Jekyll runtime.

The license rules were checked against the Linux project's
[licensing documentation](https://docs.kernel.org/process/license-rules.html)
and the bundled upstream license files. This choice preserves the upstream
terms; it does not change the license of Linux itself.
