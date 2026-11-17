"""Simple teach-a-pose greeting screen. All hardware actions start from a click."""
from concurrent.futures import ThreadPoolExecutor
import queue
import time
import tkinter as tk
from tkinter import ttk
from . import pose_greetings as poses,greetings

class GreetingPanel:
    def __init__(self,notebook,owner):
        self.owner=owner;self.pool=ThreadPoolExecutor(max_workers=1);self.future=None
        self.voice_draft=None;self.audio_name=None;self.record_then_voice=False;self.pose=None;self.profiles={};self.mode='';self.messages=queue.Queue();self.stopped=False
        self.page=ttk.Frame(notebook);notebook.add(self.page,text='Greetings')
        self.canvas=tk.Canvas(self.page,bg='#101827',highlightthickness=0)
        scroll=ttk.Scrollbar(self.page,orient='vertical',command=self.canvas.yview);self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        self.frame=ttk.Frame(self.canvas,padding=24);item=self.canvas.create_window((0,0),window=self.frame,anchor='nw')
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(item,width=e.width))
        self.frame.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        f=self.frame
        ttk.Label(f,text='Save a greeting',font=('DejaVu Sans',23,'bold')).pack(anchor='w')
        ttk.Label(f,text='Combine the saved pose and voice draft. Name the person, save via USB, then unplug and play.',style='Muted.TLabel').pack(anchor='w',pady=(5,16))
        ttk.Label(f,text='Person',font=('DejaVu Sans',11,'bold')).pack(anchor='w')
        self.person=tk.StringVar(value='')
        self.person_box=ttk.Combobox(f,textvariable=self.person,font=('DejaVu Sans',14));self.person_box.pack(fill='x',pady=(4,12))
        self.person_box.bind('<<ComboboxSelected>>',lambda e:self.load_person())
        self.message_summary=tk.StringVar(value='No voice message selected. Create one in Voice.')
        ttk.Label(f,textvariable=self.message_summary,wraplength=900).pack(anchor='w',pady=10)
        editrow=ttk.Frame(f);editrow.pack(fill='x',pady=6)
        ttk.Button(editrow,text='Set / edit pose',command=lambda:owner.notebook.select(owner.pose_page)).pack(side='left')
        ttk.Button(editrow,text='Create / edit voice',command=self.edit_voice).pack(side='left',padx=8)
        self.text=tk.Text(f,height=3,bg='#18263b',fg='#e5edf8',insertbackground='#38dbc0',font=('DejaVu Sans',14),wrap='word',relief='flat',padx=12,pady=12)
        # Hidden compatibility buffer; message editing lives only in Voice.
        self.speaker=tk.StringVar(value='Robot speaker — Bluetooth')
        self.speaker_box=ttk.Combobox(f,textvariable=self.speaker,state='readonly',values=['Robot speaker — Bluetooth'])
        self.speaker_box.configure(width=44)  # Only robot speaker is supported; no redundant selector.
        self.voice_note=tk.StringVar()
        ttk.Label(f,textvariable=self.voice_note,style='Muted.TLabel').pack(anchor='w',pady=(0,5))
        self.configure_speaker()
        self.connect_button=ttk.Button(f,text='Connect',command=self.connect_robot)
        self.connect_button.pack(anchor='w',pady=4)
        self.support=ttk.Checkbutton(f,text='Robot and both arms supported • movement path clear',variable=owner.ready,command=owner.readiness_changed)
        self.support.pack(anchor='w',pady=6)
        self.pose_info=tk.StringVar(value='No pose recorded yet.')
        ttk.Label(f,textvariable=self.pose_info,style='Muted.TLabel',wraplength=900).pack(anchor='w',pady=6)
        row=ttk.Frame(f);row.pack(fill='x',pady=10)
        self.record_button=ttk.Button(row,text='1  Record pose',style='Accent.TButton',command=self.record);# Pose capture is initiated by Pose Studio’s Next button.
        self.save_button=ttk.Button(row,text='Save greeting',command=self.save);self.save_button.pack(side='left',padx=10)
        self.play=ttk.Button(row,text='▶  Play greeting',style='Accent.TButton',command=self.execute);self.play.pack(side='left')
        self.status=tk.StringVar(value='Choose a saved person to play, or prepare a pose and voice for a new greeting.')
        self.status_label=ttk.Label(f,textvariable=self.status,font=('DejaVu Sans',12,'bold'),wraplength=950)
        self.status_label.pack(anchor='w',pady=(8,4))
        self.progress=ttk.Progressbar(f,mode='indeterminate');self.progress.pack(fill='x',pady=6)
        self.reconnect=ttk.Button(f,text='USB reconnected — Continue',command=self.confirm_reconnect)
        row=ttk.Frame(f);row.pack(fill='x',pady=8)
        self.reset_button=ttk.Button(row,text='Reset',command=self.reset_arms);self.reset_button.pack(side='left')
        self.stop_button=ttk.Button(row,text='Stop',style='Danger.TButton',command=self.stop);self.stop_button.pack(side='right')
        ttk.Label(f,text='Reset uses the measured default if saved; otherwise arms 1–6 return to 90°. Keep all moving joints supported.\nDo not force powered joints. Stop blocks the next command; use the power switch if needed.',style='Muted.TLabel',wraplength=950).pack(anchor='w',pady=6)
        try:self.profiles=poses.load();self.refresh_names();self.load_person()
        except Exception as exc:self.status.set('Could not load greetings: '+str(exc))
    def connect_robot(self):
        def connect():
            result=self.owner.robot.run()
            if result['status']!='ok':raise ValueError(result.get('error','Connection failed'))
            return result
        self.begin('connect',connect,hardware=False)

    def configure_speaker(self):
        wireless=getattr(self.owner.robot,'supports_robot_speech',False) is True
        choices=['Robot speaker — Bluetooth']
        self.speaker.set(choices[0]);self.speaker_box.configure(values=choices)
        self.voice_note.set('Wireless replay • new recordings still upload by USB.' if wireless else 'Upload by USB; then unplug and select Bluetooth to play on Alpha.')

    def current_text(self):return self.text.get('1.0','end-1c').strip()
    def refresh_names(self):self.person_box.configure(values=[p['name'] for p in self.profiles.values()])
    def load_person(self):
        if self.future is not None:return
        profile=next((p for p in self.profiles.values() if p['name'].casefold()==self.person.get().strip().casefold()),None)
        if profile:
            self.text.delete('1.0','end');self.text.insert('1.0',profile['text'])
            self.voice_draft=None;self.audio_name=profile['audio'];self.message_summary.set('Greeting for '+profile['name']+': '+profile['text'])
            self.pose=dict(profile['pose']) if profile['pose'] is not None else None
            self.show_pose();self.status.set('Saved greeting loaded. Play it, or edit the pose/message.' if self.pose else 'Message loaded. Save a pose in Pose Studio first.')
    def show_pose(self):
        self.pose_info.set('Pose recorded:  '+ '   '.join(f'{i}: {self.pose[str(i)]}°' for i in sorted(map(int,self.pose))) if self.pose else 'No pose recorded yet.')
    def controls(self):
        state='disabled' if self.future is not None else 'normal'
        for b in (self.connect_button,self.record_button,self.save_button,self.play,self.reset_button,self.person_box):b.configure(state=state)
        self.text.configure(state=state)
        self.speaker_box.configure(state='disabled' if self.future is not None else 'readonly')
    def begin(self,mode,work,hardware=True):
        if self.future is not None:
            self.status.set('Please wait for the current action to finish.')
            self.owner.status.set(self.status.get());return
        try:
            if self.owner.future is not None or self.owner.speech.active or self.owner.greeting_active:
                raise ValueError('Another robot action is running. Wait for it to finish.')
            if hardware and not self.owner.ready.get():raise ValueError('Tick “Robot and both arms supported” first.')
            self.stopped=False;self.mode=mode;self.started=time.monotonic()
            self.owner.greeting_active=True
            if mode in ('pose','reset'):
                self.status.set('Playing saved pose…' if mode=='pose' else 'Pose saved. Resetting to the stored default…')
                self.owner.status.set(self.status.get())
            if hardware:self.owner.robot.armed.set()
            self.owner.update_controls();self.progress.start(15)
            self.future=self.pool.submit(work);self.controls();self.frame.after(100,self.poll)
        except Exception as exc:
            self.status.set(str(exc));self.owner.status.set(str(exc))
    def record(self):
        if self.future is not None:return
        self.pose=None;self.show_pose()
        self.status.set('Reading the six arm angles — usually about 20–30 seconds…')
        self.begin('record',lambda:poses.capture(self.owner.robot,self.messages.put))
    def reset_arms(self):
        from .default_pose import load as load_default
        try:
            default=load_default()
            if len(default)==16 and not self.owner.legs_ready.get():raise ValueError('Confirm legs unloaded before full-body reset.')
            self.status.set('Returning to the stored default pose…')
            self.begin('reset',lambda:poses.move_to_pose(self.owner.robot,default,self.messages.put,reset=True))
        except Exception as exc:self.status.set(str(exc))
    def edit_voice(self):
        voice=self.owner.speech
        if self.current_text():
            voice.text.delete('1.0','end');voice.text.insert('1.0',self.current_text())
        item=greetings.saved_audio().get(self.audio_name,{})
        if item.get('voice'):voice.voice.set(item['voice'])
        if item.get('style'):voice.delivery.set(item['style'])
        self.owner.notebook.select(voice.page)
    def use_voice(self):
        voice=self.owner.speech
        if voice.future is None and voice.phase=='reconnect':voice.finish()
        if voice.future is not None or voice.active:
            voice.status.set('Wait for the current voice step to finish.');return
        try:
            from .speech import validate_text
            text=validate_text(voice.current_text());settings=voice.voice_settings()
            self.voice_draft={'text':text,'settings':settings}
            clip=voice.clip
            if isinstance(clip,dict) and voice.generated_text==text and clip.get('voice','Local')==settings['voice'] and clip.get('style','neutral')==settings['style']:
                self.voice_draft['clip']=dict(clip)
            self.audio_name=None
            matches=[(name,item) for name,item in greetings.saved_audio().items() if item['text'].strip()==text and item.get('voice','Local')==settings['voice'] and item.get('style','neutral')==settings['style']]
            if matches:self.audio_name=matches[-1][0]
            self.text.delete('1.0','end');self.text.insert('1.0',text)
            self.message_summary.set('Greeting message: '+text+' • '+settings['voice']+' / '+settings['style'])
            self.owner.notebook.select(self.page)
            self.status.set('Name the person and Save greeting. New audio uploads here via USB.' if self.pose else 'Save a pose in Pose Studio first.')
        except Exception as exc:voice.status.set(str(exc))
    def capture_and_continue(self):
        if self.future is not None:return
        self.record_then_voice=True
        self.owner.notebook.select(self.page)
        self.record()
    def save(self):
        try:
            name=self.person.get().strip();text=self.current_text();pose=poses.validate_pose(self.pose)
            if not name or len(name)>80:raise ValueError('Enter a person’s name (up to 80 characters).')
            audio=self.audio_name;draft=self.voice_draft
            if not audio and not draft:raise ValueError('Choose a message and voice in Voice first.')
            if not audio:
                from .conversation_speech import alpha_usb_present
                if not alpha_usb_present():raise ValueError('Connect USB to save the new greeting recording. Saving sends no movement or playback.')
                if getattr(self.owner.robot,'connected',False):self.owner.robot.disconnect()
            self.status.set('Saving pose and voice; uploading new audio if needed…')
            def work():
                selected=audio
                if not selected:
                    from .robot_speech import new_job,prepare_upload
                    clip=draft.get('clip') or self.owner.speech.synthesize_voice(text,draft['settings'])
                    job=new_job(clip,text);prepare_upload(job,self.messages.put);selected=job['name']
                return {'profiles':poses.save(name,text,pose,selected),'reconnect':not bool(audio),'audio':selected}
            self.begin('save',work,hardware=False)
        except Exception as exc:self.status.set(str(exc))
    def execute(self):
        try:
            name=self.person.get().strip()
            profile=next((p for p in self.profiles.values() if p['name'].casefold()==name.casefold()),None)
            if profile is None or profile['pose'] is None:raise ValueError('Record a pose and click Save greeting first.')
            if self.current_text()!=profile['text'].strip() or self.pose!=profile['pose']:
                raise ValueError('You changed this greeting. Click Save greeting before playing.')
            if len(profile['pose'])==16 and not self.owner.legs_ready.get():raise ValueError('Confirm legs unloaded in Pose Studio before playing this full-body greeting.')
            if getattr(self.owner.robot,'supports_robot_speech',False) is not True:
                raise ValueError('Unplug USB and select Bluetooth above to play through the robot speaker.')
            from .conversation_speech import alpha_usb_present
            if alpha_usb_present():raise ValueError('Unplug USB before Bluetooth playback.')
            speaker='robot'
            self.status.set('Moving to the saved pose, then speaking through the '+speaker.upper()+'…')
            self.begin('play',lambda:poses.play(self.owner.robot,profile,self.messages.put,speaker=speaker))
        except Exception as exc:self.status.set(str(exc))
    def stop(self):
        if self.future is not None and self.mode=='save':
            self.status.set('Let the card upload finish safely. Keep USB connected; Save does not play anything.');return
        self.stopped=True;self.owner.robot.disarm()
        self.status.set('Stopping after the current command. Keep the arms supported.')
    def confirm_reconnect(self):
        try:
            from .identify import find_device
            find_device()  # Sysfs only; does not issue a robot command.
            self.reconnect.pack_forget();self.status.set('USB ready. Click Play greeting.')
        except Exception:self.status.set('Robot not in control mode yet. Unplug USB, reconnect, then click Continue.')
    def poll(self):
        while not self.messages.empty():
            message=self.messages.get_nowait()
            if not self.stopped:
                self.status.set(message)
                if self.mode in ('pose','reset'):self.owner.status.set(message)
        if self.future is None:return
        if not self.future.done():
            if time.monotonic()-self.started>180 and self.mode in ('record','reset','play','pose'):
                self.owner.robot.disarm();self.stopped=True;self.status.set('Robot request overdue. Keep arms supported; no new commands will start.')
            self.frame.after(100,self.poll);return
        f=self.future;self.future=None;self.progress.stop()
        try:
            result=f.result()
            if self.mode=='connect':self.status.set('Robot identity verified. Saved greetings are ready to play when supported.')
            elif self.mode=='record':
                self.pose=result;self.show_pose();self.status.set('Pose recorded. Create the message in Voice, then Save greeting.')
                if self.record_then_voice:
                    self.record_then_voice=False;self.owner.notebook.select(self.owner.speech.page)
            elif self.mode=='pose':self.status.set('Saved pose commands accepted.');self.owner.status.set('Saved pose playback finished; check the robot before further movement.')
            elif self.mode=='reset':
                self.status.set('Default-pose commands accepted. Your saved pose is unchanged.')
                self.owner.status.set('Pose saved; default reset accepted. Play saved pose to check it, then Next: choose voice.')
            elif self.mode=='save':
                self.profiles=result['profiles'];self.audio_name=result.get('audio',self.audio_name);self.refresh_names()
                if result['reconnect']:
                    self.status.set('Greeting saved. Unplug USB and select Bluetooth above, then Play greeting.')

                else:self.status.set('Greeting saved. Ready to play — no upload or reconnect needed.')
            elif self.mode=='play':self.status.set('Greeting finished. No reset sent; observe that the saved pose is held.')
            if self.stopped:self.status.set('Stopped. Check the robot before starting another action.')
        except Exception as exc:
            suffix=' Saved greetings are unchanged.' if self.mode in ('play','reset') else ''
            self.status.set('Stopped: '+str(exc)+suffix)
            self.owner.status.set('Stopped: '+str(exc)+suffix)
        finally:
            self.owner.greeting_active=False
            self.owner.invalidate(self.status.get()+' • Joint editing disarmed.')
            self.controls()
    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)
