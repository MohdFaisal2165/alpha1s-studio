"""Add one short-name MP3 to the verified FAT32 layout, preserving existing files.

All device reads are injected. No formatting or overwrite of existing files; bounded directory growth is supported.
"""
import struct


def u16(b, o): return struct.unpack_from('<H', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]


def stage_audio(template, read, audio, name, action=None, *, firmware_compatible=False):
    import re
    if not re.fullmatch(r'S[0-9A-F]{7}', name):
        raise ValueError('Invalid generated audio name')
    if not 1 <= len(audio) <= 4*1024*1024:
        raise ValueError('Audio must be between 1 byte and 4 MiB')
    before=bytearray(template)
    metadata=set()
    def refresh(s):
        block=read(s)
        if len(block)!=512: raise IOError('Short card read')
        before[s*512:(s+1)*512]=block; metadata.add(s)
        return block
    mbr=refresh(0)
    if mbr!=template[:512] or mbr[510:512]!=b'\x55\xaa':
        raise ValueError('Card partition layout changed')
    start=u32(mbr,454); boot=refresh(start)
    if boot!=template[start*512:(start+1)*512]:
        raise ValueError('Card filesystem identity changed')
    spc=boot[13]; reserved=u16(boot,14); nfats=boot[16]; fatsz=u32(boot,36)
    total=u32(boot,32); root=u32(boot,44)
    if (u16(boot,11)!=512 or spc not in (1,2,4,8,16,32,64,128)
            or nfats!=2 or not fatsz or u16(boot,40)&128
            or start+total>len(template)//512):
        raise ValueError('Unsupported FAT32 geometry')
    fat=start+reserved; data=fat+nfats*fatsz
    count=(total-reserved-nfats*fatsz)//spc
    if count<1 or (count+2)*4>fatsz*512: raise ValueError('Invalid FAT size')
    for s in range(fat,data): refresh(s)
    if before[fat*512:(fat+fatsz)*512]!=before[(fat+fatsz)*512:data*512]:
        raise ValueError('FAT copies disagree; no upload')
    def next_cluster(c): return u32(before,fat*512+c*4)&0x0fffffff
    def chain(c):
        seen=set()
        while c<0x0ffffff8:
            if c<2 or c>=count+2 or c in seen: raise ValueError('Invalid directory chain')
            seen.add(c);yield c;c=next_cluster(c)
    def directory(c):
        entries=[]
        for cluster in chain(c):
            for s in range(data+(cluster-2)*spc,data+(cluster-1)*spc):
                refresh(s)
                entries.extend(range(s*512,(s+1)*512,32))
        return entries
    root_entries=directory(root)
    def subdir(short):
        for o in root_entries:
            e=before[o:o+32]
            if e[0]==0: break
            if e[:11]==short and e[11]&16:
                cluster=(u16(e,20)<<16)|u16(e,26)
                return directory(cluster),list(chain(cluster))[-1]
        raise ValueError('Required robot folder is missing')
    music,music_tail=subdir(b'MUSIC      ');actions,actions_tail=subdir(b'ACTION     ')
    # Both the direct name and a long-name alias must be absent.
    def names(entries):
        pending=[]; result=set()
        for o in entries:
            e=before[o:o+32]
            if e[0]==0: break
            if e[0]==229: pending=[];continue
            if e[11]==15:
                pending.insert(0,bytes(e[1:11]+e[14:26]+e[28:32]));continue
            result.add(bytes(e[:8]).decode('ascii',errors='replace').strip().upper())
            if pending:
                result.add(b''.join(pending).decode('utf-16le',errors='replace').split('\0')[0].split('.')[0].upper())
            pending=[]
        return result
    if name in names(music)|names(actions): raise ValueError('Audio/action name already exists')
    payloads=[(music,audio,'MP3',music_tail)]
    if action is not None:
        if not 99 <= len(action) <= 1024*1024 or len(action)%33:
            raise ValueError('Invalid paired action size')
        payloads.append((actions,action,'HTS',actions_tail))
    files=[];used=set();data_sectors=[];growth=[]
    for entries,payload,extension,tail in payloads:
        # MP3 lookup failed after MUSIC growth; existing ACTION chain playback was observed.
        if firmware_compatible and extension=='MP3':entries=entries[:spc*512//32]
        slots=[o for o in entries if before[o]==229]
        slots += [o for i,o in enumerate(entries[:-1]) if before[o:o+32]==bytes(32) and before[entries[i+1]]==0]
        if not slots:
            if firmware_compatible:
                raise ValueError(('Original MUSIC' if extension=='MP3' else 'Existing ACTION')+' directory space is full. Use Storage to delete an unwanted Studio recording. No directory expansion or file write was performed.')
            cluster=next((c for c in range(2,count+2) if c not in used and u32(before,fat*512+c*4)==0),None)
            if cluster is None:raise ValueError('No space to expand '+extension+' folder')
            used.add(cluster);sectors=list(range(data+(cluster-2)*spc,data+(cluster-1)*spc))
            for sector in sectors:refresh(sector)
            growth.append((tail,cluster,sectors));slots=[sectors[0]*512]
        needed=(len(payload)+spc*512-1)//(spc*512)
        allocated=[]
        for c in range(2,count+2):
            if c not in used and u32(before,fat*512+c*4)==0:allocated.append(c)
            if len(allocated)==needed:break
        if len(allocated)!=needed:raise ValueError('Not enough free card space')
        used.update(allocated);sectors=[]
        for c in allocated:
            for sector in range(data+(c-2)*spc,data+(c-1)*spc):
                refresh(sector);sectors.append(sector)
        files.append((slots[0],payload,extension,allocated,sectors));data_sectors.extend(sectors)
    fsinfos=[]
    for s in {start+u16(boot,48),start+u16(boot,50)+u16(boot,48)}:
        if not start<s<fat: continue
        block=refresh(s)
        if block[:4]==b'RRaA' and block[484:488]==b'rrAa': fsinfos.append(s)
    after=bytearray(before);fat_sectors=set()
    directory_sectors=[];new_directory_sectors=[]
    for tail,cluster,sectors in growth:
        new_directory_sectors.extend(sectors)
        for sector in sectors:after[sector*512:(sector+1)*512]=bytes(512)
        for f in range(nfats):
            for c,value in ((tail,cluster),(cluster,0x0fffffff)):
                off=(fat+f*fatsz)*512+c*4
                struct.pack_into('<I',after,off,value);fat_sectors.add(off//512)

    for slot,payload,extension,allocated,sectors in files:
        for i,c in enumerate(allocated):
            nxt=allocated[i+1] if i+1<len(allocated) else 0x0fffffff
            for f in range(nfats):
                off=(fat+f*fatsz)*512+c*4
                struct.pack_into('<I',after,off,nxt);fat_sectors.add(off//512)
        padded=payload.ljust(len(sectors)*512,b'\0')
        for i,sector in enumerate(sectors):after[sector*512:(sector+1)*512]=padded[i*512:(i+1)*512]
        entry=bytearray(32);entry[:11]=(name+extension).encode('ascii');entry[11]=32
        struct.pack_into('<H',entry,20,allocated[0]>>16)
        struct.pack_into('<H',entry,26,allocated[0]&65535)
        struct.pack_into('<I',entry,28,len(payload));after[slot:slot+32]=entry
        directory_sectors.append(slot//512)
    needed=len(used)
    for s in fsinfos:
        free=u32(before,s*512+488)
        if free!=0xffffffff:
            if free<needed: raise ValueError('Invalid free-space counter')
            struct.pack_into('<I',after,s*512+488,free-needed)
    order=data_sectors+new_directory_sectors+sorted(fat_sectors)+sorted(fsinfos)+[s for s in dict.fromkeys(directory_sectors) if s not in new_directory_sectors]
    order=[s for s in order if before[s*512:(s+1)*512]!=after[s*512:(s+1)*512]]
    if len(order)!=len(set(order)): raise ValueError('Invalid commit ordering')
    return before,after,order,metadata
