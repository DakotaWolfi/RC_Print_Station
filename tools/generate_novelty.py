"""Build monochrome Epson artwork and PNG previews from the same bitmap."""
import base64
import json
from pathlib import Path
import zlib

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/"assets/novelty"
FONT=ROOT/"hmi/design/typeface/NotoSans-Regular.ttf"
WIDTH=504
# No user, device or measurement data appears on these souvenirs.
COPY={
    "awoo": ("awoo",
        ("AWOO-BUSSE","Zu lautes Heulen an der Werkbank","Tatbestand: spontane Awoo-Abgabe.",
         "Busse: ein freundliches Winken und", "eine Streicheleinheit für den Wolf."),
        ("AWOO FINE","Unlicensed workshop howling","Offence: spontaneous awoo.",
         "Fine: one friendly wave and", "one pat for the workshop wolf.")),
    "paw": ("idle",
        ("PFOTEN-AKTE","Werkstattwolf · Abteilung Kleinteile","Ein Schräubchen fehlt seit 14:03.",
         "Verdacht: unter der Werkbank.", "Die Pfote schweigt zum Vorwurf."),
        ("PAW FILE","Workshop wolf · Small Parts Desk","One screw went missing at 14:03.",
         "Last seen: under the workbench.", "The paw declines to comment.")),
    "survivor": ("happy",
        ("WERKBANK ÜBERLEBT","Kleine Auszeichnung für grosse Geduld","Du hast die letzte Schraube gefunden.",
         "Der Wolf hat zugeguckt und hilft", "beim nächsten Mal bestimmt wieder."),
        ("BENCH SURVIVOR","A small award for great patience","You found the last screw.",
         "The wolf watched and promises", "to be just as helpful next time.")),
}


def design(kind, language):
    asset,de,en=COPY[kind]
    title,subtitle,*body=en if language=="en" else de
    fonts={size:ImageFont.truetype(str(FONT),size) for size in (18,20,22,38,44)}
    picture=Image.open(ROOT/f"assets/wolf/{asset}.webp").convert("RGBA")
    picture=picture.crop(picture.getchannel("A").getbbox())
    picture.thumbnail((278,250),Image.Resampling.LANCZOS)
    mat=Image.new("RGBA",picture.size,"white")
    mat.alpha_composite(picture)
    photo=ImageOps.autocontrast(mat.convert("L"),cutoff=.4)
    photo=Image.eval(photo,lambda p: min(255,round(255*(p/255)**.86)))
    bitmap=Image.new("1",(WIDTH,608),1)
    bitmap.paste(photo.convert("1"),((WIDTH-photo.width)//2,144+(250-photo.height)//2))
    draw=ImageDraw.Draw(bitmap)
    draw.rectangle((16,14,WIDTH-17,591),outline=0,width=2)
    for y in (61,131,412,538):
        draw.line((34,y,WIDTH-35,y),fill=0,width=2)

    def line(text,y,size,stroke=0):
        f=fonts[size]
        assert draw.textlength(text,font=f)<=WIDTH-68,text
        draw.text((WIDTH//2,y),text,anchor="mt",font=f,fill=0,stroke_width=stroke)

    line("FMI  /  REPAIR CAFÉ RIEHEN",31,18)
    line(title,76,38 if len(title)>16 else 44,1)
    line(subtitle,392,20)
    for i,part in enumerate(body):
        line(part,430+i*29,22)
    line("SOUVENIR ONLY  /  NOT A TEST REPORT" if language=="en" else
         "SPASSBELEG  /  KEIN PRÜFPROTOKOLL",550,18,1)
    return bitmap


def main():
    ART.mkdir(exist_ok=True)
    values={}
    for kind in COPY:
        for language in ("de","en"):
            key=f"{kind}-{language}"
            bitmap=design(kind,language)
            bitmap.save(ART/f"{key}.png",optimize=True)
            dots=bytes(v^255 for v in bitmap.tobytes())
            values[key]=[bitmap.width,bitmap.height,base64.b64encode(zlib.compress(dots)).decode("ascii")]
    (ART/"rasters.json").write_text(json.dumps(values,separators=(",",":"))+"\n",encoding="ascii")


if __name__=="__main__":
    main()
