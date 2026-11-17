# Troubleshooting

| Symptom | Next step |
| --- | --- |
| GUI cannot open | Run the environment checker; use an X11/XWayland desktop and system Python with Tk. |
| Bluetooth cannot connect | Unplug USB, disconnect the phone app, check pairing and the configured address. Close other controllers. |
| Unsupported identity | Stop. This release only supports the documented hardware/firmware; do not bypass the guard. |
| HID permission denied | Ask an administrator for narrowly scoped device access. Never run the GUI as root or use world-writable device permissions. |
| Backup missing | Run the first-time card setup in Setup. An empty folder is not a verified backup. |
| Card is mounted | Unmount the robot partition before backup; do not eject or unplug it. |
| Backup comparison failed | Keep the partial backup for diagnosis. Do not fabricate verification data or upload to that card. |
| Card filesystem identity changed | Stop uploads. Preserve a fresh read-only backup and investigate the changed metadata. Studio does not automatically clear dirty flags or repair filesystems. |
| Original MP3 directory full | Delete unwanted Studio recordings in Storage over USB. Free bytes alone do not indicate available directory entries. |
| 429 during answer or voice generation | Check the named model's rate limits/quota in Google AI Studio. Text and TTS quotas differ. Local voice avoids cloud TTS requests. |
| 503 from model API | Service unavailable. Wait and make a new explicit request; do not repeatedly trigger robot actions. |
| Microphone unavailable | Check Linux microphone permissions/input and `arecord`; the robot microphone is not used. |
| No sound | Check the status and Activity log. Fresh speech needs verified upload and USB removal. Acknowledgment alone does not prove audible playback. |
| Robot faults after a joint contacts its body | Stop commanding it, support it, and use its physical switch if needed. Clear obstructions and reconnect after recovery. Do not force powered joints. |
| Saved pair requires USB | The exact text, voice, delivery and approved gesture must match a verified accepted pair; new combinations require upload. |

For bug reports, include OS/Python, hardware/firmware, the UI step and a redacted error. Do not attach card backups, API keys, Bluetooth addresses, raw audio or personal conversation logs. See [Security](../SECURITY.md).
