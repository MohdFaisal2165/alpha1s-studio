import struct
import unittest
from alpha_demo.card_import import files_from_image,inventory


def image():
    raw=bytearray(16*512);raw[510:512]=b'\x55\xaa';struct.pack_into('<II',raw,454,1,15)
    b=512;struct.pack_into('<H',raw,b+11,512);raw[b+13]=1;struct.pack_into('<H',raw,b+14,1);raw[b+16]=2;struct.pack_into('<I',raw,b+36,1);struct.pack_into('<I',raw,b+44,2)
    for fat in (2,3):
        for c in (2,3):struct.pack_into('<I',raw,fat*512+c*4,0xfffffff)
    raw[2048:2059]=b'TEST    HTS';raw[2059]=32;struct.pack_into('<H',raw,2074,3);struct.pack_into('<I',raw,2076,3);raw[2560:2563]=b'abc'
    return raw

class CardImportTests(unittest.TestCase):
    def test_extract_and_inventory(self):
        files=files_from_image(bytes(image()));self.assertEqual(files,{'TEST.HTS':b'abc'})
        self.assertEqual(inventory(files)[0]['bytes'],3)
    def test_mismatched_fat_rejected(self):
        raw=image();raw[2*512+12]=0
        with self.assertRaises(ValueError):files_from_image(raw)
    def test_cycle_rejected(self):
        raw=image()
        for fat in (2,3):struct.pack_into('<I',raw,fat*512+12,3)
        with self.assertRaises(ValueError):files_from_image(raw)
    def test_truncated_file_rejected(self):
        raw=image();struct.pack_into('<I',raw,2076,1000)
        with self.assertRaises(ValueError):files_from_image(raw)
    def test_unsafe_filename_rejected(self):
        raw=image();raw[2048:2056]=b'../BAD  '
        with self.assertRaises(ValueError):files_from_image(raw)
    def test_crosslink_rejected(self):
        raw=image();raw[2080:2112]=raw[2048:2080];raw[2080:2088]=b'OTHER   '
        with self.assertRaises(ValueError):files_from_image(raw)
