"""Recording retention UI. Deletion is queued for the next verified USB upload."""
import tkinter as tk
from tkinter import ttk
from . import recording_store

def show(parent,panel=None,*,embedded=False):
    if embedded:window=parent
    else:
        window=tk.Toplevel(parent);window.title('Alpha 1S — Storage');window.geometry('900x500')
    ttk.Label(window,text='Robot storage',style='Title.TLabel').pack(anchor='w',padx=16,pady=(16,4))
    ttk.Label(window,text='Connect USB to delete recordings. No movement or speech is sent. Greeting recordings and factory files are protected; local backups remain.',wraplength=780).pack(padx=16,pady=12)
    table=ttk.Treeview(window,columns=('text','state','size'),show='tree headings')
    table.heading('#0',text='Recording');table.column('#0',width=120)
    for key,title,width in [('text','Message',390),('state','Used by',180),('size','Audio size',90)]:table.heading(key,text=title);table.column(key,width=width)
    table.pack(fill='both',expand=True,padx=16)
    status=tk.StringVar();ttk.Label(window,textvariable=status,wraplength=780).pack(padx=16,pady=8)
    def refresh():
        table.delete(*table.get_children());protected=recording_store.protected();count=0;total=0
        import json
        links={}
        for filename in ('pose-greetings.json','greeting-profiles.json'):
            path=recording_store.ROOT/'data'/filename
            if path.exists():
                for key,profile in json.loads(path.read_text()).items():
                    links[profile.get('audio')]=profile.get('name',key)
        for job in sorted(recording_store.jobs(),key=lambda j:j['_path'].stat().st_mtime,reverse=True):
            if job.get('card_deleted') or job.get('upload',{}).get('status')!='complete':continue
            path=job['_path'].parent/'speech.mp3';size=path.stat().st_size if path.exists() else 0;total+=size;count+=1
            state=('Greeting: '+links.get(job['name'],'saved profile')) if job['name'] in protected else 'Conversation / Voice'
            table.insert('', 'end',iid=job['name'],text=job['name'],values=(job.get('text',''),state,f'{size/1024:.0f} KB'))
        status.set(f'{count} Studio recordings • {total/1024/1024:.1f} MiB of audio • Card free space: not measured (audio size is not card usage).')
    def delete_now():
        names=list(table.selection())
        if not names:status.set('Select a recording first.');return
        try:
            if panel is None:raise ValueError('Open Recordings from the active Studio.')
            if panel.future is not None or panel.active or panel.owner.speech_active or panel.owner.greeting_active:raise ValueError('Wait for the active operation to finish.')
            panel.acquire(storage_only=True)
            panel.phase='delete'
            panel.future=panel.pool.submit(recording_store.delete_now,names,panel.messages.put)
            panel.controls();panel.frame.after(100,panel.poll)
            status.set('Deleting selected recordings via USB…')
            def check():
                if not window.winfo_exists():return
                if panel.phase=='delete':window.after(200,check);return
                refresh();status.set(panel.status.get())
            window.after(200,check)
        except Exception as e:status.set(str(e))
    row=ttk.Frame(window);row.pack(pady=12)
    ttk.Button(row,text='Refresh',command=refresh).pack(side='left',padx=6)
    ttk.Button(row,text='Delete selected',command=delete_now,style='Danger.TButton').pack(side='left',padx=6)
    refresh()
    return refresh
