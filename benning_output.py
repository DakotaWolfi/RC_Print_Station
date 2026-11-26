"""Shared display rules for the Nextion, thermal receipt and PDF."""
from datetime import datetime
from zoneinfo import ZoneInfo

from benning_csv import outcome

RESULTS = {
    "PASS": ("BESTANDEN", "#67E2A7", "#146343", "#E6F6ED"),
    "FAIL": ("NICHT BESTANDEN", "#FF9A9D", "#98232C", "#FCE9E9"),
    "partial": ("UNVOLLSTÄNDIG", "#FFD08A", "#805016", "#FFF0D6"),
    "unknown": ("UNBEKANNT", "#CDD6DD", "#4E616D", "#ECF0F3"),
    "simulation": ("SIMULATION", "#8FD9F2", "#285D75", "#E5F3FA"),
}


def show_value(value,unit):
    return " ".join(term for term in (value,unit) if term)


def report_timestamp(report):
    try:
        return datetime.fromisoformat(report["created"]).astimezone(ZoneInfo("Europe/Zurich")).strftime("%d.%m.%Y  %H:%M")
    except (KeyError, TypeError, ValueError):
        return ""


def selected_fields(report):
    record=report.get("record") or {}
    return tuple((label,value) for label,value in (
        ("Prüfnummer",report.get("ticket")),("Gerät",report.get("device")),
        ("Speicherplatz",record.get("slot")),("Prüfart",report.get("phase")),
        ("Tester-Prüfdatum",record.get("tester_date")),
        ("Schutzklasse",record.get("protection_class")),("Prüfspannung",record.get("voltage")),
        ("Protokoll erstellt",report_timestamp(report) if not record else ""))
        if value)


def examination_fields(report):
    exam=report.get("examination") or {}
    return tuple((label,exam[key]) for label,key in (
        ("Prüfzustand","status"),("Sichtprüfung","visual"),("Funktion","functional"),
        ("Prüfperson","examiner"),("Bemerkung","remarks"),("Prüfaufbau","procedure"),
        ("Betriebsart","mode"),("Am Tester beobachtet","observed"))
        if exam.get(key))


def visible_measurements(report):
    return [row for row in report.get("measurements",()) if any(row.get(key) for key in
            ("value","unit","limit","limit_unit","result","test"))]


def measurement_state(measurement):
    """Preserve supplied verdicts. Missing individual verdicts in RS232 are normal."""
    result=measurement.get("result")
    if result:
        partial=measurement["name"] not in ("Sichtprüfung","Kabel") and not (
            measurement.get("value") and measurement.get("unit"))
        return result+(" / unvollständig" if partial else ""),outcome(result) or "partial"
    if (not measurement.get("value") or not measurement.get("unit")) and measurement["name"] not in ("Sichtprüfung","Kabel"):
        return "unvollständig", "partial"
    return "", "unknown"


def result_kind(report):
    if report.get("source")=="SIMULATOR":
        return "simulation"
    record=report.get("record") or {}
    verdict=outcome(record.get("verdict") or "")
    if verdict=="FAIL":
        return verdict
    exam=report.get("examination") or {}
    rows=visible_measurements(report)
    primary={"RPE","RISO","IPE","IBer","IEA","Kabel","FI/RCD"}
    csv_source=report.get("import_source") in ("usb","file-csv")
    present={row["name"] for row in rows}
    protection=record.get("protection_class")
    guided=exam.get("procedure")
    missing_required=False
    if csv_source and verdict=="PASS":
        leakage=present & {"IEA","IPE","IBer"}
        if protection=="Klasse I" or guided=="I":
            missing_required=not {"RPE","RISO"}.issubset(present) or not leakage
        elif protection in ("Klasse II","Klasse III") or guided in ("II","III"):
            missing_required="RISO" not in present or not leakage
        elif guided in ("IEC","Verlängerung") or "Kabel" in present:
            missing_required=not {"RPE","RISO","Kabel"}.issubset(present)
    conflicting=verdict=="PASS" and any(outcome(row.get("result") or "")=="FAIL" for row in rows)
    if (conflicting or missing_required or report.get("source")=="EXAMINATION" or exam.get("status")=="Unvollständig"
            or any("unvollständig" in measurement_state(row)[0] or
                   (csv_source and row["name"] in primary and not row.get("result"))
                   for row in rows)
            or (verdict and not any(row["name"] in primary for row in rows))):
        return "partial"
    return verdict or "unknown"


def measurement_summary(row, *, csv_source=False):
    state,kind=measurement_state(row)
    if csv_source and not state and not row.get("result"):
        state,kind="unvollständig","partial"
    limit=show_value(row.get("limit"),row.get("limit_unit"))
    value=show_value(row.get("value"),row.get("unit"))
    name=" / ".join(filter(None,(row["name"],row.get("test"))))
    return name,value,limit,state,kind
