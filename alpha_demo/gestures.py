"""Record an operator's successful arm commands; replay only reviewed closed loops."""
import json
from pathlib import Path
from .robot_speech import ROOT


def arm_pose(robot):
    pose={}
    for sid in range(1,7):
        value=robot.targets.get(sid,robot.positions.get(sid,{}).get('angle'))
        if type(value)!=int or not 0<=value<=180 or sid not in robot.limits:
            raise ValueError('Read all six supported arm joints before recording a gesture.')
        pose[str(sid)]=value
    return pose


def validate(gesture):
    if type(gesture)!=dict or set(gesture)!={'start','steps','reviewed'} or gesture['reviewed'] is not True:
        raise ValueError('Gesture has not been reviewed by its operator')
    pose=gesture['start']
    if type(pose)!=dict or set(pose)!={str(i) for i in range(1,7)} or any(type(v)!=int or not 0<=v<=180 for v in pose.values()):
        raise ValueError('Invalid arm starting pose')
    steps=gesture['steps']
    if type(steps)!=list or not 2<=len(steps)<=12:raise ValueError('Record 2–12 arm moves, ending at the starting pose')
    end=dict(pose)
    for step in steps:
        if type(step)!=dict or set(step)!={'servo','target'} or type(step['servo'])!=int or step['servo'] not in range(1,7) or type(step['target'])!=int or not 0<=step['target']<=180:
            raise ValueError('Only recorded arm commands are allowed')
        end[str(step['servo'])]=step['target']
    if end!=pose:raise ValueError('Return every moved arm joint to its recorded starting angle before saving')
    return gesture


def load(root=ROOT):
    path=root/'data/faisal-gesture.json'
    if not path.exists():return None
    return validate(json.loads(path.read_text()))


def save(start,steps,reviewed,root=ROOT):
    gesture=validate({'start':start,'steps':steps,'reviewed':reviewed})
    path=root/'data/faisal-gesture.json';path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(gesture,indent=2)+'\n');tmp.replace(path)
    return gesture


def replay(robot,gesture):
    validate(gesture)
    if not robot.armed.is_set():raise ValueError('Enable editing before a rehearsed gesture')
    if arm_pose(robot)!=gesture['start']:raise ValueError('Arm values do not match the recorded start. Set that pose manually first.')
    # Check every bound before the first move, then let the normal transport check holding/arming each time.
    for step in gesture['steps']:
        lo,hi=robot.limits[step['servo']]
        if not lo<=step['target']<=hi:raise ValueError('Gesture exceeds the current joint limits')
    for step in gesture['steps']:
        if not robot.armed.is_set():raise ValueError('Gesture disarmed; remaining steps cancelled')
        result=robot.run(step['servo'],step['target'],support_confirmed=True)
        if result.get('status')!='ok':raise ValueError('Gesture stopped: '+result.get('error','motor reply failed'))
    return 'Recorded gesture completed'
