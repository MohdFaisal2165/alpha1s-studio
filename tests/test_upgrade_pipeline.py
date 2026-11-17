import base64,hashlib,io,json,struct,tempfile,threading,unittest,wave
from pathlib import Path
from unittest.mock import Mock,patch
from test_robot_speech import card
from alpha_demo import audio_card,card_cleanup,recording_store,teacher,gemini_api,expressive_voice,upload_session
from alpha_demo.sector_patch import apply_patch_blocks

class CardLifecycleTests(unittest.TestCase):
    def upload(self,raw,name='S123ABCD',action=None):
        return audio_card.stage_audio(raw,lambda s:raw[s*512:(s+1)*512],b'audio',name,action)
    def test_grow_full_music_directory_preserves_old_entries(self):
        original=bytearray(card());original[3072:3584]=b'X'*512
        before,after,order,metadata=self.upload(bytes(original))
        self.assertEqual(after[3072:3584],original[3072:3584])
        new_cluster=audio_card.u32(after,3*512+3*4)
        self.assertLess(new_cluster,0x0ffffff8)
        sector=5+new_cluster-2
        self.assertEqual(after[sector*512:sector*512+11],b'S123ABCDMP3')
        self.assertLess(order.index(sector),order.index(3))
        disk=bytearray(original)
        def write(s,b):disk[s*512:(s+1)*512]=b;return 512
        apply_patch_blocks(before,after,order,metadata,lambda s:bytes(disk[s*512:(s+1)*512]),write,lambda:None,lambda *a:None)
        self.assertEqual(disk,after)
    def test_firmware_mode_blocks_directory_growth(self):
        raw=bytearray(card());raw[3072:3584]=b'X'*512
        with self.assertRaisesRegex(ValueError,'Original MUSIC directory space is full'):
            audio_card.stage_audio(bytes(raw),lambda s:bytes(raw[s*512:(s+1)*512]),b'audio','S123ABCD',firmware_compatible=True)
    def test_firmware_mode_reuses_deleted_original_slot(self):
        raw=bytearray(card());raw[3104]=229
        _,after,_,_=audio_card.stage_audio(bytes(raw),lambda s:bytes(raw[s*512:(s+1)*512]),b'audio','S123ABCD',firmware_compatible=True)
        self.assertEqual(after[3104:3115],b'S123ABCDMP3')
    def test_delete_verified_file_and_reuse_slot(self):
        original=card();_,uploaded,_,_=self.upload(original)
        targets=[('MUSIC','S123ABCD.MP3',hashlib.sha256(b'audio').hexdigest())]
        before,after,order,metadata=card_cleanup.stage_cleanup(original,lambda s:uploaded[s*512:(s+1)*512],targets)
        self.assertEqual(after[3104],229);self.assertEqual(order[0],6)
        self.assertEqual(after[4096:4608],original[4096:4608])
        self.assertEqual(audio_card.u32(after,3*512+6*4),0)
        _,again,_,_=audio_card.stage_audio(original,lambda s:after[s*512:(s+1)*512],b'next','S123ABCE')
        self.assertEqual(again[3104:3115],b'S123ABCEMP3')
    def test_bad_hash_and_crosslink_block_cleanup(self):
        original=card();_,uploaded,_,_=self.upload(original)
        targets=[('MUSIC','S123ABCD.MP3',hashlib.sha256(b'audio').hexdigest())]
        with self.assertRaises(ValueError):card_cleanup.stage_cleanup(original,lambda s:uploaded[s*512:(s+1)*512],[('MUSIC','S123ABCD.MP3','wrong')])
        bad=bytearray(uploaded);bad[3136:3168]=bad[3104:3136];bad[3136:3147]=b'OTHER   MP3'
        with self.assertRaisesRegex(ValueError,'cross-linked'):card_cleanup.stage_cleanup(original,lambda s:bad[s*512:(s+1)*512],targets)
    def test_original_file_never_deleted(self):
        _,uploaded,_,_=self.upload(card())
        with self.assertRaisesRegex(ValueError,'Original'):card_cleanup.stage_cleanup(bytes(uploaded),lambda s:uploaded[s*512:(s+1)*512],[('MUSIC','S123ABCD.MP3',hashlib.sha256(b'audio').hexdigest())])

class RetentionTests(unittest.TestCase):
    def test_keep_and_greeting_are_protected_and_legacy_not_auto_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data').mkdir()
            for i in range(9):
                folder=root/'data/robot-speech'/str(i);folder.mkdir(parents=True)
                name='S'+f'{i:07X}'
                job={'name':name,'sha256':'sha','temporary':True,'status':'playback_accepted','upload':{'status':'complete','name':name,'sha256':'sha'}}
                if i==0:job['keep']=True
                if i==1:job['temporary']=False
                (folder/'job.json').write_text(json.dumps(job))
            (root/'data/pose-greetings.json').write_text(json.dumps({'person':{'audio':'S0000002'}}))
            names={x['name'] for x in recording_store.cleanup_candidates(root)}
            self.assertEqual(names,{'S0000003'})
            with self.assertRaises(ValueError):recording_store.update('S0000002',delete=True,root=root)
            recording_store.update('S0000001',delete=True,root=root)
            self.assertIn('S0000001',{x['name'] for x in recording_store.cleanup_candidates(root)})

class ModelPipelineTests(unittest.TestCase):
    def test_search_then_tone_selection_retains_answer_and_sources(self):
        answers=[{'content':{'parts':[{'text':'The result was announced today.'}]},'groundingMetadata':{'groundingChunks':[{'web':{'uri':'https://example.com/result','title':'Result'}}]}},
                 {'content':{'parts':[{'text':json.dumps({'heard':'What happened?','tone':'cheerful','gesture':'library:celebrate','reason':'An achievement'})}]}}]
        catalog={'none':{'title':'None','meaning':'No gesture'},'library:celebrate':{'title':'Celebrate','meaning':'Achievement'}}
        with patch.object(gemini_api,'generate',side_effect=answers) as api:
            result=teacher.ask('What happened?',None,[],catalog,'secret','model')
            self.assertEqual(api.call_args_list[0].args[0]['tools'],[{'google_search':{}}])
            self.assertNotIn('tools',api.call_args_list[1].args[0])
            self.assertEqual(result['gesture'],'library:celebrate');self.assertEqual(result['tone'],'cheerful')
            self.assertEqual(result['sources'][0]['url'],'https://example.com/result')
    def test_search_can_be_disabled_explicitly(self):
        responses=[{'content':{'parts':[{'text':'Hello.'}]}},{'content':{'parts':[{'text':json.dumps({'heard':'Hi','tone':'neutral','gesture':'none','reason':'No action needed'})}]}}]
        with patch.object(gemini_api,'generate',side_effect=responses) as api:
            teacher.ask('Hi',None,[],{'none':{'title':'None','meaning':'None'}},'secret','model',web_search=False)
            body=api.call_args_list[0].args[0]
            self.assertNotIn('tools',body)
            self.assertIn('Web search is OFF',body['systemInstruction']['parts'][0]['text'])
    def test_selector_unavailable_keeps_answer_without_gesture(self):
        response={'content':{'parts':[{'text':'Sadness is an emotion.'}]}}
        with patch.object(gemini_api,'generate',side_effect=[response,gemini_api.GeminiHTTPError(503,'Service unavailable')]) as api:
            result=teacher.ask('What is sadness?',None,[],{'none':{'title':'None','meaning':'None'}},'secret','model',web_search=False)
        self.assertEqual(result['answer'],'Sadness is an emotion.')
        self.assertEqual(result['gesture'],'none');self.assertIn('warning',result)
        self.assertEqual(api.call_count,2)
    def test_answer_failure_is_not_fabricated(self):
        with patch.object(gemini_api,'generate',side_effect=gemini_api.GeminiHTTPError(503,'Service unavailable')):
            with self.assertRaises(gemini_api.GeminiHTTPError):
                teacher.ask('Hi',None,[],{'none':{'title':'None','meaning':'None'}},'secret','model')
    def test_required_gesture_excludes_none_and_long_actions(self):
        replies=[{'content':{'parts':[{'text':'Canada has diverse landscapes and cultures.'}]}},{'content':{'parts':[{'text':json.dumps({'heard':'How is Canada?','tone':'neutral','gesture':'library:success','reason':'A brief conversational gesture'})}]}}]
        catalog={'none':{'title':'None','meaning':'No movement'},'library:success':{'title':'Success','meaning':'Positive','seconds':2.9},'library:long':{'title':'Long','meaning':'Long action','seconds':70}}
        with patch.object(gemini_api,'generate',side_effect=replies) as api:
            result=teacher.ask('How is Canada?',None,[],catalog,'secret','model',web_search=False,require_gesture=True)
        self.assertEqual(result['gesture'],'library:success')
        self.assertEqual(api.call_args_list[1].args[0]['generationConfig']['responseSchema']['properties']['gesture']['enum'],['library:success'])
        self.assertIn('Answer general questions using stable knowledge',api.call_args_list[0].args[0]['systemInstruction']['parts'][0]['text'])
    def test_unlisted_action_is_rejected(self):
        responses=[{'content':{'parts':[{'text':'Hello.'}]}},{'content':{'parts':[{'text':json.dumps({'heard':'Hi','tone':'cheerful','gesture':'motor:1:180','reason':'Hi'})}]}}]
        with patch.object(gemini_api,'generate',side_effect=responses):
            with self.assertRaises(ValueError):teacher.ask('Hi',None,[],{'none':{'title':'None','meaning':'None'}},'secret','model')
    def test_tts_preset_and_style_generate_real_wav_without_robot(self):
        data=io.BytesIO()
        with wave.open(data,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(b'\0\0'*2400)
        response={'content':{'parts':[{'inlineData':{'mimeType':'audio/wav','data':base64.b64encode(data.getvalue()).decode()}}]}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(gemini_api,'generate',return_value=response) as api,patch.object(expressive_voice.speech,'encode_mp3',side_effect=lambda pcm,rate,path:path.write_bytes(b'mp3')):
            result=expressive_voice.synthesize('Well done!',tmp,key='secret',voice='Puck',style='cheerful')
            request=api.call_args.args[0]
            self.assertEqual(request['generationConfig']['speechConfig']['voiceConfig'],{'voice':'Puck'})
            self.assertEqual(request['contents'][0]['parts'][0]['text'],'Well done!')
            self.assertEqual(result['voice'],'Puck');self.assertTrue(Path(result['mp3']).exists())
            self.assertNotIn('secret',(Path(result['mp3']).parent/'metadata.json').read_text())
    def test_invalid_voice_never_calls_api(self):
        with patch.object(gemini_api,'generate') as api:
            with self.assertRaises(ValueError):expressive_voice.synthesize('Hi','unused',key='secret',voice='clone')
            api.assert_not_called()

class UploadSessionTests(unittest.TestCase):
    def tearDown(self):upload_session.close()
    def test_two_uploads_authorize_once(self):
        proc=Mock();proc.poll.return_value=None
        proc.stdout=io.StringIO('\n'.join(json.dumps(x) for x in [{'status':'ready','message':'ready'},{'status':'complete'},{'status':'complete'}])+'\n')
        proc.stdin=io.StringIO();upload_session._process=None
        with patch.object(upload_session.subprocess,'Popen',return_value=proc) as spawn:
            for _ in range(2):upload_session.upload({'directory':'/tmp/'+'a'*32},'/dev/mock',lambda s:None)
            spawn.assert_called_once();self.assertEqual(len(proc.stdin.getvalue().splitlines()),2)
    def test_cancelled_auth_does_not_write_request(self):
        proc=Mock();proc.stdout=io.StringIO('');proc.stdin=Mock();upload_session._process=None
        with patch.object(upload_session.subprocess,'Popen',return_value=proc):
            with self.assertRaises(ValueError):upload_session.upload({'directory':'/tmp/'+'a'*32},'/dev/mock',lambda s:None)
            proc.stdin.write.assert_not_called()
