import json,tempfile,unittest
from pathlib import Path
from alpha_demo.speaker_probe import REQUEST,parse_play_reply,preflight,request_for

class SpeakerProbeTests(unittest.TestCase):
    def test_fixed_allowlisted_request(self):
        self.assertEqual(REQUEST,bytes.fromhex('f33f074c4f57424154d0ed'))
    def test_ack_is_not_audio_success(self):
        self.assertIn('not verified',parse_play_reply(bytes.fromhex('f33faaed')+bytes(60)))
        self.assertIn('not verified',parse_play_reply(bytes.fromhex('f33faaaaed')+bytes(59)))
    def test_failed_and_malformed_replies_rejected(self):
        for raw in (b'',bytes.fromhex('f33feeed'),bytes.fromhex('f33faaed01'),bytes.fromhex('f33faaa9ed')):
            with self.assertRaises(ValueError):parse_play_reply(raw)
    def test_preflight_requires_verified_backup_and_no_matching_action(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);reports=root/'reports';reports.mkdir()
            v=reports/'card-backup-verification.json';i=reports/'card-file-inventory.json'
            v.write_text(json.dumps({'status':'running'}));i.write_text(json.dumps([{'path':'MUSIC/LOWBAT.MP3'}]))
            with self.assertRaises(ValueError):preflight(root)
            v.write_text(json.dumps({'status':'complete','full_source_comparison':True}));preflight(root)
            i.write_text(json.dumps([{'path':'MUSIC/LOWBAT.MP3'},{'path':'ACTION/lowbat.hts'}]))
            with self.assertRaises(ValueError):preflight(root)

    def test_greeting_request_is_bounded(self):
        self.assertEqual(request_for('LOWBAT'),REQUEST)
        packet=request_for('FAISAL01')
        self.assertEqual(packet[3:-2],b'FAISAL01')
        self.assertEqual(packet[-2],sum(packet[2:-2])&255)
        with self.assertRaises(ValueError):request_for('Presentation')
