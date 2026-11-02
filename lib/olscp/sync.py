import grp
import json
import os
import pwd
import shutil
import time

from . import cloudlinux, const, cpanel, htaccess, olsbuild, render, server, util


def active():
    return os.path.exists(const.ACTIVE_FLAG)


def write_status(data):
    old = {}
    try:
        with open(const.STATUS_FILE) as f:
            old = json.load(f)
    except (OSError, ValueError):
        pass
    old.update(data)
    util.write_atomic(const.STATUS_FILE, json.dumps(old, indent=2, sort_keys=True), 0o600)


def read_status():
    try:
        with open(const.STATUS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def restore(previous):
    owner = render.conf_owner()
    for path, content in previous.items():
        if content is None:
            try:
                os.unlink(path)
            except OSError:
                pass
        else:
            util.write_atomic(path, content, 0o640, owner)


def nobody():
    try:
        return pwd.getpwnam('nobody').pw_uid, grp.getgrnam('nobody').gr_gid
    except KeyError:
        return 99, 99


def prepare_cache(settings, vhosts):
    if not settings.get('cache_module', True):
        return
    root = settings.get('cache_root') or const.CACHE_ROOT
    uid, gid = nobody()
    os.makedirs(root, exist_ok=True)
    os.chown(root, uid, gid)
    os.chmod(root, 0o700)
    names = set()
    for vh in vhosts:
        names.add(vh.name)
        d = os.path.join(root, vh.name)
        if not os.path.isdir(d):
            os.makedirs(d)
            os.chown(d, uid, gid)
            os.chmod(d, 0o700)
    for n in os.listdir(root):
        p = os.path.join(root, n)
        if n not in names and os.path.isdir(p) and render.SAFE_NAME.match(n):
            shutil.rmtree(p, ignore_errors=True)


def prepare_modsec(settings):
    if not render.modsec_enabled(settings):
        return
    uid, gid = nobody()
    for p in (const.MODSEC_AUDIT, '/etc/apache2/logs/modsec_debug.log'):
        if not os.path.exists(p):
            open(p, 'a').close()
        st = os.stat(p)
        if st.st_gid != gid or (st.st_mode & 0o060) != 0o060:
            os.chown(p, 0, gid)
            os.chmod(p, 0o660)


def app_changes(old, new):
    def uris(d):
        return sorted(a['uri'] for a in (d or {}).get('apps', []))
    return sorted(v for v in set(old) | set(new) if render.SAFE_NAME.match(v) and uris(old.get(v)) != uris(new.get(v)))


APP_FIELDS = ('root', 'type', 'startup', 'binary', 'mode', 'env')


def app_updates(old, new):
    out = []
    for vhost, data in sorted(new.items()):
        before = {a['uri']: a for a in (old.get(vhost) or {}).get('apps', [])}
        for a in data.get('apps', []):
            b = before.get(a['uri'])
            if b and any(b.get(k) != a.get(k) for k in APP_FIELDS):
                out.append(dict(a, vhost=vhost, user=data.get('user', '')))
    return out


def config_errors(since):
    return [e for e in server.recent_errors(since) if '[ERROR]' in e and (
        '[PlainConf]' in e or 'Fatal error' in e or 'failed to start listener' in e)]


def sync(restart=False, reason='manual', force_restart=False, overrides=None):
    const.ensure_dirs()
    started = time.time()
    with util.Lock(const.SYNC_LOCK, timeout=180):
        state = cpanel.load_state()
        settings = util.load_settings()
        settings.update(overrides or {})
        ht_files = htaccess.load().get('files', [])
        live = olsbuild.live()
        files, info = render.render_all(state, settings, ht_files, live)
        old_apps = read_status().get('apps') or {}
        moved = app_changes(old_apps, info['apps'])
        updated = app_updates(old_apps, info['apps'])
        previous = {p: util.read_text(p) for p in files}
        if os.path.isdir(const.OLS_VHOST_DIR):
            for f in os.listdir(const.OLS_VHOST_DIR):
                if f.endswith('.conf'):
                    p = os.path.join(const.OLS_VHOST_DIR, f)
                    previous.setdefault(p, util.read_text(p))
        changed, removed = render.apply(files)
        flag = os.path.join(const.OLS_ROOT, 'admin/conf/enable_webadmin')
        if settings.get('webadmin_enabled') and not os.path.exists(flag):
            util.write_atomic(flag, '', 0o600, render.conf_owner())
            changed.append(flag)
        elif not settings.get('webadmin_enabled') and os.path.exists(flag):
            os.unlink(flag)
            removed.append(flag)
        try:
            prepare_cache(settings, state.vhosts)
            prepare_modsec(settings)
        except OSError as e:
            util.log('prepare failed: %s' % e, 'WARN')
        lve_mode = cloudlinux.mode(settings)
        old_lve = read_status().get('lve_mode', 'off')
        try:
            cloudlinux.sync_cagefs(lve_mode == 'cagefs')
        except OSError as e:
            util.log('CageFS configuration failed: %s' % e, 'WARN')
        try:
            from . import limits
            limits.apply(enabled=bool(settings.get('cgroups')) and lve_mode == 'off')
        except Exception as e:
            util.log('limits apply failed: %s' % e, 'WARN')
        did_restart = False
        ok = True
        errors = []
        full = False
        if restart and active() and server.running():
            full = server.needs_full_restart([files.get(const.OLS_CONF), files.get(const.OLS_ADMIN_CONF)])
        if (changed or removed or force_restart or full) and restart and active() and server.running():
            t0 = time.time()
            ok = server.full_restart() if full else server.graceful()
            did_restart = True
            time.sleep(0.5)
            bad = config_errors(t0)
            if not ok or not server.running() or bad:
                util.log('config rejected (%s), restoring previous config' % ('; '.join(bad)[:500] or 'restart failed'), 'ERROR')
                restore(previous)
                if server.running():
                    server.graceful()
                else:
                    server.start()
                    server.systemd_reattach()
                ok = False
            errors = server.recent_errors(t0)
        if lve_mode != old_lve and did_restart and ok and active():
            util.log('CloudLinux mode %s -> %s, restarted %d PHP and application processes' % (
                old_lve, lve_mode, cloudlinux.stop_workers()))
        if moved and settings.get('cache_module', True):
            from . import wpcache
            wpcache.purge(moved)
            util.log('cache purged after application change: %s' % ', '.join(moved))
        if updated:
            from . import apps
            for app in updated:
                try:
                    apps.stop(app)
                    util.log('application restarted after configuration change: %s%s' % (app['vhost'], app['uri']))
                except Exception as e:
                    util.log('application restart failed: %s' % e, 'WARN')
        result = {
            'time': int(time.time()),
            'reason': reason,
            'changed': len(changed),
            'removed': len(removed),
            'restarted': did_restart,
            'full_restart': full,
            'ok': ok,
            'vhosts': info['vhosts'],
            'skipped': info['skipped'],
            'duplicates': [list(d) for d in info['duplicates']],
            'warnings': state.warnings,
            'errors': [e for e in errors if 'smaller than minimum requirement' not in e],
            'digest': render.digest(files),
            'seconds': round(time.time() - started, 3),
            'htaccess_files': len(ht_files),
            'live_htaccess': live,
            'apache_vhosts': len([v for v in state.vhosts if v.source == 'apache']),
        }
        status = {'last_sync': result, 'htaccess_report': info['htaccess'], 'apache_report': apache_report(state),
                  'apps': info['apps']}
        if did_restart and ok or not active():
            status['lve_mode'] = lve_mode
        write_status(status)
        util.log('sync reason=%s changed=%d removed=%d restart=%s ok=%s' % (reason, len(changed), len(removed), did_restart, ok))
        return result


APACHE_KNOWN = {
    'servername', 'serveralias', 'documentroot', 'serveradmin', 'usecanonicalname', 'userdir', 'suexecusergroup',
    'scriptalias', 'alias', 'sslengine', 'sslcertificatefile', 'sslcertificatekeyfile', 'sslcertificatechainfile',
    'sslusestapling', 'ssloptions', 'rewriteengine', 'rewritecond', 'rewriterule', 'rewriteoptions', 'proxypass',
    'requestheader', 'header', 'customlog', 'bytes_log', 'errordocument', 'directory', 'filesmatch', 'files',
    'location', 'locationmatch', 'proxymatch', 'secruleengine', 'modsecurity_rules', 'sethandler', 'options',
    'allowoverride', 'require', 'order', 'allow', 'deny', 'satisfy', 'directoryindex', 'redirect', 'redirectmatch',
    'expiresactive', 'expiresbytype', 'expiresdefault', 'addtype', 'addhandler', 'ssilegacyexprparser',
}


def apache_report(state):
    info = state.apache
    if not info:
        return {}
    unsupported = []
    for vc in info['vhosts']:
        for c in vc.custom_nodes():
            if c.key not in APACHE_KNOWN and not c.key.startswith(('php_', 'suphp', 'passenger', 'ruid', 'rmode')):
                unsupported.append({'file': c.file, 'line': c.line, 'directive': c.name})
    return {
        'global': info['global'].as_dict(),
        'extra_vhosts': [{'name': v.name, 'docroot': v.docroot, 'user': v.user, 'ssl': bool(v.ssl_cert)}
                         for v in state.vhosts if v.source == 'apache'],
        'unsupported': unsupported[:200],
        'parsed_files': len(info['files']),
        'missing_includes': info['missing'][:50],
        'modules': info['modules'],
        'version': info['version'],
    }


def docroots():
    return [vh.docroot for vh in cpanel.load_state().vhosts]


def rescan_htaccess(restart=True, reason='htaccess-scan', roots=None):
    files = htaccess.rescan(docroots(), roots)
    return sync(restart=restart, reason=reason, force_restart=False), len(files)
