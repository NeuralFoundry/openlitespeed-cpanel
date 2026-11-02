import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

LSWSGI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'libexec', 'lswsgi.py')

APP = '''
def application(environ, start_response):
    size = int(environ.get('CONTENT_LENGTH') or 0)
    body = '|'.join([environ['REMOTE_ADDR'], environ['SCRIPT_NAME'], environ['PATH_INFO'], environ['QUERY_STRING'],
                     environ['wsgi.url_scheme'], environ['SERVER_NAME'], environ['wsgi.input'].read(size).decode()])
    body = body.encode()
    start_response('200 OK', [('Content-Type', 'text/plain'), ('Content-Length', str(len(body)))])
    return [body]
'''

REQUEST = (b'POST /shop/cart?x=1 HTTP/1.1\r\nHost: example.com\r\nX-Forwarded-For: 1.2.3.4, 5.6.7.8\r\n'
           b'X-Forwarded-Proto: https\r\nContent-Length: 2\r\n\r\nhi')


@unittest.skipUnless(hasattr(socket, 'AF_UNIX'), 'needs Unix domain sockets')
class LswsgiTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='olscp-wsgi-')
        with open(os.path.join(self.dir, 'passenger_wsgi.py'), 'w') as f:
            f.write(APP)
        self.sock = os.path.join(self.dir, 'app.sock')
        self.env = dict(os.environ, LSNODE_ROOT=self.dir, OLSCP_APP_URI='/shop/',
                        LS_STDERR_LOG=os.path.join(self.dir, 'log', 'stderr.log'))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def request(self):
        for _ in range(100):
            c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c.settimeout(10)
            try:
                c.connect(self.sock)
                break
            except OSError:
                c.close()
                time.sleep(0.05)
        c.sendall(REQUEST)
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
            data = self.request()
            self.assertIn(b' 200 OK', data.split(b'\r\n', 1)[0])
            self.assertTrue(data.endswith(b'5.6.7.8|/shop|/cart|x=1|https|example.com|hi'), data)
        finally:
            proc.terminate()
            proc.wait(10)

    def test_inherited_listener(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.sock)
        s.listen(10)
        proc = subprocess.Popen([sys.executable, LSWSGI, 'lsnode.js'], env=self.env, stdin=s.fileno())
        s.close()
        self.check(proc)

    def test_socket_path(self):
        env = dict(self.env, LSNODE_SOCKET=self.sock)
        proc = subprocess.Popen([sys.executable, LSWSGI], env=env, stdin=subprocess.DEVNULL)
        for _ in range(200):
            if os.path.exists(self.sock):
                break
            time.sleep(0.05)
        self.check(proc)


if __name__ == '__main__':
    unittest.main()
