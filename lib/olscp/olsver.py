import re

from . import const, server, util

REPOS = 'olscp-litespeed,olscp-litespeed-update'


def available():
    rc, out = util.run(['/usr/bin/dnf', '-q', '--disablerepo=*', '--enablerepo=' + REPOS,
                        'list', '--available', '--showduplicates', 'openlitespeed'], timeout=180)
    versions = sorted({m.group(1) for m in re.finditer(r'^openlitespeed\.\S+\s+(\d+\.\d+\.\d+)', out, re.M)},
                      key=lambda v: [int(x) for x in v.split('.')])
    if not versions:
        raise RuntimeError(out.strip()[-600:] or 'no versions found')
    return versions


def info():
    out = {'current': server.version()}
    try:
        out['available'] = available()
        out['latest'] = out['available'][-1]
    except Exception as e:
        out['error'] = str(e)
    return out


def upgrade(version=None, rpm=None):
    args = [const.BASE + '/libexec/ols-install.sh']
    if rpm:
        args += ['--rpm', rpm]
    elif version:
        if not re.match(r'^\d+\.\d+\.\d+$', version):
            raise RuntimeError('bad version')
        args.append(version)
    rc, out = util.run(args, timeout=900)
    if rc != 0:
        raise RuntimeError(out.strip()[-1500:])
    from . import olsbuild, sync
    olsbuild.after_upgrade()
    sync.sync(restart=False, reason='ols-upgrade')
    ok = server.graceful() if server.running() else True
    util.log('openlitespeed upgraded to %s' % server.version())
    return {'version': server.version(), 'restarted': ok}
