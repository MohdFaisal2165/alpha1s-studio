"""Manufacturer Joint ID map; command span is not a mechanical clearance limit."""
MOTORS = {
    1: ('Right inner shoulder', 'Right arm'), 2: ('Right outer shoulder', 'Right arm'),
    3: ('Right elbow', 'Right arm'), 4: ('Left inner shoulder', 'Left arm'),
    5: ('Left outer shoulder', 'Left arm'), 6: ('Left elbow', 'Left arm'),
    7: ('Right upper hip', 'Right leg'), 8: ('Right lower hip', 'Right leg'),
    9: ('Right knee', 'Right leg'), 10: ('Right upper ankle', 'Right leg'),
    11: ('Right lower ankle', 'Right leg'), 12: ('Left upper hip', 'Left leg'),
    13: ('Left lower hip', 'Left leg'), 14: ('Left knee', 'Left leg'),
    15: ('Left upper ankle', 'Left leg'), 16: ('Left lower ankle', 'Left leg'),
}
COMMAND_LIMITS = {sid: (0,180) for sid in MOTORS}
REVIEWED_LIMITS = {3: (45,90), 6: (90,135)}
# No unverified pitch/roll axes or full mechanical limits are inferred.
