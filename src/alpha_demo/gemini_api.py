"""Bounded Gemini REST client; credentials never enter reports or error messages."""
import json,re,urllib.request,urllib.error

class GeminiHTTPError(ValueError):
    def __init__(self,code,message):
        self.code=code
        super().__init__(message)

def http_error(error, body, model):
    """Describe actionable quota details without displaying server text or secrets."""
    config=body.get('generationConfig',{})
    stage=('Voice generation' if 'AUDIO' in config.get('responseModalities',[]) else
           'Gesture selection' if config.get('responseSchema') else 'Answer generation')
    if stage=='Answer generation' and any('google_search' in t for t in body.get('tools',[])):stage='Answer generation with web search'
    prefix=f'{stage} ({model}): '
    if error.code in (500,502,503,504):
        return prefix+f'Google service temporarily unavailable (HTTP {error.code}). Try again later; changing your key is not required by this error.'
    if error.code != 429:
        return prefix+f'Gemini HTTP {error.code}. Check model access and API settings.'
    retry=None;daily=False;zero=False
    try:
        payload=json.loads(error.read(65536))
        for detail in payload.get('error',{}).get('details',[]):
            if not isinstance(detail,dict):continue
            if str(detail.get('@type','')).endswith('/google.rpc.RetryInfo'):
                delay=detail.get('retryDelay','')
                if isinstance(delay,str) and re.fullmatch(r'[0-9]{1,7}(?:\.[0-9]{1,9})?s',delay):
                    import math
                    retry=math.ceil(float(delay[:-1]))
            if str(detail.get('@type','')).endswith('/google.rpc.QuotaFailure'):
                for violation in detail.get('violations',[]):
                    if not isinstance(violation,dict):continue
                    metric=str(violation.get('quotaMetric',''))+' '+str(violation.get('quotaId',''))
                    daily=daily or 'perday' in metric.lower() or 'per_day' in metric.lower()
                    zero=zero or violation.get('quotaValue') in (0,'0')
    except (ValueError,TypeError,AttributeError,OSError):pass
    if zero:hint='This model reports zero available quota. Check its access and billing in Google AI Studio.'
    elif daily:hint='Daily quota reached. Check Google AI Studio for the reset time or available quota.'
    elif retry is not None:hint=f'Google suggests waiting {retry} seconds before trying again; check AI Studio if it persists.'
    else:hint='Check this model’s quota in Google AI Studio; the response provided no retry time.'
    return prefix+'rate limit or quota exceeded (429). '+hint+' No automatic retry.'

def generate(body,key,model,timeout=60):
    if not isinstance(key,str) or not key.strip() or len(key)>512 or any(ord(c)<33 or ord(c)>126 for c in key.strip()):
        raise ValueError('Enter a valid Gemini API key in Settings.')
    if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',model):raise ValueError('Invalid Gemini model ID.')
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key.strip()},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:result=json.loads(response.read(20*1024*1024))
    except urllib.error.HTTPError as e:raise GeminiHTTPError(e.code,http_error(e,body,model)) from None
    except (urllib.error.URLError,TimeoutError):raise ValueError('Gemini connection failed; nothing was played.') from None
    candidates=result.get('candidates',[])
    if len(candidates)!=1 or candidates[0].get('finishReason') not in (None,'STOP'):raise ValueError('Gemini did not return a complete response.')
    return candidates[0]
