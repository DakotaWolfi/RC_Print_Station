"""Local-only station administration. Access via SSH port forwarding."""
import argparse
import html
import secrets
import subprocess
import os
from pathlib import Path

from benning_admin import ImportPage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from station_config import load as receipt_settings, save as save_config
from station_network import NetworkManager, NetworkError, wifi_address


def nm(*args, timeout=8):
    return subprocess.run(["nmcli", *args], capture_output=True, text=True,
                          timeout=timeout, check=True).stdout


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8081)
    p.add_argument("--interface", default="wlan0")
    p.add_argument("--db",default="reports.sqlite3")
    p.add_argument("--import-token-file",default=os.environ.get("FMI_IMPORT_TOKEN_FILE"))
    args = p.parse_args()
    import_page = ImportPage(args.db,Path(args.import_token_file).read_text()) if args.import_token_file else None
    import_link = '<p><a href="/benning">BENNING-Datei importieren</a></p>' if import_page else ""
    token = secrets.token_urlsafe(32)
    network = NetworkManager(args.interface)
    esc = html.escape
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def page(self, message=""):
            try:
                networks=nm("-f","IN-USE,SSID,SIGNAL,SECURITY","device","wifi","list",
                            "ifname",args.interface,"--rescan","no")
                profiles=nm("-f","NAME,TYPE","connection","show")
            except (OSError, subprocess.SubprocessError):
                networks="NetworkManager nicht verfügbar oder keine Berechtigung."
                profiles=""
            s=receipt_settings()
            check="checked" if s["graphic"] else ""
            density_options = "".join(
                f'<option value="{key}" {"selected" if s["density"]==key else ""}>{label}</option>'
                for key,label in (("default","Druckervorgabe"),("light","Hell (GS ( K)"),("dark","Dunkel (GS ( K)")))
            body=f"""<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>FMI Station – Verwaltung</title><style>
*{{box-sizing:border-box}}body{{background:#101923;color:#f5f6f7;font:16px system-ui;margin:0 auto;max-width:760px;padding:24px}}
section{{background:#1d2c3a;border-radius:12px;padding:20px;margin:20px 0}}input,button{{font:inherit;padding:10px;margin:5px 0;max-width:100%}}button{{background:#ff941f;border:0;border-radius:6px;color:#101923;font-weight:bold}}label{{display:block}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}small{{color:#afc2d0}}</style>
<h1>Repair Café Riehen</h1><small>FMI / Station verwalten</small><p>{esc(message)}</p>{import_link}
<section><h2>WLAN</h2><p>IP: {esc(wifi_address(args.interface) or 'Nicht verbunden')}</p>
<pre>{esc(networks)}</pre><form method="post"><input type="hidden" name="token" value="{token}">
<button name="action" value="scan">Netzwerke suchen</button></form>
<form method="post"><input type="hidden" name="token" value="{token}">
<label>SSID <input name="ssid" required maxlength="32"></label>
<label>Passwort (leer für offene Netze) <input name="password" type="password" maxlength="64" autocomplete="off"></label>
<button name="action" value="connect">Verbinden</button></form>
<p><small>Ein Netzwechsel kann die SSH-Verbindung trennen. Vor Ort oder über eine separate Wartungsverbindung verwenden.</small></p>
<h3>Gespeicherte Verbindungen</h3><pre>{esc(profiles)}</pre></section>
<section><h2>Beleg</h2><form method="post"><input type="hidden" name="token" value="{token}">
<label><input type="checkbox" name="graphic" {check}> Grafischer Briefkopf</label>
<label>Papiertransport vor Schnitt (mm) <input type="number" name="feed" min="0" max="100" value="{s['feed_mm']}" required></label>
<label>Druckdichte (nur bei bestätigter GS ( K Unterstützung) <select name="density">{density_options}</select></label>
<button name="action" value="save">Speichern</button></form><small>Ab dem nächsten Druckauftrag wirksam.</small></section></html>"""
            data=body.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Frame-Options","DENY")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            if self.path == "/benning" and import_page:
                import_page.serve(self)
                return
            if self.path != "/":
                self.send_error(404); return
            self.page()
        def do_POST(self):
            if self.path == "/benning" and import_page:
                import_page.serve(self,submit=True)
                return
            if self.path != "/":
                self.send_error(404); return
            try:
                n=int(self.headers.get("Content-Length","0"))
                if not 0<n<=4096: raise ValueError()
                d=parse_qs(self.rfile.read(n).decode(),keep_blank_values=True)
                val=lambda k: d.get(k,[""])[0]
                if not secrets.compare_digest(val("token"),token):
                    self.send_error(403); return
                action=val("action")
                if action=="save":
                    save_config(dict(graphic="graphic" in d,feed_mm=int(val("feed")),density=val("density")))
                    message="Belegeinstellungen gespeichert."
                elif action=="scan":
                    nm("device","wifi","rescan","ifname",args.interface)
                    message="WLAN-Suche gestartet. Seite erneut laden."
                elif action=="connect":
                    ssid,pw=val("ssid"),val("password")
                    candidates = [n for n in network.scan(rescan=False) if n.name == ssid
                                  and n.key_mgmt is not None and bool(n.key_mgmt)==bool(pw)]
                    if not candidates:
                        raise ValueError()
                    network.connect(candidates[0],pw)
                    message="Verbindung hergestellt."
                else:
                    raise ValueError()
            except (ValueError, OSError, subprocess.SubprocessError, NetworkError):
                message="Aktion fehlgeschlagen. Eingaben, NetworkManager und Berechtigungen prüfen."
            self.page(message)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"Administration: http://127.0.0.1:{args.port}/ (nur lokal)",flush=True)
    server.serve_forever()

if __name__=="__main__":
    main()
