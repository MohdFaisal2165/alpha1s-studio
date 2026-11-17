# Audio transport findings

The desired flow is fresh question → fresh short answer → generated MP3 → built-in speaker. Short answers reduce the amount of audio transferred. They do not change the robot's available transport modes.

## Evidence

- The manufacturer PC protocol defines F9/9F with mode 1 (USB disk), 2 (VCP), 3 (HID), and F3/3F named playback. This does not establish a way to deliver the HID mode-change packet while the device exposes only mass storage.
- The reviewed manufacturer Bluetooth table documents named action playback, sound state and volume, but no ordinary MP3 upload operation. Bluetooth firmware update commands are not a safe substitute for audio transfer.
- The development robot has successfully played an existing MP3 over Bluetooth using its full `MUSIC/<name>.MP3` path and a tested skip-reset mode. That mode is firmware-specific and is restored after playback.
- New MP3 upload is implemented by identity-checked, journaled sector writes to the existing FAT32 card, followed by read-back verification. It is not a firmware update.
- A live fresh-sentence test encountered a mounted card after the authorization handoff. The privileged helper now checks and unmounts only the verified robot card immediately before opening it exclusively; it never force-unmounts.
- The subsequent upload verified successfully. USB playback was not acknowledged and the user clarified that no audio was heard. It must not be reported as a successful end-to-end conversation test.

- Follow-up: with USB still attached, Bluetooth identity timed out before any audio command. After USB was unplugged, full-path Bluetooth playback was accepted, mode restoration succeeded, and the user confirmed hearing the newly generated sentence with arms still. The conversation workflow now uses this verified playback route. A subsequent live Gemini custom-question test succeeded after the user entered a key privately; Studio reported Bluetooth playback accepted, and the user confirmed hearing the newly generated custom answer from the robot speaker.

## Next experiments

The new workflow uses full-path Bluetooth playback for newly uploaded files after USB removal. Investigate whether an explicitly controlled USB disconnect (for example a suitable hub with genuine port power control) exits storage mode on this firmware. A Linux driver rebind or USB bus reset is not proven equivalent to physically unplugging the robot. No speculative reset, firmware command or persistent system change is included in the application.

If no supported native transfer or reconnect mechanism exists, fully wireless fresh speech through the original speaker will require additional hardware or firmware development, outside this release's verified capabilities.

## Sources

- [Manufacturer Bluetooth protocol, mirrored with alpha-hacks](https://github.com/alpha-hacks/alpha-bluetooth/blob/develop/Alpha1%20Series%20Bluetooth%20communication%20protocol565212.pdf)
- [Manufacturer PC protocol mirror](https://device.report/m/710f4dde2fbd0adae839a7e063f1a91b2599c5fbe3ae4477b88010d938b97094)
- [Alpha 1S reverse-engineering project](https://github.com/adampaigge/UBTECH-Alpha-1S-SDK)
- [Gemini generateContent API](https://ai.google.dev/api/generate-content)
- [Gemini audio input](https://ai.google.dev/gemini-api/docs/audio)

Repository claims are research leads, not evidence that a command works on this robot. No third-party live motor routines were imported.
