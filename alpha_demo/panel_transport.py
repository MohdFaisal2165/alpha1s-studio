"""All-motor manual transport. Angle reads ONLY in explicit supported refresh."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import select
import stat
import threading
import time
from .identify import find_device, REQUESTS, parse as parse_identity
from .session_probe import PACKETS, ack
from .servo_status import parse_reply
from .two_elbows import frame, position
from .motor_catalog import MOTORS, COMMAND_LIMITS, REVIEWED_LIMITS

LIMITS = COMMAND_LIMITS  # Documented command domain, not mechanical clearance limits.

def validate_id(servo):
    if type(servo) is not int or servo not in MOTORS:
        raise ValueError('Select a motor ID from 1 to 16.')

def validate_bounds(servo, low, high):
    validate_id(servo)
    if type(low) is not int or type(high) is not int or not 0 <= low < high <= 180:
        raise ValueError('Limits must be whole degrees: 0 ≤ minimum < maximum ≤ 180.')
    return (low,high)

def move_packet(servo, target, limits=None):
    validate_id(servo)
    limits = LIMITS if limits is None else limits
    if servo not in limits or type(target) is not int:
        raise ValueError('Refresh the supported joint before setting a whole-degree target.')
    low,high = validate_bounds(servo,*limits[servo])
    if not low <= target <= high:
        raise ValueError(f'Target must be between {low} and {high} degrees.')
    data=bytes([servo,1,target,100,0,100])
    return b'\xfa\xaf'+data+bytes([sum(data)&255,237])

class PanelRobot:
    def __init__(self, log_dir):
        self.log_dir=Path(log_dir)
        self.armed=threading.Event()
        self.lock=threading.Lock()
        self.limits={}  # No motor enabled until this session measures a supported pose.
        self.positions={}
        self.targets={}
        self.saved_limits={}
        self.profile_path=self.log_dir.parent/'motor-panel-limits.json'
        if self.profile_path.exists():
            try:
                data=json.loads(self.profile_path.read_text())
                for key,value in data.items():
                    sid=int(key)
                    self.saved_limits[sid]=validate_bounds(sid,*value)
            except (ValueError,TypeError,AttributeError,json.JSONDecodeError):
                self.saved_limits={}  # Invalid profiles never unlock motors.

    def disarm(self):self.armed.clear()

    def set_limits(self,servo,low,high):
        bounds=validate_bounds(servo,low,high)
        if self.armed.is_set():raise ValueError('Disarm before editing limits.')
        if not self.lock.acquire(blocking=False):raise ValueError('A robot request is active.')
        try:
            if servo not in self.positions or servo not in self.limits:
                raise ValueError('Refresh this supported motor first.')
            reference=self.targets.get(servo,self.positions[servo]['angle'])
            if not low<=reference<=high:
                raise ValueError('Limits must include the latest measured or commanded position.')
            updated=dict(self.saved_limits);updated[servo]=bounds
            self.profile_path.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.profile_path.with_suffix('.tmp')
            tmp.write_text(json.dumps(updated,indent=2));tmp.replace(self.profile_path)
            self.saved_limits=updated;self.limits[servo]=bounds
        finally:self.lock.release()

    def run_pair(self, targets, support_confirmed=False):
        """Start an approved arm pair back-to-back; settle once, never retry."""
        if type(targets) is not dict or tuple(targets) not in ((1,4),(2,5),(3,6)):
            raise ValueError('Select one arm pair: 1 & 4, 2 & 5, or 3 & 6.')
        if not support_confirmed:
            raise ValueError('Explicit physical-support confirmation is required.')
        return self.run(support_confirmed=True, _pair=targets)

    def run(self,servo=None,target=None,setup=False,support_confirmed=False,*,_pair=None):
        if servo is not None:validate_id(servo)
        if setup and (servo is None or target is not None):raise ValueError('Refresh one motor without a target.')
        if (setup or (servo is not None and servo>=7)) and not support_confirmed:
            raise ValueError('Explicit physical-support confirmation is required.')
        if servo is None and target is not None:raise ValueError('A target requires a motor.')
        payload=move_packet(servo,target,self.limits) if servo is not None and not setup else None
        moves=[(sid,angle,move_packet(sid,angle,self.limits)) for sid,angle in _pair.items()] if _pair else ([(servo,target,payload)] if payload else [])
        if (moves or setup) and not self.armed.is_set():raise ValueError('Controls are disarmed.')
        if not self.lock.acquire(blocking=False):raise ValueError('Another request is active.')
        fd=None;connected=False
        log={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'servo':servo,
             'target':target,'pair_targets':_pair,'setup':setup,'support_confirmed':support_confirmed,'exchanges':[]}
        path=self.log_dir/datetime.datetime.now().strftime('panel-%Y%m%d-%H%M%S-%f.json')
        def save():path.write_text(json.dumps(log,indent=2))
        def exchange(name,request):
            if select.select([fd],[],[],0)[0]:raise ValueError('Unexpected pending data. No retry.')
            item={'name':name,'request_hex':request.hex(),'delivery':'attempting'}
            log['exchanges'].append(item);save()
            if name in ('move','supported_setup_read') and not self.armed.is_set():
                raise ValueError('Disarmed before the command was sent.')
            count=os.write(fd,b'\0'+request.ljust(64,b'\0'));item['bytes_written']=count
            if count!=65:raise ValueError('Incomplete write; delivery uncertain. No retry.')
            if not select.select([fd],[],[],2)[0]:raise TimeoutError('No reply; delivery uncertain. No retry.')
            item['delivery']='sent'
            raw=os.read(fd,64);item['response_hex']=raw.hex();save();return raw
        try:
            self.log_dir.mkdir(parents=True,exist_ok=True);save()
            p=find_device();expected=tuple(map(int,(p/'dev').read_text().strip().split(':')))
            fd=os.open('/dev/'+p.name,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
            info=os.fstat(fd)
            if not stat.S_ISCHR(info.st_mode) or (os.major(info.st_rdev),os.minor(info.st_rdev))!=expected:
                raise ValueError('USB device identity changed.')
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if find_device()!=p:raise ValueError('USB device changed.')
            if select.select([fd],[],[],.2)[0]:raise ValueError('Unsolicited data. Stop other controllers.')
            log['hardware']=parse_identity('hardware',exchange('hardware',REQUESTS['hardware']))
            if log['hardware']!='Alpha1_V2.0':raise ValueError('Unexpected hardware version.')
            log['holding']=parse_reply(exchange('status',PACKETS['status']))
            if moves or setup:
                bits=int.from_bytes(bytes.fromhex(log['holding']['status_bytes_hex']),'little')
                if not setup and any(not bits&(1<<(sid-1)) for sid,_,_ in moves):
                    raise ValueError('Selected motor reports holding disabled. Support and refresh it before moving.')
                connected=True;ack(exchange('connect',PACKETS['connect']))
                if setup:
                    self.limits.pop(servo,None)
                    data=bytes([servo,2,0,0,0,0])
                    request=b'\xfa\xaf'+data+bytes([sum(data)&255,237])
                    log['joint_may_be_released']=True
                    baseline=position(exchange('supported_setup_read',request),servo)
                    measured_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
                    log.update(baseline_degrees=baseline,measured_at=measured_at)
                    bounds=self.saved_limits.get(servo,COMMAND_LIMITS[servo])
                    source='User-reviewed limits' if servo in self.saved_limits else 'Documented command range; clearance depends on pose'
                    if not bounds[0]<=baseline<=bounds[1]:
                        bounds=COMMAND_LIMITS[servo]
                        source='Command range restored: measured position outside saved limits'
                    payload=move_packet(servo,baseline,{servo:bounds});log['target']=baseline
                    log['range_source']=source
                if setup:moves=[(servo,baseline,payload)]
                for sid,angle,packet in moves:
                    raw=exchange('move',packet);frame(raw,sid)
                    if raw[3:5]!=bytes([1,170]):
                        raise ValueError(f'Motor {sid} did not confirm its {angle}° command (0x{raw[4]:02X}). Remaining movement stopped. Support the robot, check its charge and restart it before another attempt. No automatic retry.')
                log['move_acknowledged']=True;time.sleep(3)
                log['holding']=parse_reply(exchange('status_after_move',PACKETS['status']))
                held=int.from_bytes(bytes.fromhex(log['holding']['status_bytes_hex']),'little')
                if any(not held&(1<<(sid-1)) for sid,_,_ in moves):raise ValueError('Holding is disabled after the command. Keep supporting the joint.')
                log['joint_may_be_released']=False
                if setup:log['setup_limits']=bounds
            log['status']='ok'
        except Exception as exc:
            self.disarm();log['status']='error';log['error']=str(exc)
        finally:
            try:
                if fd is not None:
                    if connected:
                        try:ack(exchange('disconnect',PACKETS['disconnect']))
                        except Exception as exc:
                            self.disarm();log['status']='error';log['cleanup_error']=str(exc)
                    os.close(fd)
                if log.get('status')=='ok' and moves:
                    for sid,angle,_ in moves:self.targets[sid]=angle
                    if setup:
                        self.limits[servo]=bounds
                        self.positions[servo]={'angle':baseline,'at':measured_at}
                elif log.get('status')!='ok':
                    self.limits.clear();self.positions.clear();self.targets.clear()
                save()
            finally:self.lock.release()
        log['report']=str(path)
        return log
