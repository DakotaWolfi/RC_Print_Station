# FMI Printstation v0.6.1 · Abnahme

## Entwicklungsprüfung

- BENNING CH, Art.-Nr. 050317, Handbuchstand 12/2021, Bild 1/2 und §§8.4, 9.1, 9.2, 10 überprüft. Alternative RISO-Spannung und netzgetrennte Verfahren bleiben verfügbar.
- Alle 63 automatisierten Tests bestanden. Enthalten sind Standard- und abweichende Betriebsart, Lo LOAD, I LEAK, USB-Import, Prüferverwaltung, Duplikate der Gerätehistorie, Textumbruch und eindeutige Berichtsfelder.
- Den v0.6-Darstellungsfehler mit einem BESTANDEN-Import und offenen Prüfungsangaben nachgestellt. Separate Layoutmuster für vollständiges PASS, PASS mit offenen Angaben, fehlenden Pflichtmesswert, FAIL, unbekannt und Simulation.
- Alle Projektseiten und die wesentlichen Zustände des Assistenten im Simulator gerendert.
- Kandidat mit nxwright und Nextion Basic Firmware 1.68.2 kompiliert. HMI-Protokoll 61, 480 × 800, 270°, 115200 Baud. TFT 15 785 244 Bytes. RAM Assistent 3432 Bytes und QR 3493 Bytes inklusive Arbeitsbereich, jeweils von 3584 Bytes. Offizieller Editor und physische Prüfung für v0.6.1 stehen aus.

## Vor Einsatz am Prüfstand

- [ ] HMI in offiziellem Nextion Editor kompilieren und Modell, Drehung und Seite `keyboard` prüfen.
- [ ] TFT per FAT32-microSD am getrennten Prüfstand installieren und mit dem passenden Pi-Backend starten.
- [ ] Tastenillustrationen und Einreihung am CH-Prüfgerät vergleichen. Standardanschluss, 500 V Bestätigung und abweichenden Aufbau prüfen.
- [ ] Lo LOAD im geeigneten sicheren Testfall testen. Für Klasse I Taste 2 und für Klasse II Taste 3, nur bei bestätigter erwarteter geringer Last. Bei I LEAK den Sicherheitsschritt und gelbe Taste 4 kontrollieren.
- [ ] Netzgetrennten Leitungstest sowie passende SELV-Verfahren separat prüfen. USB/RS232-Import und bestehende Sicherheitsabzweige nachvollziehen.
- [ ] Namen hinzufügen, wählen, umbenennen, deaktivieren, aktivieren und nach Neustart die Reihenfolge und alten Berichtsnamen prüfen. Gerätevorlagen und lange Beschreibung bearbeiten.
- [ ] BESTANDEN, Messdaten, Sicht/Funktion, offene Felder und Freigabe auf Display, Beleg und PDF vergleichen. Wi-Fi, Hotspot, Drucker, Standby, Upload und Kaltstart prüfen.
- [ ] Wiederherstellung einer passenden v0.6-TFT/Backend-Kombination und der Datenbanksicherung proben.

[Vorgehen und microSD-Anleitung](../docs/operator-usability-v061.md)
