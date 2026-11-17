import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from alpha_demo import recording_store as store,robot_speech,conversation_speech

class DeleteTests(unittest.TestCase):
    def test_delete_only_request_and_verified_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'data/robot-speech'/'original';folder.mkdir(parents=True)
            job={'name':'S123ABCD','sha256':'hash','upload':{'status':'complete','name':'S123ABCD','sha256':'hash'}}
            (folder/'job.json').write_text(json.dumps(job))
            with patch.object(conversation_speech,'alpha_usb_present',return_value=True),patch.object(robot_speech,'prepare_upload') as upload:
                store.delete_now(['S123ABCD'],lambda x:None,root)
            request=upload.call_args.args[0]
            self.assertEqual(request['kind'],'delete_recordings');self.assertEqual(request['delete_names'],['S123ABCD'])
            self.assertFalse((Path(request['directory'])/'speech.mp3').exists())
            self.assertTrue(json.loads((folder/'job.json').read_text())['card_deleted'])
    def test_usb_required_before_metadata_change(self):
        with patch.object(conversation_speech,'alpha_usb_present',return_value=False),patch.object(store,'update') as update:
            with self.assertRaisesRegex(ValueError,'Connect robot USB'):store.delete_now(['S123ABCD'],lambda x:None)
            update.assert_not_called()
    def test_failed_deletion_not_marked_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'data/robot-speech'/'original';folder.mkdir(parents=True)
            (folder/'job.json').write_text(json.dumps({'name':'S123ABCD','sha256':'hash','upload':{'status':'complete','name':'S123ABCD','sha256':'hash'}}))
            with patch.object(conversation_speech,'alpha_usb_present',return_value=True),patch.object(robot_speech,'prepare_upload',side_effect=ValueError('failed')):
                with self.assertRaises(ValueError):store.delete_now(['S123ABCD'],lambda x:None,root)
            self.assertFalse(json.loads((folder/'job.json').read_text()).get('card_deleted',False))

class StorageAcquireTests(unittest.TestCase):
    def test_storage_does_not_require_movement_confirmation(self):
        from unittest.mock import Mock
        from alpha_demo.speech_panel import SpeechPanel
        owner=Mock();owner.ready.get.return_value=False;owner.future=None;owner.greeting_active=False
        owner.robot.connected=False;owner.robot.lock.acquire.return_value=True
        panel=Mock();panel.owner=owner
        SpeechPanel.acquire(panel,storage_only=True)
        self.assertTrue(owner.speech_active)
        owner.ready.get.assert_not_called()
    def test_playback_still_requires_support(self):
        from unittest.mock import Mock
        from alpha_demo.speech_panel import SpeechPanel
        panel=Mock();panel.owner.ready.get.return_value=False
        with self.assertRaisesRegex(ValueError,'Supported'):SpeechPanel.acquire(panel)
        panel.owner.robot.lock.acquire.assert_not_called()
