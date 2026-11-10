# -*- coding: utf-8 -*-
import json
import re
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

BASE = Path(__file__).resolve().parent
SRC = (BASE / 'result_center_v200.py').read_text('utf-8')


def load_module():
    old = Mock()
    ns = dict(re=re, json=json, datetime=datetime,
              final_report=old, _voice_report=Mock(),
              _card_appearance_load=lambda: {'theme':'活力橙','mode':'深色模式'},
              _card_palette=lambda cfg: dict(background='#111111',raised='#333333',
                 surface='#222222', text='#EEEEEE',muted='#AAAAAA',
                 accent='#FF7700',negative='#FF0000',light='#FFFFFF'))
    exec(compile(SRC,'result_center_v200.py','exec'),ns)
    return ns,old


def calendar_state(text):
    return {'goal':'查询11月12日苹果日历','status':'finished',
            'final':'本地执行总结（以逐项执行记录为准）：只读快捷指令返回：'+text,
            'events':[{'tool':'calendar.list','status':'ok',
                       'result':'只读快捷指令返回（未做独立系统核验）：\n'+text}]}


class MockUIBase:
    made = []
    def __init__(self, frame=None, **kwargs):
        self.frame = frame or (0, 0, 300, 600)
        self.width = self.frame[2]
        self.height = self.frame[3]
        self.children=[]
        self.presented=False
        self.title=''
        MockUIBase.made.append(self)
    def add_subview(self, child): self.children.append(child)
    def present(self, *args,**kwargs): self.presented=True
    def wait_modal(self): pass
    def close(self): self.closed=True


class FakeUI(types.ModuleType):
    def __init__(self):
        super().__init__('ui')
        self.View=MockUIBase
        self.Label=MockUIBase
        self.Button=MockUIBase
        self.ScrollView=MockUIBase
        self.TextView=MockUIBase
        self.get_screen_size=lambda: (390,844)


class ResultCenterV200Test(unittest.TestCase):
    def setUp(self):
        self.ns,self.old=load_module()

    def test_single_calendar_entry_without_console_meta(self):
        state=calendar_state('查询到1项日程:\n2026年11月12日 10:3012:00海控芯操作培训')
        model=self.ns['_result_card_model'](state)
        self.assertEqual(model['title'],'日历查询完成')
        self.assertEqual(model['subtitle'],'查询到 1 项日程')
        self.assertEqual(model['items'][0]['title'],'海控芯操作培训')
        self.assertEqual(model['items'][0]['time'],'11月12日 · 10:30—12:00')
        self.assertEqual(model['body'],'')
        self.assertNotIn('Token',str(model))
        self.assertNotIn('calendar.list',str(model))
        self.assertNotIn('本地执行总结',str(model))
        self.assertIn('未独立核验',model['notice'])

    def test_multiple_calendar_entries(self):
        state=calendar_state('查询到2项日程:\n2026年11月12日 10:3012:00海控芯操作培训\n'
                              '2026年11月12日 15:0016:00部门会议')
        got=self.ns['_result_card_model'](state)
        self.assertEqual(got['subtitle'],'查询到 2 项日程')
        self.assertEqual([x['title'] for x in got['items']],['海控芯操作培训','部门会议'])

    def test_calendar_unknown_format_kept(self):
        state=calendar_state('查询到1项日程:\n不支持的异形日历记录')
        got=self.ns['_result_card_model'](state)
        self.assertTrue(got['body'])
        self.assertIn('不支持的异形',got['copy'])
        self.assertNotIn('查询到 0 项日程',got['subtitle'])

    def test_calendar_empty(self):
        got=self.ns['_result_card_model'](calendar_state('查询到0项日程:'))
        self.assertEqual(got['subtitle'],'查询到 0 项日程')
        self.assertFalse(got['items'])

    def test_calendar_invalid_date_not_invented(self):
        got=self.ns['_result_card_model'](calendar_state('查询到1项日程:\n2026年13月88日 25:3027:00伪造时间'))
        self.assertEqual(got['items'],[])
        self.assertIn('伪造时间',got['body'])

    def test_general_text_is_not_duplicate(self):
        state={'status':'finished','final':'本地执行总结：文本输出',
               'events':[{'tool':'text.respond','status':'ok','result':'沥青行情详细信息\n金陵 6100'}]}
        got=self.ns['_result_card_model'](state)
        self.assertEqual(got['body'],'沥青行情详细信息\n金陵 6100')
        self.assertNotIn('本地执行总结',got['body'])

    def test_unknown_iOS_result_not_marked_verified(self):
        state={'status':'finished','final':'已请求打开高德地图',
               'events':[{'tool':'app.navigate','status':'handoff','verified':False}]}
        got=self.ns['_result_card_model'](state)
        self.assertIn('待核验',got['subtitle'])
        self.assertIn('核对',got['notice'])

    def test_pending_state_is_distinguished(self):
        got=self.ns['_result_card_model']({'status':'awaiting_callback','events':[]})
        self.assertEqual(got['title'],'等待系统操作返回')

    def test_modal_shows_under_fake_native_UI(self):
        mock_ui=FakeUI()
        with patch.dict(sys.modules,{'ui':mock_ui}):
            got=self.ns['_result_ui_show'](calendar_state('查询到1项日程:\n2026年11月12日 10:3012:00海控芯操作培训'))
        self.assertEqual(got['title'],'日历查询完成')
        self.assertTrue(any(x.presented for x in MockUIBase.made))
        self.assertTrue(any(x.title=='完成' for x in MockUIBase.made))

    def test_final_report_does_not_call_old_console_dump(self):
        with patch.dict(self.ns,{'_result_ui_show':Mock(return_value=True)}):
            self.ns['final_report'](calendar_state('查询到0项日程:'))
        self.old.assert_not_called()

    def test_handoff_not_blocked_by_modal(self):
        with patch.dict(self.ns,{'_result_ui_show':Mock(side_effect=AssertionError('should not present'))}):
            self.ns['final_report']({'status':'finished'},show_dialog=False)
        self.old.assert_not_called()


if __name__=='__main__':
    unittest.main(verbosity=2)