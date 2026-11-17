"""Plan deletion of verified generated files, rejecting cross-linked FAT chains."""
import hashlib,re,struct
from collections import Counter
from .audio_card import u16,u32

def stage_cleanup(template,read,targets):
    before=bytearray(template);metadata=set()
    def refresh(s):
        block=read(s)
        if len(block)!=512:raise ValueError('Short card read')
        before[s*512:(s+1)*512]=block;metadata.add(s);return block
    mbr=refresh(0);start=u32(mbr,454);boot=refresh(start)
    if mbr!=template[:512] or boot!=template[start*512:(start+1)*512]:raise ValueError('Card identity changed')
    spc=boot[13];fat=start+u16(boot,14);nfats=boot[16];fatsz=u32(boot,36);data=fat+nfats*fatsz
    count=(u32(boot,32)-u16(boot,14)-nfats*fatsz)//spc
    if u16(boot,11)!=512 or spc not in (1,2,4,8,16,32,64,128) or nfats!=2 or not fatsz or data>=len(before)//512 or (count+2)*4>fatsz*512:raise ValueError('Unsupported FAT geometry')
    for s in range(fat,data):refresh(s)
    if before[fat*512:(fat+fatsz)*512]!=before[(fat+fatsz)*512:data*512]:raise ValueError('FAT copies disagree')
    def chain(c):
        seen=[]
        while c<0x0ffffff8:
            if c<2 or c>=count+2 or c in seen:raise ValueError('Invalid FAT chain')
            seen.append(c);c=u32(before,fat*512+c*4)&0x0fffffff
        return seen
    owners=Counter();entries={};seen_dirs=set()
    def walk(c,path):
        clusters=chain(c)
        if any(n in seen_dirs for n in clusters):raise ValueError('Directory cycle')
        seen_dirs.update(clusters);owners.update(clusters);long_name=False
        for cluster in clusters:
            for sector in range(data+(cluster-2)*spc,data+(cluster-1)*spc):
                block=refresh(sector)
                for i in range(0,512,32):
                    e=block[i:i+32]
                    if e[0]==0:return
                    if e[0]==229:long_name=False;continue
                    if e[11]==15:long_name=True;continue
                    name=e[:8].decode('ascii',errors='replace').strip();ext=e[8:11].decode('ascii',errors='replace').strip()
                    child=(u16(e,20)<<16)|u16(e,26)
                    if name in ('.','..') or e[11]&8:long_name=False;continue
                    if e[11]&16:walk(child,path+'/'+name)
                    else:
                        allocated=chain(child) if child else [];owners.update(allocated)
                        entries[path+'/'+name+('.'+ext if ext else '')]=(sector*512+i,allocated,u32(e,28),long_name)
                    long_name=False
    walk(u32(boot,44),'')
    selected=[]
    for directory,filename,sha in targets:
        if directory not in ('MUSIC','ACTION') or not re.fullmatch(r'S[0-9A-F]{7}\.(MP3|HTS)',filename):raise ValueError('Only generated files can be deleted')
        short=(filename.split('.')[0]+filename.split('.')[1]).encode('ascii')
        if short in template:raise ValueError('Original backup files are protected')
        entry=entries.get('/'+directory+'/'+filename)
        if entry is None:continue  # Already absent, never infer success for any other name.
        off,clusters,size,long_name=entry
        if long_name or any(owners[c]!=1 for c in clusters):raise ValueError('File has aliases or cross-linked clusters')
        contents=bytearray()
        for c in clusters:
            for sector in range(data+(c-2)*spc,data+(c-1)*spc):contents.extend(refresh(sector))
        if size>len(contents) or hashlib.sha256(contents[:size]).hexdigest()!=sha:raise ValueError('Recording differs from uploaded checksum; not deleted')
        selected.append(entry)
    after=bytearray(before);directories=set();fats=set();freed=set()
    for off,clusters,_,_ in selected:
        after[off]=229;directories.add(off//512)
        for c in clusters:
            freed.add(c)
            for f in range(nfats):
                off=(fat+f*fatsz)*512+c*4;struct.pack_into('<I',after,off,0);fats.add(off//512)
    # Free-space counters become unknown; allocation uses the actual FAT.
    infos=set()
    for sector in {start+u16(boot,48),start+u16(boot,50)+u16(boot,48)}:
        if start<sector<fat:
            block=refresh(sector);after[sector*512:(sector+1)*512]=block
            if block[:4]==b'RRaA' and block[484:488]==b'rrAa':
                struct.pack_into('<I',after,sector*512+488,0xffffffff);infos.add(sector)
    order=sorted(directories)+sorted(fats)+sorted(infos)
    order=[s for s in order if before[s*512:(s+1)*512]!=after[s*512:(s+1)*512]]
    return before,after,order,metadata
