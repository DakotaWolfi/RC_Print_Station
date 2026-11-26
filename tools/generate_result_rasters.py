"""Build sparse Epson GS v 0 results and standalone monochrome previews."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benning_output import RESULTS
from i18n import LANGUAGES, tr

DESIGN=ROOT/"hmi/design"
FONT=DESIGN/"typeface/NotoSans-Regular.ttf"
WIDTH=504


def glyphs(text,width,height,stroke):
    font=ImageFont.truetype(str(FONT),120)
    l,t,r,b=font.getbbox(text,stroke_width=stroke)
    mask=Image.new("L",(r-l,b-t),0)
    ImageDraw.Draw(mask).text((-l,-t),text,font=font,fill=255,stroke_width=stroke)
    target_width=min(width,round(mask.width*height/mask.height))
    return mask.resize((target_width,height),Image.Resampling.LANCZOS).point(lambda p: 255 if p>=128 else 0)


def raster(kind, language="de"):
    text=tr(language,RESULTS[kind][0])
    two_lines=kind=="FAIL" and language=="de"
    lines=("NICHT","BESTANDEN") if two_lines else (text,)
    cap_height=84 if two_lines else 147 if kind in ("PASS","FAIL") else 91
    banner=Image.new("1",(WIDTH,46+len(lines)*(cap_height+8)),0)

    def stamp(text,y,height,stroke,width):
        mask=glyphs(text,width,height,stroke)
        banner.paste(1,((WIDTH-mask.width)//2,y,(WIDTH+mask.width)//2,y+height),mask)

    stamp(tr(language,"PRÜFPROTOKOLL" if kind=="partial" else "TESTERGEBNIS"),4,19,1,250)
    draw=ImageDraw.Draw(banner)
    draw.line((8,30,WIDTH-9,30),fill=1,width=2)
    for i,line in enumerate(lines):
        stamp(line,37+i*(cap_height+8),cap_height,4,WIDTH-16)
    draw.line((8,banner.height-4,WIDTH-9,banner.height-4),fill=1,width=2)
    return banner


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previews",type=Path)
    args=p.parse_args()
    for language in LANGUAGES:
        for kind in RESULTS:
            im=raster(kind,language)
            height=im.height
            wire=b"\x1dv0\x00"+bytes([WIDTH//8,0,height%256,height//256])+im.tobytes()+b"\n"
            suffix="-en" if language=="en" else ""
            (DESIGN/f"result-{kind}{suffix}.bin").write_bytes(wire)
            if args.previews:
                args.previews.mkdir(parents=True,exist_ok=True)
                im.point(lambda x: 255-x).save(args.previews/f"receipt-{kind}{suffix}.png")
