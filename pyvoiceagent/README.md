# PYVoiceAgent V1.4｜以后无需每次下载和改参数

## 这版的核心变化

- **固定入口不变**：iPhone 的 Pythonista 3 `iCloud/PYVoiceAgent.py` 始终是桌面语音按钮和 `PYAgentHub` 的唯一回调入口。以后只需要维护远程版本，不要求你重新下载脚本。
- **自动更新**：每隔约 6 小时（仅当你主动打开或运行程序时）检查 GitHub 发布仓库；有比 V1.4 更新的版本才下载并执行。不是锁屏后台持续检查。
- **自动检验**：HTTPS 下载 + SHA-256、文件长度、语法检查。校验失败继续使用已有版本；不会清空本地任务。
- **回退**：新版本运行异常会标记为不可继续使用，下次运行自动使用上一版或内置 V1.4。为防止重复执行手机写入，异常当次不自动重跑。
- **数据与密钥不迁移**：DeepSeek API Key 仍在 Pythonista Keychain；历史任务、注册工具、提醒等存放在原来的 `~/Documents/PYVoiceAgent_Data`。
- **动态工具目录**：模型看到当前已授权的本地工具信息，无须每一个任务重复填写参数。全新 iOS 受限系统动作仍需要先配置对应的 App Intents/快捷指令动作，无法绕过 iOS 权限。

## 只需这最后一次替换

1. 把旧 `PYVoiceAgent.py` 备份到手机其他目录（建议文件名 `PYVoiceAgent_V13_Backup.py`）。
2. 从本安装包复制**新版同名** `PYVoiceAgent.py` 到 `iCloud Drive/Pythonista 3/` 根目录并覆盖旧版。
3. 打开 Pythonista 运行，同一菜单下会显示 `V1.4`。第 `16` 项是查看和立即检查更新。
4. **无需修改**桌面按钮、现有 `PYAgentHub` 的 URL、`PYBridgeEcho`、DeepSeek Key、已登记的工具信息。
5. 后续在 ChatGPT 里让我更新这个程序时，我会更新下方发布仓库版本及 manifest；你只需下一次打开桌面语音按钮，程序就会自动拉取更新，无需手动添加文件。

## 更新来源

- 发布仓库：`https://github.com/chenxianfu1378817/jev-shortcuts-config/tree/main/pyvoiceagent`
- 自动更新清单：`https://raw.githubusercontent.com/chenxianfu1378817/jev-shortcuts-config/main/pyvoiceagent/manifest.json`
- 发布仓库里**只放公开的程序代码和哈希清单**，不存 API 密钥、私人录音、笔记内容或真实任务数据。

## 首版能力仍保留

语音输入、听写纠错、DeepSeek Flash 逐步规划、剪贴板读取、Pythonista 本地笔记、提醒事项创建和核验、苹果备忘录和日历的 `PYAgentHub` 入口、快捷指令工具白名单、失败暂停、人工核验、防重复与任务记录。

### 限制（请注意）

1. `PYAgentHub` 第 13～15 项测试仍要在 iPhone 上真机验证；此版不声称未经验证的手机写入已经成功。
2. **更新源要可信**。SHA-256 对比由同一个公开 GitHub 仓库提供的清单，不构成独立的加密签名。仓库被恶意篡改时，这种方式不能保证安全。建议只允许仓库所有者写入，不公开凭证。新版执行前不会再次弹窗确认代码更新；如果不接受自动更新的安全权衡，可在启动器中关闭自动更新逻辑。
3. 如果 GitHub 在当前网络不可达，内置版本会继续工作，但**收不到**更新。切换到可以连接 GitHub 的网络后再运行第 16 项检查。
4. 新增 Pythonista 本地能力/联网接口可通过代码更新自动扩展；新增 iOS 不提供的系统动作或需要新权限的第三方 App 仍需一次性配置，AI 不会擅自操作。
5. 处于跨 App 待核验操作时暂停更新，不允许切换版本掩盖执行结果。
6. 如果新版本在运行中异常，当次不自动回放以避免重复创建提醒、备忘或日历。