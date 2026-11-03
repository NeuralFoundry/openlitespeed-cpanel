import http.server
import os
import socketserver
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))

from olscp import healthcheck  # noqa: E402


class VH(object):
    def __init__(self, name, ssl_cert='', suspended=False):
        self.name = name
        self.ssl_cert = ssl_cert
        self.suspended = suspended


class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(500 if self.headers.get('Host', '').startswith('broken') else 200)
        self.end_headers()

    def log_message(self, *a):
        pass


class HealthCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = socketserver.TCPServer(('127.0.0.1', 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.t = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.t.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_valid_host_rejects_injection(self):
        for good in ('good.com', 'a.b.example.co.uk'):
            self.assertTrue(healthcheck.valid_host(good))
        for bad in ('bad host', 'x\r\nHost: evil', 'example.com\n', 'a.com\nb.com', '', '-lead.com', 'a b', 'x' * 260):
            self.assertFalse(healthcheck.valid_host(bad), bad)

    def test_mass_failures_threshold(self):
        def res(ok_names, bad_names):
            r = {'results': {}, 'probed': len(ok_names) + len(bad_names)}
            for n in ok_names:
                r['results'][n] = {'ok': True}
            for n in bad_names:
                r['results'][n] = {'ok': False, 'http_ok': False, 'http': '503'}
            return r
        self.assertEqual(healthcheck.mass_failures(res(['a', 'b'], ['c'])), [])
        self.assertEqual(healthcheck.mass_failures(res(list('abcdefg'), [])), [])
        mf = healthcheck.mass_failures(res(['a'], ['b', 'c', 'd']))
        self.assertEqual([r['name'] for r in mf], ['b', 'c', 'd'])

    def test_probe_all_skips_suspended_and_invalid(self):
        vhosts = [VH('good.com'), VH('broken.com'), VH('x.com', suspended=True), VH('bad host')]
        r = healthcheck.probe_all(vhosts, http_port=self.port, https_port=self.port + 1, timeout=3.0)
        self.assertEqual(r['total'], 2)
        self.assertTrue(r['results']['good.com']['ok'])
        self.assertFalse(r['results']['broken.com']['ok'])
        self.assertNotIn('x.com', r['results'])
        self.assertNotIn('bad host', r['results'])

    def test_regressions_only_reports_worsened(self):
        before = {'results': {'a': {'ok': True}, 'b': {'ok': True}, 'c': {'ok': False}}}
        after = {'results': {'a': {'ok': True},
                             'b': {'ok': False, 'http_ok': False, 'http': '502'},
                             'c': {'ok': False}}}
        regr = healthcheck.regressions(before, after)
        self.assertEqual([r['name'] for r in regr], ['b'])
        self.assertIn('502', regr[0]['after'])

    def test_probe_closed_port_fails(self):
        ok, _ = healthcheck.probe('good.com', 1, False, timeout=1.0)
        self.assertFalse(ok)


if __name__ == '__main__':
    unittest.main()
