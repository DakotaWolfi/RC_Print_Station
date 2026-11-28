"""Display-independent guards for BENNING examination and import selection."""
from benning_csv import outcome

APPLIANCE_CLASSES = ("I","II","III")
PROCEDURE_LABELS = {"I":"Klasse I","II":"Klasse II","III":"Klasse III",
                    "Kabel":"Kabelprüfung","IEC":"Kaltgeräteleitung","Verlängerung":"Verlängerungskabel"}


def fresh_slot(baseline,source,current):
    before=baseline.get(source)
    batch,records=current.get(source,(0,{}))
    if not before:
        return ("Erster Import. Slot manuell bestätigen.",None) if batch else ("",None)
    if batch<=before[0]:
        return "",None
    changed=[slot for slot,record in records.items() if before[1].get(slot)!=record]
    if before[1].keys()-records.keys() or len(changed)>1:
        return "Mehrere Änderungen oder Speicher-Reset. Slot manuell wählen.",None
    if not changed:
        return "Kein neuer Datensatz erkennbar. Vorhandenen Slot nur bewusst wählen.",None
    return "Neuer Datensatz empfangen. Slot, Datum und Ergebnis prüfen.",changed[0]


def measurement_type(record,source):
    """A printer-port signature describes a likely test, never the appliance."""
    explicit=(record.get("protection_class") or "").upper().removeprefix("KLASSE ")
    if explicit in APPLIANCE_CLASSES:
        return explicit,"explicit"
    fields={row["name"] for row in record.get("measurements",()) if row.get("value")}
    if (record.get("designation") or "").strip().casefold()=="kabel" or "Kabel" in fields:
        return "Kabel","explicit"
    if source in ("rs232","file-txt") and "RISO" in fields:
        if fields & {"IB","IBer"}:
            if not fields & {"RPE","IPE"}:
                return "II","inferred"
        elif {"RPE","IPE"} <= fields:
            return "I","inferred"
    return None,"unknown"


def class_review(exam, record, source):
    selected=(exam or {}).get("procedure")
    measured,evidence=measurement_type(record,source)
    expected="Kabel" if selected in ("IEC","Verlängerung") else selected
    # The verified Class III procedure uses the Class II control on the tester.
    mismatch=bool(expected and measured and measured!=expected and (expected,measured)!=("III","II"))
    return {"selected":selected,"measured":measured,"evidence":evidence,"mismatch":mismatch}


def validate_selection(exam, record, source=None, *, resolution=None):
    if not exam:
        if resolution is not None:
            raise ValueError("Keine Abweichung zum Abgleichen.")
        return exam
    if exam["observed"]!=outcome(record["verdict"]):
        raise ValueError("Testergebnis weicht von der bestätigten Anzeige ab. Auswahl prüfen.")
    review=class_review(exam,record,source)
    if not review["mismatch"]:
        if resolution is not None:
            raise ValueError("Keine Abweichung zum Abgleichen.")
        return exam
    if resolution not in ("adopt","document"):
        raise ValueError("Schutzklasse passt nicht zur geführten Prüfung. Slot prüfen.")
    if resolution=="adopt" and review["evidence"]!="explicit":
        raise ValueError("Abgeleitete Prüfart kann nicht als Schutzklasse übernommen werden.")
    # Retain the original observations for audit, but never carry setup,
    # inspection, voltage or result confirmations to a different procedure.
    return {"examiner":exam.get("examiner"),"remarks":exam.get("remarks"),
            "procedure":review["measured"] if resolution=="adopt" else None,
            "class_reconciliation":dict(review,resolution=resolution,prior_examination=dict(exam))}
