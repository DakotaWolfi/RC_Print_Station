"""Shared German-source catalogue for the UI, guidance and reports."""
from functools import lru_cache
import json
from pathlib import Path

LANGUAGES=("de","en")


def locale(value):
    return value if value in LANGUAGES else "de"


@lru_cache
def catalogue():
    path=Path(__file__).resolve().parent/"translations/en.json"
    return json.loads(path.read_text(encoding="utf-8"))


def tr(language,message,/,**values):
    text=catalogue().get(message,message) if language=="en" else message
    return text.format(**values) if values else text


def error_text(language,message):
    """Localise structured CSV diagnostics without changing parser/CLI output."""
    import re
    match=re.fullmatch(r"CSV-Zeile (\d+): (.+)",message)
    if match:
        return tr(language,"CSV-Zeile {line}: {error}",line=match[1],
                  error=error_text(language,match[2]))
    patterns=(
        (r"Ungültige Zeichen in CSV-Zeile (\d+)\.","Ungültige Zeichen in CSV-Zeile {line}."),
        (r"CSV-Zeile (\d+) hat eine falsche Feldanzahl\.","CSV-Zeile {line} hat eine falsche Feldanzahl."),
        (r"CSV-Zeile (\d+) enthält ein zu langes Feld\.","CSV-Zeile {line} enthält ein zu langes Feld."),
    )
    for pattern,key in patterns:
        match=re.fullmatch(pattern,message)
        if match:
            return tr(language,key,line=match[1])
    match=re.fullmatch(r"Ungültiges Messwertformat \(([\w/]+)\)\.",message)
    if match:
        return tr(language,"Ungültiges Messwertformat ({name}).",name=tr(language,match[1]))
    return tr(language,message)
