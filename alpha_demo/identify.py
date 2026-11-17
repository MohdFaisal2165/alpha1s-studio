"""Explicitly approved, bounded PC-protocol version probe; no motor opcodes."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import select
import stat
import time

REQUESTS = {'hardware': bytes.fromhex('f11f00000000000000ed'),
            'firmware': bytes.fromhex('f55f01000000000001ed')}
DESCRIPTOR = bytes.fromhex('058c0901a101090315002600ff750895408102090415002600ff750895409102c0')


def report(kind):
    return b'\0' + REQUESTS[kind].ljust(64, b'\0')


def parse(kind, raw):
    header = REQUESTS[kind][:2]
    if raw[:2] != header:
        raise ValueError('Unexpected response header')
    if kind == 'hardware':
        if len(raw) < 3 or not 1 <= raw[2] <= 48:
            raise ValueError('Invalid hardware string length')
        end = 3 + raw[2]
        text = raw[3:end]
    else:
        if len(raw) < 3 or raw[2] != 0xAA:
            raise ValueError('Firmware query not successful')
        end = 13
        text = raw[3:end]
    # Both version responses have a checksum marker in the PC protocol table.
    if len(raw) < end + 2 or raw[end] != sum(raw[2:end]) & 255 or raw[end+1] != 0xED:
        raise ValueError('Length, checksum or terminator mismatch')
    if any(raw[end+2:]):
        raise ValueError('Nonzero trailing report data')
    if not text or any(c < 32 or c > 126 for c in text):
        raise ValueError('Version is not printable ASCII')
    return text.decode('ascii')


def find_device():
    matches = []
    for p in Path('/sys/class/hidraw').glob('hidraw*'):
        fields = dict(line.split('=',1) for line in (p/'device/uevent').read_text().splitlines() if '=' in line)
        if fields.get('HID_ID') == '0003:00000483:00005750' and 'Alpha1' in fields.get('HID_NAME',''):
            if (p/'device/report_descriptor').read_bytes() != DESCRIPTOR:
                raise ValueError('HID report descriptor changed')
            matches.append(p)
    if len(matches) != 1:
        raise ValueError('Expected exactly one matching Alpha1')
    return matches[0]


def run(log):
    p = find_device()
    node = Path('/dev') / p.name
    log['device'] = str(node)
    expected = tuple(map(int, (p/'dev').read_text().strip().split(':')))
    fd = os.open(node, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if not stat.S_ISCHR(s.st_mode) or (os.major(s.st_rdev),os.minor(s.st_rdev)) != expected:
            raise ValueError('Device identity changed')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Recheck kernel identity immediately before any output.
        if find_device() != p:
            raise ValueError('Device identity changed')
        if select.select([fd],[],[],0.2)[0]:
            log['unsolicited_report_hex'] = os.read(fd,64).hex()
            raise ValueError('Unsolicited input; stop before sending')
        for kind in ('hardware','firmware'):
            entry = {'kind':kind,'request_hex':REQUESTS[kind].hex(),
                     'hid_write_hex':report(kind).hex()}
            log['queries'].append(entry)
            count = os.write(fd, report(kind))
            entry['bytes_written'] = count
            if count != 65:
                raise ValueError('Short write; no retry')
            if not select.select([fd],[],[],2.0)[0]:
                raise TimeoutError('No version reply within two seconds; no retry')
            raw = os.read(fd,64)
            entry['response_hex'] = raw.hex()
            entry['version'] = parse(kind, raw)
            time.sleep(0.1)
    finally:
        os.close(fd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--approved-identification-only', action='store_true', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()
    log = {'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'scope':'Only PC hardware/firmware version requests; once each, no retries', 'queries':[]}
    try:
        run(log)
        log['status'] = 'validated'
    except Exception as exc:
        log['status'] = 'stopped'
        log['error'] = f'{type(exc).__name__}: {exc}'
    Path(args.report).write_text(json.dumps(log,indent=2))
    print(json.dumps(log,indent=2))
    return 0 if log['status']=='validated' else 1

if __name__ == '__main__':
    raise SystemExit(main())
