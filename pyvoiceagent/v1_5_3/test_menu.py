# -*- coding: utf-8 -*-
"""UI tests: five home entries, legacy tools still reachable, safe release."""
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import patch

PATH=os.path.abspath(os.path.join(os.path.dirname(__file__),'..','agent_core_1_5_3.py'))
spec=importlib.util.spec_from_file_location('agent_menu_153',PATH)
agent=importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.dialogs=types.ModuleType('dialogs')
        self.dlgpatch=patch.dict(sys.modules, {'dialogs':self.dialogs})
        self.dlgpatch.start()
        self.statepatch=patch.object(agent,'get_state',return_value={})
        self.statepatch.start()

    def tearDown(self):
        self.statepatch.stop()
        self.dlgpatch.stop()

    def sequence(self,*choices):
        calls=[]
        queue=iter(choices)
        def prompt(title,items):
            calls.append((title,list(items)))
            return next(queue)
        self.dialogs.list_dialog=prompt
        return calls

    def test_home_has_five_actions(self):
        self.assertEqual(len(agent.MAIN_MENU),5)
        self.assertIn('语音',agent.MAIN_MENU[0])
        self.assertIn('文字',agent.MAIN_MENU[1])
        self.assertIn('上次执行',agent.MAIN_MENU[2])
        self.assertIn('更新',agent.MAIN_MENU[3])
        self.assertIn('设置',agent.MAIN_MENU[4])

    def test_home_can_exit_without_running_any_tools(self):
        called=self.sequence(None)
        with patch.object(agent,'input_voice') as voice, \
             patch.object(agent,'update_from_menu') as update:
            agent.show_menu()
        voice.assert_not_called()
        update.assert_not_called()
        self.assertEqual(len(called),1)

    def test_voice_runs_on_home_first_click(self):
        called=self.sequence(agent.MAIN_MENU[0],None)
        with patch.object(agent,'input_voice',return_value='备忘录写今天的内容') as voice, \
             patch.object(agent,'start_new') as run:
            agent.show_menu()
        voice.assert_called_once()
        run.assert_called_once_with('备忘录写今天的内容')

    def test_manual_text_route_works_through_one_submenu(self):
        sequence=self.sequence(agent.MAIN_MENU[1],agent.TEXT_MENU[0],agent.TEXT_MENU[2],None)
        with patch.object(agent,'ask_text',return_value='明天下午开会') as ask, \
             patch.object(agent,'start_new') as run:
            agent.show_menu()
        self.assertEqual(len(sequence),4)
        run.assert_called_once_with('明天下午开会')

    def test_clipboard_route_works_without_changing_ai_planner(self):
        content=types.ModuleType('clipboard')
        content.get=lambda:'把剪贴板内容保存成备忘录'
        sequence=self.sequence(agent.MAIN_MENU[1],agent.TEXT_MENU[1],agent.TEXT_MENU[2],None)
        with patch.dict(sys.modules, {'clipboard':content}), \
             patch.object(agent,'prompt_alert',return_value=True) as confirm, \
             patch.object(agent,'start_new') as run:
            agent.show_menu()
        confirm.assert_called_once()
        run.assert_called_once_with('把剪贴板内容保存成备忘录')

    def test_report_accessible_from_home(self):
        sequence=self.sequence(agent.MAIN_MENU[2],None)
        with patch.object(agent,'pretty_status') as show:
            agent.show_menu()
        show.assert_called_once_with({})

    def test_update_accessible_in_one_click_and_closes_old_menu(self):
        sequence=self.sequence(agent.MAIN_MENU[3])
        with patch.object(agent,'update_from_menu',return_value=True) as update:
            agent.show_menu()
        update.assert_called_once()
        self.assertEqual(len(sequence),1)

    def test_settings_retains_module_enrollment_and_status(self):
        sequence=self.sequence(agent.MAIN_MENU[4],agent.SETTINGS_MENU[3],
                               agent.SETTINGS_MENU[5],None)
        with patch.object(agent,'install_system_module') as install:
            agent.show_menu()
        install.assert_called_once()

    def test_advanced_keeps_recovery_and_stepwise_mode(self):
        sequence=self.sequence(agent.MAIN_MENU[4],agent.SETTINGS_MENU[4],
                               agent.ADVANCED_MENU[3],agent.ADVANCED_MENU[9],
                               agent.SETTINGS_MENU[5],None)
        with patch.object(agent,'ask_text',return_value='先读取剪贴板再整理') as ask, \
             patch.object(agent,'start_new') as execute:
            agent.show_menu()
        execute.assert_called_once_with('先读取剪贴板再整理',force_stepwise=True)

    def test_submenu_callback_returns_to_launcher_without_more_prompts(self):
        self.statepatch.stop()
        self.statepatch=patch.object(agent,'get_state',side_effect=[
            {'status':'awaiting_callback'}, {'status':'awaiting_callback'}
        ])
        self.statepatch.start()
        choices=self.sequence(agent.MAIN_MENU[1],agent.TEXT_MENU[0])
        with patch.object(agent,'ask_text',return_value='测试') as ask, \
             patch.object(agent,'start_new'):
            agent.show_menu()
        self.assertEqual(len(choices),2)


if __name__=='__main__':
    unittest.main()
