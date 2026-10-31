import os
import re

from . import const, cpanel, util


def versions():
    st = cpanel.load_state()
    counts = {}
    for vh in st.vhosts:
        counts[vh.php] = counts.get(vh.php, 0) + 1
    out = []
    for v in st.php_versions:
        lsphp = cpanel.lsphp_path(v)
        rc, ver = util.run([os.path.join(const.EA_PHP_ROOT, v, 'root/usr/bin/php'), '-r', 'echo PHP_VERSION;'], timeout=20)
        fpm_rc, fpm = util.run(['/usr/bin/systemctl', 'is-active', '%s-php-fpm' % v], timeout=20)
        out.append({'name': v, 'version': ver.strip() if rc == 0 else '', 'lsphp': bool(lsphp),
                    'fpm': fpm.strip(), 'sites': counts.get(v, 0), 'default': v == st.default_php})
    return {'versions': out, 'default': st.default_php}


def install_lsphp(name):
    if not re.match(r'^ea-php\d{2}$', name or ''):
        raise RuntimeError('bad version')
    rc, out = util.run(['/usr/bin/dnf', '-y', '-q', 'install', '%s-php-litespeed' % name], timeout=900)
    if rc != 0:
        raise RuntimeError(out.strip()[-1500:])
    util.log('installed %s-php-litespeed' % name)
    return {'installed': name}
