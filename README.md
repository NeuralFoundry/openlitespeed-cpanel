**English** | [Türkçe](docs/i18n/README.tr.md) | [简体中文](docs/i18n/README.zh-CN.md) | [Español](docs/i18n/README.es.md) | [Português](docs/i18n/README.pt-BR.md) | [Русский](docs/i18n/README.ru.md) | [日本語](docs/i18n/README.ja.md) | [Deutsch](docs/i18n/README.de.md) | [Français](docs/i18n/README.fr.md) | [한국어](docs/i18n/README.ko.md) | [Bahasa Indonesia](docs/i18n/README.id.md)

# OpenLiteSpeed for cPanel and WHM

Website: [openlitespeed.dev/cpanel-whm](https://openlitespeed.dev/cpanel-whm/)

**olscp** runs [OpenLiteSpeed](https://openlitespeed.org) on cPanel/WHM servers as a drop-in replacement for Apache. It reads the existing Apache configuration and cPanel account data, generates the OpenLiteSpeed configuration, keeps it in sync automatically, and adds a WHM plugin and a cPanel plugin to manage everything. Free and open source under GPL-3.0.

![olscp WHM plugin dashboard](docs/dashboard.png)

## Features

- Works with cPanel as is: accounts, addon, sub and parked domains, AutoSSL, suspensions, MultiPHP, `restartsrv_httpd`, chkservd and EasyApache updates
- Safe switch: every site is checked over HTTP and HTTPS after the switch, and the server rolls back to Apache automatically if any site that worked on Apache fails on OpenLiteSpeed. A dry run checks every site on the preview ports first, while Apache keeps serving
- Reads `httpd.conf` and all includes, so custom Apache settings and extra virtual hosts carry over
- `.htaccess` support: rewrite rules, Directory Privacy, Require/Allow/Deny, headers, expires, redirects, error pages, MIME types, `SetEnvIf` bot blocking, `php_value`, cache headers in `<FilesMatch>` (WP Rocket, W3 Total Cache) and a different PHP version per directory
- Live `.htaccess`: rewrite changes apply within a second without a restart, with a prebuilt patched binary or one compiled on the server
- PHP through cPanel PHP-FPM pools or LSAPI per account, detached so restarts keep OPcache
- Node.js, Python and Ruby applications from cPanel Application Manager and the CloudLinux selectors, started by OpenLiteSpeed as the account user
- CloudLinux LVE and CageFS for PHP and applications, when turned on
- LSCache with per-site storage, WordPress cache management and a cPanel plugin for end users
- ModSecurity with the cPanel/OWASP rule sets
- WordPress brute-force protection, bot rate limiting and cgroups v2 resource limits per user or package
- HTTP/3 (QUIC) with a per-domain off list, Brotli, IPv6, real-time statistics with cache hit ratio and application pool use, and a preview mode on ports 8080/8443
- One-click updates from the WHM plugin

## Requirements

- cPanel & WHM 11.130 or newer
- AlmaLinux, Rocky Linux or CloudLinux 8 or 9, x86_64
- EasyApache 4 PHP versions

## Installation

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh
```

The installer downloads OpenLiteSpeed from the official LiteSpeed repository, verifies it against the pinned GPG keys in `keys/`, installs `lsphp` for every EasyApache PHP version and registers the WHM plugin. Apache keeps serving until you switch.

1. Optional dry run: click **Dry run** on the dashboard or run `olscp dry-run`. OpenLiteSpeed starts on ports 8080/8443 and every site is checked while Apache keeps serving; you see which sites, if any, would break.
2. Switch: open **WHM > Plugins > OpenLiteSpeed** and click **Switch to OpenLiteSpeed**, or run `olscp enable`. Every site is checked after the switch and the server rolls back to Apache automatically if any site that worked on Apache fails. Use `olscp enable --no-rollback` to keep OpenLiteSpeed even when some sites fail.
3. To go back to Apache at any time: `olscp disable`.

Servers that cannot reach `rpms.litespeedtech.com` can install from a local package:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## Live .htaccess

The stock OpenLiteSpeed binary loads `.htaccess` rewrite rules once. olscp includes a small patch (`build/patches/`) that reloads changed rewrite rules within a second and detects new `.htaccess` files on the first request, with no restart. Other directives are applied automatically with a graceful restart.

Each release has the patched binary for EL8 and EL9. olscp downloads it from the release, checks it against the SHA-256 in `build/prebuilt.txt` and switches to it:

```bash
olscp ols fetch --use  # download the prebuilt binary and switch to it
olscp ols build        # or compile it on the server in the background, about 10 minutes
olscp ols use olscp    # switch to a compiled build, "olscp ols use official" switches back
```

Compiling installs the toolchain with `dnf` and fetches the OpenLiteSpeed sources from GitHub at pinned commits. To get the prebuilt binary during installation, run `OLSCP_FETCH_OLS=1 bash install.sh`. The same actions are on the **Version** page of the WHM plugin.

![Apache configuration imported by olscp](docs/apache.png)

## Updates

The **Version** page of the WHM plugin shows the latest release and updates olscp with one click. The update downloads the release from GitHub, runs its installer and reloads OpenLiteSpeed gracefully. A prebuilt binary that olscp downloaded earlier is replaced with the one of the new release.

![Prebuilt binary and updates in the WHM plugin](docs/version.png)

```bash
olscp update check     # look for a new release
olscp update start     # update in the background, log in /var/log/olscp-update.log
```

## Command line

| Command | Description |
|---|---|
| `olscp status` | Server, watcher and sync status |
| `olscp enable` / `olscp disable` | Switch to OpenLiteSpeed / back to Apache |
| `olscp restart` | Regenerate the configuration and restart gracefully |
| `olscp apache report` | Settings read from the Apache configuration |
| `olscp htaccess report` | `.htaccess` directives that could not be applied |
| `olscp apps` / `olscp apps restart --vhost example.com --uri /` | Node.js, Python and Ruby applications / restart one |
| `olscp cache list` / `olscp cache purge --all` | LSCache sites / purge |
| `olscp ols versions` / `olscp ols upgrade` | OpenLiteSpeed version and upgrade |
| `olscp ols fetch --use` | Download the prebuilt live `.htaccess` binary and use it |
| `olscp update check` / `olscp update start` | Look for a new olscp release / update |
| `olscp settings key=value --apply` | Change a setting |

## Node.js, Python and Ruby applications

olscp reads the Passenger settings that cPanel Application Manager writes to the Apache configuration and that the CloudLinux Node.js and Python selectors write to `.htaccess`: `PassengerAppRoot`, `PassengerBaseURI`, `PassengerAppType`, `PassengerStartupFile`, `PassengerNodejs`, `PassengerPython`, `PassengerRuby`, `PassengerAppEnv`, `PassengerAppLogFile` and `SetEnv`. Each application runs as the account user, is started on the first request and keeps running through server restarts.

Customers keep using **cPanel > Application Manager** to register their applications:

![Applications registered in cPanel Application Manager](docs/app-manager.png)

**cPanel > Application Status** shows the customer's own applications, restarts them and shows their log:

![Application Status in cPanel](docs/app-status.png)

![Application log in cPanel](docs/app-log.png)

The **Apps** page of the WHM plugin lists the applications of every account with their state, interpreter, log file and a restart button:

![Node.js, Python and Ruby applications in the WHM plugin](docs/apps.png)

- Node.js applications run through the OpenLiteSpeed Node.js starter. Calls to `listen()` are redirected to the socket OpenLiteSpeed gives the application.
- Python applications run through `libexec/lswsgi.py`, a small WSGI server that works with any Python 3.6 or newer interpreter or virtual environment. The startup file must define `application` (default `passenger_wsgi.py`).
- Ruby applications run through `libexec/lsrack.rb`, a small Rack server for Ruby 2.5 or newer. It loads `config.ru` with Bundler when the application has a `Gemfile`, so `bundle install` with a local path works. The `rack` gem must be installed for the application. `RACK_ENV` and `RAILS_ENV` follow `PassengerAppEnv`.
- Touch `tmp/restart.txt` in the application root, use **cPanel > Application Status** or **WHM > Plugins > OpenLiteSpeed > Apps** to restart an application. Changed settings restart it automatically.
- Output goes to `stderr.log` in the application root, or to `PassengerAppLogFile` when it is inside the home directory.
- Subdirectories of the document root under the application URI are served as static files, as with Passenger. `/.well-known/` stays reachable for AutoSSL.
- The application type comes from the startup file (`passenger_wsgi.py`, `app.js` or `config.ru`) unless `PassengerAppType` is set. An interpreter path that does not point to Node.js, Python or Ruby is replaced by the system one.
- The application root must be inside the account home directory. When the Apache configuration has `PassengerDisableHtaccess on`, which is the cPanel default, Passenger settings in `.htaccess` are ignored.

## PHP version per directory

MultiPHP writes the PHP version of a domain as `AddHandler application/x-httpd-ea-phpXX` to `.htaccess`. When a subdirectory uses another version than its domain, olscp maps the PHP files of that directory to the LSAPI process of that version for the account, so the version applies like it does with Apache. This needs the LSAPI PHP mode and the LSAPI package of that version, both on the **PHP** page of the WHM plugin.

## Cache headers in FilesMatch

Caching plugins such as WP Rocket and W3 Total Cache write `<FilesMatch>` blocks to `.htaccess` that only set headers or expiry times for some file types. olscp turns each block into a regex context that keeps the access rules, PHP settings and rewrite rules of its directory, so a request for a missing `sitemap.xml` still reaches WordPress and protected directories stay protected.

## CloudLinux

On CloudLinux, OpenLiteSpeed can start PHP and the applications inside the LVE of the account and, when CageFS is installed, inside its CageFS. It is off by default; the dashboard shows when CloudLinux is detected. Turn it on in **Settings > CloudLinux** (Auto, LVE, LVE and CageFS) or with `olscp settings cloudlinux=auto --apply`. olscp adds its own files to CageFS with `/etc/cagefs/conf.d/olscp.cfg`, runs `cagefsctl --update` and restarts the PHP and application processes. Resource limits then come from LVE Manager and the cgroups v2 limits of olscp are turned off.

## Uninstall

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## Limitations

- Not translated from `.htaccess`: `<If>`, `Require host/expr`, `AuthType Digest`, `<FilesMatch>` blocks that set more than headers and expiry times.
- Ruby applications cannot use WebSockets or `rack.hijack`.
- The CloudLinux support uses the LVE and CageFS hooks built into OpenLiteSpeed. It was tested with a stand-in for `liblve`, not yet on a licensed CloudLinux server.
- Directory listing is not available for sites on PHP-FPM, because cPanel FPM pools restrict `doc_root`. It works with LSAPI.
- Clients without SNI on dedicated IPs receive the server certificate.
- Release archives are not signed. Updates rely on the HTTPS connection to GitHub; prebuilt binaries are also checked against the SHA-256 in `build/prebuilt.txt`.

## Contributing

Bug reports and pull requests are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md). Report security problems privately as described in [SECURITY.md](SECURITY.md).

## License

GPL-3.0, see [LICENSE](LICENSE). OpenLiteSpeed is developed by LiteSpeed Technologies and licensed under GPL-3.0; the patch in `build/patches/` is distributed under the same license. This project is not affiliated with or endorsed by LiteSpeed Technologies or cPanel, L.L.C. LiteSpeed, OpenLiteSpeed, LSCache, cPanel and WHM are trademarks of their respective owners.

Also by the same author: [OpenLiteSpeed for Windows](https://github.com/NeuralFoundry/openlitespeed-windows), a native Windows build of OpenLiteSpeed.
