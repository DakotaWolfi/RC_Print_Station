"""Render a focused set of v0.8.3 operator changes with the real Qt surface."""
import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PyQt5.QtWidgets import QApplication

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hdmi_frontend import RotatedSurface, Surface
from hdmi_touch import CalibrationPage
from tools.render_v080_previews import fixture,showcase


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication([])
    with TemporaryDirectory() as tmp:
        core=fixture(Path(tmp))
        try:
            scenes={name:(state,report) for name,state,report in showcase(core,"de")}
            for width,height in ((480,800),(800,480),(600,1024),(1024,600)):
                surface=Surface(preview=True)
                view=RotatedSurface(surface,0)
                view.resize(width,height)
                view.show()
                app.processEvents()

                def snap(name):
                    app.processEvents()
                    image=view.grab()
                    assert image.width()==width and image.height()==height
                    assert image.save(str(args.output/f"{width}x{height}-{name}.png"))

                surface.show_state(scenes["guide"][0])
                snap("guide")
                surface.enter_text("Prüfnummer","0001",24,lambda _:None,mode="ticket")
                snap("keypad")
                surface.close_overlay(False)
                if (width,height)==(480,800):
                    page=CalibrationPage(surface)
                    surface.open_overlay(page,None)
                    snap("calibration")
                    surface.close_overlay(False)
                if (width,height)==(800,480):
                    state,surface.report=scenes["report"]
                    surface.loaded_report=state["report"]
                    surface.show_state(state)
                    surface.open_download(state["report"])
                    surface.url="http://192.168.9.221:8080/r/preview"
                    surface.render()
                    snap("pdf")
                if (width,height)==(600,1024):
                    surface.show_state(scenes["report"][0])
                    surface.open_novelty("awoo")
                    snap("souvenir")
                view.close()
        finally:
            core.close()


if __name__=="__main__":
    main()
