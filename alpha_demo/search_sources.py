"""Display source links and provider search suggestions without executing scripts."""
import html,uuid,webbrowser
from .robot_speech import ROOT

def show(answer):
    items=''.join('<li><a target="_blank" rel="noopener noreferrer" href="'+html.escape(s['url'],quote=True)+'">'+html.escape(s['title'])+'</a></li>' for s in answer.get('sources',[]) if s['url'].startswith('https://'))
    suggestions=answer.get('grounding',{}).get('searchEntryPoint',{}).get('renderedContent','')
    page='''<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; frame-src 'self' about:;"><title>Alpha — Sources</title><style>body{font:18px sans-serif;max-width:900px;margin:40px auto;padding:20px}iframe{width:100%;height:350px;border:0}</style>'''
    page+='<h1>Answer sources</h1><p>'+html.escape(answer['answer'])+'</p><ul>'+items+'</ul>'
    if suggestions:page+='<h2>Google Search suggestions</h2><iframe sandbox="allow-popups allow-popups-to-escape-sandbox" srcdoc="'+html.escape(suggestions,quote=True)+'"></iframe>'
    folder=ROOT/'data/search-sources';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(uuid.uuid4().hex+'.html');path.write_text(page);webbrowser.open(path.as_uri())
