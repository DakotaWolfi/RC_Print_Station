#!/usr/bin/env bash
# Run as the normal station user after testing the matching HMI.
set -euo pipefail
if [[ $EUID == 0 ]]; then echo "Run as the normal station user, not root."; exit 1; fi
replace=0
power=0
render=
db=
while (($#)); do
  case "$1" in
    --replace) replace=1; shift;;
    --enable-local-power) power=1; shift;;
    --render) render="${2:?output directory required}"; shift 2;;
    --db) db="${2:?absolute database path required}"; shift 2;;
    *) echo "Usage: $0 [--db ABSOLUTE_PATH] [--replace] [--enable-local-power] [--render DIR]"; exit 2;;
  esac
done
root="$(cd "$(dirname "$0")/.." && pwd)"
user="$(id -un)"
home="$HOME"
db="${db:-$root/reports-candidate.sqlite3}"
for value in "$root" "$home" "$user" "$db"; do
  [[ "$value" =~ ^[a-zA-Z0-9_./-]+$ ]] || { echo "Unsupported service path/user"; exit 1; }
done
[[ "$db" = /* ]] || { echo "--db requires an absolute path"; exit 1; }
backend=rc-printstation.service
admin=rc-printstation-admin.service
dest=/etc/systemd/system
unit_dir="$(mktemp -d)"
trap 'rm -r -- "$unit_dir"' EXIT
power_arg=
if ((power)); then power_arg=" --enable-local-power"; fi
cat > "$unit_dir/$backend" <<EOF
[Unit]
Description=Repair Cafe native print station
After=NetworkManager.service
[Service]
Type=simple
User=$user
SupplementaryGroups=dialout
Environment=HOME=$home
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/native_ui.py --port /dev/serial0 --baud 115200 --host 169.254.223.252 --db $db --auto-report-url$power_arg
Restart=on-failure
RestartSec=5
TimeoutStopSec=90
UMask=0077
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
EOF
cat > "$unit_dir/$admin" <<EOF
[Unit]
Description=Repair Cafe loopback administration
After=NetworkManager.service
[Service]
Type=simple
User=$user
Environment=HOME=$home
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/station_admin.py
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
EOF
if [[ -n "$render" ]]; then
  mkdir -p -- "$render"
  cp -- "$unit_dir/"*.service "$render/"
  echo "Rendered units only: $render"
  exit 0
fi
/usr/bin/python3 -c 'import serial, reportlab, dbus'
command -v nmcli >/dev/null
systemd-analyze verify "$unit_dir/$backend" "$unit_dir/$admin"
for unit in "$backend" "$admin"; do
  if systemctl is-active --quiet "$unit"; then
    echo "Stop $unit yourself before installing a replacement."
    exit 1
  fi
  if [[ -e "$dest/$unit" && $replace == 0 ]]; then
    echo "$dest/$unit already exists. Use --replace after saving the working setup."
    exit 1
  fi
done
stamp="$(date +%Y%m%d-%H%M%S)"
for unit in "$backend" "$admin"; do
  if [[ -e "$dest/$unit" ]]; then
    sudo cp -an -- "$dest/$unit" "$dest/$unit.v03-$stamp.bak"
    echo "Backup: $dest/$unit.v03-$stamp.bak"
  fi
  sudo install -m 0644 -- "$unit_dir/$unit" "$dest/$unit"
done
sudo systemctl daemon-reload
sudo systemctl enable "$backend" "$admin"
echo "Enabled at boot; no service was started."
echo "Stop any manual UART client, then: sudo systemctl start $backend $admin"
