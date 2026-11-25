import json
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import urlsplit

def publish(db, report, base):
    token=secrets.token_urlsafe(18)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS downloads(token TEXT PRIMARY KEY, data TEXT)")
        conn.execute("INSERT INTO downloads VALUES (?,?)",(token,json.dumps(report)))
    return base+"/r/"+token

def start_server(db, port):
    from reportlab.pdfgen import canvas
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
            out=BytesIO()
            pdf=canvas.Canvas(out)
            pdf.setFont("Helvetica-Bold",18)
            pdf.drawString(50,780,"Repair Cafe Riehen")
            pdf.setFont("Helvetica",12)
            for i,line in enumerate(["SIMULATION - KEINE ELEKTRISCHE PRUEFUNG","Ticket: "+r["ticket"],"Geraet: "+r["device"],"Ergebnis: NICHT GEPRUEFT",r["created"]]):
                pdf.drawString(50,740-i*25,line)
            pdf.save()
            data=out.getvalue()
            self.send_response(200)
            self.send_header("Content-Type","application/pdf")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Disposition",'inline; filename="demo-report.pdf"')
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server=ThreadingHTTPServer(("0.0.0.0",port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
