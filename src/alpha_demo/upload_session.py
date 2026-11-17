"""Reuse one authenticated helper per Studio process; no password is stored."""
import atexit,json,subprocess,threading
from pathlib import Path
_process=None
_lock=threading.Lock()

def close():
    global _process
    if _process is not None:
        if _process.stdin:_process.stdin.close()  # EOF; helper exits after any current write finishes.
        _process=None
atexit.register(close)

def upload(job,device,progress):
    global _process
    from .robot_speech import ROOT
    from .recording_store import mark_deleted
    with _lock:
        if _process is None or _process.poll() is not None:
            progress('Authorize uploads once for this Studio session.')
            _process=subprocess.Popen(['/usr/bin/pkexec','/usr/bin/python3','-I',str(ROOT/'alpha_demo/upload_session_worker.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
            line=_process.stdout.readline()
            if not line:close();raise ValueError('Upload authorization was cancelled or the helper could not start.')
            event=json.loads(line)
            if event.get('status')!='ready':close();raise ValueError('Upload helper did not become ready.')
            progress(event['message'])
        request={'job':Path(job['directory']).name,'device':device}
        _process.stdin.write(json.dumps(request)+'\n');_process.stdin.flush()
        while True:
            line=_process.stdout.readline()
            if not line:close();raise ValueError('Upload session ended unexpectedly. Inspect the journal before retrying.')
            event=json.loads(line);progress(event.get('message','Uploading…'))
            if event.get('status')=='cleanup_complete':
                mark_deleted(event['names'])
                from .robot_speech import save_job
                job['cleanup_complete']=True;save_job(job)
            if event.get('status')=='error':raise ValueError(event['error'])
            if event.get('status')=='complete':return event
