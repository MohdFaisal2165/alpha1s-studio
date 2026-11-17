"""One explicit PC-protocol stop-playback request. Not an emergency stop."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import select
import stat
from .identify import find_device

REQUEST = bytes.fromhex('f22f00000000000000ed')


def parse_reply(raw):
    # PC protocol stop response has status then ED, with no checksum marker.
    if len(raw) < 4 or raw[:2] != b'\xf2\x2f' or raw[3] != 0xed or any(raw[4:]):
        raise ValueError('Unexpected stop-playback response; preserve raw bytes')
    if raw[2] != 0xaa:
        raise ValueError(f'Stop playback not acknowledged: status {raw[2]:02x}')
    return 'acknowledged; physical stopping behavior not verified'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--approved-stop-playback', action='store_true', required=True)
    ap.add_argument('--report', required=True)
    args=ap.parse_args()
    log={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'command':'stop_playback', 'request_hex':REQUEST.hex(), 'transmissions':0}
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
