"""Shared presentation of observed measurement data."""
from benning_csv import outcome


def show_value(value,unit):
    return " ".join(term for term in (value,unit) if term) or "fehlt"


def selected_fields(report):
    record=report["record"]
    return (("Prüfnummer",report["ticket"]),("Gerät",report["device"]),
            ("Speicherplatz",record["slot"]),("Prüfart",report["phase"]),
            ("Tester-Prüfdatum",record["tester_date"]),
            ("Schutzklasse",record["protection_class"] or "fehlt"),
            ("Prüfspannung",record["voltage"] or "fehlt"))


def measurement_state(measurement):
    """Display label and category. Never derive a result from value or limit."""
    result=measurement.get("result")
    if result:
        # Visual inspections are verdict-only by design.
        partial=measurement["name"]!="Sichtprüfung" and not (
            measurement.get("value") and measurement.get("unit"))
        return result+(" / unvollständig" if partial else ""),outcome(result) or "partial"
    if any(measurement.get(key) for key in ("value","unit","limit","test")):
        return "unvollständig: Ergebnis fehlt","partial"
    return "fehlt","missing"
