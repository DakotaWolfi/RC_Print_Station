"""Validate BENNING exports without converting measurement or verdict text."""
from dataclasses import dataclass
from datetime import datetime
import base64
import codecs
import csv
import re

MODEL = "BENNING ST 725"
MAX_BYTES = 512 * 1024
HEADER = (
    "Speicher Nr;Bezeichnung;Prüfdatum;Prüfergebnis;RPE Wert;RPE Einheit;RPE Ergebnis;"
    "IPE Wert;IPE Einheit;IPE Ergebnis;IBer Wert;IBer Einheit;IBer Ergebnis;"
    "IEA Wert;IEA Einheit;IEA Ergebnis;RISO Wert;RISO Einheit;RISO Ergebnis;"
    "RISO Spannung;Kabel Wert;Kabel Einheit;Kabel Ergebnis;Sichtprüfung Ergebnis;"
    "FI/RCD Test;FI/RCD Wert;FI/RCD Einheit;FI/RCD Ergebnis"
).split(";")
CODECS = ("utf-8-sig", "cp1252", "iso8859-1", "iso8859-15", "cp437", "cp850")
NUMBER = re.compile(r"[<>≤≥]?[ ]*[+-]?(?:[0-9]+(?:[.,][0-9]+)?|[.,][0-9]+)")
VOLTAGE = re.compile(r"[0-9]+(?:[.,][0-9]+)?[ ]*V")
PASS = frozenset(("bestanden","pass"))
FAIL = frozenset(("nicht bestanden","fehlgeschlagen","fail","fehlerhaft"))


class ImportErrorDetail(ValueError):
    """Safe to send to the operator. Never contains raw measurement input."""


def outcome(verdict):
    folded = verdict.casefold().strip()
    if folded in PASS:
        return "PASS"
    if folded in FAIL:
        return "FAIL"
    return None


def date_value(raw, style):
    try:
        return datetime.strptime(raw,style).date().isoformat()
    except ValueError:
        raise ImportErrorDetail("Ungültiges Prüfdatum.") from None


def slot_value(raw):
    if not re.fullmatch(r"[0-9]{1,3}",raw) or not 1<=int(raw)<=999:
        raise ImportErrorDetail("Ungültiger Speicherplatz (1 bis 999).")
    return f"{int(raw):03d}"


@dataclass(frozen=True)
class Measurement:
    name: str
    value: str | None = None
    unit: str | None = None
    result: str | None = None
    limit: str | None = None
    limit_unit: str | None = None
    test: str | None = None


@dataclass(frozen=True)
class Record:
    slot: str
    tester_date: str
    iso_date: str
    protection_class: str | None
    verdict: str
    measurements: tuple[Measurement, ...]
    voltage: str | None
    designation: str | None
    raw: str
    raw_b64: str
    model: str = MODEL


def recover_encoding(data, encoding):
    candidates = (encoding,) if encoding!="auto" else CODECS
    matches = []
    for codec in candidates:
        try:
            decoded=data.decode(codec,errors="strict")
            # Only ASCII-compatible encodings can preserve raw byte boundaries.
            if "".join(HEADER).encode(codec).find(b"Speicher Nr")<0:
                continue
        except (UnicodeError,LookupError):
            continue
        if decoded.split("\n",1)[0].rstrip("\r").split(";") == HEADER:
            matches.append((codec,decoded))
    if not matches:
        raise ImportErrorDetail("CSV-Kopfzeile oder Zeichenkodierung stimmt nicht.")
    if any(decoded!=matches[0][1] for _,decoded in matches):
        raise ImportErrorDetail("CSV-Kodierung mehrdeutig. Zeichenkodierung explizit wählen.")
    return "/".join(codec for codec,_ in matches),matches[0][1]


def text_fields(line):
    try:
        return next(csv.reader([line],delimiter=";",strict=True))
    except csv.Error:
        raise ImportErrorDetail("Ungültige CSV-Feldbegrenzung.") from None


def parse_csv(data, encoding="auto", *, wire=False, allow_empty=False):
    """Return encoding evidence and validated records. Live payloads require CRLF."""
    if not data or len(data)>MAX_BYTES:
        raise ImportErrorDetail("CSV-Export leer oder zu gross.")
    if wire and (not data.endswith(b"\r\n") or b"\n" in data.replace(b"\r\n",b"")):
        raise ImportErrorDetail("USB-Export unvollständig (CRLF fehlt).")
    name,decoded=recover_encoding(data,encoding)
    if "\r" in decoded.replace("\r\n",""):
        raise ImportErrorDetail("Unerwarteter Zeilenumbruch.")
    lines=decoded.split("\n")
    raw_lines=data.split(b"\n")
    records=[]
    seen=set()
    for index,line in enumerate(lines[1:],1):
        if index==len(lines)-1 and not line:
            continue
        line=line.removesuffix("\r")
        if any(not c.isprintable() for c in line) or len(line)>1400:
            raise ImportErrorDetail(f"Ungültige Zeichen in CSV-Zeile {index+1}.")
        fields=text_fields(line)
        if len(fields)!=len(HEADER):
            raise ImportErrorDetail(f"CSV-Zeile {index+1} hat eine falsche Feldanzahl.")
        if any(len(value)>96 for value in fields):
            raise ImportErrorDetail(f"CSV-Zeile {index+1} enthält ein zu langes Feld.")
        slot,designation,tester_date,verdict=fields[:4]
        try:
            slot=slot_value(slot)
            if slot in seen:
                raise ImportErrorDetail("Doppelter Speicherplatz im selben Export.")
            if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}",tester_date):
                raise ImportErrorDetail("Ungültiges Prüfdatum.")
            day=date_value(tester_date,"%d/%m/%Y")
            if outcome(verdict) is None:
                raise ImportErrorDetail("Unbekanntes Gesamtprüfergebnis.")
            groups=[("RPE",4),("IPE",7),("IBer",10),("IEA",13),("RISO",16),
                    ("Kabel",20),("FI/RCD",25)]
            tests=[]
            for label,position in groups:
                value,unit,result=fields[position:position+3]
                if value and not NUMBER.fullmatch(value.strip()):
                    raise ImportErrorDetail(f"Ungültiges Messwertformat ({label}).")
                tests.append(Measurement(label,value or None,unit or None,result or None,
                                         test=(fields[24] or None) if label=="FI/RCD" else None))
            voltage=fields[19] or None
            if voltage and not VOLTAGE.fullmatch(voltage.strip()):
                raise ImportErrorDetail("Ungültige Prüfspannung.")
            tests.insert(6,Measurement("Sichtprüfung",result=fields[23] or None))
            protection=re.search(r"\bKlasse (III|II|I)\b",designation,re.IGNORECASE)
            records.append(Record(slot,tester_date,day,protection[0] if protection else None,
                                  verdict,tuple(tests),voltage,designation or None,line,
                                  base64.b64encode(raw_lines[index]+(b"\n" if index<len(lines)-1 else b"")).decode("ascii")))
            seen.add(slot)
        except ImportErrorDetail as exc:
            raise ImportErrorDetail(f"CSV-Zeile {index+1}: {exc}") from None
    if not records and not allow_empty:
        raise ImportErrorDetail("CSV enthält keine Messungen.")
    return name,records


def validate_encoding(value):
    if value=="auto":
        return value
    try:
        canonical=codecs.lookup(value).name
        if "Aa1;\r\n".encode(canonical)!=b"Aa1;\r\n" and canonical!="utf-8-sig":
            raise LookupError()
    except (LookupError,UnicodeError):
        raise ImportErrorDetail("ASCII-kompatible Zeichenkodierung erforderlich.") from None
    return canonical
