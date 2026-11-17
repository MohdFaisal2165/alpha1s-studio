# Alpha 1S Studio

### Embodied AI · Embedded-systems integration · Human–robot interaction

Turn a UBTECH Alpha 1S into an interactive robot that answers questions through its own speaker and performs approved gestures alongside its speech.

Alpha 1S Studio connects a Python desktop application, Gemini, speech synthesis, and the robot's existing embedded controller. It bridges model decisions and physical behavior through validated action selection, explicit operator controls, USB file transfer, and Bluetooth protocol adapters.

**Linux desktop application · MIT licensed · Uses the original robot controller**

![Alpha 1S Studio desktop interface](src/assets/studio-demo.png)

*Pose Studio: joint controls, pose capture and playback in the desktop application.*

## See the system in action

1. Build a pose using the 16-joint editor.
2. Choose a voice and expressive delivery; preview or test a message.
3. Combine a pose and message into a named greeting.
4. Ask a question by typing or microphone. Gemini creates a concise answer and selects an approved gesture.
5. Upload new speech over USB, unplug when prompted, and hear the robot speak while it performs the library action.

Simultaneous speech and Celebrate motion were observed on the development robot, including a 4.04-second recording that continued after the 2.2-second gesture. The integrated Studio workflow was also confirmed by the operator. Rehearse each action before use; the embedded controller manages playback timing.

## Get started

```bash
git clone https://github.com/MohdFaisal2165/alpha1s-studio.git
cd alpha1s-studio
/usr/bin/python3 src/check_environment.py
/usr/bin/python3 src/main.py
```

Install the prerequisites below before launching. The application source, setup helpers and assets are together in `src/`. Robot settings, recordings, reports and backups are created locally under `src/data/`, `src/reports/`, `src/work/` and `src/backups/`.

```text
src/
  main.py                 launch Studio
  setup_robot.py          configure your robot and prepare its card
  check_environment.py    check desktop prerequisites
  alpha_demo/             pose, voice, greetings, conversation and transport
  assets/                 joint map and Studio screenshot
```

Tested configuration: Linux desktop with X11/XWayland, hardware `Alpha1_V2.0`, firmware `2016070416`, original 124 MiB FAT32 card. Fresh recordings follow USB upload → unplug → Bluetooth playback. Verified saved recordings replay wirelessly.

## Installation and first robot setup

### 1. Install desktop prerequisites

Use Linux with an X11 or XWayland desktop and Python 3.10+. The launcher uses the system Python. On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3-tk bluez alsa-utils libespeak-ng1 libmp3lame0 pkexec udisks2 util-linux x11-utils
# Optional: secure API-key storage
sudo apt install python3-keyring
```

Review these system changes yourself. Studio does not install drivers or change permissions automatically. Use a folder owned by your regular account; never run the entire GUI as root.

Extract the release ZIP or clone the repository, then:

```bash
/usr/bin/python3 src/check_environment.py
/usr/bin/python3 src/main.py
```

The GUI opens with controls disarmed. Keep the `src/` folder intact and writable.

### 2. Pair your own robot

Charge and support the robot. Disconnect its phone app. Pair it using your Linux Bluetooth settings; copy its Bluetooth device address from those settings. Configure Studio locally:

```bash
/usr/bin/python3 src/setup_robot.py --bluetooth-address 'YOUR_ROBOT_ADDRESS'
```

Replace the placeholder with your robot's address. This saves `src/data/settings.json`; it does not connect. Restart Studio after changing it. Alternatively export `ALPHA1S_BLUETOOTH_ADDRESS` before launch.

For Bluetooth operation leave USB unplugged. Connect from Pose Studio. The transport verifies hardware `Alpha1_V2.0` and firmware `2016070416`, uses RFCOMM channel 6, and rejects other versions. Do not bypass these checks.

### 3. Prepare your card for speech and the action library

This first-time operation reads your own card twice, creates a verified backup, and imports local action files. It sends no motor commands and writes nothing to the card. Allow roughly 10–15 minutes for the original 124 MiB card. Close Studio and other robot controllers first. Do not remove power or USB during the backup.

1. Connect USB with the robot powered and supported.
2. Identify the USB device with `lsusb`. If it is still in control/HID mode, explicitly request storage mode:

   ```bash
   /usr/bin/python3 src/setup_robot.py --enter-storage
   ```

   This checks the robot identity, then sends the storage-mode request. If HID permission is denied, stop and arrange a narrowly scoped device permission with your administrator. Do not run the GUI as root or make devices world-writable.

3. Identify the newly appeared **whole robot disk** with `lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS`. Do not assume it is `/dev/sda`. The helper independently requires the Alpha storage USB identity and the tested card size.
4. If Linux mounted the card, unmount its partition in Files or with `udisksctl unmount -b /dev/sdX1`. Replace this example with the actual robot partition. **Unmount; do not eject or unplug.**
5. Back up the verified whole robot disk (replace `/dev/sdX`):

   ```bash
   pkexec /usr/bin/python3 "$(pwd)/src/setup_robot.py" --backup-card /dev/sdX
   ```

   The OS asks for administrator authorization for read-only block-device access. Pass 1 saves the image; pass 2 compares every sector with the device. The tool validates the FAT copies, file chains and filenames before importing. A failed comparison does not create an upload-verification certificate.
6. Wait for “Backup verified twice and local action inventory imported.” Unplug USB before using Bluetooth again.

Outputs: `src/backups/robot-card-*.img`, `src/reports/card-backup-verification.json`, `src/reports/card-file-inventory.json`, and `src/work/card-extracted/`. Keep these private. The backup remains tied to this installation's path; moving the folder later requires updating the report's image path to the same verified image. Never use another owner's backup or fabricate these files.

Existing onboarding state is never overwritten. Unexpected layout, mounted media, damaged chains or unsupported sizes stop setup. Recovery is manual; see the Troubleshooting section below.

### 4. Configure Gemini and voices

In Conversation → Settings enter your Gemini API key and a model ID available to your account. Obtain a key from [Google AI Studio](https://aistudio.google.com/apikey). Text generation and preset TTS use separate model settings and may have separate quotas. Fields are editable; do not assume every account has access to the defaults.

Choose **Save key securely** only if you want persistence in the Linux password vault. There is no plaintext fallback. You may also set `GEMINI_API_KEY`, `GEMINI_MODEL` and `ALPHA1S_BLUETOOTH_ADDRESS` in the launch environment. Keep keys out of screenshots and issue reports.

Voice → Local uses offline synthesis. Preset voices send the text to Google's TTS API. Microphone input uses the computer's microphone and sends the explicitly recorded clip to Google. The robot's microphone is not used. Conversation sends recent turns; web search is optional.

### 5. First session

Follow the Using Studio section below. Read and rehearse actions before enabling them for Gemini. The supplied release contains no personal greetings, captured default posture or pre-approved actions. Without a captured default, Reset uses the legacy six-arm-joint 90° fallback; this is not a whole-body standing calibration. For full-body poses, capture your own default first:

1. Close Studio, unplug USB, and place the robot in your intended stable posture.
2. Secure its torso, unload both legs, clear every joint and keep the power switch reachable. Reading an angle briefly releases that joint before restoring holding.
3. Explicitly request the 16-joint measurement:

   ```bash
   /usr/bin/python3 src/setup_robot.py --capture-default --supported-legs-unloaded
   ```

4. Reopen Studio. Reset now uses the measured local default. This is an active hardware operation, not an offline setup check. Never assume every joint should be 90°. Remember that support must remain in place during the read.

## Using Studio

### Pose Studio → Voice → Greetings

1. **Pose Studio:** connect, confirm support and clearance, then enable editing. Read angles before moving joints. Set targets and Apply. Mirror controls change the displayed left-arm coordinate convention; they do not move motors by themselves.
2. Read and save your robot's supported default posture before using reset. With legs involved, support the torso and unload both legs. A default posture is local robot-specific data, not a universal standing configuration.
3. Adjust a pose, **Save pose + reset**, then **Play saved pose** to check it. This can involve all joints included in the pose. Continue to Voice.
4. **Voice:** type a greeting, choose voice and delivery, and use Computer preview. Send to robot is an optional hardware test: new recordings need USB upload, then USB removal for playback. “Finish without speaking” ends an uploaded preview without sending playback.
5. **Greetings:** choose or enter a person's name and save the prepared pose and voice together. Select that person later to play the greeting. The robot moves into the saved pose and speaks while holding it. Reset restores the saved default; it is a movement command.

### Conversation

1. Configure the API key/model in Settings. Select the shared voice and delivery in Voice.
2. Open Gesture library. Inspect actions imported from your own card. Rehearse only with the robot secured and all limbs clear. Save appropriate approved actions for Gemini selection.
3. Type a question, or click the microphone, speak, and click it again to finish. Review the transcribed text.
4. Confirm support and request the response with Ask Alpha. The model returns a concise new answer and selects from the approved action catalog. The UI reports the chosen gesture and reason.
5. Connect USB for fresh speech. Authorize the upload helper when prompted. Wait for verification, then unplug USB when instructed.
6. For a library gesture, speech and the action start through one paired playback command. For a saved greeting pose, the robot reaches the pose first and then speaks. Exact verified library pairs can replay wirelessly on a new explicit request.

Stop blocks subsequent commands. It cannot guarantee stopping a native action already accepted by the firmware. There is no automatic retry after uncertain command delivery.

### Storage

Storage is the central place to review recordings and permanently delete unwanted Studio-generated recordings. Deletion needs USB and authorization because it writes to the card, but does not request motor playback. Greetings' referenced audio is protected; edit or remove the greeting reference first. Keep responses you want to preserve. Temporary response cleanup is bounded and preserves original robot assets.

The original MUSIC directory has a finite entry capacity even if the card shows free bytes. Delete unwanted Studio recordings when it fills; do not expand or reformat the card to bypass the firmware's directory limitations.

## Troubleshooting

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

For bug reports, include OS/Python, hardware/firmware, the UI step and a redacted error. Do not attach card backups, API keys, Bluetooth addresses, raw audio or personal conversation logs.

## License and credits

An independent community project integrating UBTECH Alpha 1S with the Gemini API. [MIT license](LICENSE) covers the project source and original assets. UBTECH and Gemini names belong to their respective owners. Import your robot's native actions from its card. Python/Tk, BlueZ, ALSA, eSpeak NG, LAME and optional keyring retain their respective licenses.
