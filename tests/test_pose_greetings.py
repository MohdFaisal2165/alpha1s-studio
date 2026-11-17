import copy,tempfile,threading,unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock,patch
from alpha_demo import pose_greetings as p

class PoseTests(unittest.TestCase):
    def setUp(self):
        self.robot=Mock();self.robot.armed=threading.Event();self.robot.armed.set()
        self.robot.limits={i:(0,180) for i in range(1,7)};self.robot.saved_limits={}
        self.robot.run_pair.return_value={'status':'ok'}
        self.robot.run.side_effect=lambda sid,*a,**kw:{'status':'ok','baseline_degrees':80+sid}
    def test_capture_is_fresh_all_six_no_old_targets(self):
        self.robot.targets={i:0 for i in range(1,7)}
        pose=p.capture(self.robot)
        self.assertEqual(pose,{str(i):80+i for i in range(1,7)})
        self.assertEqual([c.args for c in self.robot.run.call_args_list],[(i,) for i in range(1,7)])
        for c in self.robot.run.call_args_list:self.assertEqual(c.kwargs,{'setup':True,'support_confirmed':True})
    def test_fault_does_not_return_partial_pose_or_continue(self):
        self.robot.run.side_effect=[{'status':'ok','baseline_degrees':90},{'status':'error','error':'fault'}]
        with self.assertRaisesRegex(ValueError,'fault'):p.capture(self.robot)
        self.assertEqual(self.robot.run.call_count,2)
    def test_disarm_cancels_capture_before_next_joint(self):
        def first(*a,**kw):self.robot.armed.clear();return {'status':'ok','baseline_degrees':90}
        self.robot.run.side_effect=first
        with self.assertRaisesRegex(ValueError,'Stopped'):p.capture(self.robot)
        self.assertEqual(self.robot.run.call_count,1)
    def test_reset_never_reads_releases_or_addresses_legs(self):
        p.move_to_pose(self.robot,p.RESET_POSE,reset=True)
        self.assertEqual([c.args[0] for c in self.robot.run_pair.call_args_list],[{3:90,6:90},{2:90,5:90},{1:90,4:90}])
        self.robot.run.assert_not_called()
    def test_all_target_limits_checked_before_pose_changes(self):
        self.robot.saved_limits={6:(0,85)}
        with self.assertRaisesRegex(ValueError,'saved limits'):p.move_to_pose(self.robot,p.RESET_POSE)
        self.robot.run.assert_not_called();self.robot.run_pair.assert_not_called()
    def test_invalid_pose_rejected_without_io(self):
        for pose in ({}, {'1':90}, {str(i):True for i in range(1,7)}, {str(i):181 for i in range(1,7)}):
            with self.assertRaises(ValueError):p.move_to_pose(self.robot,pose)
        self.robot.run.assert_not_called();self.robot.run_pair.assert_not_called()
    def test_play_pose_then_verified_audio_without_upload(self):
        profile={'pose':p.RESET_POSE,'audio':'FAISAL01','text':'Hello'}
        with patch.object(p,'saved_audio',return_value={'FAISAL01':{'text':'Hello'}}),patch('alpha_demo.hold_speech.prepare',return_value=('player','wav',1)),patch('alpha_demo.hold_speech.play') as audio,patch.object(p,'prepare_upload') as upload:
            p.play(self.robot,profile,speaker='computer')
            self.assertEqual(self.robot.run_pair.call_count,3);audio.assert_called_once();upload.assert_not_called()
            self.assertTrue(all(not c.kwargs.get('setup') for c in self.robot.run.call_args_list))
    def test_missing_audio_prevents_capture_and_motion(self):
        with patch.object(p,'saved_audio',return_value={}),patch('alpha_demo.hold_speech.prepare',return_value=('player','wav',1)):
            with self.assertRaises(ValueError):p.play(self.robot,{'pose':p.RESET_POSE,'audio':'missing','text':'Hi'},speaker='computer')
        self.robot.run.assert_not_called();self.robot.run_pair.assert_not_called()
    def test_audio_not_sent_after_motion_error(self):
        with patch.object(p,'saved_audio',return_value={'a':{'text':'Hi'}}),patch.object(p,'move_to_pose',side_effect=ValueError('fault')),patch('alpha_demo.hold_speech.prepare',return_value=('player','wav',1)),patch('alpha_demo.hold_speech.play') as audio:
            with self.assertRaises(ValueError):p.play(self.robot,{'pose':p.RESET_POSE,'audio':'a','text':'Hi'},speaker='computer')
            audio.assert_not_called()
    def test_save_roundtrip_preserves_each_person_pose(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'saved_audio',return_value={'a':{'text':'Hi'}}),patch.object(p,'load_profiles',return_value={}):
            root=Path(tmp)
            p.save('Faisal','Hi',p.RESET_POSE,'a',root)
            second=copy.deepcopy(p.RESET_POSE);second['3']=110
            p.save('Someone','Hi',second,'a',root)
            profiles=p.load(root)
            self.assertEqual(len(profiles),2)
            self.assertEqual(next(x['pose'] for x in profiles.values() if x['name']=='Faisal'),p.RESET_POSE)
    def test_save_same_audio_requires_no_connection_or_upload(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'saved_audio',return_value={'a':{'text':'Hi'}}),patch.object(p,'load_profiles',return_value={}),patch.object(p,'prepare_upload') as upload,patch.object(p,'synthesize') as synth:
            result=p.prepare('Faisal','Hi',p.RESET_POSE,root=Path(tmp))
            self.assertFalse(result['reconnect']);upload.assert_not_called();synth.assert_not_called()
    def test_new_message_uploads_before_saving_and_requests_reconnect(self):
        with patch.object(p,'saved_audio',return_value={}),patch.object(p,'synthesize',return_value={'mp3':'mock'}),patch.object(p,'new_job',return_value={'name':'S123ABCD'}) as job,patch.object(p,'prepare_upload') as upload,patch.object(p,'save',return_value={}) as save:
            result=p.prepare('Faisal','New',p.RESET_POSE)
            upload.assert_called_once();save.assert_called_once();self.assertTrue(result['reconnect'])
    def test_failed_upload_does_not_replace_profile(self):
        with patch.object(p,'saved_audio',return_value={}),patch.object(p,'synthesize',return_value={}),patch.object(p,'new_job',return_value={}),patch.object(p,'prepare_upload',side_effect=ValueError('failure')),patch.object(p,'save') as save:
            with self.assertRaises(ValueError):p.prepare('Faisal','New',p.RESET_POSE)
            save.assert_not_called()

    def test_robot_speaker_route_is_blocked_before_any_motion(self):
        with patch.object(p,'play_saved') as audio:
            with self.assertRaisesRegex(ValueError,'resets'):p.play(self.robot,{'pose':p.RESET_POSE,'audio':'a','text':'Hi'})
            audio.assert_not_called();self.robot.run.assert_not_called();self.robot.run_pair.assert_not_called()

    def test_computer_greeting_sends_only_saved_targets_never_neutral(self):
        pose={str(i):60+i for i in range(1,7)}
        with patch.object(p,'saved_audio',return_value={'a':{'text':'Hi'}}),patch('alpha_demo.hold_speech.prepare',return_value=('player','wav',1)),patch('alpha_demo.hold_speech.play') as computer,patch.object(p,'play_saved') as robot_audio:
            p.play(self.robot,{'pose':pose,'audio':'a','text':'Hi'},speaker='computer')
            self.assertEqual([c.args[0] for c in self.robot.run_pair.call_args_list],[{1:61,4:64},{2:62,5:65},{3:63,6:66}])
            computer.assert_called_once();robot_audio.assert_not_called()

    def test_pair_fault_blocks_later_pairs(self):
        self.robot.run_pair.return_value={'status':'error','error':'pair fault'}
        with self.assertRaisesRegex(ValueError,'pair fault'):p.move_to_pose(self.robot,p.RESET_POSE)
        self.assertEqual(self.robot.run_pair.call_count,1)

    def test_stop_between_pairs(self):
        def stop(*a,**kw):
            self.robot.armed.clear()
            return {'status':'ok'}
        self.robot.run_pair.side_effect=stop
        with self.assertRaisesRegex(ValueError,'Stopped'):p.move_to_pose(self.robot,p.RESET_POSE)
        self.assertEqual(self.robot.run_pair.call_count,1)

    def test_saved_profiles_reload_and_replay_repeatedly_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'saved_audio',return_value={'a':{'text':'Hi'}}),patch.object(p,'load_profiles',return_value={}),patch('alpha_demo.hold_speech.prepare',return_value=('player','wav',1)),patch('alpha_demo.hold_speech.play') as audio:
            root=Path(tmp)
            p.save('Faisal','Hi',p.RESET_POSE,'a',root)
            other={str(i):70+i for i in range(1,7)}
            p.save('LeProf','Hi',other,'a',root)
            original=(root/'data/pose-greetings.json').read_bytes()
            for profile in p.load(root).values():
                self.robot.run_pair.return_value={'status':'error','error':'0xEE'}
                with self.assertRaisesRegex(ValueError,'0xEE'):p.play(self.robot,profile,speaker='computer')
                self.robot.run_pair.return_value={'status':'ok'}
                for _ in range(2):p.play(self.robot,profile,speaker='computer')
            self.assertEqual(audio.call_count,4)
            self.assertEqual((root/'data/pose-greetings.json').read_bytes(),original)

    def test_wireless_greeting_checks_audio_then_pose_then_speech(self):
        self.robot.supports_robot_speech=True
        self.robot.sequence.side_effect=nullcontext
        profile={'pose':p.RESET_POSE,'audio':'a','text':'Hi'}
        with patch.object(p,'saved_audio',return_value={'a':{'text':'Hi'}}),patch('alpha_demo.hold_speech.play') as computer:
            p.play(self.robot,profile,speaker='robot')
        self.robot.prepare_robot_audio.assert_called_once_with('a')
        self.assertEqual(self.robot.run_pair.call_count,3)
        self.robot.play_robot_audio.assert_called_once_with(self.robot.prepare_robot_audio.return_value)
        computer.assert_not_called()
    def test_wireless_missing_audio_prevents_all_moves(self):
        self.robot.supports_robot_speech=True
        self.robot.sequence.side_effect=nullcontext
        self.robot.prepare_robot_audio.side_effect=ValueError('missing clip')
        with self.assertRaisesRegex(ValueError,'missing clip'):
            p.play(self.robot,{'pose':p.RESET_POSE,'audio':'a','text':'Hi'})
        self.robot.run_pair.assert_not_called();self.robot.play_robot_audio.assert_not_called()
