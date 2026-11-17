import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from alpha_demo.audio_card import stage_audio
from alpha_demo import robot_speech as speech


def card():
    b=bytearray(512*96)
    b[510:512]=b'\x55\xaa';struct.pack_into('<I',b,454,1)
    off=512
    struct.pack_into('<H',b,off+11,512);b[off+13]=1
    struct.pack_into('<H',b,off+14,2);b[off+16]=2
    struct.pack_into('<I',b,off+32,95);struct.pack_into('<I',b,off+36,1)
    struct.pack_into('<I',b,off+44,2);struct.pack_into('<H',b,off+48,1)
    b[1024:1028]=b'RRaA';b[1508:1512]=b'rrAa';struct.pack_into('<I',b,1512,80)
    for fat in (3,4):
        for c in range(6):struct.pack_into('<I',b,fat*512+c*4,0x0fffffff)
    # data sector5 root(cluster2),6 MUSIC(cluster3),7 ACTION(cluster4),8 existing file(cluster5)
    for o,name,c in ((2560,b'MUSIC      ',3),(2592,b'ACTION     ',4)):
        b[o:o+11]=name;b[o+11]=16;struct.pack_into('<H',b,o+26,c)
    b[3072:3083]=b'ORIGINALMP3';b[3083]=32;struct.pack_into('<H',b,3098,5);struct.pack_into('<I',b,3100,512)
    b[4096:4608]=b'K'*512
    return bytes(b)

class AudioCardTests(unittest.TestCase):
    def test_upload_preserves_existing_data_and_commits_directory_last(self):
        old=card();audio=b'new audio'*100
        before,after,order,metadata=stage_audio(old,lambda s:old[s*512:(s+1)*512],audio,'S123ABCD')
        self.assertEqual(before,old);self.assertEqual(order[-1],6)
        self.assertEqual(after[3072:3104],old[3072:3104]);self.assertEqual(after[4096:4608],old[4096:4608])
        self.assertEqual(after[3104:3115],b'S123ABCDMP3')
        self.assertEqual(after[4608:4608+len(audio)],audio)
        self.assertEqual(after[1536:2048],after[2048:2560])
        # A second upload sees the first from live metadata, even with the old backup.
        _,twice,second_order,_=stage_audio(old,lambda s:bytes(after[s*512:(s+1)*512]),b'next','S123ABCE')
        self.assertEqual(twice[3104:3136],after[3104:3136])
        self.assertFalse({9,10}&set(second_order))  # Existing audio sectors are never written.
        disk=bytearray(after)
        for sector in second_order:disk[sector*512:(sector+1)*512]=twice[sector*512:(sector+1)*512]
        self.assertEqual(disk[4608:5632],after[4608:5632])
    def test_rejects_existing_name_fat_disagreement_and_changed_boot(self):
        old=card();_,after,_,_=stage_audio(old,lambda s:old[s*512:(s+1)*512],b'a','S123ABCD')
        with self.assertRaisesRegex(ValueError,'already exists'):stage_audio(old,lambda s:bytes(after[s*512:(s+1)*512]),b'a','S123ABCD')
        for sector in (1,4):
            bad=bytearray(old);bad[sector*512+100]^=1
            with self.assertRaises(ValueError):stage_audio(old,lambda s:bytes(bad[s*512:(s+1)*512]),b'a','S123ABCD')
    def test_full_directory_and_card_leave_input_unchanged(self):
        for kind in ('space',):
            bad=bytearray(card())
            if kind=='directory':bad[3072:3584]=b'X'*512
            else:
                for fat in (3,4):
                    for c in range(6,93):struct.pack_into('<I',bad,fat*512+c*4,0x0fffffff)
            original=bytes(bad)
            with self.assertRaises(ValueError):stage_audio(original,lambda s:original[s*512:(s+1)*512],b'abc','S123ABCD')
            self.assertEqual(bytes(bad),original)

class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);(self.folder/'speech.mp3').write_bytes(b'audio')
        sha=hashlib.sha256(b'audio').hexdigest()
        self.job={'directory':str(self.folder),'name':'S123ABCD','sha256':sha,'status':'uploaded','playback_attempted':False,'upload':{'sha256':sha}}
        speech.save_job(self.job)
    def test_missing_device_does_not_send_and_can_reconnect(self):
        with patch.object(speech,'find_device',side_effect=ValueError('missing')),patch.object(speech,'hid_command') as send:
            with self.assertRaises(ValueError):speech.play_job(self.job)
            send.assert_not_called();self.assertFalse(self.job['playback_attempted'])
    def test_uncertain_delivery_is_never_retried(self):
        with patch.object(speech,'find_device'),patch.object(speech,'hid_command',side_effect=TimeoutError('no reply')) as send:
            with self.assertRaises(TimeoutError):speech.play_job(self.job)
            with self.assertRaises(ValueError):speech.play_job(self.job)
            self.assertEqual(send.call_count,1)
    def test_unverified_and_changed_audio_never_send(self):
        (self.folder/'speech.mp3').write_bytes(b'changed')
        with patch.object(speech,'hid_command') as send:
            with self.assertRaises(ValueError):speech.play_job(self.job)
            send.assert_not_called()
    def test_accepted_exactly_once(self):
        with patch.object(speech,'find_device'),patch.object(speech,'hid_command',return_value=(bytes.fromhex('f33faaed'),[])) as send:
            result=speech.play_job(self.job)
            self.assertEqual(result['status'],'playback_accepted')
            send.assert_called_once_with(speech.packet('S123ABCD'))
            with self.assertRaises(ValueError):speech.play_job(self.job)
    def test_arbitrary_names_rejected(self):
        for name in ('dance','../file','FAISAL01','S123ABC;'):
            with self.assertRaises(ValueError):speech.packet(name)

class UploadWorkflowTests(unittest.TestCase):
    def test_cancelled_authorization_never_plays(self):
        import io
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp:
            job={'directory':tmp,'name':'S123ABCD','status':'prepared','playback_attempted':False}
            process=MagicMock();process.stdout=io.StringIO('');process.stderr=io.StringIO('dismissed');process.wait.return_value=126
            block=MagicMock();block.resolve.return_value.iterdir.return_value=[]
            real_path=Path
            def path(value):
                return block if str(value)=='/sys/class/block' else real_path(value)
            block.__truediv__.return_value=block
            with patch.object(speech,'upload_prerequisites'),patch.object(speech,'storage_devices',return_value=['/dev/mock']),patch.object(speech.time,'sleep'),patch.object(speech,'Path',side_effect=path),patch.object(speech.subprocess,'run') as run,patch('alpha_demo.upload_session.upload',side_effect=ValueError('Authorization cancelled')),patch.object(speech,'hid_command') as hid:
                run.return_value.returncode=1
                with self.assertRaisesRegex(ValueError,'Authorization'):speech.prepare_upload(job,lambda text:None)
                hid.assert_not_called()
                self.assertEqual(job['status'],'upload_failed')
    def test_unresolved_write_blocks_new_upload(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(speech,'ROOT',Path(tmp)):
            folder=Path(tmp)/'data/robot-speech/old';folder.mkdir(parents=True)
            (folder/'card-journal.json').write_text('{}')
            (folder/'job.json').write_text('{"status":"upload_failed"}')
            with self.assertRaisesRegex(ValueError,'inspection'):speech.new_job({},'hello')
