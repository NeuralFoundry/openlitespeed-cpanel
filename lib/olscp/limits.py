import hashlib
import json
import os
import pwd

from . import const, util

FILE = const.ETC + '/limits.json'
APPLIED = const.STATE + '/limits-applied.json'
KEYS = ('cpu', 'mem', 'tasks', 'io')
CG = '/sys/fs/cgroup/user.slice'


def available():
    return os.path.exists('/sys/fs/cgroup/cgroup.controllers')


def load():
    try:
        with open(FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {'default': data.get('default') or {}, 'packages': data.get('packages') or {}, 'users': data.get('users') or {}}


def save(data):
    util.write_atomic(FILE, json.dumps(data, indent=2, sort_keys=True), 0o600)


def clean(values):
    out = {}
    for k in KEYS:
        v = values.get(k)
        if v in (None, ''):
            continue
        v = int(v)
        if v < 0:
            raise ValueError('negative limit: %s' % k)
        out[k] = v
    return out


def set_limits(scope, name, values):
    data = load()
    vals = clean(values)
    if scope == 'default':
        data['default'] = vals
    elif scope in ('package', 'user'):
        key = 'packages' if scope == 'package' else 'users'
        if not name:
            raise ValueError('name required')
        if vals:
            data[key][name] = vals
        else:
            data[key].pop(name, None)
    else:
        raise ValueError('bad scope')
    save(data)
    return data


def accounts():
    out = []
    try:
        names = sorted(os.listdir(const.CPANEL_USERS))
    except OSError:
        return out
    for u in names:
        if u.startswith('.') or u in ('system', 'nobody', 'root'):
            continue
        kv = util.parse_kv(os.path.join(const.CPANEL_USERS, u))
        try:
            pw = pwd.getpwnam(u)
        except KeyError:
            continue
        out.append({'user': u, 'uid': pw.pw_uid, 'home': pw.pw_dir, 'plan': kv.get('PLAN', ''),
                    'suspended': os.path.exists(os.path.join(const.SUSPENDED, u))})
    return out


def effective(data, user, plan):
    eff = dict(data['default'])
    eff.update(data['packages'].get(plan, {}))
    eff.update(data['users'].get(user, {}))
    return {k: v for k, v in eff.items() if v}


def props(lim, home):
    p = []
    p.append('CPUQuota=%d%%' % lim['cpu'] if lim.get('cpu') else 'CPUQuota=')
    p.append('MemoryMax=%dM' % lim['mem'] if lim.get('mem') else 'MemoryMax=infinity')
    p.append('TasksMax=%d' % lim['tasks'] if lim.get('tasks') else 'TasksMax=infinity')
    if lim.get('io'):
        p.append('IOReadBandwidthMax=%s %dM' % (home, lim['io']))
        p.append('IOWriteBandwidthMax=%s %dM' % (home, lim['io']))
    else:
        p.append('IOReadBandwidthMax=')
        p.append('IOWriteBandwidthMax=')
    return p


def _applied():
    try:
        with open(APPLIED) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def apply(enabled=True, force=False):
    if not available():
        return {'applied': 0, 'error': 'cgroups v2 not available'}
    data = load()
    done = _applied()
    if enabled:
        util.run(['/usr/bin/systemctl', 'set-property', 'user.slice', 'CPUAccounting=yes', 'MemoryAccounting=yes',
                  'TasksAccounting=yes', 'IOAccounting=yes'], timeout=60)
    n = 0
    errors = []
    for acc in accounts():
        lim = effective(data, acc['user'], acc['plan']) if enabled else {}
        sig = hashlib.sha1(json.dumps([lim, acc['home']], sort_keys=True).encode()).hexdigest()
        key = str(acc['uid'])
        if not force and done.get(key) == sig:
            continue
        if not lim and key not in done:
            done[key] = sig
            continue
        rc, out = util.run(['/usr/bin/systemctl', 'set-property', 'user-%d.slice' % acc['uid']] + props(lim, acc['home']), timeout=60)
        if rc == 0:
            done[key] = sig
            n += 1
        else:
            errors.append('%s: %s' % (acc['user'], out.strip()[-200:]))
    util.write_atomic(APPLIED, json.dumps(done), 0o600)
    if n:
        util.log('cgroups limits applied to %d users' % n)
    return {'applied': n, 'errors': errors}


def _read(path):
    v = (util.read_text(path, '') or '').strip()
    return v


def usage(uid):
    base = os.path.join(CG, 'user-%d.slice' % uid)
    if not os.path.isdir(base):
        return {}
    out = {}
    mem = _read(os.path.join(base, 'memory.current'))
    if mem.isdigit():
        out['mem'] = int(mem) // 1048576
    pids = _read(os.path.join(base, 'pids.current'))
    if pids.isdigit():
        out['tasks'] = int(pids)
    for line in _read(os.path.join(base, 'cpu.stat')).splitlines():
        if line.startswith('usage_usec'):
            out['cpu_seconds'] = int(line.split()[1]) // 1000000
    return out


def status():
    data = load()
    rows = []
    for acc in accounts():
        rows.append(dict(acc, limits=effective(data, acc['user'], acc['plan']),
                         own=data['users'].get(acc['user'], {}), usage=usage(acc['uid'])))
    plans = sorted({a['plan'] for a in rows if a['plan']} | set(data['packages']))
    return {'available': available(), 'config': data, 'users': rows, 'plans': plans}
