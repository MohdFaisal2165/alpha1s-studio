"""Supported elbow position read; may release torque, never commands movement."""
import argparse,datetime,fcntl,json,os,select,stat,time
from pathlib import Path
from .identify import find_device
from .session_probe import PACKETS,ack,version_reply

def packet(servo,command,angle=0):
    if type(servo) is not int or servo not in (3,6):raise ValueError('Elbows only')
    if command=='version':header=b'\xfc\xcf';data=bytes([servo,1,0,0,0,0])
    elif command=='read':header=b'\xfa\xaf';data=bytes([servo,2,0,0,0,0])
    else:raise ValueError('Unsupported request')
    return header+data+bytes([sum(data)&255,237])

def frame(raw,servo):
    if len(raw)!=64 or raw[:3]!=bytes([250,175,servo]) or raw[9]!=237 or raw[8]!=sum(raw[2:8])&255 or any(raw[10:]):
        raise ValueError('Invalid servo reply')

def position(raw,servo):
    frame(raw,servo)
    if raw[3]!=170:raise ValueError('Position read failed')
    value=int.from_bytes(raw[6:8],'big',signed=True)
    if not 0<=value<=180:raise ValueError('Invalid angle')
    return value

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--approved-supported-position-read',action='store_true',required=True)
    ap.add_argument('--servo-id',type=int,choices=(3,6),required=True);ap.add_argument('--report',required=True)
    a=ap.parse_args();sid=a.servo_id;path=Path(a.report)
    log={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'servo_id':sid,'exchanges':[], 'scope':'Single supported elbow position read; may release joint; no movement or relock'}
    def save():path.write_text(json.dumps(log,indent=2))
    save();fd=None;connected=False
    def exchange(name,payload):
        if select.select([fd],[],[],0)[0]:raise ValueError('Unexpected pending input; no command sent')
        e={'name':name,'request_hex':payload.hex(),'delivery':'attempting'};log['exchanges'].append(e);save()
        e['bytes_written']=os.write(fd,b'\0'+payload.ljust(64,b'\0'))
        if e['bytes_written']!=65:raise ValueError('Short write; no retry')
        if not select.select([fd],[],[],2)[0]:raise TimeoutError('No reply; no retry')
        raw=os.read(fd,64);e['response_hex']=raw.hex();e['delivery']='sent once';save();return raw
    try:
        p=find_device();expected=tuple(map(int,(p/'dev').read_text().strip().split(':')))
        fd=os.open('/dev/'+p.name,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW);s=os.fstat(fd)
        if not stat.S_ISCHR(s.st_mode) or (os.major(s.st_rdev),os.minor(s.st_rdev))!=expected:raise ValueError('Wrong device')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if find_device()!=p:raise ValueError('Device changed')
        if select.select([fd],[],[],.2)[0]:raise ValueError('Unsolicited data')
        connected=True;ack(exchange('connect',PACKETS['connect']))
        version_reply(exchange('version',packet(sid,'version')),sid)
        log['joint_may_be_released']=True;save()
        current=position(exchange('position_release',packet(sid,'read')),sid)
        log['start_degrees']=current
        log['status']='position_validated'
    except Exception as e:log['status']='stopped';log['error']=f'{type(e).__name__}: {e}'
    finally:
        if fd is not None:
            if connected:
                try:ack(exchange('disconnect',PACKETS['disconnect']));log['disconnected']=True
                except Exception as e:log['cleanup_error']=str(e)
            os.close(fd)
        save()
    print(json.dumps(log,indent=2))
    return 0 if log['status']=='position_validated' and log.get('disconnected') else 1
if __name__=='__main__':raise SystemExit(main())
