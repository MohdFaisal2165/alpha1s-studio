# Contributing

Use system Python and run the offline unittest suite before submitting a change. UI tests require a desktop or Xvfb. Keep hardware calls mocked in automated tests. Do not use a connected robot to verify routine code edits.

Describe the problem, behavior change, tests and any hardware observations in the pull request. Keep observed behavior separate from inference. Preserve no-retry behavior for uncertain command delivery and verify command limits before any write.

Never commit API keys, robot addresses, recordings, profiles, raw card images, firmware or personal diagnostics. Use synthetic fixtures. New device variants require documented identity/protocol review, not removal of the existing guard.

The source-checkout layout is intentional: upload helper and runtime directories resolve relative to the project. Wheel-based distribution remains future work. First-run card onboarding is provided by scripts/setup_robot.py and must be tested offline using synthetic files before any operator-authorized hardware validation.
