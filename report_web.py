import json
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

def publish(db, report, base):
    token=secrets.token_urlsafe(18)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS downloads(token TEXT PRIMARY KEY, data TEXT)")
        conn.execute("INSERT INTO downloads VALUES (?,?)",(token,json.dumps(report)))
    return base+"/r/"+token

def render_pdf(report):
    from benning_pdf import render
    return render(report)


def start_server(db, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def do_GET(self):
            path=urlsplit(self.path).path
            if not path.startswith("/r/"):
                self.send_error(404)
                return
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS downloads(token TEXT PRIMARY KEY, data TEXT)")
                row=conn.execute("SELECT data FROM downloads WHERE token=?",(path[3:],)).fetchone()
            if not row:
                self.send_error(404)
                return
            r=json.loads(row[0])
            data=render_pdf(r)
            self.send_response(200)
            self.send_header("Content-Type","application/pdf")
            self.send_header("Cache-Control","no-store")
            filename="demo-report.pdf" if r.get("source")=="SIMULATOR" else "benning-report.pdf"
            self.send_header("Content-Disposition",f'inline; filename="{filename}"')
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server=ThreadingHTTPServer(("0.0.0.0",port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
