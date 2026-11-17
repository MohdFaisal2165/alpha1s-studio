"""Fixed preview choreography. No servo values or robot action filenames."""
from types import MappingProxyType

MOTIONS = MappingProxyType({
    'idle': ('No action requested.',),
    'wave': ('Preview: raise greeting arm.', 'Preview: wave once.', 'Preview: return arm.'),
})
# A wave is NOT approved safe on hardware; calibration and rehearsal are outstanding.
HARDWARE_VALIDATED = frozenset()


def validate_call(name, arguments):
    if name != 'propose_motion' or type(arguments) is not dict:
        raise ValueError('Only propose_motion with an object is allowed')
    if set(arguments) != {'motion'}:
        raise ValueError('Exactly one motion field is required')
    motion = arguments['motion']
    if type(motion) is not str or motion not in MOTIONS:
        raise ValueError('Unknown motion')
    return motion
