import unittest
from alpha_demo.elbow_trial import movement_packet,parse_position

class ElbowTrialTests(unittest.TestCase):
    def test_synthetic_position_frame(self):
        # Synthetic protocol fixture; no private hardware report needed.
        raw=bytes.fromhex('faaf03aa0000005906ed').ljust(64,b'\0')
        self.assertEqual(parse_position(raw),89)
        for index in (0,2,3,8,9,20):
            bad=bytearray(raw);bad[index]^=1
            if index in (2,3):bad[8]=sum(bad[2:8])&255
            with self.assertRaises(ValueError):parse_position(bytes(bad))
    def test_fixed_target_and_fresh_angle_guard(self):
        self.assertEqual(movement_packet(89).hex(),'faaf03015a0a000a72ed')
        for angle in (88,89,91):self.assertEqual(movement_packet(angle),movement_packet(89))
        for angle in (-1,0,87,90,92,180,True,89.0,'89',None):
            with self.assertRaises(ValueError):movement_packet(angle)
