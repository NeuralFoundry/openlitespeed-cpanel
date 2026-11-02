# Changelog

## 0.6.0

- Ruby (Rack) applications from cPanel Application Manager run through the new Rack server `libexec/lsrack.rb`, with Bundler support
- cPanel plugin: new Application Status page where customers see their applications, restart them and read their log
- CloudLinux: PHP and applications can start inside the LVE and CageFS of the account, olscp files are added to CageFS. Off by default
- Directory names with control characters are ignored, and generated configuration values cannot span lines. Before, a customer could add OpenLiteSpeed configuration with a directory name that contained a line break
- Prebuilt live `.htaccess` binaries for EL8 and EL9 on each release, downloaded and checked against pinned SHA-256 sums with `olscp ols fetch` or from the WHM plugin
- One-click updates from the Version page of the WHM plugin, `olscp update`
- `<FilesMatch>` blocks that only set headers or expiry times, as written by WP Rocket and W3 Total Cache, are applied. Overlapping blocks are merged like Apache does
- `AddHandler application/x-httpd-ea-phpXX` in a subdirectory selects that PHP version for the directory with LSAPI
- WHM Apps page shows the log file of each application
- The build script installs `libcap-devel`, needed on clean build hosts

## 0.5.0

- Node.js and Python applications from cPanel Application Manager and the CloudLinux Node.js and Python selectors run on OpenLiteSpeed
- New WSGI server for Python applications, `libexec/lswsgi.py`
- Applications restart when their settings change, and the LSCache storage of a site is purged when an application is added or removed
- WHM plugin: Apps page with application state and restart, tested with cPanel Application Manager on cPanel 138
- New command `olscp apps`
- `SSLRequireSSL` in `.htaccess` is translated
- Unit tests in `tests/`
- The OpenLiteSpeed build workflow runs only when started by hand

## 0.4.0

- Live `.htaccess` reload with the optional patched OpenLiteSpeed build
- Apache configuration import: includes, aliases, proxies, denied files, headers and extra virtual hosts
- More `.htaccess` directives: `AddType`, `ForceType`, `AddDefaultCharset`, `SetEnv`, `SetEnvIf`, `BrowserMatch`
- Graceful restarts keep PHP processes and OPcache
