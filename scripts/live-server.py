import http.server, socketserver, os, glob, sys

PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)
    def do_GET(self):
        if self.path.startswith('/data.csv'):
            files = sorted(glob.glob(os.path.join(ROOT, 'profile700-*.csv')), key=os.path.getmtime)
            if not files:
                self.send_error(404, 'no csv yet'); return
            try:
                with open(files[-1], 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                self.send_error(500)
            return
        super().do_GET()
    def log_message(self, *a):
        pass

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(('127.0.0.1', PORT), H) as httpd:
    print('serving %s on http://127.0.0.1:%d/live.html' % (ROOT, PORT), flush=True)
    httpd.serve_forever()
