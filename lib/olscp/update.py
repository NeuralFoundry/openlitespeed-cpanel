import json
import os
import re
import shutil
import subprocess
import tarfile
import time
import urllib.request

from . import VERSION, const, util

REPO = 'NeuralFoundry/openlitespeed-cpanel'
API = 'https://api.github.com/repos/%s/releases/latest' % REPO
TARBALL = 'https://github.com/%s/archive/refs/tags/%s.tar.gz'
CACHE = const.STATE + '/update.json'
JOB = const.STATE + '/update-job.json'
WORK = const.STATE + '/update'
LOG = '/var/log/olscp-update.log'
UNIT = 'olscp-update'
TAG = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')
MAX_DOWNLOAD = 64 << 20
CHECK_EVERY = 6 * 3600


def get(url, limit=MAX_DOWNLOAD, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'olscp/' + VERSION, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError('download from %s is too large' % url)
    return data


def version_tuple(v):
    m = re.match(r'^v?(\d+)\.(\d+)\.(\d+)$', v or '')
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def check(force=False):
    try:
        with open(CACHE) as f:
            cached = json.load(f)
    except (OSError, ValueError):
        cached = {}
    if not force and cached.get('checked', 0) > time.time() - CHECK_EVERY and cached.get('current') == VERSION:
        return cached
    data = {'current': VERSION, 'checked': int(time.time())}
    try:
        rel = json.loads(get(API, 1 << 20, 15).decode('utf-8'))
        tag = rel.get('tag_name') or ''
        if not TAG.match(tag):
            raise RuntimeError('unexpected release tag %r' % tag)
        data.update({'latest': tag[1:], 'tag': tag, 'url': rel.get('html_url') or '',
                     'published': rel.get('published_at') or '',
                     'available': version_tuple(tag) > version_tuple(VERSION)})
    except Exception as e:
        data.update({'error': str(e)[:300], 'latest': cached.get('latest', ''), 'tag': cached.get('tag', ''),
                     'available': cached.get('available', False) and version_tuple(cached.get('tag')) > version_tuple(VERSION)})
    util.write_atomic(CACHE, json.dumps(data), 0o600)
    return data


def job():
    try:
        with open(JOB) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    rc, out = util.run(['/usr/bin/systemctl', 'is-active', UNIT + '.service'])
    data['running'] = out.strip() in ('active', 'activating')
    data['log'] = (util.read_text(LOG, '') or '').splitlines()[-20:]
    return data


def info(force=False):
    data = check(force)
    data['job'] = job()
    return data


def start():
    if job().get('running'):
        raise RuntimeError('an update is already running')
    data = check(force=True)
    if data.get('error'):
        raise RuntimeError(data['error'])
    if not data.get('available'):
        raise RuntimeError('olscp %s is the latest release' % VERSION)
    util.write_atomic(JOB, json.dumps({'started': int(time.time()), 'finished': 0, 'ok': None, 'tag': data['tag']}), 0o600)
    with open(LOG, 'w') as f:
        f.write('')
    rc, out = util.run(['/usr/bin/systemd-run', '--unit', UNIT, '--collect', '--quiet',
                        const.BASE + '/bin/olscp', 'update', 'run', '--tag', data['tag']])
    if rc != 0:
        raise RuntimeError(out.strip()[-500:] or 'systemd-run failed')
    return {'started': True, 'tag': data['tag']}


def extract(blob, dest, top):
    path = os.path.join(WORK, 'source.tar.gz')
    with open(path, 'wb') as f:
        f.write(blob)
    with tarfile.open(path, 'r:gz') as tar:
        members = []
        for m in tar.getmembers():
            name = m.name.rstrip('/')
            parts = name.split('/')
            if name.startswith('/') or '..' in parts or parts[0] != top:
                raise RuntimeError('unexpected path in the release archive: %s' % m.name)
            if m.isdir() or m.isfile():
                m.mode = 0o755 if m.isdir() or m.mode & 0o111 else 0o644
                m.uid = m.gid = 0
                m.uname = m.gname = 'root'
                members.append(m)
            elif m.type != tarfile.XGLTYPE and m.type != tarfile.XHDTYPE:
                raise RuntimeError('unexpected entry in the release archive: %s' % m.name)
        extra = {'filter': 'tar'} if hasattr(tarfile, 'tar_filter') else {}
        tar.extractall(dest, members=members, **extra)
    os.unlink(path)
    return os.path.join(dest, top)


def run(tag):
    state = {'started': int(time.time()), 'finished': 0, 'ok': None, 'tag': tag}
    try:
        with open(JOB) as f:
            state.update(json.load(f))
    except (OSError, ValueError):
        pass
    ok = False
    with open(LOG, 'a') as log:
        try:
            if not TAG.match(tag or ''):
                raise RuntimeError('bad tag %r' % tag)
            log.write('downloading %s\n' % tag)
            log.flush()
            shutil.rmtree(WORK, ignore_errors=True)
            os.makedirs(WORK, 0o700)
            src = extract(get(TARBALL % (REPO, tag)), WORK, 'openlitespeed-cpanel-' + tag[1:])
            got = (util.read_text(os.path.join(src, 'VERSION'), '') or '').strip()
            if got != tag[1:] or not os.path.isfile(os.path.join(src, 'install.sh')):
                raise RuntimeError('the release archive does not contain olscp %s' % tag[1:])
            log.write('installing olscp %s\n' % got)
            log.flush()
            p = subprocess.run(['/bin/bash', os.path.join(src, 'install.sh')], cwd=src, stdout=log,
                               stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            ok = p.returncode == 0
            if not ok:
                log.write('install.sh exited with %d\n' % p.returncode)
            else:
                refresh_build(log)
        except Exception as e:
            log.write('ERROR: %s\n' % e)
        finally:
            shutil.rmtree(WORK, ignore_errors=True)
    state.update({'finished': int(time.time()), 'ok': ok})
    util.write_atomic(JOB, json.dumps(state), 0o600)
    util.log('update to %s %s' % (tag, 'ok' if ok else 'FAILED'))
    return state


def refresh_build(log):
    rc, out = util.run([const.BASE + '/bin/olscp', '--json', 'ols', 'refresh'], timeout=900)
    log.write('olscp build: %s\n' % (out.strip()[-300:] or rc))
