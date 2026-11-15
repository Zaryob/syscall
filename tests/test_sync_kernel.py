# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("sync_kernel", Path(__file__).resolve().parents[1] / "scripts/sync_kernel.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


manual = importlib.util.spec_from_file_location("sync_manual_pages", Path(__file__).resolve().parents[1] / "scripts/sync_manual_pages.py")
manual_pages = importlib.util.module_from_spec(manual)
manual.loader.exec_module(manual_pages)


def tree_digest(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}


class StubSource:
    def __init__(self, files):
        self.files = files

    def read(self, path, optional=False):
        return self.files.get(path, '')


class ImportTests(unittest.TestCase):
    def test_release_directories_mirror_the_active_revisions(self):
        data = sync.ROOT / 'public/data'
        manifest = json.loads((data / 'manifest.json').read_text())
        for ref in manifest['versions']:
            with self.subTest(ref=ref):
                active = data / manifest.get('version_paths', {}).get(ref, ref)
                self.assertEqual(tree_digest(data / ref), tree_digest(active))

    def test_every_manual_alias_targets_a_cataloged_page(self):
        self.assertEqual(manual_pages.alias_errors(sync.MANUAL_CATALOG), [])
        broken = {'sections': {'2': ['exit'], '3': []}, 'aliases': {'exit': '_exit', 'mq_timedsend': 'mq_send.3'}}
        self.assertEqual(manual_pages.alias_errors(broken), ['exit -> _exit(2)', 'mq_timedsend -> mq_send(3)'])
        self.assertEqual(sync.manual_url('exit'), 'https://man7.org/linux/man-pages/man2/exit.2.html')

    def test_kconfig_selects_choose_between_guarded_declarations(self):
        header = ('#ifdef CONFIG_CLONE_BACKWARDS\nasmlinkage long sys_clone(unsigned long, int __user *, unsigned long);\n#else\n'
                  '#ifdef CONFIG_CLONE_BACKWARDS3\nasmlinkage long sys_clone(int, unsigned long);\n#else\n'
                  'asmlinkage long sys_clone(unsigned long, int __user *);\n#endif\n#endif\n'
                  '#if defined(CONFIG_ARCH_SPLIT_ARG64)\nasmlinkage long sys_fanotify_mark(unsigned int mask_1, unsigned int mask_2);\n#else\n'
                  'asmlinkage long sys_fanotify_mark(u64 mask);\n#endif\n'
                  '#ifdef CONFIG_OLD_SIGSUSPEND\nasmlinkage long sys_sigsuspend(old_sigset_t mask);\n#endif\n'
                  '#ifdef CONFIG_OLD_SIGSUSPEND3\nasmlinkage long sys_sigsuspend(int unused1, int unused2, old_sigset_t mask);\n#endif\n'
                  '#ifdef CONFIG_OLD_SIGACTION\nasmlinkage long sys_sigaction(int, const struct old_sigaction __user *);\n#endif\n'
                  '#ifdef CONFIG_COMPAT\nasmlinkage long sys_other(int a);\n#else\nasmlinkage long sys_other(long a);\n#endif\n')
        prototypes = sync.parse_prototypes(header, 'include/linux/syscalls.h')
        self.assertIsNone(prototypes['sys_clone']['arguments'])
        x86 = ('config X86_32\n\tdef_bool y\n\tdepends on !64BIT\n\tselect CLONE_BACKWARDS\n\tselect ARCH_SPLIT_ARG64\n\tselect OLD_SIGACTION\n'
               'config X86\n\tdef_bool y\n\thelp\n\t  Prose that may say\n\t  select CLONE_BACKWARDS3\n'
               'config IA32_EMULATION\n\tbool "IA32 Emulation"\n\tselect CLONE_BACKWARDS3 if EXPERT = y\n'
               'config COMPAT_32\n\tdef_bool y\n\tdepends on IA32_EMULATION || X86_32\n\tselect OLD_SIGSUSPEND3\n')
        native = sync.Configuration(StubSource({'arch/x86/Kconfig': x86}), 'x86')
        clone = native.prototype(prototypes['sys_clone'])
        self.assertEqual(clone['arguments'], ['unsigned long', 'int __user *', 'unsigned long'])
        self.assertEqual(clone['configuration'], {'path': 'arch/x86/Kconfig', 'symbols': {'CONFIG_CLONE_BACKWARDS': True}})
        self.assertEqual(native.prototype(prototypes['sys_fanotify_mark'])['arguments'], ['unsigned int mask_1', 'unsigned int mask_2'])
        self.assertEqual(len(native.prototype(prototypes['sys_sigsuspend'])['arguments']), 3)
        self.assertIs(native.prototype(prototypes['sys_sigaction']), prototypes['sys_sigaction'])
        # An undecidable select keeps the declaration configuration-dependent.
        wide = sync.Configuration(StubSource({'arch/x86/Kconfig': x86}), 'x64')
        self.assertIsNone(wide.prototype(prototypes['sys_clone'])['arguments'])
        self.assertEqual(wide.prototype(prototypes['sys_fanotify_mark'])['arguments'], ['u64 mask'])
        # Without selects the #else branches apply and unselected declarations are dropped.
        plain = sync.Configuration(StubSource({'arch/mips/Kconfig': 'config MIPS\n\tbool\n\tdefault y\n\tselect CLONE_BACKWARDS\n'}), 'mips-o32')
        self.assertIsNone(plain.prototype(prototypes['sys_sigaction']))
        self.assertIsNone(plain.prototype(prototypes['sys_sigsuspend']))
        self.assertEqual(plain.prototype(prototypes['sys_clone'])['line'], 2)
        # Symbols outside the reviewed list, or a missing Kconfig, change nothing.
        self.assertIsNone(plain.prototype(prototypes['sys_other'])['arguments'])
        missing = sync.Configuration(StubSource({}), 'arm')
        self.assertIs(missing.prototype(prototypes['sys_clone']), prototypes['sys_clone'])

    def test_architecture_definitions_and_enosys_fallbacks_are_parsed(self):
        text = ('#ifdef CONFIG_TRAD_SIGNALS\nSYSCALL_DEFINE3(sigaction, int, sig, const struct sigaction __user *, act,\n'
                '\tstruct sigaction __user *, oact)\n{\n}\n#endif\nSYSCALL_DEFINE0(getpid)\n{\n}\n'
                'COMPAT_SYSCALL_DEFINE1(old, int, value)\n{\n}\n')
        result = sync.parse_definitions(text, 'arch/mips/kernel/signal.c')
        self.assertEqual(result['sys_sigaction']['declaration'], 'asmlinkage long sys_sigaction(int sig, const struct sigaction __user *act, struct sigaction __user *oact);')
        self.assertEqual((result['sys_sigaction']['line'], result['sys_sigaction']['kind']), (2, 'syscall_macro'))
        self.assertEqual(result['sys_getpid']['arguments'], [])
        self.assertIn('compat_sys_old', result)
        with self.assertRaises(ValueError):
            sync.parse_definitions('SYSCALL_DEFINE2(bad, int, a)\n{\n}\n', 'x.c')
        fallbacks = sync.fallback_entries('#define cond_syscall(x) x\ncond_syscall(sys_old);\n/* COND_SYSCALL(hidden); */\nCOND_SYSCALL(uselib);\nCOND_SYSCALL_COMPAT(io_setup);\n', 'kernel/sys_ni.c')
        self.assertEqual(fallbacks, {'sys_old': {'path': 'kernel/sys_ni.c', 'line': 2}, 'sys_uselib': {'path': 'kernel/sys_ni.c', 'line': 4}, 'compat_sys_io_setup': {'path': 'kernel/sys_ni.c', 'line': 5}})

    def test_active_data_resolves_abi_determined_declarations(self):
        data = sync.ROOT / 'public/data/v7.3'
        def row(arch, name):
            return next(r for r in json.loads((data / (arch + '.json')).read_text())['syscalls'] if r['name'] == name)
        self.assertEqual(row('x64', 'clone')['arguments'], ['unsigned long', 'unsigned long', 'int __user *', 'int __user *', 'unsigned long'])
        self.assertEqual(row('arm64', 'clone')['arguments'], ['unsigned long', 'unsigned long', 'int __user *', 'unsigned long', 'int __user *'])
        self.assertEqual(len(row('x64', 'fanotify_mark')['arguments']), 5)
        self.assertEqual(len(row('x86', 'fanotify_mark')['arguments']), 6)
        self.assertEqual(row('mips-o32', 'sigaction')['arguments'][1], 'const struct sigaction __user *act')
        self.assertEqual(row('arm64', 'mmap')['signature_source']['path'], 'arch/arm64/kernel/sys.c')
        self.assertEqual(row('arm', 'uselib')['enosys_fallback']['path'], 'kernel/sys_ni.c')
        self.assertNotIn('enosys_fallback', row('x64', 'read'))
        self.assertTrue(row('x64', 'exit')['man_url'].endswith('/man2/exit.2.html'))

    def test_table_filters_abi_without_losing_unimplemented_slots(self):
        table = "# header\n0 common read sys_read\n1 64 write sys_write\n2 x32 compat compat_sys_read\n3 common reserved\n4 common unavailable sys_ni_syscall\n"
        rows = sync.parse_table(table, ["common", "64"])
        self.assertEqual([r['number'] for r in rows], [0, 1, 3, 4])
        self.assertIsNone(rows[2]['entry'])
        self.assertEqual(rows[0]['line'], 2)

    def test_abi_overlap_is_rejected(self):
        with self.assertRaises(ValueError):
            sync.parse_table("0 common read sys_read\n0 64 write sys_write", ["common", "64"])

    def test_mips_n64_includes_common_calls_and_keeps_source_identity(self):
        ref = 'v6.12'
        tree = sync.ROOT / 'public/data' / ref / 'sources'
        path, rows = sync.architecture_rows(sync.Source(ref, tree), 'mips-n64')
        row = next(row for row in rows if row['number'] == 5450)
        self.assertEqual((row['name'], row['abi'], row['entry']), ('set_mempolicy_home_node', 'common', 'sys_set_mempolicy_home_node'))
        original = (tree / path).read_text().splitlines()[row['line'] - 1]
        self.assertIn('common', original)
        self.assertIn('set_mempolicy_home_node', original)

    def test_powerpc_plain_prototypes_and_multiline_arguments_are_resolved(self):
        text = ('#define bogus(x) long sys_macro(x);\n'
                'long sys_mmap(unsigned long addr,\n size_t len);\n'
                'long sys_rt_sigreturn(void);\n'
                'long sys_definition(void) { return 0; }\n'
                'return sys_not_a_declaration();\n')
        result = sync.parse_prototypes(text, 'arch/powerpc/include/asm/syscalls.h')
        self.assertEqual(set(result), {'sys_mmap', 'sys_rt_sigreturn'})
        self.assertEqual(result['sys_mmap']['arguments'], ['unsigned long addr', 'size_t len'])
        self.assertEqual(result['sys_mmap']['line'], 2)
        self.assertEqual(result['sys_rt_sigreturn']['arguments'], [])

    def test_manual_aliases_never_construct_unknown_page_urls(self):
        for name, page in [('read', 'read.2'), ('pread64', 'pread.2'), ('clock_gettime64', 'clock_gettime.2'), ('clock_getres_time64', 'clock_gettime.2'), ('mq_timedsend_time64', 'mq_send.3')]:
            self.assertEqual(sync.manual_url(name), f'https://man7.org/linux/man-pages/man{page[-1]}/{page}.html')
        for name in ['unused59', 'not_a_linux_syscall', 'unknown_time64']:
            self.assertIsNone(sync.manual_url(name))

    def test_prototypes_preserve_no_arguments_unknown_names_and_source_lines(self):
        text = "/* comment\n * two lines */\nasmlinkage long sys_getpid(void);\nasmlinkage long sys_read(unsigned int fd,\nchar __user *buf, size_t count);\n"
        result = sync.parse_prototypes(text, 'include/linux/syscalls.h')
        self.assertEqual(result['sys_getpid']['arguments'], [])
        self.assertEqual(result['sys_getpid']['line'], 3)
        self.assertEqual(result['sys_read']['arguments'], ['unsigned int fd', 'char __user *buf', 'size_t count'])

    def test_prototypes_handle_historical_return_types_and_qualifiers(self):
        text = (
            "asmlinkage ssize_t sys_read(unsigned int fd, char __user *buf, size_t count);\n"
            "asmlinkage NORET_TYPE void sys_exit(int error_code);\n"
            "asmlinkage off_t sys_lseek(unsigned int fd, off_t offset, unsigned int origin);\n"
        )
        result = sync.parse_prototypes(text, 'include/linux/syscalls.h')
        self.assertEqual(result['sys_read']['arguments'], ['unsigned int fd', 'char __user *buf', 'size_t count'])
        self.assertEqual(result['sys_exit']['arguments'], ['int error_code'])
        self.assertEqual(result['sys_lseek']['arguments'], ['unsigned int fd', 'off_t offset', 'unsigned int origin'])
        self.assertEqual(result['sys_exit']['declaration'], 'asmlinkage NORET_TYPE void sys_exit(int error_code);')
        self.assertEqual(result['sys_lseek']['declaration'], 'asmlinkage off_t sys_lseek(unsigned int fd, off_t offset, unsigned int origin);')

    def test_historical_table_names_take_precedence_over_number_aliases(self):
        for ref, number, name in [('v2.6.12', 250, 'keyctl'), ('v2.6.16', 272, 'unshare')]:
            with self.subTest(ref=ref):
                tree = sync.ROOT / 'public' / 'data' / ref / 'sources'
                _, rows = sync.architecture_rows(sync.Source(ref, tree), 'x64')
                self.assertEqual(next(row['name'] for row in rows if row['number'] == number), name)

    def test_historical_license_and_gpl_plus_are_accepted(self):
        files = {
            'COPYING': {'text': 'GNU General Public License version 2 only\n', 'sha256': 'copying_hash'},
            'arch/arm/tools/syscall.tbl': {'text': '0 common restart_syscall sys_restart_syscall\n', 'sha256': 'arm_hash'},
            'arch/loongarch/include/asm/unistd.h': {'text': '/* SPDX-License-Identifier: GPL-2.0+ */\n', 'sha256': 'loongarch_hash'},
        }
        records = sync.source_licenses(files, ref='v6.6')
        records_by_path = {r['path']: r for r in records}
        self.assertEqual(records_by_path['arch/arm/tools/syscall.tbl']['license_identifier'], 'GPL-2.0-only')
        self.assertEqual(records_by_path['arch/loongarch/include/asm/unistd.h']['spdx_license_identifier'], 'GPL-2.0+')

    def test_conflicting_configuration_declarations_stay_unknown(self):
        text = 'asmlinkage long sys_clone(int flags, long stack);\nasmlinkage long sys_clone(long stack, int flags);\nasmlinkage long sys_clone(int flags, long stack);'
        result = sync.parse_prototypes(text, 'syscalls.h')
        self.assertIsNone(result['sys_clone']['arguments'])
        self.assertIsNone(result['sys_clone']['declaration'])
        self.assertIn('configuration', result['sys_clone']['note'])
        self.assertEqual(len(result['sys_clone']['alternatives']), 3)

    def test_mainline_filter_distinguishes_major_and_2_6_releases_from_maintenance(self):
        # 1.0 baseline
        self.assertTrue(sync.is_mainline('v1.0'))
        # 2.6.x mainline releases
        self.assertTrue(sync.is_mainline('v2.6.12'))
        self.assertTrue(sync.is_mainline('v2.6.16'))
        self.assertTrue(sync.is_mainline('v2.6.39'))
        # 3.x+ mainline releases (major.minor)
        self.assertTrue(sync.is_mainline('v3.0'))
        self.assertTrue(sync.is_mainline('v5.19'))
        self.assertTrue(sync.is_mainline('v6.6'))
        self.assertTrue(sync.is_mainline('v7.3'))
        # Maintenance releases (patch releases) must be rejected
        self.assertFalse(sync.is_mainline('v6.6.1'))
        self.assertFalse(sync.is_mainline('v6.12.3'))
        self.assertFalse(sync.is_mainline('v2.6.12.1'))
        # Release candidates must be rejected
        self.assertFalse(sync.is_mainline('v6.6-rc1'))
        self.assertFalse(sync.is_mainline('v7.3-rc2'))

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
                sync.MIPS_HEADER: '/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */\n' + '\n'.join(
                    f'#if _MIPS_SIM == {sim}\n#define __NR_Linux {base}\n#include <asm/unistd_{abi}.h>\n#endif'
                    for (abi, sim), base in zip(sync.MIPS_SIM.items(), [4000, 6000, 5000])
                ),
            }
            for path in sync.LICENSE_FILES:
                files[path] = 'Fixture for upstream license notice: ' + path
            for config in sync.ARCHES.values():
                abi = config['abis'][0]
                files[config['table']] = f'# SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note\n0 {abi} read sys_read\n1 {abi} unused sys_ni_syscall\n'
                if config['table'] == 'scripts/syscall.tbl':
                    files['arch/{}/kernel/Makefile.syscalls'.format(config['kernel'])] = '# SPDX-License-Identifier: GPL-2.0\nsyscall_abis_64 +=\n'
            for path, text in files.items():
                target = tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            argv = ['sync_kernel.py', '--refs', 'v7.3', '--kernel-tree', str(tree), '--output', str(output)]
            with patch.object(sync.sys, 'argv', argv):
                self.assertEqual(sync.main(), 0)
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(manifest['versions'], ['v7.3'])
            self.assertEqual(manifest['version_architectures']['v7.3'], list(sync.ARCHES))
            data = json.loads((output / 'v7.3/x64.json').read_text())
            self.assertEqual(data['provenance']['kind'], 'local')
            self.assertEqual(data['license'], 'GPL-2.0-only')
            for path, text in files.items():
                self.assertEqual((output / 'v7.3/sources' / path).read_text(), text)
            self.assertEqual(data['syscalls'][1]['status'], 'unimplemented')
            self.assertIsNone(data['syscalls'][1]['arguments'])
            with self.assertRaises(ValueError):
                sync.generate('v6.12', tree, output)

            old_manifest = (output / 'manifest.json').read_bytes()
            old_sources = (output / 'v7.3/sources.json').read_bytes()
            old_table = (output / 'v7.3/x64.json').read_bytes()
            header = tree / 'include/linux/syscalls.h'
            header.write_text(header.read_text().replace('long sys_read', 'ssize_t sys_read'))
            write_json = sync.atomic_json

            for failed_file in ['x64.json', 'manifest.json']:
                def fail_write(path, value):
                    if path.name == failed_file:
                        raise OSError('simulated failure writing ' + failed_file)
                    write_json(path, value)

                with self.subTest(failed_file=failed_file), patch.object(sync.sys, 'argv', argv), patch.object(sync, 'atomic_json', fail_write):
                    self.assertEqual(sync.main(), 1)
                    self.assertEqual((output / 'manifest.json').read_bytes(), old_manifest)
                    self.assertEqual((output / 'v7.3/sources.json').read_bytes(), old_sources)
                    self.assertEqual((output / 'v7.3/x64.json').read_bytes(), old_table)
                    self.assertFalse(list(output.glob('revisions/v7.3/*')))

            with patch.object(sync.sys, 'argv', argv):
                self.assertEqual(sync.main(), 0)
            revised = json.loads((output / 'manifest.json').read_text())
            folder = output / revised['version_paths']['v7.3']
            active = json.loads((folder / 'x64.json').read_text())
            self.assertIn('ssize_t sys_read(', active['syscalls'][0]['declaration'])
            # data/<release>/ follows the active revision; it is not a stale copy.
            self.assertNotEqual((output / 'v7.3/x64.json').read_bytes(), old_table)
            self.assertEqual(tree_digest(output / 'v7.3'), tree_digest(folder))
            self.assertFalse(list(output.glob('.tmp-*')))

    def test_batch_failure_does_not_publish_a_successful_release(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            good = 'v2.6.12'
            broken = 'v2.6.16'
            argv = ['sync_kernel.py', '--refs', good, broken, '--output', directory]

            def generate(ref, tree, staged):
                if ref == broken:
                    raise OSError('simulated source failure')
                shutil.copytree(sync.ROOT / 'public' / 'data' / ref, staged / ref)

            with patch.object(sync.sys, 'argv', argv), patch.object(sync, 'generate', generate):
                self.assertEqual(sync.main(), 1)
            self.assertEqual(list(output.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
