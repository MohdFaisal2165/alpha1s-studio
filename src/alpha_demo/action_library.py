"""Local Alpha library inspection and explicit operator approval. No startup I/O to robot."""
import hashlib,json
from pathlib import Path
from .robot_speech import ROOT
CANDIDATES={'celebrate':('Celebrate','ACTION/GAMEPAD/Celebrate.hts','Celebrate an achievement or a correct answer.'),
 'success':('Success','ACTION/COURSE/course_success.hts','Encourage a participant after solving a problem.'),
 'presentation':('Presentation','ACTION/Presentation.hts','Introduce a workshop; long full-body routine.')}

# Descriptions guide selection; authorization and integrity checks remain mandatory.
CANDIDATES['encourage']=('Try again','ACTION/COURSE/course_failer.hts','Gently acknowledge a setback and encourage another attempt.')

def candidates(root=ROOT):
    result=dict(CANDIDATES)
    source=root/'reports/card-file-inventory.json'
    if not source.exists():return result
    known={v[1].casefold() for v in result.values()}
    for entry in json.loads(source.read_text()):
        path=entry['path'];p=Path(path)
        if p.suffix.lower()!='.hts' or path.casefold() in known:continue
        if p.is_absolute() or '..' in p.parts or p.parts[0]!='ACTION':continue
        key='card_'+hashlib.sha256(path.encode()).hexdigest()[:16]
        result[key]=(p.stem.replace('_',' '),path,'Use only when the participant explicitly requests this named routine; prefer short expressive actions for conversation.')
    return result

def approval_hash(value):
    return value.get('sha256') if isinstance(value,dict) else value

def browse(root=ROOT):
    items=[]
    for key in candidates(root):
        try:items.append(inspect(key,root))
        except (OSError,ValueError):continue
    return sorted(items,key=lambda x:(not x['conversation_candidate'],x['seconds'],x['title'].casefold()))

def inspect(key,root=ROOT):
    title,path,meaning=candidates(root)[key]
    file=root/'work/card-extracted'/path
    if file.is_symlink() or not file.resolve().is_relative_to((root/'work/card-extracted').resolve()):raise ValueError('Action path is not a local card file.')
    raw=file.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    inventory=json.loads((root/'reports/card-file-inventory.json').read_text())
    if not any(x['path']==path and x['sha256']==sha for x in inventory):raise ValueError('Action differs from the verified card backup.')
    if len(raw)<99 or len(raw)%33:raise ValueError('Invalid HTS size')
    frames=[raw[i:i+33] for i in range(33,len(raw)-33,33)]
    if any(f[:2]!=b'\xfb\xbf' or f[-1]!=237 or f[31]!=sum(f[2:31])%256 for f in frames):raise ValueError('Invalid HTS frame/checksum')
    if any(v>180 for f in frames for v in f[8:24]):raise ValueError('Action includes unsupported joint values')
    seconds=int.from_bytes(raw[-4:],'little')/1000
    if not 0<seconds<=120:raise ValueError('Action duration is outside the demo limit')
    ranges={str(i+1):[min(f[8+i] for f in frames),max(f[8+i] for f in frames)] for i in range(16)}
    return {'key':key,'title':title,'path':path,'meaning':meaning,'sha256':sha,'seconds':seconds,'frames':len(frames),'ranges':ranges,'full_body':True,'conversation_candidate':True,
            'has_music':any(Path(x['path']).suffix.lower()=='.mp3' and Path(x['path']).stem.casefold()==Path(path).stem.casefold() for x in inventory)}

def approvals(root=ROOT):
    path=root/'data/teacher-action-approvals.json'
    if not path.exists():return {}
    value=json.loads(path.read_text())
    if type(value)!=dict:raise ValueError('Invalid action approvals')
    return value

def approve(key,root=ROOT,meaning=None):
    item=inspect(key,root)
    meaning=(meaning or item['meaning']).strip()
    if not 1<=len(meaning)<=240:raise ValueError('Describe when to use the gesture in 1–240 characters.')
    data=approvals(root);data[key]={'sha256':item['sha256'],'meaning':meaning}
    path=root/'data/teacher-action-approvals.json';path.parent.mkdir(exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2));temp.replace(path)

def choices(root=ROOT):
    result={'none':{'title':'Speak only','meaning':'Answer without a robot gesture.'}}
    from .pose_greetings import load
    for key,p in load(root).items():
        if p['pose'] is not None:
            result['pose:'+key]={'title':'Greet '+p['name'],'meaning':'Use when the participant introduces themselves as '+p['name']+'. Saved greeting: '+p['text'],'profile':p}
    for key,sha in approvals(root).items():
        if key not in candidates(root):continue
        item=inspect(key,root)
        if item['conversation_candidate'] and item['sha256']==approval_hash(sha):
            if isinstance(sha,dict):item['meaning']=sha.get('meaning',item['meaning'])
            result['library:'+key]=item
    return result

def play_native(robot,key,*,supported=False,rehearsal=False,root=ROOT):
    if not supported:raise ValueError('Confirm full-body support and clearance first.')
    item=inspect(key,root)
    if not rehearsal and approval_hash(approvals(root).get(key))!=item['sha256']:raise ValueError('Rehearse and approve this library action first.')
    robot.require_armed()
    # Full native actions can involve all joints and their own audio/reset behavior.
    # Never use the speech skip-reset flag for these files.
    import time
    with robot.operation('reviewed_library_action') as (session,record,save):
        record['action']=item;save();robot.require_armed()
        if session.exchange(3,item['path'].encode('ascii'))!=b'\x00':raise ValueError('Robot rejected the library action. No retry.')
        record['action_delivery']='accepted';save()
        deadline=time.monotonic()+item['seconds']+3
        # Stop cannot cancel an action already accepted by the robot.
        while time.monotonic()<deadline:time.sleep(min(.1,deadline-time.monotonic()))
    return item


def approve_all(root=ROOT):
    """Explicit bulk authorization; does not claim each action was rehearsed."""
    data=approvals(root)
    for item in browse(root):
        previous=data.get(item['key'])
        if approval_hash(previous)==item['sha256']:continue
        data[item['key']]={'sha256':item['sha256'],'meaning':item['meaning'],
                           'authorization':'User requested all verified library actions for Gemini selection',
                           'rehearsal_verified':False}
    path=root/'data/teacher-action-approvals.json';path.parent.mkdir(exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2));temp.replace(path)
    return len(data)
