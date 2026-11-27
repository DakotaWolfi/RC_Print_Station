"""Local, per-output kiosk rotation. Write only confirmed previews."""
import json
import os
from pathlib import Path
import tempfile

PATH=Path.home()/".config/rc-printstation/display-rotation.json"
ANGLES=(0,90,180,270)


class Rotation:
    def __init__(self,output,apply,default=0,path=PATH):
        self.output=output or "default"
        self.apply=apply
        self.path=Path(path)
        self.saved=self.load().get(self.output,default)
        self.preview=None
        self.apply(self.saved)

    def load(self):
        try:
            data=json.loads(self.path.read_text())
            return {key:angle for key,angle in data.items() if type(angle) is int and angle in ANGLES}
        except (OSError,ValueError,AttributeError):
            return {}

    def start(self,angle):
        if type(angle) is not int or angle not in ANGLES or self.preview is not None:
            raise ValueError("Invalid rotation preview")
        self.preview=angle
        self.apply(angle)

    def done(self,commit):
        if self.preview is None:
            return
        angle,self.preview=self.preview,None
        if not commit:
            self.apply(self.saved)
            return
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            update=self.load()
            update[self.output]=angle
            fd,name=tempfile.mkstemp(prefix=".rotation-",dir=self.path.parent)
            try:
                with os.fdopen(fd,"w",encoding="utf-8") as out:
                    json.dump(update,out)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(name,self.path)
            finally:
                Path(name).unlink(missing_ok=True)
        except OSError:
            self.apply(self.saved)
            raise
        self.saved=angle
