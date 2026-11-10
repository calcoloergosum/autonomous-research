"""Local read-only Research Observatory. Never starts an ARF controller."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl, unquote, urlsplit

from arf.observer_read import ObserverError, ObserverSource, encode, CHECKPOINT_LIMIT

ASSETS = Path(__file__).with_name('observer_assets')
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"


class ObserverServer(HTTPServer):
    request_queue_size = 8

    def __init__(self, source: ObserverSource, port: int = 0):
        self.source = source
        # A fixed allowlist, captured once from the packaged build directory.
        self.assets = {'/' + p.relative_to(ASSETS).as_posix(): p for p in ASSETS.rglob('*') if p.is_file() and not p.is_symlink()}
        self.assets['/'] = ASSETS / 'index.html'
        super().__init__(('127.0.0.1', port), ObserverHandler)

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server_port}'


class ObserverHandler(BaseHTTPRequestHandler):
    server_version = 'ARFObserver/1'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def send_error(self, code, message=None, explain=None):
        status = 413 if code in (414, 431) else code
        error = 'limit' if status == 413 else 'invalid_query'
        self.respond(status, encode({'api_version': 1, 'error': {
            'code': error, 'message': 'HTTP request exceeds budget' if status == 413 else 'Malformed HTTP request'}}))

    def log_message(self, *_):
        pass  # IDs, paths and study content are private; no raw request logging.

    def boundary(self):
        port = self.server.server_port
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if len(self.headers.get_all('Host', [])) != 1 or self.headers.get('Host') not in hosts:
            raise ObserverError('invalid_query', 'Unexpected local Host', 400)
        origins = self.headers.get_all('Origin', [])
        expected = 'http://' + self.headers['Host']
        if len(origins) > 1 or (origins and origins[0] != expected):
            raise ObserverError('invalid_query', 'Same-origin requests required', 400)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise ObserverError('invalid_query', 'Same-origin requests required', 400)
        if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Length', '0') != '0':
            raise ObserverError('invalid_query', 'Read requests have no body', 400)

    def respond(self, status, body, content_type='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('X-Observer-Epoch', self.server.source.epoch)
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True
        if self.command != 'HEAD':
            self.wfile.write(body)

    def handle_read(self):
        try:
            self.boundary()
            if len(self.path) > 32768 or not self.path.startswith('/') or re.search(r'%(?![a-fA-F0-9]{2})', self.path):
                raise ObserverError('invalid_query', 'Invalid bounded URL')
            url = urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment:
                raise ObserverError('invalid_query', 'Relative local URL required')
            path = unquote(url.path, errors='strict')
            if '\\' in path or '\x00' in path or any(p in ('.', '..') for p in path.split('/')) or '%' in path:
                raise ObserverError('invalid_query', 'Invalid local resource path')
            if path.startswith('/api/'):
                if self.command != 'GET':
                    raise ObserverError('method_not_allowed', 'API supports GET only', 405)
                pairs = parse_qsl(url.query, keep_blank_values=True, encoding='utf-8', errors='strict', max_num_fields=8)
                if len({k for k, _ in pairs}) != len(pairs):
                    raise ObserverError('invalid_query', 'Duplicate query parameter')
                if not path.startswith('/api/v1/') or path.count('/') != 3:
                    raise ObserverError('not_found', 'Unknown read resource', 404)
                # Keep epoch header and response from the same source session.
                with self.server.source.lock:
                    result = self.server.source.read(path[len('/api/v1/'):], dict(pairs))
                    self.respond(200, encode(result, CHECKPOINT_LIMIT if path.endswith('/checkpoint') else 262144))
            else:
                if url.query or path not in self.server.assets:
                    raise ObserverError('not_found', 'Bundled resource absent', 404)
                asset = self.server.assets[path]
                if asset.is_symlink() or not asset.is_file() or ASSETS.resolve() not in asset.resolve().parents:
                    raise ObserverError('not_found', 'Bundled resource absent', 404)
                if asset.stat().st_size > CHECKPOINT_LIMIT:
                    raise ObserverError('limit', 'Bundled asset exceeds budget', 413)
                mime = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.txt': 'text/plain; charset=utf-8'}.get(asset.suffix)
                if mime is None:
                    raise ObserverError('not_found', 'Unsupported bundled asset', 404)
                self.respond(200, asset.read_bytes(), mime)
        except ObserverError as exc:
            self.respond(exc.status, encode({'api_version': 1, 'error': {'code': exc.code, 'message': exc.message}}))
        except (ValueError, UnicodeError):
            self.respond(400, encode({'api_version': 1, 'error': {'code': 'invalid_query', 'message': 'Malformed URL'}}))
        except OSError:
            # Connection loss needs no mutation, retry or sensitive traceback.
            return

    do_GET = handle_read
    do_HEAD = handle_read

    def reject_method(self):
        self.respond(405, encode({'api_version': 1, 'error': {'code': 'method_not_allowed', 'message': 'Read-only observer'}}))

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_CONNECT = do_TRACE = reject_method

    def __getattr__(self, name):
        if name.startswith('do_'):
            return self.reject_method
        raise AttributeError(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='Existing schema-v4 study database')
    parser.add_argument('--port', type=int, default=0, help='Loopback port (default: OS-selected)')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('port must be 0..65535')
    try:
        with ObserverSource(args.db) as source:
            with ObserverServer(source, args.port) as server:
                print(json.dumps({'url': server.url, 'read_only': True, 'observer_version': 1}), flush=True)
                server.serve_forever(poll_interval=0.25)
    except ObserverError as exc:
        parser.exit(1, json.dumps({'api_version': 1, 'error': {'code': exc.code, 'message': exc.message}}) + '\n')
    except OSError:
        parser.exit(1, 'Observer could not open local listener or bundled assets\n')
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
