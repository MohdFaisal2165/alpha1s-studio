import unittest
from alpha_demo.session_probe import PACKETS,ack,version_packet,version_reply
class SessionTests(unittest.TestCase):
    def test_packets(self):
        for p in list(PACKETS.values())+[version_packet(i) for i in (1,2,3)]:
            self.assertEqual(len(p),10);self.assertEqual(p[8],sum(p[2:8])&255)
        for x in (0,4,255,True,'1'):
            with self.assertRaises(ValueError):version_packet(x)
    def test_synthetic_version_and_acknowledgement_frames(self):
        fixtures={1:'fccf01aa15092501efed',2:'fccf02ee00000000f0ed',3:'fccf03ee00000000f1ed'}
        for servo,frame in fixtures.items():
            raw=bytes.fromhex(frame).ljust(64,b'\0')
            if servo==1:self.assertEqual(version_reply(raw,servo)['version_bytes_hex'],'15092501')
            else:
                with self.assertRaises(ValueError):version_reply(raw,servo)
        self.assertEqual(ack(bytes.fromhex('f44faaed').ljust(64,b'\0')),'acknowledged')
        with self.assertRaises(ValueError):ack(bytes.fromhex('f44feeed').ljust(64,b'\0'))
