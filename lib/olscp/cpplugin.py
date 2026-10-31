import os
import shutil
import tarfile
import tempfile

from . import const, util

SRC = const.BASE + '/cpanel'
THEME = 'jupiter'
PAGE_DIR = '/usr/local/cpanel/base/frontend/%s/olscp_cache' % THEME
ADMIN_DIR = '/usr/local/cpanel/bin/admin/Olscp'
FLAG = const.ETC + '/cpanel_plugin'


def installed():
    return os.path.exists(FLAG) and os.path.isfile(os.path.join(PAGE_DIR, 'index.live.pl'))


def _archive(tmp):
    path = os.path.join(tmp, 'olscp_cache.tar.gz')
    with tarfile.open(path, 'w:gz') as tar:
        tar.add(os.path.join(SRC, 'install.json'), arcname='install.json')
        tar.add(const.BASE + '/whm/olscp.png', arcname='olscp_cache.png')
    return path


def install():
    os.makedirs(PAGE_DIR, exist_ok=True)
    os.chmod(PAGE_DIR, 0o755)
    dst = os.path.join(PAGE_DIR, 'index.live.pl')
    shutil.copy2(os.path.join(SRC, 'olscp_cache/index.live.pl'), dst)
    os.chown(dst, 0, 0)
    os.chmod(dst, 0o755)
    os.makedirs(ADMIN_DIR, exist_ok=True)
    os.chmod(ADMIN_DIR, 0o755)
    for name, mode in (('Cache', 0o700), ('Cache.conf', 0o644)):
        p = os.path.join(ADMIN_DIR, name)
        shutil.copy2(os.path.join(SRC, 'adminbin/Olscp', name), p)
        os.chown(p, 0, 0)
        os.chmod(p, mode)
    if os.path.exists(const.WP_CLI):
        os.chmod(const.WP_CLI, 0o755)
    tmp = tempfile.mkdtemp(prefix='olscp-plugin-')
    try:
        rc, out = util.run(['/usr/local/cpanel/scripts/install_plugin', _archive(tmp), '--theme', THEME], timeout=300)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if rc != 0:
        raise RuntimeError(out[-1500:])
    open(FLAG, 'w').close()
    util.log('cpanel plugin installed')
    return ['installed']


def uninstall():
    tmp = tempfile.mkdtemp(prefix='olscp-plugin-')
    try:
        rc, out = util.run(['/usr/local/cpanel/scripts/uninstall_plugin', _archive(tmp), '--theme', THEME], timeout=300)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(PAGE_DIR, ignore_errors=True)
    shutil.rmtree(ADMIN_DIR, ignore_errors=True)
    try:
        os.unlink(FLAG)
    except OSError:
        pass
    util.log('cpanel plugin removed rc=%d' % rc)
    return ['removed']
