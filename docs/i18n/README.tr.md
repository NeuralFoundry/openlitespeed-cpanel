[English](../../README.md) | **Türkçe** | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

Web sitesi: [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

**olscp**, [OpenLiteSpeed](https://openlitespeed.org)'i cPanel/WHM sunucularında Apache'nin doğrudan yerine geçecek şekilde çalıştırır; böylece cPanel'de Apache yerine OpenLiteSpeed kullanabilirsiniz. Mevcut Apache yapılandırmasını ve cPanel hesap verilerini okur, OpenLiteSpeed yapılandırmasını oluşturur, bunu otomatik olarak senkron tutar ve her şeyi yönetmek için bir WHM eklentisi ile bir cPanel eklentisi ekler. GPL-3.0 lisansıyla ücretsiz ve açık kaynaktır.

![olscp WHM eklentisinin dashboard ekranı](../dashboard.png)

## Özellikler

- cPanel ile olduğu gibi çalışır: hesaplar, addon, alt ve park edilmiş alan adları, AutoSSL, hesap askıya alma, MultiPHP, `restartsrv_httpd`, chkservd ve EasyApache güncellemeleri
- Güvenli geçiş: geçişten sonra her site HTTP ve HTTPS üzerinden kontrol edilir; Apache'de çalışan herhangi bir site OpenLiteSpeed'de hata verirse sunucu otomatik olarak Apache'ye geri döner. Deneme çalıştırması (dry run), Apache hizmet vermeye devam ederken önce her siteyi önizleme portlarında kontrol eder
- `httpd.conf` dosyasını ve bütün include dosyalarını okur; özel Apache ayarları ve ek sanal sunucular (virtual host) da aktarılır
- `.htaccess` desteği: rewrite kuralları, Directory Privacy, Require/Allow/Deny, başlıklar, expires, yönlendirmeler, hata sayfaları, MIME türleri, `SetEnvIf` ile bot engelleme, `php_value`, `<FilesMatch>` içinde önbellek başlıkları (WP Rocket, W3 Total Cache) ve dizin başına farklı PHP sürümü
- Canlı `.htaccess`: rewrite değişiklikleri yeniden başlatma gerekmeden bir saniye içinde uygulanır; hazır derlenmiş yamalı binary ile ya da sunucuda derlenen bir binary ile
- PHP, hesap başına cPanel PHP-FPM havuzları veya LSAPI üzerinden çalışır; detached modda çalıştığı için yeniden başlatmalarda OPcache korunur
- cPanel Application Manager ve CloudLinux selector'larındaki Node.js, Python ve Ruby uygulamaları, OpenLiteSpeed tarafından hesap kullanıcısıyla başlatılır
- Açıldığında PHP ve uygulamalar için CloudLinux LVE ve CageFS
- Site başına ayrı depolamalı LSCache, WordPress önbellek yönetimi ve son kullanıcılar için bir cPanel eklentisi
- cPanel/OWASP kural setleriyle ModSecurity
- WordPress brute-force koruması, bot hız sınırlaması ve kullanıcı ya da paket başına cgroups v2 kaynak limitleri
- Alan adı bazında kapatılabilen HTTP/3 (QUIC), Brotli, IPv6, önbellek isabet oranını ve uygulama havuzu kullanımını gösteren gerçek zamanlı istatistikler ve 8080/8443 portlarında önizleme modu
- WHM eklentisinden tek tıkla güncelleme

## Gereksinimler

- cPanel & WHM 11.130 veya daha yeni
- AlmaLinux, Rocky Linux veya CloudLinux 8 ya da 9, x86_64
- EasyApache 4 PHP sürümleri

## Kurulum

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

Kurulum programı OpenLiteSpeed'i resmi LiteSpeed deposundan indirir, `keys/` içindeki sabitlenmiş GPG anahtarlarıyla doğrular, her EasyApache PHP sürümü için `lsphp` kurar ve WHM eklentisini kaydeder. Siz geçiş yapana kadar Apache hizmet vermeye devam eder.

1. İsteğe bağlı deneme: dashboard'da **Dry run** düğmesine tıklayın veya `olscp dry-run` komutunu çalıştırın. OpenLiteSpeed 8080/8443 portlarında başlar ve Apache hizmet vermeye devam ederken her site kontrol edilir; bozulacak site varsa hangileri olduğunu görürsünüz.
2. Geçiş: **WHM > Plugins > OpenLiteSpeed** sayfasını açıp **Switch to OpenLiteSpeed** düğmesine tıklayın veya `olscp enable` komutunu çalıştırın. Geçişten sonra her site kontrol edilir; Apache'de çalışan herhangi bir site hata verirse sunucu otomatik olarak Apache'ye geri döner. Bazı siteler hata verse bile OpenLiteSpeed'de kalmak için `olscp enable --no-rollback` kullanın.
3. İstediğiniz zaman Apache'ye dönmek için: `olscp disable`.

`rpms.litespeedtech.com` adresine erişemeyen sunucular yerel bir paketten kurulum yapabilir:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## Canlı .htaccess

Standart OpenLiteSpeed binary'si `.htaccess` rewrite kurallarını yalnızca bir kez yükler. olscp küçük bir yama (`build/patches/`) içerir: bu yama değişen rewrite kurallarını bir saniye içinde yeniden yükler ve yeni `.htaccess` dosyalarını ilk istekte algılar, yeniden başlatma gerekmez. Diğer direktifler otomatik olarak graceful restart ile uygulanır.

Her sürümde EL8 ve EL9 için yamalı binary bulunur. olscp bunu sürümden indirir, `build/prebuilt.txt` içindeki SHA-256 ile doğrular ve ona geçer:

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

Derleme, araç zincirini `dnf` ile kurar ve OpenLiteSpeed kaynak kodunu GitHub'dan sabitlenmiş commit'lerde indirir. Kurulum sırasında hazır binary'yi almak için `OLSCP_FETCH_OLS=1 bash install.sh` komutunu çalıştırın. Aynı işlemler WHM eklentisinin **Version** sayfasında da bulunur.

![olscp'nin içe aktardığı Apache yapılandırması](../apache.png)

## Güncellemeler

WHM eklentisinin **Version** sayfası en son sürümü gösterir ve olscp'yi tek tıkla günceller. Güncelleme, sürümü GitHub'dan indirir, kurulum programını çalıştırır ve OpenLiteSpeed'i graceful olarak yeniden yükler. olscp'nin daha önce indirdiği hazır binary, yeni sürümün binary'siyle değiştirilir.

![WHM eklentisinde hazır binary ve güncellemeler](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## Komut satırı

| Komut | Açıklama |
|---|---|
| `olscp status` | Sunucu, izleyici (watcher) ve senkronizasyon durumu |
| `olscp enable` / `olscp disable` | OpenLiteSpeed'e geçiş / Apache'ye dönüş |
| `olscp restart` | Yapılandırmayı yeniden oluşturur ve graceful olarak yeniden başlatır |
| `olscp apache report` | Apache yapılandırmasından okunan ayarlar |
| `olscp htaccess report` | Uygulanamayan `.htaccess` direktifleri |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Node.js, Python ve Ruby uygulamaları / birini yeniden başlatma |
| `olscp cache list` / `olscp cache purge --all` | LSCache kullanan siteler / önbelleği temizleme |
| `olscp ols versions` / `olscp ols upgrade` | OpenLiteSpeed sürümü ve yükseltme |
| `olscp ols fetch --use` | Hazır canlı `.htaccess` binary'sini indirir ve kullanır |
| `olscp update check` / `olscp update start` | Yeni olscp sürümü arama / güncelleme |
| `olscp settings key=value --apply` | Bir ayarı değiştirir |

## Node.js, Python ve Ruby uygulamaları

olscp, cPanel Application Manager'ın Apache yapılandırmasına ve CloudLinux Node.js ve Python selector'larının `.htaccess` dosyasına yazdığı Passenger ayarlarını okur: `PassengerAppRoot`, `PassengerBaseURI`, `PassengerAppType`, `PassengerStartupFile`, `PassengerNodejs`, `PassengerPython`, `PassengerRuby`, `PassengerAppEnv`, `PassengerAppLogFile` ve `SetEnv`. Her uygulama hesap kullanıcısıyla çalışır, ilk istekte başlatılır ve sunucu yeniden başlatıldığında da çalışmaya devam eder.

Müşteriler uygulamalarını kaydetmek için **cPanel > Application Manager** kullanmaya devam eder:

![cPanel Application Manager'da kayıtlı uygulamalar](../app-manager.png)

**cPanel > Application Status**, müşterinin kendi uygulamalarını gösterir, onları yeniden başlatır ve loglarını gösterir:

![cPanel'de Application Status](../app-status.png)

![cPanel'de uygulama logu](../app-log.png)

WHM eklentisinin **Apps** sayfası, bütün hesapların uygulamalarını durumu, yorumlayıcısı, log dosyası ve bir yeniden başlatma düğmesiyle listeler:

![WHM eklentisinde Node.js, Python ve Ruby uygulamaları](../apps.png)

- Node.js uygulamaları OpenLiteSpeed Node.js başlatıcısıyla çalışır. `listen()` çağrıları, OpenLiteSpeed'in uygulamaya verdiği sokete yönlendirilir.
- Python uygulamaları `libexec/lswsgi.py` üzerinden çalışır; bu, Python 3.6 veya daha yeni herhangi bir yorumlayıcı ya da sanal ortamla çalışan küçük bir WSGI sunucusudur. Başlangıç dosyası `application` tanımlamalıdır (varsayılan `passenger_wsgi.py`).
- Ruby uygulamaları `libexec/lsrack.rb` üzerinden çalışır; bu, Ruby 2.5 veya daha yeni sürümler için küçük bir Rack sunucusudur. Uygulamada `Gemfile` varsa `config.ru` dosyasını Bundler ile yükler, bu yüzden yerel bir yolla yapılan `bundle install` çalışır. Uygulama için `rack` gem'i kurulu olmalıdır. `RACK_ENV` ve `RAILS_ENV`, `PassengerAppEnv` değerini izler.
- Bir uygulamayı yeniden başlatmak için uygulama kökündeki `tmp/restart.txt` dosyasına touch uygulayın ya da **cPanel > Application Status** veya **WHM > Plugins > OpenLiteSpeed > Apps** sayfasını kullanın. Ayarlar değişince uygulama otomatik olarak yeniden başlar.
- Çıktı, uygulama kökündeki `stderr.log` dosyasına, ev dizininin içindeyse `PassengerAppLogFile` dosyasına yazılır.
- Uygulama URI'si altındaki document root alt dizinleri, Passenger'da olduğu gibi statik dosya olarak sunulur. `/.well-known/` AutoSSL için erişilebilir kalır.
- `PassengerAppType` ayarlanmamışsa uygulama türü başlangıç dosyasından (`passenger_wsgi.py`, `app.js` veya `config.ru`) belirlenir. Node.js, Python veya Ruby'yi göstermeyen bir yorumlayıcı yolu, sistemdeki yorumlayıcıyla değiştirilir.
- Uygulama kökü hesabın ev dizininin içinde olmalıdır. Apache yapılandırmasında cPanel varsayılanı olan `PassengerDisableHtaccess on` varsa `.htaccess` içindeki Passenger ayarları yok sayılır.

## Dizin başına PHP sürümü

MultiPHP, bir alan adının PHP sürümünü `.htaccess` dosyasına `AddHandler application/x-httpd-ea-phpXX` olarak yazar. Bir alt dizin alan adından farklı bir sürüm kullandığında olscp o dizindeki PHP dosyalarını hesabın o sürüme ait LSAPI sürecine yönlendirir; böylece sürüm Apache'de olduğu gibi uygulanır. Bunun için LSAPI PHP modu ve o sürümün LSAPI paketi gerekir; ikisi de WHM eklentisinin **PHP** sayfasındadır.

## FilesMatch içindeki önbellek başlıkları

WP Rocket ve W3 Total Cache gibi önbellek eklentileri `.htaccess` dosyasına, bazı dosya türleri için yalnızca başlık veya geçerlilik süresi ayarlayan `<FilesMatch>` blokları yazar. olscp her bloğu, bulunduğu dizinin erişim kurallarını, PHP ayarlarını ve rewrite kurallarını koruyan bir regex context'ine dönüştürür; böylece var olmayan bir `sitemap.xml` isteği yine WordPress'e ulaşır ve korumalı dizinler korumalı kalır.

## CloudLinux

CloudLinux'ta OpenLiteSpeed, PHP'yi ve uygulamaları hesabın LVE'si içinde, CageFS kuruluysa hesabın CageFS'i içinde başlatabilir. Varsayılan olarak kapalıdır; CloudLinux algılandığında dashboard bunu gösterir. **Settings > CloudLinux** (Auto, LVE, LVE and CageFS) üzerinden veya `olscp settings cloudlinux=auto --apply` ile açın. olscp kendi dosyalarını `/etc/cagefs/conf.d/olscp.cfg` ile CageFS'e ekler, `cagefsctl --update` çalıştırır ve PHP ile uygulama süreçlerini yeniden başlatır. Bundan sonra kaynak limitleri LVE Manager'dan gelir ve olscp'nin cgroups v2 limitleri kapatılır.

## Kaldırma

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## Sınırlamalar

- `.htaccess` içinden dönüştürülmeyenler: `<If>`, `Require host/expr`, `AuthType Digest`, başlık ve geçerlilik süresi dışında ayar yapan `<FilesMatch>` blokları.
- Ruby uygulamaları WebSocket veya `rack.hijack` kullanamaz.
- CloudLinux desteği, OpenLiteSpeed'e yerleşik LVE ve CageFS hook'larını kullanır. `liblve` yerine geçen bir test kütüphanesiyle denendi, henüz lisanslı bir CloudLinux sunucusunda denenmedi.
- cPanel FPM havuzları `doc_root` değerini kısıtladığı için PHP-FPM kullanan sitelerde dizin listeleme kullanılamaz. LSAPI ile çalışır.
- Özel IP'lerde SNI desteklemeyen istemciler sunucu sertifikasını alır.
- Sürüm arşivleri imzalı değildir. Güncellemeler GitHub'a yapılan HTTPS bağlantısına dayanır; hazır binary'ler ayrıca `build/prebuilt.txt` içindeki SHA-256 ile doğrulanır.

## Katkıda bulunma

Hata raporları ve pull request'ler memnuniyetle karşılanır, bkz. [CONTRIBUTING.md](../../CONTRIBUTING.md). Güvenlik sorunlarını [SECURITY.md](../../SECURITY.md) dosyasında anlatıldığı gibi gizli olarak bildirin.

## Lisans

GPL-3.0, bkz. [LICENSE](../../LICENSE). OpenLiteSpeed, LiteSpeed Technologies tarafından geliştirilir ve GPL-3.0 ile lisanslanır; `build/patches/` içindeki yama da aynı lisansla dağıtılır. Bu proje LiteSpeed Technologies veya cPanel, L.L.C. ile bağlantılı değildir ve onlar tarafından onaylanmamıştır. LiteSpeed, OpenLiteSpeed, LSCache, cPanel ve WHM, ilgili sahiplerinin ticari markalarıdır.

Aynı yazarın diğer projesi: [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows), OpenLiteSpeed'in yerel Windows derlemesi.
