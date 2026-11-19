#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Refresh or validate the system call introduction catalog from Linux man-pages."""
import argparse
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / 'sources/introductions.json'
MANIFEST_PATH = ROOT / 'public/data/manifest.json'
UPSTREAM_URL = 'https://raw.githubusercontent.com/mkerrisk/man-pages/master/man2/syscalls.2'

# Curated additions and notes for calls not yet listed in the upstream man-pages table,
# 64-bit time64 variants, architecture-specific calls, and legacy table slots.
SUPPLEMENT = {
    # 64-bit time_t system calls (Linux 5.1)
    'clock_adjtime64': {'version': '5.1'},
    'clock_getres_time64': {'version': '5.1'},
    'clock_gettime64': {'version': '5.1'},
    'clock_nanosleep_time64': {'version': '5.1'},
    'clock_settime64': {'version': '5.1'},
    'futex_time64': {'version': '5.1'},
    'io_pgetevents_time64': {'version': '5.1'},
    'mq_timedreceive_time64': {'version': '5.1'},
    'mq_timedsend_time64': {'version': '5.1'},
    'ppoll_time64': {'version': '5.1'},
    'pselect6_time64': {'version': '5.1'},
    'recvmmsg_time64': {'version': '5.1'},
    'rt_sigtimedwait_time64': {'version': '5.1'},
    'sched_rr_get_interval_time64': {'version': '5.1'},
    'semtimedop_time64': {'version': '5.1'},
    'timer_gettime64': {'version': '5.1'},
    'timer_settime64': {'version': '5.1'},
    'timerfd_gettime64': {'version': '5.1'},
    'timerfd_settime64': {'version': '5.1'},
    'utimensat_time64': {'version': '5.1'},
    # Recent mainline system calls (Linux 5.12+)
    'mount_setattr': {'version': '5.12'},
    'process_mrelease': {'version': '5.15'},
    'futex_waitv': {'version': '5.16'},
    'set_mempolicy_home_node': {'version': '5.17'},
    'riscv_hwprobe': {'version': '6.4'},
    'cachestat': {'version': '6.5'},
    'fchmodat2': {'version': '6.6'},
    'map_shadow_stack': {'version': '6.6'},
    'futex_wait': {'version': '6.7'},
    'futex_wake': {'version': '6.7'},
    'futex_requeue': {'version': '6.7'},
    'statmount': {'version': '6.8'},
    'listmount': {'version': '6.8'},
    'lsm_get_self_attr': {'version': '6.8'},
    'lsm_set_self_attr': {'version': '6.8'},
    'lsm_list_modules': {'version': '6.8'},
    'mseal': {'version': '6.10'},
    'uretprobe': {'version': '6.11'},
    'setxattrat': {'version': '6.13'},
    'getxattrat': {'version': '6.13'},
    'listxattrat': {'version': '6.13'},
    'removexattrat': {'version': '6.13'},
    'open_tree_attr': {'version': '6.15'},
    'file_getattr': {'version': '6.17'},
    'file_setattr': {'version': '6.17'},
    'uprobe': {'version': '6.18'},
    'listns': {'version': '6.19'},
    'rseq_slice_yield': {'version': '7.0'},
    'fchroot': {'version': '7.3'},
    # Architecture and legacy calls
    'arm_fadvise64_64': {'version': '2.6.14', 'note': 'ARM only', 'note_tr': 'Yalnızca ARM'},
    'arm_sync_file_range': {'version': '2.6.20', 'note': 'ARM only', 'note_tr': 'Yalnızca ARM'},
    'cachectl': {'version': '2.6.0', 'note': 'MIPS only', 'note_tr': 'Yalnızca MIPS'},
    'ftime': {'version': '1.0'},
    'gtty': {'version': '1.0'},
    'idle': {'version': '1.0'},
    'lock': {'version': '1.0'},
    'madvise1': {'version': '2.4.0', 'note': 'i386 sys_madvise slot', 'note_tr': 'i386 sys_madvise yuvası'},
    'mpx': {'version': '1.0'},
    'phys': {'version': '1.0'},
    'prof': {'version': '1.0'},
    'profil': {'version': '1.0'},
    'stty': {'version': '1.0'},
    'sys_kexec_load': {'version': '2.6.13', 'note': 'ARM kexec_load entry', 'note_tr': 'ARM kexec_load girişi'},
    'timerfd': {'version': '2.6.22', 'note': 'Replaced by timerfd_create in 2.6.25', 'note_tr': '2.6.25 sürümünde yerini timerfd_create aldı'},
    'ulimit': {'version': '1.0'},
    'unused59': {'version': '1.0', 'note': 'MIPS olduname entry', 'note_tr': 'MIPS olduname girişi'},
    'unused109': {'version': '1.0', 'note': 'MIPS uname entry', 'note_tr': 'MIPS uname girişi'},
    'break': {'version': '1.0'},
    'pread64': {'version': '2.6', 'note': 'Added as pread in 2.2; renamed pread64 in 2.6', 'note_tr': '2.2 sürümünde pread adıyla eklendi; 2.6 sürümünde pread64 olarak yeniden adlandırıldı'},
    'pwrite64': {'version': '2.6', 'note': 'Added as pwrite in 2.2; renamed pwrite64 in 2.6', 'note_tr': '2.2 sürümünde pwrite adıyla eklendi; 2.6 sürümünde pwrite64 olarak yeniden adlandırıldı'},
    'arch_prctl': {'version': '2.6', 'note': 'x86-64; i386 since 4.12', 'note_tr': 'x86-64; i386 için 4.12 sürümünden beri'},
    # Reserved table slots with historical origins
    'afs_syscall': {'version': '1.0', 'note': 'Reserved slot', 'note_tr': 'Ayrılmış yuva'},
    'epoll_ctl_old': {'version': '2.6.0', 'note': 'Deprecated 2.6.0 epoll ABI', 'note_tr': 'Kullanımdan kaldırılan 2.6.0 epoll ABI’si'},
    'epoll_wait_old': {'version': '2.6.0', 'note': 'Deprecated 2.6.0 epoll ABI', 'note_tr': 'Kullanımdan kaldırılan 2.6.0 epoll ABI’si'},
    'getpmsg': {'version': '2.4.0', 'note': 'Unimplemented STREAMS slot', 'note_tr': 'Gerçeklenmemiş STREAMS yuvası'},
    'multiplexer': {'version': '2.6.0', 'note': 'Unimplemented PowerPC slot', 'note_tr': 'Gerçeklenmemiş PowerPC yuvası'},
    'putpmsg': {'version': '2.4.0', 'note': 'Unimplemented STREAMS slot', 'note_tr': 'Gerçeklenmemiş STREAMS yuvası'},
    'security': {'version': '2.6.0', 'note': 'Unimplemented security slot', 'note_tr': 'Gerçeklenmemiş güvenlik yuvası'},
    'tuxcall': {'version': '2.4.0', 'note': 'Unimplemented TUX slot', 'note_tr': 'Gerçeklenmemiş TUX yuvası'},
    'vserver': {'version': '2.4.0', 'note': 'Unimplemented Linux-VServer slot', 'note_tr': 'Gerçeklenmemiş Linux-VServer yuvası'},
}


def load_bundled_names():
    """Return all unique syscall names defined across any bundled snapshot."""
    manifest = json.loads(MANIFEST_PATH.read_bytes())
    defined_names = set()
    for version in manifest['versions']:
        for arch in manifest['version_architectures'].get(version, []):
            path = ROOT / 'public/data' / version / f'{arch}.json'
            if path.is_file():
                table = json.loads(path.read_bytes())
                for row in table.get('syscalls', []):
                    name = row.get('name')
                    if name and row.get('status') != 'unimplemented':
                        defined_names.add(name)
    return defined_names


def parse_syscalls2(content):
    """Parse the roff table from man2/syscalls.2."""
    entries = {}
    current_entry = None
    in_table = False
    for line in content.splitlines():
        if line.startswith('.TS'):
            in_table = True
            continue
        if line.startswith('.TE'):
            in_table = False
            continue
        if not in_table:
            continue
        m = re.match(r'\\\\f[Bb]([a-zA-Z0-9_]+)\\\\f[Pp](?:\([23]\))?\t+([^\t\n]*)(?:\t+(.*))?', line)
        if m:
            name = m.group(1)
            kernel = m.group(2).strip()
            rest = m.group(3).strip() if m.group(3) else ''
            if rest == 'T{':
                entries[name] = {'kernel': kernel, 'notes': []}
                current_entry = name
            elif kernel == 'T{':
                entries[name] = {'kernel': '', 'notes': []}
                current_entry = name
            else:
                notes = re.sub(r'\\\\f[BIPR](.*?)\\\\f[PR]', r'\1', rest)
                entries[name] = {'kernel': kernel, 'notes': [notes] if notes else []}
                current_entry = None
        elif current_entry:
            if line.strip() == 'T}':
                current_entry = None
            else:
                clean = re.sub(r'\\\\f[BIPR](.*?)\\\\f[PR]', r'\1', line.strip())
                if clean:
                    entries[current_entry]['notes'].append(clean)
    result = {}
    for name, data in entries.items():
        k = data['kernel']
        if ';' in k:
            k = k.split(';')[0].strip()
        if k:
            result[name] = {'version': k}
    return result


def build_catalog():
    with urllib.request.urlopen(UPSTREAM_URL, timeout=15) as response:
        content = response.read().decode('utf-8')
    data = parse_syscalls2(content)
    data.update(SUPPLEMENT)
    return {
        'schema_version': 1,
        'source': UPSTREAM_URL,
        'introductions': dict(sorted(data.items())),
    }


def validate_catalog(catalog, defined_names):
    intros = catalog.get('introductions', {})
    missing = defined_names - set(intros.keys())
    if missing:
        raise ValueError(f'Defined system calls missing introduction records: {sorted(missing)}')
    for name, record in intros.items():
        v = record.get('version')
        if not v or not re.match(r'^\d+\.\d+(?:\.\d+)?$', v):
            raise ValueError(f'Invalid version for {name}: {v!r}')
        if 'note' in record and 'note_tr' not in record:
            raise ValueError(f'Missing Turkish note for {name}')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate existing catalog without updating')
    args = parser.parse_args()

    defined_names = load_bundled_names()

    if args.check:
        if not CATALOG_PATH.is_file():
            raise SystemExit(f'Catalog file {CATALOG_PATH} does not exist.')
        catalog = json.loads(CATALOG_PATH.read_bytes())
        validate_catalog(catalog, defined_names)
        print(f'Introductions catalog valid: {len(catalog["introductions"])} entries cover all defined syscalls.')
        return

    catalog = build_catalog()
    validate_catalog(catalog, defined_names)
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + '\n')
    print(f'Updated {CATALOG_PATH} with {len(catalog["introductions"])} syscall introduction records.')


if __name__ == '__main__':
    main()
