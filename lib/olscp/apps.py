import glob
import os
import pwd
import re
import signal

from . import const, util

LSWSGI = const.BASE + '/libexec/lswsgi.py'
STARTERS = const.OLS_ROOT + '/fcgi-bin'
STARTUP = {'node': 'app.js', 'wsgi': 'passenger_wsgi.py', 'rack': 'config.ru'}
ENV_MODES = {'development': 0, 'production': 1, 'staging': 2}
KEYS = {
    'passengerapproot': 'root', 'passengerbaseuri': 'uri', 'passengerapptype': 'type',
    'passengerstartupfile': 'startup', 'passengernodejs': 'node', 'passengerpython': 'python',
    'passengerruby': 'ruby', 'passengerappenv': 'mode', 'railsenv': 'mode', 'rackenv': 'mode',
    'passengerenabled': 'enabled', 'passengerapplogfile': 'log',
}
RESERVED_ENV = {'LSNODE_ROOT', 'LSNODE_SOCKET', 'LSNODE_STARTUP_FILE', 'LSNODE_BIND_SOCKET', 'LS_STDERR_LOG'}
APP_KEYS = ('root', 'uri', 'type', 'startup', 'node', 'python', 'ruby')
TYPES = {'node': 'node', 'nodejs': 'node', 'wsgi': 'wsgi', 'python': 'wsgi', 'rack': 'rack', 'ruby': 'rack',
         'rails': 'rack'}
BINARY_KEY = {'node': 'node', 'wsgi': 'python', 'rack': 'ruby'}
LABEL = {'node': 'Node.js', 'wsgi': 'Python', 'rack': 'Ruby'}
SAFE_PATH = re.compile(r'^/[A-Za-z0-9._@+=,~/-]*$')
SAFE_URI = re.compile(r'^/(?:[A-Za-z0-9._~@+=,-]+/)*$')
SAFE_FILE = re.compile(r'^[A-Za-z0-9._@+=,~-]+(?:/[A-Za-z0-9._@+=,~-]+)*$')
ENV_NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
NODE_MAX_CONNS = 100
WSGI_MAX_CONNS = 10


def is_directive(name):
    return name in KEYS or name.startswith('passenger')


def norm_uri(u):
    u = re.sub(r'/+', '/', '/' + (u or '').strip().strip('/'))
    return u if u.endswith('/') else u + '/'


def clean_value(v):
    if len(v) > 4096 or v.rstrip().endswith('{') or v.strip() == '}':
        return False
    return not any(ord(c) < 32 or ord(c) == 127 for c in v)


class Spec(object):
    def __init__(self, source, uri, directory=None, nested=False):
        self.source = source
        self.uri = norm_uri(uri)
        self.directory = directory
        self.nested = nested
        self.values = {}
        self.env = []

    def add(self, name, args):
        key = KEYS.get(name)
        if key and args:
            self.values[key] = args[0]

    def set_env(self, name, value):
        self.env = [(n, v) for n, v in self.env if n != name] + [(name, value)]

    def mounted(self):
        base = self.values.get('uri')
        return not (self.nested and base and norm_uri(base) != self.uri)

    def is_app(self):
        if (self.values.get('enabled') or 'on').lower() == 'off':
            return False
        return any(k in self.values for k in APP_KEYS)


def version_key(path):
    m = re.search(r'(\d+)', path)
    return int(m.group(1)) if m else 0


def find_binary(kind):
    if kind == 'node':
        found = sorted(glob.glob('/opt/cpanel/ea-nodejs*/bin/node'), key=version_key, reverse=True)
        found += ['/usr/local/bin/node', '/usr/bin/node']
    elif kind == 'python':
        found = ['/usr/bin/python3', '/usr/local/bin/python3']
    else:
        found = ['/usr/bin/ruby', '/usr/local/bin/ruby']
    for p in found:
        if usable(p):
            return p
    return ''


def usable(path):
    return bool(path) and bool(SAFE_PATH.match(path)) and os.path.isfile(path) and os.access(path, os.X_OK)


def inside(path, base):
    base = base.rstrip('/')
    return bool(base) and path.startswith(base + '/')


def detect_type(v, root):
    raw = (v.get('type') or '').lower()
    if raw:
        return TYPES.get(raw), raw
    for key, kind in (('node', 'node'), ('python', 'wsgi'), ('ruby', 'rack')):
        if key in v:
            return kind, ''
    for kind, name in (('rack', 'config.ru'), ('wsgi', 'passenger_wsgi.py'), ('node', 'app.js'), ('node', 'package.json')):
        if os.path.isfile(os.path.join(root, name)):
            return kind, ''
    return None, ''


def resolve(spec, home, defaults=None):
    defaults = defaults or {}
    v = spec.values
    if not spec.is_app():
        return None, None
    if not spec.mounted():
        return None, None
    base = v.get('uri')
    uri = norm_uri(base) if base else spec.uri
    where = '%s (%s)' % (uri, spec.source)
    if not SAFE_URI.match(uri):
        return None, '%s: unsupported characters in the base URI' % where
    root = v.get('root') or ''
    if not root.startswith('/'):
        return None, '%s: PassengerAppRoot must be an absolute path' % where
    real = os.path.realpath(root)
    home_real = os.path.realpath(home) if home else ''
    if not inside(real, home_real):
        return None, '%s: application root %s is outside the home directory' % (where, root)
    if not SAFE_PATH.match(real):
        return None, '%s: unsupported characters in the application root' % where
    if not os.path.isdir(real):
        return None, '%s: application root %s does not exist' % (where, root)
    kind, raw = detect_type(v, real)
    if raw and not kind:
        return None, '%s: application type %s is not supported' % (where, raw)
    if not kind:
        return None, '%s: application type could not be detected, set PassengerAppType' % where
    if kind == 'rack':
        return None, '%s: Ruby applications are not supported yet' % where
    startup = v.get('startup') or STARTUP[kind]
    if startup.startswith('/'):
        if not inside(os.path.realpath(startup), real):
            return None, '%s: startup file must be inside the application root' % where
        startup = os.path.relpath(os.path.realpath(startup), real)
    if not SAFE_FILE.match(startup) or '..' in startup.split('/'):
        return None, '%s: unsupported startup file name %s' % (where, startup)
    full = os.path.realpath(os.path.join(real, startup))
    if not inside(full, real) or not os.path.isfile(full):
        return None, '%s: startup file %s not found in %s' % (where, startup, real)
    if kind == 'wsgi':
        starter = LSWSGI
    else:
        starter = os.path.join(STARTERS, 'lsnodesm.js' if startup.endswith('.mjs') else 'lsnode.js')
    if not os.path.isfile(starter):
        return None, '%s: %s is missing' % (where, starter)
    key = BINARY_KEY[kind]
    wanted = v.get(key) or defaults.get(key) or ''
    binary = wanted if usable(wanted) else find_binary(key)
    if not binary:
        return None, '%s: no usable %s binary%s' % (where, LABEL[kind], ' (%s)' % wanted if wanted else '')
    note = '%s not found, using %s' % (wanted, binary) if wanted and binary != wanted else ''
    mode = (v.get('mode') or defaults.get('mode') or 'production').lower()
    if not re.match(r'^[a-z0-9_-]{1,32}$', mode):
        mode = 'production'
    env = []
    for name, value in spec.env:
        if ENV_NAME.match(name) and clean_value(value) and name not in RESERVED_ENV and not name.startswith('OLSCP_'):
            env.append('%s=%s' % (name, value))
    env.append('PASSENGER_APP_ENV=%s' % mode)
    env.append('LS_STDERR_LOG=%s' % log_file(v.get('log'), real, home_real))
    if kind == 'wsgi':
        env.append('OLSCP_APP_URI=%s' % uri)
    return {
        'uri': uri, 'root': real + '/', 'type': kind, 'startup': startup, 'binary': binary, 'mode': mode,
        'env_mode': ENV_MODES.get(mode, 1), 'env': env, 'source': spec.source,
        'directory': spec.directory or '', 'note': note,
    }, None


def log_file(wanted, root, home):
    if wanted and wanted.startswith('/'):
        path = os.path.join(os.path.realpath(os.path.dirname(wanted)), os.path.basename(wanted))
        if SAFE_PATH.match(path) and inside(path, home) and os.path.isdir(os.path.dirname(path)):
            return path
    return root + '/stderr.log'


def resolve_all(specs, home, defaults=None):
    apps, issues, seen = [], [], set()
    off = str((defaults or {}).get('disable_htaccess', '')).lower() == 'on'
    for spec in specs:
        if off and spec.directory and spec.is_app() and spec.mounted():
            issues.append('%s: Passenger directives in .htaccess are disabled by PassengerDisableHtaccess' % spec.source)
            continue
        try:
            app, issue = resolve(spec, home, defaults)
        except (OSError, ValueError) as e:
            app, issue = None, '%s: %s' % (spec.source, e)
        if issue:
            issues.append(issue)
        if app and app['uri'] not in seen:
            seen.add(app['uri'])
            apps.append(app)
    return apps, issues


def static_dirs(app, docroot):
    top = os.path.realpath(docroot)
    d = os.path.realpath(os.path.join(docroot, app['uri'].lstrip('/')))
    root = app['root'].rstrip('/')
    if d != top and not inside(d, top):
        return []
    if not os.path.isdir(d) or d == root or inside(d, root) or inside(root, d):
        return []
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    for n in names:
        p = os.path.join(d, n)
        if n.startswith('.') or not SAFE_FILE.match(n) or os.path.islink(p) or not os.path.isdir(p):
            continue
        out.append((app['uri'] + n + '/', p + '/'))
    return out


def context(c, app):
    c.kv('type', 'appserver')
    c.kv('location', app['root'])
    if app['type'] == 'wsgi':
        c.kv('binPath', '%s %s' % (app['binary'], LSWSGI))
        c.kv('maxConns', WSGI_MAX_CONNS)
    else:
        c.kv('binPath', app['binary'])
        c.kv('maxConns', NODE_MAX_CONNS)
    c.kv('appType', 'node')
    c.kv('startupFile', app['startup'])
    c.kv('appserverEnv', app['env_mode'])
    for e in app['env']:
        c.kv('env', e)
    return c


def processes():
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open('/proc/%s/environ' % pid, 'rb') as f:
                env = f.read()
            uid = os.stat('/proc/%s' % pid).st_uid
        except OSError:
            continue
        m = re.search(rb'(?:^|\0)LSNODE_ROOT=([^\0]*)', env)
        if m:
            yield int(pid), uid, os.path.realpath(m.group(1).decode('utf-8', 'replace')).rstrip('/')


def running(apps):
    counts = {a['root'].rstrip('/'): 0 for a in apps}
    for _pid, _uid, root in processes():
        if root in counts:
            counts[root] += 1
    return counts


def stop(app):
    uid = pwd.getpwnam(app['user']).pw_uid
    root = app['root'].rstrip('/')
    found = [pid for pid, owner, r in processes() if owner == uid and r == root and pid != os.getpid()]
    for pid in found:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    return len(found)


def restart(app):
    tmp = os.path.join(app['root'], 'tmp')
    rc, out = util.run(['/usr/sbin/runuser', '-u', app['user'], '--', '/bin/sh', '-c', 'mkdir -p "$1" && touch "$1/restart.txt"',
                        'sh', tmp], timeout=30)
    if rc != 0:
        raise RuntimeError('restart of %s%s failed: %s' % (app['vhost'], app['uri'], out.strip()[:200]))
    stop(app)
    return app['vhost'] + app['uri']
