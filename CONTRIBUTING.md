# Contributing

Bug reports, fixes and improvements are welcome. Please read this page before opening a pull request.

## Reporting bugs

Open an issue with the bug report form. It asks for your OS, cPanel version and the output of `olscp status`, which is usually enough to find the cause. Security problems go through private reporting instead, see [SECURITY.md](SECURITY.md).

## Development setup

You need a cPanel & WHM server on AlmaLinux, Rocky Linux or CloudLinux 8 or 9 that you can break. Do not develop on a production server.

```bash
git clone https://github.com/NeuralFoundry/openlitespeed-cpanel.git
cd openlitespeed-cpanel
bash install.sh            # run again after every change
olscp preview start        # serve all sites on ports 8080/8443 next to Apache
olscp sync                 # regenerate the OpenLiteSpeed configuration
```

The generated configuration is in `/usr/local/olscp/ws/conf/`, the olscp log in `/var/log/olscp.log` and the server log in `/etc/apache2/logs/error_log`.

## Project layout

| Path | Contents |
|---|---|
| `lib/olscp/` | Python package: CLI, configuration generator, watcher |
| `lib/olscp/render.py` | Writes the OpenLiteSpeed configuration |
| `lib/olscp/htaccess.py` | `.htaccess` and Apache directive translation |
| `lib/olscp/apacheconf.py` | Apache configuration parser |
| `lib/olscp/apps.py` | Node.js, Python and Ruby applications from Passenger settings |
| `lib/olscp/cloudlinux.py` | CloudLinux LVE and CageFS |
| `lib/olscp/update.py`, `lib/olscp/olsbuild.py` | Updates, prebuilt and compiled OpenLiteSpeed builds |
| `libexec/lswsgi.py`, `libexec/lsrack.rb` | WSGI and Rack servers for Python and Ruby applications |
| `tests/` | Unit tests |
| `whm/` | WHM plugin, Perl CGI and Template Toolkit |
| `cpanel/` | cPanel plugin and AdminBin |
| `libexec/`, `hooks/`, `systemd/` | httpd wrapper, OpenLiteSpeed installer, EasyApache hook, watcher service |
| `build/` | OpenLiteSpeed build script, patches and the SHA-256 sums of the prebuilt binaries |

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests run without cPanel. The application server tests need Unix sockets, and the Rack tests also Ruby with the `rack` gem; they are skipped otherwise. Add a test for every translated directive and every fixed bug.

## Changing the OpenLiteSpeed patch

The patch in `build/patches/` applies to the OpenLiteSpeed commit pinned in `build/build-ols.sh`.

1. Clone OpenLiteSpeed, check out the pinned commit and apply the patch.
2. Make your change and write the patch again with `git diff > build/patches/0001-htaccess-live-reload.patch`.
3. On the test server run `olscp ols build`, then `olscp ols use olscp`.
4. Create, edit and delete `.htaccess` files with rewrite rules while the server is under load, and check `error_log` for crashes.
5. For a release, build the binary in clean AlmaLinux 8 and 9 containers with `build/build-ols.sh all`, compress it with `gzip -9 -n`, attach it to the release and put its SHA-256 in `build/prebuilt.txt`.

## Pull requests

- Keep each pull request to one topic and describe how you tested it.
- Python code must run on Python 3.9 with the standard library and PyYAML only.
- Follow the style of the surrounding code. Prefer clear code over comments.
- Interface text is English: short labels, no explanatory paragraphs.
- Changes to switching, the httpd wrapper or restarts must be tested with `/scripts/restartsrv_httpd`, `/scripts/restartsrv_httpd --status` and an EasyApache update.

## License

By contributing you agree that your contribution is licensed under [GPL-3.0](LICENSE).
