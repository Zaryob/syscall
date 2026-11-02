// SPDX-License-Identifier: GPL-2.0-only
// These templates are our own code. Kernel declarations provide structure,
// not the semantics needed to invent valid pointers, flags or object lifetimes.
const guards = {
  x64: 'defined(__x86_64__) && !defined(__ILP32__)',
  arm64: 'defined(__aarch64__) && !defined(__ILP32__)',
  riscv64: 'defined(__riscv) && __riscv_xlen == 64 && __SIZEOF_POINTER__ == 8',
  loongarch64: 'defined(__loongarch__) && __loongarch_grlen == 64 && __SIZEOF_POINTER__ == 8',
};

export function buildExample(row, snapshot) {
  const unavailable = reason => ({ kind: 'unavailable', reason, code: null });
  if (row.status !== 'defined') return unavailable('This table slot is unimplemented; no example is generated.');
  if (row.arguments === null) return unavailable('The kernel signature is unresolved. An example would require guessing the arguments.');
  if (snapshot.calling_convention.bits !== 64 || !guards[snapshot.architecture]) {
    return unavailable('Automatic C templates currently support the four 64-bit ABIs. On 32-bit ABIs, wide arguments may require manual splitting and alignment.');
  }
  const { architecture, kernel } = snapshot;
  const preamble = `// SPDX-License-Identifier: GPL-2.0-only
// ${row.name}: Linux ${kernel}, ${architecture}, syscall number ${row.number}.
// Generated from the selected kernel snapshot; not executed by this website.
#define _GNU_SOURCE
#include <unistd.h>
#include <stdio.h>
#include <errno.h>

#if !defined(__linux__) || !(${guards[architecture]})
#error "Build this example for Linux ${architecture}."
#endif

`;
  let body;
  let kind = 'skeleton';
  let reason = 'Generated C skeleton. Replace every TODO with valid userspace values and consult the manual for flags, buffer sizes, ownership and error handling. The compile-time error is intentional until you review it.';

  if (row.name === 'getpid' && row.entry === 'sys_getpid' && row.arguments.length === 0) {
    kind = 'example';
    reason = 'A hand-written getpid template with the number and ABI filled from this kernel snapshot. Build and run it on the selected Linux architecture; this website does not run it.';
    body = `int main(void)
{
    long pid = syscall(${row.number}L);
    if (pid == -1) {
        perror("getpid");
        return 1;
    }
    printf("PID: %ld\\n", pid);
    return 0;
}
`;
  } else if (row.name === 'write' && row.entry === 'sys_write' && row.arguments.length === 3) {
    kind = 'example';
    reason = 'A hand-written stdout example with the number and ABI filled from this snapshot. It handles interrupted and partial writes. Build and run it on the selected Linux architecture; this website does not run it.';
    body = `int main(void)
{
    const char message[] = "Hello from a Linux syscall!\\n";
    size_t offset = 0;
    const size_t length = sizeof(message) - 1;
    while (offset < length) {
        long written = syscall(${row.number}L, (long)STDOUT_FILENO,
                               message + offset, length - offset);
        if (written == -1) {
            if (errno == EINTR) continue;
            perror("write");
            return 1;
        }
        if (written == 0) {
            fputs("write made no progress\\n", stderr);
            return 1;
        }
        offset += (size_t)written;
    }
    return 0;
}
`;
  } else {
    // Even argument-free calls can have effects requiring semantic review.
    const values = row.arguments.map((arg, i) => `        /* ARG${i + 1}: ${arg} */ TODO_ARG${i + 1}`);
    const call = values.length ? `syscall(${row.number}L,\n${values.join(',\n')})` : `syscall(${row.number}L)`;
    body = `#error "Review this syscall, replace TODO arguments, then remove this line."

int main(void)
{
    long result = ${call};
    /* TODO: Handle this syscall's specific return and error semantics. */
    (void)result;
    return 0;
}
`;
  }
  return { kind, reason, code: preamble + body, filename: `${row.name}-${architecture}-${kernel}.c` };
}
