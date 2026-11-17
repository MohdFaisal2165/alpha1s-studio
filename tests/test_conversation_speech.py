import threading
import unittest
from unittest.mock import patch,Mock
from alpha_demo import conversation_speech as flow
from alpha_demo.teacher import spoken_sentence,validate_response

class SentenceTests(unittest.TestCase):
    def test_first_sentence_not_full_paragraph(self):
        self.assertEqual(spoken_sentence('Robots use sensors. They also use motors.'),'Robots use sensors.')
        self.assertEqual(spoken_sentence('The value is 3.14 units. More detail.'),'The value is 3.14 units.')
        self.assertEqual(spoken_sentence('Dr. Smith teaches robotics. Welcome.'),'Dr. Smith teaches robotics.')
    def test_long_sentence_is_not_silently_truncated(self):
        with self.assertRaises(ValueError):spoken_sentence('word '*50)
    def test_model_response_is_bounded_before_execution(self):
        args={'heard':'What?', 'answer':'Sensors measure the world. Additional information.', 'gesture':'none','reason':'Explain'}
        value=validate_response({'name':'respond_to_participant','args':args},{'none':{}})
        self.assertEqual(value['answer'],'Sensors measure the world.')

class FreshSpeechTests(unittest.TestCase):
    def setUp(self):
        self.cancel=threading.Event();self.progress=Mock()
        save=patch.object(flow.robot_speech,'save_job');save.start();self.addCleanup(save.stop)
        patcher=patch.object(flow,'bluetooth_address',return_value='configured');patcher.start();self.addCleanup(patcher.stop)
    def test_upload_then_reconnect_then_one_playback(self):
        order=[]
        with patch.object(flow.speech,'synthesize',side_effect=lambda *a:order.append('generate') or {}),patch.object(flow.robot_speech,'new_job',return_value={'name':'test'}),patch.object(flow.robot_speech,'prepare_upload',side_effect=lambda *a:order.append('upload')),patch.object(flow,'wait_for_playback_interface',side_effect=lambda *a:order.append('reconnect')),patch.object(flow,'play_uploaded',side_effect=lambda *a,**k:order.append('play') or {}) as play:
            flow.speak_fresh('Hello.',self.cancel,self.progress)
        self.assertEqual(order,['generate','upload','reconnect','play']);play.assert_called_once()
    def test_library_pair_attached_before_upload_and_single_playback(self):
        order=[]
        with patch.object(flow.speech,'synthesize',return_value={'seconds':4}),patch.object(flow.robot_speech,'new_job',return_value={}),patch.object(flow.paired_speech,'attach',side_effect=lambda *a:order.append('attach')),patch.object(flow.robot_speech,'prepare_upload',side_effect=lambda *a:order.append('upload')),patch.object(flow,'wait_for_playback_interface',side_effect=lambda *a:order.append('unplug')),patch.object(flow,'play_paired',side_effect=lambda *a:order.append('pair') or {}) as pair,patch.object(flow,'play_uploaded') as audio:
            flow.speak_fresh('Hello.',self.cancel,self.progress,gesture={'key':'celebrate'})
        self.assertEqual(order,['attach','upload','unplug','pair']);pair.assert_called_once();audio.assert_not_called()
    def test_stop_after_upload_prevents_pair(self):
        with patch.object(flow.speech,'synthesize',return_value={'seconds':4}),patch.object(flow.robot_speech,'new_job',return_value={}),patch.object(flow.paired_speech,'attach'),patch.object(flow.robot_speech,'prepare_upload',side_effect=lambda *a:self.cancel.set()),patch.object(flow,'play_paired') as play:
            with self.assertRaises(ValueError):flow.speak_fresh('Hello.',self.cancel,self.progress,gesture={'key':'celebrate'})
            play.assert_not_called()
    def test_invalid_duration_prevents_pair_upload(self):
        with patch.object(flow.speech,'synthesize',return_value={'seconds':float('nan')}),patch.object(flow.robot_speech,'new_job',return_value={}),patch.object(flow.robot_speech,'prepare_upload') as upload:
            with self.assertRaises(ValueError):flow.speak_fresh('Hello.',self.cancel,self.progress,gesture={'key':'celebrate'})
            upload.assert_not_called()
    def test_stop_during_upload_prevents_playback(self):
        with patch.object(flow.speech,'synthesize',return_value={}),patch.object(flow.robot_speech,'new_job',return_value={}),patch.object(flow.robot_speech,'prepare_upload',side_effect=lambda *a:self.cancel.set()),patch.object(flow,'play_uploaded') as play:
            with self.assertRaises(ValueError):flow.speak_fresh('Hello.',self.cancel,self.progress)
            play.assert_not_called()
    def test_upload_failure_does_not_play_or_retry(self):
        with patch.object(flow.speech,'synthesize',return_value={}),patch.object(flow.robot_speech,'new_job',return_value={}),patch.object(flow.robot_speech,'prepare_upload',side_effect=OSError('failure')) as upload,patch.object(flow,'play_uploaded') as play:
            with self.assertRaises(OSError):flow.speak_fresh('Hello.',self.cancel,self.progress)
            upload.assert_called_once();play.assert_not_called()
    def test_reconnect_wait_only_reads_discovery(self):
        with patch.object(flow,'alpha_usb_present',return_value=False),patch.object(self.cancel,'wait'),patch.object(flow.robot_speech,'hid_command') as hid:
            flow.wait_for_playback_interface(self.cancel,self.progress)
            hid.assert_not_called()
    def test_timeout_and_stop_never_send(self):
        with patch.object(flow.robot_speech,'hid_command') as hid:
            with self.assertRaises(TimeoutError):flow.wait_for_playback_interface(self.cancel,self.progress,0)
            self.cancel.set()
            with self.assertRaises(ValueError):flow.wait_for_playback_interface(self.cancel,self.progress)
            hid.assert_not_called()

class BluetoothFreshJobTests(unittest.TestCase):
    def test_uncertain_job_is_never_replayed(self):
        import json,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            job={'directory':tmp,'name':'S123ABCD','sha256':'verified','status':'playback_uncertain','playback_attempted':True}
            (Path(tmp)/'job.json').write_text(json.dumps(job))
            with patch.object(flow,'bluetooth_address',return_value='configured'),patch.object(flow,'BluetoothRobot') as factory:
                with self.assertRaises(ValueError):flow.play_uploaded(job,threading.Event())
                factory.assert_not_called()
    def test_verified_job_is_played_once_with_cancel_guard(self):
        import json,tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            job={'directory':tmp,'name':'S123ABCD','sha256':'verified','status':'uploaded','playback_attempted':False}
            (Path(tmp)/'job.json').write_text(json.dumps(job))
            with patch.object(flow,'bluetooth_address',return_value='configured'),patch.object(flow,'BluetoothRobot') as factory:
                factory.return_value.play_robot_audio.return_value={'status':'accepted'}
                flow.play_uploaded(job,threading.Event())
                factory.return_value.play_robot_audio.assert_called_once()
                self.assertEqual(json.loads((Path(tmp)/'job.json').read_text())['status'],'playback_accepted')
                with self.assertRaises(ValueError):flow.play_uploaded(job,threading.Event())
                factory.return_value.play_robot_audio.assert_called_once()


class ReplayResponseTests(unittest.TestCase):
    def test_exact_saved_pair_replays_without_upload(self):
        job={'name':'S123ABCD'}
        with patch.object(flow,'alpha_usb_present',return_value=False),patch.object(flow.paired_speech,'find_saved',return_value=job),patch.object(flow,'play_paired',return_value=job) as play,patch.object(flow,'replay_saved') as audio,patch.object(flow.robot_speech,'prepare_upload') as upload:
            flow.replay_response('Hello.',threading.Event(),{'key':'celebrate'},{'voice':'Kore','style':'neutral'})
        self.assertTrue(play.call_args.kwargs['replay']);audio.assert_not_called();upload.assert_not_called()
    def test_missing_pair_does_not_fall_back_to_sequential_playback(self):
        with patch.object(flow,'alpha_usb_present',return_value=False),patch.object(flow.paired_speech,'find_saved',return_value=None),patch.object(flow,'play_paired') as play,patch.object(flow,'replay_saved') as audio:
            with self.assertRaisesRegex(ValueError,'USB upload'):flow.replay_response('Hello.',threading.Event(),{'key':'celebrate'},{'voice':'Kore','style':'neutral'})
        play.assert_not_called();audio.assert_not_called()
    def test_usb_attached_blocks_paired_command(self):
        with patch.object(flow,'alpha_usb_present',return_value=True),patch.object(flow,'BluetoothRobot') as robot:
            with self.assertRaises(ValueError):flow.play_paired({},threading.Event())
        robot.assert_not_called()
