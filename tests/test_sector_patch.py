import unittest
from alpha_demo.sector_patch import apply_patch_blocks

class SectorPatchTests(unittest.TestCase):
 def test_mismatch_never_writes(self):
  writes=[]
  with self.assertRaises(ValueError):
   apply_patch_blocks(bytes(1024),bytes(512)+b'X'*512,[1],[0],lambda s:b'Y'*512,lambda *a:writes.append(a),lambda:None,lambda *a:None)
  self.assertEqual(writes,[])
 def test_order_and_readback(self):
  before=bytes(1536);after=b'A'*512+bytes(512)+b'D'*512;disk=bytearray(before);order=[]
  def write(s,b):disk[s*512:(s+1)*512]=b;order.append(s);return 512
  apply_patch_blocks(before,after,[2,0],[1],lambda s:bytes(disk[s*512:(s+1)*512]),write,lambda:None,lambda *a:None)
  self.assertEqual(order,[2,0]);self.assertEqual(bytes(disk),after)
 def test_readback_failure_stops_before_directory_commit(self):
  writes=[]
  with self.assertRaises(IOError):
   apply_patch_blocks(bytes(1024),b'A'*1024,[1,0],[],lambda s:bytes(512),lambda s,b:(writes.append(s) or 512),lambda:None,lambda *a:None)
  self.assertEqual(writes,[1])
 def test_unlisted_image_change_rejected(self):
  with self.assertRaises(ValueError):
   apply_patch_blocks(bytes(1024),b'A'*1024,[0],[],lambda s:self.fail('Unexpected read'),None,None,None)
