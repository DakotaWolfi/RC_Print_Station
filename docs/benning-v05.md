# BENNING ST 725 · Raspberry Pi 4B

v0.5 uses the BENNING ST 725 USB memory export as its primary source. It runs the receiver, display UART, NetworkManager and printer separately. The touchscreen and Ethernet printer can operate without Wi-Fi. Wi-Fi or the temporary open hotspot provides the phone’s link to the PDF endpoint.

## Operator workflow

1. Connect the tester by USB. On the Nextion choose **Neues Protokoll** and enter **Prüfnummer**, **Gerätebeschreibung** and **Prüfart**.
2. With **Letzten Speicherplatz verwenden** enabled, save the test on the BENNING, then hold **RECALL** for about five seconds. Wait for the transfer and check the displayed import time and slot. **Speicher** opens the slot list.
3. Choose **Messung prüfen** and confirm the displayed slot, tester date and result against the tester and repair sheet. If a cached slot is old or the order is unclear, the page says so. To pick a different slot, disable the checkbox and type it or choose it from the list.
4. Confirm with **Messung bestätigen**. A report keeps that exact measurement, even if the tester later overwrites its slot. Print, or open the QR code on a phone that can reach the station. PDF and receipt identify the data source and separate missing, incomplete, passed and failed checks wherever the tester supplied a verdict.

The station records the original tester result. The operator is responsible for associating the correct measurement with the appliance. A printout is a record of an imported tester result, not a safety certification by the print station. **Simulation** is an explicit host mode and its reports are visibly marked.

## USB protocol and data retention

| Property | Observed behavior or implementation |
| --- | --- |
| USB adapter | Silicon Labs CP2102, VID/PID `10c4:ea60`, serial `0001` |
| Device path | `/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0` |
| Serial | 9600 baud, 8N1, no flow control, receive only. No host handshake was observed. |
| Export trigger | Hold RECALL for approximately five seconds. The user reported 33 rows plus header, 3,770 bytes. |
| CSV | Exact German header, 28 semicolon-separated columns, CRLF wire framing, date in day/month/year and no time, comma decimals, comparisons retained as sent |
| Encoding | Validate the decoded header. Auto checks UTF-8 with/without BOM, Windows-1252, Latin-9, Latin-1, CP437 and CP850. The displayed encoding may list equivalent decodings when the bytes cannot distinguish them. If plausible decoders produce different records, the operator must set the encoding explicitly. Pin the verified codec only after examining a Pi capture. |
| Transfer completion | An idle gap (1.8 s default) closes the frame. The USB parser requires complete CRLF lines, the full header, valid fields and unique slots. Losing a device during transfer discards the frame. A snapshot missing slots from the last USB import is rejected unless an intentional reset has been authorized via the CLI. |

No end marker or record count is known. A first export truncated exactly between complete rows can therefore look valid. An established slot baseline detects many such cases. Compare the slot list and count with the tester on a first capture and after a deliberate memory reset. Set a longer idle gap if the bench capture reveals longer pauses. A dropped transfer never replaces an accepted snapshot as part of error handling.

The Pi supplies a UTC import timestamp independently of tester time. The HMI shows import time in Europe/Zurich. For a USB snapshot compared with its predecessor, exactly one added or changed slot yields a newest-slot suggestion. A first import, identical export or several changes cannot establish recency. A suggestion still requires confirmation, especially when it predates the current draft. Two writes identical in all exported fields cannot be distinguished, and a date alone cannot order measurements within a day.

SQLite keeps source-specific snapshot and slot associations, exact raw record bytes, decoded records and stable internal record IDs. Identical records share storage. A change to a reused slot adds a distinct record. An existing report contains its original snapshot. Absent measurements and limits stay absent. Routine logs and the HMI report transfer state or validation errors. Preserve the database and raw captures as local repair data.

## Standalone Pi 4 bench diagnostic

Run as the station user with `python3-serial` installed and access to the tester device via `dialout`. Use an independent database and stop any process using the BENNING USB device. This diagnostic needs neither Nextion nor Epson.

```sh
python3 benning_cli.py --db /tmp/benning-bench.sqlite3 detect --mode usb
python3 benning_cli.py --db /tmp/benning-bench.sqlite3 listen --mode usb --once --timeout 90 --capture /tmp/st725-export.bin
python3 benning_cli.py --db /tmp/benning-bench.sqlite3 slots
```

The capture is created with private permissions and never overwritten. Exercise RECALL twice and look for `unchanged`. Save a new tester result, export again and check for `single-change`. Record the byte length, codec candidates, record count and any inter-byte gaps. Unplug/replug the USB cable, interrupt an export and verify recovery before starting the HMI. Where practical, include a known failed result and a Class I and Class II record.

For a capture with ambiguous Unicode decoding, use `--encoding` before the subcommand. A known intentional memory erase can be applied to the station database using `listen --mode usb --once --accept-memory-reset` while the station backend is stopped. Back up the database first. Existing reports continue to refer to their original snapshots.

To validate an existing file without even connecting the tester:

```sh
python3 benning_cli.py --db /tmp/benning-files.sqlite3 import --format csv /path/to/export.csv
python3 benning_cli.py --db /tmp/benning-files.sqlite3 slots --source file-csv
```

## Interface selection

Set the options once on the Pi using command-line flags or the optional service environment file `/etc/rc-printstation/benning.env`. No HMI rebuild is needed.

| Setting | Value |
| --- | --- |
| `FMI_TESTER_MODE` / `--tester-mode` | `auto` (default), `usb`, `rs232`, `file` or `simulation`. Auto accepts one recognized USB device or a configured RS232 path, and reports ambiguity if both are present. Use `usb` for the initial deployment. File uses the latest valid file import and opens no serial port. |
| `FMI_TESTER_DEVICE` / `--tester-device` | USB path override. Otherwise prefer the persistent path above, then match VID/PID and serial. |
| `FMI_TESTER_RS232_DEVICE` / `--tester-rs232-device` | Explicit adapter path, preferably its own `/dev/serial/by-id/…`. Required for RS232, including auto detection. |
| `FMI_TESTER_ENCODING` / `--tester-encoding` | `auto` or a codec name. Auto RS232 uses CP437. |
| `FMI_TESTER_IDLE` / `--tester-idle` | Seconds of silence before a frame is evaluated. Default 1.8. |

The Nextion remains on `/dev/serial0` at 115200. The receiver rejects that path and its aliases. Keep the two ports separate when attaching diagnostic tools.

## Pi 4 installation and rollback

1. Back up the actual deployed v0.4 HMI/TFT, checkout, both systemd units, settings and the database using SQLite’s backup mechanism or with both old services stopped. Keep the NetworkManager profiles, policies, remembered network and open hotspot permissions, and printer Ethernet setup. See [v0.4 network and printer setup](native-v04.md).
2. Set up a separate v0.5 checkout and copied database on the Pi. Use the same station account and dependencies (`python3-serial python3-reportlab python3-dbus network-manager`). Confirm the account has `dialout` access to both serial devices. Run the standalone USB checks first.
3. Open the separate editable v0.5 project in **official Nextion Editor 1.68.2** and compile. Verify model, rotation and `keyboard` page. Follow the [bench checklist](../hmi/VALIDATION-v05.md) with a development panel. Flash and install only with operator approval. The candidate backend requires protocol 5 before sending settings.
4. With the previous UART owner stopped, run the candidate manually as the station user. Substitute the actual printer address and database copy if they differ.

   ```sh
   /usr/bin/python3 native_ui.py --port /dev/serial0 --baud 115200 --tester-mode usb \
     --auto-report-url --host 169.254.223.252 --db /tmp/rc-v05-bench.sqlite3
   bash tools/install_services.sh --render /tmp/rc-v05-units --db /tmp/rc-v05-bench.sqlite3
   systemd-analyze verify /tmp/rc-v05-units/*.service
   ```

5. After acceptance, review the two service definitions and the database path. Stop the candidate’s manual process and the two previous services. Run the installer with `--replace --db /absolute/path/to/verified.sqlite3`; it backs up existing units and enables autostart. Explicitly start the two units and test a cold boot. Pass `--enable-local-power` only if the station account already has the intended logind permissions.
6. To roll back, stop both v0.5 services, save its database and raw exports separately, restore the saved v0.4 units, checkout and database, and load the matching deployed v0.4 TFT. Reload systemd and start both restored units. Confirm QR downloads, a saved network, hotspot, Ethernet print and standby. Retain the v0.5 database so actual tester imports and reports remain available for later recovery.

## Local web import

The administration server remains on loopback. Configure `FMI_IMPORT_TOKEN_FILE` with the absolute path of a private file readable by the service user. It must contain a randomly generated ASCII token of at least 24 characters. A typical shell setup is `umask 077` followed by `openssl rand -hex 32 > /private/path/benning-import-token`. The `/benning` form uses HTTP Basic authentication (user `benning`, password from the file) and a request token on uploads. It validates a bounded CSV/TXT upload before storing anything. With `FMI_TESTER_MODE=file` and a shared database, the imported slots appear on the HMI.

Open the admin site through an SSH tunnel, such as `ssh -L 8081:127.0.0.1:8081 YOUR_PI`, then visit `http://127.0.0.1:8081/benning`. The hotspot-facing HTTP server serves only secret-token PDF links. It has no admin, upload, history or printing route. Anyone on a reachable network who has a report link can download that individual PDF. Close the temporary hotspot after use.

Shared backend entry points are `Measurements.import_bytes`, `Measurements.slots` and `Measurements.create_report`, with `station.receipt` / `station.send` and `report_web.render_pdf` for the outputs.

## Experimental Mini-DIN 6 printer port

The linked [community discussion](https://www.mikrocontroller.net/topic/555251) reports 9600 8N1 at RS232 electrical levels and includes a raw printer byte dump. Its `0x81` and `0xEA` decode as **ü** and **Ω** in CP437. That example includes ESC/POS control bytes, slot, date, overall verdict, test voltage, measured values and limits. The parser was checked against that posted dump. The [BENNING manual](https://www.benning.de/files/benning/global_content/downloads/instruction_manuals/benning_st725_manual.pdf) describes export and print controls.

The separate parser expects the observed report layout and boundary lines. It preserves reported limits and individual results where present. It does not derive them from thresholds or infer protection class. Printer-port pinout, voltage behavior, report variations, end conditions and the adapter are pending physical checks. Treat this port as experimental. Follow the [RS232 checklist](../hmi/VALIDATION-v05.md#experimental-rs232) when the adapter arrives.
