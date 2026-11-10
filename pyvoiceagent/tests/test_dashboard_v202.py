# -*- coding: utf-8 -*-
"""V2.0.2 UI lifecycle/geometry tests with simulated Pythonista widgets.

These tests are intentionally not described as iPhone physical-device tests.
"""
import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'agent_core_2_0_2.py'


class NativeWidget:
    all=[]
    def __init__(self,frame=(0,0,390,844),**kwargs):
        self.frame=frame
        self.width=frame[2]
        self.height=frame[3]
        self.subviews=[]
        self.text=''
        self.title=''
        self.closed=False
        self.background_color=None
        NativeWidget.all.append(self)
    @property
    def frame(self):
        return self._frame
    @frame.setter
    def frame(self,value):
        self._frame=value
        self.width=value[2]
        self.height=value[3]
    def add_subview(self,view):
        self.subviews.append(view)
    def remove_subview(self,view):
        self.subviews.remove(view)
    def present(self,*args,**kwargs):
        self.layout()
    def wait_modal(self): pass
    def close(self): self.closed=True


class NativeModule(types.ModuleType):
    ALIGN_LEFT=0
    ALIGN_RIGHT=2
    def __init__(self,width,height):
        super().__init__('ui')
        self.width=width
        self.height=height
        self.View=NativeWidget
        self.Label=type('Label',(NativeWidget,),{})
        self.Button=type('Button',(NativeWidget,),{})
        self.TextField=type('TextField',(NativeWidget,),{})
        self.TextView=type('TextView',(NativeWidget,),{})
        self.ScrollView=type('ScrollView',(NativeWidget,),{})
        self.get_screen_size=lambda:(width,height)


def load_ui(width=390,height=844,status='finished'):
    NativeWidget.all=[]
    source=SOURCE.read_text('utf-8')
    tree=ast.parse(source)
    defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_card_ui_show']
    assert len(defs)==1
    chosen=defs[0]
    palette=dict(background='#11151C', surface='#232933',raised='#303746',
        accent='#8A62D8',text='#FFFFFF',muted='#A7B0BB',light='#FFFFFF')
    env=dict(VERSION='2.0.2-deepseek-flash',
        _card_appearance_load=lambda:{'theme':'典雅紫','mode':'深色模式'},
        _card_palette=lambda _:palette,
        _card_task_snapshot=lambda:{'status':status,'events':[]},
        _history_search=lambda *_:[],
        _card_nav_items=lambda *_:[],
        _history_read=lambda *_:{},
        _history_md=lambda *_:'',
        _card_tool_rows=lambda *_:[],
        _card_hex=lambda c:c,
        _card_appearance_save=lambda *_:None)
    exec(compile(ast.Module(body=[chosen],type_ignores=[]),str(SOURCE),'exec'),env)
    native=NativeModule(width,height)
    with patch.dict(sys.modules,{'ui':native}):
        env['_card_ui_show']()
    # root is the only direct NativeWidget object with exact screen frame.
    root=next(v for v in NativeWidget.all
              if type(v).__name__=='AgentCardView')
    return root,native


def descendants(parent):
    for child in parent.subviews:
        yield child
        yield from descendants(child)


class DashboardV202(unittest.TestCase):
    def test_core_syntax_and_version(self):
        text=SOURCE.read_text('utf-8')
        ast.parse(text)
        self.assertIn("VERSION = '2.0.2-deepseek-flash'",text)
        self.assertIn('_V200_MAIN = main',text)
        self.assertIn('_V200_DISPATCH = _card_dispatch',text)
        self.assertIn("primary_button.action = self._link('voice')",text)

    def test_home_has_primary_and_localized_status(self):
        root,_=load_ui()
        labels=[v.text for v in descendants(root) if v.text]
        self.assertIn('语音执行任务',labels)
        self.assertIn('最近任务：已完成',labels)
        self.assertNotIn('当前任务：finished',labels)
        self.assertIn('常用功能',labels)
        self.assertIn('管理与设置',labels)

    def test_home_keyboard_safe_scroll_and_fixed_tabs(self):
        for width,height in ((320,568),(375,667),(390,844),(430,932)):
            with self.subTest(size=(width,height)):
                root,native=load_ui(width,height)
                tabs=[v for v in descendants(root)
                      if v.title in ('首页','结果','档案','设置')]
                self.assertEqual(len(tabs),4)
                for tab in tabs:
                    self.assertGreaterEqual(tab.width,30)
                nav=next(v for v in root.subviews if v.height==59)
                self.assertGreaterEqual(nav.frame[1],0)
                self.assertLessEqual(nav.frame[1]+nav.height,height-20)
                scrollers=[v for v in root.subviews
                           if isinstance(v,native.ScrollView)]
                self.assertEqual(len(scrollers),1)
                scroll=scrollers[0]
                self.assertLess(scroll.frame[1]+scroll.height,nav.frame[1])
                self.assertGreater(scroll.content_size[1],scroll.height)
                for card in scroll.subviews:
                    self.assertGreaterEqual(card.frame[0],0)
                    self.assertLessEqual(card.frame[0]+card.width,scroll.width+1)

    def test_voice_tile_does_not_auto_record(self):
        root,_=load_ui()
        panel=next(v for v in descendants(root)
                   if any(x.text=='语音执行任务' for x in v.subviews))
        hit=next(v for v in panel.subviews if getattr(v,'action',None))
        hit.action(hit)
        self.assertEqual(root.result,('voice',''))
        self.assertTrue(root.closed)

    def test_tab_navigation_stays_inside_pythonista_ui(self):
        root,native=load_ui()
        settings=next(v for v in descendants(root) if v.title=='设置')
        settings.action(settings)
        self.assertEqual(root.page,'settings')
        self.assertTrue(any(v.text=='设置中心' for v in descendants(root)))
        home=next(v for v in descendants(root) if v.title=='首页')
        home.action(home)
        self.assertEqual(root.page,'home')
        self.assertTrue(any(v.text=='语音执行任务' for v in descendants(root)))

    def test_results_open_existing_result_handler(self):
        root,_=load_ui()
        result=next(v for v in descendants(root) if v.title=='结果')
        result.action(result)
        self.assertEqual(root.result,('status',''))
        self.assertTrue(root.closed)

    def test_submenu_uses_same_theme_and_has_bottom_tabs(self):
        root,_=load_ui()
        tab=next(v for v in descendants(root) if v.title=='档案')
        tab.action(tab)
        self.assertEqual(root.page,'archive')
        self.assertEqual(root.background_color,'#11151C')
        self.assertEqual(len([v for v in descendants(root)
                              if v.title in ('首页','结果','档案','设置')]),4)

if __name__=='__main__':
    unittest.main(verbosity=2)
