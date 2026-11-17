import io,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from alpha_demo import greetings,gestures

PROFILES={'faisal':{'name':'Faisal','audio':'FAISAL01','gesture':'none'}}

class GreetingTests(unittest.TestCase):
    def test_offline_known_unknown_ambiguous(self):
        self.assertEqual(greetings.offline_select("Hi, it's Faisal",PROFILES),'faisal')
        self.assertIsNone(greetings.offline_select('FaisalXYZ',PROFILES))
        self.assertIsNone(greetings.offline_select('Bob',PROFILES))
        self.assertIsNone(greetings.offline_select('Faisal and Bob',{**PROFILES,'bob':{'name':'Bob'}}))
    def test_untrusted_calls_cannot_introduce_motor_commands(self):
        for call in ({'name':'move','args':{'person':'faisal'}},{'name':'select_greeting','args':{'person':'faisal','servo':1}},{'name':'select_greeting','args':{'person':'../../dance'}},{'name':'select_greeting','args':{'person':1}}):
            with self.assertRaises(ValueError):greetings.validate_selection(call,PROFILES)
    def test_rest_selects_only_allowlisted_profile_and_key_not_in_url(self):
        response={'candidates':[{'content':{'parts':[{'functionCall':{'name':'select_greeting','args':{'person':'faisal'}}}]}}]}
        with patch.object(greetings.urllib.request,'urlopen',return_value=io.StringIO(json.dumps(response))) as fetch:
            self.assertEqual(greetings.gemini_select('Faisal',PROFILES,'private-key','test-model'),'faisal')
            request=fetch.call_args.args[0]
            self.assertNotIn('private-key',request.full_url)
            body=json.loads(request.data)
            self.assertEqual(body['toolConfig']['functionCallingConfig']['allowedFunctionNames'],['select_greeting'])
    def test_multiple_calls_refused(self):
        response={'candidates':[{'content':{'parts':[{'functionCall':{'name':'select_greeting','args':{'person':'faisal'}}}]*2}}]}
        with patch.object(greetings.urllib.request,'urlopen',return_value=io.StringIO(json.dumps(response))):
            with self.assertRaises(ValueError):greetings.gemini_select('Faisal',PROFILES,'key','test')
    def test_playback_uncertain_blocks_retry(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(greetings,'saved_audio',return_value={'FAISAL01':{'sha256':'x'}}),patch('alpha_demo.identify.find_device'),patch.object(greetings,'hid_command',side_effect=TimeoutError('timeout')) as send:
            with self.assertRaises(TimeoutError):greetings.play_saved('FAISAL01',Path(tmp))
            with self.assertRaisesRegex(ValueError,'uncertain'):greetings.play_saved('FAISAL01',Path(tmp))
            self.assertEqual(send.call_count,1)
    def test_verified_saved_audio_can_be_played_on_new_explicit_requests(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(greetings,'saved_audio',return_value={'FAISAL01':{'sha256':'x'}}),patch('alpha_demo.identify.find_device'),patch.object(greetings,'hid_command',return_value=(bytes.fromhex('f33faaed'),[])) as send:
            greetings.play_saved('FAISAL01',Path(tmp));greetings.play_saved('FAISAL01',Path(tmp))
            self.assertEqual(send.call_count,2)
            self.assertEqual(len(list((Path(tmp)/'reports/greeting-playback').glob('*.json'))),2)

class GestureTests(unittest.TestCase):
    def setUp(self):
        self.g={'start':{str(i):90 for i in range(1,7)},'steps':[{'servo':3,'target':95},{'servo':3,'target':90}],'reviewed':True}
        self.robot=MagicMock();self.robot.armed=threading.Event();self.robot.armed.set()
        self.robot.targets={i:90 for i in range(1,7)};self.robot.positions={};self.robot.limits={i:(0,180) for i in range(1,7)}
        self.robot.run.return_value={'status':'ok'}
    def test_replay_uses_only_recorded_steps(self):
        gestures.replay(self.robot,self.g)
        self.assertEqual([c.args for c in self.robot.run.call_args_list],[(3,95),(3,90)])
    def test_bad_start_no_movement(self):
        self.robot.targets[1]=45
        with self.assertRaises(ValueError):gestures.replay(self.robot,self.g)
        self.robot.run.assert_not_called()
    def test_fault_stops_remaining_steps(self):
        self.robot.run.return_value={'status':'error','error':'fault'}
        with self.assertRaises(ValueError):gestures.replay(self.robot,self.g)
        self.assertEqual(self.robot.run.call_count,1)
    def test_disarm_stops_remaining_steps(self):
        def run(*a,**k):self.robot.armed.clear();return {'status':'ok'}
        self.robot.run.side_effect=run
        with self.assertRaises(ValueError):gestures.replay(self.robot,self.g)
        self.assertEqual(self.robot.run.call_count,1)
    def test_preflight_rejects_non_loop_leg_and_unreviewed_sequences(self):
        for edit in ('end','leg','review'):
            g=json.loads(json.dumps(self.g))
            if edit=='end':g['steps'][-1]['target']=100
            elif edit=='leg':g['steps'][0]['servo']=7
            else:g['reviewed']=False
            with self.assertRaises(ValueError):gestures.replay(self.robot,g)
        self.robot.run.assert_not_called()
    def test_limit_check_finishes_before_any_move(self):
        self.robot.limits[3]=(0,92)
        with self.assertRaises(ValueError):gestures.replay(self.robot,self.g)
        self.robot.run.assert_not_called()
