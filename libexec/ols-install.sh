#!/bin/bash
set -euo pipefail

ROOT=/usr/local/olscp/ws
KEYS=/usr/local/olscp/keys
REPO=/etc/yum.repos.d/olscp-litespeed.repo
WANT=""
LOCAL_RPM=""
while [ $# -gt 0 ]; do
    case "$1" in
        --rpm) LOCAL_RPM="$2"; shift 2 ;;
        *) WANT="$1"; shift ;;
    esac
done

. /etc/os-release
EL="${VERSION_ID%%.*}"
ARCH="$(uname -m)"
KEYNAME=RPM-GPG-KEY-litespeed
[ "$EL" -ge 10 ] && KEYNAME=RPM-GPG-KEY-litespeed2025
KEY=/etc/pki/rpm-gpg/olscp-$KEYNAME
install -m 644 "$KEYS/$KEYNAME" "$KEY"
for k in "$KEYS"/RPM-GPG-KEY-litespeed*; do rpm --import "$k"; done
ALLOWED="$(for k in "$KEYS"/RPM-GPG-KEY-litespeed*; do gpg --with-colons --show-keys "$k" 2>/dev/null | awk -F: '/^pub/{print tolower(substr($5,9))}' || true; done)"
[ -n "$ALLOWED" ] || { echo "pinned LiteSpeed keys unreadable" >&2; exit 1; }

cat > "$REPO" <<EOF
[olscp-litespeed]
name=LiteSpeed (olscp) EL$EL $ARCH
baseurl=https://rpms.litespeedtech.com/centos/$EL/$ARCH/
enabled=0
gpgcheck=1
repo_gpgcheck=0
gpgkey=file://$KEY

[olscp-litespeed-update]
name=LiteSpeed updates (olscp) EL$EL $ARCH
baseurl=https://rpms.litespeedtech.com/centos/$EL/update/$ARCH/
enabled=0
gpgcheck=1
repo_gpgcheck=0
gpgkey=file://$KEY
EOF

TMP="$(mktemp -d /var/tmp/olscp-ols.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
if [ -n "$LOCAL_RPM" ]; then
    cp "$LOCAL_RPM" "$TMP/openlitespeed-local.rpm"
else
    PKG=openlitespeed
    [ -n "$WANT" ] && PKG="openlitespeed-$WANT"
    if ! dnf -q download --disablerepo='*' --enablerepo='olscp-litespeed,olscp-litespeed-update' --destdir "$TMP" "$PKG" >/dev/null 2>"$TMP/dnf.err"; then
        cat "$TMP/dnf.err" >&2
        echo "download from rpms.litespeedtech.com failed; if outbound traffic to LiteSpeed is redirected on this server, download the RPM elsewhere and run: $0 --rpm /path/openlitespeed.rpm" >&2
        exit 1
    fi
fi
RPMF="$(ls -1 "$TMP"/openlitespeed-*.rpm | sort -V | tail -1)"
CHK="$(rpm -K "$RPMF" 2>&1 || true)"
case "$CHK" in
    *"digests signatures OK"*) ;;
    *) echo "signature check failed: $CHK" >&2; exit 1 ;;
esac
SIGKEY="$(rpm -qp --qf '%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%{RSAHEADER:pgpsig}}|\n' "$RPMF" 2>/dev/null | grep -o 'Key ID [0-9a-fA-F]*' | awk '{print tolower($3)}' || true)"
if [ -z "$SIGKEY" ] || ! echo "$ALLOWED" | grep -qx "${SIGKEY: -8}"; then
    echo "package not signed by a pinned LiteSpeed key: ${SIGKEY:-none}" >&2
    exit 1
fi
NEWVER="$(rpm -qp --qf '%{VERSION}' "$RPMF")"

mkdir -p "$TMP/x"
(cd "$TMP/x" && rpm2cpio "$RPMF" | cpio -idm --quiet)
SRC="$TMP/x/usr/local/lsws"
[ -f "$SRC/bin/openlitespeed" ] || { echo "package layout unexpected" >&2; exit 1; }

getent group lsadm >/dev/null || groupadd -r lsadm
getent passwd lsadm >/dev/null || useradd -g lsadm -d / -r -s /sbin/nologin -c lsadm lsadm
usermod -G lsadm,nobody lsadm >/dev/null 2>&1 || true

FRESH=0
[ -x "$ROOT/bin/openlitespeed" ] || FRESH=1
mkdir -p "$ROOT"
if [ "$FRESH" = 1 ]; then
    cp -a "$SRC/." "$ROOT/"
else
    for d in "$SRC"/*; do
        n="$(basename "$d")"
        case "$n" in
            conf|cachedata|logs|tmp|backup|autoupdate|lsns) continue ;;
            admin)
                for a in "$d"/*; do
                    an="$(basename "$a")"
                    case "$an" in conf|logs|tmp|cgid) continue ;; esac
                    rm -rf "$ROOT/admin/$an.new"
                    cp -a "$a" "$ROOT/admin/$an.new"
                    rm -rf "$ROOT/admin/$an"
                    mv "$ROOT/admin/$an.new" "$ROOT/admin/$an"
                done
                ;;
            bin)
                cp -a "$d/openlitespeed" "$ROOT/bin/openlitespeed.new"
                mv -f "$ROOT/bin/openlitespeed.new" "$ROOT/bin/openlitespeed"
                for f in "$d"/*; do
                    fn="$(basename "$f")"
                    [ "$fn" = openlitespeed ] && continue
                    cp -a "$f" "$ROOT/bin/"
                done
                ;;
            *)
                rm -rf "$ROOT/$n.new"
                cp -a "$d" "$ROOT/$n.new"
                rm -rf "$ROOT/$n"
                mv "$ROOT/$n.new" "$ROOT/$n"
                ;;
        esac
    done
    cp -a "$SRC/VERSION" "$ROOT/VERSION"
fi

chown root:root "$ROOT"
chown -R lsadm:lsadm "$ROOT/conf" "$ROOT/admin/conf" "$ROOT/admin/tmp" 2>/dev/null || true
[ -d "$ROOT/autoupdate" ] && chown -R lsadm:lsadm "$ROOT/autoupdate"
[ -d "$ROOT/phpbuild" ] && chown -R lsadm:lsadm "$ROOT/phpbuild"
chgrp nobody "$ROOT/admin/cgid" "$ROOT/admin/tmp"
chown nobody:nobody "$ROOT/cachedata" "$ROOT/tmp"
chmod 0700 "$ROOT/tmp"
chown root:nobody "$ROOT/logs" "$ROOT/admin/logs"
chmod 0750 "$ROOT/logs" "$ROOT/admin/logs"
mkdir -p "$ROOT/conf/vhosts/olscp"
chown lsadm:lsadm "$ROOT/conf/vhosts/olscp"

if [ ! -s "$ROOT/admin/conf/webadmin.crt" ] || [ "$FRESH" = 1 ]; then
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 -subj "/CN=webadmin" \
        -keyout "$ROOT/admin/conf/webadmin.key" -out "$ROOT/admin/conf/webadmin.crt" 2>/dev/null
    chown lsadm:lsadm "$ROOT/admin/conf/webadmin.key" "$ROOT/admin/conf/webadmin.crt"
    chmod 400 "$ROOT/admin/conf/webadmin.key" "$ROOT/admin/conf/webadmin.crt"
fi
if [ "$FRESH" = 1 ]; then
    PASS="$(head -c 64 /dev/urandom | tr -dc A-Za-z0-9 | head -c 20)"
    ENC="$("$ROOT/admin/fcgi-bin/admin_php" -q "$ROOT/admin/misc/htpasswd.php" "$PASS")"
    echo "admin:$ENC" > "$ROOT/admin/conf/htpasswd"
    chown lsadm:lsadm "$ROOT/admin/conf/htpasswd"
    chmod 600 "$ROOT/admin/conf/htpasswd"
    rm -f "$ROOT/adminpasswd"
    sed -i -E 's/^(\s*address\s+)\*:7080\s*$/\1127.0.0.1:7080/' "$ROOT/admin/conf/admin_config.conf"
fi
rm -f /etc/init.d/lsws
echo "openlitespeed $NEWVER"
