# v0.6 Abnahme · BENNING ST 725 CH

Für v0.5 physisch bestätigt sind USB-Import, HMI-Kompilierung, Auswahl, Ausdruck und PDF. Die folgenden neuen v0.6-Pfade wurden auf dem Entwicklungsrechner getestet.

## Entwicklungsprüfung

- Handbuchausgabe 12/2021 und Originalabbildungen der Schweizer Version geprüft. [Verfahrensmatrix und Belege](../docs/benning-guided-workflows.md).
- Alle 52 Tests bestanden. Native Nextion-Ereignisse und Python zusammen im Simulator ausgeführt. Abgedeckt sind Verfahren, Warnzweige, Datenprüfung, Importvergleich, Rückwärtsnavigation, Abbruch, manuelle Auswahl und Prüfstatus.
- v0.5-Regressionssuite mit Keyboard, USB-Empfang am virtuellen Port, Datenbank-Snapshots, Druck, WLAN, Host-Watchdog, QR/PDF und lokalem Import ausgeführt.
- HMI und TFT mit dem gepinnten nxwright und Basic-Firmware aus Editor 1.68.2 gebaut. Gerätedaten und Prüfsummen geprüft. TFT 16 243 036 Bytes von maximal 16 MiB. Grösster regulärer Seitenbedarf 3160 Bytes (Keyboard). QR 1940 + 1565 = 3505 von 3584 Bytes.
- Alle Assistentenzustände im Simulator erfasst. Belegvorschauen aus den ESC/POS-Daten und PDFs aus der produktiven ReportLab-Ausgabe erzeugt. Synthetische Muster decken bestanden, nicht bestanden, unvollständig, unbekannt und Simulation ab.

## Prüfung vor dem Einsatz

- [ ] HMI in offiziellem Nextion Editor öffnen, speichern und separat kompilieren. Modell, Drehung, `keyboard` und QR-Arbeitsspeicher prüfen.
- [ ] Tasten und Ports am BENNING 050317 abgleichen. Klasse I/II auf Batterie und Netz, geeigneten SELV-Aufbau nach Handbuch, IEC und Verlängerung mit repräsentativen Prüfobjekten durch Fachperson prüfen.
- [ ] Warnungen und ungültigen Aufbau in sicheren Testfällen prüfen. Tester-Originalergebnis, fehlende Pflichtmessung, Sicht- und Funktionsbefunde vergleichen.
- [ ] USB mit STORE/RECALL und Trennung aller Prüfleitungen, unverändertem Export, eindeutigem Slot, mehreren Änderungen und Verbindungsunterbruch prüfen.
- [ ] Auf Epson Breite, 147-Punkt-Schrift, zweizeiliges FAIL, Schwärzung, Vorschub, Schnitt und Stromversorgung prüfen. PDF in Farbe und Monochrom und QR auf einem Telefon öffnen.
- [ ] WLAN, gemerkte Profile, temporären Hotspot, Standby, Helligkeit, Druckerkonfiguration, lokalen Upload und Kaltstart mit bisherigen Rechten testen.
- [ ] RS232 mit verifiziertem Adapter bench-testen. Ausgabeformat der Schweizer Firmware an der Station noch physisch ungeprüft.
- [ ] Rückkehr auf v0.5 anhand der Sicherung proben. [Pi-Anleitung](../docs/guided-v06.md).
