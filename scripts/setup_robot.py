#!/usr/bin/env python3
"""Explicit first-run setup. Backup is read-only; default capture actively reads/restores supported joints."""
import argparse
import datetime
import fcntl
import hashlib
import json
import mmap
import os
from pathlib import Path
import pwd
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def backup(device):
    from alpha_demo.card_check import identify
    from alpha_demo.card_import import files_from_image,inventory
    if os.geteuid()!=0:raise ValueError('Use the documented pkexec command for read-only card access.')
    uid=int(os.environ.get('PKEXEC_UID','0'))
    if uid<=0:raise ValueError('Launch with pkexec from your regular desktop account.')
    gid=pwd.getpwuid(uid).pw_gid
    if ROOT.stat().st_uid!=uid:raise ValueError('The source folder must belong to your desktop user.')
    for name in ('backups','reports','work'):
        p=ROOT/name
        if p.is_symlink():raise ValueError('Setup directories must not be symlinks')
        p.mkdir(exist_ok=True);os.chown(p,uid,gid)
    report=ROOT/'reports/card-backup-verification.json'
    target=ROOT/'work/card-extracted';inv=ROOT/'reports/card-file-inventory.json'
    if any(p.exists() or p.is_symlink() for p in (report,target,inv)):raise ValueError('Card setup already exists. Keep it; do not overwrite an existing installation.')
    sectors,identity=identify(device)
    if sectors*512!=130023424:raise ValueError('Only the tested 124 MiB card layout is supported in this release.')
    block=Path(identity);number=(block/'dev').read_text().strip()
    numbers={number}|{(p/'dev').read_text().strip() for p in block.iterdir() if (p/'partition').exists()}
    if numbers & {line.split()[2] for line in Path('/proc/self/mountinfo').read_text().splitlines()}:raise ValueError('Unmount the robot card in Files first; do not eject or unplug it.')
    fd=os.open(device,os.O_RDONLY|os.O_DIRECT|os.O_NOFOLLOW|os.O_EXCL)
    info=os.fstat(fd)
    if f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'!=number:raise ValueError('Device changed')
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    image=ROOT/'backups'/('robot-card-'+stamp+'.img')
    try:
        with mmap.mmap(-1,512) as buf:
            for pass_number in (1,2):
                digest=hashlib.sha256()
                with (image.open('xb') if pass_number==1 else image.open('rb')) as copy:
                    if pass_number==1:os.chown(image,uid,gid)
                    for sector in range(sectors):
                        if os.preadv(fd,[buf],sector*512)!=512:raise IOError('Short card read')
                        digest.update(buf)
                        if pass_number==1:copy.write(buf)
                        elif copy.read(512)!=buf[:]:raise ValueError('Card changed during verification; backup not approved')
                        if (sector+1)%16384==0:print(f'Pass {pass_number}/2: {(sector+1)//2048}/124 MiB',flush=True)
                    if pass_number==1:copy.flush();os.fsync(copy.fileno())
            if identify(device)!=(sectors,identity):raise ValueError('Device changed')
        raw=image.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest.hexdigest():raise ValueError('Backup hash mismatch')
        files=files_from_image(raw)
        staging=Path(tempfile.mkdtemp(prefix='card-import-',dir=ROOT/'work'))
        for name,payload in files.items():
            path=staging/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
        for path in [staging,*staging.rglob('*')]:os.chown(path,uid,gid)
        staging.rename(target)
        with inv.open('x') as out:out.write(json.dumps(inventory(files),indent=2)+'\n')
        os.chown(inv,uid,gid)
        with report.open('x') as out:out.write(json.dumps({'status':'complete','full_source_comparison':True,'source_read_only':True,'image':str(image),'sha256':digest.hexdigest(),'bytes':len(raw)},indent=2)+'\n')
        os.chown(report,uid,gid)
        print('Backup verified twice and local action inventory imported. No card writes or motor commands sent.')
    finally:os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--bluetooth-address',metavar='ADDRESS')
    group.add_argument('--enter-storage',action='store_true',help='Send the identity-checked USB storage-mode request; no motor commands')
    group.add_argument('--backup-card',metavar='/dev/sdX',help='Read-only full backup and second-pass verification')
    group.add_argument('--capture-default',action='store_true',help='Read all 16 supported joints and save this robot default')
    parser.add_argument('--supported-legs-unloaded',action='store_true',help='Confirm torso secured, legs unloaded, joints clear and switch reachable')
    args=parser.parse_args()
    if args.bluetooth_address:
        from alpha_demo.config import bluetooth_address
        os.environ['ALPHA1S_BLUETOOTH_ADDRESS']=args.bluetooth_address
        value=bluetooth_address();path=ROOT/'data/settings.json';path.parent.mkdir(exist_ok=True)
        data=json.loads(path.read_text()) if path.exists() else {};data['bluetooth_address']=value
        path.write_text(json.dumps(data,indent=2)+'\n');print('Bluetooth address saved locally.')
    elif args.enter_storage:
        from alpha_demo.robot_speech import hid_command
        reply,_=hid_command(bytes.fromhex('f99f01000000000001ed'))
        if reply[:4]!=bytes.fromhex('f99faaed') or any(reply[4:]):raise ValueError('Storage mode not acknowledged; no retry')
        print('Storage mode accepted. Identify the new robot disk with lsblk; unmount its partition before backup.')
    elif args.capture_default:
        if not args.supported_legs_unloaded:raise ValueError('Default capture briefly releases each joint. Secure the torso, unload both legs, clear joints, keep the power switch reachable, then supply --supported-legs-unloaded.')
        from alpha_demo.conversation_speech import alpha_usb_present
        from alpha_demo.bluetooth_transport import BluetoothRobot
        from alpha_demo.default_pose import capture
        if alpha_usb_present():raise ValueError('Unplug USB before Bluetooth default capture.')
        robot=BluetoothRobot(ROOT/'reports/panel');robot.armed.set()
        try:capture(robot,supported=True,legs_unloaded=True,progress=lambda text:print(text,flush=True))
        finally:robot.disarm()
        print('Measured default saved locally.')
    else:backup(args.backup_card)

if __name__=='__main__':
    try:main()
    except Exception as exc:raise SystemExit(str(exc))
