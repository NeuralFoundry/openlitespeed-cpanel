[English](../../README.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | **Русский** | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [한국어](README.ko.md) | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

Сайт: [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

**olscp** позволяет установить OpenLiteSpeed на cPanel: он запускает [OpenLiteSpeed](https://openlitespeed.org) на серверах cPanel/WHM как прямую замену Apache. Он читает существующую конфигурацию Apache и данные аккаунтов cPanel, генерирует конфигурацию OpenLiteSpeed, автоматически поддерживает её в актуальном состоянии и добавляет плагин для WHM и плагин для cPanel, чтобы всем этим управлять. Бесплатный проект с открытым исходным кодом под лицензией GPL-3.0.

![Панель плагина olscp в WHM](../dashboard.png)

## Возможности

- Работает с cPanel как есть: аккаунты, дополнительные домены (addon), поддомены и припаркованные домены, AutoSSL, блокировка аккаунтов, MultiPHP, `restartsrv_httpd`, chkservd и обновления EasyApache
- Безопасное переключение: после переключения каждый сайт проверяется по HTTP и HTTPS, и сервер автоматически возвращается на Apache, если какой-либо сайт, работавший на Apache, не работает на OpenLiteSpeed. Пробный запуск (dry run) сначала проверяет каждый сайт на портах предпросмотра, пока Apache продолжает обслуживать запросы
- Читает `httpd.conf` и все подключаемые файлы, поэтому собственные настройки Apache и дополнительные виртуальные хосты переносятся
- Поддержка `.htaccess`: правила rewrite, Directory Privacy, Require/Allow/Deny, заголовки, expires, редиректы, страницы ошибок, MIME-типы, блокировка ботов через `SetEnvIf`, `php_value`, заголовки кэширования в `<FilesMatch>` (WP Rocket, W3 Total Cache) и отдельная версия PHP для каталога
- Живой `.htaccess`: изменения правил rewrite применяются в течение секунды без перезапуска, с готовым пропатченным бинарным файлом или собранным на сервере
- PHP через пулы PHP-FPM cPanel или LSAPI для каждого аккаунта, в режиме detached, поэтому OPcache сохраняется при перезапусках
- Приложения Node.js, Python и Ruby из cPanel Application Manager и селекторов CloudLinux, которые OpenLiteSpeed запускает от имени пользователя аккаунта
- CloudLinux LVE и CageFS для PHP и приложений, если включено
- LSCache с отдельным хранилищем для каждого сайта, управлением кэшем WordPress и плагином cPanel для конечных пользователей
- ModSecurity с наборами правил cPanel/OWASP
- Защита WordPress от перебора паролей, ограничение частоты запросов для ботов и лимиты ресурсов cgroups v2 для пользователя или пакета
- HTTP/3 (QUIC) со списком доменов, где он отключён, Brotli, IPv6, статистика в реальном времени с долей попаданий в кэш и загрузкой пулов приложений, а также режим предпросмотра на портах 8080/8443
- Обновление в один клик из плагина WHM

## Требования

- cPanel & WHM 11.130 или новее
- AlmaLinux, Rocky Linux или CloudLinux 8 или 9, x86_64
- Версии PHP из EasyApache 4

## Установка

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

Установщик скачивает OpenLiteSpeed из официального репозитория LiteSpeed, проверяет его по закреплённым GPG-ключам из `keys/`, устанавливает `lsphp` для каждой версии PHP из EasyApache и регистрирует плагин WHM. Apache продолжает обслуживать сайты, пока вы не переключитесь.

1. Пробный запуск (необязательно): нажмите **Dry run** на панели или выполните `olscp dry-run`. OpenLiteSpeed запускается на портах 8080/8443, и каждый сайт проверяется, пока Apache продолжает работать; вы увидите, какие сайты перестанут работать, если такие есть.
2. Переключение: откройте **WHM > Plugins > OpenLiteSpeed** и нажмите **Switch to OpenLiteSpeed** или выполните `olscp enable`. После переключения каждый сайт проверяется, и сервер автоматически возвращается на Apache, если какой-либо сайт, работавший на Apache, перестал работать. Используйте `olscp enable --no-rollback`, чтобы остаться на OpenLiteSpeed, даже если часть сайтов не работает.
3. Вернуться на Apache можно в любой момент: `olscp disable`.

Серверы без доступа к `rpms.litespeedtech.com` могут установить OpenLiteSpeed из локального пакета:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## Живой .htaccess

Стандартный бинарный файл OpenLiteSpeed загружает правила rewrite из `.htaccess` только один раз. В olscp есть небольшой патч (`build/patches/`), который перезагружает изменённые правила rewrite в течение секунды и находит новые файлы `.htaccess` при первом запросе, без перезапуска. Остальные директивы применяются автоматически через мягкий перезапуск (graceful restart).

В каждом релизе есть пропатченный бинарный файл для EL8 и EL9. olscp скачивает его из релиза, сверяет с SHA-256 из `build/prebuilt.txt` и переключается на него:

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

Для сборки устанавливаются инструменты через `dnf`, а исходный код OpenLiteSpeed загружается с GitHub на закреплённых коммитах. Чтобы получить готовый бинарный файл во время установки, выполните `OLSCP_FETCH_OLS=1 bash install.sh`. Те же действия доступны на странице **Version** плагина WHM.

![Конфигурация Apache, импортированная olscp](../apache.png)

## Обновления

Страница **Version** плагина WHM показывает последний релиз и обновляет olscp в один клик. Обновление скачивает релиз с GitHub, запускает его установщик и мягко перезагружает OpenLiteSpeed. Готовый бинарный файл, который olscp скачал ранее, заменяется файлом из нового релиза.

![Готовый бинарный файл и обновления в плагине WHM](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## Командная строка

| Команда | Описание |
|---|---|
| `olscp status` | Состояние сервера, наблюдателя (watcher) и синхронизации |
| `olscp enable` / `olscp disable` | Переключиться на OpenLiteSpeed / вернуться на Apache |
| `olscp restart` | Заново сгенерировать конфигурацию и мягко перезапустить |
| `olscp apache report` | Настройки, прочитанные из конфигурации Apache |
| `olscp htaccess report` | Директивы `.htaccess`, которые не удалось применить |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Приложения Node.js, Python и Ruby / перезапуск одного из них |
| `olscp cache list` / `olscp cache purge --all` | Сайты с LSCache / очистка кэша |
| `olscp ols versions` / `olscp ols upgrade` | Версия OpenLiteSpeed и обновление |
| `olscp ols fetch --use` | Скачать готовый бинарный файл с живым `.htaccess` и использовать его |
| `olscp update check` / `olscp update start` | Проверить новый релиз olscp / обновить |
| `olscp settings key=value --apply` | Изменить настройку |

## Приложения Node.js, Python и Ruby

olscp читает настройки Passenger, которые cPanel Application Manager записывает в конфигурацию Apache, а селекторы Node.js и Python в CloudLinux записывают в `.htaccess`: `PassengerAppRoot`, `PassengerBaseURI`, `PassengerAppType`, `PassengerStartupFile`, `PassengerNodejs`, `PassengerPython`, `PassengerRuby`, `PassengerAppEnv`, `PassengerAppLogFile` и `SetEnv`. Каждое приложение работает от имени пользователя аккаунта, запускается при первом запросе и продолжает работать при перезапусках сервера.

Клиенты по-прежнему регистрируют свои приложения в **cPanel > Application Manager**:

![Приложения, зарегистрированные в cPanel Application Manager](../app-manager.png)

**cPanel > Application Status** показывает собственные приложения клиента, перезапускает их и показывает их лог:

![Application Status в cPanel](../app-status.png)

![Лог приложения в cPanel](../app-log.png)

Страница **Apps** плагина WHM показывает приложения всех аккаунтов с их состоянием, интерпретатором, файлом лога и кнопкой перезапуска:

![Приложения Node.js, Python и Ruby в плагине WHM](../apps.png)

- Приложения Node.js запускаются через стартер Node.js из OpenLiteSpeed. Вызовы `listen()` перенаправляются на сокет, который OpenLiteSpeed выделяет приложению.
- Приложения Python запускаются через `libexec/lswsgi.py`, небольшой WSGI-сервер, который работает с любым интерпретатором или виртуальным окружением Python 3.6 или новее. Стартовый файл должен определять `application` (по умолчанию `passenger_wsgi.py`).
- Приложения Ruby запускаются через `libexec/lsrack.rb`, небольшой Rack-сервер для Ruby 2.5 или новее. Он загружает `config.ru` через Bundler, если у приложения есть `Gemfile`, поэтому `bundle install` с локальным путём работает. Для приложения должен быть установлен gem `rack`. `RACK_ENV` и `RAILS_ENV` следуют за `PassengerAppEnv`.
- Чтобы перезапустить приложение, выполните touch для `tmp/restart.txt` в корне приложения или используйте **cPanel > Application Status** или **WHM > Plugins > OpenLiteSpeed > Apps**. При изменении настроек приложение перезапускается автоматически.
- Вывод пишется в `stderr.log` в корне приложения или в `PassengerAppLogFile`, если этот файл находится внутри домашнего каталога.
- Подкаталоги корня документов (document root) под URI приложения отдаются как статические файлы, как в Passenger. `/.well-known/` остаётся доступным для AutoSSL.
- Тип приложения определяется по стартовому файлу (`passenger_wsgi.py`, `app.js` или `config.ru`), если не задан `PassengerAppType`. Путь к интерпретатору, который не указывает на Node.js, Python или Ruby, заменяется системным.
- Корень приложения должен находиться внутри домашнего каталога аккаунта. Если в конфигурации Apache указано `PassengerDisableHtaccess on` (так по умолчанию в cPanel), настройки Passenger в `.htaccess` игнорируются.

## Версия PHP для каталога

MultiPHP записывает версию PHP домена в `.htaccess` в виде `AddHandler application/x-httpd-ea-phpXX`. Если подкаталог использует другую версию, чем его домен, olscp направляет PHP-файлы этого каталога в процесс LSAPI этой версии для данного аккаунта, и версия применяется так же, как в Apache. Для этого нужны режим PHP LSAPI и пакет LSAPI этой версии, оба на странице **PHP** плагина WHM.

## Заголовки кэширования в FilesMatch

Плагины кэширования, например WP Rocket и W3 Total Cache, записывают в `.htaccess` блоки `<FilesMatch>`, которые только задают заголовки или время истечения для некоторых типов файлов. olscp превращает каждый такой блок в regex-контекст, который сохраняет правила доступа, настройки PHP и правила rewrite своего каталога, поэтому запрос к несуществующему `sitemap.xml` по-прежнему доходит до WordPress, а защищённые каталоги остаются защищёнными.

## CloudLinux

В CloudLinux OpenLiteSpeed может запускать PHP и приложения внутри LVE аккаунта, а если установлен CageFS, то и внутри его CageFS. По умолчанию это выключено; панель показывает, когда обнаружен CloudLinux. Включите в **Settings > CloudLinux** (Auto, LVE, LVE and CageFS) или командой `olscp settings cloudlinux=auto --apply`. olscp добавляет свои файлы в CageFS через `/etc/cagefs/conf.d/olscp.cfg`, выполняет `cagefsctl --update` и перезапускает процессы PHP и приложений. После этого лимиты ресурсов задаются в LVE Manager, а лимиты cgroups v2 из olscp отключаются.

## Удаление

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## Ограничения

- Не переносятся из `.htaccess`: `<If>`, `Require host/expr`, `AuthType Digest`, блоки `<FilesMatch>`, которые задают что-то кроме заголовков и времени истечения.
- Приложения Ruby не могут использовать WebSockets и `rack.hijack`.
- Поддержка CloudLinux использует встроенные в OpenLiteSpeed хуки LVE и CageFS. Она проверена с заменой для `liblve`, но ещё не на лицензированном сервере CloudLinux.
- Листинг каталогов недоступен для сайтов на PHP-FPM, так как пулы FPM в cPanel ограничивают `doc_root`. С LSAPI он работает.
- Клиенты без SNI на выделенных IP получают сертификат сервера.
- Архивы релизов не подписаны. Обновления полагаются на HTTPS-соединение с GitHub; готовые бинарные файлы дополнительно проверяются по SHA-256 из `build/prebuilt.txt`.

## Участие в разработке

Сообщения об ошибках и pull request приветствуются, см. [CONTRIBUTING.md](../../CONTRIBUTING.md). О проблемах безопасности сообщайте приватно, как описано в [SECURITY.md](../../SECURITY.md).

## Лицензия

GPL-3.0, см. [LICENSE](../../LICENSE). OpenLiteSpeed разрабатывается компанией LiteSpeed Technologies и распространяется под лицензией GPL-3.0; патч в `build/patches/` распространяется под той же лицензией. Этот проект не связан с LiteSpeed Technologies или cPanel, L.L.C. и не одобрен ими. LiteSpeed, OpenLiteSpeed, LSCache, cPanel и WHM являются товарными знаками соответствующих владельцев.

Также от этого автора: [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows), нативная сборка OpenLiteSpeed для Windows.
