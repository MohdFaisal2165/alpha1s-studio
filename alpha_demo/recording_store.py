"""Keep/delete metadata. Only hash-verified Studio-generated files can be reclaimed."""
import json,re
from pathlib import Path
from .robot_speech import ROOT

def jobs(root=ROOT):
    result=[]
    for path in (root/'data/robot-speech').glob('*/job.json'):
        try:
            j=json.loads(path.read_text())
            if not re.fullmatch(r'S[0-9A-F]{7}',j.get('name','')):continue
            j['_path']=path;result.append(j)
        except (ValueError,OSError):continue
    return result

def protected(root=ROOT):
    names=set()
    for filename in ('pose-greetings.json','greeting-profiles.json'):
        path=root/'data'/filename
        if path.exists():
            for profile in json.loads(path.read_text()).values():names.add(profile.get('audio'))
    return names

def update(name,*,keep=None,delete=False,root=ROOT):
    if delete and name in protected(root):raise ValueError('This recording belongs to a saved greeting.')
    for job in jobs(root):
        if job['name']!=name:continue
        path=job.pop('_path')
        if keep is not None:job['keep']=bool(keep);job['delete_requested']=False
        if delete:
            if job.get('keep'):raise ValueError('Unsave this recording before deleting it.')
            job['delete_requested']=True
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(job,indent=2));tmp.replace(path);return
    raise ValueError('Recording not found.')

def cleanup_candidates(root=ROOT):
    pinned=protected(root);all_jobs=jobs(root)
    temporary=sorted([j for j in all_jobs if j.get('temporary') and j.get('status')=='playback_accepted' and not j.get('keep') and j['name'] not in pinned],key=lambda j:j['_path'].stat().st_mtime,reverse=True)
    expired={j['name'] for j in temporary[5:]}
    result=[]
    for j in all_jobs:
        if j['name'] in pinned or j.get('keep') or j.get('card_deleted'):continue
        if not j.get('delete_requested') and j['name'] not in expired:continue
        upload=j.get('upload',{})
        if upload.get('status')!='complete' or upload.get('sha256')!=j.get('sha256') or upload.get('name')!=j['name']:continue
        files=[('MUSIC',j['name']+'.MP3',j['sha256'])]
        if j.get('action'):
            if upload.get('action_sha256')!=j['action']['sha256']:continue
            files.append(('ACTION',j['name']+'.HTS',j['action']['sha256']))
        result.append({'name':j['name'],'files':files})
    return result

def mark_deleted(names,root=ROOT):
    for job in jobs(root):
        if job['name'] not in names:continue
        path=job.pop('_path');job['card_deleted']=True
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(job,indent=2));tmp.replace(path)


def delete_now(names,progress,root=ROOT):
    """Explicit selection only. USB cleanup, with no upload or playback."""
    import uuid
    from . import robot_speech
    from .conversation_speech import alpha_usb_present
    if not names:raise ValueError('Select recordings first.')
    if not alpha_usb_present():raise ValueError('Connect robot USB to permanently delete recordings.')
    selected={j['name']:j for j in jobs(root)}
    for name in names:
        if name not in selected or name in protected(root):raise ValueError('Recording is missing or belongs to a saved greeting.')
    for name in names:update(name,keep=False,delete=True,root=root)
    if not set(names)<={item['name'] for item in cleanup_candidates(root)}:raise ValueError('Selected recording is not verified for deletion.')
    folder=root/'data/robot-speech'/uuid.uuid4().hex;folder.mkdir(parents=True)
    job={'directory':str(folder),'kind':'delete_recordings','delete_names':list(names),'status':'prepared','playback_attempted':False}
    robot_speech.save_job(job)
    robot_speech.prepare_upload(job,progress)
    mark_deleted(names,root)
    return names
