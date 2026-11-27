# FMI Printstation v0.8.1 bench candidate

The BENNING workflows, compact reports, database and protocol 71 run through the existing station core. HDMI, Nextion and the authenticated browser use one draft and printer queue. The existing editable HMI and TFT can be used on the Nextion.

## Bench installation

Use a new checkout and back up the database, config, service units, environments and separate slogan cache. The core uses Debian/Armbian system Python with serial, ReportLab, D-Bus and NetworkManager. Install PyQt5, the Qt SVG and image-format plugins for HDMI, qtwayland5 for Wayland and python3-evdev for interactive calibration. The headless station needs no graphical packages. See the existing [service user, power, NetworkManager and serial permissions](multi-display-v080.md). Run the installer as the non-root station user.

```sh
tools/install_multi_display.sh --board pi4 --mode both --backend wayland \
  --connector HDMI-A-1 --rotation 0 --web --db /home/pi/bench.sqlite3 --render /tmp/fmi-units
tools/install_multi_display.sh --board zero3 --mode headless --web \
  --db /home/fmi/bench.sqlite3 --render /tmp/fmi-headless
```

Use **--install** after reviewing the rendered unit files and the existing station configuration. Use **--replace** for a deliberate upgrade. The default Nextion port on the Pi is /dev/serial0 at 115200. For Zero 3 modes that include Nextion, supply the known UART. The installer preserves the configured printer endpoint with 169.254.25.23:9100 as fallback. The Pi's Ethernet interface and saved NetworkManager networks require no changes. Keep local inference disabled on the 1 GB production profile. See [optional AI providers](personality-v071.md) for supported alternatives.

## Automatic HDMI startup and touch

| Profile | Startup and rotation |
| --- | --- |
| Wayland desktop | XDG autostart inherits the station user's live session socket and starts the supervisor with /usr/bin/python3. Rotate HDMI-A-1 in the compositor and use **--rotation 0** in the installer. |
| Minimal LinuxFB | The HDMI system unit starts on boot. Use an unrotated output and use **--rotation** in Qt if needed. |
| EGLFS | Alternative on an image with a working GBM/EGL stack. Use one layer for output rotation. |

Disable the old HDMI system unit before switching to XDG autostart. If the kiosk startup prevents recovery, move its desktop entry out of ~/.config/autostart/ or stop the direct HDMI system service using a keyboard or SSH. Run **display_presence.py --inspect** to list outputs and touchscreen candidates. Work in the logged-in desktop session for Wayland.

Identify the Waveshare WS170120 (USB 0eef:0005) with **udevadm info --query=property --name=/dev/input/eventN**. Match ID_INPUT_TOUCHSCREEN and ID_PATH. Use the persistent by-path alias when available. The calibration helper takes five physical points and renders a per-device libinput rule. It temporarily grabs the selected input and accepts Esc or times out after 60 seconds.

```sh
QT_QPA_PLATFORM=wayland /usr/bin/python3 tools/touch_calibrate.py \
  --device /dev/input/by-path/SELECTED-event --interactive \
  --output HDMI-A-1 --compositor-rotation 270 > /tmp/99-fmi-touch.rules
```

Pass the compositor's actual rotation. For direct LinuxFB/EGLFS, sample without compositor rotation and use libinput if supported on that Qt build. The legacy direct **--touch** override bypasses libinput, so leave it unset when using a udev matrix. Use **--rotate**, **--swap**, **--invert-x** and **--invert-y** to render explicit transforms. Review the output, install it in /etc/udev/rules.d/ during bench setup, then reload rules and reconnect the touchscreen or restart libinput's consumer. Recover by removing the rule or generating an identity rule with **--reset**. Validate all four corners, scroll gestures, modal actions and keyboard keys. See the [libinput documentation](https://wayland.freedesktop.org/libinput/doc/latest/device-configuration-via-udev.html).

## Tablet-only setup, local HTTPS and protected fallback

1. Run **/usr/bin/python3 web_hmi.py --set-password** as the station user. Use a unique 12–128 character password. The local salted verifier lives at ~/.config/rc-printstation/web-auth.json (0600). Restart the gateway after rotating the password to revoke sessions.
2. Enable **--web** in any display mode. Configure /etc/rc-printstation/web.env. For HTTPS, install a trusted certificate for the local hostname on clients and use a local reverse proxy that preserves the external Host header and forwards to 127.0.0.1:8090. Bind the proxy only to the intended workshop interfaces.

   ```ini
   FMI_WEB_BIND=127.0.0.1
   FMI_WEB_PORT=8090
   FMI_WEB_ORIGINS=https://printstation.local
   ```

3. Configure DNS or mDNS for the hostname. A fallback IP origin must also match the configured origins and the certificate when using HTTPS. In an isolated test network, explicit LAN HTTP requires **FMI_WEB_ALLOW_LAN_HTTP=1**, a selected IPv4 bind and exact origins such as http://10.42.0.1:8090. Restrict exposure with the firewall if using a wildcard bind. HTTP exposes credentials and traffic to network observers. A manifest supports installation where the browser allows it on a secure origin. The browser needs local connectivity for station state and never queues offline changes or prints.
4. Set **FMI_REPORT_FALLBACK_URL=http://printstation.local:8080** in benning.env if QR clients need a reachable origin without a Wi-Fi address. Auto URLs use live Wi-Fi when available. Port 8080 serves the existing opaque PDF tokens; port 8090 serves the authenticated gateway. Keep their proxy routes separate.
5. Run **/usr/bin/python3 tools/set_hotspot_password.py** with a separate 12–63 character printable ASCII passphrase. The 0600 file is ~/.config/rc-printstation/hotspot.psk. Enable **--hotspot-fallback** or **FMI_HOTSPOT_FALLBACK=1**. After about 90 seconds without an active SSID, NetworkManager can start the temporary WPA2 FMI-RC-Printstation access point at 10.42.0.1. Without a valid private PSK, a protected hotspot request fails. The operator password is still required. Stopping fallback manually suspends automatic fallback until the station restarts. From the tablet, join the protected hotspot, sign in, choose a Wi-Fi network and reconnect on the new address.

The gateway requires authenticated, same-origin requests and a session CSRF token. It bounds request bodies, sessions, login attempts and concurrent requests. Its operator role includes printing, settings and power when enabled. Credentials and Wi-Fi passwords are omitted from gateway logs. The loopback admin and the existing tokenized PDF service have their own listeners. The local socket is private to the station service user.

On disconnect the browser keeps the last snapshot with a stale indicator. Check the print outcome before requesting a retry. Shared revision checks and per-field 20-second leases protect concurrent edits, including tabs sharing a login. An expired lease unlocks the field and the original value must still match before a stale edit can save. Nextion protocol 71 keeps its transition lease and field-value comparison. Reports and printing use the same deduplication guards for every frontend.

## Receive-only BENNING printer port

USB CSV remains the established source. Choose auto, USB CSV, RS232 PRINT, file or simulation in tester settings. The source is persisted. Configure serial paths in /etc/rc-printstation/benning.env. The station never scans onboard UARTs.

| Source | Configuration |
| --- | --- |
| USB CSV | FMI_TESTER_DEVICE set to the existing by-id bridge path, or use its known auto detection. |
| RS232 USB adapter | FMI_TESTER_RS232_DEVICE points to its dedicated by-id path. |
| RS232 Linux hardware UART | FMI_TESTER_RS232_DEVICE points to the explicit /dev/ttyAMA* or /dev/ttyS* node. Set FMI_TESTER_GPIO_RX=1. |
| Other options | FMI_TESTER_MODE provides the boot default, FMI_TESTER_ENCODING=auto uses CP437 for RS232, FMI_TESTER_IDLE defaults to 1.8 seconds. |

On the Pi 4 use a spare UART overlay from the installed image and release its serial console/getty. On the Orange Pi Zero 3 (H618) verify the UART overlay, Linux node and RX header pin for the actual image and board. The Zero 3W is a different board. Verify permissions for the station user, kernel console, persistent UART aliases, active/enabled getty and any other serial owner. Non-root permissions can limit visibility into other users' open descriptors. The station checks for aliases of the Nextion, console/getty reservation and detectable occupancy, and uses an exclusive read-only handle. See the [Raspberry Pi configuration manual](https://www.raspberrypi.com/documentation/computers/configuration.html) and [Orange Pi Zero 3 documentation](https://www.orangepi.org/orangepiwiki/index.php/Orange_Pi_Zero_3).

**Use a suitable RS232-level receiver/converter or an isolated receiver. Never wire RS232 directly to GPIO.** Connect only the verified receive path with station TX and all handshake lines disconnected. A prototype optocoupler is not a certified safety barrier. Begin bench captures with the BENNING on battery, mains and test leads disconnected. Verify pinout, electrical levels and isolation before connecting. The receiver uses 9600 8N1, no hardware or software flow control and no probe, transmit or acknowledgement. Tests cover the [community byte example](https://www.mikrocontroller.net/topic/555251) and a synthetic UISO label variation. The actual Swiss tester's printer-port framing, pinout and variants remain to be checked on hardware.

Use **benning_cli.py listen --help** for the diagnostic. On an isolated bench use **--mode rs232 --rs232-device** with the known adapter and **--gpio-rx** for an explicit onboard UART. **--capture** writes one private raw frame. Test fragments, malformed/partial transfers, repeat PRINT and changed slots. A valid PRINT adds one record and keeps supplied limits and original verdict. Fresh imports still require operator confirmation. USB CSV retains its full-memory import and previous baseline semantics.

## Acceptance and rollback

| Area | Physical bench checks |
| --- | --- |
| Native display | Wayland and direct startup, all four sizes and rotations, touch corners, unplug/reconnect, keyboard cancellation, long-press accents, modal help, settings and confirmation. |
| Three frontends | Enter a draft through one frontend and edit a second field from another. Reconnect after a gateway interruption, verify independent report language and confirm/print once. |
| Tablet access | HTTPS trust, DNS fallback, browser native keyboard on the actual device, close and reopen the browser during an edit, protected fallback and return to remembered Wi-Fi. Verify the PDF route exposes no operator API. |
| BENNING and output | Validate USB CSV and both PRINT transports, including invalid frame recovery. Compare real receipts and colour PDFs with the compact bilingual baseline. |
| Memory | Measure each process's PSS, CPU and startup on the actual Pi 4 and Zero 3 1 GB. Include idle, dual-display, tablet-only, import, print and PDF. The target is <300 MiB combined application memory. |
| Personality | Five FMI taps opens the wolf. Stroking, treats, Awoo and Workshop Break are optional. The fictional BIOS accepts help, status, awoo and 42. Novelty receipts require confirmation and carry a fictional label. Verify Professional Mode and active measurement suppress access and awards. |

For software validation use the existing regression suite and render native pages with **QT_QPA_PLATFORM=offscreen /usr/bin/python3 tools/render_v081_previews.py /tmp/fmi-previews**. Browser device dimensions test the real responsive pages; the host OS supplies the native mobile keyboard. The [software validation record](validation-v081.md) lists measured results and limitations.

Stop the candidate on the bench before restoring the backed-up checkout, units, desktop entry, config and database. Disable the new gateway when returning to the old profile. Reload systemd and start only the previous units. The measurement/report SQLite schemas and protocol 71 firmware are unchanged. There is no firmware installation step for v0.8.1.
