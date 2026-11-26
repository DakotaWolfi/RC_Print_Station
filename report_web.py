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

def render_pdf(report):
    """Render the original BENNING result or the existing simulated report."""
    if report.get("source")=="BENNING":
        from benning_pdf import render
        return render(report)
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from pathlib import Path
    from xml.sax.saxutils import escape
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from reportlab.lib.utils import ImageReader

    out = BytesIO()
    pdf = canvas.Canvas(out, pagesize=A4)
    pdf.setTitle("Repair Café Riehen – Simulationsprotokoll")
    pdf.setAuthor("FMI Printstation / Repair Café Riehen")
    w,h = A4
    navy=HexColor("#101923")
    panel=HexColor("#1D2C3A")
    orange=HexColor("#FF941F")
    cyan=HexColor("#42D9DD")
    ink=HexColor("#243746")
    muted=HexColor("#536878")
    pale=HexColor("#F0F4F7")
    m=42
    cw=w-2*m

    def label(x,y,s,size=10,color=muted,bold=False):
        pdf.setFillColor(color)
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica",size)
        pdf.drawString(x,y,s)

    def wrapped(value,x,top,width,size=14,color=ink,bold=False):
        style=ParagraphStyle("field",fontName="Helvetica-Bold" if bold else "Helvetica",
            fontSize=size,leading=size*1.35,textColor=color,splitLongWords=True)
        text=escape("".join(c if c.isprintable() else " " for c in str(value)))
        p=Paragraph(text or "–",style)
        _,height=p.wrap(width,700)
        p.drawOn(pdf,x,top-height)
        return top-height

    pdf.setFillColor(navy)
    pdf.rect(0,h-157,w,157,fill=1,stroke=0)
    pdf.setFillColor(orange)
    pdf.rect(0,h-161,w,4,fill=1,stroke=0)
    banner=Path(__file__).resolve().parent/"hmi"/"design"/"brand.png"
    if banner.is_file():
        try:
            pdf.drawImage(ImageReader(str(banner)),m,h-100,width=cw,height=88,
                          preserveAspectRatio=True,anchor="c",mask="auto")
        except (OSError,ValueError):
            label(m,h-54,"Repair Café Riehen",25,white,True)
            label(m,h-79,"FMI PRINTSTATION",12,cyan,True)
    else:
        label(m,h-54,"Repair Café Riehen",25,white,True)
        label(m,h-79,"FMI PRINTSTATION",12,cyan,True)
    label(m,h-122,"Elektrisches Prüfprotokoll",22,white,True)
    label(m,h-143,"Reparieren. Weitergeben.",11,cyan)

    y=h-187
    pdf.setFillColor(HexColor("#FFF0DD"))
    pdf.roundRect(m,y-66,cw,66,9,fill=1,stroke=0)
    pdf.setFillColor(orange)
    pdf.rect(m,y-66,5,66,fill=1,stroke=0)
    label(m+16,y-24,"SIMULATION / KEINE ELEKTRISCHE PRÜFUNG",13,ink,True)
    label(m+16,y-45,"Dieses Dokument ist kein Sicherheitsnachweis.",11,ink)
    y-=95
    label(m,y,"01  REPARATURDATEN",12,ink,True)
    y-=17
    try:
        stamp=datetime.fromisoformat(report["created"]).astimezone(ZoneInfo("Europe/Zurich"))
        stamp=stamp.strftime("%d.%m.%Y   %H:%M")
    except (ValueError,TypeError,KeyError):
        stamp="Unbekannt"

    for key,val in (("REPARATURNUMMER",report.get("ticket","")),
                    ("GERÄTEBEZEICHNUNG",report.get("device","")),
                    ("DATUM / UHRZEIT",stamp)):
        pdf.setFillColor(pale)
        pdf.roundRect(m,y-60,cw,60,7,fill=1,stroke=0)
        label(m+13,y-16,key,9,muted,True)
        # Valid native fields are at most 64 characters; bound legacy inputs.
        wrapped(str(val)[:128],m+13,y-23,cw-26,13,ink,True)
        y-=68

    y-=13
    label(m,y,"02  PRÜFERGEBNIS",12,ink,True)
    y-=16
    pdf.setFillColor(panel)
    pdf.roundRect(m,y-67,cw,67,8,fill=1,stroke=0)
    label(m+15,y-25,"NICHT GEPRÜFT",19,orange,True)
    label(m+15,y-46,"Keine Messwerte vorhanden.",11,white)
    y-=91
    label(m,y,"03  HINWEIS",12,ink,True)
    wrapped("Dieser Bericht wurde im Entwicklungsmodus erzeugt. Es wurde keine elektrische Sicherheitsprüfung durchgeführt und keine Freigabe erteilt.",m,y-12,cw,11,muted)
    pdf.setStrokeColor(HexColor("#D5DFE6"))
    pdf.line(m,65,w-m,65)
    label(m,45,"FMI  /  REPAIR CAFÉ RIEHEN",10,ink,True)
    label(m,29,"Digitales Simulationsprotokoll",9,muted)
    pdf.setFont("Helvetica",9)
    pdf.setFillColor(muted)
    pdf.drawRightString(w-m,45,"1 / 1")
    pdf.showPage()
    pdf.save()
    return out.getvalue()


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
            filename="benning-report.pdf" if r.get("source")=="BENNING" else "demo-report.pdf"
            self.send_header("Content-Disposition",f'inline; filename="{filename}"')
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server=ThreadingHTTPServer(("0.0.0.0",port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
