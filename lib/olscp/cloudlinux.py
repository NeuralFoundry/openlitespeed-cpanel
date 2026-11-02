import glob
import os
import signal
import time

from . import const, util

LIBLVE = ('/usr/lib64/liblve.so.0', '/lib64/liblve.so.0', '/usr/lib/liblve.so.0')
CAGEFSCTL = '/usr/sbin/cagefsctl'
CAGEFS_CFG = '/etc/cagefs/conf.d/olscp.cfg'
MODES = {'off': 0, 'lve': 1, 'cagefs': 2}
UNIT = 'olscp-cagefs-update'


def detect():
    lve = any(os.path.exists(p) for p in LIBLVE) and os.path.exists('/proc/lve')
    cagefs = lve and os.access(CAGEFSCTL, os.X_OK)
    return {
        'cloudlinux': os.path.exists('/etc/cloudlinux-release') or os.path.exists('/proc/lve'),
        'lve': lve,
        'cagefs': cagefs,
    }


def mode(settings, found=None):
    found = found or detect()
    want = settings.get('cloudlinux', 'auto')
    if want == 'off' or not found['lve']:
        return 'off'
    if want == 'lve':
        return 'lve'
    return 'cagefs' if found['cagefs'] else 'lve'


def lve_value(settings):
    return MODES[mode(settings)]


def cagefs_paths():
    paths = [const.OLS_ROOT + '/fcgi-bin/', const.BASE + '/libexec/']
    for p in sorted(glob.glob('/opt/cpanel/ea-nodejs*/')) + sorted(glob.glob('/opt/cpanel/ea-ruby*/')):
        if os.path.isdir(p):
            paths.append(p)
    return paths


def cagefs_config():
    return '[olscp]\ncomment=OpenLiteSpeed for cPanel\npaths=%s\n' % ', '.join(cagefs_paths())


def sync_cagefs(active):
    current = util.read_text(CAGEFS_CFG)
    if active:
        want = cagefs_config()
        if current == want:
            return False
        os.makedirs(os.path.dirname(CAGEFS_CFG), exist_ok=True)
        util.write_atomic(CAGEFS_CFG, want, 0o644)
    elif current is not None:
        os.unlink(CAGEFS_CFG)
    else:
        return False
    if os.access(CAGEFSCTL, os.X_OK):
        rc, out = util.run(['/usr/bin/systemd-run', '--unit', '%s-%d' % (UNIT, int(time.time())), '--collect',
                            '--quiet', '-p', 'Nice=10', CAGEFSCTL, '--update'], timeout=30)
        if rc != 0:
            if active:
                os.unlink(CAGEFS_CFG)
            util.log('cagefsctl --update could not start: %s' % out.strip()[-300:], 'WARN')
            return False
    util.log('CageFS configuration %s' % ('updated' if active else 'removed'))
    return True


def stop_workers():
    from . import apps
    count = 0
    for pid in os.listdir('/proc'):
        if not pid.isdigit():
            continue
        try:
            with open('/proc/%s/cmdline' % pid, 'rb') as f:
                cmd = f.read().split(b'\0')[0]
        except OSError:
            continue
        if os.path.basename(cmd).startswith(b'lsphp'):
            try:
                os.kill(int(pid), signal.SIGTERM)
                count += 1
            except OSError:
                pass
    for pid, _uid, _root in apps.processes():
        try:
            os.kill(pid, signal.SIGTERM)
            count += 1
        except OSError:
            pass
    return count


def status(settings):
    found = detect()
    found.update({'setting': settings.get('cloudlinux', 'auto'), 'mode': mode(settings, found),
                  'cagefs_config': os.path.exists(CAGEFS_CFG)})
    return found
