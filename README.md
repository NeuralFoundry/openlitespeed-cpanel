# OpenLiteSpeed for cPanel and WHM

Website: [openlitespeed.dev](https://openlitespeed.dev/)

**olscp** runs [OpenLiteSpeed](https://openlitespeed.org) on cPanel/WHM servers as a drop-in replacement for Apache. It reads the existing Apache configuration and cPanel account data, generates the OpenLiteSpeed configuration, keeps it in sync automatically, and adds a WHM plugin and a cPanel plugin to manage everything. Free and open source under GPL-3.0.

![olscp WHM plugin dashboard](docs/dashboard.png)

## Features

- Works with cPanel as is: accounts, addon, sub and parked domains, AutoSSL, suspensions, MultiPHP, `restartsrv_httpd`, chkservd and EasyApache updates
- Reads `httpd.conf` and all includes, so custom Apache settings and extra virtual hosts carry over
- `.htaccess` support: rewrite rules, Directory Privacy, Require/Allow/Deny, headers, expires, redirects, error pages, MIME types, `SetEnvIf` bot blocking, `php_value`
- Live `.htaccess`: rewrite changes apply within a second without a restart (optional patched build)
- PHP through cPanel PHP-FPM pools or LSAPI per account, detached so restarts keep OPcache
- LSCache with per-site storage, WordPress cache management and a cPanel plugin for end users
- ModSecurity with the cPanel/OWASP rule sets
- WordPress brute-force protection, bot rate limiting and cgroups v2 resource limits per user or package
- HTTP/3 (QUIC), Brotli, IPv6, real-time statistics and a preview mode on ports 8080/8443

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

1. Optional: test OpenLiteSpeed next to Apache with `olscp preview start`, then open your sites on ports 8080 and 8443.
2. Switch: open **WHM > Plugins > OpenLiteSpeed** and click **Switch to OpenLiteSpeed**, or run `olscp enable`.
3. To go back to Apache at any time: `olscp disable`.

Servers that cannot reach `rpms.litespeedtech.com` can install from a local package:

```bash
OLSCP_OLS_RPM=/root/openlitespeed-1.9.4-2.el9.x86_64.rpm bash install.sh
```

## Live .htaccess

The stock OpenLiteSpeed binary loads `.htaccess` rewrite rules once. olscp includes a small patch (`build/patches/`) that reloads changed rewrite rules within a second and detects new `.htaccess` files on the first request, with no restart. Other directives are applied automatically with a graceful restart.

```bash
olscp ols build        # compile the patched binary in the background, about 10 minutes
olscp ols use olscp    # switch to it, "olscp ols use official" switches back
```

The build installs the compiler toolchain with `dnf` and fetches the OpenLiteSpeed sources from GitHub at pinned commits. The same actions are on the **Version** page of the WHM plugin.

![Apache configuration imported by olscp](docs/apache.png)

## Command line

| Command | Description |
|---|---|
| `olscp status` | Server, watcher and sync status |
| `olscp enable` / `olscp disable` | Switch to OpenLiteSpeed / back to Apache |
| `olscp restart` | Regenerate the configuration and restart gracefully |
| `olscp apache report` | Settings read from the Apache configuration |
| `olscp htaccess report` | `.htaccess` directives that could not be applied |
| `olscp cache list` / `olscp cache purge --all` | LSCache sites / purge |
| `olscp ols versions` / `olscp ols upgrade` | OpenLiteSpeed version and upgrade |
| `olscp settings key=value --apply` | Change a setting |

## Uninstall

```bash
bash uninstall.sh          # switch back to Apache, remove the plugins and services
bash uninstall.sh --purge  # also delete /usr/local/olscp, settings, cache and logs
```

## Limitations

- Not translated from `.htaccess`: `<If>`, `Require host/expr`, `SSLRequireSSL`, `AuthType Digest`, header-only `<FilesMatch>`.
- Directory listing is not available for sites on PHP-FPM, because cPanel FPM pools restrict `doc_root`. It works with LSAPI.
- Clients without SNI on dedicated IPs receive the server certificate.

## Contributing

Bug reports and pull requests are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md). Report security problems privately as described in [SECURITY.md](SECURITY.md).

## License

GPL-3.0, see [LICENSE](LICENSE). OpenLiteSpeed is developed by LiteSpeed Technologies and licensed under GPL-3.0; the patch in `build/patches/` is distributed under the same license. This project is not affiliated with or endorsed by LiteSpeed Technologies or cPanel, L.L.C. LiteSpeed, OpenLiteSpeed, LSCache, cPanel and WHM are trademarks of their respective owners.
