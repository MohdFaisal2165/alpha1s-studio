"""Inline speech workflow: text, verified upload, reconnect, one playback."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import queue
import threading
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk
from .speech import synthesize
from .robot_speech import new_job, prepare_upload, play_job

ROOT=Path(__file__).resolve().parents[1]

class SpeechPanel:
    def __init__(self,notebook,owner=None):
        self.cancel_event=threading.Event()
        self.owner=owner;self.active=False;self.phase='idle';self.job=None
        self.pool=ThreadPoolExecutor(max_workers=1);self.future=None;self.player=None
        self.clip=None;self.generated_text=None;self.messages=queue.Queue()
        self.page=ttk.Frame(notebook);notebook.add(self.page,text='Voice')
        self.canvas=tk.Canvas(self.page,bg='#101827',highlightthickness=0)
        scrollbar=ttk.Scrollbar(self.page,orient='vertical',command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.frame=ttk.Frame(self.canvas,padding=22)
        item=self.canvas.create_window((0,0),window=self.frame,anchor='nw')
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(item,width=e.width))
        self.frame.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        ttk.Label(self.frame,text='Choose Alpha’s voice',font=('DejaVu Sans',20,'bold')).pack(anchor='w')
        ttk.Label(self.frame,text='Choose the voice for new speech and conversation replies. Try a message, then continue to Greetings. Automatic delivery lets Gemini choose the tone in Conversation.',style='Muted.TLabel',wraplength=950).pack(anchor='w',pady=(6,18))
        self.text=tk.Text(self.frame,height=5,bg='#18263b',fg='#e5edf8',insertbackground='#38dbc0',font=('DejaVu Sans',14),wrap='word',relief='flat',padx=16,pady=14)
        self.text.pack(fill='x');self.text.insert('1.0','Hello! Welcome to Alpha 1S Studio.')
        self.text.bind('<<Modified>>',self.edited);self.text.edit_modified(False)
        from .expressive_voice import VOICES,STYLES
        voices=ttk.Frame(self.frame);voices.pack(fill='x',pady=10)
        self.voice=tk.StringVar(value='Kore');self.delivery=tk.StringVar(value='Automatic')
        ttk.Label(voices,text='Voice').pack(side='left')
        ttk.Combobox(voices,textvariable=self.voice,values=('Local',)+VOICES,state='readonly',width=12).pack(side='left',padx=8)
        ttk.Label(voices,text='Delivery').pack(side='left')
        ttk.Combobox(voices,textvariable=self.delivery,values=('Automatic',)+tuple(STYLES),state='readonly',width=14).pack(side='left',padx=8)
        row=ttk.Frame(self.frame);row.pack(fill='x',pady=18)
        self.robot_button=ttk.Button(row,text='Send to robot',style='Accent.TButton',command=self.send);self.robot_button.pack(side='left')
        self.generate=ttk.Button(row,text='Computer preview',command=self.start);self.generate.pack(side='left',padx=8)
        self.stop_button=ttk.Button(row,text='Stop preview',command=self.stop,state='disabled');self.stop_button.pack(side='left')
        ttk.Checkbutton(self.frame,text='Robot supported • joints clear • switch ready',variable=owner.ready).pack(anchor='w',pady=8)
        ttk.Label(self.frame,text='Voices such as Charon use Gemini speech generation and its quota, even outside Conversation. Choose Local for offline speech.',style='Muted.TLabel').pack(anchor='w')
        ttk.Separator(self.frame).pack(fill='x',pady=18)
        self.status=tk.StringVar(value='New messages need USB once. The same saved message can replay wirelessly.')
        ttk.Label(self.frame,textvariable=self.status,wraplength=630,font=('DejaVu Sans',12)).pack(anchor='w',pady=8)
        self.progress=ttk.Progressbar(self.frame,mode='indeterminate');self.progress.pack(fill='x',pady=8)
        self.reconnect=ttk.Button(self.frame,text='USB unplugged — Speak',style='Accent.TButton',command=self.speak,state='disabled')
        self.reconnect.pack(anchor='w',pady=8)
        self.cancel=ttk.Button(self.frame,text='Finish without speaking',command=self.finish,state='disabled');self.cancel.pack(anchor='w')
        ttk.Label(self.frame,text='Playback uses the robot speaker over Bluetooth. Unplug USB after uploading.\nComputer preview is optional. Linux may ask permission to write new audio to the card.',wraplength=630,style='Muted.TLabel').pack(anchor='w',pady=16)
        self.files=tk.StringVar();ttk.Label(self.frame,textvariable=self.files,wraplength=630,style='Muted.TLabel').pack(anchor='w')

    def voice_settings(self):
        from .expressive_voice import MODEL
        return {'voice':self.voice.get(),'style':'neutral' if self.delivery.get()=='Automatic' else self.delivery.get(),'key':self.owner.teacher.key.get(),
                'model':self.owner.teacher.tts_model.get() if hasattr(self.owner.teacher,'tts_model') else MODEL}
    def synthesize_voice(self,text,settings):
        if settings['voice']=='Local':return synthesize(text,ROOT/'data/speech')
        from .expressive_voice import synthesize as expressive
        return expressive(text,ROOT/'data/speech',**settings)
    def current_text(self): return self.text.get('1.0','end-1c').strip()
    def edited(self,event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            if self.generated_text!=self.current_text(): self.clip=None
    def controls(self):
        busy=self.future is not None or self.active
        self.robot_button.configure(state='disabled' if busy else 'normal')
        self.generate.configure(state='disabled' if busy else 'normal')
        self.text.configure(state='disabled' if busy else 'normal')
        waiting=self.phase=='reconnect' and self.future is None
        self.reconnect.configure(state='normal' if waiting else 'disabled')
        self.cancel.configure(state='normal' if waiting else 'disabled')
    def acquire(self, *, storage_only=False):
        if self.owner is None: raise ValueError('Robot controls are unavailable in this preview')
        if not storage_only and not self.owner.ready.get(): raise ValueError('Tick “Supported • joints clear • switch ready” first.')
        if self.owner.future is not None or self.owner.greeting_active:
            raise ValueError('Wait for the current request to finish.')
        if getattr(self.owner.robot,'connected',False):self.owner.robot.disconnect()
        if not self.owner.robot.lock.acquire(blocking=False):
            raise ValueError('Wait for the current motor request to finish.')
        self.active=True;self.owner.speech_active=True
        self.owner.invalidate('Speech in progress • motor controls locked')
    def release(self):
        if self.active:
            self.active=False;self.owner.speech_active=False;self.owner.robot.lock.release()
            self.owner.invalidate('Disarmed • Connect and read joints again before moving motors')
    def start(self):
        if self.future is not None or self.active:return
        self.stop();self.generated_text=self.current_text();self.phase='preview'
        self.status.set('Preparing computer preview…');self.progress.start(15)
        settings=self.voice_settings()
        self.future=self.pool.submit(self.synthesize_voice,self.generated_text,settings)
        self.controls();self.frame.after(100,self.poll)
    def send(self):
        if self.future is not None or self.active:return
        from .speech import validate_text
        try:
            if not self.owner.ready.get():raise ValueError('Tick “Supported • joints clear • switch ready” first.')
            text=validate_text(self.current_text())
            from .greetings import saved_audio
            from . import conversation_speech
            settings=self.voice_settings()
            cached=any(item['text'].strip()==text and item.get('voice','Local')==settings['voice'] and item.get('style','neutral')==settings['style'] for item in saved_audio().values())
            if not cached and not conversation_speech.alpha_usb_present():
                raise ValueError('New message: connect USB to upload it once, then unplug for playback.')
            self.acquire();self.cancel_event.clear()
        except Exception as exc:self.status.set(str(exc));return
        if cached:
            self.job=None
            self.phase='play';self.status.set('Replaying the saved message through Alpha’s speaker…');self.progress.start(15)
            self.future=self.pool.submit(conversation_speech.replay_saved,text,self.cancel_event,voice=settings['voice'],style=settings['style'])
            self.controls();self.frame.after(100,self.poll);return
        self.stop();self.generated_text=text;self.phase='upload';self.job=None
        self.status.set('Generating your message…');self.files.set('');self.progress.start(15)
        clip=None  # Generate the explicitly selected voice/style; no stale preview reuse.
        def work():
            audio=self.synthesize_voice(text,settings)
            job=new_job(audio,text)
            job['temporary']=True
            from .robot_speech import save_job
            save_job(job)
            return prepare_upload(job,self.messages.put),audio
        self.future=self.pool.submit(work);self.controls();self.frame.after(100,self.poll)
    def speak(self):
        if self.phase!='reconnect' or self.future is not None:return
        if not self.owner.ready.get():
            self.status.set('Support the robot and tick the support checkbox before speaking.');return
        self.phase='play';self.status.set('Checking connection and sending one playback request…');self.progress.start(15)
        from .conversation_speech import play_uploaded,alpha_usb_present
        if alpha_usb_present():
            self.phase='reconnect';self.progress.stop();self.status.set('Unplug USB and leave it unplugged, then click Speak.');return
        self.future=self.pool.submit(play_uploaded,self.job,self.cancel_event);self.controls();self.frame.after(100,self.poll)
    def poll(self):
        while not self.messages.empty():self.status.set(self.messages.get_nowait())
        if self.future is None:return
        if not self.future.done():self.frame.after(100,self.poll);return
        future=self.future;self.future=None;self.progress.stop()
        try:
            result=future.result()
            if self.phase=='preview':
                self.clip=result;self.play();self.phase='idle'
            elif self.phase=='upload':
                self.job,self.clip=result;self.phase='reconnect'
                self.status.set('Audio saved and verified. Unplug USB and leave it unplugged, then click “USB unplugged — Speak”.')
                self.files.set('Saved on robot: '+self.job['name']+'.MP3')
            elif self.phase=='delete':
                self.status.set('Selected recordings permanently deleted from the robot. No playback sent.')
                self.phase='idle';self.release()
            elif self.phase=='play':
                self.status.set('Playback accepted • listen to the robot. You can send another message when it finishes.')
                self.phase='idle';self.release()
        except Exception as exc:
            if self.phase=='play' and self.job and not self.job.get('playback_attempted'):
                self.phase='reconnect'
                self.status.set('Robot not ready. Unplug USB and leave it unplugged, then try Speak. '+str(exc))
            else:
                self.phase='idle';self.release()
                self.status.set('Stopped: '+str(exc)+' No automatic retry was sent.')
        self.controls()
    def finish(self):
        if self.phase!='reconnect' or self.future is not None:return
        self.phase='idle';self.release();self.controls()
        self.status.set('Audio remains on the card; no playback sent. Unplug USB for Bluetooth replay.')
    def play(self):
        if not self.clip:return
        self.stop();player=shutil.which('aplay')
        if not player:self.status.set('Computer preview player is unavailable.');return
        try:self.player=subprocess.Popen([player,'-q',self.clip['wav']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError as exc:self.status.set(str(exc));return
        self.status.set('Previewing on computer speakers');self.stop_button.configure(state='normal');self.frame.after(100,self.poll_player)
    def poll_player(self):
        if self.player is None:return
        code=self.player.poll()
        if code is None:self.frame.after(100,self.poll_player);return
        self.player=None;self.stop_button.configure(state='disabled');self.status.set('Preview finished' if code==0 else 'Computer preview failed')
    def stop(self):
        if self.player and self.player.poll() is None:self.player.terminate()
        self.player=None;self.stop_button.configure(state='disabled')
    def close(self):
        self.stop();self.release();self.pool.shutdown(wait=False,cancel_futures=True)
