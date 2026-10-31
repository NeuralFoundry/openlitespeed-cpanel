#!/bin/bash
set -euo pipefail

PREFIX=/usr/local/olscp
SRC="$(cd "$(dirname "$0")" && pwd)"
WHM=/usr/local/cpanel/whostmgr/docroot

die() { echo "ERROR: $*" >&2; exit 1; }
step() { echo "==> $*"; }

[ "$(id -u)" = 0 ] || die "run as root"
[ -x /usr/local/cpanel/cpanel ] || die "cPanel not found"
. /etc/os-release
case "${ID_LIKE:-} $ID" in *rhel*|*centos*|*fedora*) ;; *) die "only RHEL-family systems are supported" ;; esac
EL="${VERSION_ID%%.*}"
[ "$EL" -ge 8 ] || die "EL8 or newer required"
[ "$(uname -m)" = x86_64 ] || [ "$(uname -m)" = aarch64 ] || die "unsupported architecture"

step "python"
command -v python3 >/dev/null || dnf -y -q install python3
python3 -c 'import yaml' 2>/dev/null || dnf -y -q install python3-pyyaml

step "files"
mkdir -p "$PREFIX" /etc/olscp /var/lib/olscp/backup
for d in bin lib libexec hooks systemd whm keys cpanel build; do
    rm -rf "$PREFIX/$d.new"
    cp -a "$SRC/$d" "$PREFIX/$d.new"
    rm -rf "$PREFIX/$d"
    mv "$PREFIX/$d.new" "$PREFIX/$d"
done
cp -f "$SRC/VERSION" "$PREFIX/VERSION"
chmod 755 "$PREFIX/bin/olscp" "$PREFIX/bin/olscp-user" "$PREFIX/libexec/httpd" "$PREFIX/libexec/ols-install.sh" "$PREFIX/hooks/"* "$PREFIX/whm/cgi/index.cgi" "$PREFIX/build/build-ols.sh"
chmod 755 "$PREFIX" "$PREFIX/bin" "$PREFIX/lib" "$PREFIX/lib/olscp"
find "$PREFIX/lib" -name '__pycache__' -prune -exec rm -rf {} +
chmod 700 /etc/olscp /var/lib/olscp
ln -sf "$PREFIX/bin/olscp" /usr/local/sbin/olscp

step "openlitespeed"
if [ -x "$PREFIX/ws/bin/openlitespeed" ] && [ "${OLSCP_UPGRADE_OLS:-0}" != 1 ]; then
    echo "openlitespeed $(cat "$PREFIX/ws/VERSION") already installed"
else
    if [ -n "${OLSCP_OLS_RPM:-}" ]; then
        "$PREFIX/libexec/ols-install.sh" --rpm "$OLSCP_OLS_RPM"
    else
        "$PREFIX/libexec/ols-install.sh" ${OLSCP_OLS_VERSION:-}
    fi
fi

LIVE_BUILD=0
if [ -n "${OLSCP_OLS_BIN:-}" ]; then
    step "openlitespeed olscp build"
    grep -q OLSCP_HT_NOTIFY "$OLSCP_OLS_BIN" || die "$OLSCP_OLS_BIN is not an olscp OpenLiteSpeed build"
    install -m 755 "$OLSCP_OLS_BIN" "$PREFIX/ws/bin/openlitespeed.olscp"
    LIVE_BUILD=1
elif [ "${OLSCP_BUILD_OLS:-0}" = 1 ]; then
    step "openlitespeed olscp build (compiling, this takes a while)"
    "$PREFIX/bin/olscp" ols build-run >/dev/null || die "build failed, see /var/log/olscp-ols-build.log"
    LIVE_BUILD=1
fi

step "lsphp"
for d in /opt/cpanel/ea-php*/; do
    v="$(basename "$d")"
    [[ "$v" =~ ^ea-php[0-9]+$ ]] || continue
    rpm -q "$v-php-litespeed" >/dev/null 2>&1 || dnf -y -q install "$v-php-litespeed" || echo "warning: $v-php-litespeed not installed"
done

step "wp-cli"
if [ -s "$PREFIX/.wp-cli.phar" ] && [ "${OLSCP_UPDATE_WPCLI:-0}" != 1 ]; then
    cp -f "$PREFIX/.wp-cli.phar" "$PREFIX/bin/wp-cli.phar"
else
    WTMP="$(mktemp -d /var/tmp/olscp-wpcli.XXXXXX)"
    TAG="$(curl -fsSL --max-time 30 https://api.github.com/repos/wp-cli/wp-cli/releases/latest | python3 -c 'import sys,json;print(json.load(sys.stdin)["tag_name"].lstrip("v"))')"
    URL="https://github.com/wp-cli/wp-cli/releases/download/v$TAG/wp-cli-$TAG.phar"
    curl -fsSL --max-time 120 -o "$WTMP/wp-cli.phar" "$URL"
    SUM="$(curl -fsSL --max-time 30 "$URL.sha512" | awk '{print $1}')"
    echo "$SUM  $WTMP/wp-cli.phar" | sha512sum -c --quiet || die "wp-cli checksum mismatch"
    install -m 755 "$WTMP/wp-cli.phar" "$PREFIX/bin/wp-cli.phar"
    cp -f "$WTMP/wp-cli.phar" "$PREFIX/.wp-cli.phar"
    rm -rf "$WTMP"
    echo "wp-cli $TAG"
fi
chmod 755 "$PREFIX/bin/wp-cli.phar"

step "watcher"
cp -f "$PREFIX/systemd/olscp-watch.service" /etc/systemd/system/olscp-watch.service
systemctl daemon-reload

step "whm plugin"
mkdir -p "$WHM/cgi/olscp" "$WHM/templates/olscp" "$WHM/addon_plugins"
cp -f "$PREFIX/whm/cgi/index.cgi" "$WHM/cgi/olscp/index.cgi"
chmod 700 "$WHM/cgi/olscp/index.cgi"
cp -f "$PREFIX/whm/templates/index.tmpl" "$WHM/templates/olscp/index.tmpl"
cp -f "$PREFIX/whm/olscp.png" "$WHM/addon_plugins/olscp.png"
/usr/local/cpanel/bin/register_appconfig "$PREFIX/whm/olscp.conf" >/dev/null

if [ -f /etc/olscp/cpanel_plugin ]; then
    "$PREFIX/bin/olscp" cpanel-plugin install >/dev/null || echo "warning: cPanel plugin update failed"
fi

step "config"
"$PREFIX/bin/olscp" settings >/dev/null
if [ "$LIVE_BUILD" = 1 ]; then
    "$PREFIX/bin/olscp" ols use olscp >/dev/null || die "could not switch to the olscp OpenLiteSpeed build"
fi
"$PREFIX/bin/olscp" sync >/dev/null
if [ -f /etc/olscp/active ]; then
    "$PREFIX/bin/olscp" reapply >/dev/null || true
    "$PREFIX/bin/olscp" restart >/dev/null || true
    systemctl restart olscp-watch.service || true
fi

echo
echo "olscp $(cat "$PREFIX/VERSION") installed."
echo "WHM > Plugins > OpenLiteSpeed, or: olscp enable"
