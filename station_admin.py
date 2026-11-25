"""Local-only station administration. Access via SSH port forwarding."""
import argparse
import html
import json
import os
from pathlib import Path
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

CONFIG = Path.home()/".config"/"rc-printstation"/"receipt.json"

def receipt_settings():
    defaults = {"graphic": True, "feed_mm": 45}
    try:
        d = json.loads(CONFIG.read_text())
        if isinstance(d.get("graphic"), bool):
            defaults["graphic"] = d["graphic"]
        if type(d.get("feed_mm")) is int and 0 <= d["feed_mm"] <= 100:
            defaults["feed_mm"] = d["feed_mm"]
    except (OSError, ValueError, AttributeError):
        pass
    return defaults

def save_settings(graphic, feed_mm):
    if not 0 <= feed_mm <= 100:
        raise ValueError("Papiertransport: 0–100 mm")
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps({"graphic": graphic, "feed_mm": feed_mm}))
    os.replace(tmp, CONFIG)

def nm(*args, timeout=15):
    return subprocess.run(["nmcli", *args], capture_output=True, text=True,
                          timeout=timeout, check=True).stdout

def wifi_address(interface="wlan0"):
    try:
        import ipaddress
        data = json.loads(subprocess.check_output(
            ["ip","-j","-4","addr","show","dev",interface], timeout=2))
        for device in data:
            for a in device.get("addr_info", []):
                ip = ipaddress.ip_address(a["local"])
                if not ip.is_link_local and not ip.is_loopback and a.get("scope")=="global":
                    return str(ip)
    except (OSError, ValueError, subprocess.SubprocessError, KeyError):
        pass
    return ""

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8081)
    p.add_argument("--interface", default="wlan0")
    args = p.parse_args()
    token = secrets.token_urlsafe(32)
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
            body=f"""<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>FMI Station – Verwaltung</title><style>
*{{box-sizing:border-box}}body{{background:#101923;color:#f5f6f7;font:16px system-ui;margin:0 auto;max-width:760px;padding:24px}}
section{{background:#1d2c3a;border-radius:12px;padding:20px;margin:20px 0}}input,button{{font:inherit;padding:10px;margin:5px 0;max-width:100%}}button{{background:#ff941f;border:0;border-radius:6px;color:#101923;font-weight:bold}}label{{display:block}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}small{{color:#afc2d0}}</style>
<h1>Repair Café Riehen</h1><small>FMI / Station verwalten</small><p>{esc(message)}</p>
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
            if self.path != "/":
                self.send_error(404); return
            self.page()
        def do_POST(self):
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
                    save_settings("graphic" in d,int(val("feed")))
                    message="Belegeinstellungen gespeichert."
                elif action=="scan":
                    nm("device","wifi","rescan","ifname",args.interface)
                    message="WLAN-Suche gestartet. Seite erneut laden."
                elif action=="connect":
                    ssid,pw=val("ssid"),val("password")
                    if not 1<=len(ssid.encode())<=32 or ssid.startswith("-") or any(ord(c)<32 for c in ssid+pw):
                        raise ValueError()
                    cmd=["device","wifi","connect",ssid,"ifname",args.interface]
                    if pw: cmd+=["password",pw]
                    nm(*cmd,timeout=45)
                    message="Verbindung hergestellt."
                else:
                    raise ValueError()
            except (ValueError, OSError, subprocess.SubprocessError):
                message="Aktion fehlgeschlagen. Eingaben, NetworkManager und Berechtigungen prüfen."
            self.page(message)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    print(f"Administration: http://127.0.0.1:{args.port}/ (nur lokal)",flush=True)
    server.serve_forever()

if __name__=="__main__":
    main()
