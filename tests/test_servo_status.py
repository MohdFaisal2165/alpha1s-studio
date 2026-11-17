import unittest
from alpha_demo.servo_status import REQUEST, parse_reply
class StatusTests(unittest.TestCase):
    def test_fixed_read(self):
        self.assertEqual(REQUEST.hex(),'effe00000000000000ed')
    def test_validation(self):
        self.assertEqual(parse_reply(bytes.fromhex('effe0000000000ed'))['set_bit_count'],0)
        self.assertEqual(parse_reply(bytes.fromhex('effeffff0000feed'))['set_bit_count'],16)
        for bad in ('effe0000000001ed','f22faaed','effe0000000000ed01'):
            with self.assertRaises(ValueError):parse_reply(bytes.fromhex(bad))
