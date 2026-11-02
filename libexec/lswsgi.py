import importlib.util
import os
import signal
import socket
import stat
import sys
import threading
import time
from socketserver import ThreadingMixIn, UnixStreamServer
from wsgiref.simple_server import ServerHandler, WSGIRequestHandler

STATE = {'seen': time.time(), 'active': 0}
LOCK = threading.Lock()


def redirect_output():
    log = os.environ.get('LS_STDERR_LOG')
    if not log:
        return
    try:
        log = os.path.abspath(log)
        d = os.path.dirname(log)
        if not os.path.isdir(d):
            os.makedirs(d, 0o700)
        f = open(log, 'a', buffering=1, encoding='utf-8', errors='replace')
    except OSError:
        return
    sys.stderr = f
    sys.stdout = f


def load(root, startup):
    path = os.path.normpath(os.path.join(root, startup))
    name = os.path.splitext(os.path.basename(path))[0] or 'passenger_wsgi'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    app = getattr(module, 'application', None) or getattr(module, 'app', None)
    if app is None:
        raise SystemExit('%s does not define application' % path)
    return app


def mount(app, prefix):
    prefix = prefix.rstrip('/')

    def wrapped(environ, start_response):
        fwd = environ.get('HTTP_X_FORWARDED_FOR', '')
        if fwd:
            environ['REMOTE_ADDR'] = fwd.split(',')[-1].strip() or environ.get('REMOTE_ADDR', '')
        if environ.get('HTTP_X_FORWARDED_PROTO', '').lower() == 'https':
            environ['wsgi.url_scheme'] = 'https'
            environ['HTTPS'] = 'on'
            environ['SERVER_PORT'] = '443'
        host = environ.get('HTTP_HOST', '')
        if host:
            name, _, port = host.rpartition(':') if host.rfind(':') > host.rfind(']') else (host, '', '')
            environ['SERVER_NAME'] = name or host
            if port.isdigit():
                environ['SERVER_PORT'] = port
        path = environ.get('PATH_INFO', '')
        if prefix and (path == prefix or path.startswith(prefix + '/')):
            environ['SCRIPT_NAME'] = prefix
            environ['PATH_INFO'] = path[len(prefix):]
        return app(environ, start_response)

    return wrapped


class Response(ServerHandler):
    server_software = 'olscp'


class Handler(WSGIRequestHandler):
    def setup(self):
        WSGIRequestHandler.setup(self)
        self.client_address = ('127.0.0.1', 0)

    def address_string(self):
        return '127.0.0.1'

    def log_message(self, *args):
        pass

    def handle(self):
        self.raw_requestline = self.rfile.readline(65537)
        if len(self.raw_requestline) > 65536:
            self.send_error(414)
            return
        if not self.parse_request():
            return
        with LOCK:
            STATE['active'] += 1
        try:
            h = Response(self.rfile, self.wfile, sys.stderr, self.get_environ(), multithread=True)
            h.request_handler = self
            h.run(self.server.app)
        finally:
            with LOCK:
                STATE['active'] -= 1
                STATE['seen'] = time.time()


class Server(ThreadingMixIn, UnixStreamServer):
    daemon_threads = True

    def __init__(self, sock, app):
        UnixStreamServer.__init__(self, '', Handler, bind_and_activate=False)
        self.socket.close()
        self.socket = sock
        self.app = app
        self.base_environ = {
            'SERVER_NAME': 'localhost', 'GATEWAY_INTERFACE': 'CGI/1.1', 'SERVER_PORT': '80',
            'REMOTE_HOST': '', 'CONTENT_LENGTH': '', 'SCRIPT_NAME': '',
        }


def listener():
    try:
        st = os.fstat(0)
        if stat.S_ISSOCK(st.st_mode):
            s = socket.fromfd(0, socket.AF_UNIX, socket.SOCK_STREAM)
            if s.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
                fd = os.open(os.devnull, os.O_RDONLY)
                os.dup2(fd, 0)
                os.close(fd)
                return s
            s.close()
    except OSError:
        pass
    path = os.environ.get('LSNODE_SOCKET', '')
    if not path:
        raise SystemExit('no listening socket')
    try:
        os.unlink(path)
    except OSError:
        pass
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(path)
    s.listen(100)
    return s


def idle_exit(limit):
    while True:
        time.sleep(min(30, limit))
        with LOCK:
            idle = not STATE['active'] and time.time() - STATE['seen'] > limit
        if idle:
            os._exit(0)


def main():
    redirect_output()
    root = os.path.abspath(os.environ.get('LSNODE_ROOT') or os.getcwd())
    startup = os.environ.get('LSNODE_STARTUP_FILE') or 'passenger_wsgi.py'
    os.chdir(root)
    if root not in sys.path:
        sys.path.insert(0, root)
    sock = listener()
    app = mount(load(root, startup), os.environ.get('OLSCP_APP_URI') or '/')
    signal.signal(signal.SIGTERM, lambda *a: os._exit(0))
    try:
        limit = int(os.environ.get('LSAPI_PGRP_MAX_IDLE') or 0)
    except ValueError:
        limit = 0
    if limit > 0:
        t = threading.Thread(target=idle_exit, args=(limit,))
        t.daemon = True
        t.start()
    Server(sock, app).serve_forever()


if __name__ == '__main__':
    main()
