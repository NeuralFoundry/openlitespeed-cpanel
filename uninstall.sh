#!/bin/bash
set -uo pipefail

PREFIX=/usr/local/olscp
WHM=/usr/local/cpanel/whostmgr/docroot

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

if [ -f /etc/olscp/active ] || grep -q olscp-httpd-wrapper /usr/sbin/httpd 2>/dev/null; then
    "$PREFIX/bin/olscp" disable || { echo "could not switch back to Apache" >&2; exit 1; }
fi
"$PREFIX/bin/olscp" preview stop >/dev/null 2>&1 || true
"$PREFIX/bin/olscp" cpanel-plugin uninstall >/dev/null 2>&1 || true

systemctl stop olscp-ols-build.service >/dev/null 2>&1 || true
systemctl disable --now olscp-watch.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/olscp-watch.service
systemctl daemon-reload
rm -f /etc/dnf/universal-hooks/multi_pkgs/transaction/ea-__WILDCARD__/999-olscp-reapply

/usr/local/cpanel/bin/unregister_appconfig olscp >/dev/null 2>&1 || true
rm -rf "$WHM/cgi/olscp" "$WHM/templates/olscp" "$WHM/addon_plugins/olscp.png"
rm -f /usr/local/sbin/olscp /etc/yum.repos.d/olscp-litespeed.repo

if [ "${1:-}" = "--purge" ]; then
    rm -rf "$PREFIX" /etc/olscp /var/lib/olscp /run/olscp /var/log/olscp.log /var/log/olscp-ols-build.log /home/olscp-cache
else
    echo "files kept in $PREFIX (use --purge to remove)"
fi
echo "olscp removed"
