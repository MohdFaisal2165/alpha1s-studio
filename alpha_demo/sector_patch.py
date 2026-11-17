"""Verified sector patches with injected I/O; no automatic hardware access."""

def apply_patch_blocks(before, after, order, metadata, read, write, flush, progress):
    if len(before)!=len(after) or len(before)%512:
        raise ValueError('Invalid image size')
    changed={i//512 for i in range(0,len(before),512) if before[i:i+512]!=after[i:i+512]}
    if len(order)!=len(set(order)) or set(order)!=changed:
        raise ValueError('Patch order does not match image differences')
    checks=set(metadata)|changed
    if any(s<0 or s*512>=len(before) for s in checks):
        raise ValueError('Invalid sector')
    # Finish all preflight comparisons before the first write.
    for sector in sorted(checks):
        if read(sector)!=before[sector*512:(sector+1)*512]:
            raise ValueError(f'Card changed at sector {sector}; no writes started')
    progress('preflight_complete',None)
    for sector in order:
        payload=after[sector*512:(sector+1)*512]
        progress('writing',sector)
        if write(sector,payload)!=512:
            raise IOError(f'Short write at {sector}; stopped, do not play')
        flush()
        if read(sector)!=payload:
            raise IOError(f'Readback mismatch at {sector}; stopped, do not play')
        progress('verified',sector)
    for sector in order:
        if read(sector)!=after[sector*512:(sector+1)*512]:
            raise IOError(f'Final comparison failed at {sector}')
    progress('complete',None)
