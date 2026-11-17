# Verification checklist

Run all offline tests with Xvfb before changing a release. Hardware tests are separate and require explicit operator readiness.

- Clean export launches without a robot or private state.
- Card setup rejects mounted media, wrong identity, unsupported size and conflicting existing state.
- Import rejects mismatched FAT copies, cyclic/crosslinked files, path traversal and truncated data.
- A fresh pair verifies both hashes before playback; no replay follows uncertain delivery.
- Cancellation after upload prevents playback; no robot commands run in offline tests.
- A hardware observer confirms audible completion and gesture overlap; command acknowledgment is not treated as proof.

For a hardware rehearsal, secure the robot with all limbs and cables clear and the power switch reachable. New speech requires USB upload followed by removal. Native actions may move all 16 joints and include a final posture. Never run a hardware rehearsal merely to check a documentation or packaging change.
