// SPDX-License-Identifier: GPL-2.0-only
// Editorial supplements: existing immutable kernel snapshots keep their original metadata.
// Sources: syscall(2), Linux v7.3 entry_64.S and Documentation/arch/powerpc/syscall64-abi.rst.
export const secondResult = arch => ({
  x64: 'rdx', x86: 'edx', arm64: 'x1', arm: 'r1', riscv64: 'a1', s390x: 'r3',
  'mips-o32': 'v1', 'mips-n32': 'v1', 'mips-n64': 'v1',
}[arch] ?? '—');
// Dated editorial status, not inferred from the snapshot tag or a promise of maintenance.
export const releaseLabel = version => version.slice(1) + (['v6.18', 'v6.12', 'v6.6'].includes(version) ? ' · LTS' : '');
export function referenceCopy(language) {
  return language === 'tr' ? {
    notCatalogued: 'Listelenmedi',
    advancedOptions: 'Diğer filtreler ve sürüm notları',
    sourceDetails: 'Anlık görüntülerin kapsamı ve sınırları',
    sourcesTitle: 'Kaynaklar ve yöntem',
    apiTitle: 'JSON başvurusu',
    syntaxLegend: '<span class="c-type">C türü</span> · <span class="c-name">parametre</span>',
    sourceIntro: '<p>Tablolar <a href="https://github.com/torvalds/linux">Linux çekirdeğinin kaynak kodundan</a> üretilir. Mimariye özgü <code>.tbl</code> dosyaları çağrı numaralarını ve giriş noktalarını sağlar.</p><p>C bildirimleri <code>include/linux/syscalls.h</code>, <code>compat.h</code> ve mimariye özgü başlık dosyalarından alınır. ABI seçimi çekirdekteki <code>Makefile.syscalls</code> dosyasını izler. Yazmaç kuralları <a href="https://man7.org/linux/man-pages/man2/syscall.2.html">Linux man-pages</a> belgelerinde açıklanır.</p>',
    staticIndex: 'A’dan Z’ye tüm sistem çağrıları',
    staticCall: 'Bu çağrının kalıcı sayfası (tüm ABI’ler)',
    secondResult: 'DÖNÜŞ2',
    clobber: 'Bozulan',
    configuration: 'Bu ABI için bildirimi mimarinin Kconfig seçimleri belirler:',
    fallback: 'Bu sürümün çekirdek kaynaklarında bu ABI için bu giriş noktasının tanımı yok; yalnız ENOSYS yedeği var. Çağrı ENOSYS döner. Kaynak:',
    availability: 'Tabloda yer almak, çağrının her çekirdekte bulunduğu anlamına gelmez: isteğe bağlı çağrıların çoğu, ilgili yapılandırma seçeneği veya mimari desteği derlenmemişse ENOSYS döner.',
    compareHelp: 'Karşılaştırma için bu ABI’nin en az iki kayıtlı sürümü gerekir.',
    releaseHelp: 'LTS işaretleri 7 Kasım 2026 tarihli kernel.org durumudur. Seçici yalnız bu referansta kayıtlı sürümleri gösterir; bakım yaması içermez.',
    abiNotes: '<p>NR için rax/x8, yazmacın 64 bit görünümüdür; x86-64 numarayı alt 32 bitten alır (eax), AArch64 ise w8 kullanır. RET2 yalnız ikinci sonuç kullanan çağrılar içindir; “—” listelenmiş ikinci yazmaç olmadığını belirtir. Bozulan sütunu yalnız x86-64 syscall komutunun rcx/r11 etkisini listeler; diğer ABI’ler için tam yazmaç koruma sözleşmesi değildir. <a href="https://man7.org/linux/man-pages/man2/syscall.2.html">syscall(2)</a>.</p><p>PPC32 ve PPC64 sc girişinde hata: cr0.SO=1 ve r3 pozitif errno. PPC64, Linux 5.9’dan beri AT_HWCAP2 içinde PPC_FEATURE2_SCV varsa scv 0 kullanabilir; hata r3 içinde -4095…-1’dir, cr0.SO hata göstergesi değildir. scv, sc ile farklı yazmaç koruma kurallarına sahiptir. <a href="https://docs.kernel.org/arch/powerpc/syscall64-abi.html">PPC64 ABI</a> · <a href="https://github.com/torvalds/linux/blob/v7.3/arch/powerpc/kernel/interrupt.c">PPC hata dönüşü</a>.</p>',
    analytics: 'Bu sayfa üçüncü taraf Umami Cloud ve Google Analytics betiklerini yükler ve ziyaret analitiği gönderir; Google Analytics çerez kullanır. Sistem çağrısı araması tarayıcıda yapılır. <a href="https://docs.umami.is/docs/collect-data">Umami veri toplama açıklaması</a> · <a href="https://policies.google.com/technologies/partner-sites?hl=tr">Google verileri nasıl kullanır</a>.',
  } : {
    notCatalogued: 'Not catalogued',
    advancedOptions: 'More filters and release notes',
    sourceDetails: 'Scope and limits of these snapshots',
    sourcesTitle: 'Sources and method',
    apiTitle: 'JSON reference',
    syntaxLegend: '<span class="c-type">C type</span> · <span class="c-name">parameter</span>',
    sourceIntro: '<p>The tables are generated from the <a href="https://github.com/torvalds/linux">Linux kernel source</a>. Architecture-specific <code>.tbl</code> files supply call numbers and entry points.</p><p>C declarations come from <code>include/linux/syscalls.h</code>, <code>compat.h</code>, and architecture headers. ABI selection follows the kernel’s <code>Makefile.syscalls</code>. Register conventions are documented in <a href="https://man7.org/linux/man-pages/man2/syscall.2.html">Linux man-pages</a>.</p>',
    staticIndex: 'All system calls A–Z',
    staticCall: 'Permanent page for this call (all ABIs)',
    secondResult: 'RET2',
    clobber: 'Clobber',
    configuration: 'The architecture’s Kconfig selections determine the declaration for this ABI:',
    fallback: 'This release’s kernel sources define no implementation of this entry point for this ABI, only the ENOSYS fallback. The call returns ENOSYS. Source:',
    availability: 'A table entry does not mean the call exists in every kernel: most optional calls return ENOSYS when the matching configuration option or architecture support is not built.',
    compareHelp: 'Comparison requires at least two bundled releases for this ABI.',
    releaseHelp: 'LTS labels reflect kernel.org on 7 November 2026. Only bundled releases are listed; snapshots do not include maintenance patches.',
    abiNotes: '<p>NR uses the 64-bit register names rax/x8; x86-64 takes the low 32 bits (eax), and AArch64 uses w8. RET2 applies only to calls using a second result; “—” means no second register is listed. Clobber lists only the x86-64 syscall instruction’s rcx/r11 effects, not the full register preservation contract for other ABIs. <a href="https://man7.org/linux/man-pages/man2/syscall.2.html">syscall(2)</a>.</p><p>PPC32 and PPC64 sc report errors with cr0.SO=1 and positive errno in r3. Since Linux 5.9, PPC64 can use scv 0 when AT_HWCAP2 advertises PPC_FEATURE2_SCV; errors are -4095…-1 in r3, without cr0.SO as an error indicator. scv has different register preservation rules from sc. <a href="https://docs.kernel.org/arch/powerpc/syscall64-abi.html">PPC64 ABI</a> · <a href="https://github.com/torvalds/linux/blob/v7.3/arch/powerpc/kernel/interrupt.c">PPC error return</a>.</p>',
    analytics: 'This page loads the third-party Umami Cloud and Google Analytics scripts and sends visit analytics; Google Analytics sets cookies. Syscall search runs in your browser. <a href="https://docs.umami.is/docs/collect-data">Umami data collection</a> · <a href="https://policies.google.com/technologies/partner-sites">How Google uses data</a>.',
  };
}
