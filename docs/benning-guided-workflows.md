# BENNING ST 725 CH — Verfahrensgrundlage v0.6

Grundlage ist die **BENNING ST 725 CH**, Schweizer Steckersystem und Firmware, Art.-Nr. **050317**, Ausgabe **12/2021**. Die Seitenzahlen unten sind die aufgedruckten deutschen Seiten. Die Bildtafeln liegen vor Seite 1. Die Bedienungsanleitung richtet sich an Elektrofachkräfte, befähigte und elektrotechnisch unterwiesene Personen. Die Station begleitet entsprechend geschulte oder unmittelbar beaufsichtigte Personen. Sie steuert weder das Prüfgerät noch den Prüfling.

[Hersteller-PDF 12/2021](https://www.benning.de/files/benning/global_content/downloads/instruction_manuals/benning_st725_ch_version_manual.pdf) · [Hersteller-PDF über FAQ](https://www.benning.de/sbd/SVK/produkte/pruef-und-messtechnik/ger%C3%A4tetester-vde-0701-0702-0751-1/faq/faq-benning-st-725.html?cid=192932&file=files%2Fbenning%2Fglobal_content%2Fdownloads%2Finstruction_manuals%2Fbenning_st725_ch_version_manual.pdf) · [Abbildungen des gleichen Handbuchs](https://www.manualslib.de/manual/1386849/Benning-St-725.html?page=2#manual)

## Seiten und überprüfte Symbole

Die Nummerierung der deutschen Ausgabe lautet §2 Sicherheit, §3 Lieferumfang/Zubehör, §4 Gerätebeschreibung, §5 allgemeine Angaben, §6 Umgebung, §7 Messdaten, §8 Vorbereitung und Betrieb, §9 Verfahren, §10 Speicher und §11 Instandhaltung. Bild 1/2 zeigen die tatsächliche Tasten- und Buchsenanordnung. Die Tasten 2 und 3 liegen in der mittleren Reihe links und mittig, Taste 4 rechts. Taste 2 trägt das Erdzeichen, Taste 3 ein Doppelquadrat, Taste 4 die Aufschrift IPE/IB. Taste 5 links unten trägt 250 V/500 V. Oben auf der Tastatur sind von links nach rechts Diskette (13 STORE), Ordner (14 RECALL) und Drucker (15 PRINT). Oben am Gehäuse sind von links nach rechts 4 mm (9), seriell PS/2 (12), IEC (10) und Netz (11). USB (16) liegt seitlich. Prüfsteckdose (1) liegt vorne unten.

Die Originaltafel §9.1 S. 9 zeigt **tAbLE** und **Lo LOAD**. Die Abbildung §10.4 S. 18 zeigt den Ordner und Nummer **14**, nicht Taste 4 der maschinellen PDF-Extraktion. In §10.5 ist die Diskette als Rückwärtstaste beim Aufruf zu verstehen. Für den Aufruf gilt §10.2, für den Druck Taste 15. Die Gehäuseaufschrift zu ON/OFF und die Beschreibung der Zeit in §8.2 weichen voneinander ab. Bei Bedarf gemeinsam Taste 2/3 bis zur akustischen Bestätigung betätigen. Anschlussgrafiken der Station sind neu gezeichnete Funktionsschemata ohne Pinbelegung. Die Bildtafeln sind für abweichende Prüflinge massgebend.

## Gemeinsame Vorbereitung

Trockener Arbeitsplatz, unbeschädigter Prüfer, geeignete Leitungen, Prüfling und Kalibrierstatus kontrollieren. Beschädigung, Feuchtigkeit oder unklare Einstufung stoppen die geführte Messung. Schutzleiter- und Isolationswiderstand nur am spannungslosen Prüfling prüfen. Vor dem Netzbetrieb prüft die verantwortliche Person Anschluss, Lastdaten und sicheren Betrieb. §7.4/7.5 nennen für das Schalten über die Prüfsteckdose u. a. 16 A Bemessungsstrom, 3000 VA Schaltleistung und 1000 W Lampenlast. Diese Werte sind keine Erlaubnis für unbekannte Einschaltströme oder Überlasten. §7.10 enthält differenzierte Grenzwerte und Sonderfälle. Die Station überträgt diese Tabellenwerte nicht in Messdatensätze. §11.1/11.5 behandeln Ausserbetriebnahme bei Schäden/Messfehlern und das empfohlene jährliche Kalibrierintervall. Arbeiten am Gerät, Dauerverfahren und Wartung verbleiben beim Fachpersonal.

| Beleg | Gedruckte Seiten |
| --- | --- |
| Eignung, Gefahren, Zubehör, Umgebung | §§1–6, S. 1–4, Bilder 1, 2 und 10 |
| Messbereiche, Last und Grenzwerte | §7, S. 5–7 |
| Vorbereiten, Netzprüfung und Wahl der Methode | §§8.1–8.4, S. 7–8, Bild 3 |
| Gerätepflege, Sicherungen und Kalibrierung | §11, S. 19–20, Bild 9 |

## Abdeckung und Ablauf

| Verfahren | Umfang |
| --- | --- |
| Schutzklasse I, einphasig | Geführt für geeignete Geräte mit PE. Prüfsteckdose 1 plus Klemme von 9 an das fachlich ausgewählte PE-verbundene Metallteil. Der Erdzeichenknopf 2 startet RPE mit Polaritätsprüfung, danach RISO und Ableitstrom. Batterie nur für geeignete Geräte ohne netzspannungsabhängige Schaltung. Netz über 11 bei unklarem Aufbau oder netzabhängigen Schaltungen, nach Last- und Funktionsprüfung. IPE an blinkendem ILEAK startet das Differenzverfahren mit zwei Polaritäten. Berührbare, nicht PE-verbundene Teile gesondert nach §9.2 beurteilen. §§8.4, 9.1, S. 8–11, Bild 4. |
| Schutzklasse II, einphasig | Geführt für geeignete schutzisolierte Geräte. Prüfsteckdose 1 plus Klemme von 9 an die fachlich gewählte berührbare leitfähige Stelle. Doppelquadrat 3 startet RISO und Ableitstrom. Batterie für geeignete Prüflinge ohne netzabhängige Schaltung. Im Netzbetrieb mit isoliert aufgestelltem Prüfling und ohne Erdpfad startet IPE/IB 4 bei blinkendem ILEAK die direkte Berührungsstrommessung mit zwei Polaritäten. §§8.4, 9.2, S. 8 und 11–13, Bild 5. |
| Schutzklasse III | Geführte Einordnung und nur bei bestätigtem, für §9.2 geeignetem batteriebetriebenem Prüfaufbau. Fachperson prüft SELV, getrenntes Netzteil und Anschlussmöglichkeit. Keine SELV-Geräte mit Netzspannung betreiben. Doppelquadrat 3 führt das II-Programm aus. Der voreingestellte II-RISO-Grenzwert kann eine fachliche III-Bewertung nötig machen. Aussage und Daten des Testers unverändert speichern. Bei abweichender Anschlussmöglichkeit oder Spezialmethode Fachprüfung. §7.10, §9.2, S. 6–7 und 11–13, Bild 5. |
| IEC-Geräteanschlussleitung | Geführt. Netzleitung von 11 entfernen. Zu prüfende Leitung zwischen Prüfsteckdose 1 und IEC 10, kein Gerät am Ende. Erdzeichen 2. RPE, RISO, dann Durchgang/Kurzschluss/Vertauschung. Good plus PASS oder FAIL mit Einzelbefund. §9.3.1, S. 13–14, Bild 6a. |
| Verlängerung, Verteiler, Leitungsroller | Geführt. Netzleitung von 11 entfernen, geeignete IEC-Adapterleitung an 10. Prüfling zwischen Prüfsteckdose 1 und den Netzstecker der IEC-Adapterleitung anschliessen. Erdzeichen 2 und Sequenz nach §9.3.1. Alle relevanten Ausgänge beurteilen, ein Einzelbefund vertritt nicht den ganzen Verteiler. §9.3.2, S. 14, Bild 6b. |
| Dreiphasig | Fachverfahren als Verweis. Passiver CEE-Adapter bzw. aktiver Adapter 044140/044141 und je nach Aufbau geeignete Leckstromzange, Zubehör und Methode durch Fachperson. Kein simulierter Prüfpfad. §9.4, S. 14–16, Bilder 7a/7b. |
| FI/RCD, PRCD | Fachverfahren als Verweis. 30 mA-Verfahren, Unterschied fest/mobil, Anschluss und Abschaltfolgen durch Fachperson. Verweis auf §9.5, einschliesslich UB > 50 V, rESEt, Typen PRCD-S/K und Entfernen der Klemme vor RCD-Test. S. 15–17, Bilder 8a/8b. |
| Sonder- und Dauerprüfungen | Zurückgestellt. Das Handbuch beschreibt u. a. RPE-Dauermessung und ILEAK-Dauermessung. Keine Bediensequenz in v0.6. §§9.1–9.3, S. 10–14. |
| RS232-Druckausgabe zur Station | Experimentell. Hersteller belegt PT 2 an 12, nach beendeter Messung oder Auswahl im Speicher Taste 15. Adapter und tatsächliche Ausgabe der Schweizer Version an der Station separat prüfen. §10.2 und §10.5, S. 18. |

Die Spannung für RISO wird vor dem Start durch die verantwortliche Person gewählt. §8.4 nennt 500 V als Vorgabe und 250 V für geeignete Fälle mit Überspannungsableitern bzw. empfindlicher Elektronik. Anzeige mit Taste 5 überprüfen, keine pauschale Reduzierung oder Grenzwertableitung durch die Station. Im Netzverfahren bedeutet die 1-2/2-2-Anzeige die beiden Polaritäten. Die Station fordert keinen Steckerwechsel während eines anliegenden Prüfablaufs.

## Hilfe und Sperren

| Beobachtung | Reaktion im Assistenten und Quelle |
| --- | --- |
| Lo LOAD | Geringe Last, kein Ergebnis. Schalterstellung/Anschluss und erwartete Last durch Fachperson klären. Der Assistent gibt keine pauschale Fortsetzungsanweisung. §§9.1/9.2, S. 9, 11. |
| HIGH LOAD | Überlast oder Fehler möglich. Abbrechen, Prüfling sichern und Ursache/Last fachlich klären. Kein Übersteuern im Assistenten. §§9.1/9.2, S. 9–11. |
| tAbLE | Unterbrochene RPE-Bewertung. Leitungslänge, Querschnitt und Grenzwert durch qualifizierte Person nach §7.10 beurteilen. Taste 2 oder 3 betrifft die Testerentscheidung. Die Station trifft diese Entscheidung nicht. §§9.1/9.3.1, S. 9, 13–14. |
| Falscher Prüflauf, unklarer Anschluss | Stoppen und spannungslos prüfen, Schutzklasse und Aufbau neu durch Fachperson verifizieren. §§8.1/8.4, S. 7–8. |
| Blinkendes ILEAK | Nur beim bestätigten Netzverfahren. IPE/IB kann Netz auf Prüfsteckdose 1 schalten. Gesicherten Betrieb und bei direktem IB die isolierte Aufstellung bestätigen. Polaritätsstufen am Tester beobachten. §§9.1/9.2, S. 9–12. |
| StOP / hot | Messung beenden und Tester sicher vom Netz trennen, abkühlen lassen. §§9.1/9.2, S. 11–13. |
| FAIL, OPEN, Shor, CrOSS | Keinen Erfolg ableiten. Beendeten Testerbefund als solchen speichern. Bei Leitungstests stehen die Anzeigen für Unterbruch, Kurzschluss bzw. L/N-Vertauschung. §§9.1–9.3, S. 9–14. |
| PASS | Nur der beobachtete Abschluss des ausgewählten Testerlaufs. Sichtprüfung, Funktion, Prüferidentität und Bemerkung getrennt erfassen. Fachperson entscheidet nach vollständiger Prüfung über eine Freigabe. |
| Kein eindeutiger Endzustand | Keine neue Messung bestätigen. Abbruch oder als unvollständige Prüfung dokumentieren. Ein späterer Speicherimport ersetzt diese Feststellung nicht automatisch. |

## Speichern, übertragen und zuordnen

1. Endgültige Anzeige am Tester bestätigen. Mit Diskette 13 speichern, STORE und Slot am Tester prüfen. Bei FULL kein neuer Slot, Speicher nicht aus dem Assistenten löschen. §10.1, S. 17.
2. Für USB alle Anschlussleitungen und Prüfobjekte vom Tester entfernen und erst dann das USB-Kabel anschliessen. Ordner 14 etwa fünf Sekunden halten. Der Empfang auf der Station ist passiv. §10.4, S. 18.
3. Für RS232 nach beendetem Prüflauf den gespeicherten Slot mit Ordner 14, ggf. zurück mit 13, auswählen. Am Tester Drucker 15 drücken. §10.2/10.5, S. 18. Mit passendem Adapter prüfen, der Stationsbetrieb dieser Verbindung ist experimentell.
4. Die Station vergleicht Imports gegen den Workflow-Start. Nur eine eindeutig neue bzw. geänderte Messung wird automatisch vorgeschlagen. Bedienperson prüft Slot, Datum und Ergebnis. Erster Export, mehrere Änderungen, unveränderter Inhalt oder alte Daten erfordern ausdrückliche Auswahl. Der Tester exportiert keine Live-Schritte. Gerätefreigabe und schweizerische fachliche Anforderungen sind vor Ort separat zu prüfen.

Offen für die physische Abnahme sind die Abbildungstreue am vorhandenen Gerät, Varianten bei Anschluss und Firmware, die Prüfung aller Warnpfade sowie Adapter und Ausgabeformat am Schweizer RS232-Port. Die Testergebnisse und deren Grenzwerte kommen ausschliesslich aus der importierten Messung.
