# -*- coding: utf-8 -*-
import json
import re
import sys
import hmac
import types
import unittest
import importlib.util
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch

HERE=Path(__file__).parent
SOURCE=(HERE.parent/'webui_v210.py').read_text(encoding='utf8')
class FakeView:
    instances=[]
    def __init__(self,frame=(0,0,390,844)):
        self.frame=frame;self.width=frame[2];self.height=frame[3]
        self.bounds=self.frame;self.on_screen=False;self.result=None;self.ready=False
        self.subviews=[];self.delegate=None;self.name=''
        self.__class__.instances.append(self)
    def add_subview(self,part):self.subviews.append(part)
    def present(self,*args,**kw): self.on_screen=True
    def close(self):self.on_screen=False
    def wait_modal(self):pass

class FakeWebView(FakeView):
    def load_html(self,html):
        self.html=html
        m=re.search(r'window\.PYAGENT_BOOT=(.*?);</script>',html)
        if not m:raise ValueError('no bootstrap')
        self.boot=json.loads(m.group(1))
        q=urlencode({'nonce':self.boot['nonce'],'action':'ready','payload':''})
        self.delegate.webview_should_start_load(self,'pyagent-ui://dispatch?'+q,0)
    def eval_js(self,script):self.last_js=script;return None
    def dispatch(self,action,payload='',nonce=None):
        q=urlencode({'nonce':nonce or self.boot['nonce'],'action':action,'payload':payload})
        return self.delegate.webview_should_start_load(self,'pyagent-ui://dispatch?'+q,0)

class FakeUIModule(types.ModuleType):
    def __init__(self):
        super().__init__('ui')
        self.View=FakeView;self.WebView=FakeWebView
        self.get_screen_size=lambda:(390,844)
        self.delay=lambda fn,t: fn()

class NativeBridgeTest(unittest.TestCase):
    def setUp(self):
        FakeView.instances.clear(); FakeWebView.instances.clear()
        self.ui=FakeUIModule()
        self.state={'id':'abc','goal':'查询日程','status':'finished', 'events':[]}
        self.logs=[]
        self.appearance={'theme':'典雅紫','mode':'深色模式','custom_color':''}
        self.registry=[('test','可用工具')]
        self.archive=[{'key':'2026-11/task_123456.json','title':'测试','created':'2026','quality':'本机完成','preview':'hello'}]
        self.env={'json':json,'hmac':hmac,'uuid':__import__('uuid'),
                  '_card_ui_show':lambda:('old_ui',''),
                  '_result_ui_show':lambda state:{'old':True},
                  '_card_task_snapshot':lambda:self.state,
                  '_card_appearance_load':lambda:self.appearance.copy(),
                  '_card_palette':lambda _:dict(background='#101319',accent='#8A62D8'),
                  '_result_card_model':lambda state:{'title':'已完成','body':'测试结果','copy':'结果'},
                  '_history_search':lambda q='',limit=45:self.archive,
                  '_history_read':lambda k:{'goal':'测试档案','created':'2026','events':[]},
                  '_history_md':lambda v:'这是档案内容',
                  '_history_markdown_for_key':lambda k:'完整档案',
                  '_card_tool_rows':lambda s:self.registry,
                  '_card_appearance_save':self.save_appearance,
                  'CARD_THEMES':{'典雅紫':'#8A62D8','活力橙':'#F07828'},
                  'DISPLAY_MODES':('跟随系统','浅色模式','深色模式'),
                  '_card_hex':lambda x:x if re.fullmatch(r'#[a-fA-F0-9]{6}',x) else '',
                  'VERSION':'2.1.0-deepseek-flash'}
        exec(compile(SOURCE,'webui_v210.py','exec'),self.env)
        self.patch=patch.dict(sys.modules,{'ui':self.ui,'clipboard':types.SimpleNamespace(set=lambda x:self.logs.append(x))})
        self.patch.start()
    def tearDown(self):self.patch.stop()
    def save_appearance(self,a):self.appearance.update(a);return a
    def show(self,page='home',modal=False):
        result=self.env['_webui_show'](page,state=self.state,modal=modal)
        view=FakeWebView.instances[-1]
        return result,view
    def test_html_is_offline(self):
        html=self.env['WEBUI_HTML']
        self.assertIn('default-src \'none\'',html)
        self.assertNotIn('<script src=',html)
        self.assertNotIn('<link rel="stylesheet"',html)
    def test_markup_escaping(self):
        html=self.env['_webui_document']({'goal':'</script><script>bad()</script>'})
        self.assertNotIn('</script><script>bad()</script>',html)
        self.assertIn(r'\u003c/script\u003e',html)
    def test_view_is_webview_and_ready(self):
        response,web=self.show()
        self.assertEqual(response,('exit',''))
        self.assertTrue(web.html.startswith('<!doctype html>'))
        self.assertTrue(FakeView.instances[-2].ready)
        self.assertIn('2.1.0',web.html)
    def test_no_external_navigation(self):
        _,w=self.show()
        self.assertFalse(w.delegate.webview_should_start_load(w,'https://example.org',0))
        self.assertFalse(w.dispatch('voice',nonce='wrong'))
    def test_search_stays_in_webview(self):
        _,w=self.show()
        w.dispatch('search','测试')
        self.assertIn('"type":"search"',w.last_js)
        self.assertIn('测试',w.last_js)
    def test_theme_saved_and_paletted(self):
        _,w=self.show()
        w.dispatch('theme','活力橙')
        self.assertEqual(self.appearance['theme'],'活力橙')
        self.assertIn('"type":"theme"',w.last_js)
        w.dispatch('color','#12ABFE')
        self.assertEqual(self.appearance['custom_color'],'#12ABFE')
    def test_invalid_theme_rejected(self):
        _,w=self.show()
        w.dispatch('color','javascript:alert(1)')
        self.assertEqual(self.appearance['custom_color'],'')
    def test_copy_stays_local(self):
        _,w=self.show()
        w.dispatch('copy','中文测试')
        self.assertEqual(self.logs[-1],'中文测试')
    def test_wrong_origin_does_not_run_task(self):
        _,w=self.show()
        parent=FakeView.instances[-2]
        w.dispatch('input','write token',nonce='bad')
        self.assertEqual(parent.result,('exit',''))
    def test_result_modal(self):
        response,w=self.show('result',True)
        self.assertTrue(w.boot['modal'])
        self.assertEqual(w.boot['page'],'result')
        self.assertEqual(w.boot['result']['body'],'测试结果')
    def test_deferred_native_dispatch(self):
        _,w=self.show()
        w.dispatch('input','整理今天任务')
        # The bridge must not call the business engine itself on the UI thread.
        self.assertEqual(FakeView.instances[-2].result,('input','整理今天任务'))
    def test_empty_task_rejected(self):
        _,w=self.show()
        w.dispatch('input',' ')
        self.assertIn('"type":"message"',w.last_js)
    def test_missing_webview_native_fallback(self):
        module=types.SimpleNamespace(View=FakeView,get_screen_size=lambda:(390,844))
        with patch.dict(sys.modules,{'ui':module}):
            self.assertEqual(self.env['_card_ui_show'](),('old_ui',''))

if __name__=='__main__': unittest.main(verbosity=2)