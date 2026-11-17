"""Conversation UI. Recording and all physical actions require explicit UI controls."""
import os,threading,time,queue
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk
from . import teacher,action_library,conversation_speech,credentials

class TeacherPanel:
    def __init__(self,notebook,owner):
        self.owner=owner;self.pool=ThreadPoolExecutor(max_workers=1);self.future=None;self.cancel=threading.Event();self.record_finished=threading.Event()
        self.messages=queue.Queue()
        self.last_job=None
        self.history=[];self.answer=None;self.audio=None;self.mode='';self.last_rehearsed=None
        self.page=ttk.Frame(notebook);notebook.add(self.page,text='Conversation')
        self.canvas=tk.Canvas(self.page,bg='#101827',highlightthickness=0)
        scroll=ttk.Scrollbar(self.page,orient='vertical',command=self.canvas.yview);self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');self.canvas.pack(side='left',fill='both',expand=True)
        f=ttk.Frame(self.canvas,padding=22);item=self.canvas.create_window((0,0),window=f,anchor='nw')
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(item,width=e.width));f.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.frame=f
        top=ttk.Frame(f);top.pack(fill='x')
        ttk.Label(top,text='Conversation',font=('DejaVu Sans',24,'bold')).pack(side='left')
        ttk.Button(top,text='Settings',command=self.toggle_settings).pack(side='right')
        ttk.Label(f,text='Type or record a question → Ask Alpha → upload → unplug → speech + library gesture together.',style='Muted.TLabel').pack(anchor='w',pady=(4,12))
        ttk.Label(f,text='Session conversation',style='Muted.TLabel').pack(anchor='w')
        self.transcript_frame=ttk.Frame(f);self.transcript_frame.pack(fill='both',expand=True)
        self.transcript=tk.Text(self.transcript_frame,height=7,bg='#18263b',fg='#e5edf8',wrap='word',font=('DejaVu Sans',12),padx=12,pady=12,state='disabled');self.transcript.pack(side='left',fill='both',expand=True)
        self.transcript_scroll=ttk.Scrollbar(self.transcript_frame,orient='vertical',command=self.transcript.yview)
        self.transcript_scroll.pack(side='right',fill='y');self.transcript.configure(yscrollcommand=self.transcript_scroll.set)
        self.add('Alpha','Ask me how robots work, introduce a participant, or challenge me with a follow-up question.')
        self.question=tk.StringVar()
        input_row=tk.Frame(f,bg='#18263b',highlightthickness=1,highlightbackground='#40516a',highlightcolor='#2dd4bf');input_row.pack(fill='x',pady=10)
        self.question_entry=entry=tk.Entry(input_row,textvariable=self.question,font=('DejaVu Sans',12),bg='#18263b',fg='#e5edf8',insertbackground='#e5edf8',relief='flat',borderwidth=0,highlightthickness=0);entry.pack(side='left',fill='x',expand=True,padx=(12,4),pady=11)
        self.placeholder=tk.Label(entry,text='Type your question here…',fg='#7d8da3',bg='#18263b',font=('DejaVu Sans',10),cursor='xterm',borderwidth=0,padx=0,pady=0)
        self.placeholder.bind('<Button-1>',lambda e:entry.focus_set())
        self.question.trace_add('write',lambda *args:self.refresh_placeholder())
        entry.bind('<FocusIn>',lambda e:self.placeholder.place_forget())
        entry.bind('<FocusOut>',lambda e:self.refresh_placeholder())
        self.refresh_placeholder()
        entry.bind('<Return>',lambda e:self.ask(force_gesture=True))
        self.mic_image=self.microphone_image()
        self.stop_image=tk.PhotoImage(width=24,height=24);self.stop_image.put('#2dd4bf',to=(6,6,18,18))
        self.mic_button=tk.Button(input_row,image=self.mic_image,command=self.record,bg='#18263b',activebackground='#24364d',relief='flat',borderwidth=0,highlightthickness=0,padx=10,pady=6,cursor='hand2',takefocus=True)
        self.mic_button.pack(side='right',padx=(4,4),pady=3)
        row=ttk.Frame(f);row.pack(fill='x')
        self.ask_button=ttk.Button(row,text='Ask Alpha',style='Accent.TButton',command=lambda:self.ask(force_gesture=True));self.ask_button.pack(side='left')
        self.perform_button=ttk.Button(row,text='Replay reply',command=self.perform)
        self.sources_button=ttk.Button(row,text='View sources',command=self.show_sources)
        ttk.Button(row,text='Stop',style='Danger.TButton',command=self.stop).pack(side='right')
        self.support=tk.BooleanVar();self.auto=tk.BooleanVar(value=True);self.full_body=self.support
        ttk.Checkbutton(f,text='Robot secured • all limbs and movement path clear',variable=self.support).pack(anchor='w',pady=10)
        from .expressive_voice import MODEL
        self.voice=owner.speech.voice;self.delivery=owner.speech.delivery
        self.web_search=tk.BooleanVar(value=False)
        ttk.Checkbutton(f,text='Web search • current facts (requires available search quota)',variable=self.web_search).pack(anchor='w',pady=4)
        self.status=tk.StringVar(value='Type a question or use the microphone. Set up your key in Settings.')
        ttk.Label(f,textvariable=self.status,wraplength=1000,font=('DejaVu Sans',11,'bold')).pack(anchor='w',pady=6)
        self.progress=ttk.Progressbar(f,mode='indeterminate');self.progress.pack(fill='x')
        ttk.Label(f,text='Questions and microphone recordings go to Google. Fresh robot speech needs USB upload, then unplugging. Stop blocks later commands; use the power switch for motion already playing.',style='Muted.TLabel',wraplength=1000).pack(anchor='w',pady=10)
        self.settings=ttk.Frame(f,padding=(0,10))
        self.key=tk.StringVar(value=os.environ.get('GEMINI_API_KEY',''));self.model=tk.StringVar(value=os.environ.get('GEMINI_MODEL','gemini-3.5-flash-lite'))
        for label,var,mask in [('Gemini API key',self.key,'•'),('Gemini model ID',self.model,'')]:
            ttk.Label(self.settings,text=label,style='Muted.TLabel').pack(anchor='w');ttk.Entry(self.settings,textvariable=var,show=mask).pack(fill='x',pady=3)
        keyrow=ttk.Frame(self.settings);keyrow.pack(fill='x',pady=6)
        for label,action in [('Save key securely','save'),('Use saved key','load'),('Forget saved key','forget')]:
            ttk.Button(keyrow,text=label,command=lambda a=action:self.key_action(a)).pack(side='left',padx=(0,6))
        self.key_status=tk.StringVar(value='Session only until saved to the system password vault.')
        ttk.Label(self.settings,textvariable=self.key_status,style='Muted.TLabel').pack(anchor='w')
        self.tts_model=tk.StringVar(value=MODEL)
        ttk.Label(self.settings,text='Preset voice model',style='Muted.TLabel').pack(anchor='w')
        ttk.Entry(self.settings,textvariable=self.tts_model).pack(fill='x',pady=3)
        ttk.Label(self.settings,text='Uploads: authorize once per Studio session. Closing Studio ends authorization.',style='Muted.TLabel').pack(anchor='w')
        self.key_future=None
        ttk.Button(self.settings,text='Clear conversation',command=self.clear).pack(anchor='w',pady=8)
        ttk.Button(f,text='Gesture library ▾',command=self.toggle_library).pack(anchor='w',pady=8)
        self.library=ttk.Frame(f)
        self.library_key=tk.StringVar(value='celebrate')
        self.library_items={item['key']:item for item in action_library.browse()}
        self.library_labels={f"{item['title']} · {item['seconds']:.1f}s · {item['path'].split('/')[-2]}":item['key'] for item in self.library_items.values()}
        self.library_choice=tk.StringVar()
        self.short_actions=tk.BooleanVar(value=True)
        ttk.Checkbutton(self.library,text='Short actions only (up to 6 seconds)',variable=self.short_actions,command=self.filter_library).pack(anchor='w',pady=6)
        self.library_select=ttk.Combobox(self.library,textvariable=self.library_choice,state='readonly',width=58);self.library_select.pack(anchor='w');self.library_select.bind('<<ComboboxSelected>>',lambda e:self.select_library())
        self.meaning=tk.StringVar()
        ttk.Label(self.library,text='Use this gesture when…',style='Muted.TLabel').pack(anchor='w',pady=(10,2))
        ttk.Entry(self.library,textvariable=self.meaning).pack(fill='x')
        self.library_info=tk.StringVar();ttk.Label(self.library,textvariable=self.library_info,wraplength=1000).pack(anchor='w',pady=8)
        ttk.Checkbutton(self.library,text='Full-body action: robot secured, all limbs and surrounding space clear',variable=self.full_body).pack(anchor='w')
        row=ttk.Frame(self.library);row.pack(fill='x',pady=8)
        self.rehearse_button=ttk.Button(row,text='Rehearse on robot',command=self.rehearse);self.rehearse_button.pack(side='left')
        self.approve_button=ttk.Button(row,text='Save for Gemini',command=self.approve);self.approve_button.pack(side='left',padx=8)
        self.test_button=ttk.Button(row,text='Test Celebrate + speech',command=self.test_combined);self.test_button.pack(side='left',padx=8)
        self.filter_library()
        if not self.key.get():self.frame.after(300,lambda:self.key_action('load',automatic=True))
    def key_action(self,action,automatic=False):
        if self.key_future is not None or self.future is not None:return
        value=self.key.get()
        work=(lambda:credentials.save(value)) if action=='save' else credentials.load if action=='load' else credentials.forget
        self.key_future=self.pool.submit(work)
        def finish():
            if not self.key_future.done():self.frame.after(100,finish);return
            future=self.key_future;self.key_future=None
            try:
                result=future.result()
                if action=='load':
                    if result and (not automatic or not self.key.get()):self.key.set(result)
                    self.key_status.set('Saved key loaded.' if result else 'No saved key. Paste once, then Save key securely.')
                elif action=='forget':self.key.set('');self.key_status.set('Saved key removed.')
                else:self.key_status.set('Saved in your system password vault. It will load next time.')
            except Exception as e:self.key_status.set(str(e))
        self.frame.after(100,finish)
    def add(self,who,text):
        self.transcript.configure(state='normal');self.transcript.insert('end',who+': '+text+'\n\n');self.transcript.see('end');self.transcript.configure(state='disabled')
    def toggle_settings(self):
        if self.settings.winfo_manager():self.settings.pack_forget()
        else:self.settings.pack(fill='x',before=self.transcript_frame)
    def toggle_library(self):
        if self.library.winfo_manager():self.library.pack_forget()
        else:
            self.library.pack(fill='x');self.frame.update_idletasks();self.canvas.yview_moveto(1)
    def clear(self):
        if self.future is not None:return
        self.history=[];self.answer=None
        self.perform_button.pack_forget();self.sources_button.pack_forget()
        if self.audio:self.audio.unlink(missing_ok=True);self.audio=None
        self.transcript.configure(state='normal');self.transcript.delete('1.0','end');self.transcript.configure(state='disabled');self.status.set('Conversation cleared.')
    def filter_library(self):
        labels=[label for label,key in self.library_labels.items() if not self.short_actions.get() or self.library_items[key]['seconds']<=6]
        self.library_select.configure(values=labels)
        if self.library_choice.get() not in labels:self.library_choice.set(labels[0] if labels else '')
        self.select_library()
    def select_library(self):
        key=self.library_labels.get(self.library_choice.get())
        if key:self.library_key.set(key)
        self.inspect()
    def inspect(self):
        try:
            item=action_library.inspect(self.library_key.get())
            approval=action_library.approvals().get(item['key'])
            enabled=action_library.approval_hash(approval)==item['sha256'] and item['conversation_candidate']
            self.meaning.set(approval.get('meaning',item['meaning']) if isinstance(approval,dict) else item['meaning'])
            purpose='Enabled for Gemini' if enabled else 'Rehearse, then enable for Gemini' if item['conversation_candidate'] else 'Rehearsal only • not offered to Gemini'
            music='Matching music file found' if item['has_music'] else 'No matching music file found'
            self.library_info.set(f"{item['seconds']:.1f} seconds • Full body • {music}\n{purpose}. Conversation pairs this approved gesture with your selected voice.")
        except FileNotFoundError:self.library_info.set('Optional native actions are not imported. Bring your own verified robot-card library; no vendor actions are included.')
        except Exception as e:self.library_info.set(str(e))
    def begin(self,mode,work):
        if self.future is not None or self.key_future is not None or self.owner.future is not None or self.owner.greeting_active or self.owner.speech_active:
            self.status.set('Another action or password-vault request is running. Please wait.');return False
        while not self.messages.empty():self.messages.get_nowait()
        self.cancel.clear();self.mode=mode;self.owner.greeting_active=True;self.owner.update_controls();self.progress.start(15)
        if mode=='rehearse':self.owner.robot.armed.set()
        self.future=self.pool.submit(work)
        for b in (self.ask_button,self.mic_button,self.perform_button,self.rehearse_button,self.approve_button,self.test_button):b.configure(state='disabled')
        self.frame.after(100,self.poll)
        return True
    def microphone_image(self):
        # Pixel-drawn icon avoids missing emoji glyphs on Linux desktop fonts.
        icon=tk.PhotoImage(width=24,height=24)
        for y in range(24):
            for x in range(24):
                capsule=(9<=x<=14 and 5<=y<=12) or ((x-11.5)**2+(y-5)**2<=9 and y<=5) or ((x-11.5)**2+(y-12)**2<=9 and y>=12)
                cradle=(x in (6,7,16,17) and 10<=y<=13) or (y in (15,16) and 8<=x<=15) or (x in (7,8,15,16) and y==14)
                stand=(x in (11,12) and 17<=y<=20) or (y in (20,21) and 8<=x<=15)
                if capsule or cradle or stand:icon.put('#9aadc4',(x,y))
        return icon

    def refresh_placeholder(self):
        if not self.question.get() and self.question_entry.focus_get()!=self.question_entry:
            self.placeholder.place(x=0,rely=.5,anchor='w')
        else:self.placeholder.place_forget()

    def record(self):
        if self.future is not None:
            if self.mode=='record':
                self.record_finished.set();self.mic_button.configure(state='disabled')
                self.status.set('Finishing the recording…')
            return
        try:
            if not self.key.get().strip() or not self.model.get().strip():
                raise ValueError('Enter your Gemini API key and model in Settings before speaking.')
            self.record_finished.clear()
            if self.begin('record',lambda:teacher.record(self.cancel,self.record_finished)):
                self.mic_button.configure(image=self.stop_image,state='normal')
                self.status.set('Listening to your computer microphone… Click the microphone again to finish; maximum 15 seconds. Google transcribes it for review.')
        except Exception as e:self.status.set(str(e))
    def ask_and_perform(self):
        if self.question.get().strip() or self.audio:self.ask(force_gesture=True)
        else:self.perform()
    def ask(self,force_gesture=False):
        if self.future is not None:return
        try:
            catalog=action_library.choices();text=self.question.get();audio=None if text.strip() else self.audio;history=list(self.history);key=self.key.get();model=self.model.get()
            if not key.strip() or not model.strip():raise ValueError('Enter your Gemini API key and model in Settings.')
            teacher.build_request(text,audio,history,catalog)
            require_gesture=bool(force_gesture or self.auto.get())
            self.catalog=catalog;self.auto_turn=require_gesture;self.status.set('Gemini is thinking…')
            web_search=self.web_search.get()
            self.begin('ask',lambda:teacher.ask(text,audio,history,catalog,key,model,web_search=web_search,require_gesture=require_gesture))
        except Exception as e:self.status.set(str(e))
    def check_speech_ready(self):
        if not conversation_speech.bluetooth_address():raise ValueError('Configure your paired Bluetooth address before fresh speech.')
        if not self.support.get():raise ValueError('Confirm the robot is supported and clear first.')
        if not conversation_speech.alpha_usb_present():
            raise ValueError('Fresh replies need a USB upload. Connect USB; unplug when the app asks.')
    def perform(self):
        if self.future is not None or self.owner.future is not None or self.owner.greeting_active or self.owner.speech_active:
            self.status.set('Another action is running. Please wait.');return
        try:
            if not self.answer:raise ValueError('Ask Alpha first.')
            if not self.support.get():raise ValueError('Confirm the robot is supported and clear first.')
            sentence=teacher.spoken_sentence(self.answer['answer'])
            selected=self.answer['gesture'];current=action_library.choices()
            if selected not in current:raise ValueError('Selected gesture is no longer available. Ask Alpha again.')
            gesture=current[selected] if selected!='none' else None
            if gesture and gesture.get('profile') and len(gesture['profile']['pose'])==16 and not self.owner.legs_ready.get():raise ValueError('This greeting uses legs: confirm legs unloaded in Pose Studio first.')
            if selected.startswith('library:') and not self.full_body.get():
                raise ValueError('Confirm all 16 joints are clear before playing the selected library action.')
            if gesture and self.catalog.get(selected,{}).get('sha256')!=gesture.get('sha256'):
                raise ValueError('Selected action changed. Ask Alpha again.')
            if getattr(self.owner.robot,'connected',False):self.owner.robot.disconnect()
            self.status.set('Preparing speech and the selected gesture…')
            settings={'voice':self.voice.get(),'style':self.answer.get('tone','neutral') if self.delivery.get()=='Automatic' else self.delivery.get(),
                      'key':self.key.get(),'model':self.tts_model.get()}
            cached=conversation_speech.has_saved(sentence,settings['voice'],settings['style'],gesture)
            if cached and not conversation_speech.alpha_usb_present():
                self.begin('speak',lambda:conversation_speech.replay_response(sentence,self.cancel,gesture,settings))
            else:
                self.check_speech_ready()
                self.begin('speak',lambda:conversation_speech.speak_fresh(sentence,self.cancel,self.messages.put,gesture=gesture,voice_settings=settings))
        except Exception as e:self.status.set(str(e))
    def save_response(self):
        if self.future is not None:self.status.set('Wait for playback to finish before saving.');return
        try:
            if not self.last_job:raise ValueError('Play a response first, then save it.')
            from .recording_store import update
            update(self.last_job['name'],keep=True)
            self.status.set('Response saved. Automatic cleanup will keep it.')
        except Exception as e:self.status.set(str(e))
    def show_sources(self):
        if not self.answer:self.status.set('Ask a question first.');return
        from .search_sources import show
        show(self.answer)
    def test_combined(self):
        if self.future is not None:return
        self.catalog=action_library.choices()
        if 'library:celebrate' not in self.catalog:self.status.set('Authorize Celebrate in the library first.');return
        self.answer={'answer':'Well done, that is a wonderful achievement!','gesture':'library:celebrate','tone':'cheerful','reason':'Direct combined-playback test','heard':'Test Celebrate'}
        self.add('Test',self.answer['answer']+' [Celebrate]')
        self.perform()
    def rehearse(self):
        if self.future is not None:return
        try:
            if not self.full_body.get():raise ValueError('Confirm full-body clearance before rehearsal.')
            if getattr(self.owner.robot,'supports_robot_speech',False) is not True:raise ValueError('Select Bluetooth first.')
            key=self.library_key.get();self.last_rehearsed=None;self.status.set('Rehearsing '+key+' on robot…')
            self.begin('rehearse',lambda:action_library.play_native(self.owner.robot,key,supported=True,rehearsal=True))
        except Exception as e:self.status.set(str(e))
    def approve(self):
        if self.future is not None:return
        try:
            item=action_library.inspect(self.library_key.get())
            if self.last_rehearsed!=(item['key'],item['sha256']) and action_library.approval_hash(action_library.approvals().get(item['key']))!=item['sha256']:raise ValueError('Rehearse this exact action, then confirm it looked correct.')
            action_library.approve(item['key'],meaning=self.meaning.get());self.inspect();self.status.set('Saved for Gemini. Speak + gesture uses this action when selected; full-body clearance is required.')
        except Exception as e:self.status.set(str(e))
    def stop(self):self.cancel.set();self.owner.robot.disarm();self.status.set('Stopped. A native action already sent may continue; use the power switch if needed.')
    def poll(self):
        while not self.messages.empty():
            message=self.messages.get_nowait()
            if not self.cancel.is_set():self.status.set(message)
        if self.future is None:return
        if not self.future.done():self.frame.after(100,self.poll);return
        future=self.future;self.future=None;self.progress.stop();self.owner.greeting_active=False;self.owner.robot.disarm();self.owner.update_controls()
        for b in (self.ask_button,self.mic_button,self.perform_button,self.rehearse_button,self.approve_button,self.test_button):b.configure(state='normal')
        self.mic_button.configure(image=self.mic_image)
        try:
            result=future.result()
            if self.cancel.is_set():
                if self.mode=='record':result.unlink(missing_ok=True)
                self.status.set('Stopped. Nothing further will run.');return
            if self.mode=='record':
                if self.audio:self.audio.unlink(missing_ok=True)
                self.audio=result;self.status.set('Transcribing your question…')
                key=self.key.get();model=self.model.get()
                self.begin('transcribe',lambda:teacher.transcribe(result,key,model))
            elif self.mode=='transcribe':
                self.question.set(result);self.question_entry.focus_set()
                if self.audio:self.audio.unlink(missing_ok=True);self.audio=None
                self.status.set('Review your question, then click Ask Alpha.')
            elif self.mode=='ask':
                self.answer=result;self.perform_button.pack(side='left',padx=8);self.history.append(result);self.history=self.history[-6:]
                self.add('You',result['heard']);self.add('Alpha',result['answer'])
                decision='Tone: '+result.get('tone','neutral')+' • Gesture: '+self.catalog[result['gesture']]['title']+' • '+result['reason']
                self.status.set(decision)
                self.add('Gemini selection' if not result.get('warning') else 'Gesture unavailable',decision)
                if result.get('sources'):
                    self.sources_button.pack(side='left',padx=8)
                    self.add('Sources', '\n'.join(s['title']+' — '+s['url'] for s in result['sources']))
                else:self.sources_button.pack_forget()
                self.question.set('')
                if self.audio:self.audio.unlink(missing_ok=True);self.audio=None
                if result.get('warning'):
                    self.add('Notice',result['warning']);self.status.set(result['warning'])
                elif self.auto_turn:self.perform()
            elif self.mode=='rehearse':
                self.last_rehearsed=(result['key'],result['sha256']);self.status.set('Action command accepted. If the rehearsal looked correct, enable it for Gemini.')
            elif self.mode=='speak':
                self.last_job=result.get('job')
                self.owner.invalidate('Speech finished • connect/read joints again before manual control')
                self.status.set(result['message'])
            else:self.status.set(str(result))
        except Exception as e:self.status.set(str(e))
    def close(self):
        self.stop();self.pool.shutdown(wait=False)
        if self.audio:self.audio.unlink(missing_ok=True)
