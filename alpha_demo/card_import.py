"""Validate and inventory a local FAT32 image. Never communicates with a robot."""
import hashlib
import struct


def files_from_image(raw):
    if len(raw)<512 or raw[510:512]!=b'\x55\xaa':raise ValueError('Invalid disk signature')
    partition,sectors=struct.unpack_from('<II',raw,454)
    if not partition or (partition+sectors)*512>len(raw):raise ValueError('Invalid partition bounds')
    boot=raw[partition*512:(partition+1)*512]
    bps=struct.unpack_from('<H',boot,11)[0];spc=boot[13]
    reserved=struct.unpack_from('<H',boot,14)[0];nf=boot[16];fatsectors=struct.unpack_from('<I',boot,36)[0]
    if bps!=512 or spc not in (1,2,4,8,16,32,64,128) or nf!=2 or not reserved or not fatsectors:raise ValueError('Unsupported FAT32 layout')
    fat=(partition+reserved)*512;size=fatsectors*512;data=fat+nf*size
    end=(partition+sectors)*512
    if data>=end or raw[fat:fat+size]!=raw[fat+size:fat+2*size]:raise ValueError('Invalid or mismatched FAT copies')
    owners=set();result={};directories=set()
    def chain(c):
        parts=[]
        while 2<=c<0xffffff8:
            off=data+(c-2)*spc*512
            if c in owners or c*4+4>size or off+spc*512>end:raise ValueError('Crosslinked, cyclic or out-of-range cluster')
            owners.add(c);parts.append(raw[off:off+spc*512]);c=struct.unpack_from('<I',raw,fat+c*4)[0]&0xfffffff
        if (parts and c<0xffffff8) or (not parts and c!=0):raise ValueError('Invalid chain end')
        return b''.join(parts)
    def checksum(short):
        value=0
        for b in short:value=(((value&1)<<7)+(value>>1)+b)&255
        return value
    def walk(c,parent='',depth=0):
        if depth>32:raise ValueError('Directory depth exceeds limit')
        lfn={};lfnsum=None;rawdir=chain(c)
        for i in range(0,len(rawdir),32):
            e=rawdir[i:i+32]
            if e[0]==0:break
            if e[0]==229:lfn={};continue
            if e[11]==15:
                if e[0]&64:lfn={};lfnsum=e[13]
                lfn[e[0]&31]=e[1:11]+e[14:26]+e[28:32];continue
            base=e[:8].decode('ascii').strip();ext=e[8:11].decode('ascii').strip();short=base+('.'+ext if ext else '')
            name=short
            if lfn and lfnsum==checksum(e[:11]) and sorted(lfn)==list(range(1,max(lfn)+1)):
                name=b''.join(lfn[j] for j in sorted(lfn)).decode('utf-16-le').split('\0')[0].rstrip('\uffff')
            lfn={}
            if short in ('.','..') or e[11]&8:continue
            if not name or name in ('.','..') or any(ch in name for ch in ('/','\\','\0')):raise ValueError('Unsafe card filename')
            path=parent+name
            if path.casefold() in directories or any(k.casefold()==path.casefold() for k in result):raise ValueError('Duplicate card filename')
            cluster=struct.unpack_from('<H',e,26)[0]+(struct.unpack_from('<H',e,20)[0]<<16)
            if e[11]&16:
                directories.add(path.casefold());walk(cluster,path+'/',depth+1)
            else:
                length=struct.unpack_from('<I',e,28)[0];payload=chain(cluster)[:length]
                if len(payload)!=length:raise ValueError('Truncated card file')
                result[path]=payload
    root_cluster=struct.unpack_from('<I',boot,44)[0]
    if root_cluster<2:raise ValueError('Invalid root cluster')
    walk(root_cluster)
    return result


def inventory(files):
    return [{'path':p,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for p,b in sorted(files.items())]
