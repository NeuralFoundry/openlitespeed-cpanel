import os
import shutil
import socket
import time

from . import const, olsbuild, server, sync, util

RESTARTSRV = '/usr/local/cpanel/scripts/restartsrv_httpd'
WRAPPER_MARK = b'olscp-httpd-wrapper'
HOOK_DIR = '/etc/dnf/universal-hooks/multi_pkgs/transaction/ea-__WILDCARD__'
HOOK = HOOK_DIR + '/999-olscp-reapply'
HOOK_SRC = const.BASE + '/hooks/999-olscp-reapply'
UNIT = 'olscp-watch.service'


def wrapper_installed():
    try:
        with open(const.HTTPD, 'rb') as f:
            return WRAPPER_MARK in f.read(512)
    except OSError:
        return False


def is_elf(path):
    try:
        with open(path, 'rb') as f:
            return f.read(4) == b'\x7fELF'
    except OSError:
        return False


def install_wrapper():
    if not wrapper_installed():
        if not is_elf(const.HTTPD):
            raise RuntimeError('%s is neither the Apache binary nor the olscp wrapper' % const.HTTPD)
        tmp = const.HTTPD_REAL + '.tmp'
        shutil.copy2(const.HTTPD, tmp)
        os.replace(tmp, const.HTTPD_REAL)
    elif not is_elf(const.HTTPD_REAL):
        raise RuntimeError('real Apache binary missing: %s' % const.HTTPD_REAL)
    tmp = const.HTTPD + '.olscp-tmp'
    shutil.copy2(const.WRAPPER_SRC, tmp)
    os.chmod(tmp, 0o755)
    os.replace(tmp, const.HTTPD)


def remove_wrapper():
    if wrapper_installed() and is_elf(const.HTTPD_REAL):
        tmp = const.HTTPD + '.olscp-tmp'
        shutil.copy2(const.HTTPD_REAL, tmp)
        os.replace(tmp, const.HTTPD)
        os.unlink(const.HTTPD_REAL)


def install_hook():
    if os.path.isdir(HOOK_DIR) and os.path.exists(HOOK_SRC):
        shutil.copy2(HOOK_SRC, HOOK)
        os.chmod(HOOK, 0o755)


def remove_hook():
    try:
        os.unlink(HOOK)
    except OSError:
        pass


def apache_pids():
    out = []
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            exe = os.readlink('/proc/%s/exe' % d)
        except OSError:
            continue
        exe = exe.replace(' (deleted)', '')
        if exe in (const.HTTPD, const.HTTPD_REAL):
            out.append(int(d))
    return out


def port_open(port, host='127.0.0.1'):
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def http_probe(host='127.0.0.1', port=80):
    s = socket.socket()
    s.settimeout(5)
    try:
        s.connect((host, port))
        s.sendall(b'HEAD / HTTP/1.0\r\nHost: localhost\r\n\r\n')
        data = s.recv(200).decode('latin-1', 'replace')
        return data.split('\r\n', 1)[0]
    except OSError as e:
        return 'ERROR %s' % e
    finally:
        s.close()


def systemctl(*args):
    return util.run(['/usr/bin/systemctl'] + list(args), timeout=120)


def wait_apache_gone(timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if not apache_pids() and not port_open(80):
            return True
        time.sleep(0.3)
    return not apache_pids()


def enable():
    if not server.installed():
        raise RuntimeError('OpenLiteSpeed is not installed under %s' % const.OLS_ROOT)
    const.ensure_dirs()
    steps = []
    if server.running(server.PREVIEW_PID):
        server.stop(pidfile=server.PREVIEW_PID)
        steps.append('preview stopped')
    res = sync.sync(restart=False, reason='enable')
    steps.append('config: %d vhosts' % res['vhosts'])
    if not wrapper_installed():
        rc, out = util.run([RESTARTSRV, '--stop'], timeout=180)
        steps.append('apache stop rc=%d' % rc)
        if not wait_apache_gone():
            for p in apache_pids():
                try:
                    os.kill(p, 15)
                except OSError:
                    pass
            wait_apache_gone(10)
        install_wrapper()
        steps.append('wrapper installed')
    open(const.ACTIVE_FLAG, 'w').close()
    rc, out = util.run([RESTARTSRV, '--start'], timeout=180)
    steps.append('start rc=%d' % rc)
    if not server.running():
        server.start()
    probe = http_probe()
    if not server.running():
        util.log('enable failed, reverting to Apache: %s' % out[-2000:], 'ERROR')
        disable()
        raise RuntimeError('OpenLiteSpeed did not start; Apache restored. Output: %s' % out[-1500:])
    install_hook()
    systemctl('enable', '--now', UNIT)
    steps.append('watcher enabled')
    steps.append('probe: %s' % probe)
    sync.write_status({'mode': 'ols', 'switched_at': int(time.time())})
    util.log('enabled OpenLiteSpeed: %s' % '; '.join(steps))
    return steps


def disable():
    steps = []
    try:
        os.unlink(const.ACTIVE_FLAG)
    except OSError:
        pass
    systemctl('disable', '--now', UNIT)
    server.stop()
    steps.append('ols stopped')
    remove_wrapper()
    steps.append('apache binary restored')
    remove_hook()
    rc, out = util.run([RESTARTSRV, '--start'], timeout=180)
    steps.append('apache start rc=%d' % rc)
    steps.append('probe: %s' % http_probe())
    sync.write_status({'mode': 'apache', 'switched_at': int(time.time())})
    util.log('disabled OpenLiteSpeed: %s' % '; '.join(steps))
    return steps


def reapply():
    if not sync.active():
        return ['inactive']
    steps = []
    if not wrapper_installed():
        apache_running = bool(apache_pids())
        install_wrapper()
        steps.append('wrapper reinstalled')
        if apache_running:
            util.run([const.HTTPD_REAL, '-k', 'stop'], timeout=60)
            wait_apache_gone()
            steps.append('apache stopped')
    if not server.running():
        rc, out = util.run([RESTARTSRV, '--start'], timeout=180)
        steps.append('start rc=%d' % rc)
        if not server.running():
            server.start()
    util.log('reapply: %s' % '; '.join(steps or ['nothing to do']))
    return steps


def status():
    st = sync.read_status()
    info = server.info()
    return {
        'active': sync.active(),
        'wrapper': wrapper_installed(),
        'ols': info,
        'apache_pids': apache_pids(),
        'port80': port_open(80),
        'port443': port_open(443),
        'probe': http_probe() if port_open(80) else '',
        'watcher': systemctl('is-active', UNIT)[1].strip(),
        'last_sync': st.get('last_sync'),
        'mode': st.get('mode'),
        'switched_at': st.get('switched_at'),
        'live_htaccess': olsbuild.live() and info.get('running', False),
        'ols_build': olsbuild.current(),
    }
