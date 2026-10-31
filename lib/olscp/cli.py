import argparse
import grp
import json
import os
import pwd
import sys

from . import VERSION, const, cpanel, server, switch, sync, util


def out(data, as_json):
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True, default=str))
    elif isinstance(data, (list, tuple)):
        for x in data:
            print(x)
    elif isinstance(data, dict):
        for k in sorted(data):
            print('%s: %s' % (k, data[k]))
    else:
        print(data)


def cmd_httpd(args):
    action = args.action
    if not sync.active():
        os.execv(const.HTTPD_REAL, [const.HTTPD, '-k', action])
    if action == 'start':
        try:
            sync.sync(restart=False, reason='httpd-start')
        except Exception as e:
            util.log('sync before start failed: %s' % e, 'ERROR')
        return 0 if server.start() else 1
    if action in ('restart', 'graceful'):
        try:
            sync.sync(restart=False, reason='httpd-' + action)
        except Exception as e:
            util.log('sync before %s failed: %s' % (action, e), 'ERROR')
        ok = server.graceful() if server.running() else server.start()
        return 0 if ok else 1
    if action in ('stop', 'graceful-stop'):
        server.stop()
        return 0
    return 1


def cmd_vhosts(args):
    st = cpanel.load_state()
    settings = util.load_settings()
    report = sync.read_status().get('htaccess_report', {})
    rows = []
    for vh in st.vhosts:
        if vh.fpm_socket and settings.get('php_mode') in ('auto', 'fpm'):
            mode = 'fpm'
        elif vh.lsphp:
            mode = 'lsapi'
        else:
            mode = 'none'
        rows.append({
            'name': vh.name, 'user': vh.user, 'docroot': vh.docroot, 'aliases': vh.aliases,
            'php': vh.php, 'php_mode': mode, 'ssl': bool(vh.ssl_cert), 'suspended': vh.suspended,
            'custom_includes': vh.custom_includes, 'modsec_off': vh.modsec_off, 'source': vh.source,
            'htaccess_issues': len(report.get(vh.name, [])),
        })
    if args.json:
        out({'vhosts': rows, 'hostname': st.hostname, 'warnings': st.warnings,
             'php_versions': st.php_versions, 'default_php': st.default_php}, True)
    else:
        for r in rows:
            print('%-40s %-12s %-9s %-6s ssl=%s%s' % (r['name'], r['user'], r['php'], r['php_mode'],
                                                       'y' if r['ssl'] else 'n', ' SUSPENDED' if r['suspended'] else ''))


def parse_value(k, v):
    d = const.DEFAULT_SETTINGS[k]
    if isinstance(d, bool):
        return v.lower() in ('1', 'true', 'yes', 'on')
    if isinstance(d, int):
        return int(v)
    return v


def cmd_settings(args):
    if args.set:
        vals = {}
        for item in args.set:
            if '=' not in item:
                raise RuntimeError('bad setting: %s' % item)
            k, v = item.split('=', 1)
            if k not in const.DEFAULT_SETTINGS:
                raise RuntimeError('unknown setting: %s' % k)
            vals[k] = parse_value(k, v)
        s = util.save_settings(vals)
        if args.apply:
            sync.sync(restart=True, reason='settings', force_restart=True)
        out(s, args.json)
    else:
        out(util.load_settings(), args.json)


def cmd_logs(args):
    text = util.read_text(const.LOG, '') or ''
    lines = text.splitlines()[-args.lines:]
    err = (util.read_text(const.APACHE_ERROR_LOG, '') or '')[-300000:].splitlines()
    ols = [l for l in err if '] [' in l and l[:4].isdigit()][-args.lines:]
    out({'olscp': lines, 'server': ols}, args.json)


def lsadm():
    try:
        return pwd.getpwnam('lsadm').pw_uid, grp.getgrnam('lsadm').gr_gid
    except KeyError:
        return None


def cmd_webadmin(args):
    if args.reset_password:
        pw = util.run(['/usr/bin/openssl', 'rand', '-base64', '18'])[1].strip().replace('/', 'x').replace('+', 'y')[:20]
        rc, enc = util.run([const.OLS_ROOT + '/admin/fcgi-bin/admin_php', '-q',
                            const.OLS_ROOT + '/admin/misc/htpasswd.php', pw])
        if rc != 0:
            raise RuntimeError('password hash failed')
        util.write_atomic(const.OLS_ROOT + '/admin/conf/htpasswd', 'admin:%s\n' % enc.strip(), 0o600, lsadm())
        out({'user': 'admin', 'password': pw, 'listen': util.load_settings().get('webadmin_listen')}, args.json)
    else:
        out({'user': 'admin', 'listen': util.load_settings().get('webadmin_listen')}, args.json)


def cmd_preview(args):
    if args.action == 'start':
        if sync.active():
            raise RuntimeError('OpenLiteSpeed is already the active web server')
        res = sync.sync(restart=False, reason='preview', overrides={'port_offset': args.offset})
        ok = server.graceful(pidfile=server.PREVIEW_PID) if server.running(server.PREVIEW_PID) else server.start(pidfile=server.PREVIEW_PID)
        out({'ok': ok, 'http': 80 + args.offset, 'https': 443 + args.offset, 'vhosts': res['vhosts'],
             'errors': server.recent_errors(res['time'] - 2)}, args.json)
    elif args.action == 'stop':
        server.stop(pidfile=server.PREVIEW_PID)
        sync.sync(restart=False, reason='preview-stop')
        out({'ok': True}, args.json)
    else:
        out({'running': server.running(server.PREVIEW_PID), 'pid': server.main_pid(server.PREVIEW_PID)}, args.json)


def cmd_htaccess(args):
    if args.action == 'scan':
        res, n = sync.rescan_htaccess(restart=True)
        out({'files': n, 'sync': res}, args.json)
    else:
        st = sync.read_status()
        from . import htaccess
        out({'report': st.get('htaccess_report', {}), 'files': len(htaccess.load().get('files', [])),
             'scanned': htaccess.load().get('time', 0)}, args.json)


def cmd_cache(args):
    from . import wpcache
    a = args.action
    settings = util.load_settings()
    version = args.version or settings.get('lscwp_version') or 'latest'
    if a == 'list':
        data = wpcache.load()
        out({'sites': sorted(data.get('sites', {}).values(), key=lambda s: s['url']), 'scanned': data.get('time', 0),
             'job': wpcache.job_status(), 'usage': wpcache.cache_usage(), 'version': settings.get('lscwp_version')}, args.json)
    elif a in ('scan', 'scan-new'):
        data = wpcache.scan(only_new=(a == 'scan-new'))
        out({'sites': len(data['sites'])}, args.json)
    elif a == 'job':
        out(wpcache.run_job(args.job, args.path or None, version), args.json)
    elif a == 'start':
        wpcache.start_job(args.job, args.path or None, version)
        out({'started': args.job}, args.json)
    elif a == 'status':
        out(wpcache.job_status(), args.json)
    elif a in ('flag', 'unflag'):
        wpcache.set_flag(args.path, a == 'flag')
        out({'ok': True}, args.json)
    elif a == 'purge':
        state = cpanel.load_state()
        names = {vh.name for vh in state.vhosts}
        if args.all:
            targets = sorted(names)
        else:
            targets = [v for v in args.vhost if v in names]
            if args.user:
                own = {vh.name for vh in state.vhosts if vh.user == args.user}
                if any(v not in own for v in targets):
                    raise RuntimeError('domain does not belong to %s' % args.user)
        if not targets:
            raise RuntimeError('no matching domain')
        out({'purged': targets, 'entries': wpcache.purge(targets)}, args.json)
    elif a == 'quic':
        out(wpcache.quic_ips(refresh_now=args.all), args.json)
    else:
        raise RuntimeError('unknown cache action')


def cmd_stats(args):
    from . import stats
    out(stats.read(), args.json)


def cmd_limits(args):
    from . import limits
    if args.action == 'show':
        out(limits.status(), args.json)
    elif args.action == 'set':
        vals = {'cpu': args.cpu, 'mem': args.mem, 'tasks': args.tasks, 'io': args.io}
        limits.set_limits(args.scope, args.name, vals)
        res = limits.apply(enabled=bool(util.load_settings().get('cgroups')))
        out(res, args.json)
    else:
        out(limits.apply(enabled=bool(util.load_settings().get('cgroups')), force=True), args.json)


def cmd_blocked(args):
    from . import protect
    if args.action == 'list':
        data = protect.load_blocked()
        out({'blocked': [dict(ip=ip, **v) for ip, v in sorted(data.items())]}, args.json)
    else:
        protect.unblock(None if args.action == 'clear' else args.ip)
        res = sync.sync(restart=True, reason='unblock')
        out({'ok': res['ok']}, args.json)


def cmd_php(args):
    from . import phpver
    if args.action == 'list':
        out(phpver.versions(), args.json)
    else:
        res = phpver.install_lsphp(args.name)
        sync.sync(restart=True, reason='php-install', force_restart=True)
        out(res, args.json)


def cmd_ols(args):
    from . import olsbuild, olsver
    if args.action == 'versions':
        data = olsver.info()
        data['build'] = olsbuild.info()
        out(data, args.json)
    elif args.action == 'upgrade':
        out(olsver.upgrade(args.version, args.rpm), args.json)
    elif args.action == 'build':
        out(olsbuild.start_build(), args.json)
    elif args.action == 'build-run':
        out(olsbuild.run_build(), args.json)
    elif args.action == 'build-status':
        out(olsbuild.info(), args.json)
    elif args.action == 'use':
        out(olsbuild.use(args.which), args.json)


def cmd_apache(args):
    st = cpanel.load_state()
    out(sync.apache_report(st), args.json)


def cmd_cpanel_plugin(args):
    from . import cpplugin
    if args.action == 'install':
        out(cpplugin.install(), args.json)
    elif args.action == 'uninstall':
        out(cpplugin.uninstall(), args.json)
    else:
        out({'installed': cpplugin.installed()}, args.json)


def cmd_modsec(args):
    from . import render
    settings = util.load_settings()
    out({'available': render.modsec_available(), 'enabled': render.modsec_enabled(settings),
         'setting': settings.get('modsecurity'), 'rules': render.MODSEC_RULES,
         'off_domains': [vh.name for vh in cpanel.load_state().vhosts if vh.modsec_off]}, args.json)


def main(argv=None):
    p = argparse.ArgumentParser(prog='olscp')
    p.add_argument('--json', action='store_true')
    sp = p.add_subparsers(dest='cmd')
    sp.add_parser('version')
    sp.add_parser('status')
    s = sp.add_parser('sync')
    s.add_argument('--restart', action='store_true')
    h = sp.add_parser('httpd')
    h.add_argument('action', choices=['start', 'restart', 'graceful', 'stop', 'graceful-stop'])
    for name in ('enable', 'disable', 'reapply', 'watch', 'vhosts', 'restart'):
        sp.add_parser(name)
    st = sp.add_parser('settings')
    st.add_argument('set', nargs='*')
    st.add_argument('--apply', action='store_true')
    lg = sp.add_parser('logs')
    lg.add_argument('--lines', type=int, default=100)
    wa = sp.add_parser('webadmin')
    wa.add_argument('--reset-password', action='store_true')
    pv = sp.add_parser('preview')
    pv.add_argument('action', choices=['start', 'stop', 'status'])
    pv.add_argument('--offset', type=int, default=8000)
    ht = sp.add_parser('htaccess')
    ht.add_argument('action', choices=['scan', 'report'])
    ca = sp.add_parser('cache')
    ca.add_argument('action', choices=['list', 'scan', 'scan-new', 'job', 'start', 'status', 'flag', 'unflag', 'purge', 'quic'])
    ca.add_argument('job', nargs='?', choices=['mass-enable', 'mass-disable', 'enable', 'disable', 'refresh', 'force-version'])
    ca.add_argument('--path', action='append', default=[])
    ca.add_argument('--vhost', action='append', default=[])
    ca.add_argument('--user')
    ca.add_argument('--all', action='store_true')
    ca.add_argument('--version')
    ov = sp.add_parser('ols')
    ov.add_argument('action', choices=['versions', 'upgrade', 'build', 'build-run', 'build-status', 'use'])
    ov.add_argument('which', nargs='?', choices=['olscp', 'official'])
    ov.add_argument('--version')
    ov.add_argument('--rpm')
    ap = sp.add_parser('apache')
    ap.add_argument('action', choices=['report'])
    cp = sp.add_parser('cpanel-plugin')
    cp.add_argument('action', choices=['install', 'uninstall', 'status'])
    sp.add_parser('modsec')
    sp.add_parser('stats')
    li = sp.add_parser('limits')
    li.add_argument('action', choices=['show', 'set', 'apply'])
    li.add_argument('--scope', choices=['default', 'package', 'user'], default='default')
    li.add_argument('--name')
    for k in ('cpu', 'mem', 'tasks', 'io'):
        li.add_argument('--' + k)
    bl = sp.add_parser('blocked')
    bl.add_argument('action', choices=['list', 'unblock', 'clear'])
    bl.add_argument('ip', nargs='*')
    ph = sp.add_parser('php')
    ph.add_argument('action', choices=['list', 'install'])
    ph.add_argument('name', nargs='?')
    args = p.parse_args(argv)
    if os.geteuid() != 0:
        raise SystemExit('olscp must run as root')

    try:
        if args.cmd == 'version':
            out({'olscp': VERSION, 'openlitespeed': server.version()}, args.json)
        elif args.cmd == 'status':
            out(switch.status(), args.json)
        elif args.cmd == 'sync':
            out(sync.sync(restart=args.restart, reason='cli', force_restart=False), args.json)
        elif args.cmd == 'httpd':
            return cmd_httpd(args)
        elif args.cmd == 'enable':
            out(switch.enable(), args.json)
        elif args.cmd == 'disable':
            out(switch.disable(), args.json)
        elif args.cmd == 'reapply':
            out(switch.reapply(), args.json)
        elif args.cmd == 'watch':
            from . import watch
            watch.main()
        elif args.cmd == 'vhosts':
            cmd_vhosts(args)
        elif args.cmd == 'restart':
            if not server.running():
                raise RuntimeError('OpenLiteSpeed is not running')
            res = sync.sync(restart=True, reason='restart', force_restart=True)
            out({'ok': res['ok'], 'full_restart': res.get('full_restart', False)}, args.json)
        elif args.cmd == 'settings':
            cmd_settings(args)
        elif args.cmd == 'logs':
            cmd_logs(args)
        elif args.cmd == 'webadmin':
            cmd_webadmin(args)
        elif args.cmd == 'preview':
            cmd_preview(args)
        elif args.cmd == 'htaccess':
            cmd_htaccess(args)
        elif args.cmd == 'cache':
            cmd_cache(args)
        elif args.cmd == 'ols':
            cmd_ols(args)
        elif args.cmd == 'apache':
            cmd_apache(args)
        elif args.cmd == 'cpanel-plugin':
            cmd_cpanel_plugin(args)
        elif args.cmd == 'modsec':
            cmd_modsec(args)
        elif args.cmd == 'stats':
            cmd_stats(args)
        elif args.cmd == 'limits':
            cmd_limits(args)
        elif args.cmd == 'php':
            cmd_php(args)
        elif args.cmd == 'blocked':
            cmd_blocked(args)
        else:
            p.print_help()
            return 2
    except Exception as e:
        util.log('%s failed: %s' % (args.cmd, e), 'ERROR')
        if args.json:
            print(json.dumps({'error': str(e)}))
        else:
            print('ERROR: %s' % e, file=sys.stderr)
        return 1
    return 0
