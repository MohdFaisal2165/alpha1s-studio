"""Local speech generation only. Never opens robot devices or sends actions."""
import ctypes as c
import ctypes.util
import json
from pathlib import Path
import subprocess
import sys
import uuid
import wave


def validate_text(text):
    if not isinstance(text,str) or not text.strip() or len(text)>1500 or '\0' in text:
        raise ValueError('Enter 1–1500 characters, without null characters.')
    return text.strip()

def synthesize(text,directory):
    """Generate in a separate process: native engine failures cannot freeze Tk."""
    text=validate_text(text)
    directory=Path(directory)/uuid.uuid4().hex
    directory.mkdir(parents=True)
    result=subprocess.run([sys.executable,'-m','alpha_demo.speech','--worker',str(directory)],
        input=text,text=True,capture_output=True,timeout=30,check=False,
        cwd=Path(__file__).resolve().parents[1])
    if result.returncode:
        raise RuntimeError('Speech generation failed: '+result.stderr.strip()[-400:])
    data=json.loads(result.stdout)
    for key in ('wav','mp3'):
        if not Path(data[key]).is_file():raise RuntimeError('Speech file was not created.')
    return data

def generate_files(text,directory):
    text=validate_text(text);directory=Path(directory)
    libname=ctypes.util.find_library('espeak-ng')
    if not libname:raise RuntimeError('Local eSpeak NG speech engine is unavailable.')
    lib=c.CDLL(libname)
    lib.espeak_Initialize.argtypes=[c.c_int,c.c_int,c.c_char_p,c.c_int]
    lib.espeak_Initialize.restype=c.c_int
    rate=lib.espeak_Initialize(2,0,None,0x8000) # synchronous PCM retrieval, no playback
    if rate<=0:raise RuntimeError('Speech engine data unavailable.')
    chunks=[]
    callback_type=c.CFUNCTYPE(c.c_int,c.POINTER(c.c_short),c.c_int,c.c_void_p)
    @callback_type
    def collect(samples,count,events):
        if samples and count>0:chunks.append(c.string_at(samples,count*2))
        return 0
    lib.espeak_SetSynthCallback.argtypes=[callback_type];lib.espeak_SetSynthCallback(collect)
    lib.espeak_SetVoiceByName.argtypes=[c.c_char_p]
    lib.espeak_Synth.argtypes=[c.c_char_p,c.c_size_t,c.c_uint,c.c_int,c.c_uint,c.c_uint,c.c_void_p,c.c_void_p]
    try:
        if lib.espeak_SetVoiceByName(b'en')!=0:raise RuntimeError('English voice unavailable.')
        raw=text.encode('utf-8')+b'\0'
        if lib.espeak_Synth(raw,len(raw),0,1,0,1,None,None)!=0:raise RuntimeError('Speech synthesis failed.')
    finally:lib.espeak_Terminate()
    pcm=b''.join(chunks)
    if not pcm:raise RuntimeError('Speech engine returned no audio.')
    wav=directory/'speech.wav';mp3=directory/'speech.mp3'
    with wave.open(str(wav),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(pcm)
    encode_mp3(pcm,rate,mp3)
    (directory/'text.txt').write_text(text,encoding='utf-8')
    result={'wav':str(wav.resolve()),'mp3':str(mp3.resolve()),'seconds':round(len(pcm)/(2*rate),2),'engine':'eSpeak NG (local)','robot_played':False}
    (directory/'metadata.json').write_text(json.dumps(result,indent=2))
    return result

def encode_mp3(pcm,rate,path):
    name=ctypes.util.find_library('mp3lame')
    if not name:raise RuntimeError('MP3 encoder unavailable.')
    lib=c.CDLL(name);lib.lame_init.restype=c.c_void_p
    handle=lib.lame_init()
    if not handle:raise RuntimeError('Cannot initialize MP3 encoder.')
    lib.lame_close.argtypes=[c.c_void_p]
    try:
        for method,value in [('lame_set_num_channels',1),('lame_set_in_samplerate',rate),('lame_set_out_samplerate',44100),('lame_set_brate',128),('lame_set_mode',3)]:
            fn=getattr(lib,method);fn.argtypes=[c.c_void_p,c.c_int]
            if fn(handle,value)<0:raise RuntimeError('Invalid MP3 encoder configuration.')
        lib.lame_init_params.argtypes=[c.c_void_p]
        if lib.lame_init_params(handle)<0:raise RuntimeError('MP3 initialization failed.')
        count=len(pcm)//2; samples=(c.c_short*count).from_buffer_copy(pcm)
        size=int(1.25*count)+7200;buffer=(c.c_ubyte*size)()
        lib.lame_encode_buffer.argtypes=[c.c_void_p,c.POINTER(c.c_short),c.POINTER(c.c_short),c.c_int,c.POINTER(c.c_ubyte),c.c_int]
        n=lib.lame_encode_buffer(handle,samples,samples,count,buffer,size)
        if n<0:raise RuntimeError('MP3 encoding failed.')
        encoded=bytes(buffer[:n]);lib.lame_encode_flush.argtypes=[c.c_void_p,c.POINTER(c.c_ubyte),c.c_int]
        n=lib.lame_encode_flush(handle,buffer,size)
        if n<0:raise RuntimeError('MP3 completion failed.')
        Path(path).write_bytes(encoded+bytes(buffer[:n]))
    finally:lib.lame_close(handle)

if __name__=='__main__':
    if len(sys.argv)!=3 or sys.argv[1]!='--worker':raise SystemExit('Internal speech worker only')
    print(json.dumps(generate_files(sys.stdin.read(),sys.argv[2])))
