from pathlib import Path
import os
import json
import qt,slicer

output=Path(os.environ.get("FMI_BROWSER_OUTPUT","/tmp/fmi-v082-browser"))
output.mkdir(parents=True,exist_ok=True)
view=slicer.qSlicerWebWidget()
view.resize(390,844)
view.url="http://127.0.0.1:18191/"
view.show()
script=(Path.cwd()/"tests/browser/operator_flow.js").read_text()
tasks=[]
from itertools import product
for lang,(w,h),page in product(("de","en"),((390,844),(844,390),(820,1180),(1180,820)),
                               ("home","connection","admin","wolf","achievements","report","print-dialog")):
    tasks.append((lang,w,h,page))
current=None
finished=False
def request():
    if not tasks:
        slicer.util.exit()
        return
    global current
    current=tasks.pop(0)
    lang,w,h,page=current
    view.resize(w,h)
    view.evalJS("if(dialog.open)dialog.close(); app.state.language='"+lang+"';")
    route={"home":"home","connection":"connection","admin":"settings","wolf":"pet",
           "achievements":"achievements","report":"work","print-dialog":"work"}[page]
    view.evalJS("navigate('"+route+"',false)")
    if page=="print-dialog":
        view.evalJS("confirm('Beleg jetzt drucken?',()=>{})")
    qt.QTimer.singleShot(170,lambda:view.evalJS("JSON.stringify({width:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,title:main.querySelector('h1')?.textContent,modal:dialog.open,visible:[...document.querySelectorAll('button')].filter(x=>x.offsetHeight).every(x=>x.offsetHeight>=48)})"))
def result(js, value):
    global finished
    if js=="window.v082Result" and not finished:
        if not value or value=="undefined":
            return
        finished=True
        r=json.loads(value)
        print("FLOW "+value,flush=True)
        if not r["ok"]:
            view.grab().save(str(output/"failed.png"))
            slicer.util.exit(1)
            return
        view.evalJS("window.clearInterval = clearInterval; app.polling=true;")
        request()
    elif js.startswith("JSON.stringify") and current:
        lang,w,h,page=current
        out=output/lang/f"{w}x{h}"
        out.mkdir(parents=True,exist_ok=True)
        view.grab().save(str(out/(page+".png")))
        print(f"LAYOUT {lang} {w} {h} {page} {value}",flush=True)
        qt.QTimer.singleShot(20,request)
view.connect("evalResult(QString,QString)",result)
timer=qt.QTimer()
timer.connect("timeout()",lambda:view.evalJS("window.v082Result") if not finished else timer.stop())
def launch():
    view.evalJS(script)
    timer.start(250)
qt.QTimer.singleShot(1800,launch)
qt.QTimer.singleShot(90000,lambda:slicer.util.exit(2))
