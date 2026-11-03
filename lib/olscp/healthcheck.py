import re
import socket
import ssl
import threading
import time

LOOPBACK = '127.0.0.1'
NAME_RE = re.compile(r'^(?=.{1,253}\Z)[A-Za-z0-9]([A-Za-z0-9-]{0,62}\.)*[A-Za-z0-9]([A-Za-z0-9-]{0,62})\Z')


def valid_host(name):
    if not name or '\n' in name or '\r' in name:
        return False
    return bool(NAME_RE.match(name))


def _status_line(sock, host):
    req = ('HEAD / HTTP/1.0\r\nHost: %s\r\nUser-Agent: olscp-healthcheck\r\n'
           'Accept: */*\r\nConnection: close\r\n\r\n' % host).encode('ascii')
    sock.sendall(req)
    buf = b''
    while b'\n' not in buf and len(buf) < 4096:
        chunk = sock.recv(512)
        if not chunk:
            break
        buf += chunk
    return buf.split(b'\r\n', 1)[0].decode('latin-1', 'replace')


def probe(host, port, tls, timeout=6.0):
    try:
        raw = socket.create_connection((LOOPBACK, port), timeout=timeout)
    except OSError as e:
        return False, 'connect: %s' % e
    sock = raw
    try:
        raw.settimeout(timeout)
        if tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(raw, server_hostname=host)
        line = _status_line(sock, host)
    except ssl.SSLError as e:
        return False, 'tls: %s' % str(e)[:80]
    except OSError as e:
        return False, 'io: %s' % str(e)[:80]
    finally:
        try:
            sock.close()
        except OSError:
            pass
    parts = line.split(' ', 2)
    code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
    if not code:
        return False, (line[:100] or 'no status')
    return code < 500, str(code)


def _targets(vhosts):
    out = []
    seen = set()
    for vh in vhosts:
        name = getattr(vh, 'name', '')
        if getattr(vh, 'suspended', False) or name in seen or not valid_host(name):
            continue
        seen.add(name)
        out.append((name, bool(getattr(vh, 'ssl_cert', ''))))
    out.sort()
    return out


def probe_all(vhosts, http_port=80, https_port=443, timeout=6.0, workers=24, budget=120.0):
    targets = _targets(vhosts)
    results = {}
    lock = threading.Lock()
    deadline = time.time() + budget
    idx = [0]

    def run():
        while True:
            with lock:
                if idx[0] >= len(targets) or time.time() > deadline:
                    return
                name, has_ssl = targets[idx[0]]
                idx[0] += 1
            r = {}
            r['http_ok'], r['http'] = probe(name, http_port, False, timeout)
            if has_ssl:
                r['https_ok'], r['https'] = probe(name, https_port, True, timeout)
                r['ok'] = r['http_ok'] and r['https_ok']
            else:
                r['ok'] = r['http_ok']
            with lock:
                results[name] = r

    n = min(workers, max(1, len(targets)))
    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    healthy = sum(1 for r in results.values() if r['ok'])
    return {
        'results': results,
        'total': len(targets),
        'probed': len(results),
        'healthy': healthy,
        'unhealthy': len(results) - healthy,
        'not_probed': len(targets) - len(results),
    }


def _reason(a):
    if not a.get('http_ok', True):
        return 'http %s' % a.get('http', '?')
    if a.get('https_ok') is False:
        return 'https %s' % a.get('https', '?')
    return 'failed'


def regressions(before, after):
    if not before:
        return []
    out = []
    bres = before.get('results', {})
    ares = after.get('results', {})
    for name in sorted(bres):
        if not bres[name].get('ok'):
            continue
        a = ares.get(name)
        if a is None:
            continue
        if not a.get('ok'):
            out.append({'name': name, 'after': _reason(a)})
    return out


def recheck(before, after, vhosts, http_port=80, https_port=443, timeout=6.0):
    regr = regressions(before, after)
    if not regr:
        return []
    time.sleep(2.0)
    names = {r['name'] for r in regr}
    retry = [vh for vh in vhosts if getattr(vh, 'name', '') in names]
    second = probe_all(retry, http_port, https_port, timeout=max(timeout, 10.0))
    still = []
    for r in regr:
        a = second['results'].get(r['name'])
        if a is None or not a.get('ok'):
            still.append({'name': r['name'], 'after': _reason(a) if a else r['after']})
    return still


def mass_failures(after, min_ratio=0.25, min_count=3):
    failed = [{'name': n, 'after': _reason(v)} for n, v in after.get('results', {}).items() if not v.get('ok')]
    probed = after.get('probed', 0)
    if probed and len(failed) >= min_count and len(failed) >= min_ratio * probed:
        return sorted(failed, key=lambda r: r['name'])
    return []
