# FMI Printstation v0.8.0 validation

This is a bench candidate based on v0.7.1 commit `af30824`. Test reports and screen previews use the repository's recorded BENNING fixture with a DEMO repair number and an explicit bench label. The original tester verdict and units are shown.

## Verified in development

- Existing BENNING CSV and experimental RS232 parsing, historical report snapshots, examiner records, bilingual output, printer configuration, hotspot routes and v0.7.1 optional providers were covered by the existing suite.
- New core tests exercise headless import and confirmation, no-display PDF and receipt generation, overlapping clients, stale values, editor leases, duplicate confirmation and printing, database compatibility, Professional Mode and novelty output isolation.
- A Nextion protocol 71 simulator test uses the existing project and a hardware-shaped UART transport. It enters a ticket on Nextion, adds a device from a second client, switches languages, confirms the guide starts on the panel and reconnects mid-guide without resetting the draft.
- The DRM supervisor was tested with simulated attach, removal and resolution changes. The synthetic udev data distinguish an ordinary HID mouse from a touchscreen. The serial adapter retries without holding core startup.
- Native Qt tests exercised responsive geometry, 48-pixel minimum action targets, a wrapped long appliance description, bilingual draft controls and Professional Mode. The preview pack covers all four requested resolutions in both languages. Text and protection-class images are supplied by the existing verified guide.
- Both generated Class I PDF examples are single-page A4. Text extraction verifies Ω, MΩ, 500 V and the recorded overall verdict. The existing rendering code and stock Nextion firmware are unchanged.
- All five systemd modes passed render-only verification. The separate Zero 3 HDMI profile was also rendered and checked. No service was installed or started on the physical station.

The existing and new simulator suite completed with 86 passing tests. Three additional Qt cases passed under Debian system Python (89 passing cases total). The current development execution environment restricts Unix socket creation. The private socket integration test is included and skipped in that environment. The concurrency and Qt tests use in-process transport calls, and the production Unix socket lifecycle remains a bench check.

## Resource assessment

Measured once per scenario on the x86-64 Linux development host with system Python 3.13, Qt 5.15 and the offscreen Qt platform. Each scenario uses a fresh process. Time starts after common Python imports and includes initial configuration, demo operation and rendering where applicable. The dual scenario uses a serial sink and offscreen Qt in one process. It measures the combined rendering workload on the development host. PSS includes the proportional share of shared mappings. CPU time is for the short scenario, with no steady-state CPU percentage inferred from it.

| Scenario | PSS MiB | Peak RSS MiB | Wall ms | CPU ms |
| --- | ---: | ---: | ---: | ---: |
| Headless core construction | 20.34 | 21.07 | 2.7 | 2.7 |
| Nextion adapter to serial sink | 20.37 | 21.12 | 2.9 | 3.0 |
| HDMI shell | 47.59 | 49.83 | 118.5 | 118.5 |
| Both adapters | 47.77 | 50.01 | 59.9 | 59.9 |
| Guided Qt screen | 47.98 | 50.03 | 58.4 | 58.3 |
| Recorded USB CSV contents imported from file | 20.93 | 21.49 | 7.1 | 7.1 |
| ESC/POS receipt rendering | 21.06 | 21.74 | 6.5 | 6.5 |
| Cold colour PDF rendering | 33.80 | 35.09 | 385.9 | 385.6 |
| Wolf widget | 47.80 | 49.95 | 61.3 | 61.3 |

The 1 GB ARM target is under approximately 300 MiB of Printstation app memory during ordinary use. Budget **75–150 MiB combined** for two Python processes, Qt platform and ordinary PDF work, excluding the OS and any GPU/compositor reservations. This is an estimate pending ARM measurements. The OpenAI worker keeps no model weights and is separately capped at 96 MiB by its optional unit. Live API generation and sustained ARM CPU load were not measured. Local inference is outside the ordinary memory budget and is disabled by default.

Run the reproducible workloads with:

```sh
python3 -m unittest discover -s tests
QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s tests -p test_hdmi_v080.py
QT_QPA_PLATFORM=offscreen /usr/bin/python3 tools/render_v080_previews.py /tmp/fmi-v080-previews
QT_QPA_PLATFORM=offscreen /usr/bin/python3 tools/benchmark_v080.py both
```

Use the pinned Nextion build environment for the complete existing simulator suite. Use Debian system Python for the Qt tests.

## Physical bench validation

1. Boot headless. Confirm service startup, socket access as the station user, USB import, report history and the restricted PDF route. Confirm policies on the existing hotspot.
2. Exercise Nextion-only, HDMI-only, both, and automatic operation. Leave the existing protocol 71 firmware installed and record its handshake. Verify both screen languages, the independent report language and the examiner directory.
3. On both screens, enter different fields of the same draft. Try an edit to an already changed field. Disconnect and reattach HDMI, USB touch, and Nextion separately while a draft is open. Restart the frontend during guided testing and while waiting for an import. Record recovery timing and confirm there is one import reader and one queue.
4. Confirm LCD connectors, actual 800 × 480 and 1024 × 600 modes, each rotation, gesture direction, keyboard fallback, standby and permissions. Compare rendered touch targets against actual panel size. The test host's offscreen Qt render cannot verify EGLFS, DRM or touchscreen drivers.
5. Exercise original fail and pass outcomes, shared manual selection, report confirmation, print checks, Wi-Fi reconnection, and restricted power action. Follow the original BENNING operating manual for these tests. Confirm a second print request from the other display is suppressed. Physically validate the experimental RS232 interface only with the appropriate adapter.
6. On the Zero 3 record steady and peak RSS/PSS of both services, core CPU utilisation, connector reconnect time, import and PDF latency, and power behaviour under load. Keep cloud inference disabled until the station works offline. Validate the provider separately if enabled.
