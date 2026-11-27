"""Live IPv4 interface policy and local gateway availability reporting."""
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
from threading import Event, Thread
from time import monotonic
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler

PRIVATE=(IPv4Network("10.0.0.0/8"),IPv4Network("172.16.0.0/12"),
         IPv4Network("192.168.0.0/16"),IPv4Network("169.254.0.0/16"))
HOSTNAME=re.compile(r"[a-zA-Z0-9][a-zA-Z0-9.-]{0,126}")


def interface_addresses(interfaces, trusted_profiles=()):
    if not interfaces:
        return ()
    try:
        raw=subprocess.run(["ip","-j","-4","address","show","up"],check=True,
                           capture_output=True,timeout=2).stdout
        links=json.loads(raw)
        if trusted_profiles:
            permitted=[]
            for name in interfaces:
                if not any(link["ifname"]==name for link in links):
                    continue
                try:
                    profile=subprocess.run(["nmcli","-g","GENERAL.CONNECTION","device","show",name],
                                           check=True,capture_output=True,text=True,timeout=2).stdout.strip()
                except (OSError,subprocess.SubprocessError):
                    continue
                if profile in trusted_profiles:
                    permitted.append(name)
            interfaces=permitted
        return tuple(interface for name in interfaces for link in links if link["ifname"]==name
                     for addr in link.get("addr_info",[]) if addr.get("family")=="inet"
                     for interface in (IPv4Interface(f'{addr["local"]}/{addr["prefixlen"]}'),)
                     if any(interface.network.subnet_of(scope) for scope in PRIVATE))
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        return ()


@dataclass
class LocalAccess:
    interfaces: tuple
    port: int
    advertised_host: str = ""
    addresses: tuple = ()
    trusted_profiles: tuple = ()
    public_origin: str = ""
    proxy_ready: bool = False

    def update(self):
        self.addresses=interface_addresses(self.interfaces,self.trusted_profiles)
        self.proxy_ready=False
        if self.public_origin:
            url=self.public_origin+"/api/health"
            try:
                with build_opener(ProxyHandler({})).open(url,timeout=1) as reply:
                    self.proxy_ready=reply.url==url and reply.read(48)==b'{"status": "fmi-web"}'
            except (OSError,ValueError):
                pass

    def accepts(self,local,peer):
        try:
            local,peer=IPv4Address(local),IPv4Address(peer)
        except ValueError:
            return False
        if local.is_loopback:
            return peer.is_loopback
        return any(addr.ip==local and peer in addr.network for addr in self.addresses)

    def dynamic_hosts(self,local):
        if not any(str(addr.ip)==local for addr in self.addresses):
            return ()
        suffix=f":{self.port}" if self.port!=80 else ""
        names=(local,self.advertised_host) if self.advertised_host else (local,)
        return tuple(name+suffix for name in names)

    def discover(self):
        suffix=f":{self.port}" if self.port!=80 else ""
        urls=[f"http://{addr.ip}{suffix}" for addr in self.addresses]
        host=self.advertised_host or socket.gethostname()
        port=self.port
        if self.proxy_ready:
            urls=[self.public_origin]
            origin=urlsplit(self.public_origin)
            host=origin.hostname
            port=origin.port or 443
        return {"status":"proxy" if self.proxy_ready else "reachable" if urls else "no-address" if self.interfaces else "loopback",
                "urls":urls,"ip":str(self.addresses[0].ip) if self.addresses else "",
                "hostname":host,"port":port}


def status_path(socket_path):
    return Path(socket_path).with_name("web-status.json")


def read_status(path, now=monotonic):
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        if 0<=now()-data["timestamp"]<8:
            return {k:v for k,v in data.items() if k!="timestamp"}
    except (OSError,ValueError,KeyError,TypeError):
        pass
    return {"status":"unavailable","urls":[],"ip":"","hostname":socket.gethostname(),"port":None}


def publish_status(path,access,stop):
    while not stop.is_set():
        access.update()
        record=dict(access.discover(),timestamp=monotonic())
        try:
            fd,name=tempfile.mkstemp(prefix=".web-status-",dir=path.parent)
            try:
                with os.fdopen(fd,"w",encoding="utf-8") as out:
                    json.dump(record,out)
                os.replace(name,path)
            finally:
                Path(name).unlink(missing_ok=True)
        except OSError:
            # The station core may be starting or recreating its runtime directory.
            pass
        stop.wait(2)


def serve_status(path,access):
    stop=Event()
    Thread(target=publish_status,args=(path,access,stop),daemon=True).start()
    return stop
