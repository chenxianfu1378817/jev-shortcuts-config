# PYVoiceAgent V2.1.0｜Pythonista 本地 WebView 混合架构（2026-11-11）

## 技术结构

- **Python**：保留 V2.0.2 的 DeepSeek 规划、语音、提醒事项、日历、备忘录、联系人、BU 行情、历史记录、回调、防重复、用户数据及 GitHub 自动更新。
- **Pythonista ui.WebView + HTML/CSS/JavaScript**：重新实现首页、双列常用卡片、固定底部导航、文本输入、结果页、历史搜索与详情、设置、外观与主题、工具库、高级操作。所有界面代码直接嵌在正式单文件引擎中，从本机 `load_html()` 加载。
- **本地原生桥**：通过 `pyagent-ui://dispatch` 自定义 URL，由 `webview_should_start_load` 拦截并交给 Python。仅开放固定白名单；每次页面使用随机 nonce，非法 URL 或不匹配 nonce 不执行动作。Python 读取档案或保存主题后，只通过安全编码的 JSON 将结果回传给页面。
- **离线默认**：不调用外部 CDN、网站或本地 HTTP 服务；页面 CSP 禁止网络资源。只有实际使用 DeepSeek 或 GitHub 更新等原有业务功能才可能联网。
- **回退**：WebView 初始化失败或当前 Pythonista 不支持 WebView 时自动使用原 V2.0.2 原生 ui 界面。并未删除任何旧功能或设置数据。

## 用户界面

1. 顶部名称与版本；最近任务状态汉化。
2. 大面积主题色语音按钮；保持原有“点击开始、说完手动结束”。
3. 常用功能双列卡片，检查更新和设置独立分组。
4. 首页、结果、档案、设置底部导航。
5. 独立结果与日历详情页；复制、历史检索及详情查看。
6. 八套主题、浅色/深色/跟随系统、可自定义颜色；修改实时写入原 `appearance.json`，无需迁移或删除数据。
7. 所有页面在本地运行；更换页面不重启 Python 业务引擎。

## 安全与兼容

- 不修改原快捷指令 URL（`voice`、`text`、`bridge_callback`）、固定入口 `PYVoiceAgent.py` 或 BU 定时入口。
- 不改变系统授权逻辑、不自动收音、不重复调用已执行的任务。
- WebView 完成操作之后才将动作交给既有 `_card_dispatch`；等待快捷指令回调或真正打开地图 App 时保留原有 handoff 流程。
- 原始业务档案、API Key 与个人配置仍然保存在手机本机。
- `webui/index_v210.html` 是可维护的独立界面源码；`webui_v210.py` 是 Python 桥接与内置 HTML 维护源；正式手机只更新 `agent_core_2_1_0.py`，无需额外安装 HTML。
- 不依赖 Pythonista 第三方 WKWebView 插件，使用官方 `ui.WebView` API；因不同 iOS/Pythonista 版本 WebView 表现可能不同，保留原生 ui 降级。

## 测试

- 本地 Python 3.13：`webui_v210.py` 桥接模块通过语法检查；13 项隔离模拟测试通过（拒绝外部 URL、错误 nonce、任务分派、结果回传、主题持久化、历史检索、复制、无 WebView 回退等）。
- 本地 Node.js 22：HTML 两段 JavaScript 通过语法解析，模拟 DOM 导航与主题切换通过。
- GitHub Actions 工作流 `pyvoiceagent-v210.yml` 已加入，但仓库之前多次收到 `startup_failure`；如果同样发生，**不能声称 CI 通过**。
- 当前环境无法执行 iPhone Pythonista/WebView 真机测试，不能保证 iOS 27 下的实际录音、键盘、安全区域、系统回调、内存占用与生命周期已经验收。

## 手机上如何升级与验收

1. 在已安装的 V2.0.2 页面点击 **检查更新**，安装 V2.1.0 后退出并从原固定入口重新打开，不需要重新安装 Pythonista 或 ZIP。
2. 确认出现 WebView 风格的首页，检查语音、文字、结果、历史、设置与底部导航。
3. 首先用**只读或纯文字任务**验证：执行文字任务 → 结果卡片 → 完成 → 首页。
4. 再验证语音“手动结束”，随后仅执行一次日历只读查询，检查快捷指令回调后是否返回结果页和首页。
5. 最后验证地图跳转、主题切换及历史搜索；如果出现异常，暂时回退到 V2.0.2 原生界面，不删除用户数据或重复发起系统写入。

## 回滚边界

在线更新器会保留本地上一个引擎备份，但自动恢复能力受既有启动器实现限制。不要直接把清单版本号降到旧版，也不要为测试覆盖 `current_task.json`、`history/` 或 `appearance.json`。
