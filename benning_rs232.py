"""Experimental receive-only parser for the documented ST 725 print example."""
import base64
import re

from benning_csv import ImportErrorDetail, MAX_BYTES, Measurement, Record, date_value, outcome, slot_value

PREAMBLE = b"\x18\x1bc5\x01\x1b!\x04"
VALUE = r"([<>]?[0-9]+(?:[,.][0-9]+)?)[ ]*([^\s0-9]+)"
ROW = re.compile(rf"^(RPE|RISO|IPE|IB|IBer|IEA):\s*{VALUE}(?:\s+{VALUE})?\s*$")


def parse_printout(data, encoding="cp437", *, wire=False):
    if not data or len(data)>MAX_BYTES:
        raise ImportErrorDetail("Druckbericht leer oder zu gross.")
    if wire and not data.endswith(b"\r\n"):
        raise ImportErrorDetail("Druckbericht unvollständig (CRLF fehlt).")
    payload=data.removeprefix(PREAMBLE)
    if any(b<32 and b not in (10,13) for b in payload):
        raise ImportErrorDetail("Unbekannte Steuerzeichen im Druckbericht.")
    try:
        raw=payload.decode(encoding,errors="strict")
    except (UnicodeError,LookupError):
        raise ImportErrorDetail("Druckbericht kann nicht dekodiert werden.") from None
    lines=[line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        raise ImportErrorDetail("Druckbericht leer oder zu gross.")
    if not any("Prüfung gemäss" in line or "Prüfung gemäß" in line for line in lines[:3]):
        raise ImportErrorDetail("ST-725-Druckkopf fehlt.")
    if not re.fullmatch(r"Prüfer\s+_+",lines[-1]):
        raise ImportErrorDetail("Druckbericht unvollständig oder unbekannter Abschluss.")

    def unique(pattern):
        matches=[match[1] for line in lines if (match:=re.fullmatch(pattern,line))]
        if len(matches)!=1:
            raise ImportErrorDetail("Druckbericht enthält fehlende oder doppelte Pflichtfelder.")
        return matches[0]

    slot=slot_value(unique(r"Speicherplatz-Nr\.\s+([0-9]{1,3})"))
    tester_date=unique(r"Datum\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})")
    day=date_value(tester_date,"%d.%m.%Y")
    verdict=unique(r"Prüfergebnis\s+(.+)")
    if outcome(verdict) is None:
        raise ImportErrorDetail("Unbekanntes Gesamtprüfergebnis im Druckbericht.")
    tests=[]
    seen=set()
    for line in lines:
        if match:=ROW.fullmatch(line):
            label,value,unit,limit,limit_unit=match.groups()
            if label in seen:
                raise ImportErrorDetail("Doppelte Messung im Druckbericht.")
            tests.append(Measurement(label,value,unit,limit=limit,limit_unit=limit_unit))
            seen.add(label)
        elif re.match(r"[A-Za-z][A-Za-z0-9 /-]*:",line) and not re.match(r"^[VU]ISO:",line):
            raise ImportErrorDetail("Unbekannte Messzeile im Druckbericht.")
    if not tests:
        raise ImportErrorDetail("Druckbericht enthält keine erkannten Messwerte.")
    voltage=None
    if any(re.match(r"^[VU]ISO:",line) for line in lines):
        voltage=unique(r"[VU]ISO:\s*([0-9]+(?:[,.][0-9]+)?\s*V)")
    return encoding,[Record(slot,tester_date,day,None,verdict,tuple(tests),voltage,None,
                            data.decode(encoding),base64.b64encode(data).decode("ascii"))]
