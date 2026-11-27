"""Display-independent guards for BENNING examination and import selection."""
from benning_csv import outcome


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


def validate_selection(exam, record):
    if not exam:
        return
    if exam["observed"]!=outcome(record["verdict"]):
        raise ValueError("Testergebnis weicht von der bestätigten Anzeige ab. Auswahl prüfen.")
    actual=(record.get("protection_class") or "").upper()
    expected={"I":{"KLASSE I"},"II":{"KLASSE II"},"III":{"KLASSE II","KLASSE III"}}
    classes=expected.get(exam["procedure"],set())
    if classes and actual and actual not in classes:
        raise ValueError("Schutzklasse passt nicht zur geführten Prüfung. Slot prüfen.")
