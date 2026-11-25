# Native HMI protocol v3

UART: 115200, 8N1, ISO-8859-15. Commands/events end with `FF FF FF`. `sendxy=0`: native buttons emit events; Python does not poll coordinates. Standard Nextion responses share the line. The bounded decoder handles arbitrary fragmentation/coalescing.

Startup sends `connect`, requires model `NX8048T070_011R`, then queries `get home.proto.val`, requiring numeric 3 (`71 03 00 00 00 FF FF FF`). A mismatch stops startup before page/baud/settings changes.

## Display → host

| Payload before terminator | Meaning |
| --- | --- |
| `RC3:BOOT` | Panel started; refresh host fields and clear stale readiness |
| `RC3:CREATE` + NUL + ticket + NUL + device | Atomic snapshot; persist a simulation |
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
| `report.tTicket`, `report.tDevice`, `report.tDate`, `report.tStatus` | Current saved simulation; written before readiness |
| `report.ready` | Set to 1 after complete data; native 200 ms timers change pages |
| `report.printing` | Native click latches 1; backend completes/resets; both suppress duplicates |
| `qrpage.qrReport`, `qrpage.qReady`, `qrpage.tNote` | URL, state (0 waiting / 1 ready / 2 unavailable), explanation |
| `history.bRow0` … `history.bRow4`, `history.tStatus` | Five-row snapshot labels; empty rows open nothing |
| `settings.tPrinter`, `settings.tUart`, `settings.tUrl` | Configured connection details |

All cross-page components have `vscope=1`. Working copy, Shift/Caps, limits, cancel/commit and every `page` instruction are native events. Python never paints or sends `page` commands. The keyboard is a regular native page, independent of the stock system-keyboard protocol.

Only `source=SIMULATOR`, `verdict=NOT TESTED` records open in this candidate. Future tester integration needs a separate reviewed contract preserving real measurements and verdicts; do not relabel genuine reports to fit this simulator UI.
