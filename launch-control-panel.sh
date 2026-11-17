#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
/usr/bin/python3 scripts/close_studio_windows.py
exec /usr/bin/python3 -m alpha_demo.control_panel
