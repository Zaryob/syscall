# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("sync_abi", ROOT / "scripts/sync_abi.py")
abi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(abi)

PUBLISHED = ROOT / "public/data/abi"
LATEST = json.loads((PUBLISHED / "manifest.json").read_text())["latest"]
BUNDLED = PUBLISHED / LATEST / "sources"


class StubSource:
    """Stands in for sync_kernel.Source: files come from a dict or a folder, never the network."""

    def __init__(self, files=None, folder=None):
        self.given, self.folder = files or {}, folder
        self.files, self.missing, self.archive_url, self.tree = {}, set(), None, None

    def read(self, path, optional=False):
        if path not in self.files:
            if path in self.given:
                text = self.given[path]
            elif self.folder and (self.folder / path).is_file():
                text = (self.folder / path).read_text()
            elif optional:
                return ""
            else:
                raise FileNotFoundError(path)
            self.files[path] = {"text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}
        return self.files[path]["text"]


SPDX = "/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */\n"
KBUILD = "# SPDX-License-Identifier: GPL-2.0\n"
FIXTURE = {
    "include/uapi/asm-generic/Kbuild": KBUILD + "mandatory-y += errno.h\nmandatory-y += ioctl.h\nmandatory-y += signal.h\n",
    "arch/riscv/include/uapi/asm/Kbuild": KBUILD + "syscall-y += unistd_64.h\n",
    "arch/arm/include/uapi/asm/Kbuild": KBUILD + "generic-y += sockios.h\n",
    "arch/powerpc/include/uapi/asm/Kbuild": KBUILD,
    "arch/x86/include/uapi/asm/Kbuild": KBUILD,
    "include/uapi/asm-generic/errno-base.h": SPDX + "#ifndef _BASE_H\n#define _BASE_H\n#define\tEPERM\t\t 1\t/* Operation not permitted */\n#define EAGAIN 11 /* Try again */\n#endif\n",
    "include/uapi/asm-generic/errno.h": SPDX + "#ifndef _ERRNO_H\n#define _ERRNO_H\n#include <asm-generic/errno-base.h>\n#define EDEADLK 35 /* Resource deadlock\n * would occur */\n"
                                         "#define EWOULDBLOCK EAGAIN /* Operation would block */\n#define EDEADLOCK EDEADLK\n#ifdef __KERNEL__\n#define EKERNELONLY 999\n#endif\n#endif\n",
    "arch/powerpc/include/uapi/asm/errno.h": SPDX + "#undef EDEADLOCK\n#include <asm-generic/errno.h>\n#undef EDEADLOCK\n#define EDEADLOCK 58 /* File locking deadlock error */\n",
    "include/uapi/asm-generic/signal.h": SPDX + "#define _NSIG 64\n#define SIGHUP 1\n#define SIGIO 29\n#define SIGPOLL SIGIO\n/*\n#define SIGLOST 29\n*/\n#define SIGRTMIN 32\n"
                                          "#ifndef SIGRTMAX\n#define SIGRTMAX _NSIG\n#endif\n#if !defined MINSIGSTKSZ || !defined SIGSTKSZ\n#define SIGSTKSZ 8192\n#endif\n",
    "arch/x86/include/uapi/asm/signal.h": SPDX + "#ifndef __KERNEL__\n#define NSIG 32\n#endif\n#define SIGHUP 1\n#define SIGRTMIN 32\n#define SIGRTMAX _NSIG\n#define SIGSTKSZ 8192\n#ifdef __i386__\n#define SIGONLY32 40\n#else\n#define SIGONLY64 41\n#endif\n",
    "include/uapi/asm-generic/ioctl.h": SPDX + "#define _IOC_NRBITS 8\n#define _IOC_TYPEBITS 8\n#ifndef _IOC_SIZEBITS\n# define _IOC_SIZEBITS 14\n#endif\n#ifndef _IOC_DIRBITS\n# define _IOC_DIRBITS 2\n#endif\n"
                                         "#define _IOC_NRSHIFT 0\n#define _IOC_TYPESHIFT (_IOC_NRSHIFT+_IOC_NRBITS)\n#define _IOC_SIZESHIFT (_IOC_TYPESHIFT+_IOC_TYPEBITS)\n#define _IOC_DIRSHIFT (_IOC_SIZESHIFT+_IOC_SIZEBITS)\n"
                                         "#ifndef _IOC_NONE\n# define _IOC_NONE 0U\n#endif\n#ifndef _IOC_WRITE\n# define _IOC_WRITE 1U\n#endif\n#ifndef _IOC_READ\n# define _IOC_READ 2U\n#endif\n"
                                         "#define _IOC(dir,type,nr,size) \\\n\t(((dir)  << _IOC_DIRSHIFT) | \\\n\t ((type) << _IOC_TYPESHIFT) | \\\n\t ((nr)   << _IOC_NRSHIFT) | \\\n\t ((size) << _IOC_SIZESHIFT))\n"
                                         "#define _IOC_TYPECHECK(t) (sizeof(t))\n#define _IO(type,nr) _IOC(_IOC_NONE,(type),(nr),0)\n#define _IOR(type,nr,argtype) _IOC(_IOC_READ,(type),(nr),(_IOC_TYPECHECK(argtype)))\n"
                                         "#define _IOW(type,nr,argtype) _IOC(_IOC_WRITE,(type),(nr),(_IOC_TYPECHECK(argtype)))\n#define _IOWR(type,nr,argtype) _IOC(_IOC_READ|_IOC_WRITE,(type),(nr),(_IOC_TYPECHECK(argtype)))\n",
    "arch/powerpc/include/uapi/asm/ioctl.h": SPDX + "#define _IOC_SIZEBITS 13\n#define _IOC_DIRBITS 3\n#define _IOC_NONE 1U\n#define _IOC_READ 2U\n#define _IOC_WRITE 4U\n#include <asm-generic/ioctl.h>\n",
}


class PreprocessorTests(unittest.TestCase):
    def test_expressions_cover_c_literals_and_refuse_what_headers_do_not_fix(self):
        lookup = {"A": 3}.__getitem__
        self.assertEqual(abi.c_int("(1 << A) | 0x10U", lookup), 0x18)
        self.assertEqual(abi.c_int("'T'", lookup), 0x54)
        self.assertEqual(abi.c_int("017 + 1UL", lookup), 16)
        self.assertEqual(abi.c_int("A == 3 || (0 && !1)", lookup), 1)
        self.assertEqual(abi.c_int("A != 3", lookup), 0)
        for expression in ["sizeof(int)", "(x) == 8 ? 1 : 2", "1 +"]:
            with self.assertRaises(abi.Unresolved):
                abi.c_int(expression, lambda name: 8)

    def test_asm_headers_resolve_through_the_architecture_or_a_kbuild_rule(self):
        source = StubSource(FIXTURE)
        self.assertEqual(abi.Headers(source, "ppc64").asm_header("errno.h"), {"path": "arch/powerpc/include/uapi/asm/errno.h", "kind": "architecture"})
        self.assertEqual(abi.Headers(source, "riscv64").asm_header("errno.h"),
                         {"path": "include/uapi/asm-generic/errno.h", "kind": "mandatory-y", "kbuild": "include/uapi/asm-generic/Kbuild", "line": 2})
        self.assertEqual(abi.Headers(source, "arm").asm_header("sockios.h"),
                         {"path": "include/uapi/asm-generic/sockios.h", "kind": "generic-y", "kbuild": "arch/arm/include/uapi/asm/Kbuild", "line": 2})
        with self.assertRaisesRegex(ValueError, "neither an architecture header nor a Kbuild rule"):
            abi.Headers(source, "riscv64").asm_header("sockios.h")

    def test_unreviewed_compiler_macros_stop_the_import(self):
        source = StubSource({**FIXTURE, "include/uapi/asm-generic/signal.h": FIXTURE["include/uapi/asm-generic/signal.h"] + "#ifdef __sparc__\n#define SIGHUP 99\n#endif\n"})
        headers = abi.Headers(source, "riscv64")
        headers.include("include/uapi/asm-generic/signal.h")
        with self.assertRaisesRegex(ValueError, "__sparc__"):
            headers.check_conditions()
        with self.assertRaisesRegex(ValueError, "Cannot evaluate"):
            abi.Headers(StubSource({"x.h": "#if UNKNOWN_THING > 2\n#endif\n"}), "x64").include("x.h")


class HeaderKindTests(unittest.TestCase):
    def errno(self, arch):
        headers = abi.Headers(StubSource(FIXTURE), arch)
        headers.include(headers.asm_header("errno.h")["path"])
        return headers

    def test_errno_names_numbers_aliases_comments_and_overrides(self):
        generic = self.errno("riscv64")
        self.assertEqual(generic.value("EDEADLK"), 35)
        self.assertEqual(generic.macros["EDEADLK"]["comment"], "Resource deadlock would occur")
        self.assertEqual((generic.value("EWOULDBLOCK"), generic.alias(generic.macros["EWOULDBLOCK"])), (11, "EAGAIN"))
        self.assertEqual((generic.value("EDEADLOCK"), generic.alias(generic.macros["EDEADLOCK"])), (35, "EDEADLK"))
        self.assertEqual(generic.source_of("EPERM"), {"path": "include/uapi/asm-generic/errno-base.h", "line": 4})
        self.assertNotIn("EKERNELONLY", generic.macros)
        powerpc = self.errno("ppc64")
        self.assertEqual((powerpc.value("EDEADLOCK"), powerpc.alias(powerpc.macros["EDEADLOCK"])), (58, None))
        self.assertEqual(powerpc.source_of("EDEADLOCK"), {"path": "arch/powerpc/include/uapi/asm/errno.h", "line": 5})
        self.assertEqual(powerpc.files, ["arch/powerpc/include/uapi/asm/errno.h", "include/uapi/asm-generic/errno.h", "include/uapi/asm-generic/errno-base.h"])

    def test_signal_headers_follow_abi_macros_and_leave_unresolved_bounds_unnumbered(self):
        def signals(arch):
            headers = abi.Headers(StubSource(FIXTURE), arch)
            headers.include(headers.asm_header("signal.h")["path"])
            headers.check_conditions()
            return headers
        generic = signals("riscv64")
        self.assertEqual((generic.value("SIGPOLL"), generic.alias(generic.macros["SIGPOLL"])), (29, "SIGIO"))
        self.assertNotIn("SIGLOST", generic.macros)
        self.assertEqual(generic.value("SIGRTMAX"), 64)
        x64, x86 = signals("x64"), signals("x86")
        self.assertIn("SIGONLY64", x64.macros)
        self.assertNotIn("SIGONLY32", x64.macros)
        self.assertIn("SIGONLY32", x86.macros)
        self.assertIn("NSIG", x64.macros)
        with self.assertRaises(abi.Unresolved):
            x64.value("SIGRTMAX")

    def test_ioctl_layout_is_read_per_architecture(self):
        def encoding(arch):
            headers = abi.Headers(StubSource(FIXTURE), arch)
            headers.include(headers.asm_header("ioctl.h")["path"])
            return abi.ioctl_encoding(headers)
        generic, powerpc = encoding("riscv64"), encoding("ppc64")
        self.assertEqual({k: (v["bits"], v["shift"]) for k, v in generic["fields"].items()}, {"nr": (8, 0), "type": (8, 8), "size": (14, 16), "dir": (2, 30)})
        self.assertEqual({k: (v["bits"], v["shift"]) for k, v in powerpc["fields"].items()}, {"nr": (8, 0), "type": (8, 8), "size": (13, 16), "dir": (3, 29)})
        self.assertEqual({k: v["value"] for k, v in generic["directions"].items()}, {"none": 0, "write": 1, "read": 2})
        self.assertEqual({k: v["value"] for k, v in powerpc["directions"].items()}, {"none": 1, "write": 4, "read": 2})
        self.assertEqual({k: v["value"] for k, v in powerpc["macros"].items()}, {"_IO": 1, "_IOR": 2, "_IOW": 4, "_IOWR": 6})
        self.assertEqual(powerpc["fields"]["size"]["source"], {"path": "arch/powerpc/include/uapi/asm/ioctl.h", "line": 2})
        changed = {**FIXTURE, "include/uapi/asm-generic/ioctl.h": FIXTURE["include/uapi/asm-generic/ioctl.h"].replace("((nr)   << _IOC_NRSHIFT)", "((nr)   << 1)")}
        headers = abi.Headers(StubSource(changed), "riscv64")
        headers.include("include/uapi/asm-generic/ioctl.h")
        with self.assertRaisesRegex(ValueError, "layout changed"):
            abi.ioctl_encoding(headers)

    def test_type_sizes_come_from_the_fixed_width_typedefs(self):
        sizes = abi.parse_type_sizes("typedef __signed__ char __s8;\ntypedef unsigned char __u8;\ntypedef __signed__ int __s32;\ntypedef unsigned int __u32;\n__extension__ typedef __signed__ long long __s64;\n", "x.h")
        self.assertEqual((sizes["int"], sizes["unsigned int"], sizes["long long"], sizes["unsigned char"]), (4, 4, 8, 1))
        self.assertEqual(abi.sizeof("long  long[2]", sizes), 16)
        self.assertIsNone(abi.sizeof("struct termios2", sizes))
        self.assertIsNone(abi.sizeof("pid_t", sizes))
        with self.assertRaises(ValueError):
            abi.parse_type_sizes("typedef unsigned short __u16;\n", "x.h")

    def test_default_action_table_and_its_notes(self):
        rows = "".join(" *\t|  SIG{:<16}|  terminate\t|\n".format("N%d" % i) for i in range(28))
        text = ("/*\n * The possible effects an unblocked signal set to SIG_DFL can have are:\n *   ignore\t- Nothing Happens\n *   terminate\t- kill the process,\n *\t\t  similar to exit_group.\n"
                " *   stop \t- stop all the threads\n *\n * SIGKILL and SIGSTOP cannot be caught.\n *\n *\t+----+----+\n *\t|  POSIX signal      |  default action  |\n *\t+----+----+\n"
                + rows + " *\t|  SIGABRT/SIGIOT    |\tterminate \t|\n *\t|  SIGSTOP           |\tstop(*)(+)  \t|\n *\t|  SIGCHLD           |\tignore   \t|\n *\t|  SIGRTMIN-SIGRTMAX |\tterminate       |\n *\t+----+----+\n *\n"
                " * (+) For SIGKILL and SIGSTOP the action is \"always\".\n * (*) Special job control effects:\n * more text.\n */\n")
        parsed = abi.parse_default_actions(text, "include/linux/signal.h")
        self.assertEqual(parsed["signals"]["SIGSTOP"]["action"], "stop")
        self.assertEqual(parsed["signals"]["SIGSTOP"]["markers"], ["*", "+"])
        self.assertIs(parsed["signals"]["SIGABRT"], parsed["signals"]["SIGIOT"])
        self.assertEqual(parsed["realtime"]["action"], "terminate")
        self.assertNotIn("SIGRTMIN-SIGRTMAX", parsed["signals"])
        self.assertEqual(parsed["definitions"], {"ignore": "Nothing Happens", "terminate": "kill the process, similar to exit_group.", "stop": "stop all the threads"})
        self.assertEqual(parsed["notes"], {"+": 'For SIGKILL and SIGSTOP the action is "always".', "*": "Special job control effects: more text."})
        with self.assertRaises(ValueError):
            abi.parse_default_actions("/* nothing here */", "x.h")

    def test_ioctl_number_table_rows_continuations_and_layout_guard(self):
        head = ("intro\n\n====  =====  ======================= ==========\nCode  Seq#    Include File           Comments\n      (hex)\n====  =====  ======================= ==========\n")
        body = "".join("0x{:02X}  all    linux/f{}.h\n".format(i, i) for i in range(1, 200))
        table = head + ("0x00  00-1F  linux/fs.h              conflict!\n'M'   01-16  mtd/mtd-abi.h           conflict!\n      and    drivers/mtd/mtdchar.c\n"
                        "'T'   C0-DF  linux/if_tun.h          note one\n                                     note two\n0xA1  0      linux/vtpm_proxy.h\n") + body + "====  =====  ======================= ==========\n"
        parsed = abi.parse_ioctl_registry(table, "ioctl-number.rst")
        rows = parsed["rows"]
        self.assertEqual(parsed["source"]["line"], 4)
        self.assertEqual(rows[0], {"code": "0x00", "value": 0, "sequence": "00-1F", "range": [0, 31], "includes": ["linux/fs.h"], "comments": ["conflict!"], "line": 7})
        self.assertEqual((rows[1]["value"], rows[1]["range"], rows[1]["includes"]), (ord("M"), [1, 22], ["mtd/mtd-abi.h", "and drivers/mtd/mtdchar.c"]))
        self.assertEqual((rows[2]["code"], rows[2]["comments"]), ("'T'", ["note one", "note two"]))
        self.assertEqual(rows[3]["range"], [0, 0])
        self.assertIsNone(rows[4]["range"])
        with self.assertRaisesRegex(ValueError, "column boundary"):
            abi.parse_ioctl_registry(table.replace("0x00  00-1F  linux/fs.h ", "0x00  00-1F-linux/fs.h ", 1), "x.rst")
        with self.assertRaisesRegex(ValueError, "Unrecognized ioctl code"):
            abi.parse_ioctl_registry(table.replace("0xA1  0 ", "A1    0 ", 1), "x.rst")

    def test_licence_gate_is_the_syscall_importers_plus_one_reviewed_document(self):
        copying = "Being under the terms of the GNU General Public License version 2 only,\n"
        files = {path: {"text": text, "sha256": "0"} for path, text in {
            "COPYING": copying, abi.IOCTL_REGISTRY: "=====\nIoctl Numbers\n=====\n", "include/uapi/asm-generic/errno.h": SPDX}.items()}
        records = {record["path"]: record for record in abi.source_licenses(files, "v9.0")}
        self.assertEqual(records[abi.IOCTL_REGISTRY]["license_basis"], "COPYING")
        self.assertEqual(records["include/uapi/asm-generic/errno.h"]["spdx_license_identifier"], "GPL-2.0 WITH Linux-syscall-note")
        self.assertEqual(records["COPYING"]["role"], "license-notice")
        with self.assertRaisesRegex(ValueError, "Missing SPDX"):
            abi.source_licenses({**files, "include/uapi/asm-generic/ioctl.h": {"text": "#define X 1\n", "sha256": "0"}}, "v9.0")
        with self.assertRaisesRegex(ValueError, "Unreviewed source license"):
            abi.source_licenses({**files, "x.h": {"text": "/* SPDX-License-Identifier: MIT */\n", "sha256": "0"}}, "v9.0")
        with self.assertRaisesRegex(ValueError, "No licence basis"):
            abi.source_licenses({**files, "COPYING": {"text": "something else", "sha256": "0"}}, "v9.0")


class PublishedDataTests(unittest.TestCase):
    """The checked-in JSON must be exactly what the generator derives from the bundled inputs."""

    @classmethod
    def setUpClass(cls):
        with patch.object(abi.sk, "Source", lambda ref, tree=None: StubSource(folder=BUNDLED)):
            cls.documents, cls.files = abi.build(LATEST)

    def test_published_documents_are_reproducible_from_the_bundled_sources(self):
        for name, rebuilt in self.documents.items():
            published = json.loads((PUBLISHED / LATEST / name).read_text())
            rebuilt = json.loads(json.dumps(rebuilt))
            for document in (published, rebuilt):
                document["licensing"].pop("generated_at")
            self.assertEqual(published, rebuilt, name)
        self.assertEqual({p.relative_to(BUNDLED).as_posix() for p in BUNDLED.rglob("*") if p.is_file()}, set(self.files))

    def test_every_architecture_of_the_site_is_covered(self):
        site = json.loads((ROOT / "public/data/manifest.json").read_text())
        self.assertEqual(LATEST, site["latest"])
        for name in ["errno.json", "signals.json", "ioctl.json"]:
            self.assertEqual(list(self.documents[name]["architectures"]), site["version_architectures"][LATEST], name)

    def test_spot_checks_against_the_source_lines(self):
        def line(source):
            return (BUNDLED / source["path"]).read_text().split("\n")[source["line"] - 1]

        errno = self.documents["errno.json"]
        for table in errno["tables"].values():
            for entry in table["entries"]:
                # Each row points at a #define of that very name.
                self.assertRegex(line(entry["source"]), r"^#\s*define\s+{}\b".format(entry["name"]))
                if "alias_of" not in entry:
                    self.assertRegex(line(entry["source"]), r"^#\s*define\s+{}\s+{}\b".format(entry["name"], entry["number"]))
        by_name = {table: {e["name"]: e["number"] for e in errno["tables"][table]["entries"]} for table in errno["tables"]}
        self.assertEqual((by_name["generic"]["ENOENT"], by_name["mips"]["ENOENT"]), (2, 2))
        self.assertIn("#define\tENOSYS\t\t38\t/* Invalid system call number */", (BUNDLED / "include/uapi/asm-generic/errno.h").read_text())
        self.assertEqual(by_name["generic"]["ENOSYS"], 38)
        self.assertRegex((BUNDLED / "arch/mips/include/uapi/asm/errno.h").read_text(), r"#define ENOSYS\s+89\b")
        self.assertEqual(by_name["mips"]["ENOSYS"], 89)
        self.assertEqual((by_name["generic"]["EDEADLOCK"], by_name["powerpc"]["EDEADLOCK"]), (by_name["generic"]["EDEADLK"], 58))
        self.assertEqual({arch: record["table"] for arch, record in errno["architectures"].items() if record["table"] != "generic"},
                         {"ppc64": "powerpc", "ppc": "powerpc", "mips-o32": "mips", "mips-n32": "mips", "mips-n64": "mips"})

        signals = self.documents["signals.json"]
        for table in signals["tables"].values():
            for entry in table["entries"]:
                self.assertRegex(line(entry["source"]), r"^#\s*define\s+{}\s".format(entry["name"]))
            self.assertNotIn("SIGSTKSZ", {e["name"] for e in table["entries"]})
        number = lambda table, name: next(e["number"] for e in signals["tables"][table]["entries"] if e["name"] == name)
        self.assertRegex((BUNDLED / "arch/mips/include/uapi/asm/signal.h").read_text(), r"#define SIGBUS\s+10\b")
        self.assertEqual((number("x86", "SIGBUS"), number("mips", "SIGBUS"), number("mips", "SIGEMT"), number("arm", "SIGSWI")), (7, 10, 7, 32))
        self.assertEqual(signals["tables"]["mips"]["realtime"]["max"]["value"], 128)
        self.assertEqual((signals["tables"]["x86"]["realtime"]["max"]["value"], signals["tables"]["x86"]["realtime"]["max"]["expression"]), (None, "_NSIG"))
        self.assertEqual(signals["architectures"]["riscv64"]["headers"]["signal.h"]["kind"], "mandatory-y")
        self.assertIn("|  SIGQUIT           |\tcoredump \t|", (BUNDLED / "include/linux/signal.h").read_text())
        self.assertEqual(signals["default_actions"]["signals"]["SIGQUIT"]["action"], "coredump")
        self.assertEqual(signals["default_actions"]["signals"]["SIGKILL"]["markers"], ["+"])

        ioctl = self.documents["ioctl.json"]
        command = lambda table, name: next(e for e in ioctl["commands"][table]["entries"] if e["name"] == name)
        self.assertIn("#define TCGETS\t\t0x5401", (BUNDLED / "include/uapi/asm-generic/ioctls.h").read_text())
        self.assertEqual(command("generic-64", "TCGETS")["value"], 0x5401)
        self.assertEqual(command("generic-64", "TIOCGPTN")["value"], 0x80045430)
        self.assertEqual(command("powerpc-64", "TIOCGPTN")["value"], 0x40045430)
        self.assertIsNone(command("generic-64", "TCGETS2")["value"])
        self.assertEqual(command("generic-64", "TCGETS2")["size_type"], "struct termios2")
        self.assertEqual((command("arm", "FIOQSIZE")["value"], command("generic-32", "FIOQSIZE")["value"]), (0x545E, 0x5460))
        self.assertEqual(command("generic-64", "SIOCGSTAMP")["value"], 0x8906)
        self.assertIsNone(command("generic-32", "SIOCGSTAMP")["value"])
        # PowerPC writes four numbers out by hand and states the macro in a comment; both must agree.
        encoding = ioctl["encodings"]["powerpc"]
        for entry in ioctl["commands"]["powerpc-64"]["entries"]:
            stated = re.fullmatch(r"(_IO[RW]+)\('(.)', (\d+), struct termio\)", entry.get("comment") or "")
            if stated:
                fields = encoding["fields"]
                self.assertEqual(entry["value"] >> fields["dir"]["shift"], encoding["macros"][stated[1]]["value"], entry["name"])
                self.assertEqual((entry["value"] >> fields["type"]["shift"] & 0xFF, entry["value"] & 0xFF), (ord(stated[2]), int(stated[3])), entry["name"])
        self.assertEqual(sum(1 for e in ioctl["commands"]["powerpc-64"]["entries"] if (e.get("comment") or "").endswith("struct termio)")), 4)
        names = {e["name"] for table in ioctl["commands"].values() for e in table["entries"]}
        self.assertFalse({name for name in names if name.startswith(abi.IOCTL_FLAG_PREFIXES)} | ({"SOCK_IOC_TYPE"} & names))

        registry = self.documents["ioctl-numbers.json"]
        text = (BUNDLED / abi.IOCTL_REGISTRY).read_text().split("\n")
        for row in registry["rows"]:
            self.assertTrue(text[row["line"] - 1].startswith(row["code"]), row)
            self.assertIn(row["sequence"], text[row["line"] - 1])
        self.assertTrue(any(row["code"] == "'T'" and row["includes"] == ["linux/if_tun.h"] and row["range"] == [0xC0, 0xDF] for row in registry["rows"]))

    def test_publish_is_atomic_idempotent_and_keeps_other_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "abi"
            abi.publish(output, LATEST, self.documents, self.files)
            first = {p.relative_to(output).as_posix(): p.stat().st_mtime_ns for p in output.rglob("*") if p.is_file()}
            self.assertEqual(json.loads((output / "manifest.json").read_text())["versions"], [LATEST])
            later = json.loads(json.dumps(self.documents))
            for document in later.values():
                document["licensing"]["generated_at"] = "2099-01-01T00:00:00+00:00"
            abi.publish(output, LATEST, later, self.files)
            self.assertEqual(first, {p.relative_to(output).as_posix(): p.stat().st_mtime_ns for p in output.rglob("*") if p.is_file()})
            older = json.loads(json.dumps(self.documents).replace(LATEST, "v1.5"))
            abi.publish(output, "v1.5", older, self.files)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual((manifest["versions"], manifest["latest"]), ([LATEST, "v1.5"], LATEST))
            (output / LATEST / "errno.json").write_text("{}")
            abi.publish(output, LATEST, self.documents, self.files)
            self.assertEqual(json.loads((output / LATEST / "errno.json").read_text())["kind"], "errno")
            self.assertFalse(list(output.glob(".tmp-*")))

    def test_a_syscall_sync_leaves_the_abi_folder_alone(self):
        # mirror_active() and prune_revisions() only touch what the syscall manifest names.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "revisions/v9.0/a").mkdir(parents=True)
            (output / "revisions/v9.0/a/x64.json").write_text("{}")
            (output / "abi/v9.0").mkdir(parents=True)
            (output / "abi/v9.0/errno.json").write_text("{}")
            (output / "abi/manifest.json").write_text("{}")
            paths = {"v9.0": "revisions/v9.0/a"}
            abi.sk.mirror_active(output, paths)
            abi.sk.prune_revisions(output, paths)
            self.assertTrue((output / "v9.0/x64.json").is_file())
            self.assertEqual(sorted(p.relative_to(output).as_posix() for p in (output / "abi").rglob("*") if p.is_file()), ["abi/manifest.json", "abi/v9.0/errno.json"])


if __name__ == "__main__":
    unittest.main()
