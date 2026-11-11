# PYVoiceAgent V3 · 独立引擎（Alpha 0.1.0）

> **开发阶段 / 非手机版正式发布。** 这个目录与现有 V2.3.9 严格分离，**不会修改** `pyvoiceagent/manifest.json`、固定入口 `PYVoiceAgent.py`，也不会读取或覆盖旧 `PYVoiceAgent_Data` 中的记录、设置、API Key、提醒或快捷指令。通过电脑自动化测试 **不代表** 已在 iPhone Pythonista 真机验收。

## 为什么重新设计

旧项目虽拆出了多个编号文件，最终仍拼成一个共享全局变量、猴子补丁和原生 UI 回调的超大脚本。更换 WebView、录音线程和原生 UI 后，文字发送、历史等依然出现真机崩溃。因此 V3 不再延续 V2 的运行机制：**先隔离任务引擎，再接入经过真机验收的手机交互层。**

## 已实现：真正独立的 Python 包

| 目录 | 职责 | 安全边界 |
|---|---|---|
| `core/models.py` | 不可变的任务结果和输入异常 | 不依赖 Apple API |
| `core/state_machine.py` | 有限状态机，严格禁止非法跳转 | 不重复执行已完成任务 |
| `core/dispatcher.py` | 本地意图、AI 授权、快捷指令交接 | 每次只读/外部操作均有明确状态 |
| `storage/sqlite_store.py` | SQLite 事务、唯一请求 ID、事件记录、备份 | `BEGIN IMMEDIATE`，崩溃后不自动重试 |
| `services/settings.py` | 八主题、浅色/深色/系统与自定义颜色 | 配置持久化到 V3 私有数据库 |
| `services/shortcuts.py` | 动态登记、别名冲突、待确认交接 | **只准备请求，不执行任何苹果快捷指令** |
| `services/history.py` | V3 分页历史、V2 原数据**只读预览** | 不迁移、不更改旧文件 |
| `services/llm.py` | 独立 DeepSeek HTTPS 文字接口 | 逐次同意、超时、异常脱敏；不执行工具 |
| `adapters/pythonista_cli.py` | 最小 Pythonista / Mac 文字命令入口 | 不引入 `ui`、`sound`、`speech`、`objc_util` |
| `contracts/*.json` | 输入、事件、外部工具交接的机器可读契约 | 不等同于能自动获得 iOS 系统权限 |

V3 是实际 Python `import` 分包，**不是编译时拼接脚本**。业务、存储、平台适配器分离；不需要把手机 UI 和网络/任务执行放在同一个回调里。

## 立即可运行的无副作用检查（Mac、Windows、Linux）

在 GitHub 仓库根目录：

```bash
python3 -m pyvoiceagent_v3 --data ./private_v3_test_data --check
python3 -m pyvoiceagent_v3 --data ./private_v3_test_data
```

第二行只打开**控制台文字测试模式**，可输入 `你好`、`/历史`、`/工具`、`/设置`、`/诊断`、`/帮助`、`/中断任务`、`/主题 典雅紫`、`/模式 深色模式`、`/退出`。未知问题将生成**待 AI 授权**状态，但默认不会联网，也不调用快捷指令或苹果日历、提醒事项。

**Pythonista:** 这是标准库 Python 项目。拥有源码后可从 Pythonista 控制台运行单次命令，但目前没有为 iPhone 推送、打包或安装 V3；不需要也不应覆盖现有入口。不要将“标准 Python 模拟通过”当作 iPhone 界面稳定性验收。

### 可选 DeepSeek（仅在独立验证环境）

仅在用户明确希望验证并自行提供凭据时，用环境变量 `DEEPSEEK_API_KEY` 和 `--enable-ai` 启动。第一次输入普通问题仅生成等待确认任务，必须再输入 `/同意 <完整task_id>` 才可能发送**这一条文字**到 DeepSeek。拒绝则输入 `/拒绝 <完整task_id>`。密钥不会保存到 SQLite 或日志。

本阶段 DeepSeek **只允许回答文字**，不会自动规划/运行 iOS 系统工具。`Shortcuts` 注册表仅生成 `executed=false` 的待授权交接数据，没有真正执行快捷指令的权限。

## 历史与数据保护

- 默认 V3 数据目录：`~/Documents/PYVoiceAgent_V3_Data/agent_v3.sqlite3`，**不同于** V2 的 `PYVoiceAgent_Data`。
- `LocalStore.backup(path)` 使用 SQLite 事务一致性备份，拒绝覆盖已有备份。
- 旧历史需显式调用 `HistoryService.preview_legacy(v2_data_dir)`，只读、限制扫描数量与大小、跳过不符合命名规则或损坏的数据，不会导入、更改或移动旧文件。
- 外部 AI 任务若在 `running` 时中断，再启动不会自动重新执行；可调用 `running_tasks()` 只读查看，并通过 `mark_interrupted(task_id)` 标为 `needs_review` 等待人工核验。
- 快捷指令是分阶段状态：`waiting_confirmation -> handoff_ready -> needs_review`。**本地仅生成交接信息，不声称已经执行成功。**

## 自动测试

```bash
python3 -m unittest discover -s pyvoiceagent_v3/tests -v
```

测试包括去重并发、事务回滚、授权/拒绝/审批重复、网络超时与错误、恶意/损坏数据、历史只读、数据库备份、八套主题、重复触发词、CLI 无网络检查等。测试使用假远程响应，不调用真实 DeepSeek 或 iOS 系统。

## 明确未完成的功能与验证

- 目前**不是**可直接替代 V2.3.9 的手机 App：没有新的长期聊天 UI；没有真实语音录音、历史 UI、快捷指令/日历/提醒执行适配器。
- AI 多轮上下文、Token 预算、工具执行器、状态数据库迁移、原生 iPhone UI/PWA、正式版本在线更新仍需要继续开发和逐项验收。
- **不推送** V3 到 V2 正式 `manifest.json`。以后先在同一台 iPhone 验证独立入口冷启动/退出、输入、历史、设置，再分阶段接入 AI 与已授权工具。
- 如原生 Pythonista 进程继续 SIGSEGV，必须结合经脱敏的 iOS `.ips` 报告，不能凭单元测试宣称“绝不闪退”。

后续决策与技术原则见 [ARCHITECTURE_DECISION.md](ARCHITECTURE_DECISION.md)；设计验收清单见 [MILESTONES.md](MILESTONES.md)。
