import grp
import os
import pwd
import re
import socket

import yaml

from . import const, util

try:
    _Loader = yaml.CSafeLoader
except AttributeError:
    _Loader = yaml.SafeLoader

SKIP_USERS = {'nobody', 'root', 'system'}
SERVICE_NAMES = ['cpanel', 'webmail', 'webdisk', 'cpcalendars', 'cpcontacts']
AUTOCONF_NAMES = ['autodiscover', 'autoconfig']


class Vhost(object):
    def __init__(self, name):
        self.name = name
        self.user = ''
        self.group = ''
        self.homedir = ''
        self.docroot = ''
        self.aliases = []
        self.service_aliases = []
        self.ip = ''
        self.php = ''
        self.fpm_socket = ''
        self.lsphp = ''
        self.ssl_cert = ''
        self.ssl_key = ''
        self.ssl_chain = ''
        self.source = 'cpanel'
        self.cgi = []
        self.suspended = False
        self.owner = ''
        self.domlog = ''
        self.byteslog = ''
        self.admin_email = ''
        self.custom_includes = []
        self.custom_text = []
        self.modsec_off = False
        self.ipv6 = False
        self.is_main = False

    def as_dict(self):
        return dict(self.__dict__)


class State(object):
    def __init__(self):
        self.hostname = ''
        self.main_ip = ''
        self.host_cert = ''
        self.default_php = ''
        self.php_versions = []
        self.vhosts = []
        self.users = []
        self.suspended_users = []
        self.trusted_proxies = []
        self.proxy_subdomains = True
        self.autodiscover = True
        self.warnings = []
        self.ipv6_addrs = []
        self.apache_indexes = True
        self.apache = None


def load_yaml(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return yaml.load(f, Loader=_Loader) or {}
    except (OSError, yaml.YAMLError):
        return None


def installed_php_versions():
    out = []
    try:
        names = sorted(os.listdir(const.EA_PHP_ROOT))
    except OSError:
        return out
    for n in names:
        if re.match(r'^ea-php\d+$', n) and os.path.isdir(os.path.join(const.EA_PHP_ROOT, n, 'root')):
            out.append(n)
    return out


def lsphp_path(ver):
    p = os.path.join(const.EA_PHP_ROOT, ver, 'root/usr/bin/lsphp')
    return p if os.access(p, os.X_OK) else ''


def fpm_socket(ver, vhost):
    pool = os.path.join(const.EA_PHP_ROOT, ver, 'root/etc/php-fpm.d', vhost + '.conf')
    text = util.read_text(pool)
    if not text:
        return ''
    m = re.search(r'^\s*listen\s*=\s*(\S+)\s*$', text, re.M)
    if not m:
        return ''
    sock = m.group(1).strip('"\'')
    return sock if sock.startswith('/') else ''


def resellers():
    out = set()
    for line in (util.read_text('/var/cpanel/resellers', '') or '').splitlines():
        if ':' in line:
            out.add(line.split(':', 1)[0].strip())
    return out


def trusted_proxies():
    text = util.read_text(const.CLOUDFLARE_CONF, '') or ''
    ips = []
    for m in re.finditer(r'^\s*RemoteIPTrustedProxy\s+(.+)$', text, re.M):
        ips.extend(m.group(1).split())
    return ips


def main_ip():
    ip = (util.read_text(const.MAINIP, '') or '').strip()
    if ip:
        return ip
    return util.parse_kv(const.WWWACCT, ' ').get('ADDR', '')


def ipv6_addrs():
    out = []
    for line in (util.read_text('/proc/net/if_inet6', '') or '').splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[3] == '00':
            out.append(':'.join(parts[0][i:i + 4] for i in range(0, 32, 4)))
    return out


def apache_indexes():
    text = util.read_text('/etc/apache2/conf/httpd.conf', '') or ''
    found = None
    for m in re.finditer(r'<Directory\s+"?(/|/home)"?\s*>(.*?)</Directory>', text, re.S):
        opt = re.search(r'^\s*Options\s+(.+)$', m.group(2), re.M)
        if not opt:
            continue
        toks = opt.group(1).lower().split()
        val = 'indexes' in toks or '+indexes' in toks or 'all' in toks
        if m.group(1) == '/home' or found is None:
            found = val
    return True if found is None else found


def truthy(v):
    return str(v).strip().lower() in ('1', 'on', 'yes', 'true')


def host_cert(hostname):
    p = os.path.join(const.SSL_DIR, hostname, 'combined')
    if os.path.isfile(p):
        return p
    if os.path.isfile(const.SERVICE_SSL):
        return const.SERVICE_SSL
    return ''


def load_state(apache=True):
    st = State()
    cpconf = util.parse_kv(const.CPANEL_CONFIG)
    st.proxy_subdomains = cpconf.get('proxysubdomains', '1') == '1'
    st.autodiscover = cpconf.get('autodiscover_proxy_subdomains', '1') == '1'
    st.hostname = socket.gethostname()
    st.main_ip = main_ip()
    st.host_cert = host_cert(st.hostname)
    st.php_versions = installed_php_versions()
    phpconf = load_yaml(const.EA4_PHP_CONF) or {}
    st.default_php = phpconf.get('default') or (st.php_versions[-1] if st.php_versions else '')
    st.trusted_proxies = trusted_proxies()
    st.ipv6_addrs = ipv6_addrs()
    st.apache_indexes = apache_indexes()
    resel = resellers()

    try:
        users = sorted(os.listdir(const.USERDATA))
    except OSError:
        users = []
    for user in users:
        if user in SKIP_USERS:
            continue
        udir = os.path.join(const.USERDATA, user)
        main = load_yaml(os.path.join(udir, 'main'))
        if not main or not main.get('main_domain'):
            continue
        st.users.append(user)
        suspended = os.path.exists(os.path.join(const.SUSPENDED, user))
        if suspended:
            st.suspended_users.append(user)
        main_domain = main['main_domain']
        subs = list(main.get('sub_domains') or [])
        addons = main.get('addon_domains') or {}
        parked = list(main.get('parked_domains') or [])
        bases = {main_domain: [main_domain] + parked}
        for addon, sub in addons.items():
            bases.setdefault(sub, []).append(addon)
        services = list(SERVICE_NAMES)
        if user in resel:
            services.append('whm')
        if st.autodiscover:
            services.extend(AUTOCONF_NAMES)

        for name in [main_domain] + subs:
            data = load_yaml(os.path.join(udir, name))
            if data is None:
                st.warnings.append('userdata missing: %s/%s' % (user, name))
                continue
            vh = Vhost(name)
            vh.user = data.get('user') or user
            vh.group = data.get('group') or vh.user
            vh.homedir = data.get('homedir') or ''
            vh.docroot = data.get('documentroot') or ''
            vh.ip = data.get('ip') or st.main_ip
            vh.owner = data.get('owner') or 'root'
            vh.admin_email = data.get('serveradmin') or ''
            vh.aliases = [a for a in (data.get('serveralias') or '').split() if a and a != name]
            ver = data.get('phpversion') or ''
            if not ver or ver == 'inherit' or ver not in st.php_versions:
                ver = st.default_php
            vh.php = ver
            if os.path.exists(os.path.join(udir, name + '.php-fpm.yaml')):
                vh.fpm_socket = fpm_socket(ver, name)
                if not vh.fpm_socket:
                    st.warnings.append('php-fpm pool not found: %s (%s)' % (name, ver))
            vh.lsphp = lsphp_path(ver)
            vh.is_main = name == main_domain
            vh.ipv6 = bool(data.get('ipv6'))
            vh.modsec_off = truthy(data.get('secruleengineoff'))
            if os.path.exists(os.path.join(udir, name + '_SSL')):
                cert = os.path.join(const.SSL_DIR, name, 'combined')
                if os.path.isfile(cert):
                    vh.ssl_cert = cert
                ssl_data = load_yaml(os.path.join(udir, name + '_SSL')) or {}
                vh.modsec_off = vh.modsec_off or truthy(ssl_data.get('secruleengineoff'))
            if str(data.get('hascgi', '1')) == '1':
                for sa in data.get('scriptalias') or []:
                    if sa.get('url') and sa.get('path'):
                        vh.cgi.append((sa['url'], sa['path']))
            for cl in data.get('customlog') or []:
                target = cl.get('target') or ''
                if target.endswith('-bytes_log'):
                    vh.byteslog = target
                elif cl.get('format') == 'combined':
                    vh.domlog = target
            if not vh.domlog:
                vh.domlog = os.path.join(const.DOMLOGS, name)
            if not vh.byteslog:
                vh.byteslog = os.path.join(const.DOMLOGS, name + '-bytes_log')
            if st.proxy_subdomains:
                for b in bases.get(name, []):
                    for s in services:
                        vh.service_aliases.append('%s.%s' % (s, b))
            vh.suspended = suspended
            for kind in ('std', 'ssl'):
                inc = '/etc/apache2/conf.d/userdata/%s/2_4/%s/%s' % (kind, user, name)
                if os.path.isdir(inc) and any(f.endswith('.conf') for f in os.listdir(inc)):
                    vh.custom_includes.append(inc)
            st.vhosts.append(vh)
    if apache:
        load_apache(st)
    return st


SYSTEM_NAMES = ('.localhost', '.localdomain')


def apache_user(vc):
    user, group = vc.user, vc.group
    if not user and vc.docroot:
        try:
            s = os.stat(vc.docroot)
            user = pwd.getpwuid(s.st_uid).pw_name
            group = grp.getgrgid(s.st_gid).gr_name
        except (OSError, KeyError):
            return '', '', ''
    try:
        pw = pwd.getpwnam(user)
    except KeyError:
        return '', '', ''
    if pw.pw_uid < 1000 and user != 'nobody':
        return '', '', ''
    return user, group or user, pw.pw_dir


def load_apache(st):
    from . import apacheconf
    try:
        info = apacheconf.read()
    except Exception as e:
        st.warnings.append('apache config not readable: %s' % e)
        return
    st.apache = info
    g = info['global']
    for ip in g.trusted_proxies:
        if ip not in st.trusted_proxies:
            st.trusted_proxies.append(ip)
    if g.indexes is not None:
        st.apache_indexes = g.indexes
    known = set()
    for vh in st.vhosts:
        known.add(vh.name)
        known.update(vh.aliases)
    extra = {}
    for vc in info['vhosts']:
        if vc.node.file == const.APACHE_CONF or not vc.name or vc.name in known:
            continue
        if vc.name.endswith(SYSTEM_NAMES) or not vc.docroot or not os.path.isdir(vc.docroot):
            continue
        vh = extra.get(vc.name)
        if vh is None:
            user, group, home = apache_user(vc)
            if not user:
                st.warnings.append('apache vhost %s skipped: no unprivileged owner' % vc.name)
                continue
            vh = Vhost(vc.name)
            vh.source = 'apache'
            vh.user, vh.group, vh.homedir = user, group, home
            vh.docroot = vc.docroot.rstrip('/') or '/'
            vh.ip = st.main_ip
            vh.owner = 'root'
            vh.admin_email = vc.admin
            vh.php = st.default_php
            vh.lsphp = lsphp_path(st.default_php) if user != 'nobody' else ''
            vh.domlog = os.path.join(const.DOMLOGS, vc.name)
            vh.byteslog = os.path.join(const.DOMLOGS, vc.name + '-bytes_log')
            extra[vc.name] = vh
            st.vhosts.append(vh)
        text = '\n'.join(apacheconf.to_text(vc.node.children))
        if text and ('%s:%d' % (vc.node.file, vc.node.line), text) not in vh.custom_text:
            vh.custom_text.append(('%s:%d' % (vc.node.file, vc.node.line), text))
        for a in vc.aliases:
            if a != vh.name and a not in vh.aliases and a not in known:
                vh.aliases.append(a)
        if vc.fpm_socket and os.path.exists(vc.fpm_socket):
            vh.fpm_socket = vc.fpm_socket
        if vc.ssl and vc.cert and os.path.isfile(vc.cert):
            vh.ssl_cert = vc.cert
            vh.ssl_key = vc.key if vc.key and os.path.isfile(vc.key) else ''
            vh.ssl_chain = vc.chain if vc.chain and os.path.isfile(vc.chain) else ''
