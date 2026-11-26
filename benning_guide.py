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


STEPS = {
    "visual": Step("Sichtprüfung", "Prüfling, BENNING und Leitungen auf Schäden prüfen. Trockenen Arbeitsplatz und Kalibrierstatus prüfen.",
                   "Nur geschult oder unter fachlicher Aufsicht arbeiten. Bei Schäden, Feuchtigkeit oder Unsicherheit stoppen. §§2, 8.1, 11.",
                   1, (("Ohne Befund", "kind"), ("Mangel / unklar", "stop"))),
    "kind": Step("Prüfling einordnen", "Schutzklasse bzw. Leitungsart durch die Fachperson bestimmen.",
                  "Typenschild, Aufbau und PE-Verbindung prüfen. Keine Schutzklasse aus einem Stecker allein ableiten. §§8.4, 9.",
                  2, (("Schutzklasse I", "mode1"), ("Schutzklasse II", "mode2"), ("Schutzklasse III", "class3"),
                      ("Leitung", "cable"), ("Fachverfahren", "special"))),
    "mode1": Step("Betriebsart · Klasse I", "Batterie nur bei bekanntem Aufbau ohne netzabhängige Schalter. Bei unklarem Aufbau oder netzabhängiger Schaltung Netzverfahren prüfen.",
                   "Batterie: Ersatzableitstrom. Netz: IPE im Differenzverfahren. Lastdaten und sicheren Betrieb zuerst prüfen. §8.4, §9.1.",
                   2, (("Batterie geeignet", "connect1"), ("Netz fachlich geprüft", "connect1"), ("Unklar / Stopp", "stop"))),
    "mode2": Step("Betriebsart · Klasse II", "Batterie nur bei bekanntem Aufbau ohne netzabhängige Schalter. Netzbetrieb erfordert isolierte Aufstellung für den direkten Berührungsstrom.",
                   "Batterie: Ersatzableitstrom. Netz: direkter IB, kein Erdpfad am Prüfling. Lastdaten und sicheren Betrieb prüfen. §8.4, §9.2.",
                   2, (("Batterie geeignet", "connect2"), ("Netz fachlich geprüft", "connect2"), ("Unklar / Stopp", "stop"))),
    "class3": Step("Schutzklasse III", "SELV und Anschluss durch die Fachperson prüfen. Nur geeigneten Aufbau nach Bild 5 verwenden. Kein Netz am SELV-Prüfling.",
                   "Der Tester verwendet den II-Prüflauf. Ein RISO-Fehler nach II-Grenze kann eine separate III-Bewertung erfordern. §7.10 / §9.2.",
                   2, (("Batterieaufbau geprüft", "connect2"), ("Fachprüfung nötig", "stop"))),
    "cable": Step("Leitung auswählen", "Die Leitung muss separat und ohne Verbindung zum Netz geprüft werden.",
                  "Geräteanschlussleitung wie Bild 6a. Verlängerung, Verteiler oder Roller wie Bild 6b. §9.3.",
                  2, (("IEC-Geräteleitung", "iec"), ("Verlängerung / Verteiler", "extension"))),
    "connect1": Step("Anschluss · Klasse I", "Prüfling spannungslos an Prüfsteckdose 1. Klemme von 9 an fachlich ausgewähltes PE-verbundenes Metallteil. Netz an 11 nur im gewählten Netzbetrieb.",
                     "Bild 4. Berührbare Teile ohne PE separat fachlich prüfen. Geräteschalter für die Messung einschalten. Auf sicheren Betrieb achten. §9.1.",
                     3, (("Aufbau geprüft", "voltage"), ("Unklar / Stopp", "stop")), "class1"),
    "connect2": Step("Anschluss · Klasse II/III", "Prüfling spannungslos an Prüfsteckdose 1. Klemme von 9 an fachlich gewähltes berührbares leitfähiges Teil. Netz an 11 nur bei Klasse II im Netzbetrieb.",
                     "Bild 5. Bei direktem IB isoliert aufstellen, ohne Erdpfad. SELV-Aufbau nur nach Vorgabe der Fachperson. Geräteschalter für die Messung einschalten.",
                     3, (("Aufbau geprüft", "voltage"), ("Unklar / Stopp", "stop")), "class2"),
    "iec": Step("IEC-Leitung anschliessen", "Netzleitung aus 11 entfernen. Zu prüfende Geräteleitung zwischen Prüfsteckdose 1 und IEC-Anschluss 10. Kein Gerät am Leitungsende.",
                "Bild 6a. Der Tester prüft RPE, RISO und L/N auf Unterbruch, Kurzschluss und Vertauschung. §9.3.1.",
                3, (("Netz getrennt / bereit", "start"), ("Unklar / Stopp", "stop")), "iec"),
    "extension": Step("Verlängerung anschliessen", "Netzleitung aus 11 entfernen. IEC-Adapter an 10. Verlängerung zwischen Prüfsteckdose 1 und Netzstecker des IEC-Adapters anschliessen.",
                      "Bild 6b. Bei Verteilern alle relevanten Ausgänge prüfen und zuordnen. Keine Netzspeisung. §9.3.2.",
                      3, (("Netz getrennt / bereit", "start"), ("Unklar / Stopp", "stop")), "extension"),
    "voltage": Step("RISO-Prüfspannung", "Fachlich festgelegte Prüfspannung am BENNING kontrollieren. Taste 5 schaltet zwischen 250 V und 500 V um.",
                    "500 V ist voreingestellt. 250 V nur passend zur Prüfung, etwa bei Überspannungsableitern oder empfindlicher Elektronik. §8.4.",
                    3, (("500 V geprüft", "start"), ("250 V geprüft", "start"), ("Unklar / Stopp", "stop")), "keys"),
    "start": Step("Prüflauf starten", "Passende physische Taste am BENNING drücken und die Anzeigen beobachten.",
                  "Die Station sieht keine Live-Anzeige. Nur vom BENNING tatsächlich angezeigte Zustände auswählen. Falscher Prüflauf: abbrechen und Aufbau prüfen. §9.",
                  4, (("Gestartet", "observed"), ("Falscher Prüflauf", "wrong")), "keys"),
    "observed": Step("Was zeigt der BENNING?", "Den aktuellen Zustand am Tester ablesen. Eine Anzeige auswählen.",
                     "1-2 und 2-2 sind Messstufen. Einen abschliessenden Befund erst nach dem Ende des Testerlaufs wählen. §9.",
                     4, (("PASS", "save"), ("FAIL / Leitungsfehler", "failed"), ("ILEAK blinkt", "leak"),
                         ("Warnung / Pause", "warnings"), ("Keine Endanzeige", "running"))),
    "warnings": Step("Warnung auswählen", "Nur die tatsächlich angezeigte Meldung auswählen.",
                     "Bei unbekannter Anzeige Messung sicher beenden und das Handbuch mit einer Fachperson prüfen. §9.",
                     4, (("Lo LOAD", "low"), ("HIGH LOAD", "high"), ("tAbLE / RPE", "table"),
                         ("StOP / hot", "hot"), ("Falscher Lauf / anderes", "wrong"))),
    "low": Step("Lo LOAD · geringe Last", "Schalterstellung, Anschluss und erwartete Last fachlich klären. Nur am BENNING weiterarbeiten, wenn die Fachperson die Ursache geklärt hat.",
                "Ein ausgeschalteter Prüfling kann diese Anzeige verursachen. Lo LOAD ist weder PASS noch Nachweis einer sicheren Prüfung. §§9.1/9.2.",
                4, (("Geprüft · Anzeige lesen", "observed"), ("Ungeklärt · Stopp", "stop"))),
    "high": Step("HIGH LOAD · Stopp", "Prüfung sicher beenden. Mögliche Überlast oder Fehler beim Prüfling durch die Fachperson klären lassen.",
                 "Überlast kann Tester oder Prüfling beschädigen. Die Station bietet hier keine Fortsetzung des Prüflaufs an. §§9.1/9.2.",
                 4, (("Unvollständig erfassen", "exam"),)),
    "table": Step("tAbLE · RPE beurteilen", "Fachperson beurteilt RPE anhand Leitungslänge, Querschnitt und Grenzwerttabelle. Bewertung ausschliesslich am Tester.",
                  "§7.10 / §9.1 / §9.3.1. Der Assistent bewertet diesen Messwert nicht. Bei unklarer Bewertung abbrechen.",
                  4, (("Bewertet · Anzeige lesen", "observed"), ("Ungeklärt · Stopp", "stop"))),
    "hot": Step("StOP / hot", "Prüfung beenden, Tester sicher vom Netz trennen und abkühlen lassen.",
                "Keine wiederholte Dauermessung bei hoher Last. Prüfer und Aufbau vor erneutem Einsatz fachlich kontrollieren. §§9.1/9.2.",
                4, (("Unvollständig erfassen", "exam"),)),
    "wrong": Step("Aufbau oder Prüflauf unklar", "Prüfung sicher beenden. Schutzklasse, Betriebsart und Anschlüsse durch die Fachperson neu prüfen.",
                  "Bei falscher Wahl liefert der Tester einen Hinweis. Weiter erst nach fachlicher Klärung und neuem Prüflauf. §8.4.",
                  4, (("Unvollständig erfassen", "exam"),)),
    "leak": Step("ILEAK blinkt", "Nur bei sicherem Aufbau im gewählten Netzbetrieb IPE/IB am BENNING drücken. Taste 4 schaltet Netz auf den Prüfling.",
                 "IPE bei Klasse I im Differenzverfahren. IB bei Klasse II direkt und isoliert. Den Prüfling sichern und beide Polaritätsstufen abwarten. §§9.1/9.2.",
                 4, (("Sicher · IPE/IB gedrückt", "polarity"), ("Unklar / Stopp", "stop")), "keys"),
    "polarity": Step("Beide Polaritäten abwarten", "Stufen 1-2 und 2-2 am BENNING beobachten. Beim Wechsel keinen Stecker umdrehen. Urteil erst nach Abschluss ablesen.",
                     "Der Tester polt die Prüfsteckdose automatisch um und zeigt den höchsten Wert an. §§9.1/9.2.",
                     4, (("Endanzeige ablesen", "observed"), ("StOP / hot", "hot"), ("Unklar / Stopp", "stop"))),
    "running": Step("Ende des Prüflaufs abwarten", "Nur eine abgeschlossene Anzeige als PASS oder FAIL erfassen.",
                    "Keine elektrische Messung wird aus einer Eingabe an der Printstation abgeleitet. Bei Abbruch unvollständig erfassen. §9.",
                    4, (("Anzeige erneut lesen", "observed"), ("Unvollständig erfassen", "exam"))),
    "failed": Step("FAIL · Befund sichern", "Negativen Testerbefund beibehalten. Bei Leitungen OPEN, Shor oder CrOSS beachten. Bei Klasse III RISO fachlich beurteilen lassen.",
                   "OPEN: Unterbruch. Shor: Kurzschluss. CrOSS: L/N vertauscht. Klasse III kann eine fachliche Sonderbewertung erfordern. §§9.2/9.3.",
                   5, (("Beendeten Befund speichern", "save"), ("Unvollständig erfassen", "exam"))),
    "save": Step("Messung im Tester speichern", "Diskettentaste 13 drücken. STORE und Speicherplatz kontrollieren.",
                 "Nur abgeschlossenen Befund speichern. Bei FULL Speicher nicht hier löschen. Slot und Testergebnis für den Import merken. §10.1.",
                 5, (("STORE und Slot gesehen", "exam"), ("FULL / nicht gespeichert", "unsaved")), "store"),
    "unsaved": Step("Kein neuer Speicherplatz", "Keinen alten Slot als neuen Test verwenden. Bei FULL die Speicherverwaltung der Fachperson überlassen.",
                    "Vor dem Löschen des Testerspeichers exportieren und Rückverfolgbarkeit sichern. §§10.1–10.4.",
                    5, (("Unvollständig erfassen", "exam"),)),
    "stop": Step("Prüfung unterbrochen", "Prüfling und Tester sicher ausser Betrieb nehmen und Befund oder offene Frage festhalten.",
                 "Eine nicht abgeschlossene Sicht- oder Funktionsprüfung bleibt im Protokoll offen. Fachperson entscheidet über weiteres Vorgehen.",
                 5, (("Unvollständig erfassen", "exam"),)),
    "special": Step("Fachverfahren", "Drehstrom, FI/RCD und PRCD nur mit geeigneter Ausstattung und verantwortlicher Fachperson prüfen.",
                    "Handbuch §9.4, Bilder 7a/7b (CEE-Adapter); §9.5, Bilder 8a/8b (30 mA FI/RCD). Direkteingabe für extern dokumentierte Messungen.",
                    3, (("Unvollständig erfassen", "exam"), ("Zur Auswahl", "kind"))),
    "exam": Step("Prüfung dokumentieren", "Name und Bemerkung eingeben. Funktionsbefund getrennt vom Testergebnis erfassen.",
                 "Verantwortliche Fachperson beurteilt die vollständige Prüfung und entscheidet separat über die Freigabe.",
                 6, ()),
}


@dataclass
class Guide:
    step: str = "visual"
    visual: str = "Offen"
    procedure: str = ""
    mode: str = ""
    observed: str = ""
    stored: bool = False
    functional: str = "Offen"
    blocked: bool = False
    history: list = field(default_factory=list)

    def data(self):
        return self.step,self.visual,self.procedure,self.mode,self.observed,self.stored,self.functional

    def back(self):
        if self.history and not (self.blocked and self.step!="exam"):
            self.step,self.visual,self.procedure,self.mode,self.observed,self.stored,self.functional=self.history.pop()
            return True
        return False

    def instruction(self):
        if self.step=="start":
            key="Doppelquadrat (3)" if self.procedure in ("II","III") else "Erdzeichen (2)"
            return f"Taste {key} am BENNING drücken. Prüfling sichern und Testeranzeige beobachten."
        return STEPS[self.step].instruction

    def choose(self,index):
        choices=STEPS[self.step].choices
        if not 0<=index<len(choices):
            return False
        _,target=choices[index]
        self.history.append(self.data())
        if self.step=="visual":
            self.visual=("Ohne Befund","Mangel oder ungeklärt")[index]
        elif self.step=="kind":
            self.procedure=("I","II","III","Leitung","Fachverfahren")[index]
        elif self.step.startswith("mode"):
            self.mode=("Batterie","Netz","")[index]
        elif self.step=="class3":
            self.mode="Batterie" if index==0 else ""
        elif self.step=="cable":
            self.procedure=("IEC","Verlängerung")[index]
            self.mode="Batterie"
        elif self.step=="observed":
            if index==0:
                self.observed="PASS"
            elif index==1:
                self.observed="FAIL"
            elif index==2 and self.mode!="Netz":
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
        completed=self.visual=="Ohne Befund" and self.functional in ("Ohne Befund","Mangel") and bool(examiner.strip()) and self.stored and bool(self.observed)
        return {"visual":self.visual,"functional":self.functional,"examiner":examiner.strip(),
                "remarks":remarks.strip(),"procedure":self.procedure,"mode":self.mode,
                "observed":self.observed,"status":"Erfasst" if completed else "Unvollständig"}
