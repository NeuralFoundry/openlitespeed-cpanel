import json
import os
import pwd
import subprocess
import sys

from . import wpcache


def me():
    pw = pwd.getpwuid(os.geteuid())
    return pw.pw_name, pw.pw_dir.rstrip('/')


def domains():
    p = subprocess.run(['/usr/bin/uapi', '--output=json', 'DomainInfo', 'domains_data'],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    data = json.loads(p.stdout.decode('utf-8', 'replace'))['result']['data']
    out = []
    main = data.get('main_domain') or {}
    if main:
        out.append(main)
    for k in ('addon_domains', 'sub_domains'):
        out.extend(data.get(k) or [])
    return [(d.get('servername') or d.get('domain'), d.get('documentroot'), d.get('php_version') or '') for d in out]


def sites():
    user, home = me()
    found = {}
    doms = sorted(domains(), key=lambda x: -len(x[1] or ''))
    for name, docroot, php in doms:
        if not docroot or not (docroot == home or docroot.startswith(home + '/')) or not os.path.isdir(docroot):
            continue
        for path in wpcache.find_in(docroot):
            if path in found:
                continue
            rel = os.path.relpath(path, docroot)
            found[path] = {'path': path, 'user': user, 'vhost': name, 'php': php,
                           'url': name + ('' if rel == '.' else '/' + rel)}
    for site in found.values():
        wpcache.refresh(site)
    return sorted(found.values(), key=lambda s: s['url'])


def find(path):
    for s in sites():
        if s['path'] == path:
            return s
    raise SystemExit('unknown site')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if os.geteuid() == 0:
        raise SystemExit('run as the cPanel user')
    cmd = argv[0] if argv else 'list'
    if cmd == 'list':
        print(json.dumps({'sites': sites()}))
    elif cmd in ('enable', 'disable') and len(argv) == 2:
        site = find(argv[1])
        ok = wpcache.enable(site) if cmd == 'enable' else wpcache.disable(site)
        print(json.dumps({'ok': ok, 'site': site}))
    else:
        raise SystemExit('usage: olscp-user list|enable PATH|disable PATH')
    return 0
