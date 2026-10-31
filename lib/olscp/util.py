import fcntl
import json
import os
import subprocess
import tempfile
import time

from . import const


def log(msg, level='INFO'):
    line = '%s [%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), level, msg)
    try:
        with open(const.LOG, 'a') as f:
            f.write(line)
    except OSError:
        pass


def read_text(path, default=None):
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return default


def write_atomic(path, data, mode=0o644, owner=None):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.olscp-', dir=d)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(data)
        os.chmod(tmp, mode)
        if owner:
            os.chown(tmp, owner[0], owner[1])
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_kv(path, sep='='):
    out = {}
    text = read_text(path, '')
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or sep not in line:
            continue
        k, v = line.split(sep, 1)
        out[k.strip()] = v.strip()
    return out


def load_settings():
    s = dict(const.DEFAULT_SETTINGS)
    try:
        with open(const.SETTINGS) as f:
            data = json.load(f)
        for k, v in data.items():
            if k in s:
                s[k] = v
    except (OSError, ValueError):
        pass
    return s


def save_settings(values):
    s = load_settings()
    for k, v in values.items():
        if k in const.DEFAULT_SETTINGS:
            s[k] = v
    write_atomic(const.SETTINGS, json.dumps(s, indent=2, sort_keys=True) + '\n', 0o600)
    return s


def run(args, timeout=120, env=None, cwd=None):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
                       env=env, cwd=cwd)
    return p.returncode, p.stdout.decode('utf-8', 'replace')


class Lock(object):
    def __init__(self, path, timeout=60):
        self.path = path
        self.timeout = timeout
        self.fh = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.fh = open(self.path, 'a')
        end = time.time() + self.timeout
        while True:
            try:
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.time() > end:
                    raise TimeoutError('lock busy: %s' % self.path)
                time.sleep(0.2)

    def __exit__(self, *a):
        try:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
        finally:
            self.fh.close()


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_pid(path):
    try:
        return int(read_text(path, '').strip() or 0)
    except ValueError:
        return 0
