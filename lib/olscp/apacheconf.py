import glob
import json
import os
import re

from . import const, util

SERVER_ROOT = '/etc/apache2'
MODULES_CACHE = const.STATE + '/apache-modules.json'
MAX_DEPTH = 16
CONDITIONALS = {'ifmodule', 'ifdefine', 'ifversion', 'iffile', 'ifdirective', 'ifsection'}
VAR = re.compile(r'\$\{([A-Za-z0-9_]+)\}')


class Node(object):
    __slots__ = ('name', 'args', 'children', 'file', 'line')

    def __init__(self, name, args, file='', line=0):
        self.name = name
        self.args = args
        self.children = []
        self.file = file
        self.line = line

    @property
    def key(self):
        return self.name.lower()

    def find(self, name):
        name = name.lower()
        return [c for c in self.children if c.key == name]

    def first(self, name):
        for c in self.children:
            if c.key == name.lower():
                return c
        return None

    def value(self, name, default=None):
        n = self.first(name)
        return n.args[0] if n is not None and n.args else default

    def walk(self, skip=()):
        for c in self.children:
            yield c
            if c.key not in skip:
                for x in c.walk(skip):
                    yield x

    def text(self):
        return '%s %s' % (self.name, ' '.join(quote(a) for a in self.args))


VHOST_OWN = {
    'servername', 'serveralias', 'documentroot', 'serveradmin', 'suexecusergroup', 'ruidgid', 'assignuserid',
    'sslengine', 'sslcertificatefile', 'sslcertificatekeyfile', 'sslcertificatechainfile', 'customlog', 'errorlog',
}


def to_text(nodes, depth=0):
    out = []
    pad = '  ' * depth
    for n in nodes:
        if depth == 0 and n.key in VHOST_OWN:
            continue
        if n.children or n.key in ('files', 'filesmatch', 'directory', 'directorymatch', 'location', 'locationmatch'):
            out.append('%s<%s %s>' % (pad, n.name, ' '.join(quote(a) for a in n.args)))
            out.extend(to_text(n.children, depth + 1))
            out.append('%s</%s>' % (pad, n.name))
        else:
            out.append(pad + n.text())
    return out


def quote(a):
    if a == '' or re.search(r'[\s"]', a):
        return '"%s"' % a.replace('\\', '\\\\').replace('"', '\\"')
    return a


def split_args(s):
    out = []
    i, n = 0, len(s)
    while i < n:
        while i < n and s[i].isspace():
            i += 1
        if i >= n:
            break
        q = s[i]
        if q in '"\'':
            i += 1
            buf = []
            while i < n and s[i] != q:
                if s[i] == '\\' and i + 1 < n and s[i + 1] in (q, '\\'):
                    i += 1
                buf.append(s[i])
                i += 1
            i += 1
            out.append(''.join(buf))
        else:
            j = i
            while j < n and not s[j].isspace():
                j += 1
            out.append(s[i:j])
            i = j
    return out


def logical_lines(text):
    buf, start = '', 0
    for no, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if line.endswith('\\'):
            if not buf:
                start = no
            buf += line[:-1] + ' '
            continue
        if buf:
            line = buf + line
            buf = ''
        else:
            start = no
        line = line.strip()
        if line and not line.startswith('#'):
            yield start, line


def apache_binary():
    return const.HTTPD_REAL if os.path.exists(const.HTTPD_REAL) else const.HTTPD


def runtime():
    binary = apache_binary()
    sig = []
    for p in [binary] + sorted(glob.glob(SERVER_ROOT + '/conf.modules.d/*.conf')):
        try:
            st = os.stat(p)
            sig.append('%s:%d:%d' % (p, st.st_mtime, st.st_size))
        except OSError:
            pass
    sig = '|'.join(sig)
    try:
        with open(MODULES_CACHE) as f:
            cached = json.load(f)
        if cached.get('sig') == sig:
            return cached
    except (OSError, ValueError):
        pass
    mods, version = [], ''
    rc, out = util.run([binary, '-M'], timeout=60)
    if rc == 0:
        mods = sorted({m.group(1) for m in re.finditer(r'^\s*([A-Za-z0-9_]+_module)\s', out, re.M)})
    rc, out = util.run([binary, '-v'], timeout=30)
    m = re.search(r'Apache/(\d+\.\d+\.\d+)', out)
    if m:
        version = m.group(1)
    data = {'sig': sig, 'modules': mods, 'version': version or '2.4.0'}
    if mods:
        try:
            util.write_atomic(MODULES_CACHE, json.dumps(data), 0o600)
        except OSError:
            pass
    return data


def present_modules():
    out = {'litespeed'}
    for m in runtime().get('modules') or []:
        n = re.sub(r'_module$', '', m)
        out.add(n)
        if n.startswith('mpm_'):
            out.add(n[4:])
    return out


def module_ids(arg):
    a = arg.strip().strip('"\'')
    if a.endswith('_module'):
        return {a}
    base = re.sub(r'\.c$', '', a)
    base = re.sub(r'^mod_', '', base)
    return {base + '_module', 'mpm_' + base + '_module', base}


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', v)[:3])


def version_match(args, current):
    if not args:
        return True
    neg = False
    if args[0].startswith('!'):
        neg = True
        args = [args[0][1:]] + args[1:] if args[0] != '!' else args[1:]
    if len(args) == 1:
        op, val = '=', args[0]
    else:
        op, val = args[0], args[1]
    if op in ('~', '=~') or (val.startswith('/') and val.endswith('/')):
        res = bool(re.search(val.strip('/'), current))
    else:
        a, b = version_tuple(current), version_tuple(val)
        n = len(version_tuple(val))
        a = a[:n]
        res = {'=': a == b, '==': a == b, '>': a > b, '>=': a >= b, '<': a < b, '<=': a <= b}.get(op, False)
    return not res if neg else res


class Parser(object):
    def __init__(self, modules=None, version='2.4.0', defines=None):
        self.modules = set(modules or [])
        self.version = version
        self.defines = dict(defines or {})
        self.files = []
        self.missing = []

    def expand(self, s):
        return VAR.sub(lambda m: self.defines.get(m.group(1), os.environ.get(m.group(1), m.group(0))), s)

    def condition(self, key, args):
        if key == 'ifmodule':
            a = args[0] if args else ''
            neg = a.startswith('!')
            ok = bool(module_ids(a.lstrip('!')) & self.modules)
            return ok != neg
        if key == 'ifdefine':
            a = args[0] if args else ''
            neg = a.startswith('!')
            return (a.lstrip('!') in self.defines) != neg
        if key == 'ifversion':
            return version_match(args, self.version)
        if key == 'iffile':
            a = args[0] if args else ''
            neg = a.startswith('!')
            p = a.lstrip('!')
            if not p.startswith('/'):
                p = os.path.join(SERVER_ROOT, p)
            return os.path.exists(p) != neg
        a = args[0] if args else ''
        return not a.startswith('!')

    def include_paths(self, pattern, optional):
        p = pattern if pattern.startswith('/') else os.path.join(SERVER_ROOT, pattern)
        if os.path.isdir(p):
            out = []
            for dp, dn, fn in os.walk(p):
                dn.sort()
                out.extend(os.path.join(dp, f) for f in sorted(fn))
            return out
        if any(ch in p for ch in '*?['):
            return sorted(f for f in glob.glob(p) if os.path.isfile(f))
        if os.path.isfile(p):
            return [p]
        if not optional:
            self.missing.append(p)
        return []

    def parse(self, path):
        root = Node('ROOT', [], path, 0)
        self.parse_file(path, root, 0, set())
        return root

    def parse_file(self, path, parent, depth, chain):
        real = os.path.realpath(path)
        if depth > MAX_DEPTH or real in chain:
            return
        text = util.read_text(path)
        if text is None:
            self.missing.append(path)
            return
        self.files.append(path)
        chain = chain | {real}
        stack = [(parent, True, 'ROOT')]
        for no, line in logical_lines(text):
            line = self.expand(line)
            cur, active, _tag = stack[-1]
            if line.startswith('</'):
                if len(stack) > 1:
                    stack.pop()
                continue
            if line.startswith('<') and line.endswith('>'):
                inner = line[1:-1].strip()
                parts = inner.split(None, 1)
                if not parts:
                    continue
                name = parts[0]
                args = split_args(parts[1]) if len(parts) > 1 else []
                key = name.lower()
                if not active:
                    stack.append((None, False, key))
                elif key in CONDITIONALS:
                    stack.append((cur, self.condition(key, args), key))
                else:
                    node = Node(name, args, path, no)
                    cur.children.append(node)
                    stack.append((node, True, key))
                continue
            if not active:
                continue
            parts = line.split(None, 1)
            name = parts[0]
            args = split_args(parts[1]) if len(parts) > 1 else []
            key = name.lower()
            if key in ('include', 'includeoptional'):
                for a in args:
                    for f in self.include_paths(a, key == 'includeoptional'):
                        self.parse_file(f, cur, depth + 1, chain)
                continue
            if key == 'define' and args:
                self.defines[args[0]] = args[1] if len(args) > 1 else ''
            elif key == 'undefine' and args:
                self.defines.pop(args[0], None)
            cur.children.append(Node(name, args, path, no))


def load(path=None):
    rt = runtime()
    p = Parser(rt.get('modules'), rt.get('version', '2.4.0'))
    root = p.parse(path or const.APACHE_CONF)
    return root, p, rt


DENY_REQUIRE = re.compile(r'^\s*all\s+denied\s*$', re.I)


def denies_all(node):
    order, allow, deny, req = None, [], [], []
    for c in node.walk():
        k = c.key
        if k == 'require':
            req.append(' '.join(c.args))
        elif k == 'order':
            order = ''.join(c.args).lower()
        elif k == 'allow' and c.args[:1] == ['from']:
            allow.extend(a.lower() for a in c.args[1:])
        elif k == 'deny' and c.args[:1] == ['from']:
            deny.extend(a.lower() for a in c.args[1:])
    if req:
        return all(DENY_REQUIRE.match(r) for r in req)
    if 'all' in deny and not allow:
        return True
    if order == 'allow,deny' and not allow:
        return True
    return False


def options_indexes(args):
    val = None
    for tok in args:
        t = tok.lower()
        if t in ('indexes', '+indexes', 'all', '+all'):
            val = True
        elif t in ('-indexes', 'none'):
            val = False
        elif not t.startswith(('+', '-')) and val is None:
            val = False
    return val


PASSENGER_GLOBAL = {
    'passengernodejs': 'node', 'passengerpython': 'python', 'passengerruby': 'ruby', 'passengerappenv': 'mode',
    'passengerdisablehtaccess': 'disable_htaccess',
}


class Global(object):
    def __init__(self):
        self.timeout = None
        self.keepalive = None
        self.keepalive_timeout = None
        self.max_keepalive_requests = None
        self.directory_index = []
        self.indexes = None
        self.denied_files = []
        self.headers = []
        self.aliases = []
        self.proxies = []
        self.trusted_proxies = []
        self.remoteip_header = ''
        self.server_tokens = ''
        self.unsupported = []
        self.passenger = {}

    def as_dict(self):
        return {
            'timeout': self.timeout, 'keepalive': self.keepalive, 'keepalive_timeout': self.keepalive_timeout,
            'max_keepalive_requests': self.max_keepalive_requests, 'directory_index': self.directory_index,
            'indexes': self.indexes, 'denied_files': [d[0] for d in self.denied_files],
            'headers': self.headers, 'aliases': [{'url': a, 'path': p, 'cgi': c} for a, p, c in self.aliases],
            'proxies': [{'path': a, 'url': u} for a, u in self.proxies], 'trusted_proxies': self.trusted_proxies,
            'remoteip_header': self.remoteip_header, 'passenger': self.passenger,
        }


class VHostConf(object):
    def __init__(self, node):
        self.node = node
        self.addresses = list(node.args)
        self.name = (node.value('ServerName') or '').lower()
        self.aliases = []
        for a in node.find('ServerAlias'):
            self.aliases.extend(x.lower() for x in a.args)
        self.docroot = node.value('DocumentRoot') or ''
        self.admin = node.value('ServerAdmin') or ''
        self.user = ''
        self.group = ''
        for key in ('SuexecUserGroup', 'RUidGid', 'AssignUserID'):
            n = node.first(key)
            if n is not None and len(n.args) >= 2:
                self.user, self.group = n.args[0], n.args[1]
                break
        self.ssl = (node.value('SSLEngine') or '').lower() == 'on'
        self.cert = node.value('SSLCertificateFile') or ''
        self.key = node.value('SSLCertificateKeyFile') or ''
        self.chain = node.value('SSLCertificateChainFile') or ''
        self.fpm_socket = ''
        for c in node.walk():
            if c.key == 'sethandler' and c.args and c.args[0].startswith('proxy:unix:'):
                self.fpm_socket = c.args[0][len('proxy:unix:'):].split('|', 1)[0]
                break
        self.ports = sorted({a.rsplit(':', 1)[1] for a in self.addresses if ':' in a})

    def custom_nodes(self):
        return [c for c in self.node.children if c.file != const.APACHE_CONF]


def global_info(root):
    g = Global()
    for c in root.children:
        k = c.key
        a = c.args
        if k == 'timeout' and a and a[0].isdigit():
            g.timeout = int(a[0])
        elif k == 'keepalive' and a:
            g.keepalive = a[0].lower() == 'on'
        elif k == 'keepalivetimeout' and a and a[0].isdigit():
            g.keepalive_timeout = int(a[0])
        elif k == 'maxkeepaliverequests' and a and a[0].isdigit():
            g.max_keepalive_requests = int(a[0])
        elif k == 'directoryindex':
            g.directory_index = [x for x in a if x.lower() != 'disabled']
        elif k == 'servertokens' and a:
            g.server_tokens = a[0]
        elif k in ('header', 'requestheader'):
            g.headers.append(c.text())
        elif k in ('alias', 'scriptalias') and len(a) >= 2:
            g.aliases.append((a[0], a[1], k == 'scriptalias'))
        elif k == 'proxypass' and len(a) >= 2 and not a[0].startswith('/___proxy_subdomain'):
            g.proxies.append((a[0], a[1]))
        elif k == 'remoteipheader' and a:
            g.remoteip_header = a[0]
        elif k in ('remoteiptrustedproxy', 'remoteipinternalproxy'):
            g.trusted_proxies.extend(a)
        elif k in PASSENGER_GLOBAL and a:
            g.passenger[PASSENGER_GLOBAL[k]] = a[0]
        elif k == 'directory' and a and a[0].rstrip('/') in ('', '/home'):
            for o in c.find('Options'):
                v = options_indexes(o.args)
                if v is not None and (g.indexes is None or a[0].rstrip('/') == '/home'):
                    g.indexes = v
        elif k in ('files', 'filesmatch') and a:
            regex = k == 'filesmatch'
            pat = a[0]
            if pat == '~' and len(a) > 1:
                regex, pat = True, a[1]
            if denies_all(c):
                g.denied_files.append((pat, regex))
    return g


def vhosts(root):
    out = []
    for c in root.walk(skip={'virtualhost'}):
        if c.key == 'virtualhost':
            v = VHostConf(c)
            if v.name or v.aliases:
                out.append(v)
    return out


def read(path=None):
    root, parser, rt = load(path)
    return {'root': root, 'global': global_info(root), 'vhosts': vhosts(root), 'files': parser.files,
            'missing': parser.missing, 'modules': rt.get('modules', []), 'version': rt.get('version')}
