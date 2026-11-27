"""Use NetworkManager only on the selected wireless device. No password argv."""
from dataclasses import dataclass
import fcntl
import os
import stat
from pathlib import Path
from ipaddress import IPv4Address
import json
import subprocess
import time
from dataclasses import replace

NM = "org.freedesktop.NetworkManager"
ROOT = "/org/freedesktop/NetworkManager"
PROPS = "org.freedesktop.DBus.Properties"
WIFI = NM+".Device.Wireless"
AP = NM+".AccessPoint"
ACTIVE = NM+".Connection.Active"
DEVICE = NM+".Device"


class NetworkError(Exception):
    """Contains an operator-safe message only."""


@dataclass(frozen=True)
class Network:
    path: str
    ssid: bytes
    signal: int
    security: str
    key_mgmt: str | None
    saved: str = ""

    @property
    def name(self):
        return self.ssid.decode("utf-8","replace")


def access_point(path, props):
    ssid = bytes(props["Ssid"])
    flags = int(props["Flags"])
    wpa, rsn = int(props["WpaFlags"]), int(props["RsnFlags"])
    # IEEE privacy plus NetworkManager's NM80211ApSecurityFlags.
    if rsn & 0x100:
        security, key = ("WPA2/3", "wpa-psk") if rsn & 0x400 else ("WPA2", "wpa-psk")
    elif rsn & 0x400:
        security, key = "WPA3", "sae"
    elif wpa & 0x100:
        security, key = "WPA", "wpa-psk"
    elif not flags & 1 and not (wpa or rsn):
        security, key = "Offen", ""
    else:
        security, key = "802.1X" if (wpa|rsn)&0x200 else "Sonstige", None
    return Network(str(path),ssid,int(props["Strength"]),security,key)


def wifi_address(interface="wlan0"):
    try:
        result = subprocess.run(["ip","-j","-4","addr","show","dev",interface],
                                capture_output=True,check=True,timeout=2)
        for dev in json.loads(result.stdout):
            for attr in dev.get("addr_info",[]):
                addr = IPv4Address(attr["local"])
                if attr.get("scope")=="global" and not addr.is_link_local and not addr.is_loopback:
                    return str(addr)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        pass
    return ""


HOTSPOT_PASSWORD = Path.home()/".config/rc-printstation/hotspot.psk"


def hotspot_password(path):
    if path is None:
        raise NetworkError("Hotspot-Passwort zuerst lokal konfigurieren.")
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,"rb") as secret:
            mode=os.fstat(secret.fileno()).st_mode
            if not stat.S_ISREG(mode) or mode & 0o077:
                raise ValueError
            password=secret.read(65).decode("ascii").rstrip("\n")
        if not 12<=len(password)<=63 or not all(32<=ord(c)<127 for c in password):
            raise ValueError
        return password
    except (ValueError,OSError):
        raise NetworkError("Hotspot-Passwortdatei fehlt oder ist ungültig (0600).") from None


class NetworkManager:
    def __init__(self, interface="wlan0", *, protected_hotspot=None, require_protected=False):
        self.interface = interface
        self.protected_hotspot=protected_hotspot
        self.require_protected=require_protected

    def _open(self):
        try:
            import dbus
            # A private bus per worker avoids sharing connection state between threads.
            return dbus, dbus.SystemBus(private=True)
        except Exception:
            raise NetworkError("NetworkManager / Systembus nicht verfügbar.") from None

    def _device(self, dbus, bus):
        root = dbus.Interface(bus.get_object(NM,ROOT,introspect=False), NM)
        path = root.GetDeviceByIpIface(self.interface,signature="s",timeout=3)
        dev = bus.get_object(NM,path,introspect=False)
        wifi = dbus.Interface(dev,WIFI)
        props = dbus.Interface(dev,PROPS)
        if int(props.Get(DEVICE,"DeviceType",signature="ss",timeout=3)) != 2:
            raise NetworkError("Die gewählte Schnittstelle ist kein WLAN-Gerät.")
        return root,path,wifi,props

    def _ap(self, dbus, bus, path):
        props = dbus.Interface(bus.get_object(NM,path,introspect=False),PROPS)
        return access_point(path,props.GetAll(AP,signature="s",timeout=2))

    def _saved(self, dbus, bus, net):
        manager=dbus.Interface(bus.get_object(NM,ROOT+"/Settings",introspect=False),NM+".Settings")
        for path in manager.ListConnections(signature="",timeout=4):
            try:
                connection=dbus.Interface(bus.get_object(NM,path,introspect=False),NM+".Settings.Connection")
                s=connection.GetSettings(signature="",timeout=2)
                wifi=s.get("802-11-wireless",{})
                sec=s.get("802-11-wireless-security",{})
                iface=s.get("connection",{}).get("interface-name","")
                if (bytes(wifi.get("ssid",[]))==net.ssid and wifi.get("mode","infrastructure")=="infrastructure"
                        and iface in ("",self.interface) and str(sec.get("key-mgmt",""))==net.key_mgmt):
                    return str(path)
            except dbus.DBusException:
                continue
        return ""

    def scan(self, rescan=True):
        dbus,bus=self._open()
        try:
            _,_,wifi,props=self._device(dbus,bus)
            if rescan:
                last=props.Get(WIFI,"LastScan",signature="ss",timeout=3)
                scan_allowed=True
                try:
                    wifi.RequestScan({},signature="a{sv}",timeout=4)
                except dbus.DBusException as exc:
                    if "NotAllowed" not in (exc.get_dbus_name() or ""):
                        raise
                    # NM also rate-limits recent scans. Use cached results in this case.
                    if int(last)<0:
                        raise
                    scan_allowed=False
                if scan_allowed:
                    deadline=time.monotonic()+8
                    while time.monotonic()<deadline:
                        if props.Get(WIFI,"LastScan",signature="ss",timeout=2)!=last:
                            break
                        time.sleep(.35)
            best={}
            paths=wifi.GetAllAccessPoints(signature="",timeout=4)
            deadline=time.monotonic()+5
            for path in paths[:128]:
                if time.monotonic()>deadline:
                    break
                try:
                    net=self._ap(dbus,bus,path)
                except dbus.DBusException:
                    continue
                key=(net.ssid,net.security)
                if net.ssid and (key not in best or net.signal>best[key].signal):
                    best[key]=net
            return [replace(n,saved=self._saved(dbus,bus,n)) for n in sorted(best.values(),key=lambda n:(-n.signal,n.ssid))]
        except dbus.DBusException:
            raise NetworkError("WLAN-Suche fehlgeschlagen. WLAN und Rechte prüfen.") from None
        finally:
            bus.close()

    def status(self):
        dbus,bus=self._open()
        try:
            _,_,_,props=self._device(dbus,bus)
            active=props.Get(DEVICE,"ActiveConnection",signature="ss",timeout=2)
            if active!="/":
                ap=dbus.Interface(bus.get_object(NM,active,introspect=False),PROPS)
                profile=ap.Get(ACTIVE,"Connection",signature="ss",timeout=2)
                conn=dbus.Interface(bus.get_object(NM,profile,introspect=False),NM+".Settings.Connection")
                wifi=conn.GetSettings(signature="",timeout=2).get("802-11-wireless",{})
                if wifi.get("mode")=="ap":
                    return bytes(wifi.get("ssid",[])).decode("utf-8","replace"),wifi_address(self.interface)
            path=props.Get(WIFI,"ActiveAccessPoint",signature="ss",timeout=2)
            return (self._ap(dbus,bus,path).name,wifi_address(self.interface)) if path!="/" else ("","")
        except dbus.DBusException:
            raise NetworkError("Kein WLAN-Status verfügbar.") from None
        finally:
            bus.close()

    def connect(self, net, password):
        if net.key_mgmt is None:
            raise NetworkError("Netztyp nicht unterstützt. Bestehendes Profil verwenden.")
        if net.key_mgmt and not (net.saved and not password):
            ascii_ok=password.isascii() and password.isprintable()
            hex_psk=len(password)==64 and all(c in "0123456789abcdefABCDEF" for c in password)
            if not (ascii_ok and (8<=len(password)<=63 or (hex_psk and net.key_mgmt=="wpa-psk"))):
                raise NetworkError("Passwort: 8–63 ASCII-Zeichen oder 64 Hex-Zeichen (WPA2).")
        elif password:
            raise NetworkError("Offenes WLAN benötigt kein Passwort.")
        # The existing admin site and the touchscreen run as the same user.
        directory=Path.home()/".config"/"rc-printstation"
        directory.mkdir(parents=True,exist_ok=True)
        with (directory/"wifi.lock").open("a") as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raise NetworkError("Eine andere WLAN-Verbindung wird gerade eingerichtet.") from None
            return self._connect(net,password)

    def _connect(self,net,password):
        dbus,bus=self._open()
        profile=active=None
        attempted=False
        previous_profile="/"
        ok=False
        try:
            root,path,_,props=self._device(dbus,bus)
            previous=props.Get(DEVICE,"ActiveConnection",signature="ss",timeout=3)
            if previous!="/":
                old=dbus.Interface(bus.get_object(NM,previous,introspect=False),PROPS)
                previous_profile=old.Get(ACTIVE,"Connection",signature="ss",timeout=3)
            current=self._ap(dbus,bus,net.path)
            if (net.ssid,net.key_mgmt)!=(current.ssid,current.key_mgmt):
                raise NetworkError("Netz hat sich geändert. Bitte erneut suchen.")
            settings={
                "connection": {"id":"FMI WLAN "+"".join(c for c in net.name if c.isprintable()),"type":"802-11-wireless",
                               "interface-name":self.interface,"autoconnect":False},
                "802-11-wireless":{"ssid":dbus.ByteArray(net.ssid),"mode":"infrastructure"},
                "ipv4":{"method":"auto","may-fail":False}, "ipv6":{"method":"auto"},
            }
            if net.key_mgmt:
                settings["802-11-wireless-security"]={"key-mgmt":net.key_mgmt,"psk":password}
            attempted=True
            if net.saved and not password:
                if self._saved(dbus,bus,current)!=net.saved:
                    raise NetworkError("Gespeichertes Profil geändert. Bitte neu suchen.")
                active=root.ActivateConnection(net.saved,path,net.path,signature="ooo",timeout=12)
            else:
                profile,active,_=root.AddAndActivateConnection2(
                settings,path,net.path,{"persist":"volatile"},signature="a{sa{sv}}ooa{sv}",timeout=12)
            p=dbus.Interface(bus.get_object(NM,active,introspect=False),PROPS)
            deadline=time.monotonic()+35
            while time.monotonic()<deadline:
                state=int(p.Get(ACTIVE,"State",signature="ss",timeout=3))
                if state==2:
                    ip=wifi_address(self.interface)
                    if ip:
                        # Save validated profiles through NetworkManager. The app
                        # keeps no credential file and never touches Ethernet.
                        if net.saved and not password:
                            ok=True
                            return net.name,ip
                        saved=dbus.Interface(bus.get_object(NM,profile,introspect=False),NM+".Settings.Connection")
                        saved.Update2({"connection":dict(settings["connection"],autoconnect=True),
                                       **{k:v for k,v in settings.items() if k!="connection"}},
                                      dbus.UInt32(1),{},signature="a{sa{sv}}ua{sv}",timeout=6)
                        ok=True
                        return net.name,ip
                if state>=3:
                    break
                time.sleep(.4)
            raise NetworkError("Keine Verbindung / IP. Passwort und Netz prüfen.")
        except dbus.DBusException:
            # Exceptions can contain the method arguments. Never expose them.
            raise NetworkError("WLAN-Verbindung fehlgeschlagen. Passwort, Netz und Rechte prüfen.") from None
        finally:
            if attempted and not ok:
                if active:
                    try:
                        root.DeactivateConnection(active,signature="o",timeout=3)
                    except dbus.DBusException:
                        pass
                if previous_profile!="/":
                    try:
                        root.ActivateConnection(previous_profile,path,"/",signature="ooo",timeout=3)
                    except dbus.DBusException:
                        pass
            bus.close()

    def hotspot(self):
        """Start a temporary access point using the selected deployment policy."""
        directory=Path.home()/".config"/"rc-printstation"
        directory.mkdir(parents=True,exist_ok=True)
        with (directory/"wifi.lock").open("a") as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raise NetworkError("Eine WLAN-Aktion läuft bereits.") from None
            return self._hotspot()

    def _hotspot(self):
        password=hotspot_password(self.protected_hotspot) if self.require_protected or self.protected_hotspot else ""
        dbus,bus=self._open()
        active=None
        previous_profile="/"
        ok=False
        ssid="FMI-RC-Printstation"
        try:
            root,path,_,props=self._device(dbus,bus)
            previous=props.Get(DEVICE,"ActiveConnection",signature="ss",timeout=3)
            if previous!="/":
                old=dbus.Interface(bus.get_object(NM,previous,introspect=False),PROPS)
                previous_profile=old.Get(ACTIVE,"Connection",signature="ss",timeout=3)
            settings={
                "connection":{"id":ssid,"type":"802-11-wireless","interface-name":self.interface,"autoconnect":False},
                "802-11-wireless":{"ssid":dbus.ByteArray(ssid.encode()),"mode":"ap","band":"bg"},
                "ipv4":{"method":"shared","never-default":True,"address-data":dbus.Array([{"address":"10.42.0.1","prefix":dbus.UInt32(24)}],signature="a{sv}")},
                "ipv6":{"method":"disabled"},
            }
            if password:
                settings["802-11-wireless-security"]={"key-mgmt":"wpa-psk","psk":password,
                                                      "proto":dbus.Array(["rsn"],signature="s")}
            _,active,_=root.AddAndActivateConnection2(settings,path,"/",{"persist":"volatile"},signature="a{sa{sv}}ooa{sv}",timeout=12)
            p=dbus.Interface(bus.get_object(NM,active,introspect=False),PROPS)
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                state=int(p.Get(ACTIVE,"State",signature="ss",timeout=3))
                if state==2 and wifi_address(self.interface):
                    ok=True
                    return ssid,wifi_address(self.interface),""
                if state>=3: break
                time.sleep(.4)
            raise NetworkError("Hotspot konnte nicht gestartet werden.")
        except dbus.DBusException:
            raise NetworkError("Hotspot fehlgeschlagen. WLAN und Freigaberechte prüfen.") from None
        finally:
            if not ok:
                if active:
                    try: root.DeactivateConnection(active,signature="o",timeout=3)
                    except dbus.DBusException: pass
                if previous_profile!="/":
                    try: root.ActivateConnection(previous_profile,path,"/",signature="ooo",timeout=3)
                    except dbus.DBusException: pass
            bus.close()

    def stop_hotspot(self):
        dbus,bus=self._open()
        try:
            root,path,_,props=self._device(dbus,bus)
            active=props.Get(DEVICE,"ActiveConnection",signature="ss",timeout=3)
            if active!="/":
                p=dbus.Interface(bus.get_object(NM,active,introspect=False),PROPS)
                profile=p.Get(ACTIVE,"Connection",signature="ss",timeout=3)
                conn=dbus.Interface(bus.get_object(NM,profile,introspect=False),NM+".Settings.Connection")
                s=conn.GetSettings(signature="",timeout=3)
                if s.get("connection",{}).get("id")=="FMI-RC-Printstation" and s.get("802-11-wireless",{}).get("mode")=="ap":
                    root.DeactivateConnection(active,signature="o",timeout=5)
            return "",""
        except dbus.DBusException:
            raise NetworkError("Hotspot konnte nicht beendet werden.") from None
        finally:
            bus.close()
