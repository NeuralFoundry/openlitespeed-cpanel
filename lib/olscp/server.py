import os
import re
import signal
import socket
import struct
import subprocess
import time

from . import const, util

PREVIEW_PID = const.RUN + '/preview.pid'


def _env(pidfile):
    env = {
        'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'LANG': 'C',
        'OLS_PID_FILE': pidfile,
    }
    if pidfile == const.APACHE_PID:
        env['OLSCP_HT_NOTIFY'] = const.HT_NOTIFY
    try:
        from . import apacheconf
        mods = apacheconf.present_modules()
        if len(mods) > 1:
            env['OLSCP_HT_MODULES'] = ','.join(sorted(mods))
    except Exception:
        pass
    return env


def installed():
    return os.access(os.path.join(const.OLS_BIN_DIR, 'openlitespeed'), os.X_OK)


def version():
    return (util.read_text(const.OLS_VERSION_FILE, '') or '').strip()


def _is_ols(pid):
    try:
        exe = os.readlink('/proc/%d/exe' % pid)
    except OSError:
        return False
    return exe.startswith(const.OLS_ROOT + '/') and os.stat('/proc/%d' % pid).st_uid == 0


def _cmdline(pid):
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as f:
            return f.read()
    except OSError:
        return b''


def _ppid(pid):
    try:
        return int((util.read_text('/proc/%d/stat' % pid, '') or '').rsplit(')', 1)[1].split()[1])
    except (ValueError, IndexError):
        return 0


def _pidfile_of(pid):
    try:
        with open('/proc/%d/environ' % pid, 'rb') as f:
            env = f.read().split(b'\0')
    except OSError:
        return ''
    for e in env:
        if e.startswith(b'OLS_PID_FILE='):
            return e[13:].decode('utf-8', 'replace')
    return ''


def adopt(pidfile):
    found = [p for p in ols_pids() if b'lshttpd - main' in _cmdline(p) and _is_ols(p)
             and _pidfile_of(p) == pidfile and b'lshttpd - main' not in _cmdline(_ppid(p))]
    if len(found) != 1:
        return 0
    util.write_atomic(pidfile, '%d\n' % found[0], 0o644)
    util.log('pid file %s repaired: %d' % (pidfile, found[0]), 'WARN')
    return found[0]


def main_pid(pidfile=const.APACHE_PID, repair=True):
    pid = util.read_pid(pidfile)
    if pid and util.pid_alive(pid) and _is_ols(pid):
        return pid
    if repair and pid:
        return adopt(pidfile)
    return 0


def workers(pid):
    n = 0
    for p in ols_pids():
        if _ppid(p) == pid and b'lshttpd - #' in _cmdline(p):
            n += 1
    return n


def settled(pid, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        if not pid or not util.pid_alive(pid) or not _is_ols(pid):
            return False
        if workers(pid):
            return True
        time.sleep(0.25)
    return util.pid_alive(pid)


LISTEN_ADDR = re.compile(r'(?ms)^\s*listener\s+\S+\s*\{.*?^\s*address\s+(\S+)')


def listening_v4():
    out = {}
    for line in (util.read_text('/proc/net/tcp', '') or '').splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4 or parts[3] != '0A':
            continue
        ip_hex, port_hex = parts[1].split(':')
        ip = socket.inet_ntoa(struct.pack('<I', int(ip_hex, 16)))
        out.setdefault(int(port_hex, 16), set()).add(ip)
    return out


def needs_full_restart(conf_texts):
    live = listening_v4()
    for text in conf_texts:
        for addr in LISTEN_ADDR.findall(text or ''):
            if addr.startswith('['):
                continue
            host, _, port = addr.rpartition(':')
            if not port.isdigit():
                continue
            ip = '0.0.0.0' if host in ('*', '') else host
            have = live.get(int(port))
            if have and ip not in have:
                return True
    return False


def ols_pids():
    out = []
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            exe = os.readlink('/proc/%s/exe' % d)
        except OSError:
            continue
        if exe.startswith(const.OLS_ROOT + '/bin/'):
            out.append(int(d))
    return out


def running(pidfile=const.APACHE_PID):
    return main_pid(pidfile) != 0


def _wait(cond, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.2)
    return cond()


def start(timeout=20, pidfile=const.APACHE_PID):
    if running(pidfile):
        return True
    os.makedirs(os.path.dirname(pidfile), exist_ok=True)
    try:
        os.unlink(pidfile)
    except OSError:
        pass
    p = subprocess.run(['./litespeed'], cwd=const.OLS_BIN_DIR, env=_env(pidfile),
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if p.returncode != 0:
        util.log('openlitespeed exited with %d on start' % p.returncode, 'ERROR')
        return False
    ok = _wait(lambda: running(pidfile), timeout) and settled(main_pid(pidfile, repair=False))
    util.log('start %s pid=%s' % ('ok' if ok else 'FAILED', main_pid(pidfile, repair=False)))
    return ok


def graceful(timeout=30, pidfile=const.APACHE_PID):
    old = main_pid(pidfile)
    if not old:
        return start(pidfile=pidfile)
    os.kill(old, signal.SIGUSR1)
    ok = _wait(lambda: main_pid(pidfile, repair=False) not in (0, old), timeout)
    new = main_pid(pidfile, repair=False)
    if ok:
        ok = settled(new)
    if not ok and util.pid_alive(old) and _is_ols(old):
        util.write_atomic(pidfile, '%d\n' % old, 0o644)
        new = old
    util.log('graceful %s %s -> %s' % ('ok' if ok else 'FAILED', old, new), 'INFO' if ok else 'ERROR')
    return ok


def systemd_reattach():
    rc, out = util.run(['/usr/bin/systemctl', 'is-active', 'httpd.service'])
    if out.strip() == 'active':
        return
    util.run(['/usr/bin/systemctl', 'reset-failed', 'httpd.service'])
    util.run(['/usr/bin/systemctl', 'start', '--no-block', 'httpd.service'])


def full_restart(pidfile=const.APACHE_PID):
    stop(pidfile=pidfile)
    ok = start(pidfile=pidfile)
    util.log('full restart %s pid=%s' % ('ok' if ok else 'FAILED', main_pid(pidfile, repair=False)))
    if pidfile == const.APACHE_PID:
        systemd_reattach()
    return ok


def stop(timeout=20, pidfile=const.APACHE_PID):
    pid = main_pid(pidfile)
    if not pid and pidfile != const.APACHE_PID:
        return True
    if pid:
        try:
            os.kill(pid, signal.SIGUSR2)
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        _wait(lambda: not util.pid_alive(pid), timeout)
    left = ols_pids()
    for p in left:
        try:
            os.kill(p, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        os.unlink(pidfile)
    except OSError:
        pass
    util.log('stop pid=%s killed=%d' % (pid, len(left)))
    return True


def info():
    pid = main_pid()
    out = {'installed': installed(), 'version': version(), 'pid': pid, 'running': bool(pid)}
    if pid:
        started = start_time(pid)
        if started:
            out['started'] = started
        out['workers'] = max(0, len(ols_pids()) - 2)
    return out


def start_time(pid):
    try:
        stat = util.read_text('/proc/%d/stat' % pid, '')
        ticks = int(stat.rsplit(')', 1)[1].split()[19])
        btime = 0
        for line in (util.read_text('/proc/stat', '') or '').splitlines():
            if line.startswith('btime '):
                btime = int(line.split()[1])
        return int(btime + ticks / os.sysconf('SC_CLK_TCK'))
    except (ValueError, IndexError, OSError):
        return 0


def recent_errors(since, limit=40):
    out = []
    text = util.read_text(const.APACHE_ERROR_LOG, '') or ''
    tail = text[-400000:]
    for line in tail.splitlines():
        if '[ERROR]' not in line and '[WARN]' not in line:
            continue
        ts = line[:19]
        try:
            t = time.mktime(time.strptime(ts, '%Y-%m-%d %H:%M:%S'))
        except ValueError:
            continue
        if t >= since - 1:
            out.append(line[:400])
    return out[-limit:]
