# v0.8.1 software validation

The candidate is based on v0.8.0 commit 51a5434. This is development-host validation. Keep the [physical bench checklist](usability-web-v081.md#acceptance-and-rollback) open for the Pi 4, Orange Pi Zero 3 1 GB, Epson, BENNING and both touchscreens.

## Regression and visual coverage

- The Python run covered the existing BENNING CSV store, Nextion firmware simulation, guided examination, printer, PDF routes, compact bilingual reports, network/profile handling and personality regression tests. Gateway tests exercised live loopback HTTP with the real StationCore behind an injected socket transport. They covered sign-in, cookie scope, exact Host/Origin and CSRF, session preservation, inter-client leases, duplicate command IDs, temporary core disconnect and the independent public PDF listener.
- Six native Qt tests ran separately on system Python. Coverage includes navigation without draft loss, both QWERTZ and QWERTY, long-press accents, physical cursor/input, IPv4 validation, cancel and actual four-size layout bounds. Touch calibration tests check corner transforms for all rotations, axis swap/inversion, fitting and invalid samples. The kernel-level serial test verified the descriptor access flags and raw 9600 8N1 termios on a Linux pseudoterminal. Fragmented reader tests, the known CP437 example and a synthetic UISO variant cover input validation.
- The combined runs covered 103 distinct test cases. 102 passed, with the AF_UNIX end-to-end transport case skipped due to the workspace restriction. The Unix socket code remains the production transport. The HTTP tests bind real IPv4 loopback listeners. No test printer or safety tester was energized.
- 192 actual Qt grabs cover 24 views or dialogs per language at 480×800, 800×480, 600×1024 and 1024×600. The portrait/landscape groups include settings, separate alphabets, password visibility, three-column number/IPv4 keypads, guide, warnings, reports, confirmation and mascot. The header and visible buttons are checked against the viewport.
- 60 Chromium/Qt WebEngine screenshots cover 15 scenes in both languages at 390×844 and 820×1180 using the running gateway and recorded or demo fixtures. DOM checks verified viewport width without horizontal overflow and visible button heights of at least 48 CSS pixels. The emulator does not supply an Android or iOS keyboard. The screenshots show actual browser inputs and dialogs.

Reproduce the native grabs with **QT_QPA_PLATFORM=offscreen /usr/bin/python3 tools/render_v081_previews.py OUTPUT**. Use the existing build dependencies for the Python regression suite. Qt uses **QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s tests -p 'test_hdmi*'**. The renderer uses throwaway SQLite state and does not access the production printer, tester, network or reports.

## Resource spot measurements

Measurements from the x86-64 development environment using offscreen Qt and fresh fixture processes. Elapsed/CPU cover one scripted scenario. The Qt fixture runs the simulated adapter and core in one process. The gateway used a separate live loopback server. These numbers locate candidates for bench measurement and are no substitute for an ARM boot/idle/peak profile.

| Scenario | PSS MiB | Peak RSS MiB | Elapsed / CPU ms |
| --- | ---: | ---: | ---: |
| Headless fixture | 15.9 | 21.2 | 1.9 / 1.9 |
| Nextion adapter fixture | 15.8 | 21.1 | 3.9 / 3.7 |
| HDMI fixture | 32.0 | 49.9 | 89.6 / 89.6 |
| HDMI and simulated Nextion | 32.2 | 50.2 | 85.9 / 85.8 |
| Guided view | 32.3 | 50.3 | 85.3 / 85.3 |
| CSV fixture import | 16.1 | 21.7 | 5.4 / 5.4 |
| Receipt generation | 16.2 | 21.8 | 8.9 / 8.9 |
| PDF generation | 28.2 | 35.2 | 401.6 / 401.6 |
| Illustrated wolf view | 32.4 | 50.9 | 62.2 / 63.2 |
| Gateway through first HTTP response | 14.4 | 33.6 | 108.2 / — |

The optional local and cloud AI providers were not exercised in this candidate. The gateway and Qt build have no inference dependency. The captured render package includes recorded Class I output for both languages, with original measurement values preserved. The previously validated receipt and PDF renderers are unchanged.

## Pending validation

- Physical Wayland and direct LinuxFB/EGLFS boot, touch rotation, multitouch/pinmapping and navigation on both panel sizes. CLI calibration requires a libinput-capable session for the rendered udev rule. Recovery uses a physical keyboard or local administration.
- Real USB/RS232 and GPIO receive on both boards, including actual isolation, pinout, modem-line behavior, printer report variants and incomplete electrical transfers. The termios test establishes the station-side receive-only descriptor behavior.
- Real protected hotspot failover with NetworkManager, client HTTPS trust, browser-native mobile keyboard, and simultaneous Nextion + HDMI + tablet bench operation.
- Orange Pi Zero 3 1 GB peak and idle resource usage, physical Epson output, owner-installed TLS, and WAN-free workshop operation.
