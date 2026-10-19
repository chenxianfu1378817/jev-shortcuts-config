# PYVoiceAgent V1.8.0｜一条 App 功能路由快捷指令

## 状态
- **发布**：`manifest.json` sequence=180，`agent_core_1_8_0.py`，SHA-256 已在 GitHub Actions 检查。
- **离线测试**：共 69 项通过，其中路由 8 项和此前快捷指令生成、日期提醒、工作意图的 61 项。CI: https://github.com/chenxianfu1378817/jev-shortcuts-config/actions/runs/39194965675
- **真机**：用户尚未在 iOS 27 完成逐项点击/跳转核验；所有第三方深链暂列**候选**，不要声称已可用。
- **用户安装包**：一个 `PYAgentAppRouter.unsigned.shortcut`，macOS 签名程序、Pythonista 启用程序、本机测试脚本；包已在 ChatGPT 会话提供。

## 为什么只有一条 Shortcut
这条指令名为 **PYAgentAppRouter**，做“接收文本 URL → URL → Open URLs”两个动作。具体 22 个功能的**固定、安全路由白名单在 PYVoiceAgent 的 Python 源码内**，不是让 AI 自由生成 URL；Python 使用 `urlencode` 对动态搜索词和外层快捷指令输入双重正确编码。单个功能不再生成一条独立快捷指令，不干扰已验收的 `PYAgentHub`、`PYAgentNotes`、`PYAgentCalendarRead` 等指令。

## 22 个候选入口
`app.navigate` 工具要求 `shortcut_id` 必须为以下之一。带“搜索/路线”的路线使用 `text` 传入关键词，其他功能必须留空：

| App | 语音例子 | ID | 证据 / 状态 |
|---|---|---|---|
| 微信 | 微信扫一扫 | `wechat_scan` | GitHub 社区；未实测 |
| 企业微信 | 打开企业微信文档 | `wxwork_docs` | GitHub 社区；未实测 |
| 企业微信 | 查看企业微信消息 | `wxwork_messages` | GitHub 社区；未实测 |
| 钉钉 | 打开钉钉待办 | `dingtalk_tasks` | GitHub 社区；未实测 |
| 钉钉 | 打开钉钉钉盘 | `dingtalk_drive` | GitHub 社区；未实测 |
| 百度地图 | 搜索南宁东站 | `baidu_search` | 百度官方地图调起规范；未实测 |
| 百度地图 | 查附近加油站 | `baidu_nearby` | 百度官方地图调起规范；未实测 |
| 百度地图 | 驾车路线到南宁东站 | `baidu_route` | 百度官方地图调起规范；未实测 |
| 高德地图 | 搜索南宁东站 | `amap_search` | 高德官方 HTTPS URI；未实测 |
| 抖音 | 搜索沥青视频 | `douyin_search` | GitHub 社区；未实测 |
| 抖音 | 查看抖音热榜 | `douyin_hot` | GitHub 社区；未实测 |
| 小红书 | 搜索 TLA 湖沥青 | `xhs_search` | GitHub 社区；未实测 |
| 小红书 | 打开小红书草稿箱 | `xhs_drafts` | GitHub 社区；未实测 |
| 淘宝 | 搜 SBS 改性剂 | `taobao_search` | GitHub 社区；未实测 |
| 淘宝 | 打开淘宝订单 | `taobao_orders` | GitHub 社区；未实测 |
| 美团 | 打开酒店搜索 | `meituan_hotels` | GitHub 社区；未实测 |
| 支付宝 | 打开扫一扫 | `alipay_scan` | GitHub 社区；未实测 |
| 支付宝 | 查看我的快递 | `alipay_express` | GitHub 社区；未实测 |
| 熊掌记 | 搜索项目笔记 | `bear_search` | Bear 官方 x-callback 文档；未实测 |
| QQ | 打开 QQ 扫一扫 | `qq_scan` | GitHub 社区；未实测 |
| 新浪财经 | 查看沥青主力行情页 | `sina_bu` | 固定公开 HTTPS 网页；非数据 API |
| 新浪财经 | 查看上海原油主力行情页 | `sina_sc` | 固定公开 HTTPS 网页；非数据 API |

## 安装
1. Mac 解压后运行 `Mac_双击签名并导入.command`；签名后导入 **PYAgentAppRouter** 一次。
2. 确保该快捷指令通过 iCloud 同步出现在 iPhone。
3. 在 iPhone Pythonista 运行 `Pythonista_启用与测试.py`，先测试微信扫一扫，再确认已安装并启用；本机写入 `~/Documents/PYVoiceAgent_Data/app_router_enabled.json`。
4. 在原 Pythonista 固定入口的更新菜单将引擎升级到 V1.8.0。无需更改原桌面按钮和回调 URL。
5. 语音说出对应目标。模型**只能**填路由 ID 与搜索词，不能指定自由 URL。

## 安全与边界
- 未启用时从 DeepSeek 的可用工具目录隐藏 `app.navigate`，不允许静默装载。
- 任意 URL、发消息、支付、转账、拨号、修改 VPN、下载执行程序等行为**不在允许名单内**。
- 多步计划必须最后调用路由；在 iOS 切换到 App 前先在本机持久化发起记录。
- **跳转没有回调**，不等于目标 App 已安装或目标页面已打开，更不能报告产生了文件、记录、订单或消息。
- 一旦用户发现某个第三方链接失效，需要删除/修复对应 route，而不是无条件退回危险的通用 URL 执行功能。
- 路由不获取微信、企业微信、银行或其他 App 的私人数据；它只是让 iOS 打开指定页面。

## 来源
- 百度地图官方：https://lbsyun.baidu.com/docs/webapi?title=mapadjustment%2Furi%2Fios
- 高德地图官方：https://developer.amap.com/api/uri-api/guide/search/search
- 熊掌记官方：https://bear.app/faq/x-callback-url-scheme-documentation/
- 社区公开深链：https://github.com/tofrankie/url-scheme-collection
- 另一社区列表：https://github.com/shelken/Url-Scheme

注：上游社区资料的发布/更新日期不能等同于 iOS 27 实测通过。
