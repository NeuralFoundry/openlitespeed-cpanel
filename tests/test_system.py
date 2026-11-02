import io
import os
import shutil
import tarfile
import tempfile
import unittest

import helpers  # noqa: F401
from olscp import cloudlinux, olsbuild, update

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'build', 'prebuilt.txt')


class CloudLinuxTest(unittest.TestCase):
    def test_mode(self):
        none = {'cloudlinux': False, 'lve': False, 'cagefs': False}
        lve = {'cloudlinux': True, 'lve': True, 'cagefs': False}
        full = {'cloudlinux': True, 'lve': True, 'cagefs': True}
        cases = [
            ('auto', none, 'off'), ('cagefs', none, 'off'), ('auto', lve, 'lve'), ('cagefs', lve, 'lve'),
            ('auto', full, 'cagefs'), ('lve', full, 'lve'), ('off', full, 'off'),
        ]
        for setting, found, want in cases:
            self.assertEqual(cloudlinux.mode({'cloudlinux': setting}, found), want, (setting, found))
        self.assertEqual(cloudlinux.MODES['cagefs'], 2)

    def test_cagefs_config(self):
        text = cloudlinux.cagefs_config()
        self.assertTrue(text.startswith('[olscp]\n'))
        self.assertIn('/usr/local/olscp/ws/fcgi-bin/', text)
        self.assertIn('/usr/local/olscp/libexec/', text)


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='olscp-update-')
        self.saved = update.WORK
        update.WORK = self.dir

    def tearDown(self):
        update.WORK = self.saved
        shutil.rmtree(self.dir, ignore_errors=True)

    def tarball(self, members):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            for name, data, kind in members:
                ti = tarfile.TarInfo(name)
                ti.type = kind
                if kind == tarfile.DIRTYPE:
                    ti.mode = 0o755
                    tar.addfile(ti)
                elif kind == tarfile.SYMTYPE:
                    ti.linkname = data
                    tar.addfile(ti)
                else:
                    ti.size = len(data)
                    tar.addfile(ti, io.BytesIO(data))
        return buf.getvalue()

    def test_versions(self):
        self.assertGreater(update.version_tuple('v0.10.0'), update.version_tuple('0.9.9'))
        self.assertEqual(update.version_tuple('nope'), (0, 0, 0))
        self.assertTrue(update.TAG.match('v1.2.3'))
        self.assertFalse(update.TAG.match('v1.2.3-rc1'))

    def test_extract(self):
        blob = self.tarball([('olscp-1', None, tarfile.DIRTYPE), ('olscp-1/bin', None, tarfile.DIRTYPE),
                             ('olscp-1/VERSION', b'1\n', tarfile.REGTYPE), ('olscp-1/bin/x', b'#!', tarfile.REGTYPE)])
        dest = os.path.join(self.dir, 'out')
        os.makedirs(dest)
        src = update.extract(blob, dest, 'olscp-1')
        self.assertEqual(open(os.path.join(src, 'VERSION')).read(), '1\n')

    def test_extract_rejects_escape_and_links(self):
        for bad in ([('olscp-1/../evil', b'x', tarfile.REGTYPE)], [('other/x', b'x', tarfile.REGTYPE)],
                    [('olscp-1/link', '/etc/passwd', tarfile.SYMTYPE)]):
            with self.assertRaises(RuntimeError):
                update.extract(self.tarball(bad), self.dir, 'olscp-1')


class UserFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = os.path.realpath(tempfile.mkdtemp(prefix='olscp-userfile-'))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, text):
        p = os.path.join(self.dir, name)
        with open(p, 'w') as f:
            f.write(text)
        return p

    def test_regular_file_and_limits(self):
        from olscp import util
        p = self.write('a', 'Header set A b\n')
        self.assertEqual(util.read_user_file(p), 'Header set A b\n')
        self.assertEqual(util.read_user_file(p, limit=4), '')
        self.assertEqual(util.read_user_file(p, owners={os.stat(p).st_uid + 1}), '')
        self.assertEqual(util.read_user_file(os.path.join(self.dir, 'missing')), '')

    def test_symlinks_and_fifos_are_refused(self):
        from olscp import util
        target = self.write('secret', 'SetEnv PASSWORD x\n')
        link = os.path.join(self.dir, 'link')
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest('symlinks not available')
        self.assertEqual(util.read_user_file(link), '')
        sub = os.path.join(self.dir, 'sub')
        os.symlink(self.dir, sub)
        self.assertEqual(util.read_user_file(os.path.join(sub, 'secret')), '')
        if hasattr(os, 'mkfifo'):
            fifo = os.path.join(self.dir, 'fifo')
            os.mkfifo(fifo)
            self.assertEqual(util.read_user_file(fifo), '')

    @unittest.skipIf(os.name == 'nt', 'needs POSIX paths')
    def test_scan_keeps_files_of_truncated_roots(self):
        from olscp import htaccess
        a = os.path.join(self.dir, 'a')
        b = os.path.join(self.dir, 'b')
        for d in (a, b):
            os.makedirs(os.path.join(d, 'x', 'y'))
            self.write(os.path.join(d, 'x', '.htaccess'), 'Header set A b\n')
        os.makedirs(os.path.join(a, '.git'))
        self.write(os.path.join(a, '.git', '.htaccess'), 'Require all denied\n')
        saved = htaccess.STATE, htaccess.MAX_DIRS
        htaccess.STATE = os.path.join(self.dir, 'state.json')
        try:
            htaccess.save([os.path.join(b, 'old', '.htaccess')])
            files, partial = htaccess.scan([a, b], limit=2)
            self.assertEqual(sorted(partial), sorted([a, b]))
            htaccess.MAX_DIRS = 2
            files = htaccess.rescan([a, b])
            htaccess.MAX_DIRS = saved[1]
            self.assertIn(os.path.join(b, 'old', '.htaccess'), files)
            files, partial = htaccess.scan([a, b])
            self.assertEqual(partial, [])
            self.assertIn(os.path.join(a, '.git', '.htaccess'), files)
            htaccess.save([os.path.join(b, 'old', '.htaccess'), os.path.join(a, 'gone', '.htaccess')])
            files = htaccess.rescan([a, b], only=[a])
            self.assertIn(os.path.join(b, 'old', '.htaccess'), files)
            self.assertNotIn(os.path.join(a, 'gone', '.htaccess'), files)
            self.assertIn(os.path.join(a, 'x', '.htaccess'), files)
            self.assertEqual(htaccess.add_files([os.path.join(a, 'index.php')]), [])
        finally:
            htaccess.STATE, htaccess.MAX_DIRS = saved


class LogLineTest(unittest.TestCase):
    def test_line_parses_and_long_lines_are_cheap(self):
        import time
        from olscp import protect
        line = ('1.2.3.4 - - [02/Nov/2026:20:26:11 +0000] "POST /wp-login.php HTTP/1.1" 200 12 "-" '
                '"Mozilla/5.0 \\"x\\""')
        self.assertEqual(protect.LINE.match(line).groups()[:3], ('1.2.3.4', 'POST', '/wp-login.php'))
        evil = '1.2.3.4 - - [x] "GET /' + 'a' * 8000 + ' HTTP/1.1" 404 1 "a\\"b" "ua'
        t = time.time()
        protect.LINE.match(evil)
        self.assertLess(time.time() - t, 0.5)


class PrebuiltTest(unittest.TestCase):
    def test_manifest(self):
        saved = olsbuild.PREBUILT, olsbuild.platform
        olsbuild.PREBUILT = MANIFEST
        try:
            olsbuild.platform = lambda: ('el9', 'x86_64')
            item = olsbuild.prebuilt('1.9.4')
            self.assertEqual(item['platform'], 'el9')
            self.assertTrue(item['url'].endswith('-el9-x86_64.gz'))
            self.assertEqual(len(item['sha256']), 64)
            self.assertIsNone(olsbuild.prebuilt('1.8.0'))
            olsbuild.platform = lambda: ('el7', 'x86_64')
            self.assertIsNone(olsbuild.prebuilt('1.9.4'))
        finally:
            olsbuild.PREBUILT, olsbuild.platform = saved


if __name__ == '__main__':
    unittest.main()
