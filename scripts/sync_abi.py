#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate the errno, signal and ioctl reference from Linux UAPI headers.

Every number and name is read from the kernel sources of one release tag.
Individual files are fetched (or read from a local tree) exactly as
sync_kernel.py does; no kernel build, archive or host header is used.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_kernel as sk  # noqa: E402

ROOT = sk.ROOT
OUTPUT = ROOT / "public/data/abi"
GENERATOR = "scripts/sync_abi.py"
GENERIC = "include/uapi/asm-generic/"
GENERIC_KBUILD = GENERIC + "Kbuild"
SIGNAL_ACTIONS = "include/linux/signal.h"
IOCTL_REGISTRY = "Documentation/userspace-api/ioctl/ioctl-number.rst"
TYPE_SIZES = GENERIC + "int-ll64.h"
# <asm/...> headers this reference follows; any other <asm/...> include is skipped.
ASM_HEADERS = {"errno.h", "signal.h", "ioctl.h", "ioctls.h", "sockios.h"}
LINUX_HEADERS = {"linux/ioctl.h", "linux/sockios.h"}
# Compiler macros that state which ABI is being compiled. They identify the
# ABI (as KCONFIG_FACTS does in sync_kernel.py); they carry no number.
ABI_MACROS = {"x64": ["__x86_64__"], "x86": ["__i386__"], "ppc64": ["__powerpc64__"]}
# Reserved names a conditional may test. __KERNEL__ and the assembler macros
# are never defined: the tables describe what a C program in user space sees.
# __ILP32__ is only tested together with __x86_64__ (the x32 ABI, not covered).
REVIEWED_MACROS = {"__x86_64__", "__i386__", "__powerpc64__", "__ILP32__", "__KERNEL__", "__ASSEMBLY__", "__ASSEMBLER__", "__BITS_PER_LONG"}
# Constants in the signal headers that are not signal numbers.
NOT_SIGNALS = {"SIGSTKSZ"}
REALTIME_BOUNDS = ("SIGRTMIN", "SIGRTMAX")
# Bit masks and packet flags that sit beside the commands in the ioctl headers.
IOCTL_FLAG_PREFIXES = ("TIOCPKT_", "TIOCM_", "TIOCSER_")
IOC_MACROS = ("_IO", "_IOR", "_IOW", "_IOWR")
IOC_LAYOUT = "(((dir)<<_IOC_DIRSHIFT)|((type)<<_IOC_TYPESHIFT)|((nr)<<_IOC_NRSHIFT)|((size)<<_IOC_SIZESHIFT))"
# The one input without an SPDX line or a notice of its own.
UNMARKED_DOCUMENTATION = {IOCTL_REGISTRY}


class Unresolved(Exception):
    """A C expression whose value these headers do not determine."""


def c_int(expression, lookup):
    """Evaluate an integer constant expression; identifiers go through lookup."""
    text = re.sub(r"'(\\.|[^'\\])'", lambda m: str(ord(ast.literal_eval(m[0]))), expression)

    def number(match):
        digits = match[1]
        return str(int(digits, 8) if re.fullmatch(r"0[0-7]+", digits) else int(digits, 0))

    text = re.sub(r"\b(0[xX][0-9a-fA-F]+|\d+)[uUlL]*\b", number, text)
    text = text.replace("&&", " and ").replace("||", " or ")
    text = re.sub(r"!(?!=)", " not ", text).strip()
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise Unresolved(expression) from None
    binary = {
        ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a // b, ast.LShift: lambda a, b: a << b, ast.RShift: lambda a, b: a >> b,
        ast.BitOr: lambda a, b: a | b, ast.BitAnd: lambda a, b: a & b, ast.BitXor: lambda a, b: a ^ b,
    }
    compare = {
        ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b, ast.Lt: lambda a, b: a < b,
        ast.Gt: lambda a, b: a > b, ast.LtE: lambda a, b: a <= b, ast.GtE: lambda a, b: a >= b,
    }

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.Name):
            return lookup(node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return binary[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp):
            value = walk(node.operand)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.Invert):
                return ~value
            if isinstance(node.op, ast.Not):
                return int(not value)
        if isinstance(node, ast.BoolOp):
            values = [walk(value) for value in node.values]
            return int(all(values) if isinstance(node.op, ast.And) else any(values))
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in compare:
            return int(compare[type(node.ops[0])](walk(node.left), walk(node.comparators[0])))
        raise Unresolved(expression)

    return walk(tree)


def logical_lines(text):
    """Yield (line number, text) without comments, joining continuation lines."""
    lines = sk.strip_comments(text).split("\n")
    index = 0
    while index < len(lines):
        start, line = index, lines[index]
        while line.rstrip().endswith("\\") and index + 1 < len(lines):
            index += 1
            line = line.rstrip()[:-1] + " " + lines[index]
        yield start + 1, line
        index += 1


def trailing_comment(raw_lines, number):
    """The comment that starts on a definition's own line, as one line of text."""
    line = raw_lines[number - 1]
    start = line.find("/*")
    if start < 0:
        return None
    rest = "\n".join(raw_lines[number - 1:number + 12])[start + 2:]
    end = rest.find("*/")
    if end < 0:
        return None
    return re.sub(r"\s*\n\s*\*?\s*", " ", rest[:end]).strip() or None


def kbuild_entries(text, variable):
    """Map each header named by 'variable += header' to its line number."""
    return {m[1]: text[:m.start()].count("\n") + 1 for m in re.finditer(r"^{}\s*\+=\s*(\S+)\s*$".format(re.escape(variable)), text, re.M)}


class Headers:
    """A small C preprocessor over the UAPI headers of one ABI."""

    def __init__(self, source, arch):
        self.source = source
        self.arch = arch
        self.kernel = sk.ARCHES[arch]["kernel"]
        self.predefined = {"__BITS_PER_LONG": sk.ARCHES[arch]["bits"], **{name: 1 for name in ABI_MACROS.get(arch, [])}}
        self.macros = {}
        self.files = []
        self.tested = set()
        self.resolutions = {}

    def asm_header(self, name):
        """Resolve <asm/name> the way the kernel's header install does."""
        if name in self.resolutions:
            return self.resolutions[name]
        own = "arch/{}/include/uapi/asm/{}".format(self.kernel, name)
        if self.source.read(own, optional=True):
            record = {"path": own, "kind": "architecture"}
        else:
            # No header of its own: Kbuild generates a wrapper for asm-generic.
            kbuild = "arch/{}/include/uapi/asm/Kbuild".format(self.kernel)
            generic = kbuild_entries(self.source.read(kbuild), "generic-y")
            mandatory = kbuild_entries(self.source.read(GENERIC_KBUILD), "mandatory-y")
            if name in generic:
                rule = {"kind": "generic-y", "kbuild": kbuild, "line": generic[name]}
            elif name in mandatory:
                rule = {"kind": "mandatory-y", "kbuild": GENERIC_KBUILD, "line": mandatory[name]}
            else:
                raise ValueError("No <asm/{}> for {}: neither an architecture header nor a Kbuild rule".format(name, self.kernel))
            record = {"path": GENERIC + name, **rule}
        self.resolutions[name] = record
        return record

    def resolve_include(self, name):
        if name.startswith("asm-generic/"):
            return "include/uapi/" + name
        if name.startswith("asm/") and name[4:] in ASM_HEADERS:
            return self.asm_header(name[4:])["path"]
        if name in LINUX_HEADERS:
            return "include/uapi/" + name
        return None

    def defined(self, name):
        self.tested.add(name)
        return name in self.macros or name in self.predefined

    def value(self, name, seen=()):
        """Integer value of an object-like macro."""
        if name in self.macros:
            macro = self.macros[name]
            if name in seen or macro["parameters"] is not None or not macro["body"]:
                raise Unresolved(name)
            return c_int(macro["body"], lambda inner: self.value(inner, (*seen, name)))
        if name in self.predefined:
            return self.predefined[name]
        raise Unresolved(name)

    def condition(self, kind, rest, path, number):
        if kind in {"ifdef", "ifndef"}:
            return self.defined(rest.split()[0]) == (kind == "ifdef")
        expression = re.sub(r"\bdefined\s*\(\s*(\w+)\s*\)|\bdefined\s+(\w+)", lambda m: str(int(self.defined(m[1] or m[2]))), rest)
        for name in re.findall(r"\b[A-Za-z_]\w*\b", expression):
            self.tested.add(name)
        try:
            return bool(c_int(expression, self.value))
        except Unresolved:
            raise ValueError("Cannot evaluate '#if {}' at {}:{} for {}".format(rest, path, number, self.arch)) from None

    def include(self, path):
        text = self.source.read(path)
        if path not in self.files:
            self.files.append(path)
        raw_lines = text.split("\n")
        stack = []
        for number, line in logical_lines(text):
            directive = re.match(r"\s*#\s*(\w+)\b\s*(.*?)\s*$", line)
            if not directive:
                continue
            kind, rest = directive[1], directive[2]
            active = all(level["active"] for level in stack)
            if kind in {"if", "ifdef", "ifndef"}:
                value = active and self.condition(kind, rest, path, number)
                stack.append({"active": value, "taken": value or not active})
            elif kind in {"elif", "else"}:
                if not stack:
                    raise ValueError("Unbalanced #{} at {}:{}".format(kind, path, number))
                level = stack[-1]
                outer = all(item["active"] for item in stack[:-1])
                level["active"] = outer and not level["taken"] and (kind == "else" or self.condition("if", rest, path, number))
                level["taken"] = level["taken"] or level["active"]
            elif kind == "endif":
                if not stack:
                    raise ValueError("Unbalanced #endif at {}:{}".format(path, number))
                stack.pop()
            elif not active:
                continue
            elif kind == "include":
                target = re.match(r"<([^>]+)>", rest)
                resolved = self.resolve_include(target[1]) if target else None
                if resolved:
                    self.include(resolved)
            elif kind == "undef":
                self.macros.pop(rest.split()[0], None)
            elif kind == "define":
                definition = re.match(r"(\w+)(\(([^)]*)\))?\s*(.*)$", rest)
                if not definition:
                    raise ValueError("Unrecognized #define at {}:{}".format(path, number))
                name = definition[1]
                self.macros.pop(name, None)
                self.macros[name] = {
                    "body": re.sub(r"\s+", " ", definition[4]).strip(),
                    "parameters": None if definition[2] is None else [p.strip() for p in definition[3].split(",") if p.strip()],
                    "path": path, "line": number, "comment": trailing_comment(raw_lines, number),
                }
        if stack:
            raise ValueError("Unterminated conditional in " + path)

    def check_conditions(self):
        """Refuse compiler or ABI macros that nobody reviewed for this importer."""
        guards = {name for name, macro in self.macros.items() if not macro["body"]}
        for name in sorted(self.tested):
            if name.startswith("__") and name not in self.macros and name not in guards and name not in REVIEWED_MACROS and not re.search(r"_H_*$", name):
                raise ValueError("Unreviewed predefined macro {} in the headers of {}".format(name, self.arch))

    def alias(self, macro):
        body = macro["body"]
        return body if re.fullmatch(r"[A-Za-z_]\w*", body) and body in self.macros else None

    def source_of(self, name):
        return {"path": self.macros[name]["path"], "line": self.macros[name]["line"]}


def with_optional(record, **optional):
    record.update({key: value for key, value in optional.items() if value is not None})
    return record


def errno_table(source, arch):
    headers = Headers(source, arch)
    resolution = headers.asm_header("errno.h")
    headers.include(resolution["path"])
    headers.check_conditions()
    entries = []
    for name, macro in headers.macros.items():
        if not macro["path"].rsplit("/", 1)[1].startswith("errno") or not re.fullmatch(r"E[A-Z0-9]+", name):
            continue
        try:
            number = headers.value(name)
        except Unresolved:
            raise ValueError("Unresolved errno {} at {}:{}".format(name, macro["path"], macro["line"])) from None
        entries.append(with_optional({"name": name, "number": number}, alias_of=headers.alias(macro), comment=macro["comment"], source=headers.source_of(name)))
    if len(entries) < 100 or len({e["name"] for e in entries}) != len(entries):
        raise ValueError("Implausible errno table for " + arch)
    return resolution, {"header": resolution["path"], "files": headers.files, "entries": entries}


def signal_table(source, arch):
    headers = Headers(source, arch)
    resolution = headers.asm_header("signal.h")
    headers.include(resolution["path"])
    headers.check_conditions()
    entries = []
    for name, macro in headers.macros.items():
        if not macro["path"].endswith("/signal.h") or not re.fullmatch(r"SIG[A-Z0-9]+", name) or name in NOT_SIGNALS or name in REALTIME_BOUNDS:
            continue
        try:
            number = headers.value(name)
        except Unresolved:
            raise ValueError("Unresolved signal {} at {}:{}".format(name, macro["path"], macro["line"])) from None
        entries.append(with_optional({"name": name, "number": number}, alias_of=headers.alias(macro), comment=macro["comment"], source=headers.source_of(name)))
    if len(entries) < 30:
        raise ValueError("Implausible signal table for " + arch)
    realtime = {}
    for key, name in zip(("min", "max"), REALTIME_BOUNDS):
        macro = headers.macros[name]
        try:
            value = headers.value(name)
        except Unresolved:
            # Some architectures define _NSIG only in a kernel-internal header.
            value = None
        realtime[key] = {"name": name, "expression": macro["body"], "value": value, "source": headers.source_of(name)}
    table = {"header": resolution["path"], "files": headers.files, "entries": entries, "realtime": realtime}
    if "_NSIG" in headers.macros:
        table["nsig"] = {"value": headers.value("_NSIG"), "source": headers.source_of("_NSIG")}
    return resolution, table


def parse_default_actions(text, path):
    """Read the default-action table from the comment in include/linux/signal.h."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if "POSIX signal" in line and "default action" in line), None)
    if start is None:
        raise ValueError("No default-action table in " + path)
    actions, realtime = {}, None
    index = start
    while index < len(lines) and "*/" not in lines[index]:
        row = re.match(r"\s*\*\s*\|\s*(SIG[A-Z0-9/-]+)\s*\|\s*([a-z]+)((?:\([*+]\))*)\s*\|\s*$", lines[index])
        if row:
            record = {"action": row[2], "markers": re.findall(r"\(([*+])\)", row[3]), "line": index + 1}
            if row[1] == "SIGRTMIN-SIGRTMAX":
                realtime = record
            else:
                for name in row[1].split("/"):
                    actions[name] = record
        index += 1
    end = index
    notes, current = {}, None
    for line in lines[start:end]:
        note = re.match(r"\s*\*\s*\(([*+])\)\s+(.*)$", line)
        body = re.match(r"\s*\*\s?(.*)$", line)
        if note:
            current = note[1]
            notes[current] = note[2].strip()
        elif current and body and body[1].strip() and "|" not in body[1] and "+--" not in body[1]:
            notes[current] += " " + body[1].strip()
    definitions, current = {}, None
    opening = next((i for i in range(start, -1, -1) if "possible effects" in lines[i]), None)
    if opening is None:
        raise ValueError("No action descriptions in " + path)
    for line in lines[opening + 1:start]:
        item = re.match(r"\s*\*\s+(\w+)\s+-\s+(.*)$", line)
        body = re.match(r"\s*\*\s*(.*)$", line)
        if item:
            current = item[1]
            definitions[current] = item[2].strip()
        elif current and body and body[1].strip() and not body[1].lstrip().startswith(("+", "|")) and "cannot be caught" not in body[1] and not re.match(r"(SIGKILL|Other|The job)", body[1].strip()):
            definitions[current] += " " + body[1].strip()
        elif body and not body[1].strip():
            current = None
    used = {record["action"] for record in actions.values()}
    if len(actions) < 30 or realtime is None or not used <= definitions.keys():
        raise ValueError("Default-action table layout changed in " + path)
    return {"source": {"path": path, "line": start + 1}, "definitions": {key: re.sub(r"\s+", " ", value) for key, value in definitions.items()},
            "notes": {key: re.sub(r"\s+", " ", value) for key, value in notes.items()}, "signals": actions, "realtime": realtime}


def parse_type_sizes(text, path):
    """Sizes of the C integer types, read from the kernel's fixed-width typedefs."""
    sizes = {}
    for m in re.finditer(r"^(?:__extension__\s+)?typedef\s+(__signed__\s+|unsigned\s+)?(char|short|int|long long)\s+__[su](8|16|32|64)\s*;", text, re.M):
        prefix = (m[1] or "").strip()
        size = int(m[3]) // 8
        names = ["unsigned " + m[2]] if prefix == "unsigned" else [m[2], "signed " + m[2]]
        for name in names:
            if sizes.setdefault(name, size) != size:
                raise ValueError("Conflicting size for {} in {}".format(name, path))
    if not {"int", "unsigned int", "long long"} <= sizes.keys():
        raise ValueError("Fixed-width typedefs not found in " + path)
    return sizes


def sizeof(c_type, sizes):
    text = re.sub(r"\s+", " ", c_type).strip()
    array = re.fullmatch(r"(.*?)\s*\[(\d+)\]", text)
    if array:
        return sizes[array[1]] * int(array[2]) if array[1] in sizes else None
    return sizes.get(text)


def ioctl_encoding(headers):
    macro = headers.macros.get("_IOC")
    if not macro or macro["parameters"] != ["dir", "type", "nr", "size"] or macro["body"].replace(" ", "") != IOC_LAYOUT:
        raise ValueError("_IOC() layout changed for " + headers.arch)
    fields = {}
    for field in ["nr", "type", "size", "dir"]:
        bits, shift = "_IOC_{}BITS".format(field.upper()), "_IOC_{}SHIFT".format(field.upper())
        fields[field] = {"bits": headers.value(bits), "shift": headers.value(shift), "source": headers.source_of(bits)}
    if sum(field["bits"] for field in fields.values()) != 32:
        raise ValueError("ioctl fields do not fill 32 bits for " + headers.arch)
    directions = {key: {"value": headers.value("_IOC_" + key.upper()), "source": headers.source_of("_IOC_" + key.upper())} for key in ["none", "write", "read"]}
    constructors = {}
    for name in IOC_MACROS:
        body = headers.macros[name]["body"]
        call = re.fullmatch(r"_IOC\((.*)\)", body)
        if not call:
            raise ValueError("{}() no longer expands to _IOC()".format(name))
        direction = sk.split_c_arguments(call[1])[0]
        constructors[name] = {"direction": direction, "value": c_int(direction, headers.value), "source": headers.source_of(name)}
    return {"fields": fields, "directions": directions, "macros": constructors}


def ioctl_tables(source, arch, sizes):
    headers = Headers(source, arch)
    encoding_resolution = headers.asm_header("ioctl.h")
    headers.include(encoding_resolution["path"])
    encoding_files = list(headers.files)
    encoding = {"header": encoding_resolution["path"], "files": encoding_files, **ioctl_encoding(headers)}
    resolutions = {"ioctl.h": encoding_resolution}
    for name in ["ioctls.h", "sockios.h"]:
        resolutions[name] = headers.asm_header(name)
    headers.include(resolutions["ioctls.h"]["path"])
    headers.include("include/uapi/linux/sockios.h")
    headers.check_conditions()
    fields = encoding["fields"]

    def encoded(body):
        call = re.fullmatch(r"(_IO(?:R|W|WR)?)\s*\((.*)\)", body)
        if not call:
            return None
        arguments = sk.split_c_arguments(call[2])
        if len(arguments) != (2 if call[1] == "_IO" else 3):
            raise ValueError("Unexpected {} arguments: {}".format(call[1], body))
        record = {"expression": body, "macro": call[1], "type": {"text": arguments[0], "value": c_int(arguments[0], headers.value)},
                  "nr": c_int(arguments[1], headers.value), "direction": encoding["macros"][call[1]]["value"]}
        size = 0
        if call[1] != "_IO":
            record["size_type"] = arguments[2]
            size = sizeof(arguments[2], sizes)
        record["size"] = size
        if size is None:
            record["value"] = None
        else:
            record["value"] = (record["direction"] << fields["dir"]["shift"] | record["type"]["value"] << fields["type"]["shift"]
                               | record["nr"] << fields["nr"]["shift"] | size << fields["size"]["shift"])
        return record

    # A macro used as the type argument of _IO*() names a magic number, not a command.
    type_names = set()
    for macro in headers.macros.values():
        call = re.fullmatch(r"_IO(?:R|W|WR)?\s*\((.*)\)", macro["body"])
        if call and macro["parameters"] is None:
            type_names.update(re.findall(r"[A-Za-z_]\w*", sk.split_c_arguments(call[1])[0]))

    def command(name, seen=()):
        macro = headers.macros[name]
        record = {"name": name, "set": macro["path"].rsplit("/", 1)[1][:-2]}
        target = headers.alias(macro)
        call = encoded(macro["body"])
        if target and target not in seen:
            record.update(alias_of=target, value=command(target, (*seen, name))["value"])
        elif call:
            record.update(call)
        else:
            try:
                record["value"] = c_int(macro["body"], headers.value)
            except Unresolved:
                # For example a choice made with sizeof() of a C library type.
                record.update(value=None, expression=macro["body"])
        return with_optional(record, comment=macro["comment"], source=headers.source_of(name))

    commands = []
    for name, macro in headers.macros.items():
        if macro["path"].rsplit("/", 1)[1] not in {"ioctls.h", "sockios.h"} or macro["parameters"] is not None or not macro["body"]:
            continue
        if name.startswith(IOCTL_FLAG_PREFIXES) or name in type_names:
            continue
        record = command(name)
        if "macro" not in record and "alias_of" not in record and record["value"] is not None and not record["value"] >> fields["type"]["shift"] & 0xFF:
            raise ValueError("{} in {} does not look like an ioctl command".format(name, macro["path"]))
        commands.append(record)
    if len(commands) < 100:
        raise ValueError("Implausible ioctl command list for " + arch)
    files = [path for path in headers.files if path not in encoding_files or path == encoding["header"]]
    return resolutions, encoding, {"header": resolutions["ioctls.h"]["path"], "files": files, "entries": commands}


def parse_ioctl_registry(text, path):
    """Read the magic-number table of ioctl-number.rst (an RST simple table)."""
    lines = text.expandtabs().split("\n")
    head = next((i for i, line in enumerate(lines) if re.match(r"Code\s+Seq#", line)), None)
    if head is None or not re.fullmatch(r"[= ]+", lines[head - 1]):
        raise ValueError("ioctl number table not found in " + path)
    starts = [m.start() for m in re.finditer(r"=+", lines[head - 1])]
    if len(starts) != 4:
        raise ValueError("ioctl number table layout changed in " + path)
    body = next(i for i in range(head + 1, len(lines)) if re.fullmatch(r"[= ]+", lines[i]) and lines[i].strip())
    rows = []
    for index in range(body + 1, len(lines)):
        line = lines[index]
        if re.fullmatch(r"[= ]+", line) and line.strip():
            break
        if not line.strip():
            continue
        for start in starts[1:]:
            if line[start - 1:start].strip():
                raise ValueError("Cell crosses a column boundary at {}:{}".format(path, index + 1))
        code, sequence, include, comment = (line[a:b].strip() for a, b in zip(starts, [*starts[1:], None]))
        if code:
            quoted = re.fullmatch(r"'(.)'", code)
            if quoted:
                value = ord(quoted[1])
            elif re.fullmatch(r"0x[0-9A-Fa-f]{2}", code):
                value = int(code, 16)
            else:
                raise ValueError("Unrecognized ioctl code {} at {}:{}".format(code, path, index + 1))
            span = re.fullmatch(r"([0-9A-Fa-f]{1,2})(?:-([0-9A-Fa-f]{1,2}))?", sequence)
            rows.append({
                "code": code, "value": value, "sequence": sequence,
                # Null where the document says "all" or uses a free-form range.
                "range": [int(span[1], 16), int(span[2] or span[1], 16)] if span else None,
                "includes": [include] if include else [], "comments": [comment] if comment else [], "line": index + 1,
            })
        elif not rows:
            raise ValueError("Unexpected continuation at {}:{}".format(path, index + 1))
        else:
            # A continuation line carries prose such as "and <file>" across both cells.
            include = " ".join(part for part in [sequence, include] if part)
            rows[-1]["includes"] += [include] if include else []
            rows[-1]["comments"] += [comment] if comment else []
    else:
        raise ValueError("Unterminated ioctl number table in " + path)
    if len(rows) < 200:
        raise ValueError("Implausible ioctl number table in " + path)
    return {"source": {"path": path, "line": head + 1}, "rows": rows}


def source_licenses(files, ref):
    """sync_kernel's licence gate, plus the one reviewed input that has no SPDX line."""
    unmarked = {path for path in files if path in UNMARKED_DOCUMENTATION and "SPDX-License-Identifier" not in files[path]["text"]}
    records = sk.source_licenses({path: info for path, info in files.items() if path not in unmarked}, ref)
    for path in unmarked:
        if "COPYING" not in files or "GNU General Public License version 2 only" not in files["COPYING"]["text"]:
            raise ValueError("No licence basis for " + path)
        records.append({
            "path": path, "sha256": files[path]["sha256"], "bundled_path": "sources/" + path,
            "license_identifier": "GPL-2.0-only", "license_basis": "COPYING",
            "license_note": "No SPDX identifier and no notice of its own; the release COPYING provides the kernel under GPL-2.0 where a file does not say otherwise.",
        })
    return sorted(records, key=lambda record: record["path"])


def shared_tables(per_arch):
    """Store identical tables once and name them after the header they start from."""
    groups = {}
    for arch, table in per_arch.items():
        base = "generic" if table["header"].startswith(GENERIC) else table["header"].split("/")[1]
        variants = groups.setdefault(base, [])
        for variant in variants:
            if variant["table"] == table:
                variant["architectures"].append(arch)
                break
        else:
            variants.append({"table": table, "architectures": [arch]})
    tables, assignment = {}, {}
    for base, variants in groups.items():
        for variant in variants:
            name = base if len(variants) == 1 else "{}-{}".format(base, sk.ARCHES[variant["architectures"][0]]["bits"])
            if name in tables:
                name = "{}-{}".format(base, variant["architectures"][0])
            tables[name] = variant["table"]
            assignment.update({arch: name for arch in variant["architectures"]})
    return tables, assignment


def build(ref, tree=None):
    """Parse one release; return the JSON documents and the source files read."""
    source = sk.Source(ref, tree)
    if tree:
        makefile = source.read("Makefile")
        version = "v" + ".".join(re.search(r"^{}\s*=\s*(\d+)".format(key), makefile, re.M)[1] for key in ["VERSION", "PATCHLEVEL"])
        if sk.version_key(ref)[:2] != sk.version_key(version):
            raise ValueError("Ref {} does not match kernel Makefile version {}".format(ref, version))
    source.read("COPYING")
    sizes = parse_type_sizes(source.read(TYPE_SIZES), TYPE_SIZES)
    errno, signals, encodings, commands = {}, {}, {}, {}
    resolutions = {arch: {} for arch in sk.ARCHES}
    for arch in sk.ARCHES:
        resolutions[arch]["errno.h"], errno[arch] = errno_table(source, arch)
        resolutions[arch]["signal.h"], signals[arch] = signal_table(source, arch)
        ioctl_resolutions, encodings[arch], commands[arch] = ioctl_tables(source, arch, sizes)
        resolutions[arch].update(ioctl_resolutions)
    actions = parse_default_actions(source.read(SIGNAL_ACTIONS), SIGNAL_ACTIONS)
    registry = parse_ioctl_registry(source.read(IOCTL_REGISTRY), IOCTL_REGISTRY)
    for path in sk.LICENSE_FILES:
        source.read(path)
    files = source_licenses(source.files, ref)
    provenance = {"kind": "local" if tree else "upstream", "repository": "https://github.com/torvalds/linux", "ref": ref, "files": files}
    if tree:
        provenance["local_commit"] = sk.local_kernel_commit(source.tree)
    licensing = {
        "generated_file": "GPL-2.0-only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "upstream_notice": "sources/COPYING",
        "upstream_license_texts": ["sources/" + path for path in sk.LICENSE_FILES[1:]],
        "generator": GENERATOR,
        "modification_notice": "Generated by syscall-reference from Linux " + ref + "; preprocessor definitions, a comment table and a documentation table were parsed per ABI and converted to JSON. Bundled input files are unchanged; their original licenses, notices and exceptions remain in effect. The Linux-syscall-note is not applied to all application code or all extracted data.",
    }
    labels = {arch: config["label"] for arch, config in sk.ARCHES.items()}

    def document(kind, **content):
        return {"license": "GPL-2.0-only", "schema_version": 1, "kind": kind, "kernel": ref, **content, "licensing": licensing, "provenance": provenance}

    def architectures(assignments, names):
        return {arch: {"label": labels[arch], **{key: table[arch] for key, table in assignments.items()},
                       "headers": {name: resolutions[arch][name] for name in names}} for arch in sk.ARCHES}

    errno_tables, errno_assignment = shared_tables(errno)
    signal_tables, signal_assignment = shared_tables(signals)
    encoding_tables, encoding_assignment = shared_tables(encodings)
    command_tables, command_assignment = shared_tables(commands)
    documents = {
        "errno.json": document("errno", tables=errno_tables, architectures=architectures({"table": errno_assignment}, ["errno.h"])),
        "signals.json": document("signals", tables=signal_tables, default_actions=actions, architectures=architectures({"table": signal_assignment}, ["signal.h"])),
        "ioctl.json": document("ioctl", encodings=encoding_tables, commands=command_tables,
                               type_sizes={"source": {"path": TYPE_SIZES}, "sizes": sizes},
                               architectures=architectures({"encoding": encoding_assignment, "commands": command_assignment}, ["ioctl.h", "ioctls.h", "sockios.h"])),
        "ioctl-numbers.json": document("ioctl-numbers", **registry),
        "sources.json": {"license": "GPL-2.0-only", "kernel": ref, "architectures": list(sk.ARCHES), "documents": ["errno.json", "signals.json", "ioctl.json", "ioctl-numbers.json"], "licensing": licensing, **provenance},
    }
    return documents, source.files


def stage(folder, documents, files):
    for path, info in files.items():
        sk.atomic_text(folder / "sources" / path, info["text"])
    for name, value in documents.items():
        sk.atomic_json(folder / name, value)


def unchanged(folder, documents, files):
    """True when the published release differs at most in its generation time."""
    try:
        for name, value in documents.items():
            current = json.loads((folder / name).read_bytes())
            expected = json.loads(json.dumps(value))
            current["licensing"].pop("generated_at", None)
            expected["licensing"].pop("generated_at", None)
            if current != expected:
                return False
        present = {p.relative_to(folder / "sources").as_posix() for p in (folder / "sources").rglob("*") if p.is_file()}
        return present == files.keys() and all(
            hashlib.sha256((folder / "sources" / path).read_bytes()).hexdigest() == info["sha256"] for path, info in files.items())
    except (OSError, ValueError, KeyError, TypeError):
        return False


def publish(output, ref, documents, files):
    """Replace data/abi/<release>/ as a whole, then list it in data/abi/manifest.json."""
    output.mkdir(parents=True, exist_ok=True)
    target = output / ref
    if not unchanged(target, documents, files):
        staging = output / (".tmp-abi-" + uuid4().hex)
        retired = output / (".tmp-retired-" + uuid4().hex)
        try:
            stage(staging, documents, files)
            if target.exists():
                target.rename(retired)
            staging.rename(target)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(retired, ignore_errors=True)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    versions = sorted({*manifest.get("versions", []), ref}, key=sk.version_key, reverse=True)
    versions = [version for version in versions if (output / version / "sources.json").is_file()]
    updated = {
        "license": "GPL-2.0-only", "schema_version": 1, "versions": versions, "latest": versions[0],
        "documents": documents["sources.json"]["documents"],
        "architectures": [{"id": arch, "label": config["label"], "bits": config["bits"], "kernel": config["kernel"]} for arch, config in sk.ARCHES.items()],
    }
    if updated != manifest:
        sk.atomic_json(manifest_path, updated)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refs", nargs="+", help="Kernel release tags; default: the latest release in public/data/manifest.json")
    parser.add_argument("--kernel-tree", type=Path, help="Read one matching release from a local Linux tree, without network")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    refs = list(dict.fromkeys(args.refs or [json.loads((ROOT / "public/data/manifest.json").read_text())["latest"]]))
    if any(not re.fullmatch(r"v\d+\.\d+(?:\.\d+)?", ref) for ref in refs):
        parser.error("Only explicit release tags are supported")
    if args.kernel_tree and len(refs) != 1:
        parser.error("--kernel-tree requires exactly one --refs tag matching its Makefile")
    try:
        built = {ref: build(ref, args.kernel_tree) for ref in refs}
        # Nothing is written until every requested release parsed and passed the licence gate.
        for ref, (documents, files) in built.items():
            publish(args.output, ref, documents, files)
            tables = {name: len(documents[name].get("tables", documents[name].get("commands", {}))) for name in ["errno.json", "signals.json", "ioctl.json"]}
            print("{}: {} source files; tables: {}; ioctl magic numbers: {}".format(
                ref, len(files), ", ".join("{}={}".format(k[:-5], v) for k, v in tables.items()), len(documents["ioctl-numbers.json"]["rows"])), flush=True)
    except Exception as error:
        print("ABI import failed: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
