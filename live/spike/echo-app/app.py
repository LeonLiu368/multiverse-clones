import os, http.server
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"FOO={os.environ.get('FOO','unset')} pid-env-live\n".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):  # quiet
        pass
port = int(os.environ.get("PORT", "5000"))
http.server.HTTPServer(("0.0.0.0", port), H).serve_forever()
