#!/usr/bin/env bash
# Run as the normal station user, from the candidate checkout.
set -euo pipefail
if [[ $EUID == 0 ]]; then echo "Run as your normal user, not root."; exit 1; fi
root="$(cd "$(dirname "$0")/.." && pwd)"
user="$(id -un)"
home="$HOME"
# Restrict paths to simple service-safe characters.
for value in "$root" "$home" "$user"; do
  [[ "$value" =~ ^[a-zA-Z0-9_./-]+$ ]] || { echo "Unsupported service path/user"; exit 1; }
done
/usr/bin/python3 -c 'import serial, reportlab'
sudo tee /etc/systemd/system/rc-printstation.service >/dev/null <<EOF
[Unit]
Description=Repair Cafe native print station
After=network.target
[Service]
Type=simple
User=$user
SupplementaryGroups=dialout
Environment=HOME=$home
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/native_ui.py --port /dev/serial0 --baud 115200 --host 169.254.223.252 --db $root/reports-candidate.sqlite3 --auto-report-url
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/rc-printstation-admin.service >/dev/null <<EOF
[Unit]
Description=Repair Cafe local administration
After=network.target
[Service]
Type=simple
User=$user
Environment=HOME=$home
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/station_admin.py
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable rc-printstation.service rc-printstation-admin.service
echo "Enabled for boot. Stop any manually running station processes first."
echo "Then: sudo systemctl start rc-printstation rc-printstation-admin"
