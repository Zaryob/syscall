// SPDX-License-Identifier: GPL-2.0-only
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { buildExample } from '../public/examples.mjs';

const load = async arch => JSON.parse(await readFile(new URL(`../public/data/v7.3/${arch}.json`, import.meta.url), 'utf8'));

test('examples use selected architecture numbers and distinguish reviewed templates from incomplete skeletons', async () => {
  for (const arch of ['x64', 'arm64', 'riscv64', 'loongarch64']) {
    const snapshot = await load(arch);
    for (const name of ['write', 'getpid']) {
      const row = snapshot.syscalls.find(r => r.name === name);
      const generated = buildExample(row, snapshot);
      assert.equal(generated.kind, 'example');
      assert.ok(generated.code.includes(`syscall(${row.number}L`));
      assert.ok(generated.code.includes(`Build this example for Linux ${arch}.`));
      assert.ok(!generated.code.includes('TODO_ARG'));
      assert.match(generated.code, /SPDX-License-Identifier: GPL-2.0-only/);
    }
    const openat = snapshot.syscalls.find(r => r.name === 'openat');
    const skeleton = buildExample(openat, snapshot);
    assert.equal(skeleton.kind, 'skeleton');
    assert.match(skeleton.code, /^#error "Review this syscall/m);
    assert.equal((skeleton.code.match(/TODO_ARG\d/g) || []).length, openat.arguments.length);
    assert.match(skeleton.code, /TODO: Handle this syscall's specific return/);
  }
});

test('unimplemented, ambiguous and 32-bit signatures do not produce speculative examples', async () => {
  const x64 = await load('x64');
  for (const row of [x64.syscalls.find(r => r.status === 'unimplemented'), x64.syscalls.find(r => r.arguments === null)]) {
    assert.equal(buildExample(row, x64).code, null);
  }
  for (const arch of ['arm', 'x86']) {
    const snapshot = await load(arch);
    const example = buildExample(snapshot.syscalls.find(r => r.name === 'write'), snapshot);
    assert.equal(example.kind, 'unavailable');
    assert.match(example.reason, /32-bit/);
  }
  const unknownZeroArg = x64.syscalls.find(r => r.name === 'fork');
  assert.equal(buildExample(unknownZeroArg, x64).kind, 'skeleton');
  assert.match(buildExample(unknownZeroArg, x64).code, /^#error "Review/m);
});

test('both ready templates pass Linux-target C syntax checks', async t => {
  const probe = spawnSync('cc', ['--version'], { encoding: 'utf8' });
  if (probe.error || !['darwin', 'linux'].includes(process.platform)) return t.skip('C compiler on Linux/macOS required');
  const directory = await mkdtemp(path.join(tmpdir(), 'syscall-example-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  // Minimal declarations permit a Linux-target syntax check on macOS as well.
  // This does not run the generated syscall or claim runtime verification.
  await writeFile(path.join(directory, 'unistd.h'), 'typedef __SIZE_TYPE__ size_t;\n#define STDOUT_FILENO 1\nlong syscall(long, ...);\n');
  await writeFile(path.join(directory, 'stdio.h'), 'typedef struct FILE FILE;\nextern FILE *stderr;\nint printf(const char *, ...);\nvoid perror(const char *);\nint fputs(const char *, FILE *);\n');
  await writeFile(path.join(directory, 'errno.h'), 'extern int errno;\n#define EINTR 4\n');
  const snapshot = await load('x64');
  for (const name of ['write', 'getpid']) {
    const { code } = buildExample(snapshot.syscalls.find(r => r.name === name), snapshot);
    const file = path.join(directory, name + '.c');
    await writeFile(file, code);
    const target = process.platform === 'darwin' ? ['--target=x86_64-linux-gnu'] : [];
    const compiled = spawnSync('cc', [...target, '-std=c11', '-Werror', '-fsyntax-only', '-nostdinc', '-I', directory, file], { encoding: 'utf8' });
    assert.equal(compiled.status, 0, compiled.stderr);
  }
});

test('write example retries EINTR, advances after partial writes and rejects zero progress', async t => {
  if (!['darwin', 'linux'].includes(process.platform) || spawnSync('cc', ['--version']).error) return t.skip('Native C compiler required');
  const directory = await mkdtemp(path.join(tmpdir(), 'syscall-write-loop-'));
  t.after(() => rm(directory, { recursive: true, force: true }));
  await writeFile(path.join(directory, 'unistd.h'), 'typedef __SIZE_TYPE__ size_t;\n#define STDOUT_FILENO 1\n#define syscall fake_syscall\nlong fake_syscall(long, ...);\n');
  await writeFile(path.join(directory, 'stdio.h'), 'typedef struct FILE FILE;\n#define stderr fake_stderr\n#define perror fake_perror\n#define fputs fake_fputs\nextern FILE *fake_stderr;\nvoid fake_perror(const char *);\nint fake_fputs(const char *, FILE *);\n');
  await writeFile(path.join(directory, 'errno.h'), '#define errno fake_errno\nextern int fake_errno;\n#define EINTR 4\n');
  const snapshot = await load('x64');
  let { code } = buildExample(snapshot.syscalls.find(r => r.name === 'write'), snapshot);
  // Compile its control flow against fake syscall/stdio functions. No real
  // kernel call is made, and this test does not certify Linux runtime behavior.
  code = code.replace(/^#if !defined\(__linux__\).*$/m, '#if 0').replace('int main(void)', 'int example_main(void)');
  const harness = `
int fake_errno;
FILE *fake_stderr;
void fake_perror(const char *s) { (void)s; }
int fake_fputs(const char *s, FILE *f) { (void)s; (void)f; return 0; }
static int calls, failed, zero_mode;
static const char *start;
long fake_syscall(long number, ...) {
    __builtin_va_list args;
    __builtin_va_start(args, number);
    long fd = __builtin_va_arg(args, long);
    const char *buffer = __builtin_va_arg(args, const char *);
    size_t count = __builtin_va_arg(args, size_t);
    __builtin_va_end(args);
    int call = calls++;
    if (number != 1 || fd != 1) failed = 1;
    if (zero_mode) return 0;
    const size_t length = sizeof("Hello from a Linux syscall!\\n") - 1;
    if (call == 0) {
        start = buffer;
        if (count != length) failed = 1;
        fake_errno = EINTR;
        return -1;
    }
    if (call == 1) {
        if (buffer != start || count != length) failed = 1;
        return 3;
    }
    if (call == 2) {
        if (buffer != start + 3 || count != length - 3) failed = 1;
        return (long)count;
    }
    failed = 1;
    return -1;
}
int main(void) {
    if (example_main() != 0 || calls != 3 || failed) return 10;
    zero_mode = 1; calls = 0;
    if (example_main() != 1 || calls != 1) return 11;
    return 0;
}
`;
  const file = path.join(directory, 'loop.c');
  const binary = path.join(directory, 'loop');
  await writeFile(file, code + harness);
  const compiler = spawnSync('cc', ['-std=c11', '-fno-builtin', '-nostdinc', '-I', directory, file, '-o', binary], { encoding: 'utf8' });
  assert.equal(compiler.status, 0, compiler.stderr);
  const result = spawnSync(binary, [], { encoding: 'utf8', timeout: 5000 });
  assert.equal(result.status, 0, result.error?.message || result.stderr);
});
