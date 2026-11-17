"""Scrollable 16-motor desktop panel. Starts disarmed; slider changes are preview only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
from .panel_transport import PanelRobot
from .bluetooth_transport import BluetoothRobot
from .speech_panel import SpeechPanel
from .greeting_panel import GreetingPanel
from .teacher_panel import TeacherPanel
from .motor_catalog import MOTORS,COMMAND_LIMITS,REVIEWED_LIMITS

class ControlPanel:
    def __init__(self,root,robot=None):
        self.root=root
        self.robot=robot or BluetoothRobot(Path(__file__).resolve().parents[1]/'reports'/'panel')
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.future=None;self.checked=False;self.holding=None;self.speech_active=False;self.greeting_active=False
        self.started=0;self.overdue=False;self.fault=False
        self.measured={};self.acknowledged={};self.dirty=set()
        root.title('Alpha 1S Studio -Pose, Voice, Greeting and Conversation')
        width=min(1320,root.winfo_screenwidth()-60);height=min(900,root.winfo_screenheight()-90)
        root.geometry(f'{width}x{height}');root.minsize(1060,700);root.configure(bg='#101827')
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('TFrame',background='#101827')
        style.configure('TLabel',background='#101827',foreground='#e5edf8',font=('DejaVu Sans',10))
        style.configure('Title.TLabel',font=('DejaVu Sans',21,'bold'))
        style.configure('Muted.TLabel',foreground='#aebed2',font=('DejaVu Sans',9))
        style.configure('Warning.TLabel',foreground='#ffd38a',font=('DejaVu Sans',10))
        style.configure('TButton',font=('DejaVu Sans',10,'bold'),padding=(14,10),background='#23344c',foreground='#e5edf8',borderwidth=0)
        style.map('TButton',background=[('active','#344b68'),('disabled','#182436')],foreground=[('disabled','#718096')])
        style.configure('Accent.TButton',background='#38dbc0',foreground='#082620')
        style.map('Accent.TButton',background=[('active','#75f0da'),('disabled','#182436')],foreground=[('disabled','#718096')])
        style.configure('Danger.TButton',background='#542c3e',foreground='#ffb8c7')
        style.configure('Card.TFrame',background='#18263b')
        style.configure('Card.TLabel',background='#18263b',foreground='#e5edf8')
        style.configure('CardMuted.TLabel',background='#18263b',foreground='#aebed2',font=('DejaVu Sans',9))
        style.configure('TScale',background='#18263b',troughcolor='#0c1524')
        style.configure('TEntry',fieldbackground='#18263b',foreground='#e5edf8',insertcolor='#38dbc0')
        style.configure('TCombobox',fieldbackground='#18263b',foreground='#e5edf8')
        style.map('TCombobox',fieldbackground=[('readonly','#23344c')],foreground=[('readonly','#e5edf8')])
        style.configure('TSpinbox',fieldbackground='#0c1524',foreground='#e5edf8',arrowsize=16)
        style.map('TNotebook.Tab',background=[('selected','#38dbc0'),('!selected','#23344c')],foreground=[('selected','#082620'),('!selected','#c7d6e8')])
        style.configure('TCheckbutton',background='#101827',foreground='#e5edf8',font=('DejaVu Sans',10))
        style.map('TCheckbutton',background=[('active','#23344c'),('!active','#101827')],foreground=[('disabled','#718096'),('active','#ffffff'),('!active','#e5edf8')],indicatorbackground=[('selected','#38dbc0'),('!selected','#b6c8d9')])
        style.configure('TNotebook',background='#101827');style.configure('TNotebook.Tab',padding=(18,8))
        outer=ttk.Frame(root,padding=18);outer.pack(fill='both',expand=True)
        mast=ttk.Frame(outer);mast.pack(fill='x',pady=(0,12))
        ttk.Label(mast,text='Alpha 1S',style='Title.TLabel').pack(side='left')
        self.connection=tk.StringVar(value='Bluetooth' if isinstance(self.robot,BluetoothRobot) else 'USB')
        self.connection_box=ttk.Combobox(mast,textvariable=self.connection,values=['Bluetooth','USB'],state='readonly',width=11)
        self.connection_box.pack(side='left',padx=16)
        self.connection_box.bind('<<ComboboxSelected>>',self.change_connection)
        ttk.Button(mast,text='?  Help',command=self.show_help).pack(side='right')
        self.settings_button=ttk.Button(mast,text='Joint settings',command=self.show_joint_settings)
        self.settings_button.pack(side='right',padx=8)
        ttk.Button(mast,text='Activity',command=self.show_activity).pack(side='right',padx=8)
        self.status=tk.StringVar(value='Disarmed • Connect to begin')
        content=ttk.Frame(outer);content.pack(fill='both',expand=True)
        self.notebook=ttk.Notebook(content);self.notebook.pack(side='left',fill='both',expand=True)
        self.pose_page=ttk.Frame(self.notebook);self.notebook.add(self.pose_page,text='Pose Studio')
        ttk.Label(self.pose_page,text='Build a pose',font=('DejaVu Sans',22,'bold')).pack(anchor='w',padx=12,pady=(12,4))
        ttk.Label(self.pose_page,text='0–180° is a command range, not a safe range for every pose. Collision checking is not available.\nMove in small steps; stop before joints touch or strain. Help explains recovery.',style='Warning.TLabel',wraplength=780).pack(anchor='w',padx=12,pady=(0,10))
        # Reserve the status strip before the expanding editor, including at 700 px height.
        footer=ttk.Frame(self.pose_page);footer.pack(side='bottom',fill='x',pady=(10,0))
        ttk.Label(footer,textvariable=self.status,wraplength=980).pack(anchor='w')
        ttk.Label(footer,text='Read angle releases a joint: support that limb. Disarm blocks new commands; use power switch to stop.',style='Muted.TLabel').pack(anchor='w',pady=(4,0))
        self.events=tk.Text(root,height=8,bg='#18263b',fg='#dce8f8',state='disabled',wrap='word')
        bar=ttk.Frame(self.pose_page);bar.pack(fill='x',pady=(0,10))
        self.check_button=ttk.Button(bar,text='1  Connect',command=self.check,style='Accent.TButton');self.check_button.pack(side='left')
        self.arm_button=ttk.Button(bar,text='2  Allow joint changes',command=self.arm);self.arm_button.pack(side='left',padx=8)
        self.disconnect_button=ttk.Button(bar,text='Disconnect',command=self.disconnect_robot);self.disconnect_button.pack(side='left',padx=(0,8))
        ttk.Button(bar,text='Reset panel',command=self.reset_panel).pack(side='left')
        ttk.Button(bar,text='Disarm',command=self.disarm,style='Danger.TButton').pack(side='right')
        options=ttk.Frame(self.pose_page);options.pack(fill='x',pady=(0,12))
        self.ready=tk.BooleanVar(value=False);self.legs_ready=tk.BooleanVar(value=False)
        ttk.Checkbutton(options,text='Supported • joints clear • switch ready',variable=self.ready,command=self.readiness_changed).pack(side='left')
        ttk.Checkbutton(options,text='Legs unloaded',variable=self.legs_ready,command=self.readiness_changed).pack(side='left',padx=16)
        self.mirrored=tk.BooleanVar(value=False)
        self.mirror_button=ttk.Checkbutton(options,text='Mirror left arm (4–6)',variable=self.mirrored,command=self.mirror_changed)
        self.mirror_button.pack(side='right')
        side=ttk.Frame(content,padding=(12,8,0,0));side.pack(side='right',fill='y')
        ttk.Label(side,text='YOUR ALPHA 1S',font=('DejaVu Sans',12,'bold')).pack(anchor='w',pady=(0,8))
        map_path=Path(__file__).resolve().parents[1]/'assets'/'motor-id-map.png'
        self.manufacturer_map=map_path.exists()
        if not self.manufacturer_map:map_path=map_path.with_name('joint-map.png')
        self.map_full=tk.PhotoImage(master=root,file=str(map_path))
        self.map_small=self.map_full.subsample(2,2)
        ttk.Label(side,image=self.map_small).pack()
        ttk.Label(side,text='Joint numbers • '+('manufacturer map' if self.manufacturer_map else 'Studio schematic'),style='Muted.TLabel').pack(anchor='w',pady=8)
        ttk.Button(side,text='Enlarge map',command=self.enlarge_map).pack(fill='x')
        ttk.Label(side,text='Arms  01–06    /    Legs  07–16',wraplength=240).pack(anchor='w',pady=12)
        ttk.Label(side,text='Clearance depends on nearby joints and the entire movement path. Moving both hips together does not guarantee clearance.',style='Muted.TLabel',wraplength=250).pack(anchor='w')
        self.joint_notebook=ttk.Notebook(self.pose_page);self.joint_notebook.pack(fill='both',expand=True,pady=8)
        self.targets={};self.moves={};self.refreshes={};self.edits={};self.sliders={};self.inputs={}
        self.angle_labels={};self.custom_labels={};self.measure_labels={};self.last_labels={};self.range_labels={};self.target_labels={};self.rows={};self.canvases={};self.scrollbars={}
        groups=('Right arm','Left arm','Right leg','Left leg')
        for group in groups:
            page=ttk.Frame(self.joint_notebook);self.joint_notebook.add(page,text=group)
            ids=[sid for sid,(_,g) in MOTORS.items() if g==group]
            header=ttk.Label(page,text=f'JOINTS {ids[0]:02d}—{ids[-1]:02d}     Read pose → choose angle → Apply',style='Muted.TLabel')
            header.pack(anchor='w',padx=10,pady=8)
            viewport=ttk.Frame(page);viewport.pack(fill='both',expand=True)
            canvas=tk.Canvas(viewport,bg='#101827',highlightthickness=0)
            scroll=ttk.Scrollbar(viewport,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            rows=ttk.Frame(canvas,padding=(10,0,10,0));item=canvas.create_window((0,0),window=rows,anchor='nw')
            canvas.bind('<Configure>',lambda e,c=canvas,i=item:c.itemconfigure(i,width=e.width))
            rows.bind('<Configure>',lambda e,c=canvas:c.configure(scrollregion=c.bbox('all')))
            self.canvases[group]=canvas;self.scrollbars[group]=scroll
            for sid in ids:self.create_row(rows,sid)
        self.speech=SpeechPanel(self.notebook,self)
        self.greetings=GreetingPanel(self.notebook,self)
        self.teacher=TeacherPanel(self.notebook,self)
        from .storage_panel import show
        self.storage_page=ttk.Frame(self.notebook);self.notebook.add(self.storage_page,text='Storage')
        self.refresh_storage=show(self.storage_page,self.speech,embedded=True)
        self.pose_scope=tk.StringVar(value='Arms (1–6)')
        pose_actions=ttk.Frame(self.pose_page)
        pose_actions.pack(side='bottom',fill='x',padx=12,pady=8,before=self.pose_page.pack_slaves()[0])
        ttk.Combobox(pose_actions,textvariable=self.pose_scope,values=('Arms (1–6)','All 16 joints'),state='readonly',width=16).pack(side='left')
        self.save_pose_button=ttk.Button(pose_actions,text='Save pose + reset',command=self.save_studio_pose)
        self.save_pose_button.pack(side='left',padx=6)
        self.play_pose_button=ttk.Button(pose_actions,text='Play saved pose',command=self.play_studio_pose)
        self.play_pose_button.pack(side='left')
        self.pose_next_button=ttk.Button(pose_actions,text='Next: choose voice →',command=self.pose_to_voice)
        self.pose_next_button.pack(side='right')
        ttk.Button(self.speech.page,text='Next: save greeting →',command=self.greetings.use_voice).pack(side='bottom',anchor='e',padx=16,pady=8,before=self.speech.page.pack_slaves()[0])
        self.motor_bar=bar;self.motor_options=options;self.robot_sidebar=side;self.main_content=content;self.motor_footer=footer
        self.notebook.bind('<<NotebookTabChanged>>',self.tab_changed)
        # Mouse-wheel routing works over row labels, controls and blank space.
        root.bind_all('<Button-4>',lambda e:self.scroll(-1,e))
        root.bind_all('<Button-5>',lambda e:self.scroll(1,e))
        root.bind_all('<MouseWheel>',lambda e:self.scroll(-1 if e.delta>0 else 1,e))
        self.note('Ready. No startup reads or moves. Refresh one supported motor to measure its angle and enable its slider.')
        self.update_controls();root.protocol('WM_DELETE_WINDOW',self.close)

    def pose_to_voice(self):
        from . import pose_greetings as poses
        import json
        if self.future is not None or self.speech_active or self.greeting_active:
            self.status.set('Wait for pose movement to finish.');return
        try:
            path=Path(__file__).resolve().parents[1]/'data/studio-pose.json'
            if not path.exists():raise ValueError('Save the pose first, then continue to Voice.')
            self.greetings.pose=poses.validate_pose(json.loads(path.read_text()));self.greetings.show_pose()
            self.notebook.select(self.speech.page)
        except Exception as exc:self.status.set(str(exc))

    def save_studio_pose(self):
        from . import pose_greetings as poses
        import json
        try:
            if self.future is not None or self.speech_active or self.greeting_active:raise ValueError('Wait for the active operation.')
            ids=range(1,17) if self.pose_scope.get()=='All 16 joints' else range(1,7)
            if not self.ready.get():raise ValueError('Confirm robot support and clearance before saving and resetting arms.')
            target={}
            for sid in ids:
                if sid not in self.robot.limits:raise ValueError(f'Read joint {sid} first; do not save unknown placeholder values.')
                value=float(self.targets[sid].get())
                if not value.is_integer():raise ValueError('Use whole-degree pose targets.')
                raw=self.raw_angle(sid,int(value));lo,hi=self.robot.limits[sid]
                if not lo<=raw<=hi:raise ValueError(f'Joint {sid} is outside its enabled limits.')
                target[str(sid)]=raw
            target=poses.validate_pose(target)
            from .default_pose import load as load_default
            default=load_default()
            if len(default)==16 and not self.legs_ready.get():raise ValueError('Confirm legs unloaded before resetting to the measured full-body default.')
            path=Path(__file__).resolve().parents[1]/'data/studio-pose.json'
            path.parent.mkdir(exist_ok=True);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(target));temp.replace(path)
            self.greetings.pose=target;self.greetings.show_pose()
            self.status.set('Pose saved on computer. Resetting to the stored default; keep the robot supported.')
            self.greetings.begin('reset',lambda:poses.move_to_pose(self.robot,default,self.messages_if_available,reset=True))
        except Exception as exc:self.status.set(str(exc))
    def messages_if_available(self,message):self.greetings.messages.put(message)
    def play_studio_pose(self):
        from . import pose_greetings as poses
        import json
        try:
            path=Path(__file__).resolve().parents[1]/'data/studio-pose.json'
            if not path.exists():raise ValueError('Save a pose first.')
            target=poses.validate_pose(json.loads(path.read_text()))
            if len(target)==16 and not self.legs_ready.get():raise ValueError('Confirm legs unloaded before playing all 16 joints.')
            self.greetings.begin('pose',lambda:poses.move_to_pose(self.robot,target,self.messages_if_available))
        except Exception as exc:self.status.set(str(exc))

    def tab_changed(self,event=None):
        if self.notebook.index('current')!=0:
            self.motor_bar.pack_forget();self.motor_options.pack_forget();self.robot_sidebar.pack_forget();self.motor_footer.pack_forget()
            self.settings_button.pack_forget()
        else:
            self.motor_footer.pack(in_=self.pose_page,side='bottom',fill='x',padx=10,pady=(10,0))
            self.motor_bar.pack(in_=self.pose_page,fill='x',padx=10,pady=(8,10),before=self.joint_notebook)
            self.motor_options.pack(in_=self.pose_page,fill='x',padx=10,pady=(0,12),before=self.joint_notebook)
            self.robot_sidebar.pack(side='right',fill='y',before=self.notebook)
            self.settings_button.pack(side='right',padx=8)

    def update_angle(self,sid):
        if sid in self.dirty and sid in self.acknowledged:
            raw=self.acknowledged[sid];suffix='commanded • position unverified'
        elif sid in self.measured:
            raw,at=self.measured[sid]
            stamp=datetime.datetime.fromisoformat(at).astimezone().strftime('%H:%M:%S')
            suffix=f'measured at {stamp}'
        else:
            self.angle_labels[sid].set('Angle  —  •  not read');return
        shown=self.display_angle(sid,raw)
        mirror=f' (raw {raw}°)' if sid in (4,5,6) and self.mirrored.get() else ''
        self.angle_labels[sid].set(f'Angle  {shown}°{mirror}  •  {suffix}')

    def show_joint_settings(self):
        if self.future is not None or self.robot.armed.is_set():return
        window=tk.Toplevel(self.root);window.title('Alpha 1S Studio • Joint settings')
        body=ttk.Frame(window,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Optional custom ranges',font=('DejaVu Sans',14,'bold')).pack(anchor='w')
        ttk.Label(body,text='Narrow the allowed commands for a joint after reviewing its clearance.\nRead that joint first. These limits do not detect collisions.',wraplength=500).pack(pady=12)
        choices=[f'{sid:02d}  {name}' for sid,(name,_) in MOTORS.items()]
        choice=ttk.Combobox(body,values=choices,state='readonly',width=38);choice.current(0);choice.pack(fill='x')
        info=tk.StringVar();ttk.Label(body,textvariable=info).pack(pady=8)
        def edit():
            sid=choice.current()+1
            if sid not in self.robot.limits:
                info.set('Read this joint while supported, then disarm to edit its range.');return
            window.destroy();self.edit_limits(sid)
        ttk.Button(body,text='Edit range',command=edit).pack(anchor='e')

    def show_help(self):
        messagebox.showinfo('Alpha 1S Studio • quick guide',
            '1. Connect checks identity and holding; it does not read joint angles.\n'
            '2. Support the robot, clear joints/cables, and keep the power switch ready. Allow joint changes unlocks reading and Apply; it does not move anything.\n'
            '3. Read angle releases ONE joint, reads its angle, then restores holding. Support that limb.\n'
            '4. Choose a target and Apply. Dragging alone never moves the robot.\n\n'
            'Legs unloaded means the torso is supported with weight off the legs.\n'
            'Angles are snapshots, not live telemetry. Acknowledged targets are not measurements.\n'
            '0–180° is the command range, not guaranteed mechanical clearance.\n'
            'There is no collision simulation or automatic collision detection. A successful command does not prove clearance.\n'
            'Use small changes and watch the whole movement. Nearby joints affect clearance; moving hips 7 and 12 together is not automatically safe.\n'
            'Arm planning: unfold elbows before lowering shoulders; avoid crossing arms at the same height. These guidelines are not validated limits for every pose.\n\n'
            'If a joint stalls, touches another part, or strains: stop sending commands, support the robot and switch its power off. Do not force a powered joint.\n'
            'Clear the obstruction while powered off. When clear and supported, power on, Reset panel, Connect, allow joint changes and read angles again. Do not retry the blocked target.\n'
            'Reconnecting alone does not clear a mechanical obstruction. Reset panel clears software state only.\n\n'
            'Mirror shoulder 4 matches shoulder 1: displayed angle = 180 − raw; 90 stays 90. Other joints stay unchanged.\n'
            'Disarm cannot stop an already-sent move. Use physical power if needed.',parent=self.root)

    def show_activity(self):
        window=tk.Toplevel(self.root);window.title('Alpha 1S Studio • Activity');window.geometry('820x360')
        box=tk.Text(window,bg='#101827',fg='#e5edf8',wrap='word',padx=16,pady=16)
        box.pack(fill='both',expand=True)
        box.insert('1.0',self.events.get('1.0','end'));box.configure(state='disabled');box.see('end')

    def enlarge_map(self):
        window=tk.Toplevel(self.root);window.title('Alpha 1S — Joint ID map')
        window.transient(self.root)
        ttk.Label(window,image=self.map_full).pack(padx=12,pady=12)
        ttk.Label(window,text=('Source: UBTECH Alpha 1S user manual, Joint ID map (PDF page 6).' if self.manufacturer_map else 'Original Studio schematic • front view • robot right is viewer left.'),style='Muted.TLabel').pack(padx=12,pady=(0,12))

    def create_row(self,parent,sid):
        row=ttk.Frame(parent,padding=14,style='Card.TFrame');row.pack(fill='x',pady=(0,10));self.rows[sid]=row
        ttk.Label(row,text=f'{sid:02d}  {MOTORS[sid][0]}',font=('DejaVu Sans',12,'bold'),style='Card.TLabel').grid(row=0,column=0,sticky='w')
        measured=tk.StringVar(value='Measured  —')
        self.measure_labels[sid]=measured
        self.angle_labels[sid]=tk.StringVar(value='Angle  —  •  not read')
        ttk.Label(row,textvariable=self.angle_labels[sid],style='CardMuted.TLabel').grid(row=1,column=0,columnspan=4,sticky='w',pady=(8,4))
        last=tk.StringVar(value='Last target  —');self.last_labels[sid]=last
        target=tk.DoubleVar(value=90);self.targets[sid]=target
        self.target_labels[sid]=tk.StringVar(value='Target: —')
        scale=ttk.Scale(row,from_=0,to=180,variable=target,command=lambda v,s=sid:self.slider_changed(s,v))
        scale.grid(row=3,column=0,sticky='ew',pady=6);self.sliders[sid]=scale
        spin=ttk.Spinbox(row,from_=0,to=180,increment=1,textvariable=target,width=6,command=lambda s=sid:self.slider_changed(s,self.targets[s].get()))
        spin.grid(row=3,column=1,padx=8);self.inputs[sid]=spin
        button=ttk.Button(row,text='Apply →',style='Accent.TButton',command=lambda s=sid:self.move(s));button.grid(row=3,column=2,padx=4);self.moves[sid]=button
        refresh=ttk.Button(row,text='Read angle',command=lambda s=sid:self.refresh(s));refresh.grid(row=3,column=3,padx=4);self.refreshes[sid]=refresh
        bounds=self.robot.saved_limits.get(sid,COMMAND_LIMITS[sid])
        text=f'{bounds[0]}–{bounds[1]}°  /  Read pose to unlock'
        rangevar=tk.StringVar(value=text);self.range_labels[sid]=rangevar
        self.custom_labels[sid]=tk.StringVar(value='' if bounds==(0,180) else f'Custom raw range: {bounds[0]}–{bounds[1]}°')
        ttk.Label(row,textvariable=self.custom_labels[sid],style='CardMuted.TLabel').grid(row=4,column=0,columnspan=4,sticky='w')
        row.columnconfigure(0,weight=1)

    def scroll(self,units,event):
        if event is not None and event.widget==self.teacher.transcript:
            # Text's own class binding already scrolls the session history.
            return
        index=self.notebook.index('current')
        if index>=1:
            panel=self.speech if index==1 else self.greetings if index==2 else self.teacher
            panel.canvas.yview_scroll(units,'units');return 'break'
        group=('Right arm','Left arm','Right leg','Left leg')[self.joint_notebook.index('current')]
        self.canvases[group].yview_scroll(units,'units')
        return 'break'

    def display_angle(self,sid,raw):
        return 180-raw if sid in (4,5,6) and self.mirrored.get() else raw

    def raw_angle(self,sid,display):
        return self.display_angle(sid,display)

    def mirror_changed(self):
        # Toggling reverses the display coordinate only; the pending raw target stays fixed.
        for sid in (4,5,6):
            self.targets[sid].set(180-self.targets[sid].get())
            if sid in self.robot.limits:self.configure_range(sid,'Raw limits unchanged; display mirrored' if self.mirrored.get() else 'Raw angles')
            self.slider_changed(sid,self.targets[sid].get());self.update_angle(sid)

    def invalidate(self,reason):
        self.robot.disarm();self.checked=isinstance(self.robot,BluetoothRobot) and self.robot.connected;self.holding=None
        self.robot.limits.clear();self.robot.positions.clear();self.robot.targets.clear()
        self.measured.clear();self.acknowledged.clear();self.dirty.clear()
        for sid in MOTORS:
            self.measure_labels[sid].set('Measured  —  /  read pose required')
            self.last_labels[sid].set('Last target  —  /  cleared')
            self.range_labels[sid].set('Locked  /  Connect → Enable → Read angle')
        for sid in MOTORS:self.update_angle(sid)
        self.status.set(reason);self.update_controls()

    def reset_panel(self):
        self.robot.disarm()
        if self.future is not None:
            self.overdue=True
            self.status.set('Disarmed • Request still pending. Reset waits for completion; use physical power switch.')
            return
        self.fault=False;self.ready.set(False);self.legs_ready.set(False)
        self.invalidate('Reset complete • Software state only. Once the robot is clear and supported: Connect → Allow joint changes → Read angle.')
        self.note('Local reset only. All remembered positions discarded.')

    def slider_changed(self,sid,value):
        try:self.target_labels[sid].set(f'Target: {round(float(value))}° • raw {self.raw_angle(sid,round(float(value)))}°')
        except (ValueError,tk.TclError):pass
        # Deliberately no transport call on slider change.

    def note(self,text):
        self.events.configure(state='normal');self.events.insert('end',text+'\n');self.events.see('end');self.events.configure(state='disabled')

    def change_connection(self,event=None):
        if self.future is not None or self.speech_active or self.greeting_active or self.robot.armed.is_set():
            self.connection.set('Bluetooth' if isinstance(self.robot,BluetoothRobot) else 'USB');return
        if isinstance(self.robot,BluetoothRobot):self.robot.disconnect()
        self.invalidate('Connection changed • Connect before editing')
        kind=BluetoothRobot if self.connection.get()=='Bluetooth' else PanelRobot
        self.robot=kind(self.robot.log_dir)
        self.greetings.configure_speaker();self.update_controls()

    def readiness_changed(self):self.disarm()
    def disarm(self):
        self.robot.disarm();self.status.set('Disarmed — commands already sent may finish');self.update_controls()
    def arm(self):
        if self.checked and self.ready.get() and self.future is None and not self.speech_active and not self.greeting_active:
            self.robot.armed.set();self.status.set('Editing enabled • Apply moves immediately • Read angle releases the supported joint');self.update_controls()
    def check(self):
        if self.future is not None or self.speech_active or self.greeting_active:return
        if isinstance(self.robot,BluetoothRobot) and self.robot.connected:
            self.status.set('Bluetooth connected • Read angle and Apply reuse this connection');return
        self.robot.disarm();self.submit()
    def disconnect_robot(self):
        if self.future is not None or self.speech_active or self.greeting_active:return
        try:
            if isinstance(self.robot,BluetoothRobot):self.robot.disconnect()
            self.invalidate('Disconnected • Connect before changing joints')
        except Exception as exc:self.invalidate('Disconnected • '+str(exc))

    def update_controls(self):
        busy=self.future is not None or self.speech_active or self.greeting_active;armed=self.robot.armed.is_set()
        self.connection_box.configure(state='disabled' if busy or armed else 'readonly')
        self.settings_button.configure(state='disabled' if busy or armed else 'normal')
        self.mirror_button.configure(state='disabled' if busy else 'normal')
        for button in (self.save_pose_button,self.play_pose_button,self.pose_next_button):
            button.configure(state='disabled' if busy else 'normal')
        connected=isinstance(self.robot,BluetoothRobot) and self.robot.connected
        self.check_button.configure(text='Connected' if connected else '1  Connect',state='normal' if connected else 'disabled' if busy else 'normal')
        self.disconnect_button.configure(state='normal' if connected and not busy else 'disabled')
        self.arm_button.configure(text='Joint changes allowed' if armed else '2  Allow joint changes',state='normal' if self.checked and self.ready.get() and not busy and not armed else 'disabled')
        for sid in MOTORS:
            configured=sid in self.robot.limits
            leg_ok=sid<=6 or self.legs_ready.get()
            self.moves[sid].configure(state='normal' if configured and armed and leg_ok and not busy else 'disabled')
            self.refreshes[sid].configure(state='normal' if armed and leg_ok and not busy else 'disabled')
            for widget in (self.sliders[sid],self.inputs[sid]):widget.configure(state='normal' if configured and not busy else 'disabled')

    def move(self,sid):
        if self.future is not None or not self.robot.armed.is_set() or not self.ready.get():return
        try:
            value=float(self.targets[sid].get());target=self.raw_angle(sid,round(value))
            low,high=self.robot.limits[sid]
            if not low<=target<=high:raise ValueError()
        except (ValueError,KeyError,tk.TclError,OverflowError):
            self.status.set('Invalid target • Choose an angle within the enabled range.');return
        if sid>=7 and not self.legs_ready.get():return
        self.submit(sid,target,support_confirmed=True)

    def refresh(self,sid):
        if self.future is not None or not self.robot.armed.is_set() or not self.ready.get():return
        if sid>=7 and not self.legs_ready.get():return
        self.submit(sid,setup=True,support_confirmed=True)

    def edit_limits(self,sid):
        if self.future is not None or self.robot.armed.is_set() or sid not in self.robot.limits:return
        dialog=tk.Toplevel(self.root);dialog.title(f'Motor {sid} — reviewed limits');dialog.transient(self.root);dialog.grab_set()
        body=ttk.Frame(dialog,padding=18);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Documented command range: 0–180°.\nThis does not establish mechanical clearance limits.\nSave only limits you have reviewed on the supported robot.',wraplength=430).pack(anchor='w')
        low,high=self.robot.limits[sid];lo=tk.StringVar(value=str(low));hi=tk.StringVar(value=str(high))
        for label,var in (('Minimum RAW degrees',lo),('Maximum RAW degrees',hi)):
            ttk.Label(body,text=label).pack(anchor='w',pady=(8,0));ttk.Entry(body,textvariable=var).pack(fill='x')
        accepted=tk.BooleanVar(value=False)
        ttk.Checkbutton(body,text='I have reviewed clearance throughout this range.',variable=accepted).pack(anchor='w',pady=12)
        def save():
            if not accepted.get():messagebox.showerror('Review required','Confirm clearance review first.',parent=dialog);return
            try:self.robot.set_limits(sid,int(lo.get()),int(hi.get()))
            except (ValueError,OSError) as exc:messagebox.showerror('Limits not saved',str(exc),parent=dialog);return
            self.configure_range(sid,'User-reviewed limits; not manufacturer-certified');self.note(f'Motor {sid}: reviewed limits saved.');dialog.destroy()
        ttk.Button(body,text='Save reviewed limits',command=save).pack(anchor='e')

    def configure_range(self,sid,source):
        raw_low,raw_high=self.robot.limits[sid]
        low,high=sorted((self.display_angle(sid,raw_low),self.display_angle(sid,raw_high)))
        self.sliders[sid].configure(from_=low,to=high);self.inputs[sid].configure(from_=low,to=high)
        self.range_labels[sid].set(f'Command: 0–180° • Enabled: {low}–{high}° • {source}')
        self.custom_labels[sid].set('' if (raw_low,raw_high)==(0,180) else f'Custom raw range: {raw_low}–{raw_high}°')

    def submit(self,sid=None,target=None,setup=False,support_confirmed=False):
        if self.future is not None or self.speech_active or self.greeting_active:return
        self.status.set('Connecting…' if sid is None else f'Motor {sid:02d} • '+('Reading angle and restoring holding…' if setup else f'Applying {target}°…'))
        self.started=time.monotonic();self.overdue=False
        if sid is None and target is None and not setup and isinstance(self.robot,BluetoothRobot):
            self.future=self.pool.submit(self.robot.connect)
        else:self.future=self.pool.submit(self.robot.run,sid,target,setup,support_confirmed)
        self.update_controls();self.root.after(100,self.poll)

    def poll(self):
        if self.future is None:return
        if not self.future.done():
            if time.monotonic()-self.started>20 and not self.overdue:
                self.overdue=True;self.robot.disarm()
                self.status.set('Request overdue • Disarmed • Use physical power switch. Waiting; no new requests allowed.')
                self.note('Request exceeded 20 seconds. No retry or replacement worker started.')
            self.root.after(100,self.poll);return
        future=self.future;self.future=None
        try:result=future.result()
        except Exception as exc:result={'status':'error','error':str(exc)}
        if self.overdue:result={**result,'status':'error','error':'Request exceeded wait limit or was reset. All positions discarded.'}
        sid=result.get('servo')
        if result['status']=='ok':
            self.checked=True
            if result.get('holding') is None:
                self.holding=None
                self.status.set(('Bluetooth connected' if isinstance(self.robot,BluetoothRobot) and self.robot.connected else 'Bluetooth request complete')+' • '+(f'Motor {sid:02d} '+('angle read' if result.get('setup') else 'target acknowledged') if sid else 'Allow joint changes to read or move a supported joint'))
            else:
                self.holding=int.from_bytes(bytes.fromhex(result['holding']['status_bytes_hex']),'little')
                off=[str(s) for s in MOTORS if not self.holding&(1<<(s-1))]
                self.status.set(('Armed' if self.robot.armed.is_set() else 'Disarmed')+' • '+('Holding enabled for all 16 motors' if not off else 'Holding disabled: '+', '.join(off)))
            if result.get('setup_limits'):
                self.measured[sid]=(result['baseline_degrees'],result['measured_at'])
                self.dirty.discard(sid)
                stamp=datetime.datetime.fromisoformat(result['measured_at']).astimezone().strftime('%H:%M:%S')
                self.measure_labels[sid].set(f'Last measured RAW: {result["baseline_degrees"]}° at {stamp} • snapshot before holding restore')
                self.configure_range(sid,result['range_source'])
                display=self.display_angle(sid,result['baseline_degrees'])
                self.targets[sid].set(display);self.slider_changed(sid,display)
                self.note(f'Motor {sid}: measured {result["baseline_degrees"]}°, holding restored. No continuous polling.')
            if result.get('move_acknowledged'):
                self.acknowledged[sid]=result['target']
                self.last_labels[sid].set(f'Last acknowledged RAW target: {result["target"]}° • not a position measurement')
                if not result.get('setup'):
                    self.dirty.add(sid)
                    old=self.measured.get(sid)
                    self.measure_labels[sid].set(f'Last measured RAW: {old[0]}° • STALE after movement; refresh only while supported' if old else 'Measured position unknown')
                    self.note(f'Motor {sid}: target {result["target"]}° acknowledged. Observe the result.')
            else:self.note('Robot identity checked. No joint release or movement.')
        else:
            self.fault=True
            if isinstance(self.robot,BluetoothRobot):self.robot.disconnect()
            self.invalidate('FAULT • Controls locked. If stalled or obstructed: support and power off; clear before restarting. Then Reset panel → Connect → Read angle. See Help.')
            self.note('Error: '+result.get('error',result.get('cleanup_error','Unknown error')))
        if sid in MOTORS:self.update_angle(sid)
        if result.get('report'):self.note('Saved '+Path(result['report']).name)
        self.update_controls()

    def close(self):
        self.teacher.cancel.set()
        self.robot.disarm()
        if self.future is not None or self.speech.future is not None or self.greetings.future is not None or self.teacher.future is not None or (self.teacher.key_future is not None and not self.teacher.key_future.done()):
            self.status.set('Disarmed. Waiting for the active request; close again when it finishes.');return
        if isinstance(self.robot,BluetoothRobot):self.robot.disconnect()
        self.teacher.close();self.greetings.close();self.speech.close();self.pool.shutdown(wait=False)
        from .upload_session import close
        close()
        self.root.update_idletasks()
        for callback in self.root.tk.splitlist(self.root.tk.call('after','info')):
            self.root.tk.call('after','cancel',callback)  # Widget destruction removes its own Tcl callbacks.
        self.root.destroy()

def main():
    root=tk.Tk()
    ControlPanel(root)
    root.mainloop()

if __name__=='__main__':
    main()
