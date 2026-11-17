import unittest
from unittest.mock import Mock,patch
from alpha_demo.greeting_panel import GreetingPanel
class WorkflowTests(unittest.TestCase):
    def panel(self):
        p=Mock();p.owner.speech.future=None;p.owner.speech.active=False;p.owner.speech.phase='idle'
        p.owner.speech.current_text.return_value='Welcome!'
        p.owner.speech.voice_settings.return_value={'voice':'Leda','style':'calm'}
        p.pose={'1':90};return p
    def test_exact_voice_selected_not_other_recording_of_same_words(self):
        p=self.panel()
        with patch('alpha_demo.greeting_panel.greetings.saved_audio',return_value={'S1111111':{'text':'Welcome!','voice':'Kore','style':'calm'},'S2222222':{'text':'Welcome!','voice':'Leda','style':'calm'}}):
            GreetingPanel.use_voice(p)
        self.assertEqual(p.audio_name,'S2222222');p.owner.notebook.select.assert_called_once_with(p.page)
    def test_voice_draft_can_continue_without_upload(self):
        p=self.panel()
        with patch('alpha_demo.greeting_panel.greetings.saved_audio',return_value={}):GreetingPanel.use_voice(p)
        p.owner.notebook.select.assert_called_once_with(p.page)
        self.assertIsNone(p.audio_name)
        self.assertEqual(p.voice_draft['text'],'Welcome!')
    def test_uploaded_message_can_continue_without_playback(self):
        p=self.panel();p.owner.speech.phase='reconnect'
        with patch('alpha_demo.greeting_panel.greetings.saved_audio',return_value={'S2222222':{'text':'Welcome!','voice':'Leda','style':'calm'}}):GreetingPanel.use_voice(p)
        p.owner.speech.finish.assert_called_once();p.owner.speech.speak.assert_not_called()
