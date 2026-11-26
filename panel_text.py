"""Word-aware Nextion text fitted to the compiled widget and glyph metrics."""
from functools import lru_cache
import json
from pathlib import Path

ENCODING="iso-8859-15"


def printable(value):
    return "".join(char if char.isprintable() and char!="ÿ" else " " for char in str(value)).encode(
        ENCODING,"replace").decode(ENCODING)


def word_lines(value, measure, width, height, font_height, limit, line_spacing=0):
    """Fit whole words and mark overflow. Never split a word or an identifier."""
    max_lines=max(1,(height+line_spacing)//(font_height+line_spacing))
    lines=[""]
    omitted=False
    words=[token for paragraph in value.split("\r\n") for token in (*paragraph.split(),None)][:-1]
    for word in words:
        if word is None:
            if len(lines)>=max_lines:
                omitted=True
                break
            lines.append("")
            continue
        candidate=(lines[-1]+" "+word).strip()
        if measure(candidate)<=width:
            lines[-1]=candidate
        elif len(lines)<max_lines and measure(word)<=width:
            lines.append(word)
        else:
            omitted=True
            break
        if len("\r\n".join(lines))>limit:
            words=lines[-1].split()
            lines[-1]=" ".join(words[:-1])
            omitted=True
            break
    if omitted:
        while lines:
            last=lines[-1]
            mark=(last+" ...").strip()
            if measure(mark)<=width and len("\r\n".join(lines[:-1]+[mark]))<=limit:
                lines[-1]=mark
                break
            if not last:
                lines.pop()
            else:
                lines[-1]=" ".join(last.split()[:-1])
    return "\r\n".join(lines).rstrip("\r\n")


@lru_cache(maxsize=1)
def layout():
    path=Path(__file__).resolve().parent/"hmi/design/text-layout.json"
    return json.loads(path.read_text(encoding="utf-8"))


def bounds(address):
    data=layout()
    font,width,height,capacity,sx,sy=data["widgets"][address]
    advances=data["fonts"][str(font)]
    def measure(line):
        return sum(advances[code] for code in line.encode(ENCODING))+max(len(line)-1,0)*sx
    return measure,width-4,height,font,capacity,sy


def fit(page, component, value, limit):
    address=component if "." in component else f"{page}.{component}"
    if address not in layout()["widgets"]:
        return printable(value)[:limit]
    measure,width,height,font,capacity,sy=bounds(address)
    content="\r\n".join(printable(line) for line in str(value).split("\r\n"))
    return word_lines(content,measure,width,height,font,min(limit,capacity),sy)


def paginate(address, paragraphs):
    """Keep the full protocol notes readable even when they span several screens."""
    measure,width,height,font,capacity,sy=bounds(address)
    max_lines=(height+sy)//(font+sy)
    all_lines=[]
    for entry in paragraphs:
        value=printable(entry)
        all_lines.extend(word_lines(value,measure,width,10000,font,10000,sy).split("\r\n"))
    pages=[]
    lines=[]
    for line in all_lines:
        if len(lines)>=max_lines or len("\r\n".join([*lines,line]))>capacity:
            pages.append("\r\n".join(lines))
            lines=[]
        lines.append(line)
    return [*pages,"\r\n".join(lines)]


def quote(value):
    return '"'+value.replace("\\","\\\\").replace('"','\\"').replace("\r\n","\\r")+'"'
