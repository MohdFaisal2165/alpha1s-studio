"""One native action and fresh speech under a shared, unique card basename.

No motion synthesis: HTS bytes are copied unchanged from an authorized card file.
Firmware overlap/duration behaviour still requires an observed hardware test.
"""
import math
import hashlib
import json
import time
from pathlib import Path
from . import action_library,robot_speech


def validate_action(job,root=None):
    root=root or robot_speech.ROOT
    item=action_library.inspect(job['action']['key'],root)
    if action_library.approval_hash(action_library.approvals(root).get(item['key']))!=item['sha256']:
        raise ValueError('Selected action is no longer authorized.')
    raw=(Path(job['directory'])/'action.hts').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=item['sha256'] or job['action']['sha256']!=item['sha256']:
        raise ValueError('Paired action differs from the authorized library file.')
    return raw,item


def attach(job,key,root=None):
    root=root or robot_speech.ROOT
    item=action_library.inspect(key,root)
    if action_library.approval_hash(action_library.approvals(root).get(key))!=item['sha256']:
        raise ValueError('Authorize this exact library action first.')
    raw=(root/'work/card-extracted'/item['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Action changed while preparing.')
    (Path(job['directory'])/'action.hts').write_bytes(raw)
    job['action']={'key':key,'sha256':item['sha256'],'seconds':item['seconds']}
    robot_speech.save_job(job)
    return job


def play(robot,job,audio_seconds,*,replay=False):
    stored=json.loads((Path(job['directory'])/'job.json').read_text())
    if (stored.get('status')!='playback_accepted' if replay else
        stored.get('status')!='uploaded' or stored.get('playback_attempted')):
        raise ValueError('Combined playback already attempted; no automatic retry.')
    if stored.get('name')!=job['name'] or stored.get('action')!=job.get('action'):
        raise ValueError('Combined job changed.')
    if stored.get('card_deleted') or stored.get('delete_requested'):
        raise ValueError('Paired recording was deleted or queued for deletion.')
    if stored.get('upload',{}).get('firmware_compatible_directories') is not True:
        raise ValueError('Paired upload needs verified original-directory placement. Prepare a fresh test with the current uploader.')
    _,item=validate_action(stored)
    audio=(Path(job['directory'])/'speech.mp3').read_bytes()
    upload=stored.get('upload',{})
    if (hashlib.sha256(audio).hexdigest()!=stored['sha256'] or upload.get('sha256')!=stored['sha256']
        or upload.get('action_sha256')!=item['sha256'] or upload.get('name')!=stored['name']):
        raise ValueError('Both speech and action must pass upload verification.')
    robot_speech.packet(stored['name'])  # Validate generated basename before encoding a path.
    if not isinstance(audio_seconds,(int,float)) or not math.isfinite(audio_seconds) or not 0<audio_seconds<=180:
        raise ValueError('Invalid paired recording duration.')
    robot.require_armed()
    job['playback_requests']=stored.get('playback_requests',0)+1
    job.update(status='playback_attempting',playback_attempted=True,playback_transport='bluetooth_paired')
    robot_speech.save_job(job)
    try:
        with robot.operation('paired_action_speech') as (session,record,save):
            robot.require_armed()
            if session.exchange(3,('ACTION/'+job['name']+'.hts').encode('ascii'))!=b'\x00':
                raise ValueError('Robot rejected paired playback. No retry.')
            record.update(action=item,audio=job['name'],playback='accepted');save()
            # Native routines cannot be truncated safely; wait for the longer component.
            time.sleep(max(item['seconds'],audio_seconds)+3)
        job.update(status='playback_accepted')
    except Exception as exc:
        job.update(status='playback_uncertain',error=str(exc));raise
    finally:robot_speech.save_job(job)
    return job


def prepare_probe(audio_name='FAISAL01'):
    """Offline preparation only. The explicit probe uses the approved Celebrate bytes."""
    from .greetings import saved_audio
    from .hold_speech import prepare
    library=saved_audio()
    if audio_name not in library:raise ValueError('Choose verified saved audio.')
    _,wav,seconds=prepare(audio_name,require_player=False)
    item=action_library.inspect('celebrate')
    if seconds>item['seconds']:raise ValueError('First probe audio must fit inside Celebrate; test longer speech separately.')
    if action_library.approval_hash(action_library.approvals().get('celebrate'))!=item['sha256']:
        raise ValueError('Celebrate must already be rehearsed and approved.')
    info=library[audio_name]
    clip={'mp3':str(wav.with_suffix('.mp3')),'voice':info.get('voice','Local'),'style':info.get('style','neutral')}
    if hashlib.sha256(Path(clip['mp3']).read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Audio source changed.')
    job=robot_speech.new_job(clip,info['text'])
    attach(job,'celebrate')
    job.update(experimental=True,probe_audio_seconds=seconds,source_recording=audio_name)
    robot_speech.save_job(job)
    return job


def find_saved(text,voice,style,key):
    """Only exact, verified pairs can replay; uncertain attempts stay blocked."""
    for path in sorted((robot_speech.ROOT/'data/robot-speech').glob('*/job.json'),reverse=True):
        try:
            job=json.loads(path.read_text());upload=job.get('upload',{})
            if (job.get('status')!='playback_accepted' or job.get('card_deleted') or job.get('delete_requested')
                or job.get('text','').strip()!=text.strip() or job.get('voice','Local')!=voice
                or job.get('style','neutral')!=style or job.get('action',{}).get('key')!=key
                or Path(job['directory']).resolve()!=path.parent.resolve()):continue
            _,item=validate_action(job)
            if (upload.get('status')!='complete' or upload.get('firmware_compatible_directories') is not True
                or upload.get('name')!=job['name'] or upload.get('action_sha256')!=item['sha256']
                or upload.get('sha256')!=job['sha256']
                or hashlib.sha256((path.parent/'speech.mp3').read_bytes()).hexdigest()!=job['sha256']):continue
            seconds=job.get('audio_seconds',job.get('probe_audio_seconds'))
            if not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not 0<seconds<=180:continue
            return job
        except (OSError,ValueError,KeyError,TypeError):continue
    return None
