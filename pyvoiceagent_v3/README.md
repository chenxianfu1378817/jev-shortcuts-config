# PYVoiceAgent V3.0.1 · DeepSeek 直发与网络故障诊断（iPhone 待验收）

- **版本：** 3.0.1 / 更新序号 301；保持原 Pythonista `PYVoiceAgent.py` 启动入口。
- **本地问候：** `你好` 由本地引擎直接回复，“无需联网”不等于网络错误。
- **直接聊天：** 已设置 DeepSeek Keychain 凭据时，按“发送”即可将本次普通文字发送给 DeepSeek，无需额外点“同意”。这可能产生 API Token 费用；系统快捷指令与外部写操作仍需要确认。
- **密钥：** 优先读取 V3 Keychain，兼容读取旧版 `PYVoiceAgent_DeepSeek / main`，不将密钥写入源码/数据库。
- **错误分类：** 可区分 401 无效 Key、402 余额不足、429 限流、HTTP 5xx、请求超时和 TLS 证书错误；错误文案不包含服务端原始报文或 Key。
- **模型：** 继续使用官方 `deepseek-flash`，明确指定非思考模式，降低简单对话的延迟及隐含推理 Token 消耗。
- **版本边界：** 电脑自动化测试不能代表 iPhone 真机已通过。保留旧引擎、个人 SQLite、历史与工具配置。界面仍为系统菜单，卡片 UI 待真机稳定性验收后再推进。

## 安装与验证

在手机 Pythonista 中运行原有 `PYVoiceAgent.py` 触发更新；退出后重新进入。先检查设置的“运行诊断与版本”应显示 V3.0.1 及 Keychain 状态。输入 `你好` 测试本地分流，再输入 `1+1等于几？` 测试 DeepSeek。无需重新录入已保存的 Key；若出现 HTTP 401/402 等可据提示检查密钥或账户余额。不要把 API Key 发到聊天或 GitHub。首次真机测试请勿进行重复日历/提醒写入。

---

# PYVoiceAgent V3.0.0 · iPhone 在线升级与可用版本

> **手机可安装候选（iPhone 真机尚未验收）。** V3.0.0 接入原来固定的 `PYVoiceAgent.py` GitHub 更新器，版本序号 300。现在不再仅是 Mac 命令行测试。本文下方的「Alpha 0.1.0 非手机版」描述只适用于先前第一阶段历史记录。

## 在 iPhone 直接安装（无需 ZIP 或 IPA）

1. 使用 Pythonista 3 中现有的 `PYVoiceAgent.py`；保持原桌面入口、图标和快捷指令路径。
2. 正常启动时固定启动器依据 GitHub `pyvoiceagent/manifest.json` 检查更新（版本 3.0.0 / 序号 300）；下载并 SHA-256 校验单个 `agent_core_3_0_0.py`。如果手机启动器未自动检查，请通过现有更新功能触发，不要复制替换旧版数据文件。
3. 完成后**退出再运行一次固定入口**。启动器会在 `~/Documents/PYVoiceAgent_V3_Runtime/releases/` 安装不可变的、经过二次摘要校验的独立 Python 包，不要求手工逐项下载。
4. 启动后出现「PYVoiceAgent V3 · 稳定入口」原生系统菜单，可直接使用文字、剪贴板、系统键盘听写、DeepSeek AI、历史、工具库、设置与在线更新。
5. 日后 V3 更新仍从设置的「检查在线更新」完成，并通过原 `PYVoiceAgent.py` 重启生效。

## 正式进入手机的功能和使用条件

| 功能 | V3.0.0 状态 |
|---|---|
| 文字输入、剪贴板任务及系统键盘语音听写 | 已实现；不再使用容易崩溃的持续 WebView 录音界面 |
| 本地基本指令（你好、帮助、历史、设置等） | 已实现 |
| DeepSeek 文字问答 | 已实现；需已有 Pythonista Keychain 凭据或在 V3 设置中配置；**每条新问题明确同意才联网** |
| 快捷指令工具库 | 已实现；支持手动登记及**由用户确认后导入 V2 的 launch 模式工具**；旧 bridge 模式不自动迁移 |
| 快捷指令调用 | 已实现用户明确授权后的 `shortcuts://run-shortcut` 官方 URL 交接；**不声称运行成功、不自动重试，结果须人工核验** |
| V3 历史、旧 V2 历史只读预览 | 已实现；旧历史不自动导入或覆盖 |
| 设置、八套主题、浅色/深色/跟随系统 | 设置可持久保存；当前使用 iOS 标准系统弹窗，**尚未实现八主题同步渲染的卡片 UI**，为稳定性暂作让步 |
| SQLite 本地数据库、独立备份 | 已实现，存于 `~/Documents/PYVoiceAgent_V3_Data/` |
| 手机内在线更新与版本回退备份 | 已实现，对发布 manifest、文件大小、SHA-256、Python 语法校验，旧引擎保留为 `engine/previous.py` |
| V2 日历、提醒、联系人及 BU 行情复杂自动执行 | **尚未全部迁入 V3**；可以通过现有已登记的直达型快捷指令显式交接，旧式带回调的工具需要后续适配 |

## 重要限制与故障保护

- **手机真实稳定性未验证**：Mac/CI 的 Python 3.9/3.11 自动测试无法证明在用户 iPhone 上不会闪退。
- **不会自动执行旧版未完成任务或回调**。收到旧 `bridge_callback` 入口会提示核验，以免重复创建日历、提醒事项。
- **Keychain** 优先读 V3 专属凭据，没配置时只读取已有 V2 Keychain，不会把密钥写入数据库。即使有密钥，AI 请求仍逐次征求同意。
- iPhone 菜单首版用 Pythonista 成熟 `dialogs` 与 `console`，不创建持续运行的 WebView 或录音线程；这不是最终的卡片对话版面。
- **升级不得覆盖** `~/Documents/PYVoiceAgent_Data/` 里的历史、用户设置、API Key 或自定义快捷指令配置。旧更新器只能更新它自己的 `engine/current.py` 和 `update_meta.json`。
- 首次更新后如果没有启动 V3，检查本机 `PYVoiceAgent_Data/update_meta.json` 的安装序号是否为 300，且关闭 Pythonista 重新启动；不要删除个人数据文件夹。
- 手机端若仍崩溃，应提供 iOS 设置内经过脱敏的 .ips 日志，先定位之后再修改原生 UI；不要使用真实日历写入重复测试。

## 开发构建

```bash
python pyvoiceagent_v3/tools/build_mobile_release.py --write
python pyvoiceagent_v3/tools/build_mobile_release.py
python -m unittest discover -s pyvoiceagent_v3/tests -v
```

生成正式更新文件 `pyvoiceagent/agent_core_3_0_0.py` 与 `pyvoiceagent/manifest.json`，后者包含字节数与 SHA-256。所有 V3 源码仍以真正的 Python 模块存在，并通过可重复的 ZIP 归档嵌入单文件，不需要在手机上手工 pip 安装。

---

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
