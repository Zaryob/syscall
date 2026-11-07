#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate syscall snapshots from upstream Linux or a local source tree.

No third-party packages, kernel compilation, or host headers are needed.
"""
import argparse
import ast
import concurrent.futures
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
MANUAL_CATALOG = json.loads((ROOT / 'sources/manual-pages.json').read_text())
MANUAL_PAGES = {section: set(names) for section, names in MANUAL_CATALOG['sections'].items()}
LICENSE_FILES = ("COPYING", "LICENSES/preferred/GPL-2.0", "LICENSES/exceptions/Linux-syscall-note")
ARCHES = {
    "x64": dict(label="x86-64", bits=64, kernel="x86", table="arch/x86/entry/syscalls/syscall_64.tbl", abis=["common", "64"], instruction="syscall", nr="rax", result="rax", registers=["rdi", "rsi", "rdx", "r10", "r8", "r9"]),
    "x86": dict(label="i386", bits=32, kernel="x86", table="arch/x86/entry/syscalls/syscall_32.tbl", abis=["i386"], instruction="int 0x80", nr="eax", result="eax", registers=["ebx", "ecx", "edx", "esi", "edi", "ebp"]),
    "arm64": dict(label="AArch64", bits=64, kernel="arm64", table="scripts/syscall.tbl", abis=["common", "64"], instruction="svc #0", nr="x8", result="x0", registers=["x0", "x1", "x2", "x3", "x4", "x5"]),
    "arm": dict(label="ARM EABI", bits=32, kernel="arm", table="arch/arm/tools/syscall.tbl", abis=["common", "eabi"], instruction="svc #0", nr="r7", result="r0", registers=["r0", "r1", "r2", "r3", "r4", "r5"]),
    "riscv64": dict(label="RISC-V 64", bits=64, kernel="riscv", table="scripts/syscall.tbl", abis=["common", "64"], instruction="ecall", nr="a7", result="a0", registers=["a0", "a1", "a2", "a3", "a4", "a5"]),
    "loongarch64": dict(label="LoongArch 64", bits=64, kernel="loongarch", table="scripts/syscall.tbl", abis=["common", "64"], instruction="syscall 0", nr="a7", result="a0", registers=["a0", "a1", "a2", "a3", "a4", "a5"]),
    "ppc64": dict(label="PowerPC 64", bits=64, kernel="powerpc", table="arch/powerpc/kernel/syscalls/syscall.tbl", abis=["common", "nospu", "64"], instruction="sc", nr="r0", result="r3", registers=["r3", "r4", "r5", "r6", "r7", "r8"], error_flag="cr0.SO"),
    "ppc": dict(label="PowerPC 32", bits=32, kernel="powerpc", table="arch/powerpc/kernel/syscalls/syscall.tbl", abis=["common", "nospu", "32"], instruction="sc", nr="r0", result="r3", registers=["r3", "r4", "r5", "r6", "r7", "r8"], error_flag="cr0.SO"),
    "s390x": dict(label="IBM Z (s390x)", bits=64, kernel="s390", table="arch/s390/kernel/syscalls/syscall.tbl", abis=["common", "64"], instruction="svc 0", nr="r1", result="r2", registers=["r2", "r3", "r4", "r5", "r6", "r7"]),
    "mips-o32": dict(label="MIPS o32", bits=32, kernel="mips", table="arch/mips/kernel/syscalls/syscall_o32.tbl", abis=["o32"], instruction="syscall", nr="v0", result="v0", registers=["a0", "a1", "a2", "a3"], stack_slots=[5, 6], error_flag="a3"),
    "mips-n32": dict(label="MIPS n32", bits=32, kernel="mips", table="arch/mips/kernel/syscalls/syscall_n32.tbl", abis=["n32"], instruction="syscall", nr="v0", result="v0", registers=["a0", "a1", "a2", "a3", "a4", "a5"], error_flag="a3"),
    "mips-n64": dict(label="MIPS n64", bits=64, kernel="mips", table="arch/mips/kernel/syscalls/syscall_n64.tbl", abis=["n64", "common"], instruction="syscall", nr="v0", result="v0", registers=["a0", "a1", "a2", "a3", "a4", "a5"], error_flag="a3"),
}
# Import floor for the additional ABI tables; not the ABI's debut in Linux.
EXTENDED_TABLES_FROM = (5, 19)
MIPS_HEADER = "arch/mips/include/uapi/asm/unistd.h"
MIPS_SIM = {"o32": "_MIPS_SIM_ABI32", "n32": "_MIPS_SIM_NABI32", "n64": "_MIPS_SIM_ABI64"}

# Mainline releases: in 2.6.x the third component was the mainline release;
# since 3.0 the third component denotes maintenance/patch releases instead.
def version_key(ref):
    return tuple(map(int, ref.removeprefix("v").split(".")))


def is_mainline(ref):
    return bool(re.fullmatch(r"v(?:1\.0|2\.6\.\d+|[3-9]\d*\.\d+)", ref))


def mainline_refs():
    proc = subprocess.run(["git", "ls-remote", "--tags", "https://github.com/torvalds/linux.git"], capture_output=True, text=True, check=True, timeout=180)
    refs = {line.split("refs/tags/", 1)[1].removesuffix("^{}") for line in proc.stdout.splitlines() if "refs/tags/" in line}
    return sorted({r for r in refs if is_mainline(r)} | {"v1.0"} | {"v2.6." + str(i) for i in range(12)}, key=version_key)


LEGACY_PATHS = {
    "Makefile", "include/linux/syscalls.h", "include/linux/compat.h", "include/linux/sys.h",
    "include/linux/unistd.h", "include/unistd.h", "include/asm/unistd.h",
    "include/asm-i386/unistd.h", "include/asm-x86_64/unistd.h", "include/asm-arm/unistd.h",
    "include/asm-x86/unistd_32.h", "include/asm-x86/unistd_64.h",
    "arch/x86/include/asm/unistd_32.h", "arch/x86/include/asm/unistd_64.h",
    "arch/x86/include/asm/unistd.h", "arch/x86/include/asm/syscalls.h",
    "arch/x86/kernel/syscall_table_32.S", "arch/x86/kernel/syscall_table_64.S",
    "arch/i386/kernel/syscall_table.S", "arch/i386/kernel/entry.S", "arch/i386/kernel/sys_call.S",
    "kernel/sys_call.S", "kernel/entry.S", "arch/arm/kernel/calls.S",
    "kernel/sched.c", "arch/riscv/include/uapi/asm/syscalls.h", "arch/riscv/include/uapi/asm/Kbuild",
    "arch/arm/include/asm/unistd.h", "arch/arm/include/asm/syscalls.h",
    "arch/arm64/include/asm/unistd.h", "arch/arm64/include/uapi/asm/unistd.h",
    "arch/arm64/include/asm/syscalls.h", "include/asm-generic/unistd.h",
    "include/uapi/asm-generic/unistd.h", "arch/arm/include/uapi/asm/unistd.h",
    "arch/x86/syscalls/syscall_32.tbl", "arch/x86/syscalls/syscall_64.tbl",
    "arch/x86/entry/syscalls/syscall_32.tbl", "arch/x86/entry/syscalls/syscall_64.tbl",
    "arch/arm/tools/syscall.tbl", "arch/riscv/include/asm/unistd.h",
    "arch/riscv/include/uapi/asm/unistd.h", "arch/riscv/include/asm/syscalls.h",
    "arch/loongarch/include/asm/unistd.h", "arch/loongarch/include/uapi/asm/unistd.h",
    "arch/loongarch/include/asm/syscalls.h",
}


def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".tmp-", dir=path.parent, delete=False) as f:
        temporary = Path(f.name)
        try:
            f.write(data)
            f.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def atomic_text(path, text):
    atomic_bytes(path, text.encode("utf-8"))


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def source_licenses(files, ref=None):
    """Keep upstream identifiers verbatim; do not apply a blanket UAPI exception."""
    records = []
    for path, info in sorted(files.items()):
        record = {"path": path, "sha256": info["sha256"], "bundled_path": "sources/" + path}
        if path in LICENSE_FILES:
            record["role"] = "license-notice"
        else:
            match = re.search(r"SPDX-License-Identifier:\s*([^\n]+)", info["text"])
            if match:
                record["spdx_license_identifier"] = match[1].split("*/")[0].strip()
            elif path == "arch/arm64/tools/syscall_64.tbl" and info["text"].strip() == "../../../scripts/syscall.tbl":
                # GitHub raw represents a symlink as its target path. Preserve it.
                target = files["scripts/syscall.tbl"]["text"]
                match = re.search(r"SPDX-License-Identifier:\s*([^\n]+)", target)
                if not match:
                    raise ValueError("Missing license identifier for scripts/syscall.tbl")
                record.update(spdx_license_identifier=match[1].split("*/")[0].strip(), symlink_target="scripts/syscall.tbl")
            elif ref and (version_key(ref) < (6, 12) and path in LEGACY_PATHS) and "COPYING" in files and any(p in files["COPYING"]["text"] for p in ["GNU GENERAL PUBLIC LICENSE", "GNU General Public License", "GPL-2.0"]):
                # Reviewed historical kernel inputs predate SPDX conversion. The
                # original file and release COPYING are retained without edits.
                record.update(license_identifier="GPL-2.0-only", license_basis="COPYING", license_note="Historical kernel input without an SPDX identifier; see the original notices and release COPYING.")
            else:
                raise ValueError("Missing SPDX license identifier in {}; review the source license before importing".format(path))
            allowed = {
                "GPL-2.0", "GPL-2.0-only", "GPL-2.0+", "GPL-2.0-or-later",
                "GPL-2.0 WITH Linux-syscall-note", "GPL-2.0-only WITH Linux-syscall-note",
                "GPL-2.0+ WITH Linux-syscall-note", "GPL-2.0-or-later WITH Linux-syscall-note",
            }
            license_str = record.get("spdx_license_identifier") or record.get("license_identifier")
            if license_str not in allowed:
                raise ValueError("Unreviewed source license in {}: {}".format(path, license_str))
        records.append(record)
    return records


class Source:
    def __init__(self, ref, tree=None):
        self.ref = ref
        self.tree = Path(tree).resolve() if tree else None
        self.files = {}
        self.missing = set()
        self.archive_url = None

    def archive(self):
        """Cache only allowlisted inputs from pre-Git kernel.org archives."""
        family = ".".join(self.ref[1:].split(".")[:2])
        self.archive_url = "https://www.kernel.org/pub/linux/kernel/v{}/linux-{}.tar.xz".format(family, self.ref[1:])
        cache = ROOT / ".cache" / self.ref
        if (cache / ".archive-complete").is_file():
            return
        archive_path = ROOT / ".cache" / ("linux-" + self.ref[1:] + ".tar.xz")
        if not archive_path.exists():
            with urllib.request.urlopen(self.archive_url, timeout=120) as response:
                data = response.read()
            atomic_bytes(archive_path, data)
        with tarfile.open(archive_path) as archive:
            for member in archive:
                path = member.name.partition("/")[2]
                if member.isfile() and path in LEGACY_PATHS | {"COPYING"}:
                    target = cache / path
                    atomic_bytes(target, archive.extractfile(member).read())
        atomic_text(cache / ".archive-complete", self.archive_url)

    def read(self, path, optional=False):
        if optional and path in self.missing:
            return ""
        if path in self.files:
            return self.files[path]["text"]
        try:
            if self.tree:
                target = (self.tree / path).resolve()
                if not target.is_relative_to(self.tree):
                    raise ValueError("Source path escapes kernel tree")
                text = target.read_bytes().decode("utf-8")
            else:
                cache = ROOT / ".cache" / self.ref / path
                if version_key(self.ref) < (2, 6, 12):
                    self.archive()
                    if not cache.exists():
                        raise FileNotFoundError(path)
                if cache.exists():
                    text = cache.read_bytes().decode("utf-8")
                else:
                    url = "https://raw.githubusercontent.com/torvalds/linux/{}/{}".format(self.ref, path)
                    for attempt in range(3):
                        try:
                            request = urllib.request.Request(url, headers={"User-Agent": "syscall-reference/1.0"})
                            text = urllib.request.urlopen(request, timeout=45).read().decode()
                            break
                        except urllib.error.HTTPError as e:
                            if e.code == 429:
                                mirror = "https://cdn.jsdelivr.net/gh/torvalds/linux@{}/{}".format(self.ref, path)
                                try:
                                    text = urllib.request.urlopen(mirror, timeout=45).read().decode()
                                    break
                                except urllib.error.HTTPError as mirror_error:
                                    if mirror_error.code == 404:
                                        raise
                            if e.code == 404 or attempt == 2:
                                raise
                            time.sleep(attempt + 1)
                        except (urllib.error.URLError, TimeoutError):
                            if attempt == 2:
                                raise
                            time.sleep(attempt + 1)
                    atomic_text(cache, text)
        except (FileNotFoundError, urllib.error.HTTPError) as e:
            if optional and (isinstance(e, FileNotFoundError) or e.code == 404):
                self.missing.add(path)
                return ""
            raise
        self.files[path] = {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        return text


def strip_comments(text):
    # Preserve token boundaries and source offsets, including newlines.
    pattern = r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|/\*.*?\*/|//[^\n]*"""
    return re.sub(pattern, lambda m: m[0] if m[1] else re.sub(r"[^\n]", " ", m[0]), text, flags=re.S)


def split_c_arguments(body):
    if not body.strip():
        return []
    depth = 0
    start = 0
    arguments = []
    for index, char in enumerate(body):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            arguments.append(body[start:index].strip())
            start = index + 1
    return [*arguments, body[start:].strip()]


def parse_prototypes(text, path):
    result = {}
    clean = strip_comments(text)
    pattern = r"^[ \t]*(?:asmlinkage\s+)?(?:[A-Z_]+\s+)?(?:(?:unsigned\s+)?(?:long|int|short|char)|void|ssize_t|off_t|caddr_t|clock_t|pid_t|\w+_t)\s+((?:compat_)?sys_\w+)\s*\(([^;{}]*?)\)\s*;"
    for m in re.finditer(pattern, clean, re.S | re.M):
        body = re.sub(r"\s+", " ", m[2]).strip()
        args = [] if body == "void" else split_c_arguments(body)
        declaration = re.sub(r"\s+", " ", clean[m.start():m.start(2)]).strip()
        declaration += (", ".join(args) if args else body) + ");"
        # Headers contain CONFIG_* alternatives (notably clone argument order).
        # Without a kernel configuration, conflicting declarations are ambiguous.
        if m[1] in result and result[m[1]]["declaration"] != declaration:
            result[m[1]]["arguments"] = None
            result[m[1]]["declaration"] = None
            result[m[1]]["note"] = "Multiple configuration-dependent declarations exist; consult the kernel source for this ABI."
            continue
        result[m[1]] = {"arguments": args, "declaration": declaration, "path": path, "line": clean[:m.start()].count("\n") + 1}
    return result


def mmap_prototype(text, path):
    clean = strip_comments(text)
    matches = list(re.finditer(r"^\s*SYSCALL_DEFINE6\(mmap\s*,([^()]*)\)\s*\{", clean, re.M))
    if len(matches) != 1:
        return {}
    match = matches[0]
    parts = split_c_arguments(re.sub(r"\s+", " ", match[1]))
    if len(parts) != 12 or not all(parts):
        raise ValueError("Unsupported x86-64 mmap definition in " + path)
    args = ["{} {}".format(kind, name) for kind, name in zip(parts[::2], parts[1::2])]
    return {"sys_mmap": {
        "arguments": args, "declaration": "asmlinkage long sys_mmap({});".format(", ".join(args)),
        "path": path, "line": clean[:match.start(1)].count("\n") + 1, "kind": "syscall_macro",
    }}


def parse_table(text, abis, offset=0, secondary_entry="compat_entry"):
    rows = []
    for line, raw in enumerate(text.splitlines(), 1):
        fields = raw.split("#", 1)[0].split()
        if not fields:
            continue
        if (not 3 <= len(fields) <= 6 or not re.fullmatch(r"[0-9]+", fields[0])
                or not all(re.fullmatch(r"\w+", field) for field in fields[1:3])
                or not all(re.fullmatch(r"-|[A-Za-z_]\w*(?:/ptregs)?", field) for field in fields[3:5])
                or (len(fields) == 6 and fields[5] != "noreturn")):
            raise ValueError("Invalid syscall table row at line {}: {}".format(line, raw.strip()))
        number, abi, name, *entries = fields
        if abi not in abis:
            continue
        entry = entries[0] if entries and entries[0] != "-" else None
        row = dict(number=offset + int(number), abi=abi, name=name, entry=entry, line=line)
        if len(entries) >= 2:
            row[secondary_entry] = None if entries[1] == "-" else entries[1]
        if len(entries) == 3:
            row["noreturn"] = True
        rows.append(row)
    numbers = [r["number"] for r in rows]
    if len(numbers) != len(set(numbers)):
        raise ValueError("Overlapping ABI entries in syscall table")
    if not rows:
        raise ValueError("No syscalls found; unsupported kernel table format")
    return sorted(rows, key=lambda r: r["number"])


def mips_offset(header, abi):
    condition = r"^\s*#if\s+_MIPS_SIM\s*==\s*" + MIPS_SIM[abi] + r"\s*$"
    block = re.search(condition + r"(.*?)^\s*#endif\b", header, re.M | re.S)
    base = re.search(r"^\s*#define\s+__NR_Linux\s+(\d+)\s*$", block[1], re.M) if block else None
    if not base or f"<asm/unistd_{abi}.h>" not in block[1]:
        raise ValueError("Unrecognized MIPS syscall numbering for " + abi)
    return int(base[1])


def extra_abis(makefile):
    values = []
    for line in makefile.splitlines():
        m = re.match(r"\s*syscall_abis_64\s*\+=\s*(.*?)\s*(?:#.*)?$", line)
        if m:
            values.extend(m[1].replace(",", " ").split())
    if any("$" in v for v in values):
        raise ValueError("Unsupported dynamic ABI configuration")
    return values


def integer_expression(expression, macros=None, depth=0):
    """Evaluate only integer arithmetic emitted by the C preprocessor."""
    if depth > 20:
        raise ValueError("Recursive syscall number definition")
    macros = macros or {}
    expression = re.sub(r"\b(0x[\da-fA-F]+|\d+)[uUlL]+\b", r"\1", expression)
    operations = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
                  ast.Mult: lambda a, b: a * b, ast.LShift: lambda a, b: a << b,
                  ast.RShift: lambda a, b: a >> b, ast.BitOr: lambda a, b: a | b,
                  ast.BitAnd: lambda a, b: a & b}
    def evaluate(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.Name) and node.id in macros:
            return integer_expression(macros[node.id], macros, depth + 1)
        if isinstance(node, ast.BinOp) and type(node.op) in operations:
            return operations[type(node.op)](evaluate(node.left), evaluate(node.right))
        raise ValueError("Unsupported syscall number expression: " + expression)
    return evaluate(ast.parse(expression.strip(), mode="eval").body)


def preprocess(source, path, arch, extra=""):
    """Use target ABI defines, never the host's headers or predefined macros."""
    compiler = shutil.which("clang") or shutil.which("gcc") or shutil.which("cc")
    if not compiler:
        raise ValueError("Historical header imports require clang or gcc for C preprocessing")
    kernel = ARCHES[arch]["kernel"]
    def expand(path, stack=()):
        if path in stack:
            raise ValueError("Recursive unistd include: " + path)
        text = source.read(path)
        lines = []
        for line, raw in enumerate(text.splitlines(), 1):
            match = re.match(r'\s*#\s*include\s*[<"]([^>"]+)[>"]', raw)
            if match:
                include = match[1]
                target = None
                if include == "asm-generic/unistd.h":
                    target = "include/" + ("uapi/" if version_key(source.ref) >= (3, 7) else "") + include
                elif include in {"uapi/asm/unistd.h", "asm/unistd.h"}:
                    target = "arch/{}/include/uapi/asm/unistd.h".format(kernel)
                    if arch == "riscv64" and not source.read(target, optional=True):
                        kbuild = source.read("arch/riscv/include/uapi/asm/Kbuild")
                        if not re.search(r"generic-y\s*\+=\s*unistd.h", kbuild):
                            raise ValueError("RISC-V generic unistd mapping not found")
                        target = "include/uapi/asm-generic/unistd.h"
                elif include == "linux/sys.h" and path == "kernel/sched.c":
                    target = "include/linux/sys.h"
                elif include == "uapi/asm/syscalls.h":
                    target = "arch/{}/include/uapi/asm/syscalls.h".format(kernel)
                elif "unistd" in include:
                    raise ValueError("Unsupported syscall include: " + include)
                # Type/linkage/bitsperlong headers do not supply syscall rows.
                raw = expand(target, stack + (path,)) + '\n#line {} "{}"'.format(line + 1, path) if target else ""
            lines.append(raw)
        return '#line 1 "{}"\n'.format(path) + "\n".join(lines) + "\n"
    defines = "#define __BITS_PER_LONG {}\n#define __SYSCALL(n, s, ...) SYSCALL_ROW(n, #n, s, __LINE__, __FILE__)\n".format(ARCHES[arch]["bits"])
    if arch == "arm":
        defines += "#define __ARM_EABI__ 1\n#define CONFIG_AEABI 1\n#define __KERNEL__ 1\n#define OBSOLETE(x) sys_ni_syscall\n#define ABI(eabi, oabi) eabi\n"
    if ARCHES[arch]["bits"] == 64:
        defines += "#define __LP64__ 1\n#define CONFIG_64BIT 1\n"
    if arch == "riscv64":
        defines += "#define __riscv_xlen 64\n"
    proc = subprocess.run([compiler, "-E", "-dD", "-undef", "-nostdinc", "-x", "c", "-"], input=defines + extra + expand(path), capture_output=True, text=True)
    if proc.returncode:
        raise ValueError("Cannot preprocess {}: {}".format(path, proc.stderr))
    return proc.stdout


def header_rows(source, path, arch, assembly=None):
    processed = preprocess(source, path, arch)
    macros = dict(re.findall(r"^#define\s+(__NR\w*)\s+(.+)$", processed, re.M))
    names = {}
    ignored = {"__NR_syscalls", "__NR_syscall_max", "__NR_arch_specific_syscall", "__NR_SYSCALL_BASE", "__NR_OABI_SYSCALL_BASE", "__NR_SYSCALL_MASK"}
    for name in macros:
        if name in ignored or not name.startswith("__NR_"):
            continue
        number = integer_expression(macros[name], macros)
        if 0 <= number < 4096:
            names[number] = name[5:]
    rows = []
    for match in re.finditer(r'SYSCALL_ROW\(([^,]+),\s*"([^"]+)",\s*(\w+),\s*(\d+),\s*"([^"]+)"\)', processed):
        number = integer_expression(match[1])
        # Use the macro named in the table row. Some generic headers expand it
        # in an intermediate macro, so retain number lookup as a fallback.
        macro = re.fullmatch(r"__NR(?:3264)?_(\w+)", match[2])
        name = macro[1] if macro else names.get(number)
        if name is None:
            raise ValueError("No syscall name for {} in {}".format(number, path))
        rows.append(dict(number=number, abi=arch, name=name, entry=match[3], line=int(match[4]), path=match[5]))
    if assembly:
        table = source.read(assembly)
        if arch == "arm":
            table = preprocess(source, assembly, arch, "#define CALL(x) ARM_ROW(x, __LINE__)\n")
            entries = [(m[1], int(m[2])) for m in re.finditer(r"ARM_ROW\((\w+),\s*(\d+)\)", table)]
        elif assembly == "kernel/sched.c":
            pattern = r"sys_call_table\[\]\s*=\s*\{([^}]+)\}"
            clean = strip_comments(table)
            original = re.search(pattern, clean)
            processed_table = re.search(pattern, preprocess(source, assembly, arch))
            if not original or not processed_table:
                raise ValueError("Historical C syscall table not found")
            symbols = re.findall(r"\w+", processed_table[1])
            positions = list(re.finditer(r"\w+", original[1]))
            if len(symbols) != len(positions):
                raise ValueError("Preprocessed historical C table does not match source slots")
            entries = [
                (symbol, clean.count("\n", 0, original.start(1) + position.start()) + 1)
                for symbol, position in zip(symbols, positions)
            ]
        else:
            # Embedded old entry.S files contain other vectors before this label.
            clean = strip_comments(table)
            start = re.search(r"(?:ENTRY\(sys_call_table\)|^sys_call_table:|^_sys_call_table:)", clean, re.M)
            start_pos = start.end() if start else 0
            entries = []
            for m in re.finditer(r"^[ \t]*\.long[ \t]+([^\n]+)", clean[start_pos:], re.M):
                for symbol in m[1].split(","):
                    symbol = symbol.strip().removeprefix("_")
                    if not re.fullmatch(r"[A-Za-z_]\w*", symbol):
                        raise ValueError("Unrecognized assembly syscall entry: " + symbol)
                    entries.append((symbol, clean[:start_pos + m.start()].count("\n") + 1))
        for number, name in sorted(names.items()):
            if number >= len(entries):
                raise ValueError("Syscall {} exceeds {} table".format(name, assembly))
            symbol, line = entries[number]
            rows.append(dict(number=number, abi=arch, name=name, entry=symbol, line=line, path=assembly))
    if not rows or len({r["number"] for r in rows}) != len(rows):
        raise ValueError("Empty or overlapping historical syscall table: " + path)
    return sorted(rows, key=lambda r: r["number"])


def architecture_rows(source, arch):
    config = ARCHES[arch]
    version = version_key(source.ref)
    introduced = {"x64": (2, 6, 0), "x86": (1, 0), "arm": (2, 6, 16), "arm64": (3, 7), "riscv64": (4, 15), "loongarch64": (5, 19)}
    if version < introduced.get(arch, EXTENDED_TABLES_FROM):
        return None, None
    if arch in {"arm64", "riscv64", "loongarch64"} and version < (6, 11):
        path = "arch/{}/include/asm/unistd.h".format(config["kernel"])
        return path, header_rows(source, path, arch)
    if arch in {"x64", "x86"} and version < (4, 2):
        path = "arch/x86/syscalls/syscall_{}.tbl".format("64" if arch == "x64" else "32")
        if version >= (3, 3):
            return path, parse_table(source.read(path), config["abis"])
        if arch == "x64":
            path = "arch/x86/include/asm/unistd_64.h" if version >= (2, 6, 27) else "include/asm-x86/unistd_64.h" if version >= (2, 6, 24) else "include/asm-x86_64/unistd.h"
            return path, header_rows(source, path, arch)
        path = "arch/x86/include/asm/unistd_32.h" if version >= (2, 6, 27) else "include/asm-x86/unistd_32.h" if version >= (2, 6, 24) else "include/asm-i386/unistd.h" if version >= (1, 2) else "include/linux/unistd.h"
        assembly = "arch/x86/kernel/syscall_table_32.S" if version >= (2, 6, 24) else "arch/i386/kernel/syscall_table.S" if version >= (2, 6, 12) else "arch/i386/kernel/entry.S" if version >= (1, 2) else "kernel/sched.c"
        return path, header_rows(source, path, arch, assembly)
    if arch == "arm" and version < (4, 10):
        path = "arch/arm/include/uapi/asm/unistd.h" if version >= (3, 7) else "arch/arm/include/asm/unistd.h" if version >= (2, 6, 28) else "include/asm-arm/unistd.h"
        return path, header_rows(source, path, arch, "arch/arm/kernel/calls.S")
    abis = list(config["abis"])
    if config["table"] == "scripts/syscall.tbl":
        abis += extra_abis(source.read("arch/{}/kernel/Makefile.syscalls".format(config["kernel"])))
        if arch == "arm64":
            link = source.read("arch/arm64/tools/syscall_64.tbl").strip()
            if not (link == "../../../scripts/syscall.tbl" or link.startswith("#")):
                raise ValueError("arm64 syscall table layout changed")
    offset = mips_offset(source.read(MIPS_HEADER), abis[0]) if config["kernel"] == "mips" else 0
    secondary_entry = "oabi_entry" if arch == "arm" else "compat_entry"
    return config["table"], parse_table(source.read(config["table"]), abis, offset, secondary_entry)


def manual_url(name):
    """Resolve editorial/time64 aliases only to pages in the checked-in catalog."""
    target = name
    if target.endswith('_time64'):
        target = target[:-7]
    elif target.endswith('time64'):
        target = target[:-2]
    target = MANUAL_CATALOG['aliases'].get(name, MANUAL_CATALOG['aliases'].get(target, target))
    page, _, section = target.partition('.')
    section = section or '2'
    if page not in MANUAL_PAGES.get(section, set()):
        return None
    return f'https://man7.org/linux/man-pages/man{section}/{page}.{section}.html'


def generate(ref, tree, output):
    """Write one release into the staging directory."""
    source = Source(ref, tree)
    makefile = source.read("Makefile")
    version = ".".join(re.search(r"^{}\s*=\s*(\d+)".format(k), makefile, re.M)[1] for k in ["VERSION", "PATCHLEVEL"])
    sublevel_match = re.search(r"^SUBLEVEL\s*=\s*(\d+)", makefile, re.M)
    sublevel = sublevel_match[1] if sublevel_match else "0"
    if sublevel != "0":
        version += "." + sublevel
    if version_key(ref) + (0,) * (3 - len(version_key(ref))) != version_key("v" + version) + (0,) * (3 - len(version_key("v" + version))):
        raise ValueError("Ref {} does not match kernel Makefile version {}".format(ref, version))
    common = {}
    for path in ["include/linux/syscalls.h", "include/linux/compat.h"]:
        common.update(parse_prototypes(source.read(path, optional=version_key(ref) < (2, 6, 0)), path))
    snapshots = {}
    for arch, config in ARCHES.items():
        table_path, rows = architecture_rows(source, arch)
        if rows is None:
            continue
        prototypes = dict(common)
        path = "arch/{}/include/asm/syscalls.h".format(config["kernel"])
        prototypes.update(parse_prototypes(source.read(path, optional=True), path))
        # Early x86-64 headers contain architecture-specific prototypes too.
        if table_path.endswith(".h"):
            prototypes.update(parse_prototypes(source.read(table_path), table_path))
        if arch == "x64" and version_key(ref) >= (5, 19) and "sys_mmap" not in prototypes:
            mmap_path = "arch/x86/kernel/sys_x86_64.c"
            prototypes.update(mmap_prototype(source.read(mmap_path, optional=True), mmap_path))
        for row in rows:
            symbol = row["entry"] or ""
            # Assembly wrappers have no C prototype; do not substitute another ABI.
            prototype = prototypes.get(symbol)
            unavailable = symbol in {"", "-", "sys_ni_syscall", "compat_sys_ni_syscall"}
            row.update(
                status="unimplemented" if unavailable else "defined",
                arguments=prototype["arguments"] if prototype and not unavailable else None,
                declaration=prototype["declaration"] if prototype and not unavailable else None,
                signature_source={k: prototype[k] for k in ["path", "line"]} if prototype and not unavailable else None,
                signature_note=prototype.get("note") if prototype and not unavailable else None,
                source={"path": row.pop("path", table_path), "line": row.pop("line")},
                man_url=manual_url(row["name"]) if not unavailable else None,
            )
            if row["signature_source"] and prototype.get("kind"):
                row["signature_source"]["kind"] = prototype["kind"]
            if not unavailable and row["arguments"] is None:
                if prototype and prototype.get("note"):
                    row["signature_status"] = "configuration_dependent"
                elif symbol.startswith("stub_") or symbol.endswith("/ptregs"):
                    row["signature_status"] = "wrapper_entry"
                else:
                    row["signature_status"] = "not_found"
        snapshots[arch] = {"schema_version": 1, "kernel": ref, "architecture": arch, "calling_convention": {**config, "table": table_path}, "syscalls": rows}
    # Include the exact input source and upstream license texts with every release.
    for path in LICENSE_FILES:
        source.read(path, optional=path != "COPYING" and version_key(ref) < (4, 16))
    # Finish parsing and licensing checks before replacing any data.
    hashes = source_licenses(source.files, ref)
    provenance = {"kind": "local" if tree else "upstream", "repository": "https://github.com/torvalds/linux", "ref": ref, "files": hashes}
    if source.archive_url:
        provenance.update(repository="https://www.kernel.org/pub/linux/kernel/", archive=source.archive_url)
    if tree:
        provenance["local_commit"] = local_kernel_commit(source.tree)
    licensing = {
        "generated_file": "GPL-2.0-only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upstream_notice": "sources/COPYING",
        "upstream_license_texts": ["sources/" + p for p in LICENSE_FILES[1:] if p in source.files],
        "generator": "scripts/sync_kernel.py",
        "modification_notice": "Generated by syscall-reference from Linux " + ref + "; tables and declarations were parsed, filtered by ABI, and converted to JSON. Bundled input files are unchanged; their original licenses, notices and exceptions remain in effect. The Linux-syscall-note is not applied to all application code or all extracted declarations.",
    }
    for path, info in source.files.items():
        atomic_text(output / ref / "sources" / path, info["text"])
    atomic_json(output / ref / "sources.json", {"license": "GPL-2.0-only", "kernel": ref, "architectures": list(snapshots), "licensing": licensing, **provenance})
    for arch, snapshot in snapshots.items():
        snapshot["license"] = "GPL-2.0-only"
        snapshot["licensing"] = licensing
        snapshot["provenance"] = provenance
        atomic_json(output / ref / (arch + ".json"), snapshot)
    print("{}: {}".format(ref, ", ".join("{}={}".format(a, len(s["syscalls"])) for a, s in snapshots.items())), flush=True)


def local_kernel_commit(tree):
    git = shutil.which("git")
    if not git:
        return None
    root = subprocess.run([git, "-C", str(tree), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if root.returncode != 0 or Path(root.stdout.strip()).resolve() != tree:
        return None
    commit = subprocess.run([git, "-C", str(tree), "rev-parse", "HEAD"], capture_output=True, text=True)
    return commit.stdout.strip() if commit.returncode == 0 else None


@contextmanager
def publication_lock(path):
    with path.open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield


def publish_snapshots(output, staged, refs):
    staged_architectures = {}
    for ref in refs:
        folder = staged / ref
        metadata = json.loads((folder / "sources.json").read_text())
        architectures = metadata["architectures"]
        if metadata["kernel"] != ref or not architectures:
            raise ValueError("Invalid staged snapshot: " + ref)
        for arch in architectures:
            table = json.loads((folder / (arch + ".json")).read_text())
            if (table["kernel"], table["architecture"], table["provenance"]["files"]) != (ref, arch, metadata["files"]):
                raise ValueError("Invalid staged table: {}/{}".format(ref, arch))
        for source in metadata["files"]:
            if hashlib.sha256((folder / source["bundled_path"]).read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("Invalid staged source hash: " + source["path"])
        staged_architectures[ref] = architectures

    manifest_path = output / "manifest.json"
    with publication_lock(output / ".sync.lock"):
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        availability = {
            ref: manifest.get("version_architectures", {}).get(ref, list(ARCHES))
            for ref in manifest.get("versions", [])
        }
        paths = manifest.get("version_paths", {})
        published = []
        try:
            for ref in refs:
                target = output / ref
                active = output / paths.get(ref, ref)
                if ref in availability and same_snapshot(staged / ref, active, staged_architectures[ref]):
                    continue
                if target.exists() or ref in availability:
                    # Keep every previously published path readable for clients
                    # that are still using the previous manifest.
                    target = output / "revisions" / ref / uuid4().hex
                    target.parent.mkdir(parents=True, exist_ok=True)
                    paths[ref] = target.relative_to(output).as_posix()
                (staged / ref).rename(target)
                published.append(target)
                availability[ref] = staged_architectures[ref]
            if not published:
                return
            releases = sorted(availability, key=version_key, reverse=True)
            atomic_json(manifest_path, {
                "license": "GPL-2.0-only", "schema_version": 1, "versions": releases, "latest": releases[0],
                "version_architectures": {ref: availability[ref] for ref in releases},
                "version_paths": paths,
                "architectures": [{"id": a, **c} for a, c in ARCHES.items()],
            })
        except Exception:
            for folder in published:
                shutil.rmtree(folder)
            raise


def same_snapshot(staged, active, architectures):
    try:
        for filename in ["sources.json", *(arch + ".json" for arch in architectures)]:
            new = json.loads((staged / filename).read_bytes())
            current = json.loads((active / filename).read_bytes())
            new["licensing"].pop("generated_at", None)
            current["licensing"].pop("generated_at", None)
            if new != current:
                return False
        sources = json.loads((staged / "sources.json").read_bytes())["files"]
        return all(
            hashlib.sha256((active / source["bundled_path"]).read_bytes()).hexdigest() == source["sha256"]
            for source in sources
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--refs", nargs="+", help="Explicit kernel release tags")
    selection.add_argument("--all-mainline", action="store_true", help="Import stable mainline releases since 1.0; exclude release candidates and maintenance releases")
    parser.add_argument("--kernel-tree", type=Path, help="Read one matching release from a local Linux tree, without network")
    parser.add_argument("--output", type=Path, default=ROOT / "public/data")
    args = parser.parse_args()
    args.refs = mainline_refs() if args.all_mainline else args.refs or ["v6.12", "v6.18", "v7.3"]
    if any(not re.fullmatch(r"v\d+\.\d+(?:\.\d+)?", r) for r in args.refs):
        parser.error("Only explicit release tags are supported")
    if args.kernel_tree and len(args.refs) != 1:
        parser.error("--kernel-tree requires exactly one --refs tag matching its Makefile")
    args.output.mkdir(parents=True, exist_ok=True)
    refs = list(dict.fromkeys(args.refs))
    try:
        with tempfile.TemporaryDirectory(prefix=".import-", dir=args.output) as temporary:
            staged = Path(temporary)
            errors = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                future_to_ref = {pool.submit(generate, ref, args.kernel_tree, staged): ref for ref in refs}
                for future in concurrent.futures.as_completed(future_to_ref):
                    try:
                        future.result()
                    except Exception as e:
                        errors += 1
                        print("Error importing {}: {}".format(future_to_ref[future], e), file=sys.stderr)
            if errors:
                print("Kernel import finished with {} failure(s) out of {} target(s).".format(errors, len(refs)), file=sys.stderr)
                return 1
            publish_snapshots(args.output, staged, refs)
    except Exception as e:
        print("Kernel import failed: {}".format(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
