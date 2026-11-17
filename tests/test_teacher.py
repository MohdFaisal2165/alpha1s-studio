import unittest
from unittest.mock import Mock,patch
from alpha_demo import teacher, action_library
from alpha_demo.teacher_panel import TeacherPanel

class TeacherTests(unittest.TestCase):
    def test_response_rejects_arbitrary_motors(self):
        args=dict(heard='Hello',answer='Welcome',gesture='motor:1:180',reason='Hello')
        with self.assertRaises(ValueError):teacher.validate_response(dict(name='respond_to_participant',args=args),{'none':{}})
        args['gesture']='none';args['angle']=180
        with self.assertRaises(ValueError):teacher.validate_response(dict(name='respond_to_participant',args=args),{'none':{}})
    def test_request_only_offers_approved_ids(self):
        body=teacher.build_request('Hello',None,[],{'none':{'title':'None','meaning':'Stay still'}})
        schema=body['tools'][0]['functionDeclarations'][0]['parameters']
        self.assertEqual(schema['properties']['gesture']['enum'],['none'])
    def test_no_computer_audio_fallback(self):
        robot=Mock()
        with self.assertRaisesRegex(ValueError,'Computer playback is disabled'):teacher.perform(robot,{}, {})
        self.assertEqual(robot.mock_calls,[])
    def test_speech_requires_support_and_usb(self):
        panel=TeacherPanel.__new__(TeacherPanel);panel.future=None;panel.owner=Mock()
        panel.owner.future=None;panel.owner.greeting_active=False;panel.owner.speech_active=False
        panel.answer={'answer':'Robots use sensors.','gesture':'none'};panel.status=Mock();panel.support=Mock();panel.begin=Mock()
        panel.voice=Mock();panel.delivery=Mock();panel.key=Mock();panel.tts_model=Mock()
        panel.support.get.return_value=False
        panel.perform();panel.begin.assert_not_called()
        panel.support.get.return_value=True
        with patch('alpha_demo.conversation_speech.alpha_usb_present',return_value=False):
            panel.perform();panel.begin.assert_not_called()
        with patch('alpha_demo.conversation_speech.bluetooth_address',return_value='configured'),patch('alpha_demo.conversation_speech.alpha_usb_present',return_value=True),patch('alpha_demo.action_library.choices',return_value={'none':{}}):
            panel.perform();self.assertEqual(panel.begin.call_args.args[0],'speak')
        panel.owner.robot.armed.set.assert_not_called()
    def test_busy_handoff_does_not_interrupt(self):
        panel=TeacherPanel.__new__(TeacherPanel);panel.future=None;panel.owner=Mock();panel.owner.future=object();panel.status=Mock()
        panel.perform();self.assertEqual(panel.owner.robot.mock_calls,[])
    def test_unknown_library_action(self):
        with self.assertRaises((KeyError,ValueError)):action_library.inspect('../outside')

if __name__=='__main__':unittest.main()

class CredentialTests(unittest.TestCase):
    def test_bad_header_key_never_reaches_network_or_error_text(self):
        secret='private\nkey'
        with patch('alpha_demo.teacher.urllib.request.urlopen') as request:
            with self.assertRaises(ValueError) as error:
                teacher.ask('Hello',None,[],{},secret,'test-model')
            self.assertNotIn(secret,str(error.exception));request.assert_not_called()

class MicrophoneTests(unittest.TestCase):
    def test_finish_finalizes_wav_and_never_calls_api(self):
        import signal,tempfile,threading,wave
        from pathlib import Path
        cancel=threading.Event();finished=threading.Event();finished.set()
        with tempfile.TemporaryDirectory() as tmp:
            process=Mock();process.poll.side_effect=[None,1,1];process.returncode=1
            def spawn(args,**kwargs):
                with wave.open(args[-1],'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*3200)
                return process
            with patch.object(teacher,'ROOT',Path(tmp)),patch.object(teacher.shutil,'which',return_value='/mock/arecord'),patch.object(teacher.subprocess,'Popen',side_effect=spawn),patch.object(teacher.time,'sleep'),patch.object(teacher.urllib.request,'urlopen') as api:
                result=teacher.record(cancel,finished)
                self.assertTrue(result.is_file());process.send_signal.assert_called_once_with(signal.SIGINT);api.assert_not_called()
    def test_cancel_before_capture_does_not_open_microphone(self):
        import threading
        cancel=threading.Event();cancel.set()
        with patch.object(teacher.subprocess,'Popen') as spawn:
            with self.assertRaises(ValueError):teacher.record(cancel)
            spawn.assert_not_called()
    def test_failed_capture_removes_private_file(self):
        import tempfile,threading
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            process=Mock();process.poll.return_value=1;process.returncode=1
            def spawn(args,**kwargs):Path(args[-1]).write_bytes(b'partial');return process
            with patch.object(teacher,'ROOT',Path(tmp)),patch.object(teacher.shutil,'which',return_value='/mock/arecord'),patch.object(teacher.subprocess,'Popen',side_effect=spawn):
                with self.assertRaises(ValueError):teacher.record(threading.Event())
            self.assertEqual(list((Path(tmp)/'data/teacher-audio').iterdir()),[])
    def test_second_mic_click_finishes_without_second_worker(self):
        import threading
        panel=TeacherPanel.__new__(TeacherPanel);panel.future=object();panel.mode='record';panel.record_finished=threading.Event();panel.mic_button=Mock();panel.status=Mock()
        panel.record();self.assertTrue(panel.record_finished.is_set())
