"""One read-only PC-protocol servo-status request. No angle read-back."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import select
import stat
from .identify import find_device

REQUEST = bytes.fromhex('effe00000000000000ed')


def parse_reply(raw):
    if len(raw) < 8 or raw[:2] != b'\xef\xfe' or raw[7] != 0xed:
        raise ValueError('Unexpected servo-status frame')
    if raw[6] != sum(raw[2:6]) & 255 or any(raw[8:]):
        raise ValueError('Servo-status checksum or padding mismatch')
    status = raw[2:6]
    result = {'status_bytes_hex':status.hex(), 'set_bit_count':sum(b.bit_count() for b in status)}
    # Avoid assigning per-servo bits until byte ordering is independently verified.
    result['interpretation'] = 'All 32 status bits clear' if not any(status) else 'Some status bits set; per-servo mapping not inferred'
    return result
