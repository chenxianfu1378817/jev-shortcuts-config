"""Native manager contracts and real temporary-file registry persistence."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'agent_core_2_3_2.py'
SPEC = importlib.util.spec_from_file_location('native_registry_candidate', CORE)
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class NativeRegistryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'registry.json'
        patches = (
            patch.object(core, 'REGISTRY_PATH', str(self.path)),
            patch.object(core, 'ensure_dirs'),
            patch.object(core, 'get_state', return_value={}),
        )
        for override in patches:
            override.start()
            self.addCleanup(override.stop)
        self.dialogs = Mock()
        self.console = Mock()
        self.values = {
            'id': 'work_tool', 'name': '工作台', 'description': '打开工作台',
            'aliases': '启动工作台，打开工作台', 'bridge': False,
            'confirm': True, 'enabled': True,
        }

    def test_new_edit_toggle_parameter_change_and_reopen(self):
        self.dialogs.list_dialog.side_effect = [
            '＋ 新建快捷指令',
            'work_tool · 工作台', '编辑',
            'work_tool · 新工作台', '设置传参方式', '传入整条指令',
            'work_tool · 新工作台', '停用',
            None,
        ]
        edited = dict(self.values, name='新工作台')
        del edited['id']
        self.dialogs.form_dialog.side_effect = [self.values, edited]
        with patch.dict(sys.modules, {'dialogs': self.dialogs, 'console': self.console}):
            core.add_shortcut_registration()
        item = core._reg_all()['work_tool']
        self.assertEqual(item['name'], '新工作台')
        self.assertFalse(item['enabled'])
        self.assertEqual(item['input_mode'], 'full')
        self.assertEqual(item['aliases'], ['启动工作台', '打开工作台'])
        edit_fields = self.dialogs.form_dialog.call_args_list[1].kwargs['fields']
        self.assertNotIn('id', [field['key'] for field in edit_fields])

    def test_duplicate_id_reopens_with_draft_then_cancel_preserves_bytes(self):
        core._reg_save(self.values)
        before = self.path.read_bytes()
        changed = dict(self.values, name='草稿名称')
        self.dialogs.form_dialog.side_effect = [changed, None]
        self.assertFalse(core._reg_native_form(self.dialogs, self.console))
        self.console.alert.assert_called_once()
        fields = self.dialogs.form_dialog.call_args.kwargs['fields']
        self.assertEqual(next(field['value'] for field in fields if field['key'] == 'name'), '草稿名称')
        self.assertEqual(self.path.read_bytes(), before)

    def test_pending_task_and_unconfirmed_delete_never_mutate(self):
        core._reg_save(self.values)
        before = self.path.read_bytes()
        self.dialogs.list_dialog.side_effect = [
            'work_tool · 工作台', '删除登记',
            'work_tool · 工作台', '停用',
            None,
        ]
        with patch.dict(sys.modules, {'dialogs': self.dialogs, 'console': self.console}), \
             patch.object(core, 'prompt_alert', return_value=False), \
             patch.object(core, 'get_state', return_value={'status': 'awaiting_callback'}):
            core.add_shortcut_registration()
        self.console.alert.assert_called_once()
        self.assertEqual(self.path.read_bytes(), before)

    def test_explicit_delete_removes_only_selected_record(self):
        core._reg_save(self.values)
        core._reg_save(dict(self.values, id='other_tool', aliases='另一项'))
        self.dialogs.list_dialog.side_effect = ['work_tool · 工作台', '删除登记', None]
        with patch.dict(sys.modules, {'dialogs': self.dialogs, 'console': self.console}), \
             patch.object(core, 'prompt_alert', return_value=True):
            core.add_shortcut_registration()
        self.assertEqual(set(core._reg_all()), {'other_tool'})


class RegistryWindowTests(unittest.TestCase):
    def test_dialog_runs_after_chat_close_then_chat_reopens(self):
        events = []
        first = Mock(registry_requested=True)
        second = Mock(registry_requested=False)
        first.show.side_effect = lambda: events.append('chat modal returned')
        first.close.side_effect = lambda: events.append('chat cleaned up')
        second.show.side_effect = lambda: events.append('chat reopened')
        with patch.object(core, '_ChatShell', side_effect=[first, second]), \
             patch.object(core, 'add_shortcut_registration',
                          side_effect=lambda: events.append('native dialog')):
            core.show_menu()
        self.assertEqual(events, ['chat modal returned', 'chat cleaned up', 'native dialog', 'chat reopened'])

    def test_title_bar_action_closes_chat_without_webview_call(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            shell = core._ChatShell()
        holder = Mock(bounds=(0, 0, 390, 844))
        web = Mock()
        ui = SimpleNamespace(
            get_screen_size=lambda: (390, 844),
            View=Mock(return_value=holder),
            WebView=Mock(return_value=web),
            ButtonItem=lambda **kwargs: SimpleNamespace(**kwargs),
            delay=Mock(),
        )

        def press_native_toolbar_button():
            button = holder.right_button_items[0]
            self.assertEqual(button.title, '快捷指令')
            button.action(button)
            button.action(button)

        holder.wait_modal.side_effect = press_native_toolbar_button
        with patch.dict(sys.modules, {'ui': ui}), \
             patch.object(core, '_card_appearance_load', return_value={}), \
             patch.object(core, '_card_palette', return_value={'background': '#ffffff'}):
            self.assertTrue(shell.show())
        self.assertTrue(shell.registry_requested)
        holder.close.assert_called_once()
        web.eval_js.assert_not_called()
        self.assertNotIn('PYRegistryTake', core.CHAT_HTML)
        self.assertNotIn('reg-save', core.CHAT_HTML)

    def test_busy_shell_does_not_open_or_close_registry_window(self):
        with patch.object(core, '_chat_transcript_load', return_value=[]):
            shell = core._ChatShell()
        shell.holder = Mock()
        shell.busy = True
        console = Mock()
        with patch.dict(sys.modules, {'console': console}):
            shell.request_registry()
        self.assertFalse(shell.registry_requested)
        console.hud_alert.assert_called_once()
        shell.holder.close.assert_not_called()
