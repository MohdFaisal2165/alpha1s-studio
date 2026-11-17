"""One approved LOWBAT named-playback probe. May cause default-pose movement.

This probes an existing MP3 without uploading or changing files. Success means
only command acceptance; hearing audio and observing movement require a person.
"""
import argparse
import datetime
import fcntl
import json
import hashlib
import os
from pathlib import Path
import select
import stat
from .identify import find_device, REQUESTS, parse

NAME = b'LOWBAT'
DATA = bytes([len(NAME)+1])+NAME
REQUEST = b'\xf3\x3f'+DATA+bytes([sum(DATA)&255,0xed])


def parse_play_reply(raw):
    # Accept the documented status+terminator form, with optional status checksum.
    if raw[:4] == bytes.fromhex('f33faaed') and not any(raw[4:]):
        return 'accepted; audio and movement not verified'
    if raw[:5] == bytes.fromhex('f33faaaaed') and not any(raw[5:]):
        return 'accepted; audio and movement not verified'
    raise ValueError('Playback reply not confirmed; preserve raw report, do not retry')


def request_for(name):
    if name not in ('LOWBAT','FAISAL01'):
        raise ValueError('Audio name is not allowlisted')
    value=name.encode('ascii');data=bytes([len(value)+1])+value
    return b'\xf3\x3f'+data+bytes([sum(data)&255,0xed])


def preflight(root, name='LOWBAT'):
    verification=json.loads((root/'reports/card-backup-verification.json').read_text())
    if verification.get('status')!='complete' or not verification.get('full_source_comparison'):
        raise ValueError('A full verified backup is required')
    inventory=json.loads((root/'reports/card-file-inventory.json').read_text())
    paths={item['path'].casefold() for item in inventory}
    request_for(name)
    if 'action/'+name.casefold()+'.hts' in paths:
        raise ValueError('Matching motion action exists; refusing speech probe')
    if name=='LOWBAT':
        if 'music/lowbat.mp3' not in paths:
            raise ValueError('Expected unpaired LOWBAT audio not confirmed in card inventory')
    else:
        uploaded=json.loads((root/'reports/faisal-upload-result.json').read_text())
        clip=json.loads((root/'reports/faisal-greeting.json').read_text())
        expected=hashlib.sha256(Path(clip['mp3']).read_bytes()).hexdigest()
        if (uploaded.get('status')!='complete' or not uploaded.get('readback_verified')
                or uploaded.get('file')!='MUSIC/FAISAL01.MP3'
                or uploaded.get('new_file_sha256')!=expected):
            raise ValueError('Greeting upload has not been verified')


def run(root, log, name='LOWBAT'):
    preflight(root,name)
    device=find_device();expected=tuple(map(int,(device/'dev').read_text().strip().split(':')))
    fd=os.open('/dev/'+device.name,os.O_RDWR|os.O_NONBLOCK|os.O_NOFOLLOW)
    try:
        info=os.fstat(fd)
        if not stat.S_ISCHR(info.st_mode) or (os.major(info.st_rdev),os.minor(info.st_rdev))!=expected:
            raise ValueError('Device identity mismatch')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if find_device()!=device:raise ValueError('Device changed')
        if select.select([fd],[],[],.2)[0]:raise ValueError('Pending device data; no command sent')
        def exchange(kind,packet):
            entry={'kind':kind,'request_hex':packet.hex(),'delivery':'attempting'}
            log['exchanges'].append(entry)
            if os.write(fd,b'\0'+packet.ljust(64,b'\0'))!=65:raise ValueError('Short write; no retry')
            entry['delivery']='sent'
            if not select.select([fd],[],[],2)[0]:raise TimeoutError('No reply; no retry')
            raw=os.read(fd,64);entry['response_hex']=raw.hex();return raw
        if parse('hardware',exchange('hardware',REQUESTS['hardware']))!='Alpha1_V2.0':
            raise ValueError('Unexpected robot hardware')
        firmware=parse('firmware',exchange('firmware',REQUESTS['firmware']))
        log['firmware']=firmware
        if firmware!='2016070416':raise ValueError('Firmware changed; re-review before playback')
        log['result']=parse_play_reply(exchange(name+'_play_once',request_for(name)))
        log['status']='command_accepted'
    finally:
        os.close(fd)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approved-speaker-test',action='store_true',required=True)
    parser.add_argument('--allow-possible-pose-movement',action='store_true',required=True)
    parser.add_argument('--robot-supported',action='store_true',required=True)
    parser.add_argument('--greeting',choices=('LOWBAT','FAISAL01'),default='LOWBAT')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    log={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'exchanges':[],'status':'not_sent','audio_heard':None,'motion_observed':None,
         'scope':'One allowlisted audio playback request; possible default-pose movement; no file writes','greeting':args.greeting}
    try:run(root,log,args.greeting)
    except Exception as exc:log.update(status='unverified',error=str(exc))
    report='speaker-probe.json' if args.greeting=='LOWBAT' else 'faisal-playback.json'
    (root/'reports'/report).write_text(json.dumps(log,indent=2)+'\n')
    print(json.dumps(log,indent=2))
    return 0 if log['status']=='command_accepted' else 1

if __name__=='__main__':raise SystemExit(main())
