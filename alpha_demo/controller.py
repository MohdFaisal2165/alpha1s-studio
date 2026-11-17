"""Local review, expiry and single-use proposals. Hardware always blocked."""
from dataclasses import dataclass
import time
from .motions import MOTIONS, validate_call


@dataclass(frozen=True)
class Proposal:
    motion: str
    created: float


class Controller:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.pending = None

    def propose(self, name, arguments):
        self.pending = None  # Invalid replacement must also clear the old proposal.
        motion = validate_call(name, arguments)
        self.pending = Proposal(motion, self.clock())
        return self.pending

    def cancel(self):
        self.pending = None

    def preview(self):
        p, self.pending = self.pending, None
        if p is None or not 0 <= self.clock() - p.created <= 30:
            raise ValueError('Missing or expired proposal')
        return MOTIONS[p.motion]

    def execute_hardware(self):
        self.cancel()
        raise PermissionError('Hardware disabled: protocol validation and explicit approval required')
