"""Check local software only. Does not open robot interfaces or use the network."""
import ctypes.util
import importlib.util
import shutil
import sys
checks={'Python 3.10+':sys.version_info>=(3,10),'Tk':importlib.util.find_spec('tkinter') is not None}
checks.update({name:shutil.which(name) is not None for name in ('bluetoothctl','arecord','aplay','pkexec','udisksctl','findmnt','xwininfo')})
checks.update({name:ctypes.util.find_library(name) is not None for name in ('espeak-ng','mp3lame','X11')})
for name,ok in checks.items():print(('OK      ' if ok else 'MISSING ')+name)
print('Key vault (optional):',bool(importlib.util.find_spec('keyring')))
raise SystemExit(0 if all(checks.values()) else 1)
