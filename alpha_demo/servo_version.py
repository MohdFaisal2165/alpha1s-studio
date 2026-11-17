"""One servo 3 version query; no movement, unlock or firmware modification."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import select
import stat
from .identify import find_device

REQUEST = bytes.fromhex('fccf03010000000004ed')


def parse_reply(raw):
    if len(raw)<10 or raw[:2]!=b'\xfc\xcf' or raw[2]!=3 or raw[3]!=0xaa:
        raise ValueError('Unexpected servo-version header, ID or status')
    if raw[8] != sum(raw[2:8]) & 255 or raw[9]!=0xed or any(raw[10:]):
        raise ValueError('Servo-version checksum, terminator or padding mismatch')
    return {'servo_id':3, 'version_bytes_hex':raw[4:8].hex()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--approved-servo-version-only', action='store_true', required=True)
    ap.add_argument('--report', required=True)
    args=ap.parse_args()
    log={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'command':'servo_3_version', 'request_hex':REQUEST.hex(), 'transmissions':0}
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
