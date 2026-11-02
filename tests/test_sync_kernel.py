# SPDX-License-Identifier: GPL-2.0-only
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("sync_kernel", Path(__file__).resolve().parents[1] / "scripts/sync_kernel.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class ImportTests(unittest.TestCase):
    def test_table_filters_abi_without_losing_unimplemented_slots(self):
        table = "# header\n0 common read sys_read\n1 64 write sys_write\n2 x32 compat compat_sys_read\n3 common reserved\n4 common unavailable sys_ni_syscall\n"
        rows = sync.parse_table(table, ["common", "64"])
        self.assertEqual([r['number'] for r in rows], [0, 1, 3, 4])
        self.assertIsNone(rows[2]['entry'])
        self.assertEqual(rows[0]['line'], 2)

    def test_abi_overlap_is_rejected(self):
        with self.assertRaises(ValueError):
            sync.parse_table("0 common read sys_read\n0 64 write sys_write", ["common", "64"])

    def test_prototypes_preserve_no_arguments_unknown_names_and_source_lines(self):
        text = "/* comment\n * two lines */\nasmlinkage long sys_getpid(void);\nasmlinkage long sys_read(unsigned int fd,\nchar __user *buf, size_t count);\n"
        result = sync.parse_prototypes(text, 'include/linux/syscalls.h')
        self.assertEqual(result['sys_getpid']['arguments'], [])
        self.assertEqual(result['sys_getpid']['line'], 3)
        self.assertEqual(result['sys_read']['arguments'], ['unsigned int fd', 'char __user *buf', 'size_t count'])

    def test_conflicting_configuration_declarations_stay_unknown(self):
        text = 'asmlinkage long sys_clone(int flags, long stack);\nasmlinkage long sys_clone(long stack, int flags);\nasmlinkage long sys_clone(int flags, long stack);'
        result = sync.parse_prototypes(text, 'syscalls.h')
        self.assertIsNone(result['sys_clone']['arguments'])
        self.assertIn('configuration', result['sys_clone']['note'])

    def test_extra_abis_follow_arch_makefile(self):
        self.assertEqual(sync.extra_abis('syscall_abis_32 += wrong\nsyscall_abis_64 += renameat rlimit memfd_secret\n'), ['renameat', 'rlimit', 'memfd_secret'])
        with self.assertRaises(ValueError):
            sync.extra_abis('syscall_abis_64 += $(UNKNOWN)')

    def test_unreviewed_or_missing_source_licenses_are_rejected(self):
        for text in ['asmlinkage long sys_read(void);', '/* SPDX-License-Identifier: LicenseRef-Unknown */']:
            with self.assertRaises(ValueError):
                sync.source_licenses({'include/linux/syscalls.h': {'text': text, 'sha256': 'fixture'}})

    def test_local_import_is_offline_and_publishes_a_complete_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory) / 'linux'
            output = Path(directory) / 'data'
            files = {
                'Makefile': '# SPDX-License-Identifier: GPL-2.0\nVERSION = 7\nPATCHLEVEL = 3\nSUBLEVEL = 0\n',
                'include/linux/syscalls.h': '/* SPDX-License-Identifier: GPL-2.0-only */\nasmlinkage long sys_read(unsigned int fd, char *buf, size_t count);',
                'include/linux/compat.h': '/* SPDX-License-Identifier: GPL-2.0 */\n',
                'arch/arm64/tools/syscall_64.tbl': '../../../scripts/syscall.tbl',
            }
            for path in sync.LICENSE_FILES:
                files[path] = 'Fixture for upstream license notice: ' + path
            for config in sync.ARCHES.values():
                files[config['table']] = '# SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note\n' + ('0 common read sys_read\n1 common unused sys_ni_syscall\n' if config['table'] != 'arch/x86/entry/syscalls/syscall_32.tbl' else '3 i386 read sys_read\n')
                if config['table'] == 'scripts/syscall.tbl':
                    files['arch/{}/kernel/Makefile.syscalls'.format(config['kernel'])] = '# SPDX-License-Identifier: GPL-2.0\nsyscall_abis_64 +=\n'
            for path, text in files.items():
                target = tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            sync.generate('v7.3', tree, output)
            sync.update_manifest(output)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['versions'], ['v7.3'])
            data = json.loads((output / 'v7.3/x64.json').read_text())
            self.assertEqual(data['provenance']['kind'], 'local')
            self.assertEqual(data['license'], 'GPL-2.0-only')
            for path, text in files.items():
                self.assertEqual((output / 'v7.3/sources' / path).read_text(), text)
            self.assertEqual(data['syscalls'][1]['status'], 'unimplemented')
            self.assertIsNone(data['syscalls'][1]['arguments'])
            with self.assertRaises(ValueError):
                sync.generate('v6.12', tree, output)


if __name__ == '__main__':
    unittest.main()
