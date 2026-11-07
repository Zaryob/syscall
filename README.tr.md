<!-- SPDX-License-Identifier: GPL-2.0-only -->
# Linux System Call Reference

[English](README.md) · **Türkçe**

Linux kaynaklarından üretilen, aranabilir sistem çağrısı tabloları: C imzaları,
register kuralları ve sürüm karşılaştırmaları. Arayüz Türkçe/İngilizce dil seçimi
ve açık/koyu tema sunar.

## Yerelde çalıştırma

Ruby 3.3+, Bundler ve Python 3.9+ gerekir. npm kısayolları, testler ve yerel API
için Node.js 22+ kullanılır. Yayımlanan site statiktir.

```sh
python3 scripts/jekyll.py install
npm start
# http://127.0.0.1:5173

npm run dev   # Jekyll serve + live reload
npm run build # Statik API/kaynak arşivi, Jekyll build ve çıktı kontrolü
npm test      # Veri, baseurl, opsiyonel API ve importer testleri
```

Node olmadan çalıştırmak için:

```sh
python3 scripts/prepare_site.py
python3 scripts/jekyll.py serve --port 5173
```

`jekyll.py`, PATH veya Homebrew üzerinden Ruby 3.3+ seçer ve gem’leri
`vendor/bundle/` dizinine kurar. Derleme repodaki kernel verilerini kullanır.

## GitHub Pages'te yayımlama

Repo **Settings → Pages → Build and deployment → Source** ayarını
**GitHub Actions** yapın. `main` dalına push edin veya **Build and deploy Jekyll**
iş akışını elle başlatın. İş akışı testleri çalıştırır, Chromium’da alt yol
derlemesini kontrol eder ve doğrulanan siteyi yayımlar. Pull request’lerde
yalnızca derleme ve doğrulama çalışır. [Yayın iş akışı](.github/workflows/pages.yml)

GitHub Pages dışındaki statik hosting'ler için `npm run build` sonrasında
`_site/` içeriğini yayımlayın. Alt yolda yayımlamak için:

```sh
python3 scripts/prepare_site.py
python3 scripts/jekyll.py build --baseurl /syscall
python3 scripts/check_site.py --baseurl /syscall
```

Kaynak arşivini, lisans metinlerini ve `data/` altındaki kernel girdilerini
yayımlanan çıktıyla birlikte tutun.

## Özellikler

- 12 Linux ABI’si: x64, x86, arm64, ARM EABI, riscv64, loongarch64, PowerPC 32/64, s390x ve MIPS o32/n32/n64. PowerPC, s390x ve MIPS tabloları repodaki `v5.19` ve sonrası veri kümelerinde bulunur.
- Türkçe ve İngilizce kısa açıklamalar; ne işe yaradığına, adına, çekirdek giriş noktasına, C argümanına veya numarasına göre arama. Açıklamalar [notes.mjs](public/notes.mjs) dosyasında tutulur.
- Artan/azalan isim ve numara sıralaması; hexadecimal gösterim.
- Syscall detayında C bildirimi, kernel kaynak satırı, man-page bağlantısı ve JSON.
- İlk görünümde çağrının amacı; Argümanlar görünümünde ARG1–ARG6 sütunları. Yatay kaydırırken çağrı numarası ve adı sabit kalır.
- Seçilen kernel numarası ve ABI ile indirilebilir C örneği/iskeleti üretimi.
- 64-bit mimarilerde argüman register’ları; 32-bit ABI’ler için açık hizalama notları.
- Sürümler arası eklenen, kaldırılan ve imzası değişen kayıtlar.
- URL’de korunan mimari, sürüm, karşılaştırma, arama, tablo görünümü ve açık syscall detayı.
- JSON indirme, statik JSON API ve isteğe bağlı yerel HTTP API.
- Dar ekranlarda yatay kaydırılabilen tablo ve klavyeyle kullanılabilir kontroller.

## Veriyi doğrudan kernel’den üretme

Python 3.9+ gerekir. Tarihsel başlıkları okumak için Clang veya GCC
önişlemcisi kullanılır.

```sh
npm run sync
python3 scripts/sync_kernel.py --refs v7.3
python3 scripts/sync_kernel.py --refs v6.12 v6.18 v7.3

# Ağ kullanmadan, Makefile sürümüyle eşleşen bir Linux checkout’undan:
python3 scripts/sync_kernel.py --refs v7.3 --kernel-tree /path/to/linux

# Ayrı bir çıktı dizini:
python3 scripts/sync_kernel.py --refs v7.3 --output /tmp/syscall-data
```

Importer, repoda bulunan tarihsel başlık düzenlerini ve güncel `.tbl` tablolarını
destekler. Yeni bir sürümü varsayılanlara eklemeden önce importer ve testleri
çalıştırın. Desteklenmeyen biçimlerde hata verir.

Numaralar ve ABI’ler `arch/*/.../syscall*.tbl` ve `scripts/syscall.tbl` dosyalarından
gelir. MIPS’te tablo indeksi, UAPI `unistd.h` dosyasındaki ABI tabanına eklenerek
gerçek çağrı numarası bulunur. Ortak tabloyu kullanan mimarilerde `Makefile.syscalls` içindeki
`syscall_abis_64` ekleri okunur. C argümanları `include/linux/syscalls.h`,
`include/linux/compat.h` ve mimariye ait `asm/syscalls.h` dosyalarından alınır.
Giriş sembolüyle tam eşleşme aranır; farklı bir ABI’den benzer isimli imza seçilmez.

İndirilen kaynaklar `.cache/` içinde saklanır (Git’e dahil değildir).
Tekrar indirmek için ilgili `.cache/<tag>/` dizinini kaldırabilirsiniz.
Her JSON dosyası kullanılan kaynak dosyalarının SHA-256 özetlerini ve özgün
SPDX lisanslarını taşır. Kaynak dosyaların tamamı, copyright bildirimleri ve
kernel lisans metinleriyle birlikte `public/data/<tag>/sources/` altında bulunur;
listesi aynı dizinin yanındaki `sources.json` dosyasındadır. Yeni bir kaynak
dosyasının lisansı tanınmıyorsa importer veri yayımlamadan durur.
Yerel ağaçtan üretilen veride varsa Git commit’i de kaydedilir; özetler yerel
değişiklikleri kapsar. İstenen tüm sürümlerin tabloları ve kaynak hash’leri
doğrulandıktan sonra manifest tek işlemde güncellenir. Yayımlanmış bir sürümü
yeniden içe aktarmak `data/revisions/` altında yeni bir veri kümesi oluşturur.
Manifestteki `version_paths` ve statik API dizini etkin revizyonu gösterir.
Önceki indirme adresleri kendi veri kümelerini sunmaya devam eder.

## Statik JSON API

Jekyll/GitHub Pages üzerinde aşağıdaki dosyalar doğrudan sunulur. Repo alt
yolunda URL'nin başına o yol eklenir; site bağlantıları bunu otomatik yapar.

```sh
curl 'http://127.0.0.1:5173/api/v1/index.json'
curl 'http://127.0.0.1:5173/api/v1/architectures.json'
curl 'http://127.0.0.1:5173/api/v1/versions.json'
curl 'http://127.0.0.1:5173/data/v7.3/x64.json'
curl 'http://127.0.0.1:5173/data/v7.3/sources.json'
```

Arama ve sürüm farkı tarayıcıda hesaplanır. Statik dosyalardaki query parametreleri
filtreleme yapmaz. Tek kayıt için detay panelindeki **Download entry JSON**
düğmesi, lisans ve kaynak bilgilerini de içeren dosyayı indirir. CLI örneği:

```sh
curl 'http://127.0.0.1:5173/data/v7.3/x64.json' | jq '.syscalls[] | select(.name == "read")'
```

Önceki dinamik API, gerekirse yerelde ayrı bir süreç olarak kullanılabilir:

```sh
npm run api  # http://127.0.0.1:5174; HOST ve PORT ile değiştirilebilir
curl 'http://127.0.0.1:5174/api/v1/syscalls/x64/read?version=v7.3'
curl 'http://127.0.0.1:5174/api/v1/syscalls/x64/diff?from=v6.12&version=v7.3'
```

Bu opsiyonel Node sunucusu Jekyll sitesini sunmaz; yalnızca JSON API'si ve ilgili
veri dosyalarını sağlar. Yayımlanan statik site bu sürece bağlantı kurmaz.

## Otomatik C örnekleri

Syscall detayını açınca **C usage example** veya **Generate a C skeleton**
bölümü görünür. **Download C example/skeleton** ile `.c` dosyası indirilebilir.
İşlem tarayıcıda, `public/examples.mjs` içindeki kurallarla çalışır; AI servisi,
backend veya API anahtarı gerektirmez. Jekyll'in statik çıktısında da çalışır.

`getpid` ve `write` için elle yazılmış kullanım şablonlarına seçilen mimarinin
kernel tablosundaki numara eklenir. `write` örneği kısmi yazma ve EINTR durumunu
ele alır. Diğer çözülen 64-bit imzalar C iskeleti verir: TODO argümanları,
çağrıya özel dönüş/hata işleme notu ve inceleme yapılana kadar derlemeyi
durduran `#error` içerir. Argümansız çağrılar da otomatik olarak zararsız sayılmaz.

Kernel prototipleri geçerli dosya tanımlayıcılarını, pointer yaşam sürelerini,
struct içeriklerini ve bayrak kombinasyonlarını belirlemeye yetmez. İskeletler
çalışan kullanım örneği olarak sunulmaz. 32-bit ABI'ler, çözülmemiş imzalar ve
unimplemented slotlar için kod üretilmez. Hazır C şablonları Linux hedefi için
sözdizimi kontrolünden geçirilir; gerçek kernel üzerinde çalışma testi yapılmaz.
Site üretilen kodu çalıştırmaz. Numara sabitleri nedeniyle kod seçilen Linux
mimarisi için derlenmelidir; üretilen dosya buna ilişkin bir derleme kontrolü taşır.

## Doğruluk sınırları

- Kapsam işlemci modeline değil Linux kullanıcı alanı ABI’sine göre ayrılır.
  x86-64 Linux çalıştıran Intel Core ve AMD Ryzen aynı tabloyu kullanır.
  Karşılaştırma, çağrının ilk eklendiği sürümü göstermez.
- İmzalar kernel C bildirimleridir, libc wrapper prototipleri değildir. Bildirimde
  argüman adı yoksa sadece tipi gösterilir. Birden fazla CONFIG dalı farklı bir
  imza veriyorsa (ör. `clone`) imza belirsiz olarak işaretlenir.
- Assembly wrapper’ları, header’da bulunmayan mimari çağrıları ve bazı legacy
  imzalar `arguments: null` olur; sıfır argüman ise `arguments: []` olarak ayrılır.
- `sys_ni_syscall` ve giriş noktası olmayan slotlar `unimplemented` olarak
  saklanır ve varsayılan görünümden çıkarılır. Bir tablodaki tanım, her CONFIG
  kombinasyonunda çağrının kullanılabilir olacağı anlamına gelmez. PowerPC 32 ve MIPS o32
  tabloları yerel giriş noktalarını gösterir; 64 bit çekirdekler aynı numara için
  uyumluluk giriş noktası kullanabilir.
- ARM özel `__ARM_NR_*` çağrıları, OABI ve x32 bu sürümün kapsamı dışındadır.
- Sürüm karşılaştırması numara+isim kimliği, giriş sembolü, durum ve argümanları
  karşılaştırır; kaynak satır numarasının değişmesi tek başına değişiklik değildir.
- Register kuralları [syscall(2)](https://man7.org/linux/man-pages/man2/syscall.2.html)
  kaynağından elle tanımlanmıştır. 32-bit argümanları otomatik register’lara bölmeyiz.
- İlişkili çağrılar aynı kılavuz sayfasını paylaşabilir; bazı çağrıların kılavuz sayfası yoktur.

## Kaynaklar ve lisans

Uygulama ve üretilen JSON derlemesi **GPL-2.0-only** lisanslıdır; [LICENSE](LICENSE).
Kernel’den alınan dosyaların özgün lisansları, copyright bildirimleri ve varsa
`Linux-syscall-note` istisnası korunur. Bu istisna uygulamanın tamamına veya
kernel’in iç header’larına genellenmez. Dağıtım kapsamı ve kaynakların
korunması için [LICENSING.md](LICENSING.md) ve
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) dosyalarına bakın.
Kaynak dağıtımında bu repo, generator, kullanılan kernel girdileri ve lisans
metinleri birlikte tutulmalıdır. Web arayüzünün altbilgisinde de lisans ve
kaynak bildirimleri bulunur.
GNU veya Free Software Foundation ile resmî ortaklık yoktur.

## Man bağlantıları ve üretilen metadata

İçe aktarıcı, man bağlantılarını `sources/manual-pages.json` içindeki man7 sayfa
adlarıyla eşler. Açıklama takma adları ve time64 ABI adları aynı belgelenmiş
sayfayı kullanabilir; POSIX mesaj kuyrukları için bölüm 3 bağlantıları da
korunur. Karşılığı olmayan sayfalarda `man_url: null` üretilir; arayüz durumu
açıkça belirtir ve çekirdek kaynağına erişimi korur.

Sayfa listesini `python3 scripts/sync_manual_pages.py` ile yenileyebilir,
`--check` ile yazmadan karşılaştırabilirsiniz. Ardından snapshot'ları yeniden
üretin. Yerel Linux ağacı ve depodaki sayfa kataloğuyla çekirdek içe aktarımı
çevrimdışı çalışır. Katalog man metinlerini içermez; uzak bağlantıların süresiz
olarak erişilebilir kalacağını garanti etmez.

`prepare_site.py`, arama indeksi, statik örnekler ve indirme bağlantıları için
manifestteki son sürümü ve etkin revizyonu kullanır. Arama URL'leri uygulama
köküne görelidir; sitemap mimarileri manifestten alır. npm yerine Jekyll'i
doğrudan çalıştırırken önce hazırlama betiğini çalıştırın.

## Gezinme ve ABI başvuru notları

Mimari, sürüm, karşılaştırma, tablo görünümü, sayı biçimi ve detay seçimleri
tarayıcı geçmişine adım ekler. Arama yazmak veya temizlemek geçerli adımı yeniler.
Geri/İleri URL’deki seçimi, açıkça belirtilmiş dili ve detay kimliğini geri yükler;
eski bekleyen veri yüklemeleri sonraki seçimi değiştiremez.

Çağrı kuralları tablosu RET2 ve x86-64 komutunun bozduğu yazmaçları gösterir;
notlar eax/w8 numaralandırmasını, PPC sc ve özellik denetimli PPC64 scv 0 farkını
açıklar. Kısa tablo tam bir assembly yazmaç koruma sözleşmesi değildir. Bu editoryal
notlar değişmez snapshot metaverisini değiştirmez. LTS işaretleri
[kernel.org](https://www.kernel.org/category/releases.html) verisine göre
7 Kasım 2026 tarihlidir; kayıtlı snapshot bakım yaması içermez.

Sistem çağrısı araması tarayıcıda çalışır. Sayfa ayrıca üçüncü taraf Umami Cloud
betiğini (`cloud.umami.is/script.js`) yükler ve ziyaret analitiği gönderir.
[Umami veri toplama açıklaması](https://docs.umami.is/docs/collect-data).

SPDX öncesi UAPI girdilerindeki `GPL-2.0-only` / `license_basis: COPYING` yedeği,
örneğin v3.7 COPYING başındaki normal sistem çağrısı kullanıcı programı notunu
ortadan kaldırmaz. Tarihsel kaynağa yeni SPDX ifadesi eklenmez; özgün bildirim
dosyayla birlikte okunur. Bu açıklama hukuki kullanım hükmü değildir.
[Kaynak bildirimleri ve kapsam](LICENSING.md).
