"""Capture a supported robot's measured default; never infer defaults from sliders."""
import datetime,json
from pathlib import Path
from .robot_speech import ROOT
from .pose_greetings import validate_pose,check_running,RESET_POSE

def capture(robot,*,supported=False,legs_unloaded=False,progress=lambda message:None,root=ROOT):
    if not supported or not legs_unloaded:raise ValueError('Secure the torso and unload both legs before reading the default pose.')
    measured={}
    for sid in range(1,17):
        check_running(robot);progress(f'Reading and restoring joint {sid}/16')
        result=robot.run(sid,setup=True,support_confirmed=True)
        if result.get('status')!='ok':raise ValueError(result.get('error','Read failed; previous default unchanged.'))
        value=result.get('baseline_degrees')
        if type(value)!=int or not 0<=value<=180:raise ValueError('Invalid measured angle; previous default unchanged.')
        measured[str(sid)]=value
    check_running(robot);validate_pose(measured)
    path=root/'data/default-pose.json';path.parent.mkdir(parents=True,exist_ok=True)
    record={'pose':measured,'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':'supported per-joint measured angle and restored holding'}
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(record,indent=2));temp.replace(path)
    return record

def load(root=ROOT):
    path=root/'data/default-pose.json'
    if not path.exists():return dict(RESET_POSE)
    pose=validate_pose(json.loads(path.read_text())['pose'])
    if len(pose)!=16:raise ValueError('Measured default must contain all 16 joints.')
    return pose
