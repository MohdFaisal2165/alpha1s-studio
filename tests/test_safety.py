import unittest
from types import SimpleNamespace
from alpha_demo.controller import Controller
from alpha_demo.gemini import parse_calls
from alpha_demo.motions import validate_call

class SafetyTests(unittest.TestCase):
    def test_rejects_untrusted_commands(self):
        for name, args in [('move_servo', {'motion':'wave'}),
                           ('propose_motion', {'motion':'wave','angle':90}),
                           ('propose_motion', {'motion':['wave']}),
                           ('propose_motion', {'motion':'../../dance'}),
                           ('propose_motion', {}), ('propose_motion', None)]:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                validate_call(name,args)

    def test_expiry(self):
        t=[0]; c=Controller(lambda:t[0]); c.propose('propose_motion',{'motion':'wave'})
        t[0]=31
        with self.assertRaises(ValueError): c.preview()
        self.assertIsNone(c.pending)

    def test_single_use(self):
        c=Controller(); c.propose('propose_motion',{'motion':'wave'})
        self.assertEqual(len(c.preview()),3)
        with self.assertRaises(ValueError): c.preview()

    def test_hardware_blocked(self):
        c=Controller(); c.propose('propose_motion',{'motion':'wave'})
        with self.assertRaises(PermissionError): c.execute_hardware()
        self.assertIsNone(c.pending)

    def test_invalid_replacement_cancels(self):
        c=Controller(); c.propose('propose_motion',{'motion':'wave'})
        with self.assertRaises(ValueError): c.propose('shell',{'motion':'wave'})
        self.assertIsNone(c.pending)

    def test_model_call_cardinality(self):
        call=SimpleNamespace(name='propose_motion',args={'motion':'idle'})
        for calls in ([],[call,call]):
            with self.assertRaises(ValueError): parse_calls(calls)
        self.assertEqual(parse_calls([call]),'idle')

    def test_cancel(self):
        c=Controller(); c.propose('propose_motion',{'motion':'wave'}); c.cancel()
        with self.assertRaises(ValueError): c.preview()

if __name__=='__main__': unittest.main()
