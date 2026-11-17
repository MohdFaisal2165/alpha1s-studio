import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from alpha_demo.speech import validate_text,synthesize

class SpeechTests(unittest.TestCase):
    def test_invalid_input_does_not_start_process(self):
        with patch('alpha_demo.speech.subprocess.run') as run:
            for text in ('','  ','x'*1501,'abc\0def',None):
                with self.assertRaises(ValueError):synthesize(text,'unused')
            run.assert_not_called()
    def test_text_is_stdin_not_shell_code(self):
        text='Hello; $(touch /tmp/should-never-run) <audio> is plain text'
        with tempfile.TemporaryDirectory() as tmp,patch('alpha_demo.speech.subprocess.run') as run:
            def reply(args,**kwargs):
                self.assertNotIn(text,args);self.assertEqual(kwargs['input'],text)
                self.assertNotIn('shell',kwargs)
                folder=Path(args[-1]);wav=folder/'speech.wav';mp3=folder/'speech.mp3'
                wav.write_bytes(b'audio');mp3.write_bytes(b'audio')
                from subprocess import CompletedProcess
                return CompletedProcess(args,0,json.dumps({'wav':str(wav),'mp3':str(mp3)}),'')
            run.side_effect=reply
            self.assertTrue(Path(synthesize(text,tmp)['mp3']).exists())
    def test_worker_failure_is_reported(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as tmp,patch('alpha_demo.speech.subprocess.run',return_value=CompletedProcess([],1,'','engine error')):
            with self.assertRaisesRegex(RuntimeError,'engine error'):synthesize('Hello',tmp)
