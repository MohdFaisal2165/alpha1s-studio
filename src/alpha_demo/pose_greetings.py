"""One captured arm pose per greeting. Explicit operations only; no startup I/O."""
import json
from contextlib import nullcontext
from pathlib import Path
import uuid
from .robot_speech import ROOT,new_job,prepare_upload
from .speech import synthesize,validate_text
from .greetings import saved_audio,play_saved,load_profiles

ARM_IDS=tuple(range(1,7))
POSE_PAIRS=((1,4),(2,5),(3,6))
RESET_PAIRS=tuple(reversed(POSE_PAIRS))
RESET_POSE={str(s):90 for s in ARM_IDS}


def validate_pose(pose):
    if type(pose)!=dict or set(pose) not in ({str(s) for s in ARM_IDS},{str(s) for s in range(1,17)}) or any(type(v)!=int or not 0<=v<=180 for v in pose.values()):
        raise ValueError('Save all six arm targets or all 16 joint targets in Pose Studio first.')
    return dict(pose)


def check_running(robot):
    if not robot.armed.is_set():raise ValueError('Stopped. Keep the arms supported; no further requests sent.')


def capture(robot,progress=lambda s:None):
    """Fresh readings, one joint at a time, restoring its measured holding angle."""
    pose={}
    for sid in ARM_IDS:
        check_running(robot)
        progress(f'Recording arm angle {sid}/6 — support both arms…')
        result=robot.run(sid,setup=True,support_confirmed=True)
        if result.get('status')!='ok':raise ValueError(result.get('error','Could not read arm angle. Keep arms supported.'))
        pose[str(sid)]=result['baseline_degrees']
    check_running(robot)
    return validate_pose(pose)


def move_to_pose(robot,pose,progress=lambda s:None,*,reset=False):
    target=validate_pose(pose)
    # Absolute targets do not require releasing/re-reading joints during playback.
    # Record pose remains the only capture path. Check all limits before any send.
    from .panel_transport import validate_bounds
    bounds={}
    for sid in map(int,target):
        bounds[sid]=validate_bounds(sid,*robot.saved_limits.get(sid,(0,180)))
        lo,hi=bounds[sid]
        if not lo<=target[str(sid)]<=hi:
            raise ValueError(f'Motor {sid} target is outside its saved limits. No pose movement started.')
    check_running(robot)
    robot.limits.update(bounds)
    for pair in (RESET_PAIRS if reset else POSE_PAIRS):
        check_running(robot)
        progress(f'Moving arm pair {pair[0]} & {pair[1]}…')
        result=robot.run_pair({sid:target[str(sid)] for sid in pair},support_confirmed=True)
        if result.get('status')!='ok':raise ValueError(result.get('error','Motor did not acknowledge. Remaining moves stopped.'))
    for sid in range(7,17):
        if str(sid) not in target:continue
        check_running(robot);progress(f'Moving supported leg joint {sid}…')
        result=robot.run(sid,target[str(sid)],support_confirmed=True)
        if result.get('status')!='ok':raise ValueError(result.get('error','Leg motion not acknowledged. No retry.'))
    check_running(robot)
    return target


def load(root=ROOT):
    path=root/'data/pose-greetings.json'
    if not path.exists():
        audio=saved_audio(root)
        return {k:{'name':v['name'],'text':audio[v['audio']]['text'],'audio':v['audio'],'pose':None}
                for k,v in load_profiles(root).items() if v['audio'] in audio}
    data=json.loads(path.read_text())
    if type(data)!=dict:raise ValueError('Saved greetings file is invalid.')
    for item in data.values():
        if type(item)!=dict or set(item)!={'name','text','audio','pose'}:raise ValueError('Saved greeting is invalid.')
        if not isinstance(item['name'],str) or not 1<=len(item['name'])<=80:raise ValueError('Saved name is invalid.')
        validate_text(item['text'])
        if item['pose'] is not None:validate_pose(item['pose'])
    return data


def save(name,text,pose,audio,root=ROOT):
    name=name.strip();text=validate_text(text);pose=validate_pose(pose)
    if not 1<=len(name)<=80:raise ValueError('Enter a person’s name (up to 80 characters).')
    library=saved_audio(root)
    if audio not in library or library[audio]['text'].strip()!=text:
        raise ValueError('The exact message has not been uploaded and verified.')
    profiles=load(root)
    key=next((k for k,p in profiles.items() if p['name'].casefold()==name.casefold()),'person_'+uuid.uuid4().hex[:12])
    profiles[key]={'name':name,'text':text,'audio':audio,'pose':pose}
    path=root/'data/pose-greetings.json';path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(profiles,indent=2)+'\n');temp.replace(path)
    return profiles


def prepare(name,text,pose,progress=lambda s:None,root=ROOT):
    """Reuse exact saved audio or upload new text; saving never plays a pose/audio."""
    name=name.strip();text=validate_text(text);pose=validate_pose(pose)
    if not 1<=len(name)<=80:raise ValueError('Enter a person’s name (up to 80 characters).')
    library=saved_audio(root)
    audio=next((k for k,a in library.items() if a['text'].strip()==text),None)
    reconnect=False
    if audio is None:
        progress('Creating the spoken message…')
        clip=synthesize(text,root/'data/speech')
        job=new_job(clip,text)
        prepare_upload(job,progress);audio=job['name'];reconnect=True
    profiles=save(name,text,pose,audio,root)
    return {'profiles':profiles,'reconnect':reconnect}


def play(robot,profile,progress=lambda s:None,*,speaker='robot'):
    pose=validate_pose(profile['pose'])
    # A USB F3 playback is known to reset this robot's pose. Do not send it here.
    wireless=speaker=='robot' and getattr(robot,'supports_robot_speech',False) is True
    if speaker!='computer' and not wireless:
        raise ValueError('Robot-speaker playback resets the pose. Pose-holding playback is available with Computer speaker; robot audio-only control remains unverified.')
    from . import hold_speech
    prepared=robot.prepare_robot_audio(profile['audio']) if wireless else hold_speech.prepare(profile['audio'])
    # Verify audio before any pose change.
    library=saved_audio()
    if profile['audio'] not in library or library[profile['audio']]['text'].strip()!=profile['text'].strip():
        raise ValueError('Saved message is not verified. Save this greeting again.')
    for log in (ROOT/'reports/greeting-playback').glob('*.json'):
        if json.loads(log.read_text()).get('status') in ('attempting','uncertain'):
            raise ValueError('Earlier playback is uncertain. Inspect its report before moving or playing again.')
    # Keep the link open across all pairs and speech; immediate RFCOMM
    # reconnects were rejected by this robot before any greeting command.
    with (robot.sequence() if wireless else nullcontext()):
        move_to_pose(robot,pose,progress)
        check_running(robot)
        if wireless:
            progress('Holding the saved pose. Speaking through the ROBOT…')
            return robot.play_robot_audio(prepared)
        progress('Holding the saved pose. Speaking through the COMPUTER…')
        return hold_speech.play(prepared,robot.armed)
