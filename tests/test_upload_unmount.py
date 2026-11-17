import unittest
from unittest.mock import Mock,patch
from alpha_demo import speech_upload as upload

class UnmountTests(unittest.TestCase):
    def paths(self,mounted):
        # Use MagicMock for filesystem operators without touching any device.
        from unittest.mock import MagicMock
        block=MagicMock();part=MagicMock();part.name='robot1'
        block.iterdir.return_value=[part];(part/'partition').exists.return_value=True
        (part/'dev').read_text.return_value='8:1';(block/'dev').read_text.return_value='8:0'
        mount=Mock();mount.read_text.side_effect=mounted
        return lambda value: block if str(value)=='/sys/robot' else mount
    def test_only_verified_partition_is_unmounted(self):
        with patch.object(upload,'Path',side_effect=self.paths(['1 2 8:1 / /mnt rw - vfat /dev/robot1 rw','',''])) ,patch.object(upload,'identify',return_value=(100,'/sys/robot')),patch.object(upload.subprocess,'run') as run,patch.object(upload,'emit'):
            run.return_value.returncode=0
            upload.unmount_verified_card('/dev/robot',100,'/sys/robot')
            run.assert_called_once_with(['/usr/bin/umount','--','/dev/robot1'],capture_output=True,text=True,timeout=20)
    def test_identity_change_blocks_unmount(self):
        with patch.object(upload,'Path',side_effect=self.paths([])),patch.object(upload,'identify',return_value=(200,'/sys/other')),patch.object(upload.subprocess,'run') as run:
            with self.assertRaises(ValueError):upload.unmount_verified_card('/dev/robot',100,'/sys/robot')
            run.assert_not_called()
