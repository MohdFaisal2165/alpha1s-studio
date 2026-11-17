import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from alpha_demo import action_library as library

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'reports').mkdir();(self.root/'data').mkdir()
        self.inventory=[]
        self.add('ACTION/GAMEPAD/Celebrate.hts',2200)
        self.add('ACTION/Presentation.hts',71608)
        self.add('ACTION/Left punch.hts',900)
    def add(self,path,ms):
        frame=bytearray(33);frame[:2]=b'\xfb\xbf';frame[8:24]=bytes([90]*16);frame[31]=sum(frame[2:31])%256;frame[32]=237
        tail=bytearray(33);tail[-4:]=ms.to_bytes(4,'little');raw=bytes(33)+bytes(frame)+bytes(tail)
        file=self.root/'work/card-extracted'/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
        self.inventory.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest()})
        (self.root/'reports/card-file-inventory.json').write_text(json.dumps(self.inventory))
    def test_all_verified_files_are_browsable(self):
        self.assertEqual(len(library.browse(self.root)),3)
        self.assertEqual(sum(x['seconds']<=6 for x in library.browse(self.root)),2)
    def test_approval_is_durable_and_bulk_authorization_is_explicit(self):
        library.approve('celebrate',self.root,meaning='Celebrate a correct answer')
        data=library.approvals(self.root);data['presentation']=library.inspect('presentation',self.root)['sha256']
        (self.root/'data/teacher-action-approvals.json').write_text(json.dumps(data))
        with patch('alpha_demo.pose_greetings.load',return_value={}):catalog=library.choices(self.root)
        self.assertEqual(set(catalog),{'none','library:celebrate','library:presentation'})
        self.assertEqual(catalog['library:celebrate']['meaning'],'Celebrate a correct answer')
        library.approve_all(self.root)
        self.assertEqual(len(library.approvals(self.root)),3)
        imported=next(k for k in library.approvals(self.root) if k.startswith('card_'))
        self.assertFalse(library.approvals(self.root)[imported]['rehearsal_verified'])
    def test_tampered_file_never_offered_or_sent(self):
        library.approve('celebrate',self.root)
        (self.root/'work/card-extracted/ACTION/GAMEPAD/Celebrate.hts').write_bytes(bytes(99))
        robot=Mock()
        with self.assertRaises(ValueError):library.play_native(robot,'celebrate',supported=True,root=self.root)
        robot.operation.assert_not_called()
    def test_unknown_paths_cannot_be_discovered(self):
        self.inventory.append({'path':'../../outside.hts','sha256':'x'})
        (self.root/'reports/card-file-inventory.json').write_text(json.dumps(self.inventory))
        self.assertFalse(any(x[1]=='../../outside.hts' for x in library.candidates(self.root).values()))

    def test_paired_action_is_exact_copy_and_tampering_blocks_it(self):
        from alpha_demo import paired_speech
        library.approve('celebrate',self.root)
        folder=self.root/'job';folder.mkdir()
        job={'directory':str(folder)}
        paired_speech.attach(job,'celebrate',self.root)
        original=(self.root/'work/card-extracted/ACTION/GAMEPAD/Celebrate.hts').read_bytes()
        raw,item=paired_speech.validate_action(job,self.root)
        self.assertEqual(raw,original)
        (folder/'action.hts').write_bytes(b'changed')
        with self.assertRaises(ValueError):paired_speech.validate_action(job,self.root)
