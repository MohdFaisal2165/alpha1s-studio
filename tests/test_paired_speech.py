import json,hashlib,tempfile,threading,unittest
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import Mock,patch
from test_robot_speech import card
from alpha_demo.audio_card import stage_audio
from alpha_demo import paired_speech as pair,conversation_speech as flow

class PairedCardTests(unittest.TestCase):
    def test_pair_preserves_existing_files_and_commits_both_directories_last(self):
        original=card();action=b'H'*99;audio=b'A'*700
        before,after,order,metadata=stage_audio(original,lambda s:original[s*512:(s+1)*512],audio,'S123ABCD',action)
        self.assertEqual(before,original);self.assertEqual(order[-2:],[6,7])
        self.assertEqual(after[4096:4608],original[4096:4608])
        self.assertEqual(after[3072:3104],original[3072:3104])
        self.assertEqual(after[3104:3115],b'S123ABCDMP3')
        self.assertEqual(after[3584:3595],b'S123ABCDHTS')
        audio_cluster=int.from_bytes(after[3130:3132],'little')
        action_cluster=int.from_bytes(after[3610:3612],'little')
        self.assertNotEqual(audio_cluster,action_cluster)
        offset=(5+action_cluster-2)*512;self.assertEqual(after[offset:offset+99],action)
        self.assertEqual(after[1536:2048],after[2048:2560])
        with self.assertRaises(ValueError):stage_audio(original,lambda s:after[s*512:(s+1)*512],audio,'S123ABCD',action)
    def test_compatible_pair_uses_original_directories_or_rejects(self):
        original=card()
        _,after,order,_=stage_audio(original,lambda s:original[s*512:(s+1)*512],b'a','S123ABCD',b'H'*99,firmware_compatible=True)
        self.assertEqual(order[-2:],[6,7])
        self.assertEqual(after[3104:3115],b'S123ABCDMP3')
        self.assertEqual(after[3584:3595],b'S123ABCDHTS')
        for sector in (6,7):
            full=bytearray(original);full[sector*512:(sector+1)*512]=b'X'*512
            with self.assertRaisesRegex(ValueError,'directory space is full'):
                stage_audio(bytes(full),lambda s:bytes(full[s*512:(s+1)*512]),b'a','S123ABCD',b'H'*99,firmware_compatible=True)
    def test_compatible_pair_can_use_existing_action_chain_without_growing(self):
        import struct
        raw=bytearray(card());raw[3584:4096]=b'X'*512
        for fat in (3,4):
            struct.pack_into('<I',raw,fat*512+4*4,6)
            struct.pack_into('<I',raw,fat*512+6*4,0x0fffffff)
        before,after,order,_=stage_audio(bytes(raw),lambda s:bytes(raw[s*512:(s+1)*512]),b'a','S123ABCD',b'H'*99,firmware_compatible=True)
        self.assertEqual(after[4608:4619],b'S123ABCDHTS')
        self.assertEqual(order[-2:],[6,9])
        self.assertEqual(after[3584:4096],raw[3584:4096])
        self.assertEqual(int.from_bytes(after[3*512+6*4:3*512+7*4],'little'),0x0fffffff)
    def test_full_action_directory_expands_without_overwriting(self):
        raw=bytearray(card());raw[3584:4096]=b'X'*512
        before,after,order,_=stage_audio(bytes(raw),lambda s:bytes(raw[s*512:(s+1)*512]),b'a','S123ABCD',b'H'*99)
        self.assertEqual(before,raw);self.assertEqual(after[3584:4096],raw[3584:4096])
        self.assertIn(b'S123ABCDHTS',after)

class PairedPlaybackTests(unittest.TestCase):
    def test_one_native_command_and_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);audio=b'audio';sha=hashlib.sha256(audio).hexdigest();(folder/'speech.mp3').write_bytes(audio)
            job={'directory':tmp,'name':'S123ABCD','sha256':sha,'status':'uploaded','playback_attempted':False,'action':{'key':'celebrate','sha256':'action'},'upload':{'name':'S123ABCD','sha256':sha,'action_sha256':'action','firmware_compatible_directories':True}}
            (folder/'job.json').write_text(json.dumps(job));robot=Mock();session=Mock();session.exchange.return_value=b'\x00'
            @contextmanager
            def operation(kind):yield session,{},lambda:None
            robot.operation=operation
            with patch.object(pair,'validate_action',return_value=(b'action',{'sha256':'action','seconds':2})),patch.object(pair.time,'sleep'):
                pair.play(robot,job,3)
                session.exchange.assert_called_once_with(3,b'ACTION/S123ABCD.hts')
                with self.assertRaises(ValueError):pair.play(robot,job,3)
                pair.play(robot,job,3,replay=True)
                self.assertEqual(session.exchange.call_count,2)
                session.exchange.side_effect=TimeoutError('uncertain')
                with self.assertRaises(TimeoutError):pair.play(robot,job,3,replay=True)
                with self.assertRaises(ValueError):pair.play(robot,job,3,replay=True)
                self.assertEqual(session.exchange.call_count,3)
    def test_old_placement_or_deleted_pair_cannot_play(self):
        for flags in ({'upload':{}},{'upload':{'firmware_compatible_directories':True},'card_deleted':True}):
            with tempfile.TemporaryDirectory() as tmp:
                job={'directory':tmp,'name':'S123ABCD','sha256':'hash','action':{},'status':'uploaded',**flags}
                (Path(tmp)/'job.json').write_text(json.dumps(job));robot=Mock()
                with self.assertRaises(ValueError):pair.play(robot,job,2)
                robot.operation.assert_not_called()
    def test_incomplete_pair_never_commands_robot(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);sha=hashlib.sha256(b'a').hexdigest();(folder/'speech.mp3').write_bytes(b'a')
            job={'directory':tmp,'name':'S123ABCD','sha256':sha,'status':'uploaded','action':{'key':'celebrate','sha256':'action'},'upload':{'sha256':sha,'name':'S123ABCD'}}
            (folder/'job.json').write_text(json.dumps(job));robot=Mock()
            with patch.object(pair,'validate_action',return_value=(b'action',{'sha256':'action'})):
                with self.assertRaises(ValueError):pair.play(robot,job,1)
            robot.operation.assert_not_called()

class ReplayTests(unittest.TestCase):
    def test_cached_text_replays_without_upload(self):
        with patch.object(flow,'bluetooth_address',return_value='configured'),patch('alpha_demo.greetings.saved_audio',return_value={'S123ABCD':{'text':'Hello'}}),patch.object(flow,'alpha_usb_present',return_value=False),patch.object(flow,'BluetoothRobot') as factory,patch.object(flow.robot_speech,'prepare_upload') as upload:
            flow.replay_saved('Hello',threading.Event())
            factory.return_value.prepare_robot_audio.assert_called_once_with('S123ABCD')
            factory.return_value.play_robot_audio.assert_called_once();upload.assert_not_called()
    def test_unknown_text_or_attached_usb_never_plays(self):
        for text in ('Hello','New'):
            with patch('alpha_demo.greetings.saved_audio',return_value={'S123ABCD':{'text':'Hello'}}),patch.object(flow,'alpha_usb_present',return_value=True),patch.object(flow,'BluetoothRobot') as factory:
                with self.assertRaises(ValueError):flow.replay_saved(text,threading.Event())
                factory.assert_not_called()

class SavedPairTests(unittest.TestCase):
    def test_cache_requires_exact_verified_approved_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'data/robot-speech/job';folder.mkdir(parents=True)
            sha=hashlib.sha256(b'audio').hexdigest();(folder/'speech.mp3').write_bytes(b'audio')
            job={'directory':str(folder),'name':'S123ABCD','text':'Hello','voice':'Kore','style':'neutral','audio_seconds':4,'sha256':sha,'status':'playback_accepted','action':{'key':'celebrate','sha256':'action'},'upload':{'status':'complete','name':'S123ABCD','sha256':sha,'action_sha256':'action','firmware_compatible_directories':True}}
            def save():(folder/'job.json').write_text(json.dumps(job))
            save()
            with patch.object(pair.robot_speech,'ROOT',root),patch.object(pair,'validate_action',return_value=(b'action',{'sha256':'action'})):
                self.assertIsNotNone(pair.find_saved('Hello','Kore','neutral','celebrate'))
                self.assertIsNone(pair.find_saved('Hello','Leda','neutral','celebrate'))
                self.assertIsNone(pair.find_saved('Hello','Kore','neutral','success'))
                for key,value in [('delete_requested',True),('status','playback_uncertain')]:
                    old=job.get(key);job[key]=value;save()
                    self.assertIsNone(pair.find_saved('Hello','Kore','neutral','celebrate'))
                    job[key]=old;save()
                (folder/'speech.mp3').write_bytes(b'changed')
                self.assertIsNone(pair.find_saved('Hello','Kore','neutral','celebrate'))
