import unittest
from alpha_demo.identify import report, parse, REQUESTS

class IdentifyTests(unittest.TestCase):
    def test_only_version_requests(self):
        self.assertEqual(set(REQUESTS),{'hardware','firmware'})
        self.assertEqual(REQUESTS['hardware'].hex(),'f11f00000000000000ed')
        self.assertEqual(REQUESTS['firmware'].hex(),'f55f01000000000001ed')
        for kind in REQUESTS:
            r=report(kind)
            self.assertEqual(len(r),65)
            self.assertEqual(r[0],0)
        with self.assertRaises(KeyError):report('move')

    def test_versions(self):
        for kind,head,data,value in [('hardware',b'\xf1\x1f',b'\x0bAlpha1_V2.0','Alpha1_V2.0'),
                                    ('firmware',b'\xf5\x5f',b'\xaa2015121520','2015121520')]:
            # Hardware fixture length equals actual string byte count.
            if kind=='hardware':data=bytes([len(value)])+value.encode()
            raw=head+data+bytes([sum(data)&255,0xed])
            self.assertEqual(parse(kind,raw.ljust(64,b'\0')),value)
            for bad in (raw[:3],bytes([0])+raw[1:],raw[:-2]+b'\0\xed',raw+b'\1'):
                with self.assertRaises(ValueError):parse(kind,bad)
