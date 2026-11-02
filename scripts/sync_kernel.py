#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate syscall snapshots from upstream Linux or a local source tree.

No third-party packages, kernel compilation, or host headers are needed.
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LICENSE_FILES = ("COPYING", "LICENSES/preferred/GPL-2.0", "LICENSES/exceptions/Linux-syscall-note")
ARCHES = {
    "x64": dict(label="x86-64", bits=64, kernel="x86", table="arch/x86/entry/syscalls/syscall_64.tbl", abis=["common", "64"], instruction="syscall", nr="rax", result="rax", registers=["rdi", "rsi", "rdx", "r10", "r8", "r9"]),
    "x86": dict(label="i386", bits=32, kernel="x86", table="arch/x86/entry/syscalls/syscall_32.tbl", abis=["i386"], instruction="int 0x80", nr="eax", result="eax", registers=["ebx", "ecx", "edx", "esi", "edi", "ebp"]),
    "arm64": dict(label="AArch64", bits=64, kernel="arm64", table="scripts/syscall.tbl", abis=["common", "64"], instruction="svc #0", nr="x8", result="x0", registers=["x0", "x1", "x2", "x3", "x4", "x5"]),
    "arm": dict(label="ARM EABI", bits=32, kernel="arm", table="arch/arm/tools/syscall.tbl", abis=["common", "eabi"], instruction="svc #0", nr="r7", result="r0", registers=["r0", "r1", "r2", "r3", "r4", "r5"]),
    "riscv64": dict(label="RISC-V 64", bits=64, kernel="riscv", table="scripts/syscall.tbl", abis=["common", "64"], instruction="ecall", nr="a7", result="a0", registers=["a0", "a1", "a2", "a3", "a4", "a5"]),
    "loongarch64": dict(label="LoongArch 64", bits=64, kernel="loongarch", table="scripts/syscall.tbl", abis=["common", "64"], instruction="syscall 0", nr="a7", result="a0", registers=["a0", "a1", "a2", "a3", "a4", "a5"]),
}


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as f:
        f.write(text)
    os.replace(f.name, path)


def atomic_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def source_licenses(files):
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
            else:
                raise ValueError("Missing SPDX license identifier in {}; review the source license before importing".format(path))
            allowed = {"GPL-2.0", "GPL-2.0-only", "GPL-2.0 WITH Linux-syscall-note", "GPL-2.0-only WITH Linux-syscall-note"}
            if record["spdx_license_identifier"] not in allowed:
                raise ValueError("Unreviewed source license in {}: {}".format(path, record["spdx_license_identifier"]))
        records.append(record)
    return records


class Source:
    def __init__(self, ref, tree=None):
        self.ref = ref
        self.tree = Path(tree).resolve() if tree else None
        self.files = {}

    def read(self, path, optional=False):
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
                            if e.code == 404 or attempt == 2:
                                raise
                            time.sleep(attempt + 1)
                        except (urllib.error.URLError, TimeoutError):
                            if attempt == 2:
                                raise
                            time.sleep(attempt + 1)
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(text)
        except (FileNotFoundError, urllib.error.HTTPError) as e:
            if optional and (isinstance(e, FileNotFoundError) or e.code == 404):
                return ""
            raise
        self.files[path] = {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        return text


def strip_comments(text):
    # Preserve newlines so provenance links retain the original line numbers.
    return re.sub(r"/\*.*?\*/|//[^\n]*", lambda m: "\n" * m.group().count("\n"), text, flags=re.S)


def parse_prototypes(text, path):
    result = {}
    clean = strip_comments(text)
    for m in re.finditer(r"asmlinkage\s+(?:long|int|unsigned\s+long)\s+((?:compat_)?sys_\w+)\s*\((.*?)\)\s*;", clean, re.S):
        body = re.sub(r"\s+", " ", m[2]).strip()
        args = [] if body == "void" else [a.strip() for a in body.split(",")]
        # Headers contain CONFIG_* alternatives (notably clone argument order).
        # Without a kernel configuration, conflicting declarations are ambiguous.
        if m[1] in result and result[m[1]]["arguments"] != args:
            result[m[1]]["arguments"] = None
            result[m[1]]["note"] = "Multiple configuration-dependent declarations exist; consult the kernel source for this ABI."
            continue
        result[m[1]] = {"arguments": args, "path": path, "line": clean[:m.start()].count("\n") + 1}
    return result


def parse_table(text, abis):
    rows = []
    for line, raw in enumerate(text.splitlines(), 1):
        fields = raw.split("#", 1)[0].split()
        if len(fields) < 3 or not fields[0].isdigit() or fields[1] not in abis:
            continue
        entry = fields[3] if len(fields) > 3 else None
        rows.append(dict(number=int(fields[0]), abi=fields[1], name=fields[2], entry=entry, line=line))
    numbers = [r["number"] for r in rows]
    if len(numbers) != len(set(numbers)):
        raise ValueError("Overlapping ABI entries in syscall table")
    if not rows:
        raise ValueError("No syscalls found; unsupported kernel table format")
    return sorted(rows, key=lambda r: r["number"])


def extra_abis(makefile):
    values = []
    for line in makefile.splitlines():
        m = re.match(r"\s*syscall_abis_64\s*\+=\s*(.*?)\s*(?:#.*)?$", line)
        if m:
            values.extend(m[1].replace(",", " ").split())
    if any("$" in v for v in values):
        raise ValueError("Unsupported dynamic ABI configuration")
    return values


def generate(ref, tree, output):
    source = Source(ref, tree)
    makefile = source.read("Makefile")
    version = ".".join(re.search(r"^{}\s*=\s*(\d+)".format(k), makefile, re.M)[1] for k in ["VERSION", "PATCHLEVEL"])
    sublevel = re.search(r"^SUBLEVEL\s*=\s*(\d+)", makefile, re.M)[1]
    if sublevel != "0":
        version += "." + sublevel
    if ref != "v" + version:
        raise ValueError("Ref {} does not match kernel Makefile version {}".format(ref, version))
    common = {}
    for path in ["include/linux/syscalls.h", "include/linux/compat.h"]:
        common.update(parse_prototypes(source.read(path), path))
    snapshots = {}
    for arch, config in ARCHES.items():
        prototypes = dict(common)
        path = "arch/{}/include/asm/syscalls.h".format(config["kernel"])
        prototypes.update(parse_prototypes(source.read(path, optional=True), path))
        abis = list(config["abis"])
        if config["table"] == "scripts/syscall.tbl":
            abis += extra_abis(source.read("arch/{}/kernel/Makefile.syscalls".format(config["kernel"])))
            # Fail on upstream format changes instead of silently using the wrong table.
            if arch == "arm64":
                link = source.read("arch/arm64/tools/syscall_64.tbl").strip()
                if not (link == "../../../scripts/syscall.tbl" or link.startswith("#")):
                    raise ValueError("arm64 syscall table layout changed")
        rows = parse_table(source.read(config["table"]), abis)
        for row in rows:
            symbol = row["entry"] or ""
            # Assembly wrappers have no C prototype; do not substitute another ABI.
            prototype = prototypes.get(symbol)
            unavailable = not symbol or symbol == "sys_ni_syscall"
            row.update(
                status="unimplemented" if unavailable else "defined",
                arguments=prototype["arguments"] if prototype and not unavailable else None,
                signature_source={k: prototype[k] for k in ["path", "line"]} if prototype and not unavailable else None,
                signature_note=prototype.get("note") if prototype and not unavailable else None,
                source={"path": config["table"], "line": row.pop("line")},
                man_url="https://man7.org/linux/man-pages/man2/{}.2.html".format(row["name"]),
            )
        snapshots[arch] = {"schema_version": 1, "kernel": ref, "architecture": arch, "calling_convention": config, "syscalls": rows}
    # Include the exact input source and upstream license texts with every release.
    for path in LICENSE_FILES:
        source.read(path)
    # Finish parsing and licensing checks before replacing any data.
    hashes = source_licenses(source.files)
    provenance = {"kind": "local" if tree else "upstream", "repository": "https://github.com/torvalds/linux", "ref": ref, "files": hashes}
    if tree:
        proc = subprocess.run(["git", "-C", str(source.tree), "rev-parse", "HEAD"], capture_output=True, text=True)
        provenance["local_commit"] = proc.stdout.strip() if proc.returncode == 0 else None
    licensing = {
        "generated_file": "GPL-2.0-only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upstream_notice": "sources/COPYING",
        "upstream_license_texts": ["sources/" + p for p in LICENSE_FILES[1:]],
        "generator": "scripts/sync_kernel.py",
        "modification_notice": "Generated by syscall-reference from Linux " + ref + "; tables and declarations were parsed, filtered by ABI, and converted to JSON. Bundled input files are unchanged; their original licenses, notices and exceptions remain in effect. The Linux-syscall-note is not applied to all application code or all extracted declarations.",
    }
    for path, info in source.files.items():
        atomic_text(output / ref / "sources" / path, info["text"])
    atomic_json(output / ref / "sources.json", {"license": "GPL-2.0-only", "kernel": ref, "licensing": licensing, **provenance})
    for arch, snapshot in snapshots.items():
        snapshot["license"] = "GPL-2.0-only"
        snapshot["licensing"] = licensing
        snapshot["provenance"] = provenance
        atomic_json(output / ref / (arch + ".json"), snapshot)
    print("{}: {}".format(ref, ", ".join("{}={}".format(a, len(s["syscalls"])) for a, s in snapshots.items())), flush=True)


def update_manifest(output):
    releases = []
    for folder in output.iterdir():
        if folder.is_dir() and re.fullmatch(r"v\d+\.\d+(?:\.\d+)?", folder.name):
            if all((folder / (a + ".json")).is_file() for a in ARCHES):
                releases.append(folder.name)
    releases.sort(key=lambda v: tuple(map(int, v[1:].split("."))), reverse=True)
    atomic_json(output / "manifest.json", {"license": "GPL-2.0-only", "schema_version": 1, "versions": releases, "latest": releases[0], "architectures": [{"id": a, **c} for a, c in ARCHES.items()]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refs", nargs="+", default=["v6.12", "v6.18", "v7.3"], help="Kernel release tags (v6.12 or newer)")
    parser.add_argument("--kernel-tree", type=Path, help="Read one matching release from a local Linux tree, without network")
    parser.add_argument("--output", type=Path, default=ROOT / "public/data")
    args = parser.parse_args()
    if any(not re.fullmatch(r"v\d+\.\d+(?:\.\d+)?", r) for r in args.refs):
        parser.error("Only explicit release tags are supported")
    if args.kernel_tree and len(args.refs) != 1:
        parser.error("--kernel-tree requires exactly one --refs tag matching its Makefile")
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda ref: generate(ref, args.kernel_tree, args.output), args.refs))
        update_manifest(args.output)
    except Exception as e:
        print("Kernel import failed: {}".format(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
