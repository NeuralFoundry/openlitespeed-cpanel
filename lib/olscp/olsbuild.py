import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import zlib

from . import const, server, util

ACTIVE = const.OLS_BIN_DIR + '/openlitespeed'
OFFICIAL = const.OLS_BIN_DIR + '/openlitespeed.official'
PATCHED = const.OLS_BIN_DIR + '/openlitespeed.olscp'
SCRIPT = const.BASE + '/build/build-ols.sh'
WORK = const.STATE + '/ols-build'
JOB = const.STATE + '/ols-build.json'
LOG = '/var/log/olscp-ols-build.log'
CACHE = const.STATE + '/ols-binary.json'
UNIT = 'olscp-ols-build'
MARKER = b'OLSCP_HT_NOTIFY'
PREBUILT = const.BASE + '/build/prebuilt.txt'
FETCHED = const.STATE + '/ols-prebuilt.json'
MAX_BINARY = 96 << 20


def _sig(path):
    st = os.stat(path)
    return '%d:%d:%d' % (st.st_ino, st.st_size, int(st.st_mtime))


def is_patched(path=ACTIVE):
    try:
        sig = _sig(path)
    except OSError:
        return False
    try:
        with open(CACHE) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    if path in cache and cache[path].get('sig') == sig:
        return cache[path]['patched']
    found = False
    tail = b''
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            if MARKER in tail + chunk:
                found = True
                break
            tail = chunk[-len(MARKER):]
    cache[path] = {'sig': sig, 'patched': found}
    try:
        util.write_atomic(CACHE, json.dumps(cache), 0o600)
    except OSError:
        pass
    return found


def current():
    return 'olscp' if is_patched(ACTIVE) else 'official'


def live():
    return current() == 'olscp'


def target_version():
    m = re.search(r'^OLS_TAG=v(\S+)', util.read_text(SCRIPT, '') or '', re.M)
    return m.group(1) if m else ''


def binary_version(path):
    if not os.access(path, os.X_OK):
        return ''
    rc, out = util.run([path, '-v'], timeout=20)
    m = re.search(r'LiteSpeed/(\d+\.\d+\.\d+)', out)
    return m.group(1) if m else ''


def job():
    try:
        with open(JOB) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    rc, out = util.run(['/usr/bin/systemctl', 'is-active', UNIT + '.service'])
    data['running'] = out.strip() in ('active', 'activating')
    data['log'] = (util.read_text(LOG, '') or '').splitlines()[-15:]
    return data


def info():
    item = prebuilt()
    return {
        'current': current(),
        'olscp_available': os.path.isfile(PATCHED),
        'olscp_version': binary_version(PATCHED) if os.path.isfile(PATCHED) else '',
        'official_available': os.path.isfile(OFFICIAL) or current() == 'official',
        'installed_version': server.version(),
        'target_version': target_version(),
        'prebuilt': item,
        'prebuilt_current': bool(item) and os.path.isfile(PATCHED) and sha256(PATCHED) == item['sha256'],
        'job': job(),
    }


def platform():
    text = util.read_text('/etc/os-release', '') or ''
    m = re.search(r'^VERSION_ID="?(\d+)', text, re.M)
    return ('el' + m.group(1) if m else ''), os.uname().machine


def prebuilt(version=None):
    el, arch = platform()
    version = version or server.version()
    for line in (util.read_text(PREBUILT, '') or '').splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[:3] == [el, arch, version] and re.match(r'^[0-9a-f]{64}$', parts[3]) \
                and parts[4].startswith('https://github.com/'):
            return {'platform': el, 'arch': arch, 'version': version, 'sha256': parts[3], 'url': parts[4]}
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def fetch():
    from . import update
    item = prebuilt()
    if not item:
        el, arch = platform()
        raise RuntimeError('no prebuilt olscp build for OpenLiteSpeed %s on %s %s, compile it instead'
                           % (server.version(), el, arch))
    blob = update.get(item['url'], 48 << 20, 120)
    if blob[:2] == b'\x1f\x8b':
        z = zlib.decompressobj(16 + zlib.MAX_WBITS)
        data = z.decompress(blob, MAX_BINARY + 1)
        if len(data) > MAX_BINARY or z.unconsumed_tail:
            raise RuntimeError('prebuilt binary is too large')
    else:
        data = blob
    if len(data) > MAX_BINARY:
        raise RuntimeError('prebuilt binary is too large')
    if hashlib.sha256(data).hexdigest() != item['sha256']:
        raise RuntimeError('prebuilt binary checksum mismatch')
    tmp = PATCHED + '.new'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.chmod(tmp, 0o755)
    ver = binary_version(tmp)
    if ver != item['version'] or not is_patched(tmp):
        os.unlink(tmp)
        raise RuntimeError('prebuilt binary does not run here (reports %r)' % ver)
    os.rename(tmp, PATCHED)
    util.write_atomic(FETCHED, json.dumps({'sha256': item['sha256'], 'time': int(time.time())}), 0o600)
    util.log('downloaded prebuilt olscp build %s for %s' % (item['version'], item['platform']))
    return {'fetched': True, 'version': ver, 'sha256': item['sha256']}


def refresh():
    item = prebuilt()
    if current() != 'olscp' or not item or not os.path.isfile(PATCHED):
        return {'changed': False}
    try:
        with open(FETCHED) as f:
            mine = json.load(f).get('sha256')
    except (OSError, ValueError):
        mine = None
    have = sha256(PATCHED)
    if have == item['sha256'] or have != mine:
        return {'changed': False}
    res = fetch()
    res.update(use('olscp'))
    return res


def start_build():
    if job().get('running'):
        raise RuntimeError('a build is already running')
    want = target_version()
    if want and server.version() and want != server.version():
        raise RuntimeError('the live .htaccess patch targets OpenLiteSpeed %s, installed is %s' % (want, server.version()))
    util.write_atomic(JOB, json.dumps({'started': int(time.time()), 'finished': 0, 'ok': None}), 0o600)
    with open(LOG, 'w') as f:
        f.write('')
    rc, out = util.run(['/usr/bin/systemd-run', '--unit', UNIT, '--collect', '--quiet',
                        '-p', 'Nice=10', '-p', 'CPUWeight=20', '-p', 'IOWeight=20',
                        const.BASE + '/bin/olscp', 'ols', 'build-run'])
    if rc != 0:
        util.write_atomic(JOB, json.dumps({'started': int(time.time()), 'finished': int(time.time()), 'ok': False,
                                           'error': out.strip()[-500:]}), 0o600)
        raise RuntimeError(out.strip()[-500:] or 'systemd-run failed')
    return {'started': True}


def run_build():
    state = {'started': int(time.time()), 'finished': 0, 'ok': None}
    try:
        with open(JOB) as f:
            state.update(json.load(f))
    except (OSError, ValueError):
        pass
    env = dict(os.environ, OLSCP_BUILD_DIR=WORK)
    with open(LOG, 'a') as log:
        p = subprocess.run(['/bin/bash', SCRIPT, 'all'], stdout=log, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, env=env)
    built = os.path.join(WORK, 'dist/openlitespeed')
    ok = p.returncode == 0 and os.path.isfile(built) and is_patched(built)
    if ok:
        tmp = PATCHED + '.new'
        shutil.copyfile(built, tmp)
        os.chmod(tmp, 0o755)
        os.rename(tmp, PATCHED)
    state.update({'finished': int(time.time()), 'ok': ok, 'rc': p.returncode})
    util.write_atomic(JOB, json.dumps(state), 0o600)
    util.log('openlitespeed build %s' % ('ok' if ok else 'FAILED rc=%d' % p.returncode))
    return state


def install_binary(src):
    tmp = ACTIVE + '.new'
    shutil.copyfile(src, tmp)
    os.chmod(tmp, 0o755)
    os.rename(tmp, ACTIVE)


def use(which):
    from . import sync
    if which == 'olscp':
        if not os.path.isfile(PATCHED) or not is_patched(PATCHED):
            raise RuntimeError('olscp build not available, build it first')
        ver = binary_version(PATCHED)
        if ver != server.version():
            raise RuntimeError('olscp build is %s but installed OpenLiteSpeed is %s, rebuild first' % (ver, server.version()))
        if not is_patched(ACTIVE):
            shutil.copyfile(ACTIVE, OFFICIAL + '.new')
            os.chmod(OFFICIAL + '.new', 0o755)
            os.rename(OFFICIAL + '.new', OFFICIAL)
        install_binary(PATCHED)
    elif which == 'official':
        if is_patched(ACTIVE):
            if not os.path.isfile(OFFICIAL) or is_patched(OFFICIAL):
                raise RuntimeError('official binary backup missing, reinstall with: olscp ols upgrade')
            install_binary(OFFICIAL)
    else:
        raise RuntimeError('unknown build: %s' % which)
    res = sync.sync(restart=True, reason='ols-use-' + which, force_restart=True)
    util.log('openlitespeed binary switched to %s' % current())
    return {'ok': res.get('ok', True), 'current': current()}


def after_upgrade():
    if os.path.isfile(ACTIVE) and not is_patched(ACTIVE):
        shutil.copyfile(ACTIVE, OFFICIAL + '.new')
        os.chmod(OFFICIAL + '.new', 0o755)
        os.rename(OFFICIAL + '.new', OFFICIAL)
