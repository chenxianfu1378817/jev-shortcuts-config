# PYVoiceAgent V2.3.6 全功能模块化架构

## 设计原则和当前实现边界

为保留已经在 iPhone 安装的固定入口 `PYVoiceAgent.py`、原升级清单协议和 350,000 字节的下载上限，本阶段采用 **GitHub 源码按业务模块拆分 + 确定性兼容打包**。

- **开发端**：`pyvoiceagent/src/` 中分模块修改，不再直接修改 35 万字节的最终发布引擎；每次构建自动覆盖所有功能。
- **发布端**：`tools/build_modular.py` 只读取源文件、严格按文件名顺序组装，使用 tokenize 识别和移除非语义注释，使用 AST 逐节点比较确保删除注释没有改变语法结构，运行 compile；检查单文件上限和 SHA-256，生成 `agent_core_2_3_6.py` 与 `manifest.json`。
- **兼容端**：手机依旧只下载一个受 SHA-256 校验的引擎文件，不需要安装第三方扩展、手工搬运模块或重新签名。业务数据和密钥仍留在设备。
- **真实运行时隔离**：本次新建的 `_VoiceSession` 是有明确构造参数和回调接口的独立运行时音频服务，原生 Recorder 生命周期仅由专属工作线程拥有。
- **尚未实现**：其他源码单元目前仍使用旧引擎的共享全局接口。源码已全量拆分，但不能称为全部业务模块之间都实现了彻底的运行时依赖隔离。后续逐模块注入 `Storage / ToolRegistry / Calendar / DeepSeek` 接口，不破坏固定启动器和用户数据。

## 全部源码模块一览

| 文件 | 子系统 | 职责 |
| --- | --- | --- |
| `00_bootstrap.py` | 全局配置、工具定义 | 版本、路径、白名单、参数、全局协议 |
| `10_app_routes.py` | App 唤起 | URL 路由与系统跳转 |
| `11_contacts_clipboard.py` | 通讯录 | 剪贴板识别联系人和防重复登记 |
| `12_local_routing.py` | 本地意图 | 简单指令直达，不请求 DeepSeek |
| `20_state_settings.py` | 配置和持久化 | 任务状态、原子写入、密钥与参数 |
| `21_decision_validation.py` | 决策契约 | 模型输出及工具参数校验 |
| `22_deepseek.py` | AI 接口 | 网络请求、规划接口 |
| `23_natural_language.py` | 自然语言任务 | 日期和计划解析 |
| `24_voice_legacy.py` | 旧语音兼容 | 传统录音入口与语音播报保留 |
| `25_clarifications_planner.py` | 多轮任务 | 补充提问、计划和执行循环 |
| `26_shortcuts_bridge.py` | 苹果快捷指令桥接 | 回传、幂等性、令牌和人工核验 |
| `27_ios_services.py` | iOS 工具 | 提醒、日历、通讯录、地图、备忘录 |
| `28_research.py` | 联网资料与分析 | 公开网页验证、研究辅助 |
| `29_agent_execution.py` | 工具执行器 | 工具分流、回执、任务状态 |
| `30_shortcuts_generator.py` | 快捷指令生成 | 工作流、动作参数与导出 |
| `31_task_start_voice.py` | 启动和传统语音 | 任务入口、旧式录音转写 |
| `32_updater.py` | GitHub 更新器 | 下载、验签式摘要校验、回滚 |
| `33_menus.py` | 系统菜单 | 传统原生设置、工具状态 |
| `34_bu_market.py` | BU 沥青期货 | 快照、合约、日历同步 |
| `39_voice_session.py` | **独立音频服务** | 专属线程录音生命周期、取消、识别 |
| `40_ui_cards.py` | 卡片界面 | 首页、主题、设置、系统菜单 |
| `41_history.py` | 历史档案 | 本地归档、查询、导出 |
| `42_result.py` | 结果展示 | 日历结构化结果和执行结果卡片 |
| `43_chat.py` | 长对话 WebView | 持续对话、JS 事件、键盘与输入、音频服务接入 |
| `44_registered_tools.py` | 本地快捷指令管理 | 登记、编辑、参数、启停、授权和执行 |

这些文件是**构建源码**，不能像独立 Python 软件一样单独运行。新业务逻辑应逐步沉淀为独立服务，不能在构建产物中追加猴子补丁。

## 音频问题定位与修复

用户在 V2.3.5 确认「第二次点击麦克风停止录音」仍然导致 Pythonista 退出。此前：

1. `ui.delay` 回调在 Pythonista 的 UI 线程创建并开始 `sound.Recorder`；
2. V2.3.4 以后却在新建后台线程调用 `stop()`；
3. 退出/取消路径还可能在其他线程再次停止同一 Recorder，存在 native 对象跨线程及重复释放风险；
4. 即使捕获了普通 Python 异常，也无法捕获 Objective-C/C 层的 SIGSEGV。

V2.3.6 让 `_VoiceSession` 从开始到停止持有 Recorder，**所有 native Recorder 操作均在同一工作线程**进行，UI 只发出 Event 请求；关闭或取消只设置 cancel/stop 标志，识别完成时必须再次核对取消状态。测试覆盖双击停止、异常只调用一次 stop、取消时不提交文字、原生回调只发控制信号。

**此措施是对源码中明确风险的有针对性调整，不是 iPhone 已证明的根因和修复结论。** 若 iPhone 仍闪退，优先根据本地 `voice_last_stage.json` 的最后阶段和脱敏 .ips 堆栈区分 `record()`、`stop()`、`speech.recognize()` 或 WebView 回调。

## 构建和测试

Mac/CI 的仓库工作目录：

```bash
python pyvoiceagent/tools/build_modular.py --sequence 236 --write
python pyvoiceagent/tools/build_modular.py --sequence 236
python -m unittest discover -s pyvoiceagent/tests -p 'test_voice_session_v236.py' -v
python -m unittest discover -s pyvoiceagent/tests -p 'test_chat_audio_integration_v236.py' -v
python -m unittest discover -s pyvoiceagent/tests -p 'test_modular_build_v236.py' -v
```

GitHub Actions `PYVoiceAgent modular candidate builder` 只在功能分支自动生成候选并提交，不自动更新 `main`。正式手机发布前还必须检查 PR CI 和远程清单、引擎字节、SHA-256 一致；测试通过≠iPhone 真机无崩溃。

## 数据不变量和回退

- `~/Documents/PYVoiceAgent_Data/`、Keychain、历史、工具登记、任务和 BU 台账不在源码分包目录内，不做覆盖。
- 用户现有 `PYVoiceAgent.py` 不更名、不用 ZIP、不安装 IPA、不要求重新制作快捷指令。
- 不改已存在的日历和提醒创建/回调协议，不对不明确的真实写入自动重试。
- 保留旧正式引擎在 GitHub 历史中的版本，更新器沿用现有 `previous.py` 回退机制，不改变旧更新器的信任和文件大小限制。
- 若升级后声音输入仍导致 Pythonista 闪退，请立即停止反复触发该路径并使用文字输入；提供脱敏诊断阶段才能继续准确定位。
