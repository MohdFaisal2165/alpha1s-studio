# Engineering scope and architecture

Alpha 1S Studio is a host-side embodied-AI application integrated with a commercial embedded controller. The model selects intent; deterministic application code owns physical execution.

## Layers

| Layer | Responsibility | Representative modules |
| --- | --- | --- |
| Desktop | Operator workflow, status, microphone, configuration | `control_panel`, `teacher_panel`, `speech_panel` |
| AI orchestration | Bounded answer, allowed action selection, optional search | `teacher`, `gemini_api` |
| Speech | Local or cloud synthesis, shared voice/delivery | `speech`, `expressive_voice` |
| Playback | Paired audio/action jobs, exact replay, uncertainty tracking | `conversation_speech`, `paired_speech` |
| Embedded transport | HID framing; RFCOMM packets, identity checks and sessions | `identify`, `robot_speech`, `bluetooth_transport` |
| Storage | FAT32 import, staging, journals, privileged bounded uploads | `card_import`, `audio_card`, `sector_patch`, `speech_upload` |

## Physical execution boundary

Gemini returns an approved catalog identifier, not motor packets. The application resolves the identifier, checks current approval and content hashes, and enforces operator readiness. A native action retains its original HTS bytes. Fresh speech and the action receive the same generated basename in MUSIC and ACTION, followed by one Bluetooth action request after USB removal.

Writes commit file data before allocation metadata and directory entries. Exact sector journals and readback checks support diagnosis. Uncertain playback is recorded before attempting the command and blocks automatic replay. Software Stop prevents subsequent requests; the embedded firmware controls motion already accepted.

## What has been demonstrated

- Direct USB and Bluetooth robot integration on the documented hardware/firmware.
- Persistent joint-control sessions, saved pose/greeting workflows and robot-speaker output.
- Fresh model-generated answers with preset expressive voices.
- Speech overlapping Celebrate motion, including speech longer than the action, followed by operator confirmation of the Studio integration.
- Offline fault-path, protocol, upload, deletion and UI tests.

## Scope boundaries

The repository contains host software and protocol adapters. It does not contain custom firmware, firmware flashing tools, an RTOS port, motor-driver design, or a learned robotics controller. The 0–180° protocol domain is not a complete collision model. Joint feedback is a snapshot and may require briefly releasing a joint; it is not continuous telemetry.

## Future engineering milestones

- Validate clean first-run setup on additional Alpha 1S units and firmware revisions.
- Add hardware-in-the-loop regression procedures with explicit operator control.
- Investigate safer joint/path constraints using measured robot geometry.
- Investigate wireless fresh-audio transfer without assuming protocol support.
- Treat custom embedded firmware or an external controller as a separate future project with documented design, hardware interfaces and validation.

These are proposed extensions, not features claimed by this release.
