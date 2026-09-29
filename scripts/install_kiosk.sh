#!/bin/sh
# Install or remove OVRLand's per-user boot and graphical-session launchers.
set -eu

ovrland_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
service_dir="$HOME/.config/systemd/user"
autostart_dir="$HOME/.config/autostart"
service_file="$service_dir/ovrland.service"
desktop_file="$autostart_dir/ovrland-kiosk.desktop"
applications_dir="$HOME/.local/share/applications"
app_desktop_file="$applications_dir/ovrland.desktop"

case "${1:-install}" in
  install)
    if [ ! -x "$ovrland_root/.venv/bin/python" ]; then
      echo "Missing $ovrland_root/.venv/bin/python. Create the virtual environment first." >&2
      exit 1
    fi
    if ! command -v wmctrl >/dev/null 2>&1; then
      echo "Missing wmctrl. Install it with: sudo apt install wmctrl" >&2
      exit 1
    fi
    if ! command -v chromium >/dev/null 2>&1 && ! command -v chromium-browser >/dev/null 2>&1; then
      echo "Missing Chromium. Install chromium before setting up the kiosk." >&2
      exit 1
    fi
    if ! "$ovrland_root/.venv/bin/python" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
      echo "The virtual environment is missing FastAPI or Uvicorn. Install requirements.lock.txt first." >&2
      exit 1
    fi
    mkdir -p "$service_dir" "$autostart_dir" "$applications_dir"
    render_template() {
      "$ovrland_root/.venv/bin/python" -c 'from pathlib import Path; import sys; template=Path(sys.argv[1]).read_text(); Path(sys.argv[2]).write_text(template.replace("@OVRLAND_ROOT@", sys.argv[3]))' "$1" "$2" "$ovrland_root"
    }
    render_template "$ovrland_root/deploy/ovrland.service.in" "$service_file"
    render_template "$ovrland_root/deploy/ovrland-kiosk.desktop.in" "$desktop_file"
    render_template "$ovrland_root/deploy/ovrland.desktop.in" "$app_desktop_file"
    systemctl --user daemon-reload
    systemctl --user enable --now ovrland.service
    echo "OVRLand will open full screen at the next graphical login."
    ;;
  remove)
    systemctl --user disable --now ovrland.service 2>/dev/null || true
    rm -f "$service_file" "$desktop_file" "$app_desktop_file"
    systemctl --user daemon-reload
    echo "OVRLand kiosk startup removed."
    ;;
  *)
    echo "Usage: $0 [install|remove]" >&2
    exit 2
    ;;
esac
