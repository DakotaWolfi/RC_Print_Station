"""Non-official workshop souvenirs and their exact printer raster payloads."""
from functools import lru_cache
import base64
import json
from pathlib import Path
import struct
import zlib

from escpos import feed_and_cut

ART=Path(__file__).resolve().parent/"assets/novelty"
ITEMS={
    "awoo":"Awoo-Busse",
    "paw":"Werkstattpfoten-Akte",
    "survivor":"Werkbank überlebt",
}
MIN_FEED_MM=45


@lru_cache(maxsize=6)
def raster(kind, language):
    if kind not in ITEMS:
        raise ValueError("Unbekannter Spassbeleg.")
    language="en" if language=="en" else "de"
    values=json.loads((ART/"rasters.json").read_text(encoding="ascii"))
    w,h,payload=values[f"{kind}-{language}"]
    dots=zlib.decompress(base64.b64decode(payload))
    if w!=504 or not 1<=h<=1200 or len(dots)!=w//8*h:
        raise ValueError("Ungültige Spassbeleg-Grafik.")
    return b"\x1dv0\x00"+struct.pack("<HH",w//8,h)+dots


def render(kind, language, feed_mm=MIN_FEED_MM):
    # Fully packed raster, line termination, paper clear of the cutter, then one cut.
    return b"\x1b@"+raster(kind,language)+b"\n"+feed_and_cut(max(MIN_FEED_MM,feed_mm))


def preview_path(kind,language):
    if kind not in ITEMS or language not in ("de","en"):
        raise ValueError("Unbekannter Spassbeleg.")
    return ART/f"{kind}-{language}.png"
