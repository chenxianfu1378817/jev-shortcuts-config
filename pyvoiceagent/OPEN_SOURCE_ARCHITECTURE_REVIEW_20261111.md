# PYVoiceAgent｜开源架构借鉴与持续稳定性优化（2026-11-11）

> 基线：main 正式 manifest **V2.3.4**；V2.3.5 回调异常修复当时仍是草稿 PR #17。版本事实以后以远程 manifest 为准。
> 此文档和同分支的测试/CI **不改变 iPhone 运行引擎**，不得称作真机修复。

## 阅读的开源项目与选择

| 项目 | 适合借鉴 | 为什么暂不直接移植 |
| --- | --- | --- |
| [mikaelho/pythonista-webview](https://github.com/mikaelho/pythonista-webview) | WKWebView 的 JS `messageHandlers` 及异步 `eval_js_async`，比自定义 URL 导航回调更容易做可靠的双向通信与异常回执 | 最近提交在 2020 年；通过 objc_util 操作 WKWebView 的实现需在 **iOS 27 / Pythonista 3.4** 真机验证。不可在崩溃原因尚未闭环时替换稳定界面容器 |
| [mikaelho/ui3](https://github.com/mikaelho/ui3) | iOS 安全区域、弹窗与布局分层；对原生表单和全屏聊天切换有参考价值 | 最近提交在 2021 年，兼容性与现有 Pythonista 模态生命周期需先验证 |
| [shafaypro/PYSHA](https://github.com/shafaypro/PYSHA) | 工具注册、状态追踪、语音/LLM 插件隔离、单元测试和发布 CI | Python 3.11+/FastAPI/桌面或服务器依赖不能直接作为 Pythonista 本地引擎 |
| [zahanzo/lia-framework](https://github.com/zahanzo/lia-framework) | 动态工具清单、明确的工具描述及 AI 调用白名单 | 桌面 MCP 工具可执行任意 Python，不适合照搬为可自动写入 iOS 用户数据的手机插件 |
| [alexander-akhmetov/python-shortcuts](https://github.com/alexander-akhmetov/python-shortcuts) | 快捷指令动作与参数模型设计 | 项目已归档；不能绕过苹果签名和用户授权 |

## 当前版本的实施决定

1. **保留 V2.3.2–V2.3.4 的原生快捷指令工具库**；不回滚到旧版网页表单，不强制替换 `ui.WebView` 为未经验证的第三方 WKWebView。
2. **先稳定再重构**：以 PR #17 的主线程回调异常/脱敏阶段日志与真机 .ips 复验为前置，再评估是否将 WebView 通信换为 WK message handler。若迁移，必须保持 JS 消息白名单、一次性 nonce、完成/失败回执、幂等去重，且提供原有桥接回退。
3. **工具能力模块化但不破坏固定入口**：把注册数据结构、参数校验、权限确认、执行请求和回调状态分别作为可单测的服务边界；发布仍可打包成旧更新器可安装的单文件，避免在手机上补装多个模块。
4. **数据保护优先**：不把含未完成/待回调的 `current_task.json` 覆盖；保留失效或未来格式的快捷指令记录；写入失败不误报成功；不将 API Key、用户文本或录音加入调试日志。
5. **建立始终跟随正式 manifest 的 CI**：随新版本自动检查源码长度 ≤350000 字节、SHA-256、源文件版本、Python 语法、直接路径和重复清单键；对当前引擎执行原始注册表保留、异常数据保护和待回调写保护测试。避免只测试固定版本号的历史引擎。

## 本次已实现的低风险优化

- `tests/test_active_release_contract.py`：9 项发布清单与引擎一致性测试（含合成故障样本）。
- `tests/test_active_registry_contract.py`：7 项当前引擎注册表安全测试，不涉及真机系统写入或外部快捷指令执行。
- `.github/workflows/pyvoiceagent-active-release.yml`：push / PR / 手动执行时检查**当前已发布引擎**，不依赖某个旧版本文件名。
- **手机正式版本保持不变**。以上测试是发布门禁辅助，不是原生录音和 WKWebView 的真机验收。

## 下一阶段优先级

P0：等待 V2.3.5 回调修复的真实 iPhone 复验，确认“点击编辑/登记/退出”和“开始/停止/取消录音”是否仍导致 Pythonista 进程退出，并取得最后本机诊断阶段或脱敏 .ips 堆栈。

P1：在 iPhone 完成无副作用的注册、编辑、停用、重开、传参、回传测试；录音与快捷指令工具库分开逐项验收。

P2：经过确认后，再建立受控的 UI↔Python 消息队列（事件 ID、幂等键、处理回执、超时、不重复系统写入）以及独立工具服务模块；不要在没有真机回滚方案时直接替换 WebView 技术栈。

> **避免误用**：自动化测试通过不等于 iOS 真机稳定。此文件不包含真实 API Key、日志原文、联系人或个人数据。
