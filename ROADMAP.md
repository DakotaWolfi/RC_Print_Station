# Repair Café Print Station — living checklist

Status: initial development prototype (v0.1.0 target). Checked means implemented or confirmed, not necessarily hardware-tested. Update this file as milestones are verified.

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
- [ ] Verify paper width and final receipt layout
- [ ] Add printer discovery/status, error handling and reprint support
- [ ] Add Repair Café logo (confirm permission) and final receipt layout

## 4. Nextion touchscreen
- [x] Identify available display: NX8048T070_011 (7 inch, 800 × 480)
- [x] Implement serial identification probe
- [ ] Verify power supply headroom and UART signal levels
- [x] Confirm functional UART wiring and 9600 baud
- [x] Verify physical serial communication (PL011 /dev/serial0, 9600 baud, comok NX8048T070_011R)
- [ ] Create Nextion Editor HMI project and commit source
- [ ] Build home/status screen, ticket and device entry, report preview and print confirmation
- [ ] Add touchscreen keyboard and error/status feedback
- [ ] Test HMI/backend integration

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
- [ ] Add automated integration tests
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
- Printer link-local IP and raw printing verified; permanent DHCP setup outstanding. Nextion serial communication verified at 9600 baud. HMI hardware testing outstanding.
- Four initial unit tests passed. Epson printing and Nextion identification verified; runtime HMI not yet tested.
- Final receipt layout, report retention and shared power budget undecided.
