"""Capture native software previews using temporary state and the real surface."""
from argparse import ArgumentParser
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from hdmi_frontend import Keyboard, Surface
from tools.render_v080_previews import fixture, run, showcase

RESOLUTIONS=((480,800),(800,480),(600,1024),(1024,600))
SETTINGS=("settings","printer","wifi","display","tester","people","personality","system","info","pet","workshop","novelty")


def capture(widget,path):
    app=QApplication.instance()
    app.processEvents()
    if not widget.grab().save(str(path)):
        raise RuntimeError(f"Cannot write preview {path}")


def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    app=QApplication([])
    with TemporaryDirectory() as directory:
        core=fixture(Path(directory))
        try:
            for lang in ("de","en"):
                scenes=list(showcase(core,lang))
                for w,h in RESOLUTIONS:
                    target=args.output/lang/f"{w}x{h}"
                    target.mkdir(parents=True,exist_ok=True)
                    win=Surface(preview=True)
                    win.people=run(core,"people")
                    win.resize(w,h)
                    win.show()
                    for name,state,report in scenes:
                        win.loaded_report=state["report"] if report else None
                        win.report=report
                        win.show_state(state)
                        capture(win,target/f"{name}.png")
                    for view in SETTINGS:
                        win.route(view)
                        capture(win,target/f"{view}.png")
                    captures=(("keyboard","Gerätebeschreibung","Kaffeemaschine","text",False),
                              ("keypad","Prüfnummer","047","ticket",False),
                              ("ipv4","IPv4-Adresse","169.254.25.23","ipv4",False),
                              ("password","Passwort","","text",True))
                    for filename,title,value,mode,secret in captures:
                        editor=Keyboard(win,win.t(title),value,64,secret,mode)
                        editor.show()
                        capture(editor,target/f"{filename}.png")
                        editor.close()
                    def dialog_preview():
                        popup=app.activeModalWidget()
                        capture(popup,target/"confirmation.png")
                        popup.reject()
                    QTimer.singleShot(25,dialog_preview)
                    win.question("Beleg jetzt drucken?",lambda:None)
                    win.close()
                    app.processEvents()
        finally:
            core.close()


if __name__=="__main__":
    main()
