"""Local, non-secret robot connection configuration. Never discovers/connects on import."""
import json
import os
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def bluetooth_address(root=ROOT):
    value=os.environ.get('ALPHA1S_BLUETOOTH_ADDRESS','').strip()
    if not value:
        path=root/'data/settings.json'
        if path.exists():value=json.loads(path.read_text()).get('bluetooth_address','').strip()
    if value and not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',value):
        raise ValueError('Set a valid ALPHA1S_BLUETOOTH_ADDRESS or data/settings.json Bluetooth address.')
    return value.upper()
