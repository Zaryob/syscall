<!-- SPDX-License-Identifier: GPL-2.0-only -->
# Linux System Call Reference

[English](README.md) · **Türkçe**

Linux kaynaklarından üretilen, aranabilir sistem çağrısı tabloları: C imzaları,
register kuralları ve sürüm karşılaştırmaları. Arayüz Türkçe/İngilizce dil seçimi
ve açık/koyu tema sunar.

## Jekyll ile çalıştırma

Gereksinimler: Ruby 3.3+, Bundler ve Python 3.9+. Node.js 22+ yalnızca npm
kısayolları, testler ve isteğe bağlı yerel API için gerekir. Site ziyaretçisinin
Ruby, Node veya Python çalıştırması gerekmez; yayımlanan çıktı tamamen statiktir.

```sh
python3 scripts/jekyll.py install
npm start
# http://127.0.0.1:5173

npm run dev   # Jekyll serve + live reload
npm run build # Statik API/kaynak arşivi, Jekyll build ve çıktı kontrolü
npm test      # Veri, baseurl, opsiyonel API ve importer testleri
```

`jekyll.py`, PATH'teki uygun Ruby'yi veya mevcut Homebrew Ruby kurulumunu
kullanır; sistem Ruby'sini ve shell ayarlarınızı değiştirmez. Gem'ler yerel
`vendor/bundle/` dizinine kurulur. macOS sistem Ruby 2.6 tek başına yeterli değildir.

Node olmadan da Jekyll kullanılabilir:

```sh
python3 scripts/prepare_site.py
bundle exec jekyll serve --port 5173
# Üretim çıktısı:
bundle exec jekyll build
python3 scripts/check_site.py
```

Doğrudan Bundler kullanırken Ruby 3.3+ PATH'te bulunmalıdır. `_config.yml` site
kaynağını `public/`, çıktıyı `_site/` olarak belirler. Hazır kernel snapshot'ları
repoda bulunduğu için derleme yerel çekirdek verilerini kullanır.
İlk gem kurulumu tamamlandıktan sonra build yerel girdilerle çalışır.

## GitHub Pages'te yayımlama

1. Bu repoyu GitHub'a aktarın; varsayılan yayımlama dalı `main`dir.
2. Repo **Settings → Pages → Build and deployment → Source** ayarını
   **GitHub Actions** yapın.
3. `main` dalına push edin veya **Build and deploy Jekyll** iş akışını elle başlatın.

`.github/workflows/pages.yml` Ruby/gem ve Node testlerini çalıştırır, statik API ve
GPL kaynak arşivini üretir, Jekyll çıktısını doğrular ve Pages'e yükler. Pull
request'ler build edilir ve doğrulanır; deployment yapılmaz. Repo alt yolu
`actions/configure-pages` çıktısından alınır; özel alan adı veya kullanıcı sitesi
kökünde de aynı kaynaklar kullanılabilir. Dalınız farklıysa workflow'daki
`branches: [main]` satırını değiştirin.

Bu hazırlık herhangi bir uzak repo oluşturmaz veya kendiliğinden yayımlamaz.
GitHub'a aktarılıp Pages etkinleştirildiğinde workflow devreye girer.

GitHub Pages dışındaki statik hosting'ler için `npm run build` sonrasında
`_site/` içeriğini yayımlayın. Alt yolda yayımlamak için:

```sh
python3 scripts/prepare_site.py
python3 scripts/jekyll.py build --baseurl /syscall
python3 scripts/check_site.py --baseurl /syscall
```

`url` ve `baseurl` değerleri `_config.yml` içinden de düzenlenebilir. Kaynak
arşivini, lisans metinlerini ve `data/` altındaki kernel girdilerini çıktıdan
çıkarmayın. Hazırlık, yerel `.git`, `.cache`, `.bundle`, `vendor` ve ortam
dosyalarını kaynak arşivine almaz.

## Özellikler

- x64, x86, arm64, ARM EABI, riscv64 ve loongarch64.
- Linux v6.12, v6.18 ve v7.3 snapshot’ları repoya dahildir.
- İsim, kernel giriş noktası, C argümanı, ondalık veya hexadecimal numarayla arama.
- Artan/azalan isim ve numara sıralaması; hexadecimal gösterim.
- Syscall detayında C bildirimi, kernel kaynak satırı, man-page bağlantısı ve JSON.
- Ana tabloda ARG1–ARG6 sütunları; detayda sıra, tam C bildirimi ve register tablosu.
- Seçilen kernel numarası ve ABI ile indirilebilir C örneği/iskeleti üretimi.
- 64-bit mimarilerde argüman register’ları; 32-bit ABI’ler için açık hizalama notları.
- Sürümler arası eklenen, kaldırılan ve imzası değişen kayıtlar.
- URL’de korunan mimari, sürüm, karşılaştırma, arama ve açık syscall detayı.
- JSON indirme, statik JSON API ve isteğe bağlı yerel HTTP API.
- Dar ekranlarda yatay kaydırılabilen tablo ve klavyeyle kullanılabilir kontroller.

## Veriyi doğrudan kernel’den üretme

Python 3.9+; yalnızca standart kütüphane kullanılır. Kernel derlemek gerekmez.

```sh
npm run sync
python3 scripts/sync_kernel.py --refs v7.3
python3 scripts/sync_kernel.py --refs v6.12 v6.18 v7.3

# Ağ kullanmadan, Makefile sürümüyle eşleşen bir Linux checkout’undan:
python3 scripts/sync_kernel.py --refs v7.3 --kernel-tree /path/to/linux

# Ayrı bir çıktı dizini:
python3 scripts/sync_kernel.py --refs v7.3 --output /tmp/syscall-data
```

Importer yalnızca açık sürüm etiketlerini kabul eder. v6.12 ve sonrasındaki `.tbl`
yerleşimini destekler; eski kernel serileri için ek bir `asm-generic/unistd.h`
okuyucusu gerekir. Yeni bir sürümü varsayılanlara eklemeden önce importer ve testleri
çalıştırın. Desteklenmeyen biçimlerde hata verir.

Numaralar ve ABI’ler `arch/*/.../syscall*.tbl` ve `scripts/syscall.tbl` dosyalarından
gelir. Ortak tabloyu kullanan mimarilerde `Makefile.syscalls` içindeki
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
değişiklikleri kapsar. Dosyalar geçici dosya + atomik replace ile yazılır;
manifest yalnızca tüm istenen sürümler başarıyla tamamlandıktan sonra güncellenir.
Importer’ı aynı çıktı dizini üzerinde eşzamanlı çalıştırmayın.

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

- Bu sürüm altı mimari ve üç snapshot sunar. “İlk eklendiği kernel” gibi
  çıkarılamayan bilgiler üretilmez.
- İmzalar kernel C bildirimleridir, libc wrapper prototipleri değildir. Bildirimde
  argüman adı yoksa sadece tipi gösterilir. Birden fazla CONFIG dalı farklı bir
  imza veriyorsa (ör. `clone`) imza belirsiz olarak işaretlenir.
- Assembly wrapper’ları, header’da bulunmayan mimari çağrıları ve bazı legacy
  imzalar `arguments: null` olur; sıfır argüman ise `arguments: []` olarak ayrılır.
- `sys_ni_syscall` ve giriş noktası olmayan slotlar `unimplemented` olarak
  saklanır ve varsayılan görünümden çıkarılır. Bir tablodaki tanım, her CONFIG
  kombinasyonunda çağrının kullanılabilir olacağı anlamına gelmez.
- ARM özel `__ARM_NR_*` çağrıları, OABI ve x32 bu sürümün kapsamı dışındadır.
- Sürüm karşılaştırması numara+isim kimliği, giriş sembolü, durum ve argümanları
  karşılaştırır; kaynak satır numarasının değişmesi tek başına değişiklik değildir.
- Register kuralları [syscall(2)](https://man7.org/linux/man-pages/man2/syscall.2.html)
  kaynağından elle tanımlanmıştır. 32-bit argümanları otomatik register’lara bölmeyiz.
- Man-page bağlantıları isimden üretilir; her çağrı için ayrı bir sayfa bulunmayabilir.

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
