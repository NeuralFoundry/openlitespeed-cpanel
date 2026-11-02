import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

LSRACK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'libexec', 'lsrack.rb')

APP = '''
run lambda { |env|
  body = [env['REMOTE_ADDR'], env['SCRIPT_NAME'], env['PATH_INFO'], env['QUERY_STRING'],
          env['rack.url_scheme'], env['SERVER_NAME'], env['rack.input'].read].join('|')
  [200, { 'content-type' => 'text/plain', 'set-cookie' => "a=1\\nb=2" }, [body]]
}
'''

FIRST = (b'POST /shop/cart?x=1 HTTP/1.1\r\nHost: example.com\r\nX-Forwarded-For: 1.2.3.4, 5.6.7.8\r\n'
         b'X-Forwarded-Proto: https\r\nContent-Length: 2\r\n\r\nhi')
SECOND = (b'POST /shop/cart?x=1 HTTP/1.1\r\nHost: example.com\r\nX-Forwarded-For: 5.6.7.8\r\n'
          b'X-Forwarded-Proto: https\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n1\r\nh\r\n1\r\ni\r\n0\r\n\r\n')
EXPECTED = b'5.6.7.8|/shop|/cart|x=1|https|example.com|hi'


def rack_available():
    if not hasattr(socket, 'AF_UNIX'):
        return False
    try:
        return subprocess.run(['ruby', '-e', 'require "rack"'], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@unittest.skipUnless(rack_available(), 'needs Unix domain sockets, Ruby and the rack gem')
class LsrackTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='olscp-rack-')
        with open(os.path.join(self.dir, 'config.ru'), 'w') as f:
            f.write(APP)
        self.sock = os.path.join(self.dir, 'app.sock')
        self.env = dict(os.environ, LSNODE_ROOT=self.dir, OLSCP_APP_URI='/shop/',
                        LS_STDERR_LOG=os.path.join(self.dir, 'log', 'stderr.log'))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def exchange(self):
        for _ in range(200):
            c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c.settimeout(20)
            try:
                c.connect(self.sock)
                break
            except OSError:
                c.close()
                time.sleep(0.05)
        c.sendall(FIRST + SECOND)
        data = b''
        while True:
            chunk = c.recv(65536)
            if not chunk:
                break
            data += chunk
        c.close()
        return data

    def check(self, proc):
        try:
            data = self.exchange()
            self.assertEqual(data.count(b'HTTP/1.1 200 OK\r\n'), 2, data)
            self.assertEqual(data.count(EXPECTED), 2, data)
            self.assertEqual(data.count(b'set-cookie: '), 4, data)
            self.assertIn(b'Connection: keep-alive', data)
            self.assertTrue(data.endswith(b'0\r\n\r\n'), data)
        finally:
            proc.terminate()
            proc.wait(10)

    def test_inherited_listener(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.sock)
        s.listen(10)
        proc = subprocess.Popen(['ruby', LSRACK, 'lsnode.js'], env=self.env, stdin=s.fileno())
        s.close()
        self.check(proc)

    def test_bad_chunk_is_rejected(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.sock)
        s.listen(10)
        proc = subprocess.Popen(['ruby', LSRACK, 'lsnode.js'], env=self.env, stdin=s.fileno())
        s.close()
        try:
            c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c.settimeout(20)
            c.connect(self.sock)
            c.sendall(b'POST / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n\r\n\r\n')
            data = c.recv(65536)
            c.close()
            self.assertTrue(data.startswith(b'HTTP/1.1 400 '), data)
        finally:
            proc.terminate()
            proc.wait(10)

    def test_socket_path(self):
        env = dict(self.env, LSNODE_SOCKET=self.sock)
        proc = subprocess.Popen(['ruby', LSRACK], env=env, stdin=subprocess.DEVNULL)
        for _ in range(400):
            if os.path.exists(self.sock):
                break
            time.sleep(0.05)
        self.check(proc)


if __name__ == '__main__':
    unittest.main()
