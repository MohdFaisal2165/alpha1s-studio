"""Explicit computer-speaker fallback; never sends robot audio/action commands."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import time
import wave
from .robot_speech import ROOT
from .greetings import saved_audio


def prepare(audio_name,root=ROOT,*,require_player=True):
    library=saved_audio(root)
    if audio_name not in library:raise ValueError('Saved audio is not verified.')
    player=shutil.which('aplay')
    if require_player and not player:raise ValueError('Computer speaker player is unavailable.')
    checksum=library[audio_name]['sha256']
    sources=list((root/'data/speech').glob('*/speech.mp3'))+list((root/'data/conversation-speech').glob('*/speech.mp3'))
    for mp3 in sources:
        if hashlib.sha256(mp3.read_bytes()).hexdigest()!=checksum:continue
        wav=mp3.with_suffix('.wav')
        if not wav.is_file():continue
        with wave.open(str(wav)) as data:
            seconds=data.getnframes()/data.getframerate()
        if not 0<seconds<=180:raise ValueError('Saved recording duration is invalid.')
        return player,wav,seconds
    raise ValueError('The local source recording is missing. Generate this message again in Speech.')


def play(prepared,armed):
    player,wav,seconds=prepared
    if not armed.is_set():raise ValueError('Stopped before speech.')
    proc=subprocess.Popen([player,'-q',str(wav)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+seconds+10
        while proc.poll() is None:
            if not armed.is_set():raise ValueError('Stopped during computer speech.')
            if time.monotonic()>deadline:raise TimeoutError('Computer audio timed out.')
            time.sleep(.05)
        if proc.returncode:raise ValueError('Computer speaker playback failed.')
        return {'status':'computer_audio_finished','pose_reset_sent':False}
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=2)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=2)
