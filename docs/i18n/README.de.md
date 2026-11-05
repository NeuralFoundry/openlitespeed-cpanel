[English](../../README.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Русский](README.ru.md) | [日本語](README.ja.md) | **Deutsch** | [Français](README.fr.md) | [한국어](README.ko.md) | [Bahasa Indonesia](README.id.md)

# OpenLiteSpeed for cPanel and WHM

Website: [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

Mit **olscp** nutzen Sie OpenLiteSpeed unter cPanel: olscp betreibt [OpenLiteSpeed](https://openlitespeed.org) auf cPanel/WHM-Servern als Drop-in-Ersatz für Apache. Es liest die vorhandene Apache-Konfiguration und die Kontodaten von cPanel, erzeugt daraus die OpenLiteSpeed-Konfiguration, hält sie automatisch synchron und fügt ein WHM-Plugin und ein cPanel-Plugin hinzu, mit denen Sie alles verwalten. Kostenlos und Open Source unter GPL-3.0.

![Dashboard des olscp-WHM-Plugins](../dashboard.png)

## Funktionen

- Funktioniert mit cPanel, wie es ist: Konten, Addon-, Sub- und Parked-Domains, AutoSSL, Sperrungen, MultiPHP, `restartsrv_httpd`, chkservd und EasyApache-Updates
- Sicherer Wechsel: Nach dem Wechsel wird jede Site über HTTP und HTTPS geprüft, und der Server wechselt automatisch zurück zu Apache, wenn eine Site, die unter Apache lief, unter OpenLiteSpeed fehlschlägt. Ein Probelauf (Dry Run) prüft vorher jede Site auf den Vorschau-Ports, während Apache weiter ausliefert
- Liest `httpd.conf` und alle Includes, sodass eigene Apache-Einstellungen und zusätzliche virtuelle Hosts übernommen werden
- `.htaccess`-Unterstützung: Rewrite-Regeln, Directory Privacy, Require/Allow/Deny, Header, Expires, Weiterleitungen, Fehlerseiten, MIME-Typen, Bot-Sperren mit `SetEnvIf`, `php_value`, Cache-Header in `<FilesMatch>` (WP Rocket, W3 Total Cache) und eine eigene PHP-Version pro Verzeichnis
- Live-`.htaccess`: Rewrite-Änderungen greifen innerhalb einer Sekunde ohne Neustart, mit einem vorkompilierten gepatchten Binary oder einem auf dem Server kompilierten
- PHP über die PHP-FPM-Pools von cPanel oder LSAPI pro Konto, im Detached-Modus, sodass OPcache Neustarts übersteht
- Node.js-, Python- und Ruby-Anwendungen aus dem cPanel Application Manager und den CloudLinux-Selectors, von OpenLiteSpeed als Kontobenutzer gestartet
- CloudLinux LVE und CageFS für PHP und Anwendungen, wenn eingeschaltet
- LSCache mit eigenem Speicher pro Site, WordPress-Cache-Verwaltung und einem cPanel-Plugin für Endkunden
- ModSecurity mit den Regelsätzen von cPanel/OWASP
- Brute-Force-Schutz für WordPress, Rate Limiting für Bots und Ressourcenlimits mit cgroups v2 pro Benutzer oder Paket
- HTTP/3 (QUIC) mit einer Ausschlussliste pro Domain, Brotli, IPv6, Echtzeitstatistiken mit Cache-Trefferquote und Auslastung der Anwendungspools sowie ein Vorschaumodus auf den Ports 8080/8443
- Updates mit einem Klick im WHM-Plugin

## Voraussetzungen

- cPanel & WHM 11.130 oder neuer
- AlmaLinux, Rocky Linux oder CloudLinux 8 oder 9, x86_64
- PHP-Versionen aus EasyApache 4

## Installation

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

Das Installationsprogramm lädt OpenLiteSpeed aus dem offiziellen LiteSpeed-Repository, prüft es gegen die festgelegten GPG-Schlüssel in `keys/`, installiert `lsphp` für jede PHP-Version aus EasyApache und registriert das WHM-Plugin. Apache liefert weiter aus, bis Sie wechseln.

1. Optionaler Probelauf: Klicken Sie im Dashboard auf **Dry run** oder führen Sie `olscp dry-run` aus. OpenLiteSpeed startet auf den Ports 8080/8443, und jede Site wird geprüft, während Apache weiter ausliefert; Sie sehen, welche Sites gegebenenfalls nicht mehr funktionieren würden.
2. Wechsel: Öffnen Sie **WHM > Plugins > OpenLiteSpeed** und klicken Sie auf **Switch to OpenLiteSpeed**, oder führen Sie `olscp enable` aus. Nach dem Wechsel wird jede Site geprüft, und der Server wechselt automatisch zurück zu Apache, wenn eine Site, die unter Apache lief, fehlschlägt. Mit `olscp enable --no-rollback` bleibt OpenLiteSpeed aktiv, auch wenn einige Sites fehlschlagen.
3. Zurück zu Apache jederzeit mit: `olscp disable`.

Server, die `rpms.litespeedtech.com` nicht erreichen, können aus einem lokalen Paket installieren:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## Live-.htaccess

Das Standard-Binary von OpenLiteSpeed lädt die Rewrite-Regeln aus `.htaccess` nur einmal. olscp enthält einen kleinen Patch (`build/patches/`), der geänderte Rewrite-Regeln innerhalb einer Sekunde neu lädt und neue `.htaccess`-Dateien bei der ersten Anfrage erkennt, ganz ohne Neustart. Andere Direktiven werden automatisch mit einem Graceful Restart übernommen.

Jedes Release enthält das gepatchte Binary für EL8 und EL9. olscp lädt es aus dem Release, prüft es gegen die SHA-256-Prüfsumme in `build/prebuilt.txt` und wechselt darauf:

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

Beim Kompilieren wird die Toolchain mit `dnf` installiert, und die Quellen von OpenLiteSpeed werden in festgelegten Commits von GitHub geladen. Um das vorkompilierte Binary schon bei der Installation zu erhalten, führen Sie `OLSCP_FETCH_OLS=1 bash install.sh` aus. Dieselben Aktionen finden Sie auf der Seite **Version** des WHM-Plugins.

![Von olscp importierte Apache-Konfiguration](../apache.png)

## Updates

Die Seite **Version** des WHM-Plugins zeigt das neueste Release und aktualisiert olscp mit einem Klick. Das Update lädt das Release von GitHub, führt dessen Installationsprogramm aus und lädt OpenLiteSpeed per Graceful Reload neu. Ein vorkompiliertes Binary, das olscp früher heruntergeladen hat, wird durch das des neuen Release ersetzt.

![Vorkompiliertes Binary und Updates im WHM-Plugin](../version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## Kommandozeile

| Befehl | Beschreibung |
|---|---|
| `olscp status` | Status von Server, Watcher und Synchronisierung |
| `olscp enable` / `olscp disable` | Zu OpenLiteSpeed wechseln / zurück zu Apache |
| `olscp restart` | Konfiguration neu erzeugen und per Graceful Restart neu starten |
| `olscp apache report` | Aus der Apache-Konfiguration gelesene Einstellungen |
| `olscp htaccess report` | `.htaccess`-Direktiven, die nicht übernommen werden konnten |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Node.js-, Python- und Ruby-Anwendungen / eine davon neu starten |
| `olscp cache list` / `olscp cache purge --all` | Sites mit LSCache / Cache leeren |
| `olscp ols versions` / `olscp ols upgrade` | OpenLiteSpeed-Version und Upgrade |
| `olscp ols fetch --use` | Das vorkompilierte Binary mit Live-`.htaccess` herunterladen und verwenden |
| `olscp update check` / `olscp update start` | Nach einem neuen olscp-Release suchen / aktualisieren |
| `olscp settings key=value --apply` | Eine Einstellung ändern |

## Node.js-, Python- und Ruby-Anwendungen

olscp liest die Passenger-Einstellungen, die der cPanel Application Manager in die Apache-Konfiguration und die Node.js- und Python-Selectors von CloudLinux in `.htaccess` schreiben: `PassengerAppRoot`, `PassengerBaseURI`, `PassengerAppType`, `PassengerStartupFile`, `PassengerNodejs`, `PassengerPython`, `PassengerRuby`, `PassengerAppEnv`, `PassengerAppLogFile` und `SetEnv`. Jede Anwendung läuft als Kontobenutzer, wird bei der ersten Anfrage gestartet und läuft auch bei Neustarts des Servers weiter.

Kunden registrieren ihre Anwendungen weiterhin unter **cPanel > Application Manager**:

![Im cPanel Application Manager registrierte Anwendungen](../app-manager.png)

**cPanel > Application Status** zeigt die eigenen Anwendungen des Kunden, startet sie neu und zeigt ihr Log:

![Application Status in cPanel](../app-status.png)

![Anwendungslog in cPanel](../app-log.png)

Die Seite **Apps** des WHM-Plugins listet die Anwendungen aller Konten mit Status, Interpreter, Logdatei und einer Schaltfläche zum Neustarten:

![Node.js-, Python- und Ruby-Anwendungen im WHM-Plugin](../apps.png)

- Node.js-Anwendungen laufen über den Node.js-Starter von OpenLiteSpeed. Aufrufe von `listen()` werden auf den Socket umgeleitet, den OpenLiteSpeed der Anwendung zuweist.
- Python-Anwendungen laufen über `libexec/lswsgi.py`, einen kleinen WSGI-Server, der mit jedem Interpreter oder jeder virtuellen Umgebung ab Python 3.6 funktioniert. Die Startdatei muss `application` definieren (Standard `passenger_wsgi.py`).
- Ruby-Anwendungen laufen über `libexec/lsrack.rb`, einen kleinen Rack-Server ab Ruby 2.5. Er lädt `config.ru` mit Bundler, wenn die Anwendung ein `Gemfile` hat, sodass `bundle install` mit einem lokalen Pfad funktioniert. Das Gem `rack` muss für die Anwendung installiert sein. `RACK_ENV` und `RAILS_ENV` folgen `PassengerAppEnv`.
- Um eine Anwendung neu zu starten, führen Sie touch auf `tmp/restart.txt` im Anwendungsverzeichnis aus oder verwenden Sie **cPanel > Application Status** oder **WHM > Plugins > OpenLiteSpeed > Apps**. Geänderte Einstellungen starten sie automatisch neu.
- Die Ausgabe landet in `stderr.log` im Anwendungsverzeichnis oder in `PassengerAppLogFile`, wenn diese Datei im Home-Verzeichnis liegt.
- Unterverzeichnisse des Document Root unterhalb der Anwendungs-URI werden wie bei Passenger als statische Dateien ausgeliefert. `/.well-known/` bleibt für AutoSSL erreichbar.
- Der Anwendungstyp ergibt sich aus der Startdatei (`passenger_wsgi.py`, `app.js` oder `config.ru`), sofern `PassengerAppType` nicht gesetzt ist. Ein Interpreterpfad, der nicht auf Node.js, Python oder Ruby zeigt, wird durch den des Systems ersetzt.
- Das Anwendungsverzeichnis muss im Home-Verzeichnis des Kontos liegen. Wenn die Apache-Konfiguration `PassengerDisableHtaccess on` enthält, was der Standard von cPanel ist, werden Passenger-Einstellungen in `.htaccess` ignoriert.

## PHP-Version pro Verzeichnis

MultiPHP schreibt die PHP-Version einer Domain als `AddHandler application/x-httpd-ea-phpXX` in `.htaccess`. Wenn ein Unterverzeichnis eine andere Version als seine Domain verwendet, ordnet olscp die PHP-Dateien dieses Verzeichnisses dem LSAPI-Prozess dieser Version für das Konto zu, sodass die Version wie unter Apache gilt. Dafür sind der LSAPI-PHP-Modus und das LSAPI-Paket dieser Version nötig, beides auf der Seite **PHP** des WHM-Plugins.

## Cache-Header in FilesMatch

Caching-Plugins wie WP Rocket und W3 Total Cache schreiben `<FilesMatch>`-Blöcke in `.htaccess`, die für einige Dateitypen nur Header oder Ablaufzeiten setzen. olscp macht aus jedem Block einen Regex-Kontext, der die Zugriffsregeln, PHP-Einstellungen und Rewrite-Regeln seines Verzeichnisses beibehält. So erreicht eine Anfrage nach einer fehlenden `sitemap.xml` weiterhin WordPress, und geschützte Verzeichnisse bleiben geschützt.

## CloudLinux

Unter CloudLinux kann OpenLiteSpeed PHP und die Anwendungen im LVE des Kontos starten und, wenn CageFS installiert ist, in dessen CageFS. Das ist standardmäßig ausgeschaltet; das Dashboard zeigt an, wenn CloudLinux erkannt wurde. Schalten Sie es unter **Settings > CloudLinux** (Auto, LVE, LVE and CageFS) oder mit `olscp settings cloudlinux=auto --apply` ein. olscp fügt seine eigenen Dateien mit `/etc/cagefs/conf.d/olscp.cfg` zu CageFS hinzu, führt `cagefsctl --update` aus und startet die PHP- und Anwendungsprozesse neu. Die Ressourcenlimits kommen dann aus dem LVE Manager, und die cgroups-v2-Limits von olscp werden ausgeschaltet.

## Deinstallation

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## Einschränkungen

- Nicht aus `.htaccess` übersetzt werden: `<If>`, `Require host/expr`, `AuthType Digest` sowie `<FilesMatch>`-Blöcke, die mehr als Header und Ablaufzeiten setzen.
- Ruby-Anwendungen können weder WebSockets noch `rack.hijack` verwenden.
- Die CloudLinux-Unterstützung nutzt die in OpenLiteSpeed eingebauten Hooks für LVE und CageFS. Sie wurde mit einem Ersatz für `liblve` getestet, noch nicht auf einem lizenzierten CloudLinux-Server.
- Verzeichnislisten sind für Sites mit PHP-FPM nicht verfügbar, weil die FPM-Pools von cPanel `doc_root` einschränken. Mit LSAPI funktionieren sie.
- Clients ohne SNI erhalten auf dedizierten IPs das Serverzertifikat.
- Release-Archive sind nicht signiert. Updates verlassen sich auf die HTTPS-Verbindung zu GitHub; vorkompilierte Binaries werden zusätzlich gegen die SHA-256-Prüfsumme in `build/prebuilt.txt` geprüft.

## Mitwirken

Fehlerberichte und Pull Requests sind willkommen, siehe [CONTRIBUTING.md](../../CONTRIBUTING.md). Melden Sie Sicherheitsprobleme vertraulich, wie in [SECURITY.md](../../SECURITY.md) beschrieben.

## Lizenz

GPL-3.0, siehe [LICENSE](../../LICENSE). OpenLiteSpeed wird von LiteSpeed Technologies entwickelt und steht unter GPL-3.0; der Patch in `build/patches/` wird unter derselben Lizenz verteilt. Dieses Projekt steht in keiner Verbindung zu LiteSpeed Technologies oder cPanel, L.L.C. und wird von diesen nicht unterstützt. LiteSpeed, OpenLiteSpeed, LSCache, cPanel und WHM sind Marken ihrer jeweiligen Inhaber.

Ebenfalls vom selben Autor: [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows), ein nativer Windows-Build von OpenLiteSpeed.
