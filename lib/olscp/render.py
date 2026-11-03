import grp
import hashlib
import json
import os
import pwd
import re

from . import apps, cloudlinux, const, htaccess, util

LOG_FORMAT = '%h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-Agent}i"'
SERVICE_BACKENDS = [
    ('cpanel', 'olscp-svc-cpanel', const.SERVICE_PORTS['cpanel']),
    ('webmail', 'olscp-svc-webmail', const.SERVICE_PORTS['webmail']),
    ('whm', 'olscp-svc-whm', const.SERVICE_PORTS['whm']),
    ('webdisk', 'olscp-svc-webdisk', const.SERVICE_PORTS['webdisk']),
    ('cpcalendars', 'olscp-svc-cpdav', const.SERVICE_PORTS['cpcalendars']),
    ('cpcontacts', 'olscp-svc-cpdav', const.SERVICE_PORTS['cpcontacts']),
]
DEFAULT_VHOST = 'olscp-default'
SELF_PROXY = 'olscp-self'
SAFE_NAME = re.compile(r'^[A-Za-z0-9._-]+$')
MODSEC_RULES = const.OLS_ROOT + '/conf/olscp-modsec.conf'
MODSEC_MAIN = '/etc/apache2/conf.d/modsec2.conf'
REDIRECT_PATHS = 'cpanel|controlpanel|kpanel|securecontrolpanel|securecpanel|whm|securewhm'
AUTOINDEX_URI = '/_autoindex/default.php'
DEFAULT_DENIED = [r'^(\.ht(access|passwds?)|\.user\.ini|php\.ini)$', r'^(error_log|stderr\.log)$']
WELL_KNOWN = r'exp:^/\.well-known/.*'
MAX_LINE = 8000
MAX_CONTEXT = 4000
CONTROL = re.compile(r'[\x00-\x1f\x7f]')


def clean(value):
    return CONTROL.sub(' ', str(value)).rstrip('\\')


def fit(line, where):
    if len(line) <= MAX_LINE:
        return True
    util.log('configuration line longer than %d characters dropped in %s' % (MAX_LINE, where), 'WARN')
    return False


def autoindex_on(state, settings, vht=None):
    mode = settings.get('autoindex', 'auto')
    on = state.apache_indexes if mode == 'auto' else mode == 'on'
    if vht is not None and vht.autoindex is not None:
        on = on and vht.autoindex
    return on


def index_block(vb, on, files=None):
    idx = vb.block('index')
    idx.kv('useServer', 0)
    idx.kv('indexFiles', ', '.join(files or const.INDEX_FILES))
    idx.kv('autoIndex', 1 if on else 0)
    if on:
        idx.kv('autoIndexURI', AUTOINDEX_URI)


def blocked_ips():
    from . import protect
    return sorted(protect.load_blocked())


class Block(object):
    def __init__(self, head=None):
        self.head = head
        self.items = []

    def kv(self, key, value):
        if value is None or value == '':
            return self
        self.items.append(('kv', key, clean(value)))
        return self

    def raw(self, text):
        self.items.append(('raw', text, None))
        return self

    def heredoc(self, key, lines):
        if lines:
            self.items.append(('heredoc', key, list(lines)))
        return self

    def block(self, head):
        b = Block(clean(head))
        self.items.append(('block', b, None))
        return b

    def render(self, indent=0):
        pad = '  ' * indent
        out = []
        inner = indent
        if self.head is not None:
            out.append('%s%s {' % (pad, self.head))
            inner = indent + 1
        ipad = '  ' * inner
        for kind, a, b in self.items:
            if kind == 'kv':
                line = '%s%-24s %s' % (ipad, a, b)
                if fit(line, self.head):
                    out.append(line)
            elif kind == 'raw':
                for line in a.splitlines():
                    out.append(line if not line.strip() else ipad + line)
            elif kind == 'heredoc':
                tag = 'END_' + a
                out.append('%s%-24s <<<%s' % (ipad, a, tag))
                for l in b:
                    l = CONTROL.sub(' ', str(l))
                    if l.strip() != tag and fit(l, self.head):
                        out.append(l)
                out.append(tag)
            else:
                out.append(a.render(inner))
        if self.head is not None:
            out.append('%s}' % pad)
        return '\n'.join(out)


def uds(path):
    return 'uds://' + path.lstrip('/')


def ver_tag(ver):
    m = re.search(r'(\d+)$', ver or '')
    return m.group(1) if m else 'x'


def lsphp_name(user, ver):
    return 'lsphp-%s-%s' % (user, ver_tag(ver))


def norm_domain(d):
    d = d.strip().lower().rstrip('.')
    if d.startswith('www.'):
        d = d[4:]
    return d


def http3_off_names(settings):
    off = settings.get('http3_off') or ''
    return {d.strip().lower() for d in re.split(r'[\s,]+', off) if d.strip()}


def http3_for(name, settings):
    if not settings.get('http3'):
        return False
    return (name or '').lower() not in http3_off_names(settings)


def ssl_block(parent, cert, settings, head='vhssl', key=None, chain=None, quic=None):
    b = parent.block(head) if head else parent
    b.kv('keyFile', key or cert)
    b.kv('certFile', cert)
    if chain:
        b.kv('CACertFile', chain)
    b.kv('certChain', 1)
    b.kv('sslProtocol', 24)
    b.kv('enableECDHE', 1)
    b.kv('renegProtection', 1)
    b.kv('sslSessionCache', 1)
    b.kv('sslSessionTickets', 1)
    if not settings.get('http2'):
        b.kv('enableSpdy', 0)
    if head is not None:
        on = settings.get('http3') if quic is None else quic
        b.kv('enableQuic', 1 if on else 0)
    b.kv('enableStapling', 0)
    return b


def service_rules(state, proxy_self):
    rules = ['RewriteRule ^/\\.well-known/(acme-challenge|pki-validation|cpanel-dcv)/ - [L]']
    if state.proxy_subdomains:
        for svc, backend, _port in SERVICE_BACKENDS:
            rules.append('RewriteCond %%{HTTP_HOST} ^%s\\. [NC]' % svc)
            rules.append('RewriteRule ^/(.*)$ http://%s/$1 [P,L]' % backend)
        if state.autodiscover:
            for name in ('autoconfig', 'autodiscover'):
                rules.append('RewriteCond %%{HTTP_HOST} ^%s\\. [NC]' % name)
                if proxy_self:
                    rules.append('RewriteRule ^ http://%s/cgi-sys/%s.cgi [P,L]' % (SELF_PROXY, name))
                else:
                    rules.append('RewriteRule ^ /cgi-sys/%s.cgi [L]' % name)
    rules.append('RewriteRule ^/Microsoft-Server-ActiveSync(.*)$ http://olscp-svc-activesync/Microsoft-Server-ActiveSync$1 [P,L]')
    if proxy_self:
        rules.append('RewriteRule ^/(%s)/?$ http://%s%%{REQUEST_URI} [P,L]' % (REDIRECT_PATHS, SELF_PROXY))
        rules.append('RewriteRule ^/webmail(/.*)?$ http://%s%%{REQUEST_URI} [P,L]' % SELF_PROXY)
        rules.append('RewriteRule ^/[Aa]utodiscover/[Aa]utodiscover\\.xml$ http://%s%%{REQUEST_URI} [P,L]' % SELF_PROXY)
    else:
        rules.append('RewriteRule ^/(cpanel|controlpanel|kpanel)/?$ /cgi-sys/redirect.cgi [L]')
        rules.append('RewriteRule ^/(securecontrolpanel|securecpanel)/?$ /cgi-sys/sredirect.cgi [L]')
        rules.append('RewriteRule ^/securewhm/?$ /cgi-sys/swhmredirect.cgi [L]')
        rules.append('RewriteRule ^/whm/?$ /cgi-sys/whmredirect.cgi [L]')
        rules.append('RewriteRule ^/webmail(/.*)?$ /cgi-sys/wredirect.cgi [L]')
        rules.append('RewriteRule ^/[Aa]utodiscover/[Aa]utodiscover\\.xml$ /cgi-sys/autodiscover.cgi [L]')
    return rules


def suspended_rules():
    return [
        'RewriteCond %{REQUEST_URI} !^/cgi-sys/',
        'RewriteCond %{REQUEST_URI} !^/\\.well-known/',
        'RewriteRule ^ /cgi-sys/suspendedpage.cgi [L]',
    ]


def rewrite_block(parent, rules, autoload):
    b = parent.block('rewrite')
    b.kv('enable', 1)
    if autoload is not None:
        b.kv('autoLoadHtaccess', 1 if autoload else 0)
    b.kv('logLevel', 0)
    b.heredoc('rules', rules)
    return b


def accesslog_block(parent, domlog, byteslog):
    b = parent.block('accesslog ' + domlog)
    b.kv('useServer', 0)
    b.kv('logFormat', LOG_FORMAT)
    if byteslog:
        b.kv('bytesLog', byteslog)
    b.kv('rollingSize', 0)
    b.kv('keepDays', 0)
    b.kv('compressArchive', 0)
    return b


def policy_lines(c, scope, realm=None, browse=None):
    acc = scope.access
    deny_all = bool(acc) and acc.get('deny') == ['ALL'] and not acc.get('allow')
    if deny_all:
        c.kv('allowBrowse', 0)
    elif browse is not None:
        c.kv('allowBrowse', browse)
    if scope.auth_require and realm:
        c.kv('realm', realm)
        if scope.auth_name:
            c.kv('authName', scope.auth_name.replace('\n', ' '))
        kind, vals = scope.auth_require
        c.kv('required', kind if kind == 'valid-user' else '%s %s' % (kind, ' '.join(vals)))
    if acc and not deny_all:
        ac = c.block('accessControl')
        if acc.get('allow'):
            ac.kv('allow', ', '.join(acc['allow']))
        if acc.get('deny'):
            ac.kv('deny', ', '.join(acc['deny']))
    c.heredoc('extraHeaders', scope.headers)
    if scope.expires_active and (scope.expires_default or scope.expires_by_type):
        c.kv('enableExpires', 1)
        c.kv('expiresDefault', scope.expires_default)
        if scope.expires_by_type:
            c.kv('expiresByType', ', '.join('%s=%s' % kv for kv in sorted(scope.expires_by_type.items())))
    if scope.index:
        c.kv('indexFiles', ', '.join(scope.index))
    if scope.indexes is not None:
        c.kv('autoIndex', 1 if scope.indexes else 0)
        if scope.indexes:
            c.kv('autoIndexURI', AUTOINDEX_URI)


def realm_blocks(vb, realms):
    for name, (userfile, groupfile) in sorted(realms.items()):
        r = vb.block('realm ' + name)
        u = r.block('userDB')
        u.kv('location', userfile)
        u.kv('maxCacheSize', 200)
        u.kv('cacheTimeout', 60)
        if groupfile:
            g = r.block('groupDB')
            g.kv('location', groupfile)
            g.kv('maxCacheSize', 200)
            g.kv('cacheTimeout', 60)


def apache_global(state):
    return state.apache['global'] if state.apache else None


def index_files(state):
    g = apache_global(state)
    return g.directory_index if g and g.directory_index else const.INDEX_FILES


def denied_contexts(state):
    g = apache_global(state)
    out = []
    for pat, is_regex in (g.denied_files if g else []):
        out.append(htaccess.files_uri_regex('/', pat, is_regex))
    for pat in DEFAULT_DENIED:
        uri = htaccess.files_uri_regex('/', pat, True)
        if uri not in out:
            out.append(uri)
    return out


def alias_contexts(state):
    g = apache_global(state)
    out = []
    for url, path, cgi in (g.aliases if g else []):
        uri = url.rstrip('/') + '/'
        if uri == '/cgi-sys/' or not uri.startswith('/') or not os.path.isdir(path):
            continue
        out.append((uri, path.rstrip('/') + '/', cgi))
    return out


def proxy_targets(state):
    g = apache_global(state)
    out = []
    for path, url in (g.proxies if g else []):
        m = re.match(r'^(https?|wss?)://([^/:]+):?(\d+)?(/.*)?$', url)
        if not m or not path.startswith('/'):
            continue
        port = int(m.group(3) or (443 if m.group(1) in ('https', 'wss') else 80))
        out.append((path, m.group(2), port, m.group(4) or '/'))
    return out


def proxy_name(host, port):
    for _svc, backend, p in SERVICE_BACKENDS:
        if host in ('127.0.0.1', 'localhost') and p == port:
            return backend
    return 'olscp-proxy-%s-%d' % (re.sub(r'[^A-Za-z0-9]', '-', host), port)


def proxy_rules(state):
    rules = []
    for path, host, port, target in proxy_targets(state):
        src = re.escape(path.rstrip('/')).replace('\\/', '/')
        rules.append('RewriteRule ^%s(/.*)?$ http://%s%s$1 [P,L]' % (src, proxy_name(host, port), target.rstrip('/')))
    return rules


def passenger_defaults(state):
    g = apache_global(state)
    return dict(getattr(g, 'passenger', None) or {}) if g else {}


def global_headers(state):
    g = apache_global(state)
    out = []
    for h in (g.headers if g else []):
        conv = htaccess.convert_header(h)
        if conv:
            out.append(conv)
    return out


def ver_lsphp(ver):
    p = os.path.join(const.EA_PHP_ROOT, ver, 'root/usr/bin/lsphp')
    return p if os.access(p, os.X_OK) else ''


def php_types(vh, vht, lsapi):
    out = {}
    if not lsapi:
        return out
    out[vh.php] = 'application/x-httpd-php'
    for ver in sorted(vht.php_versions):
        if ver != vh.php and ver_lsphp(ver):
            out[ver] = 'application/x-httpd-olscp-' + ver
    return out


def handler_issues(vh, vht, types, lsapi):
    out = []
    for ctx in vht.contexts:
        h = ctx.get('php_handler')
        if not h or h[0] in types:
            continue
        if h[0] == vh.php and all(x in htaccess.PHP_SUFFIXES for x in h[1]):
            continue
        why = 'LSAPI for %s is not installed' % h[0] if lsapi else 'needs the LSAPI PHP mode'
        out.append((ctx['location'] + '.htaccess', ['AddHandler %s: %s' % (h[0], why)]))
    return out


def context_body(c, ctx, scope, lsapi, live, types, app=None, clone=None):
    policy_lines(c, scope, ctx.get('realm'), browse=1)
    entries = list(ctx.get('mime', []))
    h = ctx.get('php_handler')
    if h and not app and h[0] in types:
        entries.append(('addMIMEType', '%s %s' % (types[h[0]], ' '.join(h[1]))))
    mime = {}
    for k, v in entries:
        mime[k] = mime[k] + ', ' + v if k == 'addMIMEType' and k in mime else v
    for k in sorted(mime):
        c.kv(k, mime[k])
    if lsapi and ctx['php'] and not app:
        c.block('phpIniOverride').raw('\n'.join(ctx['php']))
    inline = list(ctx.get('pre_rules', []))
    if clone is not None:
        inline += clone
    elif not live or app:
        inline += [l for l in ctx['rewrite'] if not l.lower().startswith('rewriteengine')]
    full = clone is not None or not live or app
    if inline:
        r = c.block('rewrite')
        if full:
            r.kv('enable', 1)
        r.heredoc('rules', inline)
    elif app:
        c.block('rewrite').kv('enable', 0)


def clone_rules(ctx):
    src = ctx.get('rewrite_from')
    if not src:
        return []
    owner, lines = src
    engine = [l.split(None, 1)[1].strip().lower() for l in lines
              if l.lower().startswith('rewriteengine') and len(l.split()) > 1]
    if engine and engine[-1] == 'off':
        return None
    bases = [l.split(None, 1)[1].strip() for l in lines if l.lower().startswith('rewritebase') and len(l.split()) > 1]
    if bases and bases[-1].rstrip('/') + '/' != owner:
        return False
    rules = [l for l in lines if not l.lower().startswith(('rewriteengine', 'rewritebase', 'rewriteoptions'))]
    return ['RewriteBase ' + owner] + rules if rules else []


def nested_uris(uri, uris):
    inner = sorted(u for u in uris if u != uri and u.startswith(uri) and not u.startswith('exp:'))
    out = []
    for u in inner:
        if not any(u.startswith(o) for o in out):
            out.append(u)
    return [u[len(uri):] for u in out]


def header_groups(blocks):
    lists = [htaccess.ext_list(pat, rx) for pat, rx, _fs, _level in blocks]
    if not all(lists):
        return [(pat, rx, fs) for pat, rx, fs, _level in sorted(blocks, key=lambda b: -b[3])]
    groups = {}
    for ext in sorted({e for l in lists for e in l}):
        key = tuple(i for i, l in enumerate(lists) if ext in l)
        groups.setdefault(key, []).append(ext)
    out = []
    for key in sorted(groups):
        fs = htaccess.Scope()
        for i in key:
            fs = htaccess.with_files(fs, blocks[i][2])
        out.append((r'\.(%s)$' % '|'.join(re.escape(e) for e in groups[key]), True, fs))
    return out


def header_contexts(vb, vht, rendered, prefixes, headers, lsapi, types, seen):
    issues = []
    for ctx in vht.contexts:
        if not ctx.get('file_headers') or ctx['uri'] not in rendered:
            continue
        acc = ctx['scope'].access
        if acc and acc.get('deny') == ['ALL'] and not acc.get('allow'):
            continue
        where = ctx['location'] + '.htaccess'
        rules = clone_rules(ctx)
        if rules is False:
            issues.append((where, ['<FilesMatch> headers: RewriteBase differs from the directory']))
            continue
        exclude = nested_uris(ctx['uri'], prefixes)
        base = htaccess.with_headers(ctx['scope'], headers) if headers else ctx['scope']
        for pat, is_regex, fs in header_groups(ctx['file_headers']):
            uri = htaccess.files_uri_regex(ctx['uri'], pat, is_regex, exclude)
            if len(uri) > MAX_CONTEXT:
                issues.append((where, ['<FilesMatch> headers: too many subdirectories with their own settings']))
                break
            if uri in seen:
                continue
            seen.add(uri)
            c = vb.block('context ' + uri)
            context_body(c, ctx, htaccess.with_files(base, fs), lsapi, False, types, clone=rules or [])
            if rules is None and not ctx.get('pre_rules'):
                c.block('rewrite').kv('enable', 0)
    return issues


def render_vhost(vh, state, settings, vht, live=False):
    vht.apps, vht.app_issues = apps.resolve_all(vht.app_specs, vh.homedir, passenger_defaults(state))
    app_by_uri = {a['uri']: a for a in vht.apps}
    vb = Block()
    vb.kv('docRoot', vh.docroot)
    vb.kv('vhDomain', vh.name)
    if vh.aliases:
        vb.kv('vhAliases', ', '.join(vh.aliases))
    vb.kv('adminEmails', vh.admin_email)
    vb.kv('enableGzip', 1)
    vb.kv('enableBr', 1 if settings.get('brotli') else 0)
    fpm = bool(vh.fpm_socket) and settings.get('php_mode', 'auto') in ('auto', 'fpm')
    index_block(vb, autoindex_on(state, settings, vht) and not fpm, index_files(state))
    accesslog_block(vb, vh.domlog, vh.byteslog)
    for code, url in sorted(vht.errors.items()):
        e = vb.block('errorpage ' + code)
        e.kv('url', url)

    mode = settings.get('php_mode', 'auto')
    handler = None
    lsapi = False
    if vh.fpm_socket and mode in ('auto', 'fpm'):
        fpm_name = 'olscp-fpm-' + vh.name
        ep = vb.block('extprocessor ' + fpm_name)
        ep.kv('type', 'fcgi')
        ep.kv('address', uds(vh.fpm_socket))
        ep.kv('maxConns', 50)
        ep.kv('initTimeout', 300)
        ep.kv('retryTimeout', 0)
        ep.kv('persistConn', 1)
        ep.kv('pcKeepAliveTimeout', 60)
        ep.kv('respBuffer', 0)
        ep.kv('autoStart', 0)
        handler = 'fcgi:' + fpm_name
    elif vh.lsphp:
        handler = 'lsapi:' + lsphp_name(vh.user, vh.php)
        lsapi = True
        if vht.php_root:
            vb.block('phpIniOverride').raw('\n'.join(vht.php_root))
    types = php_types(vh, vht, lsapi)
    vht.report.extend(handler_issues(vh, vht, types, lsapi))
    if handler:
        sh = vb.block('scripthandler')
        for suf in const.PHP_SUFFIXES:
            sh.kv('add', '%s %s' % (handler, suf))
        for ver in sorted(types):
            if ver != vh.php:
                sh.kv('add', 'lsapi:%s olscp-%s' % (lsphp_name(vh.user, ver), ver))

    if settings.get('cache_module', True):
        m = vb.block('module cache')
        m.kv('storagePath', os.path.join(settings.get('cache_root') or const.CACHE_ROOT, vh.name))

    if vh.modsec_off and modsec_enabled(settings):
        m = vb.block('module mod_security')
        m.kv('ls_enabled', 0)

    rules = service_rules(state, True)
    rules.extend(proxy_rules(state))
    if vh.suspended:
        rules.extend(suspended_rules())
    rules.extend(vht.vhost_rules)
    rules.extend(vht.redirects)
    rewrite_block(vb, rules, True)
    realm_blocks(vb, vht.realms)

    seen = set()
    for uri in denied_contexts(state):
        seen.add(uri)
        vb.block('context ' + uri).kv('allowBrowse', 0)
    for fc in vht.file_contexts:
        if fc['uri'] in seen:
            continue
        seen.add(fc['uri'])
        c = vb.block('context ' + fc['uri'])
        policy_lines(c, fc['scope'], fc.get('realm'))
    if '/' in app_by_uri and WELL_KNOWN not in seen:
        seen.add(WELL_KNOWN)
        vb.block('context ' + WELL_KNOWN).kv('allowBrowse', 1)

    headers = global_headers(state) + vht.vhost_headers
    cgi_uris = {(url if url.endswith('/') else url + '/'): path for url, path in vh.cgi}
    contexts = list(vht.contexts)
    if headers and not any(ctx['uri'] == '/' for ctx in contexts):
        contexts.insert(0, {'uri': '/', 'location': vh.docroot.rstrip('/') + '/', 'scope': htaccess.Scope(),
                            'rewrite': [], 'php': []})
    rendered = set()
    for ctx in contexts:
        if ctx['uri'] in cgi_uris or ctx['uri'] == '/cgi-sys/':
            continue
        scope = ctx['scope']
        if headers:
            scope = htaccess.with_headers(scope, headers)
        c = vb.block('context ' + ctx['uri'])
        app = app_by_uri.pop(ctx['uri'], None)
        if app:
            apps.context(c, app)
        else:
            c.kv('location', ctx['location'])
            rendered.add(ctx['uri'])
        context_body(c, ctx, scope, lsapi, live, types, app)
    for uri in sorted(app_by_uri):
        c = vb.block('context ' + uri)
        apps.context(c, app_by_uri[uri])
        policy_lines(c, htaccess.with_headers(htaccess.Scope(), headers), browse=1)
        c.block('rewrite').kv('enable', 0)

    own = [(u.rstrip('/') + '/', p.rstrip('/') + '/', cg) for u, p, cg in vht.aliases
           if u.startswith('/') and os.path.isdir(p)]
    done = set()
    for uri, path, cgi in own + alias_contexts(state):
        if uri in cgi_uris or uri in done or uri == '/cgi-sys/':
            continue
        done.add(uri)
        c = vb.block('context ' + uri)
        if cgi:
            c.kv('type', 'cgi')
        c.kv('location', path)
        c.kv('allowBrowse', 1)

    taken = done | set(cgi_uris) | {ctx['uri'] for ctx in contexts} | {a['uri'] for a in vht.apps}
    for app in vht.apps:
        for uri, path in apps.static_dirs(app, vh.docroot):
            if uri in taken or uri == '/cgi-sys/':
                continue
            taken.add(uri)
            c = vb.block('context ' + uri)
            c.kv('location', path)
            c.kv('allowBrowse', 1)

    c = vb.block('context /cgi-sys/')
    c.kv('type', 'cgi')
    c.kv('location', const.CGI_SYS + '/')
    c.kv('allowBrowse', 1)
    ht_by_uri = {ctx['uri']: ctx for ctx in vht.contexts}
    for uri, path in cgi_uris.items():
        c = vb.block('context ' + uri)
        c.kv('type', 'cgi')
        c.kv('location', path.rstrip('/') + '/')
        if uri in ht_by_uri:
            policy_lines(c, ht_by_uri[uri]['scope'], ht_by_uri[uri].get('realm'), browse=1)
        else:
            c.kv('allowBrowse', 1)

    prefixes = taken | {'/cgi-sys/'} | {ctx['uri'] for ctx in vht.contexts} | {fc['uri'] for fc in vht.file_contexts}
    vht.report.extend(header_contexts(vb, vht, rendered, prefixes, headers, lsapi, types, seen))

    if vh.ssl_cert:
        ssl_block(vb, vh.ssl_cert, settings, key=vh.ssl_key, chain=vh.ssl_chain,
                  quic=http3_for(vh.name, settings))
    return vb.render() + '\n'


def render_default_vhost(state, settings):
    vb = Block()
    vb.kv('docRoot', const.DEFAULT_DOCROOT)
    vb.kv('vhDomain', state.hostname)
    vb.kv('enableGzip', 1)
    index_block(vb, False, index_files(state))
    rewrite_block(vb, service_rules(state, False) + proxy_rules(state), False)
    for uri in denied_contexts(state):
        vb.block('context ' + uri).kv('allowBrowse', 0)
    c = vb.block('context /cgi-sys/')
    c.kv('type', 'cgi')
    c.kv('location', const.CGI_SYS + '/')
    c.kv('allowBrowse', 1)
    if state.host_cert:
        ssl_block(vb, state.host_cert, settings)
    return vb.render() + '\n'


def lsphp_processor(root, name, user, group, ver_path, settings):
    ep = root.block('extprocessor ' + name)
    ep.kv('type', 'lsapi')
    ep.kv('address', uds('/tmp/lshttpd/olscp-%s.sock' % name))
    ep.kv('maxConns', settings.get('lsphp_max_conns', 10))
    ep.kv('env', 'PHP_LSAPI_CHILDREN=%s' % settings.get('lsphp_children', 10))
    ep.raw('env                      LSAPI_AVOID_FORK=200M')
    ep.kv('initTimeout', 300)
    ep.kv('retryTimeout', 0)
    ep.kv('persistConn', 1)
    ep.kv('pcKeepAliveTimeout', 60)
    ep.kv('respBuffer', 0)
    ep.kv('autoStart', 2)
    ep.kv('path', ver_path)
    ep.kv('backlog', 100)
    ep.kv('instances', 1)
    ep.kv('extUser', user)
    ep.kv('extGroup', group)
    ep.kv('runOnStartUp', 3)
    ep.kv('extMaxIdleTime', 300)
    ep.kv('priority', 0)
    ep.kv('memSoftLimit', settings.get('mem_limit', '2047M'))
    ep.kv('memHardLimit', settings.get('mem_limit', '2047M'))
    ep.kv('procSoftLimit', settings.get('proc_soft_limit', 400))
    ep.kv('procHardLimit', settings.get('proc_hard_limit', 500))


def proxy_processor(root, name, address, conns=200):
    ep = root.block('extprocessor ' + name)
    ep.kv('type', 'proxy')
    ep.kv('address', address)
    ep.kv('maxConns', conns)
    ep.kv('pcKeepAliveTimeout', 60)
    ep.kv('initTimeout', 300)
    ep.kv('retryTimeout', 0)
    ep.kv('respBuffer', 0)


def modsec_available():
    return os.path.isfile(MODSEC_MAIN) and os.path.isfile(const.OLS_ROOT + '/modules/mod_security.so')


def modsec_enabled(settings):
    return settings.get('modsecurity', 'auto') != 'off' and modsec_available()


MODSEC_UNQUOTE = re.compile(r'^(SecRuleEngine|SecAuditEngine|SecRequestBodyAccess|SecResponseBodyAccess|SecDataDir|SecTmpDir|'
                            r'SecAuditLogType|SecAuditLogStorageDir|SecRequestBodyLimitAction|SecResponseBodyLimitAction|'
                            r'SecRequestBodyLimit|SecRequestBodyNoFilesLimit|SecResponseBodyLimit|SecDebugLogLevel|'
                            r'SecAuditLogRelevantStatus|SecAuditLogParts|SecArgumentSeparator|SecCookieFormat|'
                            r'SecUnicodeMapFile|SecPcreMatchLimit|SecPcreMatchLimitRecursion)\s+"([^"]*)"\s*$', re.I)
MODSEC_INLINE_DIR = '/etc/apache2/conf.d/modsec/'


def modsec_lines(path, depth=0):
    text = util.read_text(path, '') or ''
    out = []
    skip_depth = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        low = line.lower()
        if low.startswith('<ifmodule'):
            if 'ruid2' in low or 'itk' in low:
                skip_depth += 1
            continue
        if low.startswith('</ifmodule'):
            if skip_depth:
                skip_depth -= 1
            continue
        if skip_depth or low.startswith('loadmodule'):
            continue
        m = re.match(r'^Include\s+"?([^"]+)"?\s*$', line, re.I)
        if m and m.group(1).startswith(MODSEC_INLINE_DIR) and depth < 3:
            out.extend(modsec_lines(m.group(1), depth + 1))
            continue
        line = re.sub(r'^(SecAuditLog|SecDebugLog)\s+(?!/)(\S+)', lambda m: '%s /etc/apache2/%s' % (m.group(1), m.group(2)), line)
        mq = MODSEC_UNQUOTE.match(line)
        if mq:
            line = '%s %s' % (mq.group(1), mq.group(2))
        out.append(line)
    return out


def modsec_rules():
    lines = modsec_lines(MODSEC_MAIN)
    phases = set()
    for line in lines:
        m = re.match(r'^Include\s+"?([^"]+)"?\s*$', line, re.I)
        if not m:
            continue
        for inc in re.findall(r'(?m)^\s*SecDefaultAction\s+"?phase:(\d)', util.read_text(m.group(1), '') or ''):
            phases.add(inc)

    def overridden(line):
        m = re.match(r'^SecDefaultAction\s+"?phase:(\d)', line, re.I)
        return bool(m) and m.group(1) in phases

    return '\n'.join(l for l in lines if not overridden(l)) + '\n'


def render_server(state, settings, vhosts, extra_php=None):
    root = Block()
    root.kv('serverName', state.hostname)
    root.kv('user', 'nobody')
    root.kv('group', 'nobody')
    root.kv('priority', 0)
    if int(settings.get('workers') or 0) > 0:
        root.kv('httpdWorkers', int(settings['workers']))
    root.kv('autoRestart', 1)
    root.kv('chrootPath', '/')
    root.kv('enableChroot', 0)
    root.kv('inMemBufSize', '60M')
    root.kv('swappingDir', '/tmp/lshttpd/swap')
    root.kv('autoFix503', 1)
    root.kv('gracefulRestartTimeout', 300)
    root.kv('mime', 'conf/mime.properties')
    root.kv('showVersionNumber', 0)
    root.kv('disableInitLogRotation', 1)
    if state.trusted_proxies:
        root.kv('useIpInProxyHeader', 2)
    root.kv('adminEmails', 'root@localhost')
    root.kv('indexFiles', ', '.join(index_files(state)))
    root.kv('autoIndexURI', AUTOINDEX_URI)
    root.kv('autoLoadHtaccess', 1)
    lve = cloudlinux.lve_value(settings)
    if lve:
        root.kv('enableLVE', lve)

    el = root.block('errorlog ' + const.APACHE_ERROR_LOG)
    el.kv('logLevel', 'NOTICE')
    el.kv('debugLevel', 0)
    el.kv('rollingSize', 0)
    el.kv('enableStderrLog', 1)
    al = root.block('accesslog ' + const.APACHE_ACCESS_LOG)
    al.kv('logFormat', LOG_FORMAT)
    al.kv('rollingSize', 0)
    al.kv('keepDays', 0)
    al.kv('compressArchive', 0)

    ex = root.block('expires')
    ex.kv('enableExpires', 0)

    t = root.block('tuning')
    t.kv('maxConnections', settings.get('max_conns', 10000))
    t.kv('maxSSLConnections', settings.get('max_conns', 10000))
    t.kv('connTimeout', settings.get('conn_timeout', 300))
    t.kv('maxKeepAliveReq', 10000)
    t.kv('keepAliveTimeout', settings.get('keepalive_timeout', 5))
    t.kv('smartKeepAlive', 0)
    t.kv('sndBufSize', 0)
    t.kv('rcvBufSize', 0)
    t.kv('maxReqURLLen', 32768)
    t.kv('maxReqHeaderSize', 65536)
    t.kv('maxReqBodySize', settings.get('max_req_body', '2047M'))
    t.kv('maxDynRespHeaderSize', 32768)
    t.kv('maxDynRespSize', '2047M')
    t.kv('maxCachedFileSize', 4096)
    t.kv('totalInMemCacheSize', '20M')
    t.kv('maxMMapFileSize', '256K')
    t.kv('totalMMapCacheSize', '40M')
    t.kv('useSendfile', 1)
    t.kv('fileETag', 28)
    t.kv('SSLCryptoDevice', 'null')
    t.kv('enableGzipCompress', 1)
    t.kv('enableDynGzipCompress', 1)
    t.kv('gzipCompressLevel', 6)
    t.kv('enableBrCompress', 4 if settings.get('brotli') else 0)
    t.kv('brStaticCompressLevel', 6)
    t.kv('compressibleTypes', 'default')
    t.kv('gzipAutoUpdateStatic', 1)
    t.kv('gzipStaticCompressLevel', 6)
    t.kv('gzipMaxFileSize', '10M')
    t.kv('gzipMinFileSize', 300)
    t.kv('quicEnable', 1 if settings.get('http3') else 0)
    t.kv('quicShmDir', '/dev/shm/ols')

    fa = root.block('fileAccessControl')
    fa.kv('followSymbolLink', 1)
    fa.kv('checkSymbolLink', 1)
    fa.kv('forceStrictOwnership', 0)
    fa.kv('requiredPermissionMask', '000')
    fa.kv('restrictedPermissionMask', '000')

    pc = root.block('perClientConnLimit')
    pc.kv('staticReqPerSec', 0)
    pc.kv('dynReqPerSec', 0)
    pc.kv('outBandwidth', 0)
    pc.kv('inBandwidth', 0)
    pc.kv('softLimit', 10000)
    pc.kv('hardLimit', 10000)
    pc.kv('gracePeriod', 15)
    pc.kv('banPeriod', 300)
    pc.kv('blockBadReq', 1 if settings.get('block_bad_req', True) else 0)

    cg = root.block('CGIRLimit')
    cg.kv('maxCGIInstances', 200)
    cg.kv('minUID', 11)
    cg.kv('minGID', 10)
    cg.kv('priority', 0)
    cg.kv('CPUSoftLimit', 3600)
    cg.kv('CPUHardLimit', 3700)
    cg.kv('memSoftLimit', settings.get('mem_limit', '2047M'))
    cg.kv('memHardLimit', settings.get('mem_limit', '2047M'))
    cg.kv('procSoftLimit', settings.get('proc_soft_limit', 400))
    cg.kv('procHardLimit', settings.get('proc_hard_limit', 500))
    cg.kv('cgroups', 2 if settings.get('cgroups') and not lve else 1)

    ad = root.block('accessDenyDir')
    for d in ('/', '/etc/*', '/dev/*', 'conf/*', 'admin/conf/*', '/root/*', '/var/cpanel/*'):
        ad.raw('dir                      ' + d)

    ac = root.block('accessControl')
    allow = ['ALL'] + ['%sT' % ip for ip in state.trusted_proxies]
    ac.kv('allow', ', '.join(allow))
    deny = blocked_ips()
    if deny:
        ac.kv('deny', ', '.join(deny))
    else:
        ac.raw('deny')

    seen = set()
    for _svc, backend, port in SERVICE_BACKENDS:
        if backend in seen:
            continue
        seen.add(backend)
        proxy_processor(root, backend, '127.0.0.1:%d' % port)
    proxy_processor(root, 'olscp-svc-activesync', '127.0.0.1:%d' % const.ACTIVESYNC_PORT, 100)
    proxy_processor(root, SELF_PROXY, '127.0.0.1:%d' % int(settings.get('internal_port') or 49280), 100)
    for _path, host, port, _target in proxy_targets(state):
        name = proxy_name(host, port)
        if name not in seen:
            seen.add(name)
            proxy_processor(root, name, '%s:%d' % (host, port), 100)

    seen = set()
    for vh in vhosts:
        if vh.fpm_socket and settings.get('php_mode', 'auto') in ('auto', 'fpm'):
            continue
        if not vh.lsphp:
            continue
        name = lsphp_name(vh.user, vh.php)
        if name in seen:
            continue
        seen.add(name)
        lsphp_processor(root, name, vh.user, vh.group, vh.lsphp, settings)
    for vh, ver in extra_php or []:
        if vh.fpm_socket and settings.get('php_mode', 'auto') in ('auto', 'fpm') or not vh.lsphp:
            continue
        name = lsphp_name(vh.user, ver)
        path = ver_lsphp(ver)
        if name in seen or not path:
            continue
        seen.add(name)
        lsphp_processor(root, name, vh.user, vh.group, path, settings)

    if settings.get('cache_module', True):
        m = root.block('module cache')
        m.kv('ls_enabled', 1)
        m.kv('checkPrivateCache', 1)
        m.kv('checkPublicCache', 1)
        m.kv('maxCacheObjSize', 10000000)
        m.kv('maxStaleAge', 200)
        m.kv('qsCache', 1)
        m.kv('reqCookieCache', 1)
        m.kv('respCookieCache', 1)
        m.kv('ignoreReqCacheCtrl', 1)
        m.kv('ignoreRespCacheCtrl', 0)
        m.kv('enableCache', 0)
        m.kv('expireInSeconds', 3600)
        m.kv('enablePrivateCache', 0)
        m.kv('privateExpireInSeconds', 3600)
        m.kv('storagePath', settings.get('cache_root') or const.CACHE_ROOT)

    if modsec_enabled(settings):
        m = root.block('module mod_security')
        m.kv('modsecurity', 'on')
        m.kv('modsecurity_rules_file', MODSEC_RULES)
        m.kv('ls_enabled', 1)

    for vh in vhosts:
        v = root.block('virtualhost ' + vh.name)
        v.kv('vhRoot', vh.homedir or os.path.dirname(vh.docroot))
        v.kv('configFile', '$SERVER_ROOT/conf/vhosts/olscp/%s.conf' % vh.name)
        v.kv('allowSymbolLink', 1)
        v.kv('enableScript', 1)
        v.kv('restrained', 1)
        v.kv('setUIDMode', 2)
        v.kv('user', vh.user)
        v.kv('group', vh.group)
    v = root.block('virtualhost ' + DEFAULT_VHOST)
    v.kv('vhRoot', '/var/www/')
    v.kv('configFile', '$SERVER_ROOT/conf/vhosts/olscp/%s.conf' % DEFAULT_VHOST)
    v.kv('allowSymbolLink', 1)
    v.kv('enableScript', 1)
    v.kv('restrained', 0)
    v.kv('setUIDMode', 0)

    off = int(settings.get('port_offset') or 0)
    http_map, https_map, dupes = listener_maps(state, vhosts)
    addrs = ['*']
    if ipv6_wanted(state, vhosts, settings):
        addrs.append('[ANY]')
    for a in addrs:
        suffix = '' if a == '*' else '-v6'
        lh = root.block('listener olscp-http' + suffix)
        lh.kv('address', '%s:%d' % (a, 80 + off))
        lh.kv('secure', 0)
        for name, doms in http_map:
            lh.kv('map', '%s %s' % (name, ', '.join(doms)))
        ls = root.block('listener olscp-https' + suffix)
        ls.kv('address', '%s:%d' % (a, 443 + off))
        ls.kv('secure', 1)
        if state.host_cert:
            ssl_block(ls, state.host_cert, settings, head=None)
        for name, doms in https_map:
            ls.kv('map', '%s %s' % (name, ', '.join(doms)))
    li = root.block('listener olscp-internal')
    li.kv('address', '127.0.0.1:%d' % int(settings.get('internal_port') or 49280))
    li.kv('secure', 0)
    li.kv('map', '%s *' % DEFAULT_VHOST)
    return root.render() + '\n', dupes


def ipv6_wanted(state, vhosts, settings):
    mode = settings.get('ipv6', 'auto')
    if mode == 'off' or not state.ipv6_addrs:
        return False
    if mode == 'on':
        return True
    return any(vh.ipv6 for vh in vhosts)


def listener_maps(state, vhosts):
    used = {}
    dupes = []
    http_map = []
    https_map = []

    def take(name, domains):
        out = []
        for d in domains:
            n = norm_domain(d)
            if not n:
                continue
            if n in used:
                if used[n] != name:
                    dupes.append((n, used[n], name))
                continue
            used[n] = name
            out.append(n)
        return out

    ip_users = {}
    for vh in vhosts:
        ip_users.setdefault(vh.ip, set()).add(vh.user)
    dedicated = {}
    for vh in vhosts:
        if vh.ip and vh.ip != state.main_ip and len(ip_users.get(vh.ip, ())) == 1 and vh.is_main:
            dedicated[vh.name] = vh.ip

    for vh in vhosts:
        extra = [dedicated[vh.name]] if vh.name in dedicated else []
        doms = take(vh.name, [vh.name] + vh.aliases + vh.service_aliases + extra)
        if doms:
            http_map.append((vh.name, doms))
            if vh.ssl_cert:
                https_map.append((vh.name, doms))
    base = [state.hostname, state.main_ip, 'localhost', '127.0.0.1']
    default = [d for d in (norm_domain(x) for x in base if x) if d and d not in used] + ['*']
    http_map.append((DEFAULT_VHOST, default))
    https_map.append((DEFAULT_VHOST, default))
    return http_map, https_map, dupes


def admin_config(settings):
    text = util.read_text(const.OLS_ADMIN_CONF, '') or ''
    listen = settings.get('webadmin_listen') or '127.0.0.1:7080'
    return re.sub(r'(?m)^(\s*address\s+)\S+\s*$', lambda m: m.group(1) + listen, text, count=1)


def render_all(state, settings, ht_files=None, live=False):
    htaccess.reset_modules()
    files = {}
    vhosts = [vh for vh in state.vhosts if SAFE_NAME.match(vh.name) and vh.docroot and vh.user]
    skipped = [vh.name for vh in state.vhosts if vh not in vhosts]
    cache = {}
    report = {}
    app_info = {}
    built = [(vh, htaccess.build(vh.docroot, ht_files or [], cache, vh.custom_includes, vh.custom_text, vh.php))
             for vh in vhosts]
    extra = [(vh, ver) for vh, vht in built for ver in sorted(vht.php_versions)]
    server, dupes = render_server(state, settings, vhosts, extra)
    files[const.OLS_CONF] = server
    for vh, vht in built:
        files[os.path.join(const.OLS_VHOST_DIR, vh.name + '.conf')] = render_vhost(vh, state, settings, vht, live)
        if vht.report:
            report[vh.name] = vht.report
        if vht.apps or vht.app_issues:
            app_info[vh.name] = {'user': vh.user, 'docroot': vh.docroot, 'apps': vht.apps, 'issues': vht.app_issues}
    files[os.path.join(const.OLS_VHOST_DIR, DEFAULT_VHOST + '.conf')] = render_default_vhost(state, settings)
    admin = admin_config(settings)
    if admin:
        files[const.OLS_ADMIN_CONF] = admin
    if modsec_enabled(settings):
        files[MODSEC_RULES] = modsec_rules()
    return files, {'skipped': skipped, 'duplicates': dupes, 'vhosts': len(vhosts), 'htaccess': report, 'apps': app_info}


def conf_owner():
    try:
        return pwd.getpwnam('lsadm').pw_uid, grp.getgrnam('lsadm').gr_gid
    except KeyError:
        return 0, 0


def digest(files):
    h = hashlib.sha256()
    for k in sorted(files):
        h.update(k.encode())
        h.update(b'\0')
        h.update(files[k].encode())
    return h.hexdigest()


def apply(files):
    owner = conf_owner()
    changed = []
    for path, content in files.items():
        if util.read_text(path) == content:
            continue
        util.write_atomic(path, content, 0o640, owner)
        changed.append(path)
    keep = {os.path.basename(p) for p in files if os.path.dirname(p) == const.OLS_VHOST_DIR}
    removed = []
    try:
        for f in os.listdir(const.OLS_VHOST_DIR):
            base = re.sub(r'\.conf(0|\.txt)$', '.conf', f)
            if base.endswith('.conf') and base not in keep:
                os.unlink(os.path.join(const.OLS_VHOST_DIR, f))
                removed.append(f)
    except OSError:
        pass
    return changed, removed
