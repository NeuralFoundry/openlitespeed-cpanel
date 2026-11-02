# Changelog

## 0.5.0

- Node.js and Python applications from cPanel Application Manager and the CloudLinux Node.js and Python selectors run on OpenLiteSpeed
- New WSGI server for Python applications, `libexec/lswsgi.py`
- WHM plugin: Apps page with application state and restart
- New command `olscp apps`
- `SSLRequireSSL` in `.htaccess` is translated
- Unit tests in `tests/`
- The OpenLiteSpeed build workflow runs only when started by hand

## 0.4.0

- Live `.htaccess` reload with the optional patched OpenLiteSpeed build
- Apache configuration import: includes, aliases, proxies, denied files, headers and extra virtual hosts
- More `.htaccess` directives: `AddType`, `ForceType`, `AddDefaultCharset`, `SetEnv`, `SetEnvIf`, `BrowserMatch`
- Graceful restarts keep PHP processes and OPcache
