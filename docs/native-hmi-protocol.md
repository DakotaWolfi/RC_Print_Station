# Native HMI UART protocol

UART: 115200, 8N1, ISO-8859-15. Commands/events end with `FF FF FF`. `sendxy=0`: native buttons emit events; Python does not poll coordinates. Standard Nextion responses share the line. The bounded decoder handles arbitrary fragmentation/coalescing.

Startup sends `connect`, requires model `NX8048T070_011R`, then queries `get home.proto.val`. The v0.5 backend requires numeric 5 (`71 05 00 00 00 FF FF FF`). A mismatch stops startup before page/baud/settings changes.

## Display → host

| Payload before terminator | Meaning |
| --- | --- |
| `RC3:BOOT` | Panel started; refresh host fields and clear stale readiness |
| `RC3:CREATE` + NUL + ticket + NUL + device | Atomic snapshot; persist a simulation. v0.5 accepts this only in explicit simulation mode. |
| `RC3:PRINT` | Submit current report with `station.receipt/send` |
| `RC3:QR` | Publish/reuse current report token URL |
| `RC3:HISTORY` | Populate five latest rows |
| `RC3:OPEN:0` … `RC3:OPEN:4` | Open corresponding host-retained history row |
| `RC3:LAST` | Open latest saved report |

Ticket/device limits are 32/64 encoded bytes. The keyboard does not offer NUL/control characters. Quotes, backslashes, colons and pipes remain data; Python escapes values before `.txt` assignments. U+00FF is excluded from display assignments because its wire byte is the delimiter; stored originals remain intact.

## Component contract

| Component | Role |
| --- | --- |
| `home.online`, `home.age`, `home.tLink`, `home.tClock`, `home.tHint` | Host heartbeat/status; does not imply printer polling |
| `entry.tTicket`, `entry.tDevice`, `entry.field`, `entry.busy`, `entry.tStatus` | Native draft, active field, creation latch and feedback |
| `report.tTicket`, `report.tDevice`, `report.tDate`, `report.tStatus` | Current saved report fields, written before readiness |
| `report.ready` | Set to 1 after complete data; native 200 ms timers change pages |
| `report.printing` | Native click latches 1; backend completes/resets; both suppress duplicates |
| `qrpage.qrReport`, `qrpage.qReady`, `qrpage.tNote` | URL, state (0 waiting / 1 ready / 2 unavailable), explanation |
| `history.bRow0` … `history.bRow4`, `history.tStatus` | Five-row snapshot labels; empty rows open nothing |
| `settings.tPrinter`, `settings.tUart`, `settings.tUrl` | Configured connection details |

All cross-page components have `vscope=1`. Working copy, Shift/Caps, limits, cancel/commit and every `page` instruction are native events. Python never paints or sends `page` commands. The keyboard is a regular native page, independent of the stock system-keyboard protocol.

## v4 settings extension

The v0.4 backend requires `home.proto.val=4`. Existing `RC3:*` report events stay unchanged. Each native page sends `sendme` on load; status replies use component names local to the current settings page. The page IDs are defined in `station_panel_settings.PAGES`. Navigation and button feedback still run on the panel.

Settings events are `RC4:SCAN/NEXT/PREV/SEL:n/JOIN`, `RC4:PASS` + NUL + password, `RC4:IP/PORT` + NUL + value, `RC4:PROBE/TEST`, `RC4:GRAPH/FEED+/FEED-/DENSITY`, `RC4:BR+/BR-/STANDBY`, and `RC4:REBOOT/HALT`. Each frame uses the existing terminator and Latin-9 encoding. Password bytes are sent once from a keyboard-local buffer, never echoed to the panel. Field initialization for printer uses a separate bounded nonsecret draft. Host state scopes commands by the announced page. The application never records raw RC4 input. Generic serial tracing tools can see UART payloads.

## v5 BENNING extension

The BENNING serial receiver runs independently from this 115200-baud Nextion interface. See the [BENNING protocol and Pi 4 guide](benning-v05.md) for its 9600-baud framing, device selection and record handling. The two ports must be distinct.

| Payload before the frame terminator | Role |
| --- | --- |
| `RC5:NEW` | Start an entry draft, record the already available import, and enable automatic slot suggestion |
| `RC5:AUTOON`, `RC5:AUTOOFF` | Change automatic suggestion for this entry |
| `RC5:REVIEW` + NUL + ticket + NUL + device + NUL + slot + NUL + phase + NUL + auto | Snapshot the native draft. Slot is empty or one to three digits. Phase 0/1/2 means Eingangsprüfung/Zwischenprüfung/Ausgangsprüfung. Auto 0/1 is explicit. Native code opens the tester page. |
| `RC5:BROWSE` | Show the available slots without arming report creation |
| `RC5:NEXT`, `RC5:PREV`, `RC5:SEL:0` … `RC5:SEL:3` | Navigate a four-row tester list and select a displayed row |
| `RC5:USE` | Confirm the selected source, import batch and internal record. Reject stale or in-progress selection. Persist before enabling the native report transition. |

`entry.tSlot`, `entry.useLast` and `entry.phase` hold the slot, checkbox value and test phase. Keyboard field 5 edits the slot when automatic suggestion is disabled. `entry.tTester` displays tester status. `entry.sim` is set by the backend from the explicit mode. `tester.mLink/mImport/mRow0..3/mSelected/mNote` carry status, count/time, page rows, selection and warnings. `mCount/mPrev/mNext/mReady/mSaving` guard native actions and the transition. The backend writes `report.tOrigin/tMeta/tResult` and the saved report fields before `report.ready`, and sets `qrpage.tKind` for source identification. All navigation still uses native `page` instructions.

Previously saved simulations and token links remain supported. Real reports retain the source, tester date, original verdict and immutable measurement snapshot. Printer, display, Wi-Fi and power events keep the v4 contract.

## v6 Assistent und Importseite

Der v0.6 Host erwartet `home.proto.val=6`. Seiten 14 `guide` und 15 `importer` kommen hinzu. Der Host liefert Texte und Zustandsflags. Touch, Tasten und Seitenwechsel bleiben nativ.

| Frame | Bedeutung |
| --- | --- |
| `RC6:NEW` | Start des Entwurfs und Baseline der Slot-Identitäten pro Quelle |
| `RC6:GUIDE`, `RC6:IMPORT`, `RC6:EXISTING` + v5 REVIEW-Felder | Eingabe in Assistent, Warte-/Empfangsseite oder bewusste Speicherwahl überführen |
| `RC6:STEP:0` … `RC6:STEP:4`, `RC6:HELP`, `RC6:BACK`, `RC6:CANCEL` | Schrittoption, Hilfe, zurück oder Abbruch |
| `RC6:FUNCTION`; `RC6:EXAM` + NUL + Prüfperson + NUL + Bemerkung | Separate Funktion und Prüfnotizen erfassen |
| `RC6:MANUAL` | Cache-Auswahl auf der Importseite |
| `RC6:VALUES` | Weitere sichtbare Messwerte des aktuellen Protokolls |

Die Bestätigung nutzt `RC5:USE`. Tastaturziel 6 ist die Prüfperson (48 Byte), Ziel 7 die Bemerkung (64 Byte). Zur Prüfverfahrenslogik siehe [Verfahrensmatrix](benning-guided-workflows.md).

## v6.1 Bedienoberfläche

Protokollkennung 61. Seite 16 `picker` verwendet `RC61:APPLIANCES/PEOPLE`, `ROW:n`, `PREV/NEXT`, `ADD/EDIT`, `NAME` (NUL + Name), `STATE`, `TOGGLE` und `USE`. `RC6:EXAM` enthält jetzt NUL + Bemerkung. `RC61:DRAFT` meldet NUL + Prüfnummer + NUL + die rohe Beschreibung, um beide Felder passend darzustellen. Die Prüfperson wird aus der Namensliste aufgelöst und als Text im Bericht eingefroren. `RC61:DETAILS` schaltet zwischen Messwerten und Prüfdetails, `RC6:VALUES` blättert in der sichtbaren Ansicht. Automatisch umbrochene Feldtexte nutzen Nextion-CRLF-Escapes an Wortgrenzen. UART- und serielle BENNING-Verbindungen bleiben getrennt.
