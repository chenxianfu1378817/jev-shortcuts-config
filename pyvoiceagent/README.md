# PYVoiceAgent — Pythonista iPhone AI 语音智能体

**当前正式发布版本：以 [manifest.json](manifest.json) 为准。**
固定入口依旧是 iCloud Drive / Pythonista 3 / **PYVoiceAgent.py**，不要更名。
启动器从 GitHub 自动检查并校验 agent_core_*.py；后续开发原则上直接在 GitHub 发布，无须反复下载 ZIP。

## V1.9.0 — 按统一 Python 开发规范改造的界面

- 以 **V1.8.5** 为基线升级，不删除旧工具：自动语音录制、静音收尾、语音追问、DeepSeek Flash、任务规划、提醒事项、通讯录、日历、备忘录、网页摘要、地图及已登记的快捷指令。
- 新增 Pythonista 原生 **统一卡片界面**：首页、文字输入、任务结果、工具搜索、设置、系统模块和高级故障排查一致设计；程序仍提供原文字菜单作为失败保护。
- 「外观与主题」：活力橙、科技蓝、翡翠绿、典雅紫、中国红、玫瑰粉、深海青、石墨黑；支持浅色、深色、跟随系统及自定义 #RRGGBB。颜色统一由主题管理，变更立即生效。
- 主题设定独立存放在 ~/Documents/PYVoiceAgent_Data/appearance.json，更新不会覆盖。默认活力橙，显示模式跟随系统。
- 原 PYVoiceAgent.py、PYAgentHub 和所有回调 URL 继续使用同一个地址；保留系统模块授权、安全核验、待处理任务、历史/用户数据及 Keychain。
- 更新文件和工具清单继续通过 pyvoiceagent/manifest.json 分发。提供独立的界面源码 ui_1_9_0.py 便于以后维护；正式更新包是打包好的 agent_core_1_9_0.py，手机无须安装额外 Python 模块。

## 手机更新流程

1. 直接使用你已有的桌面语音入口，或在 Pythonista 打开固定脚本 PYVoiceAgent.py。
2. 如果程序自动更新间隔未到，可在首页点 **「检查在线更新」**。检查通过后退出重新运行，让新版引擎生效。
3. 首次进入新首页，通过 **「设置与工具 → 外观与主题」** 选择颜色/显示模式。
4. 如果提示有待核验的跨 App 操作，先在苹果 App 中核对后再处理，不能为了更新直接删除任务状态。

## 安全与限制

- GitHub 仅发布程序、清单、测试和说明；**不上传 DeepSeek API Key、录音、联系人、真实任务或个人配置**。
- 下载后会检查版本、长度、SHA-256 与编译语法；本地保留历史引擎，失败时不自动重复系统写入。
- SHA 与程序清单同仓库，并非独立签名；保护依赖 GitHub 仓库权限和更新源安全。
- iOS 部分第三方功能仍需首次导入快捷指令或用户授权，不能以 Python 自动绕过系统限制。
- **真机需验收**：未在你的 iPhone 上实测新界面；离线代码/模拟测试不等于真机测试。

## 开发与回归

- 主题配置、八主题、三模式、工具筛选、页面布局和故障降级离线测试；
- [V1.9.0 回归测试](tests/test_release_v190.py) 和 [CI 工作流](https://github.com/chenxianfu1378817/jev-shortcuts-config/actions/workflows/pyvoiceagent-v190.yml)；
- [独立界面源码](ui_1_9_0.py)、[正式单文件引擎](agent_core_1_9_0.py)。

> 提醒：自动更新只会在主动打开/运行程序时执行；不保证锁屏后台持续检查。
