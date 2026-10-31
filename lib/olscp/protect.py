import collections
import ipaddress
import json
import os
import re
import time

from . import const, cpanel, util

BLOCKED = const.STATE + '/blocked.json'
LINE = re.compile(r'^(\S+) \S+ \S+ \[[^\]]*\] "(\S+) (\S+)[^"]*" \d+ \S+ "[^"]*" "([^"]*)"')
WP_PATH = re.compile(r'/(wp-login|xmlrpc)\.php(?:\?|$)')
MAX_READ = 4 * 1048576
WINDOW = 60


def load_blocked():
    try:
        with open(BLOCKED) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    now = time.time()
    return {ip: v for ip, v in data.items() if v.get('until', 0) > now}


def save_blocked(data):
    util.write_atomic(BLOCKED, json.dumps(data, indent=1, sort_keys=True), 0o600)


def unblock(ips=None):
    data = load_blocked()
    if ips is None:
        data = {}
    else:
        for ip in ips:
            data.pop(ip, None)
    save_blocked(data)
    return data


def safe_networks(settings):
    nets = []
    st = cpanel.load_state()
    for x in ['127.0.0.0/8', '::1/128', st.main_ip] + st.trusted_proxies + st.ipv6_addrs + \
            [s.strip() for s in (settings.get('protect_whitelist') or '').split(',') if s.strip()]:
        try:
            nets.append(ipaddress.ip_network(x, strict=False))
        except ValueError:
            continue
    return nets


def enabled(settings):
    return settings.get('wp_protect', 'off') == 'block' or int(settings.get('bot_throttle') or 0) > 0


class Protector(object):
    def __init__(self):
        self.offsets = {}
        self.hits = collections.defaultdict(collections.deque)
        self.safe = []
        self.safe_time = 0

    def _is_safe(self, ip, settings):
        if time.time() - self.safe_time > 300:
            self.safe = safe_networks(settings)
            self.safe_time = time.time()
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return True
        return any(addr in n for n in self.safe)

    def _lines(self, path, size):
        off = self.offsets.get(path)
        self.offsets[path] = size
        if off is None or size == off:
            return []
        if size < off:
            off = 0
        try:
            with open(path, 'rb') as f:
                f.seek(max(off, size - MAX_READ))
                data = f.read(size - max(off, size - MAX_READ))
        except OSError:
            return []
        return data.decode('utf-8', 'replace').splitlines()

    def scan(self, settings):
        if not enabled(settings):
            self.offsets.clear()
            self.hits.clear()
            return []
        wp = settings.get('wp_protect', 'off') == 'block'
        wp_limit = int(settings.get('wp_protect_limit') or 20)
        xmlrpc = settings.get('wp_protect_xmlrpc', True)
        bot_limit = int(settings.get('bot_throttle') or 0)
        agents = settings.get('bot_agents') or ''
        try:
            bot_re = re.compile(agents, re.I) if bot_limit and agents else None
        except re.error:
            bot_re = None
        now = time.time()
        try:
            entries = list(os.scandir(const.DOMLOGS))
        except OSError:
            return []
        for e in entries:
            if not e.is_file(follow_symlinks=False) or e.name.endswith(('-bytes_log', '.offset', '.bkup')):
                continue
            try:
                size = e.stat().st_size
            except OSError:
                continue
            for line in self._lines(e.path, size):
                m = LINE.match(line)
                if not m:
                    continue
                ip, method, path, ua = m.groups()
                if wp and method == 'POST':
                    w = WP_PATH.search(path)
                    if w and (xmlrpc or w.group(1) == 'wp-login'):
                        self.hits[(ip, 'wp')].append(now)
                if bot_re and bot_re.search(ua):
                    self.hits[(ip, 'bot')].append(now)
        blocked = load_blocked()
        new = []
        ban = int(settings.get('protect_ban_minutes') or 15) * 60
        for (ip, kind), dq in list(self.hits.items()):
            while dq and dq[0] < now - WINDOW:
                dq.popleft()
            if not dq:
                del self.hits[(ip, kind)]
                continue
            limit = wp_limit if kind == 'wp' else bot_limit
            if len(dq) > limit and ip not in blocked and not self._is_safe(ip, settings):
                blocked[ip] = {'since': int(now), 'until': int(now + ban), 'reason': kind, 'hits': len(dq)}
                new.append(ip)
                dq.clear()
        if new:
            save_blocked(blocked)
            util.log('protect: blocked %s' % ', '.join('%s(%s)' % (ip, blocked[ip]['reason']) for ip in new))
        return new
