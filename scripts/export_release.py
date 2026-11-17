"""Create a clean, reviewed GitHub upload folder. Never copy runtime state or publish."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
TOP=('README.md','LICENSE','CHANGELOG.md','CONTRIBUTING.md','SECURITY.md','THIRD_PARTY_NOTICES.md',
     'pyproject.toml','.gitignore','.env.example','launch-control-panel.sh')


def source_files(root):
    files=[root/name for name in TOP]
    for folder,suffixes in [('alpha_demo',{'.py'}),('tests',{'.py'}),('docs',{'.md'}),('scripts',{'.py'}),('.github',{'.md','.yml','.yaml'})]:
        files += sorted(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
    files.append(root/'assets/joint-map.png')
    return files


def validate(path):
    if path.is_symlink():raise ValueError('Symlinks are not exported: '+str(path))
    if path.suffix=='.png':return
    text=path.read_text()
    patterns=[r'AIza[0-9A-Za-z_-]{30,}',r'gh[pousr]_[0-9A-Za-z]{30,}',r'-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----',r'/home/[a-zA-Z][\w.-]+/',r'(?i)(?:[0-9a-f]{2}:){5}[0-9a-f]{2}']
    if any(re.search(pattern,text) for pattern in patterns):
        raise ValueError('Potential private credential/address/path in '+str(path))


def export(root=ROOT):
    files=source_files(root)
    for path in files:validate(path)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    destination=root/'release'/('alpha1s-studio-'+stamp)
    destination.mkdir(parents=True,exist_ok=False)
    manifest=[]
    for path in files:
        relative=path.relative_to(root);target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        manifest.append({'path':relative.as_posix(),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    for name in ('data','reports','work','backups'):
        folder=destination/name;folder.mkdir(exist_ok=True)
        target=folder/'.gitkeep';target.write_text('')
        manifest.append({'path':name+'/.gitkeep','sha256':hashlib.sha256(b'').hexdigest()})
    (destination/'RELEASE-MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return destination

if __name__=='__main__':print(export())
