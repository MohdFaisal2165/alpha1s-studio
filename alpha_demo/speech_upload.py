"""Privileged, bounded MP3 and optional authorized HTS upload helper; invoked only after Send + OS authorization."""
import base64
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import stat
import subprocess
import sys
from contextlib import contextmanager

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from alpha_demo.audio_card import stage_audio
from alpha_demo.card_check import identify
from alpha_demo.sector_patch import apply_patch_blocks


def emit(**data): print(json.dumps(data),flush=True)


def unmount_verified_card(device, sectors, identity):
    """Unmount only this identity-checked robot, after the authorization dialog."""
    block=Path(identity)
    nodes=[(device,(block/'dev').read_text().strip())]
    nodes += [('/dev/'+p.name,(p/'dev').read_text().strip()) for p in block.iterdir() if (p/'partition').exists()]
    def mounted_numbers():
        return {line.split()[2] for line in Path('/proc/self/mountinfo').read_text().splitlines()}
    for node,number in reversed(nodes):
        if identify(device)!=(sectors,identity):raise ValueError('Robot disk identity changed before unmount.')
        if number in mounted_numbers():
            emit(status='unmounting',message='Closing the robot card before upload…')
            result=subprocess.run(['/usr/bin/umount','--',node],capture_output=True,text=True,timeout=20)
            if result.returncode:raise ValueError('Robot card is busy. Close its files and try again; no write started.')
    if {number for _,number in nodes}&mounted_numbers():
        raise ValueError('Robot card was mounted again; no write started.')


@contextmanager
def admin_device_access():
    uid=os.geteuid()
    if uid!=0 and os.getuid()==0:os.seteuid(0)
    try:yield
    finally:
        if os.geteuid()!=uid:os.seteuid(uid)


def upload(job_path,device):
    if os.geteuid()==0 and int(os.environ.get('PKEXEC_UID','0'))>0:os.seteuid(int(os.environ['PKEXEC_UID']))
    folder=Path(job_path).resolve().parent
    if folder.parent!=ROOT/'data'/'robot-speech': raise ValueError('Invalid speech job folder')
    job=json.loads((folder/'job.json').read_text())
    if job.get('status')!='prepared' or job.get('playback_attempted'): raise ValueError('Upload already attempted; create a new job')
    cleanup_only=job.get('kind')=='delete_recordings'
    if cleanup_only and (not isinstance(job.get('delete_names'),list) or not job['delete_names']):raise ValueError('No recordings selected')
    action=None
    if job.get('action'):
        from alpha_demo.paired_speech import validate_action
        if Path(job['directory']).resolve()!=folder:raise ValueError('Job directory changed')
        action,_=validate_action(job)
    audio=b'' if cleanup_only else (folder/'speech.mp3').read_bytes()
    if not cleanup_only and hashlib.sha256(audio).hexdigest()!=job['sha256']: raise ValueError('Audio checksum changed')
    verified=json.loads((ROOT/'reports/card-backup-verification.json').read_text())
    if verified.get('status')!='complete' or not verified.get('full_source_comparison'):
        raise ValueError('Verified card backup required')
    template=Path(verified['image']).read_bytes() if 'image' in verified else Path(verified['image_path']).read_bytes()
    if hashlib.sha256(template).hexdigest()!=verified['sha256']: raise ValueError('Backup checksum mismatch')
    sectors,identity=identify(device)
    if sectors*512!=len(template): raise ValueError('Unexpected card size')
    block=Path(identity);expected=(block/'dev').read_text().strip()
    with admin_device_access():
        unmount_verified_card(device,sectors,identity)
        fd=os.open(device,os.O_RDWR|os.O_DIRECT|os.O_NOFOLLOW|os.O_EXCL)
    try:
        info=os.fstat(fd)
        if not stat.S_ISBLK(info.st_mode) or f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'!=expected:
            raise ValueError('Device changed')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Robot memory card is locked by another process. Close other Studio windows or card tools. No card writes started.') from None
        if identify(device)!=(sectors,identity): raise ValueError('Device changed')
        with mmap.mmap(-1,512) as buffer:
            def read(s):
                if os.preadv(fd,[buffer],s*512)!=512: raise IOError('Short card read')
                return buffer[:]
            def write(s,b):
                buffer[:]=b;return os.pwritev(fd,[buffer],s*512)
            from alpha_demo.recording_store import cleanup_candidates
            from alpha_demo.card_cleanup import stage_cleanup
            cleanup=cleanup_candidates(ROOT)
            if cleanup_only:
                cleanup=[item for item in cleanup if item['name'] in job['delete_names']]
                if {item['name'] for item in cleanup}!=set(job['delete_names']):raise ValueError('Selected recordings changed or are protected; nothing deleted.')
            if cleanup:
                targets=[tuple(file) for item in cleanup for file in item['files']]
                cb,ca,co,cm=stage_cleanup(template,read,targets)
                journal={'names':[i['name'] for i in cleanup],'order':co,
                         'originals':{str(s):base64.b64encode(cb[s*512:(s+1)*512]).decode() for s in co}}
                with (folder/'cleanup-journal.json').open('x') as out:
                    json.dump(journal,out);out.flush();os.fsync(out.fileno())
                apply_patch_blocks(cb,ca,co,cm,read,write,lambda:os.fsync(fd),lambda *a:None)
                emit(status='cleanup_complete',names=journal['names'],message='Temporary recordings reclaimed and verified.')
            if cleanup_only:
                emit(status='complete',message='Selected recordings deleted from robot and verified.',deleted_names=job['delete_names'])
                return
            emit(status='checking',message='Checking card and available space…')
            before,after,order,metadata=stage_audio(template,read,audio,job['name'],action=action,firmware_compatible=True)
            # Save exact changed-sector originals for diagnosis/recovery before any write.
            journal={'name':job['name'],'sha256':job['sha256'],'order':order,
                     'originals':{str(s):base64.b64encode(before[s*512:(s+1)*512]).decode() for s in order}}
            path=folder/'card-journal.json'
            with path.open('x') as out:
                json.dump(journal,out);out.flush();os.fsync(out.fileno())
            uid=int(os.environ.get('PKEXEC_UID',os.getuid()))
            if os.geteuid()==0:os.chown(path,uid,folder.stat().st_gid,follow_symlinks=False)
            done=0
            def progress(phase,sector):
                nonlocal done
                if phase=='verified':
                    done+=1;emit(status='uploading',message=f'Uploading and verifying… {done}/{len(order)}')
            apply_patch_blocks(before,after,order,metadata,read,write,lambda:os.fsync(fd),progress)
            emit(status='complete',message='Upload verified. Unplug USB for Bluetooth playback.',sha256=job['sha256'],name=job['name'],sectors=len(order),action_sha256=hashlib.sha256(action).hexdigest() if action is not None else None,firmware_compatible_directories=True)
    finally: os.close(fd)


if __name__=='__main__':
    try:
        if len(sys.argv)!=3: raise ValueError('Expected speech job and robot disk')
        upload(sys.argv[1],sys.argv[2])
    except Exception as exc:
        emit(status='error',error=str(exc),message='Upload stopped: '+str(exc));sys.exit(1)
