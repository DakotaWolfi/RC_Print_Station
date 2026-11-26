# v0.5 validation · BENNING ST 725

Target: **Nextion Basic NX8048T070_011R**, portrait 270°, 480 × 800, 115200 baud. Host: Raspberry Pi 4B. The BENNING USB receiver uses its own 9600 baud 8N1 device.

## Completed in development

- The development suite passed all 41 tests. Parser tests use the three supplied USB transcript rows re-encoded as fixtures and clearly identified synthetic pass/fail, missing and interrupted inputs. Raw USB bytes from the Pi were unavailable for independent codec verification.
- Receiver exercised on a pseudo-terminal with fragmented transfer and disconnect. The test checks that the host sends no bytes on the tester port and that a partial transfer leaves the accepted snapshot intact.
- SQLite tests cover duplicate/cache behavior, short snapshots, multiple changed slots and immutable historical reports after a slot overwrite.
- Native simulation covers slot entry, automatic suggestion and explicit confirmation, stale selection after a new import, phase, legacy simulation and the v0.4 regressions.
- Validated source and built an editable HMI and compiled TFT with pinned nxwright and a 1.68.2 Basic-series firmware bundle. The panel budget is 3,584 bytes and 16 MiB flash. The 14,524,372-byte TFT passed its structural checksums. The largest normal page allocation is keyboard at 2,956 bytes. QR uses 1,736 bytes plus up to 1,565 bytes of QR working space (3,301 total).
- Generated and rendered real CSV and RS232 sample PDFs for review. Checked graphical receipt output, historical simulation behavior and download-only public HTTP routing in regression tests.
- Validated the posted RS232 byte dump in CP437 with reported measurements and limits. The independently captured USB byte stream and physical RS232 adapter remain to be checked.

## Official Editor and physical Pi 4

- [ ] Open the editable HMI copy in official Nextion Editor 1.68.2. Verify NX8048T070_011R, 270°, 480 × 800, page name `keyboard` and all page memory reports. Compile and save under a separate candidate name.
- [ ] On a development display, verify 115200 baud, touch alignment, native keyboard modes, password masking, slot input, phase cycling and the checkbox enabled on each new draft.
- [ ] Independently capture the full real USB export with the CLI. Verify the persistent path, encoding candidates against German characters, value delimiters, actual row/byte count and idle gap. Check pass/fail results against the tester display.
- [ ] Disconnect during a transfer and reconnect; verify the cache does not advance on interruption. Re-export unchanged data, add and overwrite slots, and test the first-import and multiple-change uncertainty prompts. Confirm historical reports retain original measurements.
- [ ] Keep the HMI responsive during a transfer. Verify tester status, interface, count, local import time, pagination, manually selected slot, explicit confirmation and the original verdict.
- [ ] Print a real report and a simulated report. Compare graphical header, measurement characters, feed, cut, density and branding. Print with Wi-Fi off. Verify A4 PDF with limits where available, simulation markings, and genuine QR downloads from the working phone setup.
- [ ] Confirm remembered Wi-Fi, NetworkManager permissions, open hotspot start/stop, QR URL rollover, loopback admin access by tunnel, and no public import/history/printing routes. Verify standby, wake, brightness, saved settings and cold-boot services. Do not grant broader network or power permissions just to pass a bench test.
- [ ] Rehearse restoring the saved v0.4 Pi and HMI artifacts and confirm the original setup still functions.

## Experimental RS232

- [ ] Verify the exact model and Mini-DIN connector pinout using reliable electrical documentation or qualified bench measurement. Use a suitable RS232-level adapter. Keep the Nextion TTL UART and the USB CSV link separate.
- [ ] Configure one explicit adapter path, preferably persistent, and run `benning_cli.py listen --mode rs232 --rs232-device /dev/serial/by-id/… --once --timeout 90 --capture /tmp/st725-print.bin`. The host only receives.
- [ ] Trigger PRINT per the tester manual. Capture multiple pass/fail Class I/II reports, a current measurement and a recalled record. Verify control codes, code page, line spacing, inter-record idle time, units, thresholds and missing data. If layouts differ, keep new sanitized fixtures before extending the parser.
- [ ] Check that unplug/interrupt and malformed printouts preserve the existing cache, and dual-interface auto detection requests an explicit choice.
- [ ] Repeat the HMI, receipt and PDF checklist with verified reports. Enable production RS232 only after the adapter and supported report variants pass these checks.
