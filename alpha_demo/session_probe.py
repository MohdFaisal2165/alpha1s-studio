"""Bounded official PC connect -> servo-version -> disconnect diagnostic."""
import argparse, datetime, fcntl, json, os, select, stat, time
from pathlib import Path
from .identify import find_device

from .servo_status import parse_reply as status_reply
PACKETS = {
 'status':bytes.fromhex('effe00000000000000ed'),
 'connect':bytes.fromhex('f44f01010000000002ed'),

 'disconnect':bytes.fromhex('f44f01000000000001ed'),
}

def ack(raw):
    if raw[:4]!=bytes.fromhex('f44faaed') or any(raw[4:]):
        raise ValueError('PC connection acknowledgement invalid')
    return 'acknowledged'

def version_packet(servo_id):
    if type(servo_id) is not int or servo_id not in (1,2,3):
        raise ValueError('Only the three reviewed arm IDs are allowed')
    return bytes([0xfc,0xcf,servo_id,1,0,0,0,0,servo_id+1,0xed])

def version_reply(raw,servo_id):
    if len(raw)<10 or raw[:2]!=b'\xfc\xcf' or raw[8]!=sum(raw[2:8])&255 or raw[9]!=0xed or any(raw[10:]):
        raise ValueError('Malformed servo-version reply')
    if raw[3]!=0xaa:
        raise ValueError(f'Robot returned failure status {raw[3]:02x}; returned ID {raw[2]} is not trusted')
    if raw[2]!=servo_id:
        raise ValueError('Servo reply ID mismatch')
    return {'servo_id':servo_id,'version_bytes_hex':raw[4:8].hex()}

def exchange(fd,name,log):
    payload=version_packet(log['servo_id']) if name=='version' else PACKETS[name];r={'name':name,'request_hex':payload.hex()};log['exchanges'].append(r)
    report=b'\0'+payload.ljust(64,b'\0')
    r['bytes_written']=os.write(fd,report)
    if r['bytes_written']!=65:raise ValueError('Short write; no retry')
    if not select.select([fd],[],[],2)[0]:raise TimeoutError('Reply timeout; no retry')
    raw=os.read(fd,64);r['response_hex']=raw.hex()
    r['result']=(status_reply(raw) if name=='status' else version_reply(raw,log['servo_id']) if name=='version' else ack(raw))
    time.sleep(.15)
    return r['result']

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--approved-session-probe',action='store_true',required=True);ap.add_argument('--report',required=True);ap.add_argument('--servo-id',type=int,choices=(1,2,3),default=3);a=ap.parse_args()
    log={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exchanges':[], 'servo_id':a.servo_id}
    fd=None;attempted=False
    try:
        p=find_device();expected=tuple(map(int,(p/'dev').read_text().strip().split(':')))
        fd=os.open('/dev/'+p.name,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
        s=os.fstat(fd)
        if not stat.S_ISCHR(s.st_mode) or (os.major(s.st_rdev),os.minor(s.st_rdev))!=expected:raise ValueError('Wrong device')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if find_device()!=p:raise ValueError('Device changed')
        if select.select([fd],[],[],.2)[0]:raise ValueError('Unsolicited input; no commands sent')
        log['before']=exchange(fd,'status',log)
        attempted=True
        exchange(fd,'connect',log)
        exchange(fd,'version',log)
        log['status']='servo_version_validated'
    except Exception as e:log['status']='stopped';log['error']=f'{type(e).__name__}: {e}'
    finally:
        if fd is not None:
            if attempted:
                try:
                    exchange(fd,'disconnect',log)
                    log['after']=exchange(fd,'status',log)
                    log['status_bytes_unchanged']=log.get('before')==log['after']
                except Exception as e:log['cleanup_error']=f'{type(e).__name__}: {e}'
            os.close(fd)
    Path(a.report).write_text(json.dumps(log,indent=2));print(json.dumps(log,indent=2))
    return 0 if log['status']=='servo_version_validated' and 'cleanup_error' not in log else 1
if __name__=='__main__':raise SystemExit(main())
