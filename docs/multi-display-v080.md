# FMI Printstation v0.8.0 bench candidate

The shared station keeps running without display hardware. The Qt HDMI process and serial adapter can reconnect to the current draft. Firmware protocol **71** remains the Nextion contract. Keep the existing v0.7.1 panel firmware. The HDMI UI requires no browser or desktop environment.

## Profiles

| Mode | Nextion | HDMI |
| --- | --- | --- |
| `auto` | Try the configured UART and retry independently | Launch when a DRM connector or fallback session is available |
| `nextion` | Configured UART with retry | No HDMI service |
| `hdmi` | No UART probe | Connector detection or `--force-hdmi` |
| `both` | Configured UART with retry | Connector detection or `--force-hdmi` |
| `headless` | No UART probe | No HDMI service |

The HDMI frontend and Nextion share one draft, guide, record confirmation and printer queue. The two screens can open different settings and history views. A committed field updates the other interface. While a keyboard is open, its uncommitted input stays local and state-changing workflow actions from the other screen are temporarily held. A conflicting write can be rejected. If it is, compare the saved value before retrying.

## Raspberry Pi 4B and Orange Pi Zero 3

Use the existing Raspberry Pi 4B service identity and `/dev/serial0` at 115200 baud for the initial bench. Confirm the production printer still listens at **169.254.25.23:9100** and preserve the Pi's existing **169.254.100.1/16** Ethernet configuration.

For deployment, choose an ARM64 minimal image for **Orange Pi Zero 3 (Allwinner H618)**, distinct from Zero 3W. Debian or Armbian CLI works as a starting point. Bring up BENNING over USB and the touchscreen on a second USB host connection, using a powered hub or the correct expansion hardware if needed. HDMI and touch USB are separate connections. Pin a working image and record its kernel and overlays after testing. [Armbian Orange Pi Zero 3](https://www.armbian.com/orange-pi-zero-3/)

Select the board-specific UART overlay only for a connected Nextion. Discover the actual device node on the running image. A dedicated USB UART adapter with a persistent `/dev/serial/by-id/` path is another option. Preserve the original BENNING settings in `/etc/rc-printstation/benning.env`, using `FMI_TESTER_DEVICE`, `FMI_TESTER_RS232_DEVICE`, `FMI_TESTER_MODE`, `FMI_TESTER_ENCODING` and `FMI_TESTER_IDLE` as before. The tester receiver rejects attempts to give the same device to the display and measurement stream.

On a **bench image**, install the system dependencies explicitly for the services you intend to use.

```sh
sudo apt install python3-serial python3-reportlab python3-dbus network-manager
sudo apt install python3-pyqt5 fonts-dejavu-core
```

The second command applies to HDMI. Wayland also requires its Qt plugin and a small compositor. Headless and Nextion-only runs need no Qt package. Use `dialout` for the serial devices. The HDMI service renders with `video` and `input` supplementary groups. On a shared system consider narrower device-specific permissions, or launch Qt inside the same user's Wayland graphical session to let the compositor own device access. The service user retains the existing narrowly scoped logind and NetworkManager permissions. The entire application runs without root.

## Install and roll back

1. Save the working checkout, unit files, station user's `~/.config/rc-printstation/receipt.json`, BENNING settings and Nextion firmware. Use SQLite's backup function or stop writers and back up the report database consistently. Also retain the existing `~/.local/state/rc-printstation/slogans.sqlite3` if personality data matters.
2. Use a separate checkout of `feature/multi-display-v080` and a copied database for the bench. Render the units for one mode.

   ```sh
   bash tools/install_multi_display.sh --board pi4 --mode both \
     --db /absolute/path/bench.sqlite3 --render /tmp/fmi-v080-units
   systemd-analyze verify /tmp/fmi-v080-units/*.service
   ```

   The HDMI-only Zero 3 profile uses `--board zero3 --mode hdmi --backend linuxfb`. For `auto`, `both` or `nextion` on Zero 3 supply `--nextion-port` explicitly. Choose `--printer-host` and `--printer-port` only for an intentional change. The installer preserves a previously customised unit endpoint, and the station's saved printer settings take precedence.
3. Verify the [bench checklist](../hmi/VALIDATION-v080.md). When installation is authorised, stop the current station units and repeat with `--install --replace` in place of `--render`. Add `--enable-local-power` only where its permissions were already reviewed. The installer backs up replaced units and enables them for subsequent boots. It leaves service startup to the operator.
4. For rollback, stop the candidate core, HDMI, and loopback administration. Disable the candidate HDMI unit if it was enabled. Save new reports and settings, restore the old checkout and unit backups, reload systemd, and start the old services. Keep the existing protocol 71 firmware for a v0.7.1 rollback. A failed hardware migration can also be rolled back by returning the existing SD card and peripherals to the previous host.

No official report schema was removed or replaced. The new persisted mode lives in the existing station settings file. Personality achievement counters are additive keys in the existing slogan SQLite cache. An older station can open the reports and ignore those new keys. The active draft is in memory and survives frontend restarts during the same core lifetime. Save it as a report before restarting the core or changing the host.

## Display rotation and touch

The normal first choice is `--backend linuxfb` on a TTY with working framebuffer access. For a compatible Qt build that supports DRM dumb buffers, try `QT_QPA_FB_DRM=1` in `/etc/rc-printstation/hdmi.env`. EGLFS is an alternative on working EGL/GBM stacks. Wayland/XCB require an existing compositor or X session and the appropriate environment, including the display socket and authentication. One Qt output is selected. A mouse and a keyboard remain usable on a non-touch monitor.

```sh
python3 display_presence.py --inspect
udevadm info --query=property --name=/dev/input/eventN
ls -l /dev/input/by-id/ /dev/dri/ /dev/fb0
```

A direct touchscreen is identified by udev's class or direct absolute position capabilities. HDMI and the input device are discovered independently. DRM modes inform the supervisor, and Qt uses the actual screen geometry. Use `--connector HDMI-A-1` for an explicit DRM output on a multi-output device and use `--force-hdmi` when the driver offers no reliable connector status. For a pinned evdev path set `--touch /dev/input/by-id/…` or a stable udev symlink. Avoid hard-coding a transient event number for deployment.

Use `--rotation 0|90|180|270` to rotate the Qt surface, which inverse-maps pointer coordinates to its controls. Alternatively let your compositor rotate the output and calibrate the touchscreen when necessary, leaving the app rotation at 0. Avoid two independent rotations. Validate every corner and both display orientations with the deployed touch driver. Direct input hotplug is normally handled by Qt/libinput/evdev. The supervisor restarts the frontend on detected connector or pinned-input changes and the draft remains in the core.

HDMI standby blanks only the app and wakes on the next input. It stays awake during a guided examination, waiting or review. For an exposed Linux backlight device supply its sysfs basename as `FMI_HDMI_BACKLIGHT` in `hdmi.env` and grant the station user write access to that device's brightness attribute. Ordinary HDMI monitors typically need their own hardware brightness controls. Nextion keeps its native brightness and standby behaviour.

## Headless and permissions

Use `python3 tools/stationctl.py state` or `python3 tools/stationctl.py history` as the service account. The private socket in `/run/rc-printstation` is owned by that account. The CLI also accepts the semantic commands documented in the [local protocol](multi-display-ipc.md). Keep administrative access local or use the existing SSH/loopback arrangement. The hotspot retains the restricted PDF token routes. Report history, actions, printing and graphics IPC have no public listener.

## Personality and AI

- In HDMI, tap the FMI logo five times in three seconds. The wolf responds to a stroking gesture or the pet button. The same logo gesture and the simple tap button remain on Nextion. Pet counts and milestone progress persist.
- HDMI's hidden pet screen offers Awoo Permit, Certificate of Pointlessness, Certified Jank and Emotional Support Engineer. The four receipts require confirmation and carry a prominent novelty label. They have no repair number and create no historical report.
- Open Engineering Mode from the HDMI station menu or hold the Nextion version footer for one second. It is read-only.
- Turn on **Professional Mode** in HDMI settings or set it in the local socket with `python3 tools/stationctl.py settings.save '{"values":{"professional":true}}'`. It suppresses the pet, novelty output, achievement display, new counter awards, slogans and humorous farewell. Read-only engineering diagnostics remain accessible.

The offline catalogue is always available outside Professional Mode. Optional [OpenAI and llama.cpp provider setup](personality-v071.md#optional-slogan-providers) is unchanged. The API worker is the optional AI choice for 1 GB. Keep the private environment file at mode 0600 with the key outside the station service and repository. The worker checks Professional Mode before requesting new content. A request already in flight can complete, and its results remain hidden while Professional Mode is enabled. Keep local inference disabled on the Zero 3. No provider participates in guide actions or verdicts.

## Scope and remaining work

Protocol 71 firmware keeps its existing settings navigation. Professional Mode and novelty printing are available through HDMI or the private local interface. The unchanged firmware does not add buttons for them. Nextion phase and remark edits are committed at firmware workflow submission. Arbitrary characters entered in Qt are preserved by the core. The supported Nextion font encoding remains limited, so characters outside it may render as replacements there. QR links on that panel are limited to 78 bytes.

The lightweight v0.8 candidate includes the animated pet, persistent milestone progress and novelty receipts. Pong, rubber duck debugging, bouncing screensaver, fictional BIOS and emotional telemetry, horoscope, coffee, tea timer, installation anniversary, wolf mode and 42 are deferred. Use the electrical bench checklist before deployment. No devices were installed or flashed as part of candidate preparation.
