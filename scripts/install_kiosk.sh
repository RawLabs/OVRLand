#!/bin/sh
# Install or remove OVRLand's per-user boot and graphical-session launchers.
set -eu

ovrland_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
service_dir="$HOME/.config/systemd/user"
autostart_dir="$HOME/.config/autostart"
service_file="$service_dir/ovrland.service"
desktop_file="$autostart_dir/ovrland-kiosk.desktop"

case "${1:-install}" in
  install)
    if [ ! -x "$ovrland_root/.venv/bin/python" ]; then
      echo "Missing $ovrland_root/.venv/bin/python. Create the virtual environment first." >&2
      exit 1
    fi
    mkdir -p "$service_dir" "$autostart_dir"
    sed "s|@OVRLAND_ROOT@|$ovrland_root|g" "$ovrland_root/deploy/ovrland.service.in" > "$service_file"
    sed "s|@OVRLAND_ROOT@|$ovrland_root|g" "$ovrland_root/deploy/ovrland-kiosk.desktop.in" > "$desktop_file"
    systemctl --user daemon-reload
    systemctl --user enable --now ovrland.service
    echo "OVRLand will open full screen at the next graphical login."
    ;;
  remove)
    systemctl --user disable --now ovrland.service 2>/dev/null || true
    rm -f "$service_file" "$desktop_file"
    systemctl --user daemon-reload
    echo "OVRLand kiosk startup removed."
    ;;
  *)
    echo "Usage: $0 [install|remove]" >&2
    exit 2
    ;;
esac
