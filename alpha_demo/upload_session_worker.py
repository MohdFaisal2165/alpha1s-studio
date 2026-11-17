"""One explicitly authorized upload session. Private stdin/stdout, no network listener.

Freeze project Python sources before accepting requests; subsequent code edits
cannot change the elevated helper. File metadata runs as the invoking user.
"""
import importlib.abc,importlib.util,json,os,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class FrozenPackage(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def __init__(self):
        self.sources={}
        for p in (ROOT/'alpha_demo').glob('*.py'):
            raw=p.read_bytes()
            if len(raw)>1024*1024:raise ValueError('Oversized helper module')
            name='alpha_demo' if p.stem=='__init__' else 'alpha_demo.'+p.stem
            self.sources[name]=(str(p),raw)
    def find_spec(self,name,path=None,target=None):
        if name in self.sources:return importlib.util.spec_from_loader(name,self,is_package=name=='alpha_demo')
    def create_module(self,spec):return None
    def exec_module(self,module):
        filename,raw=self.sources[module.__name__];module.__file__=filename
        if module.__name__=='alpha_demo':module.__path__=[]
        exec(compile(raw,filename,'exec'),module.__dict__)

def main():
    if os.getuid()!=0:raise ValueError('Start this helper with the system authorization dialog.')
    uid=int(os.environ['PKEXEC_UID'])
    if uid<=0:raise ValueError('A desktop user is required.')
    sys.meta_path.insert(0,FrozenPackage())
    from alpha_demo.speech_upload import upload,emit
    os.seteuid(uid)
    emit(status='ready',message='Upload session authorized until Studio closes.')
    for line in sys.stdin:
        try:
            if len(line)>2048:raise ValueError('Oversized upload request')
            request=json.loads(line)
            if set(request)!={'job','device'} or not re.fullmatch('[0-9a-f]{32}',request['job']):raise ValueError('Invalid upload request')
            if not re.fullmatch('/dev/[A-Za-z0-9]+',request['device']):raise ValueError('Invalid device path')
            upload(ROOT/'data/robot-speech'/request['job']/'job.json',request['device'])
        except Exception as exc:emit(status='error',error=str(exc),message='Upload stopped: '+str(exc))
if __name__=='__main__':main()
