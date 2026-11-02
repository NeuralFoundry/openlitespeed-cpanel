import os
import shutil
import sys
import tempfile
import types

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))

from olscp import apps, htaccess, render  # noqa: E402


class Tree(object):
    def __init__(self):
        self.base = os.path.realpath(tempfile.mkdtemp(prefix='olscp-test-'))
        self.home = os.path.join(self.base, 'home', 'alice')
        self.docroot = os.path.join(self.home, 'public_html')
        os.makedirs(self.docroot)
        self.bin = os.path.join(self.base, 'bin')
        os.makedirs(self.bin)
        self.node = self.exe('node')
        self.python = self.exe('python3')
        self.ruby = self.exe('ruby')
        starters = os.path.join(self.base, 'fcgi-bin')
        os.makedirs(starters)
        for n in ('lsnode.js', 'lsnodesm.js'):
            self.write(os.path.join(starters, n), '')
        self.lswsgi = self.write(os.path.join(self.base, 'lswsgi.py'), '')
        self.lsrack = self.write(os.path.join(self.base, 'lsrack.rb'), '')
        self.saved = (apps.STARTERS, apps.LSWSGI, apps.LSRACK, apps.find_binary)
        apps.STARTERS = starters
        apps.LSWSGI = self.lswsgi
        apps.LSRACK = self.lsrack
        apps.find_binary = lambda kind: {'node': self.node, 'python': self.python, 'ruby': self.ruby}.get(kind, '')
        htaccess._present[:] = [htaccess.PRESENT_MODULES | {'passenger', 'env'}]

    def exe(self, name):
        p = self.write(os.path.join(self.bin, name), '#!/bin/sh\n')
        os.chmod(p, 0o755)
        return p

    def write(self, path, text):
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(path, 'w') as f:
            f.write(text)
        return path

    def app(self, name, files):
        root = os.path.join(self.home, name)
        for f in files:
            self.write(os.path.join(root, f), '')
        return root

    def htaccess(self, rel, text):
        return self.write(os.path.join(self.docroot, rel, '.htaccess'), text)

    def files(self):
        out = []
        for dp, _dn, fn in os.walk(self.docroot):
            out.extend(os.path.join(dp, f) for f in fn if f == '.htaccess')
        return sorted(out)

    def build(self, includes=None):
        return htaccess.build(self.docroot, self.files(), {}, None, includes or [])

    def close(self):
        apps.STARTERS, apps.LSWSGI, apps.LSRACK, apps.find_binary = self.saved
        htaccess._present[:] = []
        shutil.rmtree(self.base, ignore_errors=True)


def vhost(tree, name='example.com'):
    return types.SimpleNamespace(
        name=name, docroot=tree.docroot, homedir=tree.home, aliases=['www.' + name], admin_email='', user='alice',
        group='alice', php='ea-php83', fpm_socket='', lsphp='', domlog='/dev/null', byteslog='/dev/null',
        suspended=False, modsec_off=False, cgi=[], ssl_cert='', ssl_key='', ssl_chain='', custom_includes=[],
        custom_text=[])


def state():
    return types.SimpleNamespace(apache=None, apache_indexes=False, proxy_subdomains=False, autodiscover=False)


def render_vhost(tree, vht, settings=None):
    return render.render_vhost(vhost(tree), state(), settings or {'php_mode': 'auto', 'cache_module': False}, vht)
