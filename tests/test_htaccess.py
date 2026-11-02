import os
import unittest

from helpers import Tree, render, state, vhost

ROCKET = r'''# BEGIN WP Rocket
<IfModule mod_headers.c>
Header unset ETag
</IfModule>
FileETag None
<IfModule mod_alias.c>
<FilesMatch "\.(css|js)$">
    <IfModule mod_headers.c>
        Header unset Pragma
        Header append Cache-Control "public"
    </IfModule>
</FilesMatch>
</IfModule>
<FilesMatch "\.(jpg|png)$">
    ExpiresActive On
    ExpiresDefault "access plus 1 year"
</FilesMatch>
# END WP Rocket
RewriteEngine On
RewriteBase /
RewriteRule ^index\.php$ - [L]
RewriteCond %{REQUEST_FILENAME} !-f
RewriteRule . /index.php [L]
'''

MULTIPHP = '''<IfModule mime_module>
  AddHandler application/x-httpd-%s .php .php7 .phtml
</IfModule>
'''


def kv(key, value):
    return '%-24s %s' % (key, value)


def block(conf, head):
    return conf.split('context %s {' % head, 1)[1].split('\n}', 1)[0]


class FilesHeadersTest(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def render(self, vh=None, settings=None):
        vh = vh or vhost(self.t)
        vht = render.htaccess.build(self.t.docroot, self.t.files(), {}, None, [], vh.php)
        conf = render.render_vhost(vh, state(), settings or {'cache_module': False}, vht)
        return conf, vht

    def test_header_only_files_match(self):
        self.t.htaccess('', ROCKET)
        self.t.htaccess('secret', 'Require ip 10.0.0.0/8\n')
        self.t.htaccess('off', 'Deny from all\n')
        conf, vht = self.render()
        self.assertEqual([r for r in vht.report if 'FilesMatch' in str(r)], [])
        css = r'exp:^/(?!cgi\-sys/|off/|secret/)(?:.*/)?[^/]*(?:\.(css|js)$)'
        body = block(conf, css)
        for line in ('Header unset ETag', 'Header unset Pragma', 'Header append Cache-Control public',
                     'RewriteBase /', 'RewriteRule . /index.php [L]', kv('enable', 1)):
            self.assertIn(line, body)
        self.assertNotIn('location', body)
        img = block(conf, r'exp:^/(?!cgi\-sys/|off/|secret/)(?:.*/)?[^/]*(?:\.(jpg|png)$)')
        self.assertIn(kv('enableExpires', 1), img)
        self.assertIn(kv('expiresDefault', 'A31536000'), img)
        secret = block(conf, r'exp:^/secret/(?:.*/)?[^/]*(?:\.(css|js)$)')
        self.assertIn(kv('allow', '10.0.0.0/8'), secret)
        self.assertIn('RewriteBase /', secret)
        self.assertNotIn('context exp:^/off/', conf)
        denied = conf.index(r'context exp:^/(?:.*/)?(?:(\.ht')
        self.assertLess(denied, conf.index('context ' + css))

    def test_rewrite_base_mismatch_is_reported(self):
        self.t.htaccess('blog', ROCKET)
        conf, vht = self.render()
        self.assertNotIn('context exp:^/blog/', conf)
        self.assertTrue(any('RewriteBase' in i for _p, issues in vht.report for i in issues))

    def test_files_match_with_other_directives_is_reported(self):
        self.t.htaccess('', '<FilesMatch "\\.css$">\nHeader set A b\nAddType text/x-a .css\n</FilesMatch>\n')
        conf, vht = self.render()
        self.assertNotIn('Header set A b', conf)
        self.assertTrue(any('FilesMatch' in i for _p, issues in vht.report for i in issues))


class ReviewFixesTest(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def render(self, includes=None):
        vh = vhost(self.t)
        vht = render.htaccess.build(self.t.docroot, self.t.files(), {}, None, includes or [], vh.php)
        return render.render_vhost(vh, state(), {'cache_module': False}, vht), vht

    def test_block_values_cannot_break_out(self):
        b = render.Block()
        c = b.block('context /a\n}\ncontext /x/ {')
        c.kv('location', '/home/a/\nallowBrowse 1\\')
        c.heredoc('rules', ['RewriteRule a b', 'END_rules', 'x\ny'])
        text = b.render()
        self.assertEqual(len([l for l in text.splitlines() if l.rstrip().endswith('{')]), 1)
        self.assertEqual(len([l for l in text.splitlines() if l.strip() == '}']), 1)
        self.assertEqual(text.count('\nEND_rules'), 1)
        self.assertIn('location                 /home/a/ allowBrowse 1\n', text)
        self.assertFalse(render.htaccess.safe_path('/home/a/x\n}/.htaccess'))
        self.assertTrue(render.htaccess.safe_path('/home/a/x y/.htaccess'))

    def test_location_rules_are_not_bypassed(self):
        self.t.htaccess('', '<FilesMatch "\\.(css|js)$">\nHeader set A b\n</FilesMatch>\n')
        conf, _vht = self.render([('admin.conf', '<Location /admin>\nRequire ip 10.0.0.0/8\n</Location>\n')])
        self.assertIn(r'context exp:^/(?!admin|cgi\-sys/)(?:.*/)?[^/]*(?:\.(css|js)$) {', conf)

    def test_long_lookahead_is_reported(self):
        self.t.htaccess('', '<FilesMatch "\\.css$">\nHeader set A b\n</FilesMatch>\n')
        for i in range(60):
            self.t.htaccess('d%02d' % i + 'x' * 77, 'Header set B c\n')
        conf, vht = self.render()
        self.assertNotIn('context exp:^/(?!', conf)
        self.assertIn('context exp:^/d00', conf)
        self.assertTrue(any('too many subdirectories' in i for _p, issues in vht.report for i in issues))
        self.assertTrue(all(len(l) <= render.MAX_LINE for l in conf.splitlines()))

    def test_overlapping_blocks_are_merged(self):
        self.t.htaccess('', '<FilesMatch "\\.(woff|css)$">\nHeader set Access-Control-Allow-Origin "*"\n</FilesMatch>\n'
                            '<FilesMatch "\\.(css|js)$">\nHeader append Cache-Control public\n</FilesMatch>\n')
        self.t.htaccess('sub', '<FilesMatch "\\.js$">\nHeader set X-Sub 1\n</FilesMatch>\n')
        conf, _vht = self.render()
        css = block(conf, r'exp:^/(?!cgi\-sys/|sub/)(?:.*/)?[^/]*(?:\.(css)$)')
        self.assertLess(css.index('Access-Control-Allow-Origin'), css.index('Cache-Control'))
        woff = block(conf, r'exp:^/(?!cgi\-sys/|sub/)(?:.*/)?[^/]*(?:\.(woff)$)')
        self.assertNotIn('Cache-Control', woff)
        js = block(conf, r'exp:^/sub/(?:.*/)?[^/]*(?:\.(js)$)')
        self.assertLess(js.index('Cache-Control'), js.index('X-Sub'))

    def test_rewrite_off_is_kept(self):
        self.t.htaccess('', ROCKET)
        self.t.htaccess('static', 'RewriteEngine Off\n')
        conf, _vht = self.render()
        body = block(conf, r'exp:^/static/(?:.*/)?[^/]*(?:\.(css|js)$)')
        self.assertIn(kv('enable', 0), body)
        self.assertNotIn('RewriteRule', body)

    def test_php_admin_values_are_refused(self):
        self.t.htaccess('', 'php_admin_value open_basedir none\nphp_value memory_limit 256M\n')
        vht = render.htaccess.build(self.t.docroot, self.t.files(), {}, None, [], 'ea-php83')
        self.assertEqual(vht.php_root, ['php_value memory_limit 256M'])
        self.assertTrue(any('php_admin_value' in i for _p, issues in vht.report for i in issues))

    def test_files_match_with_dropped_directives_is_reported(self):
        self.t.htaccess('', '<FilesMatch "\\.(php)$">\nHeader set A b\nSetHandler none\n</FilesMatch>\n')
        conf, vht = self.render()
        self.assertNotIn('Header set A b', conf)
        self.assertTrue(any('FilesMatch' in i for _p, issues in vht.report for i in issues))


class PhpHandlerTest(unittest.TestCase):
    def setUp(self):
        self.t = Tree()
        self.saved = render.ver_lsphp
        render.ver_lsphp = lambda ver: '/opt/cpanel/%s/root/usr/bin/lsphp' % ver if ver != 'ea-php56' else ''

    def tearDown(self):
        render.ver_lsphp = self.saved
        self.t.close()

    def vhost(self):
        vh = vhost(self.t)
        vh.lsphp = '/opt/cpanel/ea-php83/root/usr/bin/lsphp'
        return vh

    def render(self, vh=None, mode='lsapi'):
        vh = vh or self.vhost()
        vht = render.htaccess.build(self.t.docroot, self.t.files(), {}, None, [], vh.php)
        conf = render.render_vhost(vh, state(), {'php_mode': mode, 'cache_module': False},
                                   vht)
        return conf, vht

    def test_subdirectory_version(self):
        self.t.htaccess('', MULTIPHP % 'ea-php83')
        self.t.htaccess('old', MULTIPHP % 'ea-php74')
        self.t.htaccess('old/inner', 'Header set A b\n')
        self.t.htaccess('old/back', MULTIPHP % 'ea-php83')
        self.t.htaccess('same', MULTIPHP % 'ea-php83')
        conf, vht = self.render()
        self.assertIn(kv('addMIMEType', 'application/x-httpd-php php php7 phtml'), block(conf, '/old/back/'))
        self.assertNotIn('context /same/', conf)
        self.assertEqual(vht.php_versions, {'ea-php74'})
        self.assertIn(kv('add', 'lsapi:%s olscp-ea-php74' % render.lsphp_name('alice', 'ea-php74')), conf)
        for ctx in ('/old/', '/old/inner/'):
            self.assertIn(kv('addMIMEType', 'application/x-httpd-olscp-ea-php74 php php7 phtml'), block(conf, ctx))
        self.assertNotIn('context / {', conf)

    def test_same_version_at_root_adds_nothing(self):
        self.t.htaccess('', MULTIPHP % 'ea-php83' + 'RewriteEngine On\nRewriteRule . /index.php [L]\n')
        conf, vht = self.render()
        self.assertEqual(vht.php_versions, set())
        self.assertNotIn('addMIMEType', conf)
        self.assertNotIn('context / {', conf)

    def test_root_extra_suffix(self):
        self.t.htaccess('', 'AddHandler application/x-httpd-ea-php83___lsphp .php .html\n')
        conf, _vht = self.render()
        self.assertIn(kv('addMIMEType', 'application/x-httpd-php php html'), block(conf, '/'))

    def test_missing_lsphp_and_fpm_are_reported(self):
        self.t.htaccess('a', MULTIPHP % 'ea-php56')
        conf, vht = self.render()
        self.assertNotIn('addMIMEType', conf)
        self.assertTrue(any('LSAPI for ea-php56' in i for _p, issues in vht.report for i in issues))
        vh = self.vhost()
        vh.fpm_socket = '/run/x.sock'
        self.t.htaccess('a', MULTIPHP % 'ea-php74')
        conf, vht = self.render(vh, 'auto')
        self.assertNotIn('addMIMEType', conf)
        self.assertTrue(any('LSAPI PHP mode' in i for _p, issues in vht.report for i in issues))


if __name__ == '__main__':
    unittest.main()
