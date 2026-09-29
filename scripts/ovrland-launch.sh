#!/bin/sh
# Desktop recovery entry point: start the backend before opening the dashboard.
set -eu

ovrland_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
systemctl --user start ovrland.service
exec /bin/sh "$ovrland_root/scripts/ovrland-kiosk.sh"
