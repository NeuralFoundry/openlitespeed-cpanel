import ctypes
import ctypes.util
import errno
import glob
import grp
import os
import select
import signal
import socket
import struct
import time

from . import const, cpanel, htaccess, olsbuild, protect, server, sync, util

IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
IN_ONLYDIR = 0x01000000
IN_ISDIR = 0x40000000
MASK = (IN_CLOSE_WRITE | IN_MOVED_TO | IN_MOVED_FROM | IN_CREATE | IN_DELETE | IN_ATTRIB
        | IN_DELETE_SELF | IN_MOVE_SELF | IN_ONLYDIR)
EVENT = struct.Struct('iIII')

QUIET = 2.0
MAX_WAIT = 15.0
MIN_RESTART_GAP = 5.0
FULL_SYNC_EVERY = 600

_libc = ctypes.CDLL(ctypes.util.find_library('c') or 'libc.so.6', use_errno=True)


class Inotify(object):
    def __init__(self):
        self.fd = _libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'inotify_init1')
        self.wd = {}
        self.paths = {}

    def add(self, path, kind):
        if path in self.paths:
            return True
        wd = _libc.inotify_add_watch(self.fd, path.encode(), MASK)
        if wd < 0:
            e = ctypes.get_errno()
            if e == errno.ENOSPC:
                util.log('inotify watch limit reached at %s' % path, 'WARN')
            return False
        self.wd[wd] = (path, kind)
        self.paths[path] = wd
        return True

    def remove_missing(self):
        for path, wd in list(self.paths.items()):
            if not os.path.isdir(path):
                _libc.inotify_rm_watch(self.fd, wd)
                self.paths.pop(path, None)
                self.wd.pop(wd, None)

    def read(self):
        events = []
        try:
            data = os.read(self.fd, 65536)
        except BlockingIOError:
            return events
        i = 0
        while i + EVENT.size <= len(data):
            wd, mask, _cookie, size = EVENT.unpack_from(data, i)
            name = data[i + EVENT.size:i + EVENT.size + size].split(b'\0', 1)[0].decode('utf-8', 'replace')
            i += EVENT.size + size
            if mask & IN_IGNORED:
                info = self.wd.pop(wd, None)
                if info:
                    self.paths.pop(info[0], None)
                continue
            path, kind = self.wd.get(wd, ('', ''))
            events.append((path, kind, name, mask))
        return events


def config_dirs():
    dirs = ['/etc/apache2/conf', '/etc/apache2/conf.d', '/etc/apache2/conf.d/includes', const.USERDATA,
            const.SSL_DIR, const.SUSPENDED, '/etc/cpanel/ea4', const.CPANEL_USERS]
    dirs += [d for d in glob.glob(const.USERDATA + '/*') if os.path.isdir(d)]
    dirs += [d for d in glob.glob(const.SSL_DIR + '/*') if os.path.isdir(d)]
    dirs += glob.glob(const.EA_PHP_ROOT + '/ea-php*/root/etc/php-fpm.d')
    return dirs


def open_notify():
    path = const.HT_NOTIFY
    try:
        os.unlink(path)
    except OSError:
        pass
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.bind(path)
    try:
        gid = grp.getgrnam('nobody').gr_gid
    except KeyError:
        gid = 99
    os.chown(path, 0, gid)
    os.chmod(path, 0o660)
    s.setblocking(False)
    return s


def docroot_dirs():
    try:
        st = cpanel.load_state()
    except Exception as e:
        util.log('watch: state load failed: %s' % e, 'WARN')
        return [], []
    roots = sorted({vh.docroot for vh in st.vhosts if vh.docroot and os.path.isdir(vh.docroot)})
    homes = sorted({vh.homedir for vh in st.vhosts if vh.homedir})
    ht = sorted({os.path.dirname(f) for f in htaccess.load().get('files', [])})
    pw = []
    for h in homes:
        base = os.path.join(h, '.htpasswds')
        if os.path.isdir(base):
            for dp, dn, _fn in os.walk(base):
                pw.append(dp)
                if len(pw) > 5000:
                    break
    return sorted(set(roots) | set(ht)), pw + [h for h in homes if os.path.isdir(h)]


class Watcher(object):
    def __init__(self):
        self.ino = Inotify()
        self.stop = False
        self.pending_conf = 0.0
        self.pending_ht = 0.0
        self.pending_scan = 0.0
        self.first = 0.0
        self.last_restart = 0.0
        self.last_full = 0.0
        self.last_scan = 0.0
        self.settings = util.load_settings()
        self.protector = protect.Protector()
        self.last_protect = 0.0
        self.last_settings = 0.0
        self.last_blocked = set(protect.load_blocked())
        self.known = set()
        self.roots = []
        self.notify = None

    def notified(self, data):
        path = data.decode('utf-8', 'replace').strip()
        if not path.endswith('/.htaccess') or path in self.known or '\0' in path:
            return
        real = os.path.realpath(path)
        if not any(real == r + '/.htaccess' or real.startswith(r + '/') for r in self.roots):
            return
        if not os.path.isfile(real):
            return
        self.known.add(path)
        if htaccess.add_files([real]):
            self.ino.add(os.path.dirname(real), 'ht')
            now = time.time()
            if not self.first:
                self.first = now
            self.pending_ht = now

    def read_notify(self):
        for _ in range(1000):
            try:
                data = self.notify.recv(4096)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            self.notified(data)

    def protect_tick(self):
        now = time.time()
        if now - self.last_settings > 10:
            self.settings = util.load_settings()
            self.last_settings = now
        if now - self.last_protect < 2:
            return
        self.last_protect = now
        try:
            new = self.protector.scan(self.settings)
            cur = set(protect.load_blocked())
            if new or cur != self.last_blocked:
                self.last_blocked = cur
                if not self.first:
                    self.first = now
                self.pending_conf = now
        except Exception as e:
            util.log('protect scan failed: %s' % e, 'ERROR')

    def rescan(self):
        self.ino.remove_missing()
        for d in config_dirs():
            if os.path.isdir(d):
                self.ino.add(d, 'conf')
        if self.settings.get('htaccess_watch', True):
            ht_dirs, pw_dirs = docroot_dirs()
            for d in ht_dirs:
                self.ino.add(d, 'ht')
            for d in pw_dirs:
                self.ino.add(d, 'pw')
        self.known = set(htaccess.load().get('files', []))
        try:
            self.roots = sorted({os.path.realpath(vh.docroot).rstrip('/') for vh in cpanel.load_state().vhosts if vh.docroot})
        except Exception:
            pass

    def classify(self, path, kind, name, mask):
        if mask & IN_Q_OVERFLOW:
            return 'conf'
        if kind == 'ht':
            return 'ht' if name == '.htaccess' else None
        if kind == 'pw':
            if name == '.htpasswds' or path.endswith('/.htpasswds') or '/.htpasswds/' in path + '/':
                return 'scan'
            return None
        if path == '/etc/apache2/conf' and name not in ('httpd.conf',):
            return None
        if path.startswith('/etc/apache2/conf.d') and not name.endswith('.conf'):
            return None
        if name.startswith('.') and not name.startswith('.pending'):
            return None
        return 'conf'

    def handle(self):
        now = time.time()
        if not (self.pending_conf or self.pending_ht or self.pending_scan):
            return
        last = max(self.pending_conf, self.pending_ht, self.pending_scan)
        if now - last < QUIET and now - self.first < MAX_WAIT:
            return
        if now - self.last_restart < MIN_RESTART_GAP:
            return
        conf, ht, scan = self.pending_conf, self.pending_ht, self.pending_scan
        self.pending_conf = self.pending_ht = self.pending_scan = self.first = 0.0
        try:
            self.settings = util.load_settings()
            if scan:
                res, _n = sync.rescan_htaccess(restart=True, reason='watch-scan')
                self.last_scan = time.time()
            else:
                res = sync.sync(restart=True, reason='watch-htaccess' if ht and not conf else 'watch',
                                force_restart=bool(ht) and not olsbuild.live())
            if res.get('restarted'):
                self.last_restart = time.time()
            self.last_full = time.time()
            self.rescan()
        except Exception as e:
            util.log('watch action failed: %s' % e, 'ERROR')

    def run(self):
        signal.signal(signal.SIGTERM, self._term)
        signal.signal(signal.SIGINT, self._term)
        const.ensure_dirs()
        try:
            sync.rescan_htaccess(restart=True, reason='watch-start')
        except Exception as e:
            util.log('initial sync failed: %s' % e, 'ERROR')
        self.rescan()
        util.log('watcher started with %d watches' % len(self.ino.paths))
        self.last_full = self.last_scan = time.time()
        poll = select.poll()
        poll.register(self.ino.fd, select.POLLIN)
        try:
            self.notify = open_notify()
            poll.register(self.notify.fileno(), select.POLLIN)
        except OSError as e:
            util.log('htaccess notify socket unavailable: %s' % e, 'WARN')
        while not self.stop:
            for fd, _ev in poll.poll(500):
                if self.notify is not None and fd == self.notify.fileno():
                    self.read_notify()
                    continue
                for path, kind, name, mask in self.ino.read():
                    c = self.classify(path, kind, name, mask)
                    if not c:
                        continue
                    now = time.time()
                    if not self.first:
                        self.first = now
                    if c == 'conf':
                        self.pending_conf = now
                    elif c == 'scan':
                        self.pending_scan = now
                    else:
                        self.pending_ht = now
                    if mask & IN_ISDIR and mask & (IN_CREATE | IN_MOVED_TO) and kind in ('conf', 'pw'):
                        self.ino.add(os.path.join(path, name), kind)
            self.protect_tick()
            self.handle()
            interval = int(self.settings.get('htaccess_scan_interval') or 900)
            if not self.first and time.time() - self.last_scan > interval:
                try:
                    sync.rescan_htaccess(restart=True, reason='periodic-scan')
                    self.rescan()
                except Exception as e:
                    util.log('periodic scan failed: %s' % e, 'ERROR')
                self.last_scan = self.last_full = time.time()
            elif not self.first and time.time() - self.last_full > FULL_SYNC_EVERY:
                try:
                    sync.sync(restart=True, reason='periodic')
                    self.rescan()
                except Exception as e:
                    util.log('periodic sync failed: %s' % e, 'ERROR')
                self.last_full = time.time()
        util.log('watcher stopped')

    def _term(self, *a):
        self.stop = True


def main():
    Watcher().run()
