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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--approved-status-only', action='store_true', required=True)
    ap.add_argument('--report', required=True)
    args=ap.parse_args()
    log={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'command':'read_servo_status', 'request_hex':REQUEST.hex(), 'transmissions':0}
    fd=None
    try:
        p=find_device(); node=Path('/dev')/p.name
        expected=tuple(map(int,(p/'dev').read_text().strip().split(':')))
        fd=os.open(node,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
        s=os.fstat(fd)
        if not stat.S_ISCHR(s.st_mode) or (os.major(s.st_rdev),os.minor(s.st_rdev))!=expected:
            raise ValueError('Device identity mismatch')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if find_device()!=p:raise ValueError('Device changed')
        log['device']=str(node)
        if select.select([fd],[],[],0.2)[0]:
            log['unsolicited_hex']=os.read(fd,64).hex()
            raise ValueError('Unsolicited input; no command sent')
        payload=b'\0'+REQUEST.ljust(64,b'\0')
        log['hid_write_hex']=payload.hex()
        count=os.write(fd,payload)
        log['transmissions']=1;log['bytes_written']=count
        if count!=65:raise ValueError('Short write; no retry')
        if not select.select([fd],[],[],2)[0]:raise TimeoutError('No reply; no retry')
        raw=os.read(fd,64);log['response_hex']=raw.hex()
        log['result']=parse_reply(raw);log['status']='acknowledged'
    except Exception as e:
        log['status']='unverified';log['error']=f'{type(e).__name__}: {e}'
    finally:
        if fd is not None:os.close(fd)
    Path(args.report).write_text(json.dumps(log,indent=2));print(json.dumps(log,indent=2))
    return 0 if log['status']=='acknowledged' else 1

if __name__=='__main__':raise SystemExit(main())
