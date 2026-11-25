"""Native settings page protocol; all NetworkManager/power calls run off UART."""
from concurrent.futures import ThreadPoolExecutor
from ipaddress import IPv4Address
from pathlib import Path
import platform
import socket
import sqlite3
import subprocess
import time

import station_config as config
from station_network import Network, NetworkError, NetworkManager

PAGES = ("home","entry","keyboard","report","qrpage","history","settings",
         "wifi","wjoin","printer","receipt","system","power")
ROWS = 4
DENSITY_LABELS = {"default":"Druckervorgabe","light":"Hell (GS ( K)","dark":"Dunkel (GS ( K)"}


def probe(host,port):
    with socket.create_connection((host,port),timeout=4):
        pass


def system_power(action):
    # No shell, privilege changes, or argument derived from the UART.
    command = {"REBOOT":"reboot","HALT":"poweroff"}[action]
    subprocess.run(["loginctl","--no-ask-password",command], check=True,
                   capture_output=True,timeout=8)


class PanelSettings:
    def __init__(self,ui,network=None,path=None,enable_power=False, power_fn=system_power, probe_fn=probe):
        self.ui=ui
        self.network=network or NetworkManager()
        self.path=path
        self.enable_power=enable_power
        self.power_fn,self.probe_fn=power_fn,probe_fn
        self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix="network")
        self.job=None
        self.page=None
        self.selected=None
        self.joined=False
        self.networks=[]
        self.hotspot_password=""
        self.offset=0
        self.ssid=self.ip=""
        self.status="Netzwerke suchen, um WLAN einzurichten."
        self.printer_note=""
        self.receipt_note=""
        self.system_note=""
        self.power_note=""
        self.armed_until=0
        self.printer_probe=None
        self.power_job=None
        self.last_check=float("-inf")
        self.display_values=None
        try:
            self.model=Path("/proc/device-tree/model").read_bytes().rstrip(b"\x00").decode()
        except (OSError,UnicodeError):
            self.model=f"Linux / {platform.machine()}"

    def cfg(self):
        return config.load(self.path)

    def endpoint(self, settings):
        return settings.get("printer_host",self.ui.host),settings.get("printer_port",self.ui.printer_port)

    def apply_display(self,force=False):
        values=self.cfg()
        pair=(values["brightness"],values["standby"])
        if force or pair!=self.display_values:
            self.display_values=pair
            self.ui.cmd(f"dim={pair[0]}")
            self.ui.cmd("thup=1")
            self.ui.cmd(f"thsp={pair[1]}")

    def enter(self, ident):
        self.page=PAGES[ident] if 0<=ident<len(PAGES) else None
        if self.page=="power":
            self.armed_until=time.monotonic()+20
            self.power_note="" if self.enable_power else "Ausschalten am Display ist nicht freigegeben."
        else:
            self.armed_until=0
        self.draw()

    def choices(self):
        active=self.ssid=="FMI-RC-Printstation" and bool(self.ip)
        ap=Network("hotspot-stop" if active else "hotspot-start",
                   b"Hotspot beenden" if active else b"FMI Hotspot starten",0,"AP","")
        return [ap] if active else self.networks+[ap]

    def draw(self):
        t=self.ui.text
        c=self.ui.cmd
        p=self.page
        if p=="wifi":
            t("wCurrent",f"{self.ssid or 'Nicht verbunden'} / {self.ip or 'keine IPv4'}",56)
            choices=self.choices()
            page=choices[self.offset:self.offset+ROWS]
            for i in range(ROWS):
                label="-"
                if i<len(page):
                    net=page[i]
                    label=net.name if net.path.startswith("hotspot-") else f"{net.signal:3d}% {net.security} | {net.name}"+(" [gesp.]" if getattr(net,"saved","") else "")
                t(f"wRow{i}",label,54)
            c(f"wCount.val={len(page)}")
            c(f"wBusy.val={int(self.job is not None and self.job[0]!='status')}")
            c(f"wNext.val={int(self.offset+ROWS<len(choices))}")
            c(f"wPrev.val={int(self.offset>0)}")
            total=(len(choices)+ROWS-1)//ROWS
            t("wIndex",f"{self.offset//ROWS+1} / {total}" if total else "",16)
            t("wStatus",f"Hotspot-Passwort: {self.hotspot_password}" if self.hotspot_password and self.ssid=="FMI-RC-Printstation" and (not self.job or self.job[0]=="status") else self.status,76)
        elif p=="wjoin":
            net=self.selected
            t("jName",net.name if net else "Netz nicht verfügbar",42)
            t("jStatus",self.status,86)
            supported=(1 if net.key_mgmt=="" or getattr(net,"saved","") else 2) if net and net.key_mgmt is not None else 0
            c(f"jMode.val={0 if self.joined or (self.job and self.job[0] in ('connect','hotspot','hotspot-stop')) else supported}")
        elif p=="printer":
            host,port=self.endpoint(self.cfg())
            t("pHost",host,16)
            t("pPort",port,5)
            t("pStatus",self.printer_note,76)
        elif p=="receipt":
            s=self.cfg()
            t("rGraphic","Kopf: Grafik" if s["graphic"] else "Kopf: Text",28)
            t("rFeed",f'{s["feed_mm"]} mm',16)
            t("rDensity",DENSITY_LABELS[s["density"]],30)
            t("rStatus",self.receipt_note,68)
        elif p=="system":
            s=self.cfg()
            t("sModel",self.model,50)
            t("sBright",f'{s["brightness"]} %',16)
            t("sStand",f'{s["standby"]} s' if s["standby"] else "Aus",16)
            t("sStatus",self.system_note,60)
        elif p=="power":
            c(f"xEnabled.val={int(self.enable_power and self.armed_until>time.monotonic() and self.power_job is None)}")
            t("xStatus",self.power_note or "Bestätigung innerhalb von 20 Sekunden.",76)

    def start_network(self, kind, fn, *args):
        if self.job and self.job[0]!="status":
            return False
        # At most one active operation plus one short status call finishing.
        self.job=(kind,self.worker.submit(fn,*args))
        return True

    def set_status(self, ssid, ip):
        self.ssid=ssid
        self.ip=str(IPv4Address(ip)) if ip else ""
        if self.ui.auto_port is not None:
            url=f"http://{self.ip}:{self.ui.auto_port}" if self.ip else ""
            if url!=self.ui.base_url:
                self.ui.base_url=url
                self.ui.urls.clear()
                self.ui.cmd("qrpage.qReady.val=2")
                self.ui.text("qrpage.tNote","WLAN / IP geändert. Kein aktueller Download-Link.",100)
                if self.page=="qrpage" and self.ui.report:
                    try:
                        self.ui.show_qr()
                    except (OSError,ValueError, sqlite3.Error):
                        self.ui.text("qrpage.tNote","PDF-Link nicht verfügbar. Bitte erneut öffnen.",100)

    def poll(self):
        now=time.monotonic()
        if self.job and self.job[1].done():
            kind,future=self.job
            self.job=None
            try:
                result=future.result()
                if kind=="scan":
                    self.networks=result
                    self.status=f"{len(result)} Netze gefunden." if result else "Keine WLAN-Netze gefunden."
                elif kind=="hotspot":
                    ssid,ip,password=result
                    self.hotspot_password=password
                    self.set_status(ssid,ip)
                    self.offset=0
                    self.status=f"Offener Hotspot aktiv. IP: {ip}"
                    self.joined=True
                elif kind=="hotspot-stop":
                    self.hotspot_password=""
                    self.set_status(*result)
                    self.offset=0
                    self.networks=[]
                    self.status="Hotspot beendet. WLAN erneut suchen."
                    self.joined=True
                else:
                    self.set_status(*result)
                    if kind=="connect":
                        self.status=f"Verbunden · IP: {self.ip}"
                        self.joined=True
            except Exception as exc:
                if kind!="status":
                    self.status=str(exc) if isinstance(exc,NetworkError) else "WLAN-Aktion fehlgeschlagen."
                else:
                    self.set_status("","")
                    if self.status.startswith("Netzwerke suchen"):
                        self.status="WLAN-Status nicht verfügbar. Netzwerkdienst prüfen."
            self.draw()
        if not self.job and now-self.last_check>=4:
            self.last_check=now
            self.start_network("status",self.network.status)
        if self.printer_probe and self.printer_probe.done():
            try:
                self.printer_probe.result()
                self.printer_note="TCP-Verbindung erfolgreich."
            except Exception:
                self.printer_note="TCP-Verbindung fehlgeschlagen."
            self.printer_probe=None
            self.draw()
        if self.power_job and self.power_job.done():
            try:
                self.power_job.result()
                self.power_note="Systemaktion wurde angefordert."
            except Exception:
                self.power_note="Systemaktion nicht erlaubt oder fehlgeschlagen."
            self.power_job=None
            self.draw()
        if self.armed_until and now>=self.armed_until:
            self.armed_until=0
            self.power_note="Bestätigung abgelaufen. Seite erneut öffnen."
            self.draw()

    def connect(self,password):
        if self.selected is None or self.selected.key_mgmt is None:
            self.status="WLAN bitte erneut auswählen."
        elif self.start_network("connect",self.network.connect,self.selected,password):
            self.status="Verbinde mit WLAN ... warte auf IP-Adresse."
            self.set_status("","")
        else:
            self.status="WLAN-Aktion läuft bereits."
        self.draw()

    def handle(self,frame):
        action,_,payload=frame.partition(b"\x00")
        page=self.page
        try:
            if page=="wifi" and action==b"RC4:SCAN":
                if self.ssid=="FMI-RC-Printstation" and self.ip:
                    self.status="Hotspot zuerst beenden."
                elif self.start_network("scan",self.network.scan):
                    self.offset=0
                    self.networks=[]
                    self.selected=None
                    self.joined=False
                    self.status="WLAN-Suche läuft ..."
            elif page=="wifi" and action in (b"RC4:NEXT",b"RC4:PREV"):
                self.offset=min(max(0,self.offset+(ROWS if action.endswith(b"NEXT") else -ROWS)),
                                max(0,(len(self.choices())-1)//ROWS*ROWS))
            elif page=="wifi" and action in (b"RC4:SEL:0",b"RC4:SEL:1",b"RC4:SEL:2",b"RC4:SEL:3"):
                index=self.offset+int(action[-1:])
                choices=self.choices()
                self.selected=choices[index] if index<len(choices) else None
                net=self.selected
                self.joined=False
                self.status=(f"{net.security} / {net.signal}% · Verbindung bestätigen."
                             if net and net.key_mgmt is not None else "Netztyp nicht unterstützt oder Netz nicht verfügbar.")
                if net and net.path.startswith("hotspot-"):
                    self.status="WLAN wird getrennt. Hotspot starten?" if net.path=="hotspot-start" else "Hotspot beenden und WLAN wieder nutzen?"
                elif net and getattr(net,"saved",""):
                    self.status="Gespeichertes WLAN. Ohne Passworteingabe verbinden."
                return  # Next event is wjoin's page ID; no stale writes.
            elif page=="wjoin" and action==b"RC4:JOIN":
                if self.selected and self.selected.path.startswith("hotspot-"):
                    starting=self.selected.path=="hotspot-start"
                    if self.start_network("hotspot" if starting else "hotspot-stop", self.network.hotspot if starting else self.network.stop_hotspot):
                        self.status="Hotspot wird gestartet ..." if starting else "Hotspot wird beendet ..."
                        self.draw()
                elif self.selected and (self.selected.key_mgmt=="" or getattr(self.selected,"saved","")):
                    self.connect("")
                return
            elif page=="keyboard" and action==b"RC4:PASS":
                if self.selected and self.selected.key_mgmt and len(payload)<=64:
                    self.connect(payload.decode("iso-8859-15"))
                return
            elif page=="keyboard" and action in (b"RC4:IP",b"RC4:PORT"):
                key="printer_host" if action.endswith(b"IP") else "printer_port"
                v=payload.decode("ascii").strip()
                config.save({key: int(v) if key=="printer_port" else v},self.path)
                self.printer_note="Druckeradresse gespeichert."
                return
            elif page=="printer" and action==b"RC4:PROBE":
                if not self.printer_probe and not self.ui.print_job:
                    self.printer_note="TCP-Verbindung wird geprüft ..."
                    self.printer_probe=self.ui.executor.submit(self.probe_fn,*self.endpoint(self.cfg()))
            elif page=="printer" and action==b"RC4:TEST":
                if not self.printer_probe:
                    self.ui.queue_print_test()
            elif page=="receipt" and action in (b"RC4:GRAPH",b"RC4:FEED+",b"RC4:FEED-",b"RC4:DENSITY"):
                s=self.cfg()
                if action==b"RC4:GRAPH":
                    updates={"graphic":not s["graphic"]}
                elif action==b"RC4:DENSITY":
                    keys=tuple(DENSITY_LABELS)
                    updates={"density":keys[(keys.index(s["density"])+1)%len(keys)]}
                else:
                    updates={"feed_mm":min(100,max(0,s["feed_mm"]+(5 if action.endswith(b"+") else -5)))}
                config.save(updates,self.path)
                self.receipt_note="Gespeichert. Wirksam ab dem nächsten Beleg."
            elif page=="system" and action in (b"RC4:BR+",b"RC4:BR-",b"RC4:STANDBY"):
                s=self.cfg()
                if action==b"RC4:STANDBY":
                    options=(0,30,60,120,300,600)
                    value=next((v for v in options if v>s["standby"]),0)
                    updates={"standby":value}
                else:
                    updates={"brightness":min(100,max(10,s["brightness"]+(10 if action.endswith(b"+") else -10)))}
                config.save(updates,self.path)
                self.apply_display()
                self.system_note="Display-Einstellungen gespeichert."
            elif page=="power" and action in (b"RC4:REBOOT",b"RC4:HALT"):
                if not self.enable_power or time.monotonic()>self.armed_until:
                    return
                if self.ui.print_job or self.printer_probe or (self.job and self.job[0]!="status"):
                    self.power_note="Bitte laufende Aktionen abwarten."
                elif self.power_job is None:
                    self.armed_until=0
                    self.power_note="Systemaktion wird angefordert ..."
                    self.power_job=self.ui.executor.submit(self.power_fn,action[4:].decode("ascii"))
            else:
                return
        except (OSError,ValueError,TypeError):
            # Never log raw settings frames, especially RC4:PASS.
            if action in (b"RC4:IP",b"RC4:PORT"):
                self.printer_note="Ungültige IPv4-Adresse / Port (1–65535) oder Speicherfehler."
            elif page=="receipt":
                self.receipt_note="Speichern fehlgeschlagen. Einstellungen prüfen."
            elif page=="system":
                self.system_note="Speichern fehlgeschlagen."
            elif page=="wjoin":
                self.status="WLAN-Aktion fehlgeschlagen."
        self.draw()

    def close(self):
        self.worker.shutdown(wait=True,cancel_futures=True)
