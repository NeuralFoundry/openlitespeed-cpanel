import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))

from olscp import apacheconf, htaccess, render  # noqa: E402


class LsapiModules(unittest.TestCase):
    def setUp(self):
        self.saved = apacheconf.present_modules
        apacheconf.present_modules = lambda: {'rewrite', 'headers', 'mime'}
        htaccess.reset_modules()

    def tearDown(self):
        apacheconf.present_modules = self.saved
        htaccess.reset_modules()

    def test_lsapi_blocks_apply_with_real_module_list(self):
        self.assertTrue(htaccess.module_present('lsapi_module'))
        self.assertTrue(htaccess.module_present('mod_lsapi.c'))
        self.assertFalse(htaccess.module_present('!lsapi_module'))
        self.assertFalse(htaccess.module_present('php8_module'))
        self.assertTrue(htaccess.module_present('rewrite_module'))


class LsphpProcessor(unittest.TestCase):
    def test_user_ini_enabled(self):
        root = render.Block()
        render.lsphp_processor(root, 'lsphp-alice-82', 'alice', 'alice', '/opt/php/lsphp', {})
        self.assertIn('LSPHP_ENABLE_USER_INI=on', root.render())


class PhpProcessorChange(unittest.TestCase):
    def test_only_lsphp_blocks_are_compared(self):
        try:
            from olscp import sync
        except ImportError:
            self.skipTest('sync needs a Linux system')
        old = 'listener a {\n  map x\n}\nextprocessor lsphp-a {\n  env A=1\n}\n'
        self.assertEqual(sync.php_processors(old), sync.php_processors(old.replace('map x', 'map y')))
        self.assertNotEqual(sync.php_processors(old), sync.php_processors(old.replace('A=1', 'A=2')))
        self.assertEqual(sync.php_processors(None), [])


if __name__ == '__main__':
    unittest.main()
