# Repair Café Print Station — living checklist

Status: working legacy hybrid prototype plus separate native HMI v0.3 candidate. Checked means implemented or confirmed, not necessarily hardware-tested. The candidate is not approved for replacing the working installation. See [validation evidence](hmi/VALIDATION.md).

## 1. Project foundation
- [x] Create GitHub repository
- [x] Choose Raspberry Pi 4B (former PT35) as development host
- [x] Choose Orange Pi Zero 3 (1 GB) as production host
- [x] Add Python CLI and setup documentation
- [x] Add simulated report storage in SQLite
- [x] Add four initial unit tests (not yet executed)
- [x] Run unit tests and record results (4 passed on Raspberry Pi 4)
- [ ] Split backend into modular display, printer, tester and storage drivers
- [ ] Add configurable hardware settings and versioning

## 2. Raspberry Pi bring-up
- [x] Finish PT35 SD card backup (7-Zip integrity test passed; boot restoration not tested)
- [x] Boot existing installation and connect over SSH
- [ ] Clone repository and run diagnostic command
- [ ] Identify and disable conflicting PT35 services only
- [ ] Verify Python dependencies and serial permissions
- [ ] Keep existing SSH and networking functional

## 3. Epson thermal printer
- [x] Implement initial raw TCP ESC/POS test receipt
- [x] Connect Epson Gen 3 via dedicated Ethernet
- [x] Identify printer IP and verify TCP port (169.254.223.252:9100, link-local)
- [ ] Implement isolated, configurable DHCP if required; never enable on shared network
- [x] Verify physical text printing and cutter; ESC J 240 pre-cut feed confirmed working
- [ ] Verify paper width, PC850 character encoding and polished v0.2 receipt layout
- [ ] Add printer discovery/status, error handling and reprint support
- [ ] Add Repair Café logo (confirm permission) and final receipt layout

## 4. Nextion touchscreen
- [x] Identify available display: NX8048T070_011 (7 inch, 800 × 480)
- [x] Implement serial identification probe
- [ ] Verify power supply headroom and UART signal levels
- [x] Confirm functional UART wiring and 9600 baud
- [x] Verify physical serial communication (PL011 /dev/serial0, 9600 baud, comok NX8048T070_011R)
- [x] Preserve original compiling HMI and add separate editable native candidate with font resources
- [x] Implement Pi-driven runtime HMI
- [x] Implement home/status, ticket and device entry and demo report preview
- [x] Create and render polished native home, input, report, QR, history and station pages
- [ ] Validate native layout on the physical portrait display
- [x] Native keyboard text return and physical receipt confirmed by user
- [x] Implement native Swiss QWERTZ keyboard, Shift/Caps, umlauts, accents, symbols and euro; pass simulator tests
- [ ] Validate native keyboard on resistive touch hardware
- [x] Test HMI/backend integration (runtime UI and physical printing confirmed)
- [ ] Verify 270-degree portrait orientation and touch alignment
- [ ] Validate physical mixed-case/umlaut entry and candidate UART at 115200 separately

## 5. Electrical safety tester — BLOCKED on identification
- [ ] Obtain manufacturer, model and firmware from colleague
- [ ] Arrange access to tester for bench testing
- [ ] Identify connectors, USB enumeration and documented export protocol
- [ ] Capture sample reports with no personal data
- [ ] Implement read-only retrieval of latest report
- [ ] Preserve original measurements, units, limits and tester verdict
- [ ] Validate against original tester reports; never infer a safety pass
- [ ] Handle missing, stale, duplicate and incomplete reports
- [ ] Keep simulated reports unmistakably marked and separate from genuine records

## 6. Application integration
- [ ] Link repair ticket and appliance name to retrieved report
- [ ] Store genuine reports and support history/reprinting
- [ ] Add local administration and configuration interface
- [ ] Handle disconnected hardware and interrupted print jobs
- [x] Add native-event/serial/backend integration tests, printing failure tests and HTTP PDF download test
- [ ] Verify full offline workflow on Raspberry Pi 4
- [ ] Review data retention and access with Repair Café

## 7. Production migration
- [ ] Receive Orange Pi Zero 3
- [ ] Install fresh supported Linux image
- [ ] Configure UART, Ethernet and USB
- [ ] Install app and systemd service
- [ ] Verify memory use and boot recovery
- [ ] Repeat all hardware and end-to-end tests

## 8. Power and enclosure
- [ ] Use separate supplies during development
- [ ] Measure printer, SBC and display combined peak current
- [ ] Select suitable 24 V to 5 V converter and verify supply headroom
- [ ] Design enclosure, mounting, ventilation and cable strain relief
- [ ] Test sustained printing and power interruption recovery

## 9. Deployment
- [ ] Demonstrate complete workflow to Repair Café team
- [ ] Verify receipt content and operational acceptance
- [ ] Document installation, operation, troubleshooting and backups
- [ ] Tag first validated release

## Current blockers / open decisions
- Tester make/model and protocol unknown (red enclosure is the only known clue).
- Pi SD card backup completed and archive integrity verified.
- Printer link-local IP and raw printing verified; permanent DHCP setup outstanding. Legacy Nextion communication and touchscreen printing confirmed at 9600; physical native portrait touch, 115200 and keyboard checks remain outstanding.
- Native v0.3 candidate: editable HMI built, TFT compiled, 19 automated tests pass, source/HMI round trip and TFT format/recompile checks pass. Official Editor open/compile and physical receipt/phone QR acceptance are still required. Working HMI and `nextion_ui.py` remain preserved.
- Final receipt layout, report retention and shared power budget undecided.

## Native v0.3 candidate acceptance
- [x] Investigate HMI generation and reverse-engineering tools; record choices and limits
- [x] Extract the latest compiling user HMI without unknown-format warnings
- [x] Preserve its bytes and hash under `hmi/reference/`
- [x] Build unlocked, editable `FMI_RC_native_v0_3.HMI`; distribute exact bytes in `hmi/build/FMI_RC_native_v0_3.zip`
- [x] Compile a separate Basic-series TFT within 16 MB flash
- [x] Keep page rendering, keyboard and transitions native; use protocol v3 for backend actions
- [x] Fit all page/global memory and QR temporary memory within 3584 bytes
- [x] Preserve existing German receipt/cutter bytes; render euro as EUR for PC850
- [x] Keep simulations visibly labelled on home, report, QR, receipts and PDFs
- [x] Add host heartbeat, preserved drafts, print duplicate suppression and no automatic print retry
- [x] Document startup, protocol, editing and rollback; add CI checks
- [ ] Open/save/recompile candidate in official Nextion Editor 1.68.2
- [ ] Verify 270° orientation and touch alignment on NX8048T070_011R
- [ ] Verify 115200 after cold boots and host restarts
- [ ] Verify all keyboard banks, Shift/Caps, cancel/commit and maximum field lengths physically
- [ ] Print a simulation through the complete native workflow; compare umlauts, feed and cutter
- [ ] Scan actual PDF link on a phone on the same LAN; verify simulation marking
- [ ] Test cable disconnect, printer timeout and rollback on the bench
- [ ] Only then adopt/merge the native candidate as the working installation
