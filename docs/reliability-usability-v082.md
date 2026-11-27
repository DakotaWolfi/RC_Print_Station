# FMI Printstation v0.8.2 bench candidate

HDMI and browser are the primary interfaces. Use HDMI-only or headless with the web gateway. Nextion remains an optional legacy display through explicit **--mode nextion** or **--mode both**. Its firmware and adapter remain on the frozen protocol 71 implementation. The earlier unavailable-host incident is unresolved. It is outside this candidate's release gate.

## Install or migrate a copied bench station

Keep the deployed checkout, database, service environment, printer/network config and personality SQLite database as backups. Use a distinct checkout of the v0.8.2 development branch. Avoid editing or regenerating any TFT artifact. Review the existing [v0.8.1 hardware guide](usability-web-v081.md) for UART, GPIO and network details. The access policy and startup guidance below supersede its old operator login and fixed IP examples.

```sh
tools/install_multi_display.sh --board pi4 --mode hdmi --backend wayland \
  --connector HDMI-A-1 --web --db /home/pi/bench.sqlite3 --render /tmp/fmi-v082
```

For a tablet-only Zero 3, use **--board zero3 --mode headless --web**. For a direct kiosk framebuffer, use **--backend linuxfb** with HDMI mode. The Wayland XDG launcher inherits the graphical session and uses system Python. The systemd core and PDF server run independently from graphical availability. Review the generated units and your service user's existing hardware permissions before an explicit **--install --replace** on bench equipment. Maintain the same unit user and shared socket directory. Make sure the migrated web unit has no v0.8.1 ConditionPathExists check for web-auth.json.

If an older optional slogan worker/timer was enabled, stop it and disable its timer on the **bench** before starting the candidate. The current branch contains no slogan provider.

```sh
sudo systemctl disable --now rc-printstation-slogans.timer
sudo systemctl stop rc-printstation-slogans.service
```

Keep any existing private env files and the historical SQLite tables. The branch keeps the original personality SQLite path and counters. Measurement/report tables and content are unchanged. One additive SQLite table, fmi_resume, stores the latest acknowledged draft fields and completed report reference. Following a full core restart, unfinished examinations reopen at entry, with an explicit instruction to recheck the setup. Old commands are rejected by epoch. A queued or uncertain print must be checked before starting another. Frontend or gateway restart leaves the live core draft and guide in place.

## Password-free operator access on a trusted network

The ordinary operator takes no password and the connection QR points directly to the HMI. Whoever can reach the permitted interface/subnet can perform examinations, print and view operator-accessible reports. Use a dedicated trusted network or protected hotspot and restrict firewall ingress. Never forward or publish the HTTP listener or an HTTPS proxy publicly. The existing PDF download listener serves only opaque report tokens on its separate port. Treat those links as private.

For a station that moves between workshop Wi-Fi, house Wi-Fi and the protected hotspot, configure private /etc/rc-printstation/web.env like this, replacing the example NetworkManager profile names:

```ini
FMI_WEB_ALLOW_LAN_HTTP=1
FMI_WEB_INTERFACES=wlan0
FMI_WEB_PORT=8090
FMI_WEB_TRUSTED_PROFILES="Workshop Wi-Fi,House Wi-Fi,FMI-RC-Printstation"
```

Use **nmcli -g GENERAL.CONNECTION device show wlan0** to check each actual profile name. Keep the profiles allowlist for a station that may join other Wi-Fi networks. To serve tablets on a wired trusted LAN, explicitly add its interface and active profile. Exclude the private printer-only Ethernet link unless its access is intended. The opt-in LAN listener checks the socket's local interface address, the peer's current private IPv4 subnet and the exact Host/Origin on each request. A two-second refresh learns DHCP changes and removes previous ingress addresses and origins. An earlier fixed LAN bind is migrated to wlan0 if the existing explicit LAN HTTP opt-in is present. Remove obsolete fixed bind and origin values when migrating. If LAN HTTP is not opted in, the service defaults to loopback.

The HDMI **Web connection** page displays current gateway heartbeat, hostname, current IP and port, and a scan-ready operator QR. If the gateway stops or has no eligible address, it explains the status and removes the stale QR. An open browser at a literal old IP needs the new QR when its network changes. A stable, locally resolving mDNS/DNS name can be configured with **FMI_WEB_HOSTNAME** in the dynamic HTTP profile. Configure its resolution separately. Use **FMI_REPORT_FALLBACK_URL** only for a reachable PDF origin. The existing wireless address and gateway metadata update the automatic PDF base.

For a private HTTPS reverse proxy, keep the gateway on 127.0.0.1 with no direct interfaces. Use **FMI_WEB_ORIGINS=https://printstation.local** and **FMI_WEB_PUBLIC_ORIGIN=https://printstation.local**. Preserve the external Host at the proxy. Install a certificate trusted by station and clients. The gateway advertises the HTTPS URL only after a valid health response from that origin. Browser installation, if desired, requires a suitable secure context. The HMI never queues or replays safety actions or prints while offline.

Settings opens a separate administrator sign-in dialog/page in the browser. The password is optional and can be created or reset using **/usr/bin/python3 web_hmi.py --set-password** as the service user (8–128 characters). An existing v0.8.1 hash remains valid. Preserve mode 0600 and restart the gateway after changing that file to revoke sessions. With no administrator credential, settings changes are available locally. The ordinary browser uses an anonymous same-origin CSRF session. Server-side authorization protects examiner administration, network/hotspot changes, printer and tester config, diagnostics and power. Station language and choice of an existing examiner remain operator actions. Production print confirmation and the duplicate-job guard remain, with a bounded gateway print rate. The hotspot passphrase remains separate.

## Display and examination

In HDMI **Settings → Display**, choose 0°, 90°, 180° or 270°. The candidate rotates the application and inverse-maps its pointer coordinates in the same Qt view. Confirm within 15 seconds to persist the setting. Cancel, timeout or closing during preview keeps the previous setting. For Wayland, keep the compositor transform fixed. Avoid configuring an equivalent rotation in both layers. HDMI hotplug relaunches the surface with the saved profile and shows the live core draft. Wayland connector names scope saved rotations, and the single direct-rendering window uses the default key. The setting is stored in ~/.config/rc-printstation/display-rotation.json. Change or remove a wrong entry from a keyboard/SSH session with the kiosk closed, then restart it. Incorrect raw touch axes still require the existing per-device libinput calibration. The application does not force browser rotation.

The keyboard, selection lists and confirmations occupy the Qt viewport and replace underlying controls while open. Native Back and Home stay in the shell during scrolling. PDF / QR moves to a dedicated page with the original tester verdict, protocol/release status and QR. The HDMI interface does not start an external PDF app. Browser PDF links retain the usual download/open action.

Class I shows the verified Start, Lo LOAD and I LEAK instructions together. The operator still selects the observed tester display, and uncertain class, faults, abnormal load and energization checks retain their explicit branches. See [BENNING workflow references](benning-guided-workflows.md) and the manufacturer [ST 725 Swiss manual, revision 12/2021, §§8.4 and 9.1–9.3](https://www.benning.de/files/benning/global_content/downloads/instruction_manuals/benning_st725_ch_version_manual.pdf). Calibration remains a maintenance responsibility. The application does not decide release.

Retain the existing **FMI_TESTER_RS232_DEVICE=/dev/ttyAMA3** and **FMI_TESTER_GPIO_RX=1** for the validated Pi 4 bench adapter. Preserve USB CSV configuration and the existing UART reservation checks. The software still rejects bad frames and resumes on the next valid frame. A printout without a protection class remains class unknown. The recorded concern about the homemade optical adapter's mains isolation is still open and needs separate bench verification.

The illustrated home mascot takes one tap for a pet, with a second deliberate tap within 700 ms opening the wolf screen. A labeled control opens the same screen directly. Treats and separate achievements remain. Professional Mode hides access and suppresses new personality actions during operation.

## Development validation

The regression run used the existing virtual environment and a separate system Python/PyQt5 run. Of 106 cases, 105 passed and the end-to-end Unix socket test was skipped because the development sandbox disallows AF_UNIX. The separate Qt run covered nine actual widget tests. Its complete flow clicked visual inspection, Lo LOAD and I LEAK branches, selected the examiner and received a synthetic CP437 RS232 record. It verified the separate PDF QR and one captured print. The rotated-window test clicked mapped controls, resized the viewport, confirmed a rotation, timed out a preview and scrolled a long list. The legacy Nextion emulator tests ran as regression coverage.

The reproducible browser flow uses actual DOM controls plus a loopback fixture gateway and the real shared core with an injected socket transport. It completed one guided report and captured one print without a login, verified admin sign-in/logout, and checked the wolf and achievements. The rendered Chromium/Qt WebEngine layout run included 56 grabs in German and English at 390×844, 844×390, 820×1180 and 1180×820, checking viewport bounds and 48 px touch targets. The native renderer captured 208 views at the four required HDMI sizes.

- Run the backend and legacy simulator regression with **python -m unittest discover -s tests** and the build requirements installed.
- Run the Qt interaction suite with **QT_QPA_PLATFORM=offscreen /usr/bin/python3 -m unittest discover -s tests -p 'test_hdmi*'**.
- Render native screens with **QT_QPA_PLATFORM=offscreen /usr/bin/python3 tools/render_v081_previews.py OUTPUT**.
- Start the browser fixture with **PYTHONPATH=.:tests python tests/browser/fixture_server.py** in a local development environment. Open http://127.0.0.1:18191 and run **tests/browser/operator_flow.js** in a fresh browser. Read the result in **window.v082Result**. The optional Qt WebEngine/Slicer driver captures the additional layouts against that running fixture. Ports 18191 and 18193 and its passwords are test-only. The fixture is separate from the production gateway.

The test used a loopback browser and simulated serial frames. It does not verify a live NetworkManager transition, actual Wayland/DRM hardware, TFT UART availability, physical touch calibration, the test adapter's mains isolation or receipt output. The upcoming bench work remains required.

## Physical acceptance before release

- Boot headless and with HDMI on the Pi 4. Reconnect after a separate frontend restart, a gateway restart and a core restart. Verify acknowledged inputs and explicitly restart any interrupted live measurement. With internet disconnected, confirm HDMI, USB/RS232 reception and printing still work.
- Move the running station from one permitted WLAN/subnet to another by changing profiles. Verify the previous IP disappears from the HDMI web and PDF pages. Scan the new QR from a fresh phone. Restart the gateway without moving the station and verify anonymous recovery. Check protected fallback and subsequent Wi-Fi reconnection. Test an untrusted profile or off-subnet source and verify the web API is inaccessible. Verify the admin controls and direct unauthorized API requests.
- Complete a Class I examination separately with HDMI and browser using actual operator input, BENNING RS232 reception and a physical print. Verify the original verdict, status, no-release indication and PDF QR. Test class uncertainty, low-load and I LEAK decisions under qualified supervision. Send a truncated frame, then a good one. Retest USB reception.
- Check HDMI and browser portrait/landscape layouts at 480×800, 800×480, 600×1024, 1024×600 and phone/tablet orientation. Rotate through all four native angles. Confirm and time out previews, hot-unplug/replug HDMI and check saved orientation, touch corners, scrolling, dialog exclusivity and keyboard focus. Verify Wayland/direct operation on each intended OS image. Check the suspected display cable flicker independently.
- Have an operator unfamiliar with the candidate repeat the HDMI and browser workflows unaided. Measure peak/idle resource usage on the 1 GB Zero 3. Only promote after physical acceptance.

## Rollback

Stop bench units before restoring previous checkout paths, unit files and the XDG launcher. Restore original environment/private config as required. Preserve reports created during candidate testing before restoring any backup. v0.8.1 ignores the additive checkpoint table. Restore the earlier operator gateway policy if returning to that version. Reload systemd and start only the intended previous units. The release contains no firmware update or deployed hardware changes.
