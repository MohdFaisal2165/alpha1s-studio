"""Paired Alpha 1S RFCOMM transport. No device access on construction."""
import datetime
import fcntl
import json
import socket
import time
import threading
import uuid
from contextlib import contextmanager
from .panel_transport import PanelRobot, move_packet, validate_id

from .config import bluetooth_address
ADDRESS=bluetooth_address()
CHANNEL=6
# Reproduced on firmware 2016070416: immediate servo queries after identity
# return 0x88, whereas a one-second settling interval returns valid versions.
SERVO_SETTLE_SECONDS=1.0
SERVO_REQUEST_GAP_SECONDS=0.2
SERVO_COMMANDS=frozenset((0x22,0x24,0x2a))

def encode(command,params=b'\x00'):
    if not 1<=len(params)<=249:raise ValueError('Invalid Bluetooth payload size')
    data=bytes([len(params)+5,command])+params
    return b'\xfb\xbf'+data+bytes([sum(data)&255,237])

class Session:
    _last_closed={}
    def __init__(self,address,record,save):
        self.address=address;self.record=record;self.save=save;self.buffer=bytearray();self.sock=None
        self.servo_ready_at=0.0;self.before_servo_write=None
    def __enter__(self):
        if not self.address:raise ValueError('Configure your paired robot address in data/settings.json or ALPHA1S_BLUETOOTH_ADDRESS, then restart Studio.')
        if not hasattr(socket,'AF_BLUETOOTH'):raise RuntimeError('Start Studio with /usr/bin/python3 for Bluetooth support.')
        remaining=self._last_closed.get(self.address,0)+1.0-time.monotonic()
        if remaining>0:time.sleep(remaining)
        self.sock=socket.socket(socket.AF_BLUETOOTH,socket.SOCK_STREAM,socket.BTPROTO_RFCOMM)
        self.sock.settimeout(6)
        try:
            self.sock.connect((self.address,CHANNEL))
            name=self.exchange(1).decode('ascii').strip('\x00')
            firmware=self.exchange(0x11).decode('ascii').strip('\x00')
            hardware=self.exchange(0x20).decode('ascii').strip('\x00')
            self.record.update(name=name,hardware=hardware,firmware=firmware);self.save()
            if 'ALPHA' not in name.upper() or firmware!='2016070416' or hardware!='Alpha1_V2.0':
                raise ValueError('Robot identity differs from the verified Alpha 1S.')
            self.servo_ready_at=time.monotonic()+SERVO_SETTLE_SECONDS
            self.record['servo_settle_seconds']=SERVO_SETTLE_SECONDS;self.save()
            return self
        except Exception:self.close();raise
    def close(self):
        try:
            if self.sock is not None:self.sock.close();self.sock=None
        finally:self._last_closed[self.address]=time.monotonic()
    def __exit__(self,*args):self.close()
    def exchange(self,command,params=b'\x00'):
        if command in SERVO_COMMANDS:
            remaining=self.servo_ready_at-time.monotonic()
            if remaining>0:time.sleep(remaining)
        if command in (0x22,0x24) and self.before_servo_write is not None:
            self.before_servo_write()  # Stop may have been clicked during the wait.
        item={'command':command,'request':encode(command,params).hex(),'delivery':'attempting'}
        self.record['exchanges'].append(item);self.save()
        self.sock.sendall(bytes.fromhex(item['request']))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            while len(self.buffer)>=3:
                if self.buffer[:2]!=b'\xfb\xbf':raise ValueError('Unexpected Bluetooth data. No retry.')
                size=self.buffer[2]+1
                if not 7<=size<=255:raise ValueError('Invalid Bluetooth frame size')
                if len(self.buffer)<size:break
                raw=bytes(self.buffer[:size]);del self.buffer[:size]
                item.setdefault('responses',[]).append(raw.hex());self.save()
                if raw[-1]!=237 or raw[-2]!=sum(raw[2:-2])&255:raise ValueError('Invalid Bluetooth checksum')
                if raw[3]==command:
                    if command in SERVO_COMMANDS:
                        self.servo_ready_at=time.monotonic()+SERVO_REQUEST_GAP_SECONDS
                    item['delivery']='replied';self.save();return raw[4:-2]
                if raw[3] not in (0x0a,0x19,0x31,0x32):raise ValueError('Unexpected Bluetooth reply')
            self.sock.settimeout(max(.1,deadline-time.monotonic()))
            chunk=self.sock.recv(256)
            if not chunk:raise ConnectionError('Bluetooth disconnected. No retry.')
            self.buffer.extend(chunk)
        raise TimeoutError('Bluetooth reply missing. No automatic retry.')

class BluetoothRobot(PanelRobot):
    supports_robot_speech=True
    def __init__(self,log_dir,address=ADDRESS):
        super().__init__(log_dir);self.address=address
        self.recovery_path=self.log_dir/'bluetooth-recovery-required.json'
        self._sequence=None;self._sequence_owner=None
        self._persistent_mode=False;self._connection=None;self._connection_lock=None;self._connection_id=None
    @property
    def connected(self):return self._connection is not None
    def connect(self):
        """Explicit manual connection; later operations reuse it without reconnecting."""
        self._persistent_mode=True
        return self.run()
    def _close_connection(self):
        connection,self._connection=self._connection,None
        lock,self._connection_lock=self._connection_lock,None
        self._connection_id=None
        try:
            if connection is not None:connection.__exit__(None,None,None)
        finally:
            if lock is not None:lock.close()
    def disconnect(self):
        """Close only while idle. Disarm alone intentionally keeps Bluetooth open."""
        if not self.lock.acquire(blocking=False):raise ValueError('Wait for the current request before disconnecting.')
        try:
            self.disarm()
            try:self._close_connection()
            finally:self.positions.clear();self.targets.clear();self.limits.clear()
        finally:self.lock.release()
    @contextmanager
    def connection_for(self,kind,record,save):
        if self.recovery_path.exists():raise ValueError('Previous playback-mode restoration is uncertain. Power-cycle the robot and inspect the recovery report before continuing.')
        if not self._persistent_mode:
            with (self.log_dir/'bluetooth.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with Session(self.address,record,save) as session:yield session
            return
        if self._connection is None:
            if kind!='connect':raise ValueError('Bluetooth is disconnected. Click Connect; no automatic reconnect or movement retry.')
            lock=(self.log_dir/'bluetooth.lock').open('a')
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                session=Session(self.address,record,save).__enter__()
            except Exception:lock.close();raise
            self._connection=session;self._connection_lock=lock;self._connection_id=uuid.uuid4().hex
            record['connection_reused']=False
        else:
            record['connection_reused']=True
            self._connection.record=record;self._connection.save=save
        record['connection_id']=self._connection_id;save()
        try:yield self._connection
        except Exception:
            self._close_connection();raise
    def require_armed(self):
        if not self.armed.is_set():raise ValueError('Stopped. No further movement sent.')
    @contextmanager
    def sequence(self):
        """Keep one checked RFCOMM session for a whole gesture and speech."""
        if self._sequence is not None:raise ValueError('Another sequence is active.')
        with self.operation('greeting_sequence') as connection:
            self._sequence=connection;self._sequence_owner=threading.get_ident()
            try:yield
            finally:self._sequence=None;self._sequence_owner=None

    @contextmanager
    def operation(self,kind):
        if self._sequence is not None and self._sequence_owner==threading.get_ident():
            session,record,save=self._sequence
            step={'kind':kind,'first_exchange':len(record['exchanges'])}
            record.setdefault('steps',[]).append(step);save()
            try:
                yield session,record,save
                step['status']='ok'
            except Exception as exc:
                step.update(status='error',error=str(exc));self.disarm()
                self.positions.clear();self.targets.clear();self.limits.clear();raise
            finally:
                step['end_exchange']=len(record['exchanges']);save()
            return
        if not self.lock.acquire(blocking=False):raise ValueError('Another robot request is active.')
        record={'kind':kind,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'status':'attempting','exchanges':[]}
        try:
            self.log_dir.mkdir(parents=True,exist_ok=True)
            path=self.log_dir/('bluetooth-'+uuid.uuid4().hex+'.json')
            def save():path.write_text(json.dumps(record,indent=2)+'\n')
            save()
            try:
                with self.connection_for(kind,record,save) as session:
                    session.before_servo_write=self.require_armed
                    yield session,record,save
                record['status']='ok'
            except Exception as exc:
                record.update(status='error',error=str(exc));self.disarm()
                self._close_connection()
                self.positions.clear();self.targets.clear();self.limits.clear();raise
            finally:save()
        finally:self.lock.release()
    def run(self,servo=None,target=None,setup=False,support_confirmed=False,*,_pair=None):
        if servo is not None:validate_id(servo)
        if setup and (servo is None or target is not None):raise ValueError('Read one joint without a target.')
        if servo is None and target is not None:raise ValueError('Target requires a joint.')
        moves=dict(_pair or ({servo:target} if target is not None else {}))
        if (moves or setup) and not support_confirmed:raise ValueError('Physical support confirmation required.')
        for sid,angle in moves.items():move_packet(sid,angle,self.limits)
        if moves or setup:self.require_armed()
        result={'servo':servo,'target':target,'setup':setup,'holding':None}
        try:
            with self.operation('read_angle' if setup else 'move' if moves else 'connect') as (session,record,save):
                # Probe responsiveness before any movement or joint release.
                for sid in ([servo] if setup else moves):
                    self.require_armed()
                    version=session.exchange(0x2a,bytes([sid]))
                    if len(version)!=5 or version[0]!=sid or version[1]==0x88:
                        raise ValueError(f'Motor {sid} did not pass the response check. No movement or joint release sent in this operation.')
                    record.setdefault('verified_servo_versions',{})[str(sid)]=version[1:].hex();save()
                if setup:
                    self.require_armed();self.limits.pop(servo,None)
                    reply=session.exchange(0x24,bytes([servo]))
                    if len(reply)!=2 or reply[0]!=servo or reply[1]>180:raise ValueError('Angle read failed; support the released joint.')
                    baseline=reply[1];moves={servo:baseline}
                    bounds=self.saved_limits.get(servo,(0,180))
                    if not bounds[0]<=baseline<=bounds[1]:bounds=(0,180)
                    result.update(baseline_degrees=baseline,measured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),setup_limits=bounds,range_source='Supported Bluetooth reading',target=baseline)
                for sid,angle in moves.items():
                    self.require_armed()
                    reply=session.exchange(0x22,bytes([sid,angle,100,0,100]))
                    if reply!=bytes([sid,0]):
                        if reply==bytes([sid,3]):
                            result.update(movement_unconfirmed=True,attempted_servo=sid,attempted_target=angle)
                            record.update(result);save()
                            raise ValueError(f'Motor {sid}: no reply from servo (code 0x03). It may have moved to {angle}°. Position is unconfirmed; remaining movement and speech were not sent. No retry.')
                        reasons={1:'invalid servo ID',2:'angle outside allowed range',3:'no reply from servo'}
                        reason=reasons.get(reply[1],'unknown status') if len(reply)==2 and reply[0]==sid else 'unexpected response'
                        raise ValueError(f'Motor {sid}: {reason} ({reply.hex()}). Remaining movement and greeting speech were not sent. No retry.')
                if moves:
                    time.sleep(3);result['move_acknowledged']=True
                    self.targets.update(moves)
                if setup:
                    self.limits[servo]=bounds;self.positions[servo]={'angle':baseline,'at':result['measured_at']}
                record.update(result);save()
            result['status']='ok'
        except Exception as exc:result.update(status='error',error=str(exc))
        return result
    def prepare_robot_audio(self,name):
        import re
        from .greetings import saved_audio
        from .robot_speech import ROOT
        from .hold_speech import prepare
        if not re.fullmatch(r'S[0-9A-F]{7}|FAISAL01',name) or name not in saved_audio():raise ValueError('Recording is not verified.')
        inventory=json.loads((ROOT/'reports/card-file-inventory.json').read_text())
        if any(x['path'].casefold()=='action/'+name.lower()+'.hts' for x in inventory):raise ValueError('Recording has a matching action file; playback blocked.')
        _,_,seconds=prepare(name,require_player=False)
        return name,seconds
    def play_robot_audio(self,prepared):
        name,seconds=prepared;self.require_armed()
        with self.operation('robot_speech') as (session,record,save):
            attempted=False
            try:
                self.require_armed();attempted=True
                # Durable marker survives process termination before restoration.
                self.recovery_path.write_text(json.dumps({'reason':'Playback mode may be enabled','audio':name}))
                if session.exchange(0x21,b'\x01')!=b'\x00':raise ValueError('Skip-reset mode was not accepted.')
                self.require_armed()
                reply=session.exchange(3,('MUSIC/'+name+'.MP3').encode('ascii'))
                if reply!=b'\x00':raise ValueError('Robot rejected recording '+name+' (reply '+reply.hex()+'). Upload verification does not confirm firmware playback compatibility. No retry.')
                record['playback']='accepted';save()
                # Keep reset suppressed through playback, even if locally disarmed.
                time.sleep(seconds+3)
            finally:
                if attempted:
                    try:
                        if session.exchange(0x21,b'\x00')!=b'\x00':raise ValueError('Mode restoration rejected')
                        record['restoration']='acknowledged';self.recovery_path.unlink()
                    except Exception as exc:
                        raise RuntimeError('Playback mode restoration uncertain. Power-cycle the robot before further use.') from exc
        return {'status':'robot_audio_accepted','pose_reset_sent':False}
