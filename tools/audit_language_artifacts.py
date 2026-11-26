"""Verify the editable Nextion project and actual TFT language objects."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

from nxwright.tft.decompiling.decoded_file import read_decoded
from nxwright.tft.frame import page_name_crc
from nxwright.tft.tft_file import read_tft
from nxwright.testing.simulation import Simulation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from native_ui import END, NativeUI, PROTOCOL


class PanelUART:
    def __init__(self, sim):
        self.sim=sim

    def write(self, data):
        for command in data.split(END):
            if command:
                self.sim.serial_input(command.decode("iso-8859-15"))

    def flush(self):
        pass


def editable_and_compiled(source, tft, protocol):
    app=tomllib.loads((source/"app.toml").read_text())
    decoded=read_decoded(read_tft(tft.read_bytes(),str(tft)))
    assert "keyboard" in app["pages"]
    assert (app["screen"],app["rotation"])==("NX8048T070",270)
    assert app["pages"][:2]==["home","entry"]
    assert [page.objects[0].name.crc for page in decoded.pages]==[
        page_name_crc(name.encode()) for name in app["pages"]]
    for page_id,button,message in ((0,"bLang",b"RC70:LANG"),(1,"bReportLang",b"RC70:REPORTLANG")):
        page=app["pages"][page_id]
        objects=tomllib.loads((source/f"pages/{page}.page.toml").read_text())["component"]
        compiled=decoded.pages[page_id]
        assert compiled.page_id==page_id
        assert compiled.objects[0].name.crc==page_name_crc(page.encode())
        ids={obj["name"]:i for i,obj in enumerate(objects,1)}
        for name in (button,"hLocale",*(("lang","proto") if page_id==0 else ())):
            obj=compiled.objects[ids[name]]
            assert obj.name.crc==page_name_crc(name.encode()),(page,name)
            if name=="lang":
                assert obj.is_global
        widget=objects[ids[button]-1]
        assert widget["type"]=="button"
        assert widget["w"]>=100 and widget["h"]>=40
        release=compiled.objects[ids[button]].events["up"].blocks
        if protocol==70:
            assert any(message in block for block in release)
            assert any(b"ff ff ff" in block for block in release)
        else:
            packet=(message+END).hex(" ").encode()
            sendme=b"\x09\x09\x08"
            assert sendme in release
            assert any(packet in block.lower() for block in release[release.index(sendme)+1:])
            assert b"\x09\x00\x08"+f"{ids['hLocale']},0".encode() in compiled.load_section.blocks
        refresh=compiled.objects[ids["hLocale"]].events["up"].blocks
        assert len(refresh)>10
        if page_id==0:
            assert objects[ids["proto"]-1]["val"]==protocol
            if protocol==PROTOCOL:
                for suffix in ("DE","EN"):
                    ack=(f"RC71:LOCALE:{suffix}".encode()+END).hex(" ").encode()
                    assert any(ack in block.lower() for block in refresh)
        print(f"protocol {protocol}, page {page_id} {page}, button ID {ids[button]}, "
              f"locale refresh ID {ids['hLocale']}: compiled release and checksums verified")


def simulate_editable(source, temp):
    rx=bytearray()
    panel=Simulation(source,sending=rx.extend)
    ui=NativeUI(PanelUART(panel),"127.0.0.1",temp/"report.sqlite3",
                config_path=temp/"ui.json",tester_mode="simulation")
    def pump():
        for _ in range(18):
            data=bytes(rx)
            rx.clear()
            if not data:
                return
            ui.feed(data)
        raise AssertionError("UART did not settle")
    def tap(name):
        widget=next(c for c in panel.components() if c.name==name)
        v=widget.values
        x,y=v["x"]+v["w"]//2,v["y"]+v["h"]//2
        assert panel.component_at(x,y)==name
        panel.press(name,x,y)
        panel.release()
        frames=bytes(rx)
        pump()
        return frames
    try:
        pump()
        first=panel.values()["pLabel0.pic"]
        tap("bDirect")
        panel.serial_input('tTicket.txt="RC-AUDIT"')
        panel.serial_input('tDevice.txt="Draft text"')
        tap("bBack")
        assert b"RC70:LANG"+END in tap("bLang")
        panel.advance(200)
        pump()
        assert ui.language=="en" and ui.language_ack is None
        assert panel.values()["pLabel0.pic"]!=first
        assert panel.values()["bLang.txt"]=="EN / DE"
        tap("bResume")
        assert panel.values()["tDevice.txt"]=="Draft text"
        assert panel.values()["bReportLang.txt"]=="Report: EN"
        assert b"RC70:REPORTLANG"+END in tap("bReportLang")
        assert ui.workflow.report_language=="de" and ui.language_ack is None
        assert panel.values()["bReportLang.txt"]=="Report: DE"
        print("Extracted HMI simulation: both touch areas, wire events, rendered locale, draft and report override verified")
    finally:
        ui.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("hmi",type=Path)
    p.add_argument("tft",type=Path)
    p.add_argument("--protocol",type=int,default=PROTOCOL)
    args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix="fmi-hmi-audit-") as scratch:
        temp=Path(scratch)
        source=temp/"editable"
        executable=Path(sys.executable).with_name("nxwright")
        subprocess.run([executable,"extract",args.hmi,source],check=True)
        editable_and_compiled(source,args.tft,args.protocol)
        if args.protocol==PROTOCOL:
            simulate_editable(source,temp)


if __name__=="__main__":
    main()
