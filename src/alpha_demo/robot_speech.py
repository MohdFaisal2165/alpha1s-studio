"""Explicit speech workflow. No hardware access on import or startup."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import time
import uuid
from .identify import find_device, REQUESTS, parse
from .protocol import parse_play_reply

ROOT=Path(__file__).resolve().parents[1]


def save_job(job):
    path=Path(job['directory'])/'job.json';tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(job,indent=2)+'\n');tmp.replace(path)


def new_job(clip,text):
    for journal in list((ROOT/'data'/'robot-speech').glob('*/card-journal.json'))+list((ROOT/'data'/'robot-speech').glob('*/cleanup-journal.json')):
        previous=json.loads((journal.parent/'job.json').read_text())
        if journal.name=='cleanup-journal.json' and previous.get('cleanup_complete'):continue
        if previous.get('status') not in ('uploaded','playback_attempting','playback_accepted','playback_uncertain'):
            raise ValueError('An earlier card write needs inspection before another upload. Keep the card unchanged.')
    folder=ROOT/'data'/'robot-speech'/uuid.uuid4().hex
    folder.mkdir(parents=True)
    audio=Path(clip['mp3']).read_bytes()
    (folder/'speech.mp3').write_bytes(audio)
    job={'directory':str(folder),'name':'S'+uuid.uuid4().hex[:7].upper(),
         'text':text,'sha256':hashlib.sha256(audio).hexdigest(),
         'status':'prepared','playback_attempted':False,'voice':clip.get('voice','Local'),'style':clip.get('style','neutral')}
    save_job(job);return job


def packet(name):
    if not re.fullmatch(r'S[0-9A-F]{7}',name): raise ValueError('Invalid generated audio name')
    data=bytes([len(name)+1])+name.encode('ascii')
    return b'\xf3\x3f'+data+bytes([sum(data)&255,237])


def hid_command(command, cancelled=None):
    device=find_device();expected=tuple(map(int,(device/'dev').read_text().split(':')))
    fd=os.open('/dev/'+device.name,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
    exchanges=[]
    try:
        info=os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or (os.major(info.st_rdev),os.minor(info.st_rdev))!=expected:
            raise ValueError('Device identity changed')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('USB connection is held by another controller. Close older Studio windows and disconnect their controls before uploading. No storage command sent.') from None
        if find_device()!=device: raise ValueError('Device changed')
        def exchange(data):
            if cancelled is not None and cancelled(): raise ValueError("Stopped before the next device command.")
            if select.select([fd],[],[],.1)[0]: raise ValueError('Robot is busy; stop other controllers')
            if cancelled is not None and cancelled(): raise ValueError('Stopped before the next device command.')
            entry={'request':data.hex(),'delivery':'attempting'};exchanges.append(entry)
            if os.write(fd,b'\0'+data.ljust(64,b'\0'))!=65: raise IOError('Short send; do not retry')
            entry['delivery']='sent'
            if not select.select([fd],[],[],2)[0]: raise TimeoutError('Robot reply missing; no automatic retry')

            try:reply=os.read(fd,64)
            except BlockingIOError:raise ValueError('USB reply became unavailable after sending a command. No retry: reconnect USB and check the robot before a new upload.') from None
            entry['reply']=reply.hex();return reply
        if parse('hardware',exchange(REQUESTS['hardware']))!='Alpha1_V2.0': raise ValueError('Unexpected hardware')
        if parse('firmware',exchange(REQUESTS['firmware']))!='2016070416': raise ValueError('Firmware changed; review required')
        reply=exchange(command)
        return reply,exchanges
    finally: os.close(fd)


def storage_devices():
    from .card_check import identify
    matches=[]
    for p in Path('/sys/class/block').iterdir():
        try:
            if (p/'partition').exists(): continue
            identify('/dev/'+p.name);matches.append('/dev/'+p.name)
        except (OSError,ValueError): pass
    return matches


def upload_prerequisites():
    path=ROOT/'reports/card-backup-verification.json'
    if not path.is_file():raise ValueError('Verified robot-card backup is missing. See docs/SETUP.md; no storage-mode command sent.')
    verified=json.loads(path.read_text())
    if verified.get('status')!='complete' or not verified.get('full_source_comparison'):
        raise ValueError('Complete source-verified robot-card backup required before upload.')
    image=verified.get('image') or verified.get('image_path')
    if not image or not Path(image).is_file():raise ValueError('Verified card backup image is unavailable.')


def prepare_upload(job,progress):
    """Called only by Send. Upload helper never plays audio."""
    try:
        upload_prerequisites()
        devices=storage_devices()
        if not devices:
            progress('Preparing the robot for upload…')
            reply,exchanges=hid_command(bytes.fromhex('f99f01000000000001ed'))
            job['storage_exchanges']=exchanges;save_job(job)
            if reply[:4]!=bytes.fromhex('f99faaed') or any(reply[4:]):
                raise ValueError('Storage mode was not acknowledged; no retry')
            for _ in range(40):
                devices=storage_devices()
                if devices: break
                time.sleep(.25)
        if len(devices)!=1: raise ValueError('Connect exactly one Alpha 1S robot')
        device=devices[0]
        # Linux may automount after enumeration. Unmount only this robot's volumes.
        time.sleep(1)
        progress('Preparing the memory card…')
        block=Path('/sys/class/block')/Path(device).name
        nodes=[device]+['/dev/'+p.name for p in block.resolve().iterdir() if (p/'partition').exists()]
        for node in nodes:
            mounted=subprocess.run(['findmnt','-rn','-S',node],capture_output=True,text=True)
            if mounted.returncode==0:
                result=subprocess.run(['udisksctl','unmount','-b',node,'--no-user-interaction'],capture_output=True,text=True,timeout=20)
                if result.returncode: raise RuntimeError('Close the robot drive in Files, then try Send again. '+result.stderr.strip())
        from .upload_session import upload
        last=upload(job,device,progress)
        job.update(status='uploaded',upload=last);save_job(job)
        return job
    except Exception as exc:
        job.update(status='upload_failed',error=str(exc));save_job(job);raise


def play_job(job, cancelled=None):
    # Never send a second command after uncertain delivery, even after app restart.
    stored=json.loads((Path(job['directory'])/'job.json').read_text())
    if stored.get('status')!='uploaded' or stored.get('playback_attempted'):
        raise ValueError('This upload is not ready for a new playback request')
    if hashlib.sha256((Path(job['directory'])/'speech.mp3').read_bytes()).hexdigest()!=stored['sha256']:
        raise ValueError('Audio changed since upload')
    if stored.get('upload',{}).get('sha256')!=stored['sha256']:
        raise ValueError('Upload verification is missing')
    # Device discovery is read-only; remain retryable if cable has not been reconnected.
    find_device()
    if cancelled is not None and cancelled(): raise ValueError('Stopped before playback.')
    job.update(playback_attempted=True,status='playback_attempting');save_job(job)
    try:
        reply,exchanges=(hid_command(packet(job['name'])) if cancelled is None else hid_command(packet(job['name']),cancelled=cancelled))
        job.update(exchanges=exchanges,raw_playback_reply=reply.hex());save_job(job)
        result=parse_play_reply(reply)
        job.update(status='playback_accepted',exchanges=exchanges,result=result)
    except Exception as exc:
        job.update(status='playback_uncertain',error=str(exc));save_job(job);raise
    save_job(job);return job
