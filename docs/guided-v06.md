# v0.6 auf dem Raspberry Pi 4B

**Geführte Prüfung** begleitet geschulte oder fachlich beaufsichtigte Personen am BENNING ST 725 CH (050317). **Direkt** öffnet die Eingabe mit **Messung importieren** und **Vorhandene Messung**. Beide Wege verwenden dieselben SQLite-Daten und Ausgabefunktionen. Hilfe bleibt lokal am Display verfügbar. Details und Grenzen stehen in der [Handbuch-Zuordnung](benning-guided-workflows.md).

## Geführter und direkter Ablauf

- Prüfnummer, Gerät und Prüfart erfassen. Zurückblättern behält die Eingaben. Ein neues Protokoll am Startbildschirm beginnt einen neuen Entwurf.
- Im Assistenten die beobachteten Zustände am BENNING auswählen. Nach einem unsicheren oder abgebrochenen Lauf kann ein unvollständiges Protokoll mit Sichtbefund, Funktionsbewertung, Prüfperson und Bemerkung gespeichert werden. Es enthält keine erfundene elektrische Messung.
- Nach abgeschlossener Messung STORE und Slot am Tester prüfen. Der Import zeigt Verbindung, Verfahren, Empfang und Fehler. USB erfordert das Entfernen aller Anschlussleitungen und Prüfobjekte vor dem Anschliessen des USB-Kabels. Bei RS232 im gespeicherten Slot PRINT drücken. Der Stationsbetrieb von RS232 ist experimentell.
- Eine einzelne neue oder geänderte Slot-Identität seit Workflow-Start öffnet die Bestätigung. Erster Import, unveränderte Wiederholung, mehrere Änderungen, Speicher-Reset oder alter Cache erfordern eine bewusste Auswahl. Ein erstmals an einer gültigen Zeilengrenze abgebrochener Export kann ohne bekannte Ende-Markierung vollständig aussehen. Slot und Datum gegen das Testerdisplay prüfen.
- Bericht drucken oder PDF per QR herunterladen. Die ursprüngliche Tester-Aussage bleibt erhalten. Die verantwortliche Prüfperson entscheidet nach vollständiger Prüfung über die Freigabe.

Auf dem Beleg sind BESTANDEN-Buchstaben 147 Punkte hoch (rund 18,4 mm bei 203 dpi). NICHT BESTANDEN steht auf zwei Zeilen. Masse und Schwärzung am eigenen Drucker prüfen. Abwesende Kategorien werden ausgeblendet. Vergleichszeichen, Werte, Einheiten, übertragene Grenzen und Einzelbefunde bleiben erhalten. Das PDF trennt die Einträge der Prüfperson von den Daten des BENNING.

## Installation auf dem Prüfstand

1. Aktuell eingesetztes v0.5-HMI/TFT, Pi-Checkout, beide systemd-Units, Stationskonfiguration und Datenbank sichern. SQLite-Backup verwenden oder Schreibdienste vor der Kopie stoppen. WLAN-Profile, Hotspot-Berechtigungen und Drucker-Ethernet beibehalten.
2. Einen separaten Checkout für `feature/guided-testing-v06` und eine Datenbankkopie verwenden. Die Pi-Voraussetzungen und Schnittstellenparameter aus der [v0.5 Anleitung](benning-v05.md) gelten weiter.
3. Die v0.6-HMI in **Nextion Editor 1.68.2** öffnen. NX8048T070_011R, 270°, 480 × 800, 115200 Baud und Seite `keyboard` prüfen. Unter einem eigenen Namen kompilieren. Nur für einen geplanten Test am Entwicklungsdisplay aufspielen.
4. Den bisherigen seriellen Prozess beim geplanten Test stoppen. Kandidaten mit der vorhandenen Schnittstellenkonfiguration starten.

   ```sh
   /usr/bin/python3 native_ui.py --port /dev/serial0 --baud 115200 --tester-mode usb \
     --auto-report-url --host 169.254.223.252 --db /tmp/rc-v06-bench.sqlite3
   bash tools/install_services.sh --render /tmp/rc-v06-units --db /tmp/rc-v06-bench.sqlite3
   systemd-analyze verify /tmp/rc-v06-units/*.service
   ```

   v0.6 verwendet HMI-Protokoll 6. Bei einer anderen Protokollversion bricht der Backendstart vor dem Senden von Einstellungen ab.

5. Erst nach [Bench-Abnahme](../hmi/VALIDATION-v06.md) die verifizierten Units mit dem freigegebenen dauerhaften Datenbankpfad installieren. Das vorhandene Skript sichert die alten Units, wenn `--replace` bewusst gesetzt wird. Dienste gezielt starten und Kaltstart prüfen.

## Rückkehr zu v0.5

Beide v0.6-Dienste stoppen und die v0.6-Datenbank für neue Berichte und Prüfnotizen separat sichern. Gesicherte v0.5-Units, Checkout, Datenbank und zugehöriges v0.5-TFT wiederherstellen. systemd neu laden und beide Dienste starten. USB, Auswahl, Epson-Ausgabe und QR prüfen. v0.5 kann Berichte ohne BENNING-Messung aus dem Assistenten nicht anzeigen. Die gesicherte v0.5-Datenbank verwenden.
