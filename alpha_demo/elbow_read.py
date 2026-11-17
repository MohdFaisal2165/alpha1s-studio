"""One approved servo-3 position request; may release holding torque. Never moves."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import select
import stat
from .identify import find_device
from .session_probe import exchange

REQUEST = bytes.fromhex('faaf03020000000005ed')

def inspect_frame(raw):
    # Capture fields without assuming the USB response's status/angle semantics.
    if len(raw) != 64 or raw[:2] != b'\xfa\xaf' or raw[9] != 0xed:
        raise ValueError('Unexpected position response framing')
    if raw[8] != sum(raw[2:8]) & 255 or any(raw[10:]):
        raise ValueError('Invalid position response checksum or padding')
    return {'data_bytes_hex':raw[2:8].hex(), 'interpretation':'Raw fields only; no motion authorized by this response'}

def parse_position(raw):
    inspect_frame(raw)
    if raw[2] != 3 or raw[3] != 0xaa:
        raise ValueError('Wrong servo or unsuccessful position reply')
    angle=int.from_bytes(raw[6:8], 'big', signed=True)
    if not 0 <= angle <= 180:
        raise ValueError('Position outside expected angular range')
    return angle


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--approved-supported-elbow-release',action='store_true',required=True)
    ap.add_argument('--report',required=True)
    a=ap.parse_args()
    path=Path(a.report)
    log={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'servo_id':3,
         'scope':'Single servo-3 angle request which may release elbow; no movement or automatic relock', 'exchanges':[]}
    path.write_text(json.dumps(log,indent=2))
    fd=None
    attempted=False
    try:
        p=find_device()
        expected=tuple(map(int,(p/'dev').read_text().strip().split(':')))
        fd=os.open('/dev/'+p.name,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
        s=os.fstat(fd)
        if not stat.S_ISCHR(s.st_mode) or (os.major(s.st_rdev),os.minor(s.st_rdev))!=expected:
            raise ValueError('Device identity mismatch')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if find_device()!=p:raise ValueError('Device changed')
        if select.select([fd],[],[],.2)[0]:raise ValueError('Unsolicited input; no commands sent')
        exchange(fd,'status',log)
        attempted=True
        exchange(fd,'connect',log)
        exchange(fd,'version',log)
        entry={'name':'elbow_position_release', 'request_hex':REQUEST.hex()}
        log['exchanges'].append(entry)
        log['elbow_may_be_released']=True
        path.write_text(json.dumps(log,indent=2))
        entry['bytes_written']=os.write(fd,b'\0'+REQUEST.ljust(64,b'\0'))
        if entry['bytes_written']!=65:raise ValueError('Short write; no retry')
        if not select.select([fd],[],[],2)[0]:raise TimeoutError('No position reply; no retry')
        raw=os.read(fd,64)
        entry['response_hex']=raw.hex()
        entry['result']=inspect_frame(raw)
        log['status']='response_captured_for_review'
    except Exception as e:
        log['status']='stopped'
        log['error']=f'{type(e).__name__}: {e}'
    finally:
        if fd is not None:
            if attempted:
                try:exchange(fd,'disconnect',log)
                except Exception as e:log['cleanup_error']=f'{type(e).__name__}: {e}'
            os.close(fd)
        path.write_text(json.dumps(log,indent=2))
    print(json.dumps(log,indent=2))
    return 0 if log['status']=='response_captured_for_review' and 'cleanup_error' not in log else 1

if __name__=='__main__':raise SystemExit(main())
