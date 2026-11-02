import json
import os
import pwd
import re
import shutil
import subprocess
import time

from . import const, cpanel, util

DATA = const.STATE + '/wp.json'
JOB = const.STATE + '/wpjob.json'
PLUGIN = 'litespeed-cache'
SKIP = {'wp-content', 'wp-includes', 'wp-admin', 'node_modules', '.git', 'cgi-bin', '.well-known', 'vendor'}
MAX_DEPTH = 3


def load():
    try:
        with open(DATA) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'time': 0, 'sites': {}}


def save(data):
    util.write_atomic(DATA, json.dumps(data, indent=1, sort_keys=True), 0o600)


def wp_version(path):
    text = util.read_user_file(os.path.join(path, 'wp-includes/version.php'), 1 << 20, canonical=False)
    m = re.search(r"\$wp_version\s*=\s*'([^']+)'", text)
    return m.group(1) if m else ''


def find_in(docroot):
    found = []
    stack = [(docroot, 0)]
    while stack:
        d, depth = stack.pop()
        if os.path.isfile(os.path.join(d, 'wp-config.php')) or os.path.isfile(os.path.join(os.path.dirname(d), 'wp-config.php')) and d == docroot:
            if os.path.isfile(os.path.join(d, 'wp-includes/version.php')):
                found.append(d)
                continue
        if depth >= MAX_DEPTH:
            continue
        try:
            it = os.scandir(d)
        except OSError:
            continue
        with it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False) and e.name not in SKIP and not e.name.startswith('.'):
                        stack.append((e.path, depth + 1))
                except OSError:
                    continue
    return found


def owner_vhost(path, vhosts):
    best = None
    for vh in vhosts:
        root = vh.docroot.rstrip('/')
        if path == root or path.startswith(root + '/'):
            if best is None or len(root) > len(best.docroot.rstrip('/')):
                best = vh
    return best


def php_cli(ver):
    p = os.path.join(const.EA_PHP_ROOT, ver or '', 'root/usr/bin/php')
    return p if ver and os.access(p, os.X_OK) else '/usr/local/bin/php'


def wp(site, args, timeout=240):
    user = site['user']
    try:
        home = pwd.getpwnam(user).pw_dir
    except KeyError:
        return 1, 'unknown user'
    cmd = [php_cli(site.get('php')), '-d', 'memory_limit=512M', '-d', 'display_errors=0',
           const.WP_CLI, '--path=' + site['path'], '--no-color'] + list(args)
    if os.geteuid() == 0:
        cmd = ['/usr/sbin/runuser', '-u', user, '--'] + cmd
    env = {'HOME': home, 'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C', 'WP_CLI_CACHE_DIR': home + '/.wp-cli/cache'}
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                           start_new_session=True, timeout=timeout, env=env, cwd=site['path'])
        return p.returncode, p.stdout.decode('utf-8', 'replace').strip()
    except subprocess.TimeoutExpired:
        return 124, 'timeout'


def refresh(site):
    site['wp_version'] = wp_version(site['path'])
    rc, out = wp(site, ['plugin', 'list', '--name=' + PLUGIN, '--fields=status,version', '--format=json'], 120)
    site['checked'] = int(time.time())
    if rc != 0:
        site['lscache'] = 'error'
        site['error'] = out[-300:]
        return site
    try:
        rows = json.loads(out[out.index('['):]) if '[' in out else []
    except ValueError:
        rows = []
    if rows:
        site['lscache'] = 'enabled' if rows[0].get('status') in ('active', 'active-network') else 'disabled'
        site['plugin_version'] = rows[0].get('version', '')
    else:
        site['lscache'] = 'missing'
        site['plugin_version'] = ''
    site.pop('error', None)
    return site


def enable(site, version='latest'):
    if site.get('lscache') == 'missing' or not os.path.isdir(os.path.join(site['path'], 'wp-content/plugins', PLUGIN)):
        args = ['plugin', 'install', PLUGIN, '--activate']
        if version and version != 'latest':
            args += ['--version=' + version, '--force']
    else:
        args = ['plugin', 'activate', PLUGIN]
    rc, out = wp(site, args)
    refresh(site)
    if rc != 0:
        site['error'] = out[-300:]
    return rc == 0


def disable(site):
    rc, out = wp(site, ['plugin', 'deactivate', PLUGIN])
    refresh(site)
    if rc != 0:
        site['error'] = out[-300:]
    return rc == 0


def scan(only_new=False, users=None):
    state = cpanel.load_state()
    data = load()
    sites = data.get('sites', {})
    seen = set()
    known_users = {s['user'] for s in sites.values()}
    for vh in state.vhosts:
        if users and vh.user not in users:
            continue
        if only_new and vh.user in known_users:
            continue
        if not os.path.isdir(vh.docroot):
            continue
        for path in find_in(vh.docroot):
            if path in seen:
                continue
            seen.add(path)
            owner = owner_vhost(path, state.vhosts) or vh
            rel = os.path.relpath(path, owner.docroot)
            site = sites.get(path, {'flagged': False})
            site.update({
                'path': path, 'user': owner.user, 'vhost': owner.name, 'php': owner.php,
                'url': owner.name + ('' if rel == '.' else '/' + rel),
            })
            sites[path] = site
    if not only_new:
        for p in list(sites):
            if p not in seen and (not users or sites[p]['user'] in users):
                sites.pop(p)
    for p, site in sites.items():
        if p in seen:
            refresh(site)
    data['sites'] = sites
    data['time'] = int(time.time())
    save(data)
    return data


def set_flag(paths, flag):
    data = load()
    for p in paths:
        if p in data['sites']:
            data['sites'][p]['flagged'] = bool(flag)
    save(data)


def job_status():
    try:
        with open(JOB) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def run_job(action, paths=None, version='latest'):
    data = load()
    sites = data.get('sites', {})
    targets = [p for p in (paths or sites.keys()) if p in sites]
    if action in ('mass-enable', 'mass-disable', 'force-version') and not paths:
        targets = [p for p in targets if not sites[p].get('flagged')]
    job = {'action': action, 'total': len(targets), 'done': 0, 'ok': 0, 'failed': [], 'started': int(time.time()), 'running': True}
    util.write_atomic(JOB, json.dumps(job), 0o600)
    for p in targets:
        site = sites[p]
        if action in ('mass-enable', 'enable'):
            ok = enable(site, version)
        elif action in ('mass-disable', 'disable'):
            ok = disable(site)
            if ok and action == 'disable':
                site['flagged'] = True
        elif action == 'refresh':
            refresh(site)
            ok = site.get('lscache') != 'error'
        elif action == 'force-version':
            if site.get('lscache') not in ('enabled', 'disabled'):
                job['total'] -= 1
                continue
            args = ['plugin', 'install', PLUGIN, '--force'] + ([] if version == 'latest' else ['--version=' + version])
            rc, out = wp(site, args)
            refresh(site)
            ok = rc == 0
            if not ok:
                site['error'] = out[-300:]
        else:
            ok = False
        job['done'] += 1
        if ok:
            job['ok'] += 1
        else:
            job['failed'].append({'path': p, 'error': site.get('error', '')[-200:]})
        data['sites'] = sites
        save(data)
        util.write_atomic(JOB, json.dumps(job), 0o600)
    job['running'] = False
    job['finished'] = int(time.time())
    util.write_atomic(JOB, json.dumps(job), 0o600)
    util.log('cache job %s: %d/%d ok' % (action, job['ok'], job['total']))
    return job


def start_job(action, paths=None, version='latest'):
    cmd = ['/usr/bin/systemd-run', '--unit=olscp-cachejob-%d' % int(time.time()), '--collect', '--quiet',
           const.BASE + '/bin/olscp', 'cache', 'job', action, '--version', version]
    for p in paths or []:
        cmd += ['--path', p]
    job = job_status()
    if job.get('running') and time.time() - job.get('started', 0) < 7200:
        raise RuntimeError('another cache job is running')
    util.write_atomic(JOB, json.dumps({'action': action, 'total': 0, 'done': 0, 'running': True, 'started': int(time.time())}), 0o600)
    rc, out = util.run(cmd, timeout=30)
    if rc != 0:
        raise RuntimeError(out)
    return True


QUIC_FILE = const.STATE + '/quic-ips.json'


def quic_ips(refresh_now=False):
    try:
        with open(QUIC_FILE) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if refresh_now or time.time() - data.get('time', 0) > 86400:
        rc, out = util.run(['/usr/bin/curl', '-fsS', '--max-time', '20', 'https://quic.cloud/ips?ln'], timeout=30)
        ips = [l.strip() for l in out.splitlines() if re.match(r'^[0-9a-fA-F:.]+(/\d+)?$', l.strip())]
        if rc == 0 and ips:
            data = {'time': int(time.time()), 'ips': ips}
            util.write_atomic(QUIC_FILE, json.dumps(data), 0o600)
        elif not data:
            data = {'time': 0, 'ips': [], 'error': out.strip()[-200:]}
    return data


def cache_dir(vhost, settings=None):
    settings = settings or util.load_settings()
    return os.path.join(settings.get('cache_root') or const.CACHE_ROOT, vhost)


def purge(vhosts):
    n = 0
    for vh in vhosts:
        d = cache_dir(vh)
        if not os.path.isdir(d):
            continue
        for e in os.listdir(d):
            p = os.path.join(d, e)
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                try:
                    os.unlink(p)
                except OSError:
                    pass
            n += 1
    return n


def cache_usage():
    root = util.load_settings().get('cache_root') or const.CACHE_ROOT
    out = {}
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for n in names:
        total = 0
        files = 0
        for dp, _dn, fn in os.walk(os.path.join(root, n)):
            for f in fn:
                try:
                    total += os.lstat(os.path.join(dp, f)).st_size
                    files += 1
                except OSError:
                    pass
        out[n] = {'bytes': total, 'files': files}
    return out
