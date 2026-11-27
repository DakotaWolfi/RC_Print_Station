"""Trusted-network operator gateway with separately authorized administration."""
import argparse
from collections import OrderedDict
from dataclasses import dataclass
import getpass
from hashlib import scrypt
from hmac import compare_digest
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
import json
import logging
import os
from pathlib import Path
import re
import secrets
import tempfile
from threading import BoundedSemaphore, Lock
from time import monotonic
from urllib.parse import urlsplit

from i18n import catalogue
from station_ipc import DEFAULT_SOCKET, request
from web_access import HOSTNAME, LocalAccess, serve_status, status_path

ROOT = Path(__file__).resolve().parent
CREDENTIALS = Path.home()/".config/rc-printstation/web-auth.json"
COOKIE = "fmi_operator"
MAX_BODY = 8192
LOG=logging.getLogger(__name__)
READ = frozenset(("state", "history", "people", "templates", "report.view", "system.info"))
MUTATE = frozenset("""
    draft.new draft.edit draft.editor draft.discard
    exam.start exam.submit exam.function guide.choose guide.back guide.cancel
    review.find review.manual review.back review.select review.confirm language.report
    settings.save person.pick person.save person.active report.qr report.print
    printer.probe printer.test wifi.scan wifi.connect wifi.hotspot wifi.stop
    power.halt power.reboot personality.pet personality.treat personality.engineering novelty.print
""".split())
CONFIG_KEYS = frozenset("""
    language professional graphic feed_mm density brightness standby printer_host printer_port tester_mode
""".split())
ASSETS = {
    "/": ("text/html; charset=utf-8", ROOT/"web/index.html"),
    "/app.js": ("text/javascript; charset=utf-8", ROOT/"web/app.js"),
    "/app.css": ("text/css; charset=utf-8", ROOT/"web/app.css"),
    "/icon.svg": ("image/svg+xml", ROOT/"web/icon.svg"),
    "/manifest.webmanifest": ("application/manifest+json", ROOT/"web/manifest.webmanifest"),
}
ART = re.compile(r"/art/(g_[a-z0-9_]+)\.png")
ICONS = re.compile(r"/icons/(printer|wifi|display|tester|people|personality|system|home|back|menu)\.svg")
WOLF = re.compile(r"/wolf/(idle|happy|sleep|treat|awoo)\.webp")
TOKEN = re.compile(r"[a-f0-9]{32}")
ORIGIN = re.compile(r"https?://(?:[a-zA-Z0-9._-]+|\[[a-fA-F0-9:]+\])(?::[0-9]{1,5})?")
MAX_SESSIONS = 64
ADMIN = frozenset("""
    settings.save person.save person.active printer.probe printer.test
    wifi.scan wifi.connect wifi.hotspot wifi.stop power.halt power.reboot
    system.info personality.engineering
""".split())
PRINT = frozenset(("report.print","printer.test","novelty.print"))
STATE_PUBLIC = frozenset(("language","professional"))



def digest(password, salt):
    return scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)


def set_password(path, password):
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ValueError("Use a password of 8–128 characters")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    salt = secrets.token_bytes(16)
    fd, name = tempfile.mkstemp(prefix=".web-auth-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as file:
            json.dump({"salt": salt.hex(), "digest": digest(password, salt).hex()}, file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def load_auth(path):
    with path.open(encoding="ascii") as file:
        if os.fstat(file.fileno()).st_mode & 0o077:
            raise ValueError("Web credential file must be private (0600)")
        data = json.load(file)
    salt, password_hash = bytes.fromhex(data["salt"]), bytes.fromhex(data["digest"])
    if len(salt) != 16 or len(password_hash) != 32:
        raise ValueError("Malformed web credential file")
    return salt, password_hash


@dataclass
class Session:
    csrf: str
    expires: float
    client: str
    admin: bool=False


class Gateway:
    def __init__(self, credential, origins, socket=DEFAULT_SOCKET, transport=request, *, clock=monotonic, access=None):
        if not origins or any(not ORIGIN.fullmatch(origin) for origin in origins):
            raise ValueError("Provide exact allowed HTTP or HTTPS origins")
        if len({origin.split(":")[0] for origin in origins}) != 1:
            raise ValueError("Configure HTTP or HTTPS origins in a single gateway")
        self.secure = origins[0].startswith("https://")
        self.origins = frozenset(origins)
        self.credential = credential
        self.access = access
        self.socket, self.transport = socket, transport
        self.clock = clock
        self.lock = Lock()
        self.sessions = OrderedDict()
        self.attempts = OrderedDict()
        self.hash_limit = BoundedSemaphore(2)
        self.login_window = (0, 0)
        self.print_window = (0, 0)

    def new_session(self, prior="", *, admin=False):
        token=secrets.token_urlsafe(32)
        session=Session(secrets.token_urlsafe(32),self.clock()+12*3600,
                        "web-"+secrets.token_hex(12),admin)
        with self.lock:
            self.sessions.pop(prior,None)
            self.sessions[token]=session
            while len(self.sessions)>MAX_SESSIONS:
                # Preserve administrators during bursts of new anonymous tablets.
                oldest=next((t for t,s in self.sessions.items() if not s.admin),next(iter(self.sessions)))
                self.sessions.pop(oldest)
        return token,session

    def session_data(self,session):
        return {"csrf":session.csrf,"admin":session.admin,"admin_available":bool(self.credential)}

    def trusted_host(self,host,local):
        if self.access and not ip_address(local).is_loopback:
            return not self.secure and host in self.access.dynamic_hosts(local)
        return any(urlsplit(origin).netloc==host for origin in self.origins)

    def login(self, password, address, prior=""):
        if not self.credential or not isinstance(password, str) or not 1 <= len(password) <= 128:
            return 401, {"error": "Anmeldung fehlgeschlagen."}, ""
        now = self.clock()
        with self.lock:
            since, count = self.attempts.get(address, (now, 0))
            window, total = self.login_window
            if now - since >= 60:
                since, count = now, 0
            if now - window >= 60:
                window, total = now, 0
            if count >= 8 or total >= 48:
                return 429, {"error": "Bitte später erneut versuchen."}, ""
            self.login_window = (window, total + 1)
            self.attempts[address] = (since, count + 1)
            self.attempts.move_to_end(address)
            if len(self.attempts) > 128:
                self.attempts.popitem(last=False)
        if not self.hash_limit.acquire(blocking=False):
            return 429, {"error": "Bitte erneut versuchen."}, ""
        try:
            valid = compare_digest(digest(password, self.credential[0]), self.credential[1])
        except UnicodeError:
            valid = False
        finally:
            self.hash_limit.release()
        if not valid:
            return 401, {"error": "Anmeldung fehlgeschlagen."}, ""
        with self.lock:
            self.attempts.pop(address,None)
        token,session=self.new_session(prior,admin=True)
        return 200,self.session_data(session),token

    def session(self, token):
        with self.lock:
            session = self.sessions.get(token)
            if session and session.expires > self.clock():
                return session
            self.sessions.pop(token, None)
        return None

    def cookie(self, token):
        suffix = "; Secure" if self.secure else ""
        max_age = 43200 if token else 0
        return f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}{suffix}"

    def valid_origin(self, headers, local):
        host=headers.get("Host","")
        scheme="https" if self.secure else "http"
        return (self.trusted_host(host,local) and headers.get("Origin")==scheme+"://"+host and
                headers.get("Sec-Fetch-Site","same-origin")=="same-origin")

    def command(self, session, packet):
        if not isinstance(packet, dict) or set(packet)-{"op", "args", "id", "epoch", "tab"}:
            return 400, {"error": "Ungültige Eingabe."}
        op, args = packet.get("op"), packet.get("args", {})
        if not isinstance(op, str) or not isinstance(args, dict):
            return 400, {"error": "Ungültige Eingabe."}
        tab=packet.get("tab")
        if not isinstance(tab,str) or not TOKEN.fullmatch(tab):
            return 400, {"error": "Ungültige Eingabe."}
        if op not in READ | MUTATE:
            return 403, {"error": "Unbekannter Befehl."}
        if op in MUTATE and not all(isinstance(packet.get(field), str) and TOKEN.fullmatch(packet[field])
                                    for field in ("id", "epoch")):
            return 400, {"error": "Ungültige Eingabe."}
        if op == "settings.save":
            values=args.get("values")
            if not isinstance(values,dict) or not values or set(values)-CONFIG_KEYS:
                return 403,{"error":"Ungültige Eingabe."}
        language_only=op=="settings.save" and set(args["values"])=={"language"}
        if op in ADMIN and not language_only and not session.admin:
            return 403,{"error":"Administratoranmeldung erforderlich."}
        if op in PRINT:
            with self.lock:
                now=self.clock()
                start,count=self.print_window
                if now-start>=60:
                    start,count=now,0
                if count>=12:
                    return 429,{"error":"Zu viele Druckanfragen. Bitte kurz warten."}
                self.print_window=start,count+1
        try:
            data = self.transport(self.socket, {**{k:v for k,v in packet.items() if k!="tab"}, "client": session.client+tab})
        except (OSError, ValueError):
            return 503, {"error": "Verbindung zur Station unterbrochen."}
        if data.get("ok") and op=="state" and not session.admin:
            value=data["data"]
            data={"ok":True,"data":{**value,
                "settings":{k:v for k,v in value.get("settings",{}).items() if k in STATE_PUBLIC},
                "wifi":{},"power":{"enabled":False,"note":""}}}
        return (200 if data.get("ok") else 409),data


def token_from(headers):
    try:
        cookies = SimpleCookie(headers.get("Cookie", ""))
        value = cookies[COOKIE].value if COOKIE in cookies else ""
        return value if re.fullmatch(r"[A-Za-z0-9_-]{43}", value) else ""
    except CookieError:
        return ""


class Handler(BaseHTTPRequestHandler):
    timeout = 5
    server_version = "FMI"
    sys_version = ""

    def log_message(self, *args):
        pass

    def send_payload(self, code, value, mime="application/json; charset=utf-8", cookie=None):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; object-src 'none'")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def host_valid(self):
        if len(self.headers.get_all("Host") or [])!=1:
            return False
        host = self.headers.get("Host", "")
        return self.server.gateway.trusted_host(host,self.connection.getsockname()[0])

    def do_GET(self):
        if not self.host_valid():
            return self.send_payload(400, {})
        path = urlsplit(self.path).path
        if path == "/api/health":
            return self.send_payload(200,{"status":"fmi-web"})
        if path == "/api/session":
            gateway=self.server.gateway
            if self.headers.get("Sec-Fetch-Site","same-origin") not in ("same-origin","none"):
                return self.send_payload(403,{})
            session=gateway.session(token_from(self.headers))
            if session:
                return self.send_payload(200,gateway.session_data(session))
            token,session=gateway.new_session()
            return self.send_payload(200,gateway.session_data(session),cookie=gateway.cookie(token))
        if path == "/locale.json":
            return self.send_payload(200, catalogue())
        asset = ASSETS.get(path)
        if not asset and (match := ART.fullmatch(path)):
            asset = ("image/png", ROOT/"hmi/native/pictures"/f"{match[1]}.png")
        if not asset and (match := WOLF.fullmatch(path)):
            asset = ("image/webp", ROOT/"assets/wolf"/f"{match[1]}.webp")
        if not asset and (match := ICONS.fullmatch(path)):
            asset = ("image/svg+xml", ROOT/"assets/interfaces"/f"{match[1]}.svg")
        if asset and asset[1].is_file():
            return self.send_payload(200, asset[1].read_bytes(), asset[0])
        self.send_payload(404, {})

    def do_POST(self):
        gateway = self.server.gateway
        if (not self.host_valid() or len(self.headers.get_all("Origin") or [])!=1
                or not gateway.valid_origin(self.headers,self.connection.getsockname()[0])):
            return self.send_payload(403, {"error": "Anfrage abgelehnt."})
        if self.path not in ("/api/login", "/api/logout", "/api/command"):
            return self.send_payload(404, {})
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            return self.send_payload(415, {})
        if len(self.headers.get_all("Content-Length") or []) != 1:
            return self.send_payload(411, {})
        length = self.headers.get("Content-Length", "")
        if not length.isascii() or not length.isdecimal() or len(length) > 5 or not 1 <= int(length) <= MAX_BODY:
            return self.send_payload(413, {})
        try:
            payload = json.loads(self.rfile.read(int(length)))
        except (ValueError, RecursionError):
            return self.send_payload(400, {})
        if not isinstance(payload, dict):
            return self.send_payload(400, {})
        token = token_from(self.headers)
        if self.path == "/api/login":
            code, data, new_token = gateway.login(payload.get("password"), self.client_address[0], token)
            return self.send_payload(code, data, cookie=gateway.cookie(new_token) if new_token else None)
        session = gateway.session(token)
        if not session:
            return self.send_payload(401, {"error": "Verbindung neu aufbauen."})
        csrf = self.headers.get("X-CSRF-Token", "")
        if not csrf.isascii() or not compare_digest(csrf, session.csrf):
            return self.send_payload(403, {"error": "Anfrage abgelehnt."})
        if self.path == "/api/logout":
            token,session=gateway.new_session(token)
            return self.send_payload(200,gateway.session_data(session),cookie=gateway.cookie(token))
        code, data = gateway.command(session, payload)
        self.send_payload(code, data)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, address, gateway):
        self.gateway = gateway
        self.limit = BoundedSemaphore(12)
        super().__init__(address, Handler)

    def verify_request(self,connection,address):
        access=self.gateway.access
        return not access or access.accepts(connection.getsockname()[0],address[0])

    def process_request(self, connection, address):
        if not self.limit.acquire(blocking=False):
            self.shutdown_request(connection)
            return
        try:
            super().process_request(connection, address)
        except BaseException:
            self.limit.release()
            raise

    def process_request_thread(self, connection, address):
        try:
            super().process_request_thread(connection, address)
        finally:
            self.limit.release()

    def handle_error(self, request, client_address):
        # Avoid recording credentials, URLs or request bodies.
        pass


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--credentials", type=Path, default=CREDENTIALS)
    p.add_argument("--set-password", action="store_true")
    p.add_argument("--bind", default=os.environ.get("FMI_WEB_BIND", "127.0.0.1"))
    p.add_argument("--port", type=int, default=os.environ.get("FMI_WEB_PORT", "8090"))
    p.add_argument("--origins", default=os.environ.get("FMI_WEB_ORIGINS", ""))
    p.add_argument("--allow-lan-http", action="store_true", default=os.environ.get("FMI_WEB_ALLOW_LAN_HTTP")=="1")
    p.add_argument("--interfaces", default=os.environ.get("FMI_WEB_INTERFACES",""))
    p.add_argument("--hostname", default=os.environ.get("FMI_WEB_HOSTNAME",""))
    p.add_argument("--trusted-profiles", default=os.environ.get("FMI_WEB_TRUSTED_PROFILES",""))
    p.add_argument("--public-origin", default=os.environ.get("FMI_WEB_PUBLIC_ORIGIN",""))
    p.add_argument("--socket", default=DEFAULT_SOCKET)
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        if a.set_password:
            password=getpass.getpass("Administrator password: ")
            if password!=getpass.getpass("Repeat password: "):
                p.error("Passwords differ")
            set_password(a.credentials,password)
            return
        port=int(a.port)
        launch_ip=ip_address(a.bind)
        if launch_ip.version!=4 or not 1<=port<=65535:
            raise ValueError("Use an IPv4 listener and valid TCP port")
        interfaces=tuple(dict.fromkeys(a.interfaces.split(","))) if a.interfaces else ()
        origins=a.origins.split(",") if a.origins else []
        # v0.8.1 explicit direct-LAN opt-in is retained while dropping
        # its fixed DHCP address from both the bind and allowed origins.
        if not interfaces and not launch_ip.is_loopback and a.allow_lan_http:
            interfaces=("wlan0",)
            LOG.warning("Migrating fixed LAN bind to trusted wlan0 addresses")
        if interfaces:
            if not a.allow_lan_http or any(not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}",i) or i=="lo" for i in interfaces):
                raise ValueError("Direct LAN HTTP requires opt-in and trusted interface names")
            if any(origin.startswith("https:") for origin in origins):
                raise ValueError("Use the loopback profile for HTTPS reverse proxy")
            origins=[]
        elif not launch_ip.is_loopback:
            raise ValueError("Configure explicit trusted interfaces for direct LAN HTTP")
        if a.hostname and not HOSTNAME.fullmatch(a.hostname):
            raise ValueError("Use a configured local hostname without scheme or port")
        origins=origins or [f"http://127.0.0.1:{port}",f"http://localhost:{port}"]
        if a.public_origin and (interfaces or not a.public_origin.startswith("https://") or a.public_origin not in origins):
            raise ValueError("Advertised HTTPS origin must match the loopback proxy profile")
        access=LocalAccess(interfaces,port,a.hostname,
                           trusted_profiles=tuple(a.trusted_profiles.split(",")) if a.trusted_profiles else (),
                           public_origin=a.public_origin)
        if interfaces:
            access.update()
        try:
            auth=load_auth(a.credentials)
        except FileNotFoundError:
            auth=None
        gateway=Gateway(auth,origins,a.socket,access=access)
    except (OSError,ValueError,KeyError) as error:
        p.error(f"Web gateway configuration: {error}")
    address=("0.0.0.0" if interfaces else a.bind,port)
    with Server(address,gateway) as server:
        LOG.info("Web listener %s:%s, trusted interfaces=%s",*address,",".join(interfaces) or "loopback")
        stop=serve_status(status_path(a.socket),access)
        try:
            server.serve_forever()
        finally:
            stop.set()


if __name__ == "__main__":
    main()
