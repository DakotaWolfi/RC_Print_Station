#!/usr/bin/env bash
# Render first. Unit installation is explicit and does not start services.
set -euo pipefail
if ((EUID == 0)); then echo "Run as the station user."; exit 1; fi
mode=auto
board=pi4
backend=linuxfb
rotation=0
port=
db=
render=
host=
tcp=
touch=
connector=
power=0
replace=0
install=0
force=0
web=0
fallback=0
desktop=0
while (($#)); do
    case "$1" in
        --mode) mode="${2:?mode required}"; shift 2;;
        --board) board="${2:?board required}"; shift 2;;
        --backend) backend="${2:?backend required}"; shift 2;;
        --rotation) rotation="${2:?degrees required}"; shift 2;;
        --nextion-port) port="${2:?device required}"; shift 2;;
        --touch) touch="${2:?input device required}"; shift 2;;
        --connector) connector="${2:?DRM connector required}"; shift 2;;
        --printer-host) host="${2:?IPv4 address required}"; shift 2;;
        --printer-port) tcp="${2:?TCP port required}"; shift 2;;
        --db) db="${2:?absolute database path required}"; shift 2;;
        --render) render="${2:?output directory required}"; shift 2;;
        --web) web=1; shift;;
        --hotspot-fallback) fallback=1; shift;;
        --force-hdmi) force=1; shift;;
        --enable-local-power) power=1; shift;;
        --replace) replace=1; shift;;
        --install) install=1; shift;;
        *) echo "Usage: $0 --db PATH [--board pi4|zero3] [--mode auto|nextion|hdmi|both|headless] [--nextion-port PATH] [--backend linuxfb|eglfs|wayland|xcb] [--rotation DEGREES] [--touch PATH] [--connector NAME] [--force-hdmi] [--web] [--hotspot-fallback] [--printer-host ADDRESS] [--printer-port PORT] [--enable-local-power] [--render DIR | --install [--replace]]"; exit 2;;
    esac
done
[[ "$mode" =~ ^(auto|nextion|hdmi|both|headless)$ ]]
[[ "$board" =~ ^(pi4|zero3)$ ]]
[[ "$backend" =~ ^(linuxfb|eglfs|wayland|xcb|offscreen)$ ]]
[[ "$rotation" =~ ^(0|90|180|270)$ ]]
[[ "$db" = /* ]] || { echo "Supply the existing or copied database with --db ABSOLUTE_PATH."; exit 2; }
((install==1)) || [[ -n "$render" ]] || { echo "Use --render DIR or --install."; exit 2; }
if ((install)) && [[ -n "$render" ]]; then echo "Choose --render or --install."; exit 2; fi
if [[ -z "$port" ]]; then
    if [[ "$board" == zero3 && "$mode" =~ ^(auto|nextion|both)$ ]]; then
        echo "Specify the UART selected on your Zero 3 image with --nextion-port."
        exit 2
    fi
    port=/dev/serial0
fi
root="$(cd "$(dirname "$0")/.." && pwd)"
user="$(id -un)"
home_dir="$HOME"
group="$(id -gn)"
for value in "$root" "$user" "$home_dir" "$db" "$group" "$port" "$touch" "$connector"; do
    [[ "$value" =~ ^[a-zA-Z0-9_./-]*$ ]] || { echo "Unsupported service path/identity."; exit 2; }
done
[[ "$port" = /* ]] || { echo "Nextion device must be an absolute path."; exit 2; }
if [[ -n "$touch" && "$touch" != /* ]]; then echo "Input device must be an absolute path."; exit 2; fi
dest=/etc/systemd/system
endpoint="$(/usr/bin/python3 "$root/tools/printer_endpoint.py" "$dest/rc-printstation.service" "$host" "$tcp")"
read -r host tcp <<<"$endpoint"
power_param=
if ((power)); then power_param=" --enable-local-power"; fi
hdmi_args=
if ((force)); then hdmi_args=" --force"; fi
if [[ -n "$touch" ]]; then hdmi_args+=" --touch $touch"; fi
if [[ -n "$connector" ]]; then hdmi_args+=" --connector $connector"; fi
unit_dir="$(mktemp -d)"
trap 'rm -r -- "$unit_dir"' EXIT
units=(rc-printstation.service rc-printstation-admin.service)
fallback_param=
if ((fallback)); then fallback_param=" --hotspot-fallback"; fi
cat > "$unit_dir/rc-printstation.service" <<EOF
[Unit]
Description=FMI Printstation shared core
After=NetworkManager.service
[Service]
Type=simple
User=$user
Group=$group
SupplementaryGroups=dialout
Environment=HOME=$home_dir
EnvironmentFile=-/etc/rc-printstation/benning.env
WorkingDirectory=$root
RuntimeDirectory=rc-printstation
RuntimeDirectoryMode=0700
ExecStart=/usr/bin/python3 $root/station_service.py --mode $mode --db $db --port $port --host $host --printer-port $tcp --auto-report-url$power_param$fallback_param
Restart=on-failure
RestartSec=4
TimeoutStopSec=90
UMask=0077
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
EOF
cat > "$unit_dir/rc-printstation-admin.service" <<EOF
[Unit]
Description=FMI loopback administration
After=NetworkManager.service
[Service]
Type=simple
User=$user
Group=$group
Environment=HOME=$home_dir
EnvironmentFile=-/etc/rc-printstation/benning.env
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/station_admin.py --db $db
Restart=on-failure
RestartSec=4
UMask=0077
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
EOF
if ((web)); then
    units+=(rc-printstation-web.service)
    cat > "$unit_dir/rc-printstation-web.service" <<EOF
[Unit]
Description=FMI authenticated operator web gateway
Wants=rc-printstation.service
After=rc-printstation.service
ConditionPathExists=$home_dir/.config/rc-printstation/web-auth.json
[Service]
Type=simple
User=$user
Group=$group
Environment=HOME=$home_dir
EnvironmentFile=-/etc/rc-printstation/web.env
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/web_hmi.py
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
EOF
fi
if [[ "$mode" =~ ^(auto|hdmi|both)$ && "$backend" =~ ^(wayland|xcb)$ ]]; then
    desktop=1
    cat > "$unit_dir/fmi-printstation-hdmi.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=FMI Printstation HDMI
Exec=/usr/bin/python3 $root/display_presence.py --mode $mode --backend $backend --rotation $rotation$hdmi_args
Terminal=false
EOF
elif [[ "$mode" =~ ^(auto|hdmi|both)$ ]]; then
    units+=(rc-printstation-hdmi.service)
    cat > "$unit_dir/rc-printstation-hdmi.service" <<EOF
[Unit]
Description=FMI Printstation HDMI discovery and Qt kiosk
Wants=rc-printstation.service
After=rc-printstation.service
[Service]
Type=simple
User=$user
Group=$group
SupplementaryGroups=video input
Environment=HOME=$home_dir
EnvironmentFile=-/etc/rc-printstation/hdmi.env
WorkingDirectory=$root
ExecStart=/usr/bin/python3 $root/display_presence.py --mode $mode --backend $backend --rotation $rotation$hdmi_args
Restart=on-failure
RestartSec=4
TimeoutStopSec=8
UMask=0077
NoNewPrivileges=yes
[Install]
WantedBy=multi-user.target
EOF
fi
if [[ -n "$render" ]]; then
    mkdir -p -- "$render"
    cp -- "$unit_dir/"*.service "$render/"
    if ((desktop)); then cp -- "$unit_dir/fmi-printstation-hdmi.desktop" "$render/"; fi
    echo "Rendered units only in $render"
    exit 0
fi
/usr/bin/python3 -c 'import serial, reportlab, dbus'
if ((desktop)) || [[ " ${units[*]} " == *" rc-printstation-hdmi.service "* ]]; then
    /usr/bin/python3 -c 'import PyQt5.QtWidgets'
fi
if [[ " ${units[*]} " != *" rc-printstation-hdmi.service "* ]]; then
    if systemctl is-enabled --quiet rc-printstation-hdmi.service || systemctl is-active --quiet rc-printstation-hdmi.service; then
        echo "Stop and disable the existing HDMI service before changing to $mode."
        exit 1
    fi
fi
if ((!web)); then
    if systemctl is-enabled --quiet rc-printstation-web.service || systemctl is-active --quiet rc-printstation-web.service; then
        echo "Stop and disable the existing web gateway before omitting --web."
        exit 1
    fi
fi
desktop_path="$home_dir/.config/autostart/fmi-printstation-hdmi.desktop"
if [[ -e "$desktop_path" ]] && { ((!desktop)) || ((!replace)); }; then
    echo "Existing desktop autostart detected. Review it before switching profiles, or use --replace."
    exit 1
fi
systemd-analyze verify "$unit_dir/"*.service
for unit in "${units[@]}"; do
    if systemctl is-active --quiet "$unit"; then
        echo "Stop $unit before replacing it."
        exit 1
    fi
    if [[ -e "$dest/$unit" && "$replace" == 0 ]]; then
        echo "$unit exists. Review the upgrade and use --replace."
        exit 1
    fi
done
stamp="$(date +%Y%m%d-%H%M%S)"
for unit in "${units[@]}"; do
    if [[ -e "$dest/$unit" ]]; then sudo cp -an "$dest/$unit" "$dest/$unit.$stamp.bak"; fi
    sudo install -m 0644 "$unit_dir/$unit" "$dest/$unit"
done
if ((desktop)); then
    mkdir -p -- "$(dirname "$desktop_path")"
    if [[ -e "$desktop_path" ]]; then cp -an -- "$desktop_path" "$desktop_path.$stamp.bak"; fi
    install -m 0644 "$unit_dir/fmi-printstation-hdmi.desktop" "$desktop_path"
fi
sudo systemctl daemon-reload
sudo systemctl enable "${units[@]}"
echo "Units enabled for subsequent boots. No service was started."
