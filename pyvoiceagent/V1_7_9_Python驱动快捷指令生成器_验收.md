# PYVoiceAgent V1.7.9：Python 自动生成苹果快捷指令

## 目标

不再让用户在 iPhone 上手动把十几个动作一个个拼起来。保留已有 `PYVoiceAgent.py` 固定入口、五项首页，以及 PYAgentNotes、PYAgentCalendar、PYAgentCalendarRead、PYAgentHub；**独立加入一条“生成快捷指令文件”的本地路径**，不影响正常语音任务和提醒事项。

### 第一版支持的自然语言（无需调用 DeepSeek）

| 语音 / 文字指令 | 输出快捷指令 | 动作 |
|---|---|---|
| `创建快捷指令：显示传入内容` | `PYGen_ShowInput` | 显示 Pythonista 传来的文本 |
| `创建快捷指令：显示 欢迎使用` | `PYGen_Text_<摘要>` | 显示指定固定文字 |
| `创建快捷指令：打开百度地图` | `PYGen_Web_<摘要>` | 打开百度地图网站（不是调用其未验证的 App Intent） |
| `创建快捷指令：打开网页 https://example.com` | `PYGen_Web_<摘要>` | 打开指定的公开 HTTPS 网页 |
| `创建快捷指令：用苹果地图搜索输入地点` | `PYGen_AppleMapSearch` | 接收位置文本 → URL 编码 → 打开苹果地图搜索链接 |

模板基于 GitHub 的 [shortcutkit](https://github.com/frontboat/shortcutkit) 提供的动作 ID、plist 格式和 UTF-16 token 引用编码实现；无需在 Pythonista 中 `pip install`。动作采用固定白名单，不执行 AI 自创的 Python、第三方 App Intent ID 或任意 shell。

## 语音操作流程

1. 在 Pythonista 固定首页选语音或文字，直接说 **创建快捷指令：显示传入内容**。
2. Pythonista 本地生成二进制、**未签名**的 `.unsigned.shortcut`，另存仅本机的 metadata JSON（`installed:false`）。
3. 如弹出分享面板，选择发送到 Mac（AirDrop、iCloud Drive 等）；也可以在 Pythonista 的 `Documents/PYVoiceAgent_Data/GeneratedShortcuts` 查找文件。
4. Mac 下载仓库中的 `Mac_快捷指令签名并导入.command`，双击后从文件选择器选取 `.unsigned.shortcut`，使用系统 `shortcuts sign --mode anyone` 自动签名并打开 Shortcuts 导入对话框。
5. **用户在 Mac 确认“添加快捷指令”**，确保 Mac 和 iPhone 已登录相同 Apple 账户并开启 iCloud 快捷指令同步。后续 Pythonista 可以执行这个已导入的快捷指令。
6. 示例（仅完成导入后）：
   ```python
   import shortcuts
   shortcuts.open_shortcuts_app("PYGen_ShowInput", shortcut_input="测试 Pythonista → 快捷指令")
   ```

Mac 使用系统自带的 `shortcuts sign`，不调用第三方在线签名接口。创建本地文件 ≠ 已签名、已导入或已执行。iCloud 同步也可能存在延迟。

## 防重和安全

- 同样模板、参数采用确定性 UUID，因此**重复语音产生字节完全相同的工作流**；已有同内容文件直接复用，不覆盖。
- 已有相同文件名但内容不同则报错停止；不擅自修改已有签名或已安装快捷指令。
- URL 仅允许公开 HTTPS 域名；禁止内网、IP 字面量、携带用户名密码和自定义端口。
- 不提供转账、支付、消息发送、删除数据、越权读取、后台操作第三方 App 等模板。
- 第三方 App Intents 参数未有真机确认前不自动生成；百度地图仅打开公开网站，苹果地图搜索使用 Apple Maps 网页 URL。
- Mac 签名只处理用户手动选择的文件，并打开系统导入确认界面，**不会后台静默安装**。
- 不改变现有执行器的原有工具白名单或防重复记录。
- **已有快捷指令仍能继续使用，生成器不是其替代品。**

## 测试阶段

- GitHub Actions 离线回归：Python 3.11 解析；二进制 plist 读回；UTF-16 token 偏移；变量引用；危险 URL 拒绝；幂等文件生成；生成后不虚报安装；保留旧首页、日历和提醒事项行为。
- **未完成的真机验收**：苹果 iOS 27 从 Mac 签名后的导入、Pythonista `shortcuts.open_shortcuts_app` 输入传递、苹果地图搜索实际动作结果。必须用户真机验证后才能标为可用。
- 如在 iPhone 上导入显示为空或某动作“不可用”，把快捷指令编辑画面发回来再校正序列化，不要改变主执行器已有模块。

## 后续扩展

下一阶段研究 `shortcutkit` 的 App Intents 数据字典，增加经过实际参数测试的第三方模板（百度地图、百度网盘、企业微信等）；**不能**只凭 App 名称或 URL Scheme 就推断动作可用。先在测试快捷指令里验收，再进入 PYVoiceAgent 主工具库。
