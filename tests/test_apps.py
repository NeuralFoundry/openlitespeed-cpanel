import os
import unittest

from helpers import Tree, apps, htaccess, render, render_vhost

CLOUDLINUX_NODE = '''# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION BEGIN
PassengerAppRoot "{root}"
PassengerBaseURI "/"
PassengerNodejs "{node}"
PassengerAppType node
PassengerStartupFile server.js
# DO NOT REMOVE. CLOUDLINUX PASSENGER CONFIGURATION END
# DO NOT REMOVE OR MODIFY. CLOUDLINUX ENV VARS CONFIGURATION BEGIN
<IfModule Litespeed>
SetEnv API_URL https://api.example.com
SetEnv LSNODE_ROOT /tmp
SetEnv LS_STDERR_LOG /tmp/x.log
SetEnv BROKEN "value {{"
</IfModule>
# DO NOT REMOVE OR MODIFY. CLOUDLINUX ENV VARS CONFIGURATION END
'''

CLOUDLINUX_PYTHON = '''PassengerAppRoot "{root}"
PassengerBaseURI "/shop"
PassengerPython "{python}"
'''

APP_MANAGER = '''<Location "/api">
    <IfModule mod_env.c>
        SetEnv "TOKEN" "abc"
    </IfModule>

    <IfModule mod_passenger.c>
        PassengerAppEnv "development"

        PassengerEnabled on
        PassengerBaseURI "/api"
        PassengerAppRoot "{root}"
        PassengerAppGroupName "alice - api"
        PassengerNodejs /opt/cpanel/ea-nodejs10/bin/node
    </IfModule>
</Location>
<Directory "{root}">
    Allow from all
    Options -MultiViews
    Options -Indexes
    Require all granted
</Directory>
'''


def kv(key, value):
    return '%-24s %s' % (key, value)


class AppsTest(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def resolve(self, vht, defaults=None):
        return apps.resolve_all(vht.app_specs, self.t.home, defaults)

    def test_cloudlinux_node(self):
        root = self.t.app('nodeapp', ['server.js', 'package.json'])
        self.t.htaccess('', CLOUDLINUX_NODE.format(root=root, node=self.t.node))
        found, issues = self.resolve(self.t.build())
        self.assertEqual(issues, [])
        self.assertEqual(len(found), 1)
        a = found[0]
        self.assertEqual(a['uri'], '/')
        self.assertEqual(a['type'], 'node')
        self.assertEqual(a['startup'], 'server.js')
        self.assertEqual(a['binary'], self.t.node)
        self.assertEqual(a['root'], root + '/')
        self.assertIn('API_URL=https://api.example.com', a['env'])
        self.assertIn('LS_STDERR_LOG=%s/stderr.log' % root, a['env'])
        self.assertFalse(any(e.startswith(('LSNODE_ROOT', 'BROKEN')) for e in a['env']))

    def test_cloudlinux_python_sub_uri(self):
        root = self.t.app('shop', ['passenger_wsgi.py'])
        os.makedirs(os.path.join(self.t.home, 'logs'))
        self.t.htaccess('shop', CLOUDLINUX_PYTHON.format(root=root, python=self.t.python) +
                        'PassengerAppLogFile "%s/logs/shop.log"\n' % self.t.home)
        found, issues = self.resolve(self.t.build())
        self.assertEqual(issues, [])
        a = found[0]
        self.assertEqual((a['uri'], a['type'], a['startup']), ('/shop/', 'wsgi', 'passenger_wsgi.py'))
        self.assertIn('OLSCP_APP_URI=/shop/', a['env'])
        self.assertIn('LS_STDERR_LOG=%s/logs/shop.log' % self.t.home, a['env'])
        self.assertEqual(apps.log_file('/etc/x.log', root, self.t.home), root + '/stderr.log')

    def test_nested_app_of_other_vhost_is_ignored(self):
        root = self.t.app('sub', ['passenger_wsgi.py'])
        self.t.htaccess('sub.example.com', 'PassengerAppRoot "%s"\nPassengerBaseURI "/"\nPassengerPython "%s"\n'
                        % (root, self.t.python))
        found, issues = self.resolve(self.t.build())
        self.assertEqual((found, issues), ([], []))

    def test_root_outside_home(self):
        self.t.htaccess('', 'PassengerAppRoot "/srv/app"\nPassengerAppType node\n')
        found, issues = self.resolve(self.t.build())
        self.assertEqual(found, [])
        self.assertIn('outside the home directory', issues[0])

    def test_application_manager_include(self):
        root = self.t.app('api', ['app.js'])
        vht = self.t.build([('api.conf', APP_MANAGER.format(root=root))])
        found, issues = self.resolve(vht, {'disable_htaccess': 'on'})
        self.assertEqual(issues, [])
        a = found[0]
        self.assertEqual((a['uri'], a['type'], a['mode'], a['env_mode']), ('/api/', 'node', 'development', 0))
        self.assertEqual(a['binary'], self.t.node)
        self.assertEqual(a['note'], 'instead of /opt/cpanel/ea-nodejs10/bin/node')
        self.assertIn('TOKEN=abc', a['env'])
        self.assertEqual(vht.report, [])

    def test_application_manager_python_with_all_binaries(self):
        root = self.t.app('shop', ['passenger_wsgi.py'])
        bogus = self.t.exe('python-html2text')
        text = APP_MANAGER.format(root=root).replace(
            'PassengerNodejs /opt/cpanel/ea-nodejs10/bin/node',
            'PassengerRuby /usr/bin/ruby\n        PassengerPython %s\n'
            '        PassengerNodejs %s' % (bogus, self.t.node))
        vht = self.t.build([('std/shop.conf', text), ('ssl/shop.conf', text)])
        found, issues = self.resolve(vht)
        self.assertEqual(issues, [])
        self.assertEqual([(a['uri'], a['type'], a['binary']) for a in found], [('/api/', 'wsgi', self.t.python)])

    def test_duplicate_includes_report_once(self):
        root = self.t.app('empty', [])
        text = APP_MANAGER.format(root=root)
        found, issues = self.resolve(self.t.build([('std/a.conf', text), ('ssl/a.conf', text)]))
        self.assertEqual((found, len(issues)), ([], 1))

    def test_binary_name_is_checked(self):
        root = self.t.app('api', ['app.js'])
        bogus = self.t.exe('python-html2text')
        text = APP_MANAGER.format(root=root).replace('PassengerNodejs /opt/cpanel/ea-nodejs10/bin/node',
                                                     'PassengerPython %s\n        PassengerAppType wsgi' % bogus)
        self.t.write(os.path.join(root, 'passenger_wsgi.py'), '')
        found, issues = self.resolve(self.t.build([('api.conf', text)]))
        self.assertEqual(issues, [])
        self.assertEqual(found[0]['binary'], self.t.python)

    def test_htaccess_disabled(self):
        root = self.t.app('nodeapp', ['server.js'])
        self.t.htaccess('', CLOUDLINUX_NODE.format(root=root, node=self.t.node))
        found, issues = self.resolve(self.t.build(), {'disable_htaccess': 'on'})
        self.assertEqual(found, [])
        self.assertIn('PassengerDisableHtaccess', issues[0])

    def test_disabled_and_unsupported(self):
        root = self.t.app('rb', ['config.ru'])
        self.t.htaccess('a', 'PassengerAppRoot "%s"\nPassengerEnabled off\n' % root)
        self.t.htaccess('b', 'PassengerAppRoot "%s"\nPassengerBaseURI "/b"\n' % root)
        self.t.htaccess('c', 'PassengerAppRoot "%s"\nPassengerAppType node\nPassengerStartupFile ../x.js\n' % root)
        found, issues = self.resolve(self.t.build())
        self.assertEqual(found, [])
        self.assertEqual(len(issues), 2)
        self.assertTrue(any('Ruby' in i for i in issues))
        self.assertTrue(any('startup file' in i for i in issues))

    def test_missing_startup_file(self):
        root = self.t.app('empty', ['package.json'])
        self.t.htaccess('', 'PassengerAppRoot "%s"\n' % root)
        found, issues = self.resolve(self.t.build())
        self.assertEqual(found, [])
        self.assertIn('app.js not found', issues[0])

    def test_render_node_app_with_policy(self):
        root = self.t.app('nodeapp', ['server.js'])
        self.t.htaccess('', CLOUDLINUX_NODE.format(root=root, node=self.t.node) + 'Require ip 10.0.0.0/8\n')
        os.makedirs(os.path.join(self.t.docroot, 'static'))
        conf = render_vhost(self.t, self.t.build())
        block = conf.split('context / {', 1)[1].split('\n}', 1)[0]
        for line in (kv('type', 'appserver'), kv('location', root + '/'), kv('binPath', self.t.node),
                     kv('startupFile', 'server.js'), kv('allow', '10.0.0.0/8'),
                     kv('env', 'API_URL=https://api.example.com')):
            self.assertIn(line, block)
        self.assertEqual(conf.count('context / {'), 1)
        self.assertIn('context %s {' % render.WELL_KNOWN, conf)
        self.assertIn('context /static/ {', conf)

    def test_render_python_app(self):
        root = self.t.app('shop', ['passenger_wsgi.py'])
        self.t.htaccess('shop', CLOUDLINUX_PYTHON.format(root=root, python=self.t.python))
        conf = render_vhost(self.t, self.t.build())
        block = conf.split('context /shop/ {', 1)[1].split('\n}', 1)[0]
        for line in (kv('binPath', '%s %s' % (self.t.python, self.t.lswsgi)), kv('appType', 'node'),
                     kv('maxConns', apps.WSGI_MAX_CONNS)):
            self.assertIn(line, block)
        self.assertNotIn('context %s' % render.WELL_KNOWN, conf)

    def test_app_context_does_not_inherit_rewrite(self):
        root = self.t.app('api', ['app.js'])
        self.t.htaccess('', 'RewriteEngine On\nRewriteRule . /index.php [L]\n')
        conf = render_vhost(self.t, self.t.build([('api.conf', APP_MANAGER.format(root=root))]))
        block = conf.split('context /api/ {', 1)[1].split('\n}', 1)[0]
        self.assertIn('rewrite {\n    ' + kv('enable', 0), block)

    def test_disabled_htaccess_ignores_other_vhost(self):
        root = self.t.app('sub', ['passenger_wsgi.py'])
        self.t.htaccess('sub.example.com', 'PassengerAppRoot "%s"\nPassengerBaseURI "/"\n' % root)
        self.assertEqual(self.resolve(self.t.build(), {'disable_htaccess': 'on'}), ([], []))

    def test_static_dirs_skip_app_inside_docroot(self):
        root = self.t.app('public_html/inner', ['server.js'])
        os.makedirs(os.path.join(root, 'node_modules'))
        self.t.htaccess('inner', 'PassengerAppRoot "%s"\nPassengerBaseURI "/inner"\nPassengerAppType node\n'
                        'PassengerStartupFile server.js\n' % root)
        found, _issues = self.resolve(self.t.build())
        self.assertEqual(apps.static_dirs(found[0], self.t.docroot), [])

    def test_static_dirs_stay_in_docroot(self):
        root = self.t.app('nodeapp', ['server.js'])
        found, _issues = apps.resolve_all([self.spec(root, '/elsewhere/')], self.t.home)
        os.makedirs(os.path.join(self.t.base, 'outside', 'secret'))
        try:
            os.symlink(os.path.join(self.t.base, 'outside'), os.path.join(self.t.docroot, 'elsewhere'))
        except (OSError, NotImplementedError):
            self.skipTest('symlinks not available')
        self.assertEqual(apps.static_dirs(found[0], self.t.docroot), [])

    def spec(self, root, uri):
        s = apps.Spec('test', uri)
        s.add('passengerapproot', [root])
        s.add('passengerapptype', ['node'])
        s.add('passengerstartupfile', ['server.js'])
        return s


class HtaccessTest(unittest.TestCase):
    def test_ssl_require_ssl(self):
        ht = htaccess.Parser('/x/.htaccess', 'SSLRequireSSL\n').parse()
        self.assertEqual(ht.scope.pre_rules, ['RewriteCond %{HTTPS} !on', 'RewriteRule .* - [F]'])
        self.assertEqual(ht.unsupported, [])

    def test_passenger_lines_are_not_reported(self):
        ht = htaccess.Parser('/x/.htaccess', 'PassengerAppRoot /home/a/app\nPassengerFriendlyErrorPages on\n').parse()
        self.assertEqual(ht.unsupported, [])
        self.assertEqual(len(ht.app['values']), 2)

    def test_setenv_in_files_is_reported(self):
        ht = htaccess.Parser('/x/.htaccess', '<Files "a.php">\nSetEnv A b\n</Files>\n').parse()
        self.assertIn('SetEnv', ht.unsupported)


class SyncTest(unittest.TestCase):
    def test_app_changes(self):
        from olscp import sync
        old = {'a.com': {'apps': [{'uri': '/'}]}, 'b.com': {'apps': [{'uri': '/x/'}]}, 'd.com': {'issues': ['x']}}
        new = {'a.com': {'apps': [{'uri': '/'}]}, 'c.com': {'apps': [{'uri': '/'}]}}
        self.assertEqual(sync.app_changes(old, new), ['b.com', 'c.com'])

    def test_app_updates(self):
        from olscp import sync
        a = {'uri': '/', 'root': '/home/a/app/', 'type': 'node', 'startup': 'app.js', 'binary': '/usr/bin/node',
             'mode': 'production', 'env': ['A=1']}
        old = {'a.com': {'user': 'a', 'apps': [a]}}
        same = {'a.com': {'user': 'a', 'apps': [dict(a)]}}
        mode = {'a.com': {'user': 'a', 'apps': [dict(a, mode='development')]}}
        self.assertEqual(sync.app_updates(old, same), [])
        self.assertEqual([(x['vhost'], x['user'], x['uri']) for x in sync.app_updates(old, mode)], [('a.com', 'a', '/')])
        self.assertEqual(sync.app_updates({}, mode), [])


if __name__ == '__main__':
    unittest.main()
