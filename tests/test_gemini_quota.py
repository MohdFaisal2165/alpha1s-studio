import io,json,unittest,urllib.error
from unittest.mock import patch
from alpha_demo import gemini_api

class QuotaTests(unittest.TestCase):
    def error(self,details=(),message='secret should not be printed'):
        return urllib.error.HTTPError('https://example.invalid',429,'limited',{},io.BytesIO(json.dumps({'error':{'message':message,'details':details}}).encode()))
    def test_retry_and_stage(self):
        error=self.error([{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'12.2s'}])
        text=gemini_api.http_error(error,{'generationConfig':{'responseModalities':['AUDIO']}},'test-model')
        self.assertIn('Voice generation',text);self.assertIn('13 seconds',text);self.assertNotIn('secret',text)
    def test_daily_overrides_short_retry(self):
        error=self.error([{'@type':'type.googleapis.com/google.rpc.QuotaFailure','violations':[{'quotaId':'RequestsPerDay'}]},{'@type':'type.googleapis.com/google.rpc.RetryInfo','retryDelay':'2s'}])
        self.assertIn('Daily quota',gemini_api.http_error(error,{},'test'))
    def test_zero_quota(self):
        error=self.error([{'@type':'type.googleapis.com/google.rpc.QuotaFailure','violations':[{'quotaValue':'0'}]}])
        self.assertIn('zero available quota',gemini_api.http_error(error,{},'test'))
    def test_no_retry_or_secret_leak(self):
        with patch.object(gemini_api.urllib.request,'urlopen',side_effect=self.error()) as request:
            with self.assertRaisesRegex(ValueError,'Answer generation.*429') as caught:
                gemini_api.generate({},'private-key','test')
            self.assertNotIn('private-key',str(caught.exception));self.assertNotIn('secret',str(caught.exception));self.assertEqual(request.call_count,1)
    def test_malformed_response(self):
        error=urllib.error.HTTPError('https://example.invalid',429,'limited',{},io.BytesIO(b'not json'))
        self.assertIn('no retry time',gemini_api.http_error(error,{'generationConfig':{'responseSchema':{'type':'OBJECT'}}},'test'))

if __name__=='__main__':unittest.main()
