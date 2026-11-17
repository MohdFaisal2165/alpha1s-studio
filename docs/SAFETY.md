# Hardware operation

- Support the robot and clear all limbs/cables before arming. Support leg weight before any joint release. Do not force powered joints.
- 0–180° is a protocol command range, not verified collision-free travel. Mirrored joints and mechanical assembly vary.
- Angle readback may briefly release the joint. Displayed angles are snapshots, not continuous telemetry.
- Sliders select targets; Apply sends commands. No motor commands run on startup or during offline tests.
- Stop blocks subsequent requests; it is not a physical emergency stop. Keep the robot's power switch reachable.
- Uncertain motor/playback acknowledgements are not retried automatically. Recharge and investigate faults instead of repeatedly resending.
- Card upload requires the correct identity and verified backup, writes a journal and verifies changed sectors. Do not unplug during writing.
- Gemini only proposes an approved identifier; generated angles, code and arbitrary device commands are rejected.
- Full-body native actions require explicit rehearsal and approval tied to the file hash. No factory action pack is included.
- Firmware changes and persistent system configuration changes require separate explicit approval.
