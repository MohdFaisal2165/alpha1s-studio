# Using Studio

## Pose Studio → Voice → Greetings

1. **Pose Studio:** connect, confirm support and clearance, then enable editing. Read angles before moving joints. Set targets and Apply. Mirror controls change the displayed left-arm coordinate convention; they do not move motors by themselves.
2. Read and save your robot's supported default posture before using reset. With legs involved, support the torso and unload both legs. A default posture is local robot-specific data, not a universal standing configuration.
3. Adjust a pose, **Save pose + reset**, then **Play saved pose** to check it. This can involve all joints included in the pose. Continue to Voice.
4. **Voice:** type a greeting, choose voice and delivery, and use Computer preview. Send to robot is an optional hardware test: new recordings need USB upload, then USB removal for playback. “Finish without speaking” ends an uploaded preview without sending playback.
5. **Greetings:** choose or enter a person's name and save the prepared pose and voice together. Select that person later to play the greeting. The robot moves into the saved pose and speaks while holding it. Reset restores the saved default; it is a movement command.

## Conversation

1. Configure the API key/model in Settings. Select the shared voice and delivery in Voice.
2. Open Gesture library. Inspect actions imported from your own card. Rehearse only with the robot secured and all limbs clear. Save appropriate approved actions for Gemini selection.
3. Type a question, or click the microphone, speak, and click it again to finish. Review the transcribed text.
4. Confirm support and request the response with Ask Alpha. The model returns a concise new answer and selects from the approved action catalog. The UI reports the chosen gesture and reason.
5. Connect USB for fresh speech. Authorize the upload helper when prompted. Wait for verification, then unplug USB when instructed.
6. For a library gesture, speech and the action start through one paired playback command. For a saved greeting pose, the robot reaches the pose first and then speaks. Exact verified library pairs can replay wirelessly on a new explicit request.

Stop blocks subsequent commands. It cannot guarantee stopping a native action already accepted by the firmware. There is no automatic retry after uncertain command delivery.

## Storage

Storage is the central place to review recordings and permanently delete unwanted Studio-generated recordings. Deletion needs USB and authorization because it writes to the card, but does not request motor playback. Greetings' referenced audio is protected; edit or remove the greeting reference first. Keep responses you want to preserve. Temporary response cleanup is bounded and preserves original robot assets.

The original MUSIC directory has a finite entry capacity even if the card shows free bytes. Delete unwanted Studio recordings when it fills; do not expand or reformat the card to bypass the firmware's directory limitations.
