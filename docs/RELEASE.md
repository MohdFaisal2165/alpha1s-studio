# Release process

The active development installation holds private device state. Publish only a new allowlisted export:

```bash
/usr/bin/python3 scripts/export_release.py
```

The exporter creates `release/alpha1s-studio-*`, copies source, tests, original assets and documentation, scans for credential/address/private-path patterns, creates empty runtime folder placeholders and writes a SHA-256 manifest. It never publishes or copies runtime content.

Run the full offline tests from the export under Xvfb. Check that the exported UI launches without local device data. Publish that folder as the repository, and attach a ZIP plus SHA-256 checksum to a versioned GitHub release. Do not include the development card backup, vendor actions, logs, keys, settings or personal recordings.

Version 0.3.0 is an experimental Linux source distribution. First-run setup is supplied as a documented CLI; it has offline validation, with physical onboarding on a second robot still pending. The existing Studio integration was observed on the documented development configuration. A signed installer, automatic updater and cross-platform deployment are not provided.
