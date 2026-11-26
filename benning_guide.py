"""Offline decision graph for the BENNING ST 725 CH (050317, 12/2021)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Step:
    title: str
    instruction: str
    help: str
    phase: int
    choices: tuple
    art: str = "lcd"


OBSERVATIONS = (("Lo LOAD", "low"), ("I LEAK blinkt", "leak"),
                ("Messung läuft", "running"), ("PASS", "save"), ("FAIL", "save"),
                ("HIGH LOAD", "high"), ("Andere Warnung", "warnings"))
STOP = ("Abbrechen / unsicher", "stop")

STEPS = {
    "visual": Step("Sichtprüfung", "Prüfling, Messgerät und Leitungen auf Schäden prüfen. Arbeitsplatz und Kalibrierstatus prüfen.",
                   "Nur geschult oder unter Aufsicht arbeiten. Bei Schäden, Feuchtigkeit oder Unsicherheit stoppen. §§2, 8.1, 11.",
                   1, (("Ohne Befund", "kind"), ("Mangel", "stop"), ("Ungeklärt", "stop"))),
    "kind": Step("Prüfling einordnen", "Schutzklasse oder Leitungsart am Prüfling bestimmen.",
                  "Typenschild, Aufbau und Schutzleiter prüfen. Eine Beschreibung oder der Stecker allein reicht nicht. §§8.4, 9.",
                  2, (("Schutzklasse I", "connect1"), ("Schutzklasse II", "connect2"), ("Schutzklasse III", "class3"),
                      ("Leitung", "cable"), ("Fachverfahren", "special"))),
    "class3": Step("Schutzklasse III", "SELV-Aufbau nach Bild 5 fachlich prüfen. Kein Netz am SELV-Prüfling. Abweichende Aufbauten separat prüfen.",
                   "Das II-Programm kann bei RISO eine gesonderte III-Bewertung erfordern. Prüfvorgaben beachten. §7.10 / §9.2.",
                   3, (("Geeigneter SELV-Aufbau", "connect2"), ("Fachprüfung nötig", "stop"))),
    "cable": Step("Leitungsart wählen", "Die Leitung einzeln und ohne Verbindung zum Netz prüfen.",
                  "Geräteanschlussleitung wie Bild 6a. Verlängerung, Verteiler oder Roller wie Bild 6b. §9.3.",
                  2, (("IEC-Geräteleitung", "iec"), ("Verlängerung / Verteiler", "extension"))),
    "connect1": Step("Anschliessen · Klasse I", "Spannungslosen Prüfling an 1 anschliessen. Klemme von 9 an ein PE-Metallteil legen.",
                     "Typenschild und Last prüfen. Geräteschalter für die Prüfung einschalten. Teile ohne PE gesondert beurteilen. Bild 4, §9.1.",
                     3, (("Netz + 500 V geprüft", "start"), ("Abweichendes Verfahren", "exception"), STOP), "class1"),
    "connect2": Step("Anschliessen · Klasse II", "Prüfling spannungslos an 1. Klemme von 9 an berührbares Metallteil. Für IB den Prüfling ohne Erdpfad aufstellen.",
                     "Typenschild und Last prüfen. Geräteschalter für die Prüfung einschalten. Bild 5, §9.2.",
                     3, (("Netz + 500 V geprüft", "start"), ("Abweichendes Verfahren", "exception"), STOP), "class2"),
    "exception": Step("Abweichendes Verfahren", "Betriebsart fachlich festlegen. Prüfspannung mit Taste 5 einstellen und die Anzeige am BENNING prüfen.",
                      "250 V kann z. B. bei Überspannungsschutz nötig sein. Ersatzableitstrom auf Batterie nur bei geeignetem Aufbau ohne netzabhängige Schalter. §8.4.",
                      3, (), "key_voltage"),
    "iec": Step("IEC-Leitung anschliessen", "Netzleitung aus 11 entfernen. IEC-Leitung zwischen 1 und 10 anschliessen. Kein Gerät am Leitungsende.",
                "Bild 6a. RPE, RISO sowie L/N auf Unterbruch, Kurzschluss und Vertauschung. §9.3.1.",
                3, (("Getrennt + 500 V geprüft", "start"), ("Abweichendes Verfahren", "exception"), STOP), "iec"),
    "extension": Step("Verlängerung anschliessen", "Netzleitung aus 11 entfernen. IEC-Adapter an 10. Verlängerung zwischen 1 und Netzstecker des Adapters anschliessen.",
                      "Bild 6b. Bei Verteilern alle relevanten Ausgänge prüfen. Keine Netzspeisung. §9.3.2.",
                      3, (("Getrennt + 500 V geprüft", "start"), ("Abweichendes Verfahren", "exception"), STOP), "extension"),
    "start": Step("Prüflauf starten", "", "Gelbe Taste am BENNING drücken. Danach die tatsächlich sichtbare Anzeige unten wählen. Prüfling für Betrieb sichern. §9.",
                  4, OBSERVATIONS),
    "running": Step("Messung läuft", "Prüfling gesichert lassen. Anzeige beobachten und den nächsten Zustand wählen.",
                    "1-2 und 2-2 sind die Messstufen im Netzbetrieb. Der BENNING wechselt intern die Polarität. Stecker in Ruhe lassen.",
                    4, OBSERVATIONS),
    "warnings": Step("Andere Warnung", "Die beobachtete Meldung auswählen.",
                     "Bei unbekannter Meldung stoppen und Handbuch mit der Fachperson prüfen. §9.",
                     4, (("tAbLE / RPE", "table"), ("StOP / hot", "hot"), ("Falscher Lauf / anderes", "wrong"))),
    "low": Step("Lo LOAD · geringe Last", "Ist der Prüfling eingeschaltet? Anschluss und Last prüfen. Nur fortsetzen, wenn die geringe Last für diesen Prüfling erwartet wird.",
                "Lo LOAD allein ist kein Ergebnis. Schalter, Aufbau und erwartete Last fachlich klären. §§9.1/9.2.",
                4, (("Geringe Last bestätigt", "low_continue"), STOP)),
    "low_continue": Step("Lo LOAD · fortsetzen", "", "Für erwartete geringe Last dieselbe Klassentaste erneut drücken. Danach die echte Anzeige auswählen. §§9.1/9.2.",
                         4, OBSERVATIONS),
    "high": Step("HIGH LOAD · Stopp", "Prüfung beenden. Mögliche Überlast oder einen Fehler fachlich klären lassen.",
                 "Überlast kann Tester oder Prüfling beschädigen. Der Assistent bietet keinen Weiterlauf an. §§9.1/9.2.",
                 4, (("Abbruch dokumentieren", "exam"),)),
    "table": Step("tAbLE · RPE beurteilen", "Fachperson beurteilt RPE anhand Leitungslänge, Querschnitt und Grenzwerttabelle. Bewertung am BENNING eingeben.",
                  "§7.10 / §9.1 / §9.3.1. Die Station bewertet den Messwert nicht. Bei unklarer Bewertung stoppen.",
                  4, (("Bewertet · Anzeige lesen", "running"), STOP)),
    "hot": Step("StOP / hot", "Prüfung beenden. Tester sicher vom Netz trennen und abkühlen lassen.",
                "Keine wiederholte Dauermessung bei hoher Last. Aufbau vor erneutem Einsatz fachlich prüfen. §§9.1/9.2.",
                4, (("Abbruch dokumentieren", "exam"),)),
    "wrong": Step("Prüflauf unklar", "Prüfung sicher beenden. Schutzklasse, Betriebsart und Anschlüsse fachlich prüfen.",
                  "Bei einer falschen Wahl warnt der BENNING. Erst nach Klärung einen neuen Prüflauf starten. §8.4.",
                  4, (("Abbruch dokumentieren", "exam"),)),
    "leak": Step("I LEAK blinkt", "", "IPE (Klasse I) ist eine Differenzmessung. IB (Klasse II) ist eine direkte Messung mit isoliertem Prüfling. §§9.1/9.2.",
                 4, (("Sicherheit bestätigt", "energise"), STOP), "lcd"),
    "energise": Step("IPE/IB am BENNING drücken", "Taste 4 legt 230 V an Prüfsteckdose 1. Beide Polaritätsstufen abwarten. Prüfling gesichert lassen.",
                     "Nur im geprüften Netzaufbau ausführen. 1-2 und 2-2 sind Messstufen. Stecker während der Prüfung in Ruhe lassen. §§9.1/9.2.",
                     4, OBSERVATIONS, "key_leak"),
    "save": Step("Befund speichern", "", "Bei FAIL den Originalbefund sichern. OPEN: Unterbruch. Shor: Kurzschluss. CrOSS: L/N vertauscht. Klasse III bei RISO fachlich beurteilen.",
                 5, (("STORE + Slot gesehen", "exam"), ("FULL / nicht gespeichert", "unsaved")), "store"),
    "unsaved": Step("Kein neuer Speicherplatz", "Bei FULL keinen alten Slot verwenden. Speicherverwaltung der Fachperson überlassen.",
                    "Vor dem Löschen des Speichers die Daten exportieren. §§10.1-10.4.",
                    5, (("Ohne Messwert dokumentieren", "exam"),)),
    "stop": Step("Prüfung unterbrochen", "Prüfling und Tester sicher ausser Betrieb nehmen. Befund oder offene Frage dokumentieren.",
                 "Eine nicht durchgeführte Kontrolle bleibt im Protokoll offen.",
                 5, (("Abbruch dokumentieren", "exam"),)),
    "special": Step("Fachverfahren", "Drehstrom, FI/RCD und PRCD brauchen passende Ausrüstung und eine verantwortliche Fachperson.",
                    "Handbuch §9.4, Bilder 7a/7b (CEE). §9.5, Bilder 8a/8b (30 mA FI/RCD). Für externe Messungen «Direkt» verwenden.",
                    3, (("Ohne Messwert dokumentieren", "exam"), ("Zur Auswahl", "kind"))),
    "exam": Step("Prüfung dokumentieren", "Prüfperson auswählen und Funktion erfassen. Bemerkung bei Bedarf ergänzen.",
                 "Sichtprüfung, Funktion und Freigabe getrennt beurteilen. Die Printstation entscheidet nicht über die Freigabe.",
                 6, ()),
}


@dataclass
class Guide:
    step: str = "visual"
    visual: str = "Offen"
    procedure: str = ""
    mode: str = "Netz"
    voltage: int = 500
    observed: str = ""
    stored: bool = False
    functional: str = "Offen"
    blocked: bool = False
    history: list = field(default_factory=list)

    def data(self):
        return (self.step,self.visual,self.procedure,self.mode,self.voltage,
                self.observed,self.stored,self.functional)

    def back(self):
        if self.history and not (self.blocked and self.step!="exam"):
            (self.step,self.visual,self.procedure,self.mode,self.voltage,
             self.observed,self.stored,self.functional)=self.history.pop()
            return True
        return False

    @property
    def key(self):
        return "Doppelquadrat (3)" if self.procedure in ("II","III") else "Erdzeichen (2)"

    @property
    def art(self):
        if self.step in ("start","low_continue"):
            return "key_ii" if self.procedure in ("II","III") else "key_i"
        return STEPS[self.step].art

    def choices(self):
        if self.step=="connect2" and self.procedure=="III":
            return (("Batterie + 500 V geprüft","start"),("Abweichendes Verfahren","exception"),STOP)
        if self.step=="exception":
            if self.procedure in ("I","II"):
                return (("Netz + 250 V geprüft","start"),("Batterie + 500 V geprüft","start"),
                        ("Batterie + 250 V geprüft","start"),STOP)
            return (("Getrennt + 250 V geprüft","start"),STOP)
        return STEPS[self.step].choices

    def instruction(self):
        if self.step in ("connect1","connect2","iec","extension"):
            text=STEPS[self.step].instruction
            if self.mode=="Netz":
                text+=" Netz an 11 prüfen."
            else:
                text+=" Netz an 11 trennen." if self.procedure=="III" else ""
            return text+" 500 V am Tester prüfen, sofern geeignet."
        if self.step=="start":
            return f"Prüfling sichern und einschalten. {self.key} am BENNING drücken. Danach Anzeige unten wählen."
        if self.step=="low_continue":
            return f"Erwartete geringe Last bestätigt. {self.key} am BENNING erneut drücken."
        if self.step=="leak":
            extra=" Isoliert aufstellen, ohne Erdpfad." if self.procedure=="II" else ""
            return ("Der nächste Schritt schaltet 230 V auf die Prüfsteckdose. "
                    "Anschlüsse, Last und sicheren Lauf prüfen." + extra)
        if self.step=="save":
            return f"{self.observed} am BENNING. Diskette (13) drücken, dann STORE und Slot prüfen."
        return STEPS[self.step].instruction

    def choose(self,index):
        choices=self.choices()
        if not 0<=index<len(choices):
            return False
        label,target=choices[index]
        if self.step!=target:
            self.history.append(self.data())
        if self.step=="visual":
            self.visual=("Ohne Befund","Mangel","Ungeklärt")[index]
        elif self.step=="kind":
            self.procedure=("I","II","III","Leitung","Fachverfahren")[index]
            self.mode="Netz" if index<2 else "Batterie"
            self.voltage=500
        elif self.step=="cable":
            self.procedure=("IEC","Verlängerung")[index]
        elif self.step=="exception" and target=="start":
            self.mode="Netz" if label.startswith("Netz") else "Batterie"
            self.voltage=250 if "250" in label else 500
        elif self.step in ("connect1","connect2","iec","extension") and target=="start":
            self.mode="Netz" if self.procedure in ("I","II") else "Batterie"
            self.voltage=500
        elif choices==OBSERVATIONS:
            if label in ("PASS","FAIL"):
                self.observed=label
            elif target=="leak" and self.mode!="Netz":
                target="wrong"
            elif target in ("low","high") and self.procedure in ("IEC","Verlängerung"):
                target="wrong"
        elif self.step=="save":
            self.stored=index==0
        if self.step=="warnings" and target=="table" and self.procedure not in ("I","IEC","Verlängerung"):
            target="wrong"
        if target in ("stop","hot","high","wrong","unsaved"):
            self.blocked=True
        self.step=target
        return True

    def examination(self,examiner="",remarks=""):
        return {"visual":self.visual,"functional":self.functional,"examiner":examiner.strip(),
                "remarks":remarks.strip(),"procedure":self.procedure,"mode":self.mode,
                "voltage_confirmed":self.voltage if self.stored else None,
                "observed":self.observed}
