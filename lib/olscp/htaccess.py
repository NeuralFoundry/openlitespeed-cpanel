import hashlib
import json
import os
import re
import shlex
import time

from . import const, util

STATE = const.STATE + '/htaccess.json'
SKIP_DIRS = {'.git', '.svn', '.hg', 'node_modules', '.trash', '.cagefs', '.cpanel', '.cache', '.npm', '.composer'}
MAX_DEPTH = 14
MAX_DIRS = 400000
PRESENT_MODULES = {
    'authz_core', 'rewrite', 'headers', 'expires', 'deflate', 'mime', 'alias', 'access_compat', 'dir',
    'setenvif', 'filter', 'env', 'autoindex', 'authn_file', 'authn_core', 'auth_basic', 'authz_user',
    'authz_host', 'authz_groupfile', 'version', 'ssl', 'lsapi', 'litespeed', 'http2', 'negotiation',
    'include', 'cgi', 'cgid', 'suexec', 'unique_id', 'remoteip', 'proxy', 'proxy_fcgi', 'proxy_http',
}
REWRITE = {'rewriteengine', 'rewritebase', 'rewritecond', 'rewriterule', 'rewriteoptions'}
PHP_INI = {'php_value', 'php_flag', 'php_admin_value', 'php_admin_flag'}
SETENVIF = {'setenvif', 'setenvifnocase', 'browsermatch', 'browsermatchnocase'}
ENV_ATTRS = {
    'user-agent': 'HTTP_USER_AGENT', 'referer': 'HTTP_REFERER', 'remote_addr': 'REMOTE_ADDR',
    'remote_host': 'REMOTE_HOST', 'request_uri': 'REQUEST_URI', 'request_method': 'REQUEST_METHOD',
    'request_protocol': 'SERVER_PROTOCOL', 'server_addr': 'SERVER_ADDR', 'host': 'HTTP_HOST',
    'query_string': 'QUERY_STRING',
}
IGNORED = {
    'addhandler', 'sethandler', 'removehandler', 'addcharset',
    'fileetag', 'serversignature',
    'checkspelling', 'contentdigest', 'defaulttype', 'addoutputfilter', 'addoutputfilterbytype', 'addencoding',
    'removetype', 'addlanguage', 'defaultlanguage', 'languagepriority', 'forcelanguagepriority', 'unsetenv',
    'passenv', 'limitrequestbody', 'indexoptions', 'indexignore', 'headername', 'readmename',
    'addicon', 'addiconbytype', 'addiconbyencoding', 'adddescription', 'defaulticon', 'ssilegacyexprparser',
    'secfilterengine', 'secfilterscanpost', 'authbasicprovider', 'satisfy', 'expiresactive', 'rewritemap',
    'cgipassauth', 'xbithack', 'mergeslashes', 'acceptpathinfo', 'suphp_configpath', 'passengerenabled',
}
UNIT = {'year': 31536000, 'month': 2592000, 'week': 604800, 'day': 86400, 'hour': 3600, 'minute': 60, 'second': 1}


class Scope(object):
    def __init__(self):
        self.access = None
        self.auth_type = None
        self.auth_name = None
        self.auth_user_file = None
        self.auth_group_file = None
        self.auth_require = None
        self.headers = []
        self.expires_active = None
        self.expires_default = None
        self.expires_by_type = {}
        self.index = None
        self.indexes = None
        self.mime = []
        self.pre_rules = []

    def has_policy(self):
        return bool(self.access or self.auth_require or self.headers or self.expires_active
                    or self.expires_by_type or self.expires_default or self.index or self.indexes is not None
                    or self.mime or self.pre_rules)


def with_headers(scope, headers):
    s = Scope()
    s.__dict__.update(scope.__dict__)
    s.headers = list(headers) + [h for h in scope.headers if h not in headers]
    return s


def header_line(name, rest, unsupported):
    args = split_args(rest)
    if not args:
        return None
    if args[0].lower() in ('always', 'onsuccess'):
        args = args[1:]
    if not args or args[0].lower() not in ('set', 'append', 'merge', 'add', 'unset'):
        unsupported.append('Header %s' % (args[0] if args else ''))
        return None
    if any(a.lower().startswith(('expr=', 'env=')) for a in args):
        unsupported.append('Header expr=/env=')
        return None
    out = ['RequestHeader' if name == 'requestheader' else 'Header', args[0].lower()]
    for a in args[1:]:
        out.append('"%s"' % a.replace('"', '\\"') if (' ' in a or a == '') else a)
    return ' '.join(out)


def convert_header(text):
    parts = text.split(None, 1)
    if len(parts) < 2:
        return None
    return header_line(parts[0].lower(), parts[1], [])


def env_rules(envs, deny_vars, allow_vars, unsupported):
    rules = []
    for var in deny_vars:
        conds = envs.get(var)
        if not conds:
            unsupported.append('Deny from env=%s' % var)
            continue
        for i, (attr, regex, nocase) in enumerate(conds):
            flags = ['NC'] if nocase else []
            if i < len(conds) - 1:
                flags.append('OR')
            rules.append('RewriteCond %%{%s} %s%s' % (attr, regex.replace(' ', '\\s'),
                                                     ' [%s]' % ','.join(flags) if flags else ''))
        rules.append('RewriteRule .* - [F]')
    if allow_vars:
        conds = []
        for var in allow_vars:
            if not envs.get(var):
                unsupported.append('Allow from env=%s' % var)
                return rules
            conds.extend(envs[var])
        for attr, regex, nocase in conds:
            rules.append('RewriteCond %%{%s} !%s%s' % (attr, regex.replace(' ', '\\s'), ' [NC]' if nocase else ''))
        rules.append('RewriteRule .* - [F]')
    return rules


def new_legacy():
    return {'order': None, 'allow': [], 'deny': [], 'allow_env': [], 'deny_env': [], 'seen': False}


class Ht(object):
    def __init__(self, path):
        self.path = path
        self.dir = os.path.dirname(path)
        self.scope = Scope()
        self.files = []
        self.locations = []
        self.directories = []
        self.rewrite = []
        self.php = []
        self.redirects = []
        self.errors = {}
        self.unsupported = []
        self.envs = {}
        self.aliases = []
        self.headers = []


def split_args(s):
    try:
        return shlex.split(s, posix=True)
    except ValueError:
        return s.split()


_present = []


def present_modules():
    if not _present:
        try:
            from . import apacheconf
            mods = apacheconf.present_modules()
        except Exception:
            mods = set()
        _present.append(mods if len(mods) > 1 else PRESENT_MODULES)
    return _present[0]


def module_present(arg):
    arg = arg.strip('"\'')
    neg = arg.startswith('!')
    name = arg.lstrip('!').strip('"\'').lower()
    name = re.sub(r'\.c$', '', name)
    name = re.sub(r'^mod_', '', name)
    name = re.sub(r'_module$', '', name)
    ok = name in present_modules()
    return not ok if neg else ok


def seconds(spec):
    spec = spec.strip().strip('"\'')
    m = re.match(r'^([AM])(\d+)$', spec)
    if m:
        return m.group(1) + m.group(2)
    parts = spec.split()
    if len(parts) < 3:
        return None
    base = 'M' if parts[0].lower().startswith('mod') else 'A'
    words = parts[1:]
    if words and words[0].lower() == 'plus':
        words = words[1:]
    total = 0
    i = 0
    while i + 1 < len(words):
        try:
            n = int(words[i])
        except ValueError:
            return None
        u = words[i + 1].lower().rstrip('s')
        if u not in UNIT:
            return None
        total += n * UNIT[u]
        i += 2
    return '%s%d' % (base, total) if total else None


def options_indexes(rest):
    val = None
    for tok in rest.split():
        t = tok.lower()
        if t in ('indexes', '+indexes', 'all', '+all'):
            val = True
        elif t in ('-indexes', 'none'):
            val = False
        elif not t.startswith(('+', '-')) and val is None:
            val = False
    return val


def access_from_require(reqs, ctx, envs=None):
    allow, deny, auth = [], [], None
    granted = denied = False
    for neg, kind, vals in reqs:
        if kind == 'all':
            v = vals[0].lower() if vals else ''
            if (v == 'granted') != neg:
                granted = True
            else:
                denied = True
        elif kind == 'ip':
            (deny if neg else allow).extend(vals)
        elif kind in ('valid-user', 'user', 'group'):
            auth = (kind, vals)
        elif kind in ('local',):
            (deny if neg else allow).append('127.0.0.1')
        elif kind == 'env' and envs is not None:
            envs[1 if neg else 0].extend(vals)
        else:
            ctx.append('Require %s' % kind)
    acc = None
    if denied and not allow:
        acc = {'allow': [], 'deny': ['ALL']}
    elif allow:
        acc = {'allow': allow, 'deny': ['ALL']}
    elif deny:
        acc = {'allow': ['ALL'], 'deny': deny}
    elif granted:
        acc = {'allow': ['ALL'], 'deny': []}
    return acc, auth


def access_from_legacy(order, allows, denies, ctx):
    al, dn = [], []
    for v in allows:
        if v.lower() == 'all':
            al.append('ALL')
        elif v.lower().startswith('env='):
            ctx.append('Allow from env=')
        elif re.match(r'^[0-9a-fA-F:.\[\]/*]+$', v):
            al.append(v)
        else:
            ctx.append('Allow from host')
    for v in denies:
        if v.lower() == 'all':
            dn.append('ALL')
        elif v.lower().startswith('env='):
            ctx.append('Deny from env=')
        elif re.match(r'^[0-9a-fA-F:.\[\]/*]+$', v):
            dn.append(v)
        else:
            ctx.append('Deny from host')
    order = (order or 'deny,allow').replace(' ', '').lower()
    if order == 'allow,deny':
        if 'ALL' in al:
            return {'allow': ['ALL'], 'deny': dn}
        if al:
            return {'allow': al, 'deny': ['ALL'] + [d for d in dn if d != 'ALL']}
        return {'allow': [], 'deny': ['ALL']}
    if 'ALL' in dn:
        if 'ALL' in al:
            return {'allow': ['ALL'], 'deny': []}
        return {'allow': al, 'deny': ['ALL']}
    if dn:
        return {'allow': ['ALL'], 'deny': dn}
    if al:
        return {'allow': ['ALL'], 'deny': []}
    return None


def apache_unquote(arg):
    arg = arg.strip()
    if len(arg) >= 2 and arg[0] == arg[-1] == '"':
        return arg[1:-1].replace('\\\\', '\\').replace('\\"', '"')
    return arg.strip('\'')


class Parser(object):
    def __init__(self, path, text, include=False):
        self.ht = Ht(path)
        self.include = include
        self.lines = self._logical(text)

    @staticmethod
    def _logical(text):
        out, buf = [], ''
        for raw in text.splitlines():
            line = raw.rstrip()
            if line.endswith('\\'):
                buf += line[:-1] + ' '
                continue
            line = (buf + line).strip()
            buf = ''
            if line and not line.startswith('#'):
                out.append(line)
        return out

    def parse(self):
        self._block(0, len(self.lines), self.ht.scope, True)
        return self.ht

    def _end_of(self, start, tag):
        depth = 0
        open_re = re.compile(r'^<%s[\s>]' % tag, re.I)
        close_re = re.compile(r'^</%s\s*>' % tag, re.I)
        for i in range(start, len(self.lines)):
            if open_re.match(self.lines[i]):
                depth += 1
            elif close_re.match(self.lines[i]):
                depth -= 1
                if depth == 0:
                    return i
        return len(self.lines) - 1

    def _block(self, a, b, scope, top, legacy=None, reqs=None):
        legacy = legacy if legacy is not None else new_legacy()
        reqs = reqs if reqs is not None else []
        i = a
        while i < b:
            line = self.lines[i]
            m = re.match(r'^<(/?)([A-Za-z]+)\s*([^>]*)>$', line)
            if m and m.group(1):
                i += 1
                continue
            if m:
                tag = m.group(2).lower()
                arg = m.group(3).strip()
                end = self._end_of(i, m.group(2))
                if tag == 'ifmodule':
                    if module_present(arg):
                        self._block(i + 1, end, scope, top, legacy, reqs)
                elif tag in ('ifversion', 'limit', 'limitexcept', 'requireany', 'requireall'):
                    if tag == 'requireall' or tag == 'requireany':
                        self._block(i + 1, end, scope, top, legacy, reqs)
                    else:
                        self._block(i + 1, end, scope, top, legacy, reqs)
                elif tag == 'requirenone':
                    sub = []
                    self._block(i + 1, end, scope, top, legacy, sub)
                    reqs.extend((not n, k, v) for n, k, v in sub)
                elif tag in ('files', 'filesmatch') and top:
                    regex = tag == 'filesmatch'
                    pat = arg
                    if pat.startswith('~'):
                        regex = True
                        pat = pat[1:].strip()
                    pat = apache_unquote(pat) if self.include else pat.strip('"\'')
                    fs = Scope()
                    fl = new_legacy()
                    fr = []
                    self._block(i + 1, end, fs, False, fl, fr)
                    self._finish(fs, fl, fr)
                    if fs.access or fs.auth_require:
                        self.ht.files.append((pat, regex, fs))
                    elif fs.has_policy():
                        self.ht.unsupported.append('<%s> without access rules' % m.group(2))
                elif tag in ('location', 'locationmatch') and top and self.include:
                    regex = tag == 'locationmatch'
                    pat = arg
                    if pat.startswith('~'):
                        regex = True
                        pat = pat[1:].strip()
                    pat = apache_unquote(pat)
                    ls = Scope()
                    ll = new_legacy()
                    lr = []
                    self._block(i + 1, end, ls, False, ll, lr)
                    self._finish(ls, ll, lr)
                    if ls.access or ls.auth_require:
                        self.ht.locations.append((pat, regex, ls))
                    elif ls.has_policy():
                        self.ht.unsupported.append('<%s> without access rules' % m.group(2))
                elif tag == 'directory' and self.include:
                    ds = Scope()
                    self._block(i + 1, end, ds, False, new_legacy(), [])
                    if ds.indexes is not None:
                        self.ht.directories.append((apache_unquote(arg).rstrip('/'), ds.indexes))
                elif tag == 'directorymatch' and self.include:
                    pass
                elif tag == 'ifdefine':
                    if arg.startswith('!'):
                        self._block(i + 1, end, scope, top, legacy, reqs)
                else:
                    self.ht.unsupported.append('<%s>' % m.group(2))
                i = end + 1
                continue
            self._directive(line, scope, top, legacy, reqs)
            i += 1
        if top and scope is self.ht.scope and a == 0:
            self._finish(scope, legacy, reqs)

    def _finish(self, scope, legacy, reqs):
        ctx = self.ht.unsupported
        env_r = ([], [])
        acc_r, auth = access_from_require(reqs, ctx, env_r) if reqs else (None, None)
        deny_env = legacy['deny_env'] + env_r[1]
        allow_env = list(env_r[0])
        deny_all = any(d.lower() == 'all' for d in legacy['deny'])
        allow_all = any(a.lower() == 'all' for a in legacy['allow'])
        legacy_deny = legacy['deny']
        if legacy['allow_env'] and deny_all and not allow_all and not legacy['allow']:
            allow_env += legacy['allow_env']
            legacy_deny = [d for d in legacy['deny'] if d.lower() != 'all']
        if deny_env or allow_env:
            scope.pre_rules.extend(env_rules(self.ht.envs, deny_env, allow_env, ctx))
        has_legacy = legacy['seen'] and (legacy_deny or legacy['allow'] or legacy['order'] and not (deny_env or allow_env))
        acc_l = access_from_legacy(legacy['order'], legacy['allow'], legacy_deny, ctx) if has_legacy else None
        if acc_r and acc_l:
            allow = [x for x in acc_r['allow'] if x in acc_l['allow'] or 'ALL' in acc_l['allow']] if 'ALL' not in acc_r['allow'] else acc_l['allow']
            deny = sorted(set(acc_r['deny']) | set(acc_l['deny']))
            scope.access = {'allow': allow, 'deny': deny}
        else:
            scope.access = acc_r or acc_l
        if auth and scope.auth_user_file and (scope.auth_type or 'basic').lower() == 'basic':
            scope.auth_require = auth
        elif auth and (scope.auth_type or '').lower() == 'digest':
            ctx.append('AuthType Digest')

    def _directive(self, line, scope, top, legacy, reqs):
        parts = line.split(None, 1)
        name = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ''
        ht = self.ht
        if name in REWRITE:
            if top:
                ht.rewrite.append(line)
        elif name in PHP_INI:
            if top:
                ht.php.append(line)
        elif name == 'order':
            legacy['order'] = rest
            legacy['seen'] = True
        elif name in ('allow', 'deny'):
            args = split_args(rest)
            if args and args[0].lower() == 'from':
                for v in args[1:]:
                    if v.lower().startswith('env='):
                        legacy[name + '_env'].append(v[4:].lstrip('!'))
                    else:
                        legacy[name].append(v)
                legacy['seen'] = True
        elif name in SETENVIF:
            args = split_args(rest)
            if name.startswith('browsermatch'):
                args = ['User-Agent'] + args
            if len(args) >= 3:
                attr = ENV_ATTRS.get(args[0].lower()) or 'HTTP:' + args[0]
                for spec in args[2:]:
                    var = spec.split('=', 1)[0]
                    if not var.startswith('!'):
                        ht.envs.setdefault(var, []).append((attr, args[1], name.endswith('nocase')))
        elif name == 'setenv' and top:
            args = split_args(rest)
            if args and re.match(r'^[A-Za-z0-9_]+$', args[0]) and (len(args) == 1 or re.match(r'^[^\s\]\[,]*$', args[1])):
                scope.pre_rules.append('RewriteRule .* - [E=%s:%s]' % (args[0], args[1] if len(args) > 1 else ''))
            else:
                ht.unsupported.append('SetEnv')
        elif name == 'addtype':
            args = split_args(rest)
            if len(args) >= 2:
                scope.mime.append(('addMIMEType', '%s %s' % (args[0], ' '.join(e.lstrip('.') for e in args[1:]))))
        elif name == 'forcetype':
            v = rest.strip().strip('"\'')
            if v and v.lower() != 'none':
                scope.mime.append(('forceType', v))
        elif name == 'adddefaultcharset':
            v = rest.strip().strip('"\'')
            if v.lower() in ('on', 'off'):
                scope.mime.append(('addDefaultCharset', v.lower()))
            elif v:
                scope.mime.append(('addDefaultCharset', 'on'))
                scope.mime.append(('defaultCharsetCustomized', v))
        elif name in ('alias', 'scriptalias') and top and self.include:
            args = split_args(rest)
            if len(args) == 2:
                ht.aliases.append((args[0], args[1], name == 'scriptalias'))
        elif name == 'require':
            args = split_args(rest)
            if not args:
                return
            neg = False
            if args[0].lower() == 'not':
                neg = True
                args = args[1:]
            if not args:
                return
            kind = args[0].lower()
            reqs.append((neg, kind, args[1:]))
        elif name == 'authtype':
            scope.auth_type = rest.strip().strip('"\'')
        elif name == 'authname':
            scope.auth_name = rest.strip().strip('"\'')
        elif name == 'authuserfile':
            scope.auth_user_file = rest.strip().strip('"\'')
        elif name == 'authgroupfile':
            scope.auth_group_file = rest.strip().strip('"\'')
        elif name in ('header', 'requestheader'):
            h = self._header(name, rest)
            if h:
                scope.headers.append(h)
        elif name == 'expiresactive':
            scope.expires_active = rest.strip().lower() == 'on'
        elif name == 'expiresdefault':
            v = seconds(rest)
            if v:
                scope.expires_default = v
        elif name == 'expiresbytype':
            args = rest.split(None, 1)
            if len(args) == 2:
                v = seconds(args[1])
                if v:
                    scope.expires_by_type[args[0].strip('"\'')] = v
        elif name == 'options':
            v = options_indexes(rest)
            if v is not None:
                scope.indexes = v
        elif name == 'directoryindex':
            files = [f for f in split_args(rest) if f.lower() not in ('disabled',)]
            if files:
                scope.index = files
        elif name == 'errordocument' and top:
            args = rest.split(None, 1)
            if len(args) == 2 and args[1].startswith('/') and args[0].isdigit():
                ht.errors[args[0]] = args[1].strip('"\'')
        elif name in ('redirect', 'redirectmatch', 'redirectpermanent', 'redirecttemp') and top:
            self._redirect(name, rest)
        elif name in IGNORED:
            pass
        elif name.startswith('ssl'):
            ht.unsupported.append(parts[0])
        else:
            ht.unsupported.append(parts[0])

    def _header(self, name, rest):
        return header_line(name, rest, self.ht.unsupported)

    def _redirect(self, name, rest):
        args = split_args(rest)
        status = '302'
        if name == 'redirectpermanent':
            status = '301'
        elif args and (args[0].isdigit() or args[0].lower() in ('permanent', 'temp', 'seeother', 'gone')):
            s = args.pop(0).lower()
            status = {'permanent': '301', 'temp': '302', 'seeother': '303', 'gone': '410'}.get(s, s)
        if not args:
            return
        src = args[0]
        dst = args[1] if len(args) > 1 else ''
        if name == 'redirectmatch':
            pat = src
        else:
            pat = '^' + re.escape(src).replace('\\/', '/') + ('(.*)$' if src.endswith('/') else '(/.*)?$')
            if dst:
                dst = dst + '$1'
        if status == '410':
            self.ht.redirects.append('RewriteRule %s - [G,L]' % pat)
        elif dst:
            if status not in ('301', '302', '303', '307', '308'):
                return
            self.ht.redirects.append('RewriteRule %s %s [R=%s,L]' % (pat, dst.replace(' ', '%20'), status))


def parse_file(path):
    text = util.read_text(path, '') or ''
    return Parser(path, text).parse()


def scan_roots(docroots):
    roots = sorted({os.path.realpath(d) for d in docroots if d and os.path.isdir(d)})
    out = []
    for r in roots:
        if not any(r.startswith(o.rstrip('/') + '/') for o in out):
            out.append(r)
    return out


def scan(docroots, limit=MAX_DIRS):
    found = []
    seen = 0
    for root in scan_roots(docroots):
        stack = [(root, 0)]
        while stack:
            d, depth = stack.pop()
            seen += 1
            if seen > limit:
                util.log('htaccess scan limit reached at %s' % d, 'WARN')
                return found
            try:
                it = os.scandir(d)
            except OSError:
                continue
            with it:
                for e in it:
                    try:
                        if e.name == '.htaccess' and e.is_file(follow_symlinks=False):
                            found.append(e.path)
                        elif depth < MAX_DEPTH and e.is_dir(follow_symlinks=False) and e.name not in SKIP_DIRS:
                            stack.append((e.path, depth + 1))
                    except OSError:
                        continue
    return sorted(found)


def save(files):
    util.write_atomic(STATE, json.dumps({'time': int(time.time()), 'files': files}), 0o600)


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'time': 0, 'files': []}


def add_files(paths):
    data = load()
    files = set(data.get('files', []))
    new = [p for p in paths if p not in files]
    if new:
        util.write_atomic(STATE, json.dumps({'time': data.get('time', 0), 'files': sorted(files | set(new))}), 0o600)
    return new


def rescan(docroots):
    t0 = time.time()
    files = scan(docroots)
    save(files)
    util.log('htaccess scan: %d files in %.1fs' % (len(files), time.time() - t0))
    return files


def merged_scope(chain):
    eff = Scope()
    for s in chain:
        if s.access is not None:
            eff.access = s.access
        if s.auth_require is not None:
            eff.auth_require = s.auth_require
            eff.auth_name = s.auth_name
            eff.auth_user_file = s.auth_user_file
            eff.auth_group_file = s.auth_group_file
        elif s.auth_type and s.auth_type.lower() == 'none':
            eff.auth_require = None
        eff.headers = eff.headers + s.headers
        if s.expires_active is not None:
            eff.expires_active = s.expires_active
        if s.expires_default:
            eff.expires_default = s.expires_default
        eff.expires_by_type = dict(eff.expires_by_type, **s.expires_by_type)
        if s.index:
            eff.index = s.index
        if s.indexes is not None:
            eff.indexes = s.indexes
        eff.mime = eff.mime + s.mime
        eff.pre_rules = eff.pre_rules + s.pre_rules
    return eff


def realm_name(userfile, groupfile):
    return 'olscp-' + hashlib.sha1(('%s|%s' % (userfile, groupfile or '')).encode()).hexdigest()[:12]


def glob_to_regex(g):
    out = ''
    for ch in g:
        if ch == '*':
            out += '[^/]*'
        elif ch == '?':
            out += '[^/]'
        else:
            out += re.escape(ch)
    return out


def files_uri_regex(prefix, pat, is_regex):
    if is_regex:
        core = pat
        lead = ''
        if core.startswith('^'):
            core = core[1:]
        else:
            lead = '[^/]*'
        tail = '' if core.endswith('$') else '[^/]*$'
        base = lead + '(?:' + core + ')' + tail
    else:
        base = '(?:' + glob_to_regex(pat) + ')$'
    return 'exp:^' + re.escape(prefix).replace('\\/', '/') + '(?:.*/)?' + base


class VhostHt(object):
    def __init__(self):
        self.contexts = []
        self.file_contexts = []
        self.realms = {}
        self.redirects = []
        self.errors = {}
        self.php_root = []
        self.report = []
        self.include_rules = 0
        self.autoindex = None
        self.vhost_rules = []
        self.vhost_headers = []
        self.aliases = []


def include_files(dirs):
    out = []
    for d in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        out.extend(os.path.join(d, n) for n in names if n.endswith('.conf'))
    return out


def location_uri(pat, is_regex):
    if is_regex:
        return 'exp:' + pat
    return pat if pat.endswith('/') else pat


def build_includes(res, include_dirs, docroot, texts=None):
    seen = set()
    root = os.path.realpath(docroot).rstrip('/')
    sources = [(p, util.read_text(p, '') or '') for p in include_files(include_dirs or [])] + list(texts or [])
    for path, text in sources:
        ht = Parser(path, text, include=True).parse()
        for d, indexes in ht.directories:
            if root == d or root.startswith(d + '/'):
                res.autoindex = indexes
        for pat, is_regex, fs in ht.files:
            uri = files_uri_regex('/', pat, is_regex)
            if uri in seen:
                continue
            seen.add(uri)
            res.file_contexts.append({'uri': uri, 'scope': fs, 'depth': 99})
        for pat, is_regex, ls in ht.locations:
            uri = location_uri(pat, is_regex)
            if uri in seen or not uri.startswith(('exp:', '/')):
                continue
            seen.add(uri)
            res.file_contexts.append({'uri': uri, 'scope': ls, 'depth': 99})
        sc = ht.scope
        res.vhost_rules.extend(sc.pre_rules)
        res.vhost_rules.extend(l for l in ht.rewrite
                               if l.split(None, 1)[0].lower() in ('rewritecond', 'rewriterule'))
        res.redirects.extend(ht.redirects)
        res.vhost_headers.extend(h for h in sc.headers if h not in res.vhost_headers)
        res.aliases.extend(ht.aliases)
        for code, url in ht.errors.items():
            res.errors.setdefault(code, url)
        unsup = sorted(set(ht.unsupported) - {'Options'})
        if sc.access or sc.auth_require or sc.expires_active or sc.expires_by_type or sc.index or sc.mime:
            unsup.append('top-level access/expires/mime directives')
        if unsup:
            res.report.append((path, unsup))
        res.include_rules += len(ht.files) + len(ht.locations) + len(ht.rewrite) + len(sc.headers)


def build(docroot, files, cache=None, include_dirs=None, include_texts=None):
    cache = cache if cache is not None else {}
    res = VhostHt()
    if include_dirs or include_texts:
        build_includes(res, include_dirs, docroot, include_texts)
    root = os.path.realpath(docroot).rstrip('/')
    mine = sorted(f for f in files if f == root + '/.htaccess' or f.startswith(root + '/'))
    parsed = {}
    for f in mine:
        try:
            st = os.stat(f)
        except OSError:
            continue
        key = (f, st.st_mtime_ns, st.st_size)
        if key not in cache:
            cache[key] = parse_file(f)
        parsed[os.path.dirname(f)] = cache[key]
    if not parsed:
        return res
    for d, ht in parsed.items():
        if ht.unsupported:
            res.report.append((ht.path, sorted(set(ht.unsupported))))
    root_ht = parsed.get(root)
    if root_ht:
        res.errors = dict(root_ht.errors)
        res.php_root = list(root_ht.php)
    for d in sorted(parsed):
        res.redirects.extend(parsed[d].redirects)

    def chain(d):
        out = []
        cur = d
        while True:
            if cur in parsed:
                out.append(parsed[cur])
            if cur == root or len(cur) <= len(root):
                break
            cur = os.path.dirname(cur)
        return list(reversed(out))

    def uri_of(d):
        return '/' if d == root else '/' + os.path.relpath(d, root).replace(os.sep, '/') + '/'

    policy_dirs = {d for d, ht in parsed.items() if ht.scope.has_policy()}
    need = set()
    for d in parsed:
        if any(p == d or d.startswith(p + '/') for p in policy_dirs):
            need.add(d)
    for d in sorted(need):
        ch = chain(d)
        eff = merged_scope([h.scope for h in ch])
        ht = parsed[d]
        ctx = {'uri': uri_of(d), 'location': d + '/', 'scope': eff, 'rewrite': list(ht.rewrite), 'php': list(ht.php),
               'mime': list(eff.mime), 'pre_rules': list(eff.pre_rules)}
        if eff.auth_require:
            rn = realm_name(eff.auth_user_file, eff.auth_group_file)
            res.realms[rn] = (eff.auth_user_file, eff.auth_group_file)
            ctx['realm'] = rn
        res.contexts.append(ctx)
    for d in sorted(parsed):
        ht = parsed[d]
        uri = uri_of(d)
        for pat, is_regex, fs in ht.files:
            fctx = {'uri': files_uri_regex(uri, pat, is_regex), 'scope': fs, 'depth': uri.count('/')}
            if fs.auth_require and fs.auth_user_file:
                rn = realm_name(fs.auth_user_file, fs.auth_group_file)
                res.realms[rn] = (fs.auth_user_file, fs.auth_group_file)
                fctx['realm'] = rn
            res.file_contexts.append(fctx)
    res.file_contexts.sort(key=lambda c: -c['depth'])
    return res
