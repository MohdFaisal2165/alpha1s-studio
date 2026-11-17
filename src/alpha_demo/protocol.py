"""USB protocol framing and response validation used by Studio."""

PACKETS = {
 'status':bytes.fromhex('effe00000000000000ed'),
 'connect':bytes.fromhex('f44f01010000000002ed'),

 'disconnect':bytes.fromhex('f44f01000000000001ed'),
}

def ack(raw):
    if raw[:4]!=bytes.fromhex('f44faaed') or any(raw[4:]):
        raise ValueError('PC connection acknowledgement invalid')
    return 'acknowledged'

def frame(raw,servo):
    if len(raw)!=64 or raw[:3]!=bytes([250,175,servo]) or raw[9]!=237 or raw[8]!=sum(raw[2:8])&255 or any(raw[10:]):
        raise ValueError('Invalid servo reply')

def position(raw,servo):
    frame(raw,servo)
    if raw[3]!=170:raise ValueError('Position read failed')
    value=int.from_bytes(raw[6:8],'big',signed=True)
    if not 0<=value<=180:raise ValueError('Invalid angle')
    return value

def parse_play_reply(raw):
    # Accept the documented status+terminator form, with optional status checksum.
    if raw[:4] == bytes.fromhex('f33faaed') and not any(raw[4:]):
        return 'accepted; audio and movement not verified'
    if raw[:5] == bytes.fromhex('f33faaaaed') and not any(raw[5:]):
        return 'accepted; audio and movement not verified'
    raise ValueError('Playback reply not confirmed; preserve raw report, do not retry')

def request_for(name):
    if name not in ('LOWBAT','FAISAL01'):
        raise ValueError('Audio name is not allowlisted')
    value=name.encode('ascii');data=bytes([len(value)+1])+value
    return b'\xf3\x3f'+data+bytes([sum(data)&255,0xed])
