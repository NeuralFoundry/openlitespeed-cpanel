import glob
import re

from . import util

PAIR = re.compile(r'([A-Z_]+): ([0-9.]+)')


def _num(v):
    try:
        return float(v) if '.' in v else int(v)
    except ValueError:
        return 0


def _add(d, line):
    for k, v in PAIR.findall(line):
        d[k] = d.get(k, 0) + _num(v)


def read():
    server = {}
    vhosts = {}
    apps = {}
    blocked = set()
    uptime = ''
    version = ''
    files = sorted(glob.glob('/tmp/lshttpd/.rtreport*'))
    for f in files:
        for line in (util.read_text(f, '') or '').splitlines():
            if line.startswith('VERSION:'):
                version = line.split(':', 1)[1].strip()
            elif line.startswith('UPTIME:'):
                uptime = uptime or line.split(':', 1)[1].strip()
            elif line.startswith(('BPS_IN', 'MAXCONN')):
                _add(server, line)
            elif line.startswith('REQ_RATE ['):
                name = line[len('REQ_RATE ['):line.index(']')]
                if name == '':
                    _add(server, line)
                elif name != '_AdminVHost':
                    _add(vhosts.setdefault(name, {}), line)
            elif line.startswith('EXTAPP '):
                parts = re.findall(r'\[([^\]]*)\]', line)
                if len(parts) >= 3:
                    _add(apps.setdefault(parts[2], {'type': parts[0], 'vhost': parts[1]}), line)
            elif line.startswith('BLOCKED_IP:'):
                blocked.update(x.strip() for x in line.split(':', 1)[1].split(',') if x.strip())
    for k in ('MAXCONN', 'MAXSSL_CONN', 'AVAILCONN', 'AVAILSSL'):
        if k in server and files:
            server[k] = server[k] // len(files) if isinstance(server[k], int) else server[k]
    top = sorted(({'name': k, **v} for k, v in vhosts.items()), key=lambda r: (-r.get('REQ_PER_SEC', 0), -r.get('TOT_REQS', 0)))
    return {'version': version, 'uptime': uptime, 'workers': len(files), 'server': server,
            'vhosts': top, 'apps': [{'name': k, **v} for k, v in sorted(apps.items())], 'blocked': sorted(blocked)}
