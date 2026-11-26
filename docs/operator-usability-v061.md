# FMI Printstation v0.6.1 · Bedienung und Installation

## Station im Netzbetrieb

**Geführte Prüfung** führt bei Klasse I und II direkt zum Anschluss. Am BENNING Netzanschluss, Prüfling und die für den Prüfling zulässige, angezeigte RISO-Prüfspannung kontrollieren. Die normale Stationseinstellung ist 500 V. Die Schaltfläche **Netz + 500 V geprüft** bestätigt die Kontrolle am Gerät. Sie ändert keine Geräteeinstellung. Batteriebetrieb und fachlich festgelegte 250 V bleiben unter **Abweichendes Verfahren**. Klasse III und der Leitungstest haben weiterhin ihre eigenen spannungslosen beziehungsweise netzgetrennten Aufbauten. Fachverfahren für Drehstrom und FI/RCD bleiben separat.

Die gelb hervorgehobene Taste entspricht Bild 1 des [Schweizer BENNING-Handbuchs, 050317, 12/2021](https://www.benning.de/files/benning/global_content/downloads/instruction_manuals/benning_st725_ch_version_manual.pdf). Die zwei Reihen sind von links nach rechts Diskette, Ordner, Drucker sowie Erdzeichen, Doppelquadrat, IPE/IB. Die Station erzeugt keine Prüfspannung und erkennt den aktuellen Testerzustand nicht. Sie benötigt die vom Bediener beobachtete Anzeige.

| Anzeige | Ablauf |
| --- | --- |
| Lo LOAD | Schalterstellung, Anschluss und erwartete geringe Last prüfen. Erst nach Bestätigung zeigt der Assistent erneut die physische Klassentaste 2 oder 3. Bei ungeklärter Last abbrechen. |
| I LEAK blinkt | Warnung und Prüfung von Anschluss, Last und sicherem Betrieb. Bei Klasse II isolierte Aufstellung ohne Erdpfad bestätigen. Erst danach erscheint IPE/IB (4) gelb. Die Taste am BENNING legt 230 V an die Prüfsteckdose. |
| Messung läuft | Prüfling gesichert lassen, Polaritätsstufen abwarten und die nächste Anzeige auswählen. |
| PASS / FAIL | Befund und Slot am BENNING über STORE (13) sichern. Für Klasse III und Leitungstests stehen die Einzelhinweise unter Hilfe. |
| HIGH LOAD / andere Warnung | Bei Überlast, Übertemperatur oder falschem Prüflauf abbrechen und Ursache klären. tAbLE bleibt die fachliche RPE-Bewertung am Tester. |

Die Regeln stützen sich auf §§8.1, 8.4, 9.1, 9.2 und 10 des Handbuchs. Siehe auch die [Verfahrensmatrix](benning-guided-workflows.md).

## Namensliste und Gerätevorlagen

- In **Prüfung dokumentieren → Prüfperson** einen Namen wählen und **Übernehmen** drücken. **Neu** und **Bearbeiten** verwenden die Tastatur. **Deaktivieren** benötigt **Bestätigen**. Mit **Auch inaktiv** können ausgeblendete Namen wieder aktiviert werden. Der zuletzt in einem Bericht benutzte aktive Name wird bei neuen geführten Prüfungen sichtbar vorgeschlagen.
- **Vorlagen** zeigt bis zu acht zuletzt protokollierte, unterschiedliche Beschreibungen vor den Standardvorlagen. Duplikate werden ohne Beachtung von Grossschreibung und zusätzlichen Leerzeichen zusammengeführt. Ein Eintrag füllt nur die Beschreibung. Danach kann der Text geändert oder vollständig ersetzt werden. Die Schutzklasse wird am Gerät gewählt.
- Die beiden Listen bleiben in der Stationsdatenbank. Bestehende Berichte behalten ihren ursprünglichen Namen. Neue Berichtsdaten, Verwendungszeit und Gerätehistorie werden zusammen gespeichert.

## Warum BESTANDEN und UNVOLLSTÄNDIG zusammen erschienen

In v0.6 lieferte `benning_output.result_kind()` ein gemeinsames Anzeigeetikett. Selbst mit raw `bestanden` entschied die Funktion unter anderem bei `examination.status == "Unvollständig"` für `partial`. `Guide.examination()` setzte diesen Status beispielsweise bei offenem Funktionsbefund oder fehlender Prüfperson. Die Oberfläche zeigte im kleinen Feld weiter `Tester-Original: bestanden`; das grosse Etikett sagte bereits UNVOLLSTÄNDIG. Auch unvollständige Pflichtmessdaten oder ein widersprechendes Einzelurteil konnten das gemeinsame Etikett auslösen. Die vorliegende Bench-Beobachtung enthält keine Rohdaten zur Eingrenzung auf einen dieser Auslöser.

v0.6.1 zeigt das **BENNING-Urteil** prominent und führt **elektrische Messdaten**, **Sichtprüfung**, **Funktion**, **Protokoll** und **Freigabe** separat. Nextion zeigt Details mit **Prüfdetails** und bei Bedarf **Weitere Angaben**. Fehlende Angaben werden benannt. Vollständig leere optionale Kategorien und fehlende USB-Grenzwerte zählen nicht als Mangel. Fehlende Pflichtmesswerte, fehlende Einzelurteile zu Pflichtmessungen und belegte Widersprüche werden angezeigt. Das gewählte Verfahren und die bestätigte Spannung bleiben von importierten Messwerten getrennt. Eine importierte Spannung, die von der bestätigten abweicht, erscheint ausdrücklich im Protokollstatus.

Ein vollständiges Protokoll sagt aus, dass die erforderlichen Angaben dokumentiert sind. Die Freigabe bleibt ein separater Entscheid der verantwortlichen Prüfperson und wird in der Station nicht automatisch gesetzt. Ohne erfassten Entscheid steht **Nicht erfasst**.

## Bevorzugte Firmwareinstallation per microSD

1. Den aktuellen v0.6-Checkout, die passende TFT-Datei, SQLite, Stationskonfiguration und beide systemd-Units sichern. Für den Prüfstand einen getrennten v0.6.1-Checkout und eine Datenbankkopie vorsehen.
2. HMI in Nextion Editor 1.68.2 öffnen und für **NX8048T070_011R**, 270°, 480 × 800, separat kompilieren. Kandidaten anhand von [manifest-v061.json](../hmi/build/manifest-v061.json) identifizieren. Das TFT und die HMI sind verschiedene Dateien.
3. Eine separate FAT32-microSD verwenden. 8 oder 16 GB ist für den Test ein geeigneter Ausgangspunkt. Genau eine zum Display passende **.tft** in das Wurzelverzeichnis kopieren und sicher auswerfen. Das Display ausschalten, die Karte einsetzen, dann das Display mit stabiler Versorgung einschalten.
4. Die erfolgreiche Anzeige des Uploads abwarten. Während des Schreibens die Versorgung nicht unterbrechen. Danach Display ausschalten, Karte entfernen und wieder einschalten. Nach dem Boot das Stationsmenü prüfen.
5. Den bisherigen seriellen Prozess erst für den geplanten Test stoppen. v0.6.1 verwendet HMI-Protokoll **61**. HMI und Backend als Paar starten.

   ```sh
   /usr/bin/python3 native_ui.py --port /dev/serial0 --baud 115200 --tester-mode usb \
     --auto-report-url --host 169.254.223.252 --db /tmp/rc-v061-bench.sqlite3
   bash tools/install_services.sh --render /tmp/rc-v061-units --db /tmp/rc-v061-bench.sqlite3
   systemd-analyze verify /tmp/rc-v061-units/*.service
   ```

6. Erst nach [Prüfstand-Abnahme](../hmi/VALIDATION-v061.md) die geprüften Units mit dem dauerhaften Datenbankpfad installieren. Für Rollback die beiden Dienste stoppen, v0.6.1-Daten separat sichern, v0.6-Checkout, Units und Datenbank wiederherstellen und das passende v0.6-TFT per microSD laden. Die aufbereiteten v0.6.1-Berichte bleiben in der separat gesicherten Datenbank erhalten.

[Nextion microSD-FAQ](https://m.media-amazon.com/images/I/41GXdDznw7L.pdf) · [Netzwerk, Epson und Importverwaltung](guided-v06.md)
