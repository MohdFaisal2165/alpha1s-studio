"""Request normal WM close only for the earlier generated panel; never kill it."""
import ctypes as c
import ctypes.util
import re
import time
import subprocess
text=subprocess.check_output(['xwininfo','-root','-tree'],text=True)
ids=re.findall(r'^\s*(0x[0-9a-f]+) "Alpha 1S Studio[^"\n]*":',text,re.M)
if not ids:
    print('Previous panel is already closed.');raise SystemExit
x=c.CDLL(ctypes.util.find_library('X11'))
x.XOpenDisplay.argtypes=[c.c_char_p];x.XOpenDisplay.restype=c.c_void_p
x.XInternAtom.argtypes=[c.c_void_p,c.c_char_p,c.c_int];x.XInternAtom.restype=c.c_ulong
class Data(c.Union):_fields_=[('b',c.c_char*20),('s',c.c_short*10),('l',c.c_long*5)]
class Message(c.Structure):_fields_=[('type',c.c_int),('serial',c.c_ulong),('send_event',c.c_int),('display',c.c_void_p),('window',c.c_ulong),('message_type',c.c_ulong),('format',c.c_int),('data',Data)]
class Event(c.Union):_fields_=[('client',Message),('pad',c.c_long*24)]
x.XSendEvent.argtypes=[c.c_void_p,c.c_ulong,c.c_int,c.c_long,c.POINTER(Event)]
x.XFlush.argtypes=[c.c_void_p];x.XCloseDisplay.argtypes=[c.c_void_p]
d=x.XOpenDisplay(None)
if not d:raise SystemExit('Cannot access desktop.')
for wid in ids:
    e=Event();e.client.type=33;e.client.send_event=1;e.client.display=d;e.client.window=int(wid,16)
    e.client.message_type=x.XInternAtom(d,b'WM_PROTOCOLS',False);e.client.format=32
    e.client.data.l[0]=x.XInternAtom(d,b'WM_DELETE_WINDOW',False);e.client.data.l[1]=0
    x.XSendEvent(d,int(wid,16),False,0,c.byref(e))
x.XFlush(d);x.XCloseDisplay(d)
print('Requested normal close of the old panel; its own handler disarms and refuses to close during an active request.')

for attempt in range(30):
    current=subprocess.check_output(['xwininfo','-root','-tree'],text=True)
    if not any(re.search(r'^\s*'+re.escape(wid)+r' "Alpha 1S Studio',current,re.M) for wid in ids):break
    time.sleep(.1)
else:
    raise SystemExit('An older Studio window is still open, possibly waiting for an operation. No new window started; finish that operation and try again.')
