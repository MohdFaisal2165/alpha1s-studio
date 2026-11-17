"""Read kernel caches and node metadata; never open device nodes."""
import datetime
import glob
import os
from pathlib import Path
import stat
import subprocess


def command(argv):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=15)
        return dict(argv=argv, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return dict(argv=argv, error=str(exc))


def collect():
    result = {'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'mode': 'passive; no device nodes opened', 'usb': [], 'hid': [], 'nodes': []}
    result['commands'] = [command(c) for c in (
        ['uname', '-a'], ['id'], ['lsusb'], ['lsusb', '-t'],
        ['dmesg', '--color=never'], ['journalctl', '-k', '-b', '--no-pager', '-n', '150'])]
    result['os_release'] = Path('/etc/os-release').read_text()
    for p in sorted(Path('/sys/bus/usb/devices').glob('*')):
        record = {'path': str(p), 'resolved': str(p.resolve())}
        for field in ('idVendor', 'idProduct', 'manufacturer', 'product', 'busnum',
                      'devnum', 'bDeviceClass', 'bInterfaceClass', 'bInterfaceSubClass',
                      'bInterfaceProtocol', 'speed', 'uevent', 'descriptors'):
            try:
                record[field] = ((p / field).read_bytes().hex() if field == 'descriptors'
                                 else (p / field).read_text().strip())
            except OSError:
                pass
        if (p / 'driver').exists():
            record['driver'] = str((p / 'driver').resolve())
        result['usb'].append(record)
    for p in sorted(Path('/sys/class/hidraw').glob('*')):
        record = {'path': str(p), 'resolved': str(p.resolve()),
                  'udev': command(['udevadm', 'info', '--query=all', '--path', str(p)])}
        for field in ('dev', 'device/uevent', 'device/report_descriptor'):
            try:
                record[field] = ((p / field).read_bytes().hex() if field.endswith('descriptor')
                                 else (p / field).read_text())
            except OSError as exc:
                record[field] = {'error': str(exc)}
        result['hid'].append(record)
    for pattern in ('/dev/hidraw*', '/dev/ttyUSB*', '/dev/ttyACM*'):
        for name in sorted(glob.glob(pattern)):
            try:
                s = os.stat(name)
                result['nodes'].append(dict(path=name, mode=stat.filemode(s.st_mode),
                    uid=s.st_uid, gid=s.st_gid, readable=os.access(name, os.R_OK),
                    writable=os.access(name, os.W_OK),
                    udev=command(['udevadm', 'info', '--query=all', '--name', name])))
            except OSError as exc:
                result['nodes'].append(dict(path=name, error=str(exc)))
    return result
