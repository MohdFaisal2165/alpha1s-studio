import unittest
from alpha_demo.stop_playback import REQUEST, parse_reply

class StopTests(unittest.TestCase):
    def test_fixed_request(self):
        self.assertEqual(REQUEST.hex(),'f22f00000000000000ed')
    def test_reply(self):
        self.assertIn('acknowledged',parse_reply(bytes.fromhex('f22faaed').ljust(64,b'\0')))
        for raw in ('f22feeed','f11faaed','f22faaaaed','f22faa','f22faaed01'):
            with self.assertRaises(ValueError):parse_reply(bytes.fromhex(raw))
