# -*- coding: utf-8 -*-
"""V2.0.1 lifecycle regression; CPython mocks are NOT iPhone real-device tests."""
import ast
import copy
import hmac
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

SOURCE = Path(__file__).resolve().parents[1] / 'agent_core_2_0_1.py'
TREE = ast.parse(SOURCE.read_text('utf-8'))
NAMES = ('_card_should_show_home', '_card_current_callback', '_card_dispatch', 'main')
FUNCS = [next(node for node in reversed(TREE.body)
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name)
         for name in NAMES]
SNIPPET = compile(ast.Module(body=FUNCS, type_ignores=[]), str(SOURCE), 'exec')


def setup(entry=(), current=None, outcome='handoff'):
    state = current if current is not None else {'status': 'finished',
           'events': [{'tool': 'text.respond', 'status': 'ok'}]}
    original = Mock(return_value=outcome)
    run = Mock()
    home = Mock()
    env = dict(get_state=lambda: copy.deepcopy(state), hmac=hmac,
               sys=type('FakeSys', (), {'argv': ['PYVoiceAgent.py', *entry]})(),
               _V200_DISPATCH=original, _V200_MAIN=run, show_menu=home)
    exec(SNIPPET, env)
    return env, state, original, run, home


class LifecycleV201(unittest.TestCase):
    def test_local_dispatch_reenters_home(self):
        for action in ('voice', 'input', 'clipboard', 'stepwise'):
            with self.subTest(action=action):
                env, state, old, _, _ = setup()
                self.assertEqual(env['_card_dispatch'](action, 'test'), 'stay')
                old.assert_called_once_with(action, 'test')

    def test_shortcut_wait_does_not_hold_main_modal(self):
        env, state, _, _, _ = setup(current={'status':'awaiting_callback'})
        self.assertEqual(env['_card_dispatch']('voice'), 'handoff')

    def test_native_map_handoff_keeps_other_app_foreground(self):
        for tool in ('app.navigate', 'maps.search'):
            with self.subTest(tool=tool):
                state={'id':'old', 'status':'finished', 'events':[
                    {'tool':'text.respond','status':'ok'}]}
                env, _, old, _, _ = setup(current=state)
                def open_native_app(*args):
                    state.update(id='new',status='finished',
                        events=[{'tool':tool,'status':'ok'}])
                    return 'handoff'
                old.side_effect = open_native_app
                self.assertEqual(env['_card_dispatch']('input'), 'handoff')

    def test_cancelling_recording_after_previous_map_returns_home(self):
        state={'id':'old', 'status':'finished','events':[
            {'tool':'maps.search','status':'ok'}]}
        env, _, original, _, _ = setup(current=state)
        self.assertEqual(env['_card_dispatch']('voice'), 'stay')
        original.assert_called_once()
        self.assertEqual(env['_card_should_show_home'](),False)
        env2, _, _, run, home = setup(('voice',),current=state)
        env2['main']()
        run.assert_called_once()
        home.assert_called_once()

    def test_no_home_for_explicit_update_or_export(self):
        for action in ('update', 'history_share', 'contact_import'):
            env, _, _, _, _ = setup()
            self.assertEqual(env['_card_dispatch'](action), 'handoff')

    def test_voice_url_returns_home_without_second_task(self):
        env, _, _, run, home = setup(('voice',))
        env['main']()
        run.assert_called_once()
        home.assert_called_once()

    def test_text_url_returns_home(self):
        env, _, _, run, home = setup(('text','hello'))
        env['main']()
        run.assert_called_once()
        home.assert_called_once()

    def test_bu_capture_never_opens_ui(self):
        env, _, _, run, home = setup(('bu_close','night'))
        env['main']()
        run.assert_called_once()
        home.assert_not_called()

    def test_valid_callback_returns_home(self):
        token = 'safeabc'
        state = {'status':'awaiting_callback','pending':{'token':token}, 'events':[]}
        env, _, _, run, home = setup(('bridge_callback', token,'ok'),state)
        def after_callback():
            state['status'] = 'finished'
        run.side_effect = after_callback
        env['main']()
        home.assert_called_once()

    def test_unrelated_callback_never_opens_ui(self):
        state = {'status':'awaiting_callback','pending':{'token':'different'}}
        env, _, _, _, home = setup(('bridge_callback','unknown','ok'),state)
        env['main']()
        home.assert_not_called()

    def test_next_shortcut_step_suppresses_home(self):
        token='nextstep'
        state = {'status':'awaiting_callback','pending':{'token':token}}
        env, _, _, _, home = setup(('bridge_callback',token,'ok'),state)
        env['main']()
        home.assert_not_called()

    def test_legacy_callback_returns_home_only_if_active(self):
        state={'status':'awaiting_callback','pending':{'tool':'shortcut.echo'}}
        env, _, _, run, home = setup(('callback','DONE'),state)
        run.side_effect=lambda:state.update(status='finished')
        env['main']()
        home.assert_called_once()
        env2, _, _, _, home2 = setup(('callback','NO'),{'status':'finished'})
        env2['main']()
        home2.assert_not_called()

    def test_manual_close_not_force_reopened(self):
        env, _, _, _, home = setup(())
        env['main']()
        home.assert_not_called()

    def test_source_version(self):
        source = SOURCE.read_text('utf-8')
        self.assertIn("VERSION = '2.0.1-deepseek-flash'",source)
        self.assertIn('_V200_MAIN = main',source)
        self.assertIn('_V200_DISPATCH = _card_dispatch',source)

if __name__ == '__main__':
    unittest.main(verbosity=2)
