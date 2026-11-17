"""Small, read-only Alpha 1S storage checks. Never formats or writes a device."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import time


def summarize_sector(data):
    return {'bytes': len(data), 'all_zero': bool(data) and not any(data),
            'boot_signature': data[510:512].hex() if len(data) >= 512 else None,
            'first_64_hex': data[:64].hex()}


def classify(samples):
    if not samples or any(s.get('error') or s.get('bytes') != 512 for s in samples):
        return 'read_failed'
    if all(s['all_zero'] for s in samples):
        return 'zero_data_returned'
    return 'data_found_filesystem_not_yet_verified'


def identify(device):
    path = Path(device)
    info = path.stat()
    if not stat.S_ISBLK(info.st_mode):
        raise ValueError('Expected a robot block device.')
    block = Path('/sys/dev/block') / f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'
    resolved = block.resolve(strict=True)
    if (resolved / 'partition').exists():
        raise ValueError('Select the whole robot disk, not a partition.')
    for parent in resolved.parents:
        if (parent / 'idVendor').exists():
            if (parent / 'idVendor').read_text().strip() != '0483' or (parent / 'idProduct').read_text().strip() != '5720':
                raise ValueError('Device is not Alpha USB storage.')
            return int((resolved / 'size').read_text()), str(resolved)
    raise ValueError('Cannot verify robot USB identity.')


def read_sector(device, sector):
    # O_DIRECT via dd avoids cached data and requests one 512-byte block only.
    proc = subprocess.Popen(['/usr/bin/dd', f'if={device}', 'bs=512', 'count=1',
                             f'skip={sector}', 'iflag=direct', 'status=none'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    start = time.monotonic()
    try:
        data, error = proc.communicate(timeout=12)
    except subprocess.TimeoutExpired:
        proc.kill()
        # A kernel-blocked read may outlive its timeout. Do not queue more reads.
        return {'sector': sector, 'error': 'Read timed out; further reads stopped.'}
    result = {'sector': sector, 'seconds': round(time.monotonic()-start, 3), **summarize_sector(data)}
    if proc.returncode:
        result['error'] = error.decode(errors='replace').strip()
    return result


def check(device, reader=read_sector):
    sectors, identity = identify(device)
    if sectors < 4:
        raise ValueError('Invalid card size.')
    result = {'device': device, 'identity': identity, 'sectors': sectors,
              'source_read_only': True, 'samples': []}
    for sector in sorted(set((0, min(2048, sectors-1), sectors//2, sectors-1))):
        # Recheck identity before each read; never follow a newly attached disk.
        if identify(device) != (sectors, identity):
            raise RuntimeError('Device changed during check.')
        sample = reader(device, sector)
        result['samples'].append(sample)
        if sample.get('error'):
            break
    result['status'] = classify(result['samples'])
    result['safe_to_upload'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', default='/dev/sda')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = check(args.device)
    except Exception as exc:
        result = {'status': 'check_failed', 'error': str(exc), 'safe_to_upload': False}
    args.report.write_text(json.dumps(result, indent=2)+'\n')
    if os.geteuid() == 0 and 'SUDO_UID' in os.environ:
        os.chown(args.report, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
