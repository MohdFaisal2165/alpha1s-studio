import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from alpha_demo import teacher

class TranscriptionTests(unittest.TestCase):
    def test_transcription_does_not_answer_or_select_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio=Path(tmp)/'voice.wav';audio.write_bytes(b'0'*100)
            with patch('alpha_demo.gemini_api.generate',return_value={'content':{'parts':[{'text':'How do robots learn?'}]}}) as api:
                self.assertEqual(teacher.transcribe(audio,'secret','test-model'),'How do robots learn?')
            body=api.call_args.args[0]
            self.assertNotIn('tools',body)
            self.assertIn('without answering',body['systemInstruction']['parts'][0]['text'])
    def test_empty_transcription_is_not_a_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio=Path(tmp)/'voice.wav';audio.write_bytes(b'0'*100)
            with patch('alpha_demo.gemini_api.generate',return_value={'content':{'parts':[]}}):
                with self.assertRaisesRegex(ValueError,'No usable transcription'):teacher.transcribe(audio,'secret','test-model')
