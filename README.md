# Repair Café Print Station

Development prototype for Repair Café Riehen. Python 3.11+ on Raspberry Pi 4B, later Orange Pi Zero 3. Nextion NX8048T070_011 HMI, Epson network ESC/POS printer and modular electrical safety tester integration.

## First boot

Back up the existing SD card. Inspect existing services and network configuration before changing anything. Do not enable a DHCP server on a shared network. The prototype does not modify system services or networking.

```sh
python3 station.py diagnose
python3 station.py simulate --ticket DEV-001 --device 'Demo appliance'
python3 station.py history
python3 -m unittest discover -s tests
```

Printer test (replace IP with the actual printer address):

```sh
python3 station.py printer-test --host 10.88.77.30
```

Nextion probe (verify voltage levels, power and UART availability first; use a suitable USB TTL adapter if needed):

```sh
sudo apt install python3-serial
python3 station.py display-test --port /dev/ttyUSB0 --baud 9600
```

All reports are simulated; no actual safety certification is produced. The real tester protocol is not implemented. The Gen 3 printer at `169.254.223.252:9100` and legacy hybrid HMI have been physically tested. The new native HMI is a separate candidate, with bench validation outstanding.

## Native portrait HMI candidate (v0.3)

![Native Nextion screens](hmi/previews/overview.png)

The candidate uses the Nextion Basic NX8048T070_011R at 270° (480 × 800) and 115200 baud. All seven pages, the Swiss QWERTZ keyboard, touch feedback and page transitions run on the panel. Python handles SQLite, the existing Epson receipt sender and optional local PDF downloads.

- [Editable HMI project (ZIP; extract before opening)](hmi/build/FMI_RC_native_v0_3.zip)
- [Setup, build and rollback](hmi/README.md)
- [Protocol and component contract](docs/native-hmi-protocol.md)
- [Tool investigation](docs/nextion-tooling.md)
- [Validation evidence and remaining bench checks](hmi/VALIDATION.md)

The original compiling HMI is preserved byte for byte inside `hmi/reference/FMI_RC_Printstation_working.zip`. `nextion_ui.py` remains the legacy backend. Complete the Editor and physical checks before adopting the candidate as the working installation.

After uploading the candidate on a development display:

```sh
python3 -m pip install -r requirements.txt
python3 native_ui.py --port /dev/serial0 --host 169.254.223.252
```

For PDF downloads, add `--report-url http://YOUR-PI-LAN-IP:8080`. The phone must reach that address. The app does not configure Wi-Fi, Ethernet, DHCP or system services.

## Project progress

See the [living project roadmap and checklist](ROADMAP.md) for completed tasks, outstanding work, hardware validation and current blockers.

## Station administration (candidate)

Run `python3 station_admin.py` as the same user as native_ui.py. The admin server binds to 127.0.0.1:8081 only. For remote access use an SSH tunnel, e.g. `ssh -L 8081:127.0.0.1:8081 jenna@192.168.200.241`, then open http://127.0.0.1:8081. Wi-Fi controls require NetworkManager and permission to use nmcli. Changing the Wi-Fi can disconnect SSH; arrange local access before doing so. Passwords are not logged by the app but are briefly passed in nmcli process arguments. Receipt options are saved in ~/.config/rc-printstation/receipt.json and read per print.

Use `--auto-report-url` instead of a fixed `--report-url` to discover wlan0 IPv4 and update QR links automatically. Previously issued QR links still contain the old address. No native HMI firmware changes are included in this update. The graphical header and administration features require bench testing.
