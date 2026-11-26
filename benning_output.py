"""Shared display rules for the Nextion, thermal receipt and PDF."""
from datetime import date, datetime
import re
from zoneinfo import ZoneInfo

from benning_csv import outcome
from i18n import locale, tr

RESULTS = {
    "PASS": ("BESTANDEN", "#67E2A7", "#146343", "#E6F6ED"),
    "FAIL": ("NICHT BESTANDEN", "#FF9A9D", "#98232C", "#FCE9E9"),
    "partial": ("UNVOLLSTÄNDIG", "#FFD08A", "#805016", "#FFF0D6"),
    "unknown": ("UNBEKANNT", "#CDD6DD", "#4E616D", "#ECF0F3"),
    "simulation": ("SIMULATION", "#8FD9F2", "#285D75", "#E5F3FA"),
}


def report_language(report):
    return locale(report.get("language"))


def resistance_unit(unit):
    if not unit:
        return unit
    match=re.fullmatch(r"([km]?)\s*(?:ohms?|Ω)",unit.strip(),re.IGNORECASE)
    return {"":"Ω","k":"kΩ","m":"MΩ"}[match[1].lower()] if match else unit


def voltage_text(voltage):
    if not voltage:
        return voltage
    return re.sub(r"(?<=\d)\s*(?=V\b)"," ",voltage,flags=re.IGNORECASE)


def show_value(value,unit):
    return " ".join(term for term in (value,resistance_unit(unit)) if term)


def date_format(language):
    return "%d/%m/%Y" if language=="en" else "%d.%m.%Y"


def tester_date(record,language="de"):
    raw=record.get("tester_date")
    if not raw:
        return ""
    try:
        if record.get("iso_date"):
            parsed=date.fromisoformat(record["iso_date"])
        else:
            parsed=datetime.strptime(raw.replace("/","."),"%d.%m.%Y")
        return parsed.strftime(date_format(language))
    except (ValueError,TypeError):
        return raw


def report_timestamp(report,language=None):
    try:
        stamp=datetime.fromisoformat(report["created"]).astimezone(ZoneInfo("Europe/Zurich"))
        return stamp.strftime(date_format(language or report_language(report))+"  %H:%M")
    except (KeyError, TypeError, ValueError):
        return ""


def protection_class(value,language):
    if language!="en" or not value:
        return value
    return tr(language,"Klasse {class_name}",class_name=value.split()[-1]) if re.fullmatch(
        r"Klasse (?:I|II|III)",value,re.IGNORECASE) else value


def verdict_text(value,language):
    kind=outcome(value or "")
    return tr(language,{"PASS":"bestanden","FAIL":"nicht bestanden"}[kind]) if kind else value


def selected_fields(report,language=None):
    language=language or report_language(report)
    record=report.get("record") or {}
    return tuple((label,value) for label,value in (
        ("Prüfnummer",report.get("ticket")),("Gerät",report.get("device")),
        ("Speicherplatz",record.get("slot")),("Prüfart",tr(language,report.get("phase",""))),
        ("Tester-Prüfdatum",tester_date(record,language)),
        ("Schutzklasse",protection_class(record.get("protection_class"),language)),
        ("Prüfspannung",voltage_text(record.get("voltage"))),
        ("Protokoll erstellt",report_timestamp(report,language) if not record else ""))
        if value)


def examination_fields(report):
    exam=report.get("examination") or {}
    return tuple((label,exam[key]) for label,key in (
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
    """Headline and raster reflect the actual tester, not the protocol."""
    if report.get("source")=="SIMULATOR":
        return "simulation"
    if report.get("source")=="EXAMINATION":
        return "partial"
    return outcome((report.get("record") or {}).get("verdict") or "") or "unknown"


def electrical_check(report):
    """Assess imported data only. Limits and wholly unused CSV columns are optional."""
    record=report.get("record") or {}
    if not record:
        return "Keine Messwerte übernommen", ()
    rows={row["name"]:row for row in visible_measurements(report)}
    verdict=outcome(record.get("verdict") or "")
    exam=report.get("examination") or {}
    protection=(record.get("protection_class") or "").upper()
    procedure=exam.get("procedure")
    csv=report.get("import_source") in ("usb","file-csv")
    required=set()
    leakage=set()
    if procedure in ("IEC","Verlängerung") or "Kabel" in rows:
        required={"RPE","RISO","Kabel"}
    elif procedure=="I" or protection=="KLASSE I":
        required={"RPE","RISO"}
        leakage={"IPE","IEA"}
        # Published CSV maps BER/IBer independently. Older BENNING exports may
        # put the replacement current in IEA and the protective current in IPE.
    elif procedure in ("II","III") or protection in ("KLASSE II","KLASSE III"):
        required={"RISO"}
        leakage={"IPE","IBer","IEA"} if not csv else {"IBer","IEA"}
    elif "FI/RCD" in rows:
        required={"FI/RCD"}
    selected_leakage=rows.keys() & leakage
    missing=sorted(required-rows.keys())
    if leakage and not selected_leakage:
        missing.append("Ableitstrom")
    relevant=required | selected_leakage
    if not relevant:
        relevant=rows.keys() & {"RPE","RISO","IPE","IBer","IEA","Kabel","FI/RCD"}
    issues=[f"{name} fehlt" for name in missing]
    for name in sorted(relevant & rows.keys()):
        row=rows[name]
        result=row.get("result")
        if name!="Kabel" and (not row.get("value") or not row.get("unit")):
            issues.append(f"{name}: Messwert oder Einheit fehlt")
        elif csv and not result:
            issues.append(f"{name}: Einzelurteil fehlt")
    if verdict=="PASS" and any(outcome(row.get("result") or "")=="FAIL" for row in rows.values()):
        issues.append("Einzelurteil widerspricht BENNING-Gesamturteil")
    if issues:
        return "Messdaten unvollständig", tuple(issues)
    if not relevant:
        return "Umfang nicht beurteilbar", ()
    if not verdict:
        return "Messwerte vorhanden", ()
    if not required and not leakage:
        return "Messwerte vorhanden · Umfang nicht beurteilbar", ()
    return "Messdaten vollständig", ()


def report_checks(report, language=None):
    """Separate electrical data, manual observations, completeness and release."""
    language=language or report_language(report)
    t=lambda key,**values:tr(language,key,**values)
    if report.get("source")=="SIMULATOR":
        return (("Elektrische Messung",t("Simulation")),)
    exam=report.get("examination") or {}
    electrical, issues=electrical_check(report)
    record=report.get("record") or {}
    visual=exam.get("visual") or next((row.get("result") for row in visible_measurements(report)
                                      if row["name"]=="Sichtprüfung" and row.get("result")),None)
    function=exam.get("functional")
    missing=[]
    if not record:
        missing.append("BENNING-Messung fehlt")
    elif not outcome(record.get("verdict") or ""):
        missing.append("BENNING-Urteil fehlt")
    elif "nicht beurteilbar" in electrical.lower():
        missing.append("Messumfang nicht beurteilbar")
    if not visual or visual in ("Offen","Ungeklärt","Mangel oder ungeklärt","Nicht geprüft","Nicht erfasst"):
        missing.append("Sichtbefund fehlt oder ist ungeklärt")
    if function not in ("Ohne Befund","Mangel"):
        missing.append("Funktionsbefund fehlt")
    if not exam.get("examiner"):
        missing.append("Prüfperson fehlt")
    voltage=exam.get("voltage_confirmed")
    measured=record.get("voltage","")
    if voltage and measured and measured.replace(" ","").upper()!=f"{voltage}V":
        missing.append(t("Prüfspannung abweichend (bestätigt: {voltage} V)",voltage=voltage))
    translated_issues=[]
    for issue in issues:
        for suffix,key in ((": Messwert oder Einheit fehlt","{name}: reading or unit missing"),
                           (": Einzelurteil fehlt","{name}: individual verdict missing"),
                           (" fehlt","{name} missing")):
            if issue.endswith(suffix) and language=="en":
                translated_issues.append(key.format(name=t(issue[:-len(suffix)])))
                break
        else:
            translated_issues.append(t(issue))
    missing=[t(reason) for reason in missing]
    missing.extend(translated_issues)
    return (("Elektrische Messung", t(electrical) + (": "+", ".join(translated_issues) if issues else "")),
            ("Sichtprüfung", t(verdict_text(visual,language) or "Nicht erfasst")),
            ("Funktion", t(function or "Nicht erfasst")),
            ("Protokoll", t("Offen: {reasons}",reasons=", ".join(missing)) if missing else t("Dokumentiert")),
            ("Freigabe", t(exam.get("release") or "Nicht erfasst · Entscheid der Prüfperson")))


def compact_checks(report,language=None):
    """The v0.6.2 printer and PDF hide redundant success and empty release."""
    language=language or report_language(report)
    t=lambda key:tr(language,key)
    items=[]
    for key,value in report_checks(report,language):
        if key=="Elektrische Messung" and value==t("Messdaten vollständig"):
            continue
        if key=="Protokoll":
            if value!=t("Dokumentiert"):
                items.append(("Offene Punkte",value.partition(": ")[2]))
            continue
        if key=="Freigabe" and value==t("Nicht erfasst · Entscheid der Prüfperson"):
            continue
        items.append((key,value))
    return items+[(key,value) for key,value in examination_fields(report) if key in ("Prüfperson","Bemerkung")]


def measurement_summary(row, *, csv_source=False, language="de"):
    state,kind=measurement_state(row)
    if csv_source and not state and not row.get("result"):
        state,kind="unvollständig","partial"
    limit=show_value(row.get("limit"),row.get("limit_unit"))
    value=show_value(row.get("value"),row.get("unit"))
    if language=="en":
        if row.get("result") and outcome(row["result"]):
            partial=state.endswith(" / unvollständig")
            state=verdict_text(row["result"],language)+(tr(language," / unvollständig") if partial else "")
        else:
            state=tr(language,state)
    name=" / ".join(filter(None,(tr(language,row["name"]),row.get("test"))))
    return name,value,limit,state,kind
