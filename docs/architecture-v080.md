# FMI Printstation architecture · v0.8

## Audit of af30824

| v0.7.1 surface | Coupling | v0.8 boundary |
| --- | --- | --- |
| `native_ui.py` | Owns the serial handshake, receiver lifetime, report selection, printer executor, PDF links and UART dispatch. An absent panel delays or prevents startup. | The core owns the receiver, data and output queue. A bounded serial adapter owns the handshake and panel transport. |
| `benning_workflow.py` | Draft completion, import waiting and report creation are driven by numeric page routes, wire payloads and writes to named widgets. | Share the existing `Guide` state machine and extract the fresh-slot and report-match rules into a display-free module. |
| `benning_panel.py` | Formats the tester status, caches a batch, retains selection offsets, and submits selections from on-screen row buttons. | Explicit batch and record identity at the core. A frontend's paging, byte decoding and visual selection remain local. |
| `operator_panel.py` and native HMI | Repair number, description, phase, mode and partial keyboard edits live in Nextion variables; the host receives a subset on entry or submission. | Use one core draft. Apply per-field compare-and-set updates so edits to different fields merge. Keep unfinished keyboard input local. |
| `station_panel_settings.py` | Presentation, network jobs, printer probes and power confirmation share a page-specific state object. | Shared settings and asynchronous control in the core. The existing NetworkManager and logind implementations are retained. |
| `personality.py` | Slogans and the pet/engineering state depend on page transitions. | Retain the separate slogan cache and worker. Professional Mode is a persisted setting and suppresses entertainment. |
| Storage, output and safety logic | `benning_csv`, `benning_rs232`, `benning_receiver`, `benning_store`, `operator_store`, `station`, `benning_pdf`, `report_web` and `i18n` already provide independent services. | Reuse these modules and preserve their report snapshots, exact verdicts, schemas and rendering. |
| Tools, assets, tests, services | Native generator and artifact tests depend on Nextion target limits. The installer assumes one UART. The legacy hybrid frontend has independent historic code. | Keep protocol 71 firmware. Make the Qt process optional. Keep the former service, tools and tests available for rollback. |

## Boundaries

The station service has one application core, one BENNING receiver and one queue for official print jobs. SQLite remains authoritative for historical records. The core serialises state changes under one lock. Display clients can reconnect to an in-memory draft during the lifetime of the core. The configuration and report data persist as before.

HDMI uses PyQt5 Widgets and native raster rendering. A separate process polls a private Unix-domain socket. The socket exchanges bounded newline-delimited JSON. The Nextion adapter translates protocol 71 frames to the same command interface. No display owns the acquisition or rendering lifetime.

HDMI and Nextion can show different views while sharing one examination. A guide option identifies the step and the draft version it was presented for. Confirming a record carries its identity and batch. A render never submits an action. Report creation consumes the current draft and print commands have confirmation, an idempotency key, and a short shared anti-duplicate window.

The HDMI supervisor polls DRM status and udev input properties, launches Qt when appropriate, and restarts the display process after connection or geometry changes. The operating system's input stack owns touch events and calibration. Existing NetworkManager and Ethernet configuration are preserved.

## Qt decision

Qt Widgets renders with the raster paint engine without a QML scene graph. Qt Quick can use a software scene graph, and can simplify animation, but it adds packages and makes GPU driver and scene graph configuration an extra variable on H618. Debian provides PyQt5 Widgets on ARM64. LinuxFB is the initial no-desktop profile; software DRM dumb buffers can be enabled where Qt's build supports them. EGLFS depends on a working EGL/GBM stack. Wayland requires a small compositor and its Qt plugin. XCB is useful on a bench with an existing X server. KMS, libinput, timing and driver compatibility still need to be checked on the deployed image.

- [Qt Embedded Linux](https://doc.qt.io/qt-6/embedded-linux.html)
- [Qt Embedded Linux input stack](https://doc.qt.io/qt-6/inputs-linux-device.html)
- [Debian ARM64 PyQt5 package](https://packages.debian.org/trixie/arm64/python3-pyqt5)
