"""Preset-only Gemini TTS. No voice cloning or microphone samples are used."""
import base64,io,json,uuid,wave
from pathlib import Path
from . import gemini_api,speech
VOICES=('Kore','Puck','Charon','Aoede','Fenrir','Leda')
STYLES={'neutral':'Clear, conversational and natural.','cheerful':'Cheerful and warm, without shouting.',
        'encouraging':'Warm, encouraging and supportive.','calm':'Calm, gentle and measured.',
        'serious':'Respectful, steady and serious.'}
MODEL='gemini-3.8-flash-tts'

def synthesize(text,directory,*,key,voice='Kore',style='neutral',model=MODEL):
    text=speech.validate_text(text)
    if voice not in VOICES or style not in STYLES:raise ValueError('Choose a preset voice and delivery style.')
    body={'contents':[{'role':'user','parts':[{'text':text,'speech_metadata':{'style':STYLES[style]}}]}],
          'generationConfig':{'responseModalities':['AUDIO'],'speechConfig':{'voiceConfig':{'voice':voice}}}}
    candidate=gemini_api.generate(body,key,model,timeout=90)
    chunks=[p['inlineData'] for p in candidate.get('content',{}).get('parts',[]) if 'inlineData' in p]
    if len(chunks)!=1:raise ValueError('TTS returned no single audio recording.')
    blob=base64.b64decode(chunks[0]['data'],validate=True);mime=chunks[0].get('mimeType','')
    if blob.startswith(b'RIFF'):
        with wave.open(io.BytesIO(blob),'rb') as wav:
            if wav.getnchannels()!=1 or wav.getsampwidth()!=2 or wav.getcomptype()!='NONE':raise ValueError('Unsupported TTS WAV format.')
            rate=wav.getframerate();pcm=wav.readframes(wav.getnframes())
    elif mime.lower().startswith('audio/l16') and 'rate=24000' in mime.lower():rate=24000;pcm=blob
    else:raise ValueError('Unsupported TTS audio format; nothing uploaded.')
    if not 8000<=rate<=48000 or len(pcm)%2 or not 0<len(pcm)<=rate*2*180:raise ValueError('Invalid TTS audio duration.')
    folder=Path(directory)/uuid.uuid4().hex;folder.mkdir(parents=True)
    wav_path=folder/'speech.wav';mp3=folder/'speech.mp3'
    with wave.open(str(wav_path),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(pcm)
    speech.encode_mp3(pcm,rate,mp3)
    result={'wav':str(wav_path),'mp3':str(mp3),'seconds':len(pcm)/(2*rate),'engine':'Gemini TTS','voice':voice,'style':style,'robot_played':False}
    (folder/'metadata.json').write_text(json.dumps(result,indent=2));(folder/'text.txt').write_text(text)
    return result
