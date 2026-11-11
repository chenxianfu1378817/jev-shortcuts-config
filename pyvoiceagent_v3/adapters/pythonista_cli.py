"""Optional Pythonista/desktop console entry; not a persistent app UI.

Only uses standard input/output. Never imports ui, sound, speech, dialogs,
objc_util or an unsafe URL navigation bridge. The V2 launcher is untouched.
"""
import argparse
import os
from pathlib import Path
import sys

from ..storage.sqlite_store import LocalStore
from ..core.dispatcher import Agent
from ..services.history import HistoryService
from ..services.settings import THEMES, MODES
from ..services.llm import DeepSeekText


def default_data_dir():
    return os.path.join(os.path.expanduser('~/Documents'), 'PYVoiceAgent_V3_Data')


def run(argv=None, input_fn=input, output_fn=print):
    parser = argparse.ArgumentParser(description='PYVoiceAgent V3 safe core (preview)')
    parser.add_argument('--data', default=default_data_dir(), help='separate V3 data folder')
    parser.add_argument('--check', action='store_true', help='no network, no real iOS actions')
    parser.add_argument('--enable-ai', action='store_true',
                        help='allow explicit consent flow using DEEPSEEK_API_KEY env var')
    args = parser.parse_args(argv)
    data = os.path.abspath(args.data)
    store = LocalStore(os.path.join(data, 'agent_v3.sqlite3'))
    key = os.environ.get('DEEPSEEK_API_KEY', '') if args.enable_ai else ''
    agent = Agent(store, llm=DeepSeekText(key) if key else None)
    if args.check:
        output_fn('V3 检查成功：SQLite/状态引擎正常；未调用 DeepSeek 或手机系统接口。')
        return 0
    output_fn('PYVoiceAgent V3 隔离测试入口，输入 /帮助；/退出 结束。')
    output_fn('当前无 WebView、录音或自动快捷指令；AI 需 --enable-ai 且逐次同意。')
    while True:
        try:
            text = input_fn('V3 > ')
        except (KeyboardInterrupt, EOFError):
            output_fn('已安全退出')
            return 0
        if text is None or text.strip() in ('/退出', '/quit', '/exit'):
            output_fn('已安全退出')
            return 0
        value = str(text).strip()
        if not value:
            continue
        if value.startswith('/同意 ') or value.startswith('/拒绝 '):
            yes = value.startswith('/同意 ')
            task_id = value.partition(' ')[2].strip()
            try:
                result = agent.approve_remote(task_id, yes)
                output_fn('[{}] {}'.format(result.status, result.message))
            except (KeyError, ValueError) as exc:
                output_fn('授权状态无效：'+type(exc).__name__)
            continue
        if value.startswith('/恢复检查 '):
            task_id = value.partition(' ')[2].strip()
            try:
                row = store.mark_interrupted(task_id)
                output_fn('任务状态：'+row['status']+'；不会自动重试')
            except (KeyError, ValueError) as exc:
                output_fn('恢复检查失败：'+type(exc).__name__)
            continue
        if value in ('/中断任务', '/interrupted'):
            pending = store.running_tasks()
            output_fn('待核验运行中任务：'+str(len(pending)))
            for row in pending:
                output_fn('  '+row['task_id']+' ('+row['created_at']+')')
            continue
        if value.startswith('/旧历史预览 '):
            folder = value.partition(' ')[2].strip()
            preview = HistoryService.preview_legacy(folder)
            output_fn('只读预览：找到{}项，跳过{}项，无文件修改'.format(
                len(preview['entries']), preview['skipped']))
            continue
        if value.startswith('/主题 '):
            theme = value.partition(' ')[2].strip()
            if theme in THEMES:
                agent.appearance.change(theme=theme)
                output_fn('主题已保存：'+theme)
            else:
                output_fn('未知主题：'+', '.join(THEMES))
            continue
        if value.startswith('/模式 '):
            mode = value.partition(' ')[2].strip()
            if mode in MODES:
                agent.appearance.change(mode=mode)
                output_fn('模式已保存：'+mode)
            else:
                output_fn('未知模式：'+', '.join(MODES))
            continue
        try:
            answer = agent.submit(value)
            output_fn('[{}] {}：{}'.format(answer.status, answer.task_id[:8], answer.message))
            if answer.status == 'waiting_consent':
                output_fn('AI 授权方式：/同意 '+answer.task_id+' 或 /拒绝 '+answer.task_id)
            elif answer.status == 'waiting_confirmation':
                output_fn('本测试版不会执行快捷指令，确认也不会触发 iOS 系统动作。')
        except Exception as exc:
            output_fn('输入未处理：{}'.format(type(exc).__name__))


if __name__ == '__main__':
    sys.exit(run())
