# Installation and first robot setup

## 1. Install desktop prerequisites

Use Linux with an X11 or XWayland desktop and Python 3.10+. The launcher uses the system Python. On Debian/Ubuntu:

```bash
sudo apt update
sudo apt install python3-tk bluez alsa-utils libespeak-ng1 libmp3lame0 pkexec udisks2 util-linux x11-utils
# Optional: secure API-key storage and offline GUI test runner
sudo apt install python3-keyring xvfb
```

Review these system changes yourself. Studio does not install drivers or change permissions automatically. Use a folder owned by your regular account; never run the entire GUI as root.

Extract the release ZIP or clone the repository, then:

```bash
/usr/bin/python3 scripts/check_environment.py
./launch-control-panel.sh
```

The GUI can open without a robot. `pyproject.toml` describes the source project; installing a wheel is not the supported desktop deployment in this release.

## 2. Pair your own robot

Charge and support the robot. Disconnect its phone app. Pair it using your Linux Bluetooth settings; copy its Bluetooth device address from those settings. Configure Studio locally:

```bash
/usr/bin/python3 scripts/setup_robot.py --bluetooth-address 'YOUR_ROBOT_ADDRESS'
```

Replace the placeholder with your robot's address. This saves `data/settings.json`; it does not connect. Restart Studio after changing it. Alternatively export `ALPHA1S_BLUETOOTH_ADDRESS` before launch.

For Bluetooth operation leave USB unplugged. Connect from Pose Studio. The transport verifies hardware `Alpha1_V2.0` and firmware `2016070416`, uses RFCOMM channel 6, and rejects other versions. Do not bypass these checks.

## 3. Prepare your card for speech and the action library

This first-time operation reads your own card twice, creates a verified backup, and imports local action files. It sends no motor commands and writes nothing to the card. Allow roughly 10–15 minutes for the original 124 MiB card. Close Studio and other robot controllers first. Do not remove power or USB during the backup.

1. Connect USB with the robot powered and supported.
2. Identify the USB device with `lsusb`. If it is still in control/HID mode, explicitly request storage mode:

   ```bash
   /usr/bin/python3 scripts/setup_robot.py --enter-storage
   ```

   This checks the robot identity, then sends the storage-mode request. If HID permission is denied, stop and arrange a narrowly scoped device permission with your administrator. Do not run the GUI as root or make devices world-writable.

3. Identify the newly appeared **whole robot disk** with `lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS`. Do not assume it is `/dev/sda`. The helper independently requires the Alpha storage USB identity and the tested card size.
4. If Linux mounted the card, unmount its partition in Files or with `udisksctl unmount -b /dev/sdX1`. Replace this example with the actual robot partition. **Unmount; do not eject or unplug.**
5. Back up the verified whole robot disk (replace `/dev/sdX`):

   ```bash
   pkexec /usr/bin/python3 "$(pwd)/scripts/setup_robot.py" --backup-card /dev/sdX
   ```

   The OS asks for administrator authorization for read-only block-device access. Pass 1 saves the image; pass 2 compares every sector with the device. The tool validates the FAT copies, file chains and filenames before importing. A failed comparison does not create an upload-verification certificate.
6. Wait for “Backup verified twice and local action inventory imported.” Unplug USB before using Bluetooth again.

Outputs: `backups/robot-card-*.img`, `reports/card-backup-verification.json`, `reports/card-file-inventory.json`, and `work/card-extracted/`. Keep these private. The backup remains tied to this installation's path; moving the folder later requires updating the report's image path to the same verified image. Never use another owner's backup or fabricate these files.

Existing onboarding state is never overwritten. Unexpected layout, mounted media, damaged chains or unsupported sizes stop setup. Recovery is manual; see [Troubleshooting](TROUBLESHOOTING.md). This new onboarding tool has offline validation; repeat physical first-run validation on a second robot remains pending.

## 4. Configure Gemini and voices

In Conversation → Settings enter your Gemini API key and a model ID available to your account. Obtain a key from [Google AI Studio](https://aistudio.google.com/apikey). Text generation and preset TTS use separate model settings and may have separate quotas. Fields are editable; do not assume every account has access to the defaults.

Choose **Save key securely** only if you want persistence in the Linux password vault. There is no plaintext fallback. Environment variables are documented in `.env.example`; `.env` is not loaded automatically. Keep keys out of screenshots and issue reports.

Voice → Local uses offline synthesis. Preset voices send the text to Google's TTS API. Microphone input uses the computer's microphone and sends the explicitly recorded clip to Google. The robot's microphone is not used. Conversation sends recent turns; web search is optional.

## 5. First session

Follow [Using Studio](DEMO.md). Read and rehearse actions before enabling them for Gemini. The supplied release contains no personal greetings, captured default posture or pre-approved actions. Without a captured default, Reset uses the legacy six-arm-joint 90° fallback; this is not a whole-body standing calibration. For full-body poses, capture your own default first:

1. Close Studio, unplug USB, and place the robot in your intended stable posture.
2. Secure its torso, unload both legs, clear every joint and keep the power switch reachable. Reading an angle briefly releases that joint before restoring holding.
3. Explicitly request the 16-joint measurement:

   ```bash
   /usr/bin/python3 scripts/setup_robot.py --capture-default --supported-legs-unloaded
   ```

4. Reopen Studio. Reset now uses the measured local default. This is an active hardware operation, not an offline setup check. Never assume every joint should be 90°. Remember that support must remain in place during the read.
