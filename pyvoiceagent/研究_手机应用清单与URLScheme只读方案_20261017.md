# PYVoiceAgent｜iOS 27 本机安装 App / URL Scheme 只读盘点（2026-10-17）

## 研究结论

在未经越狱的 iOS 27 上，Pythonista 自身通过 `LSApplicationWorkspace.allApplications()` 未得到任何结果（用户真机为 0），**不能**由此推断未安装 App，也不应继续使用同一接口反复尝试。

对比三项实现：

1. **Antrag**：<https://github.com/claration/antrag>。Swift + IDeviceSwift；通过设备配对、loopback VPN、`installation_proxy_get_apps` 查 App，主要返回名称/Bundle ID；项目已归档。关键参考 `Antrag/Views/ATAppsViewController.swift`。
2. **EscapeOS**：<https://github.com/pwnapplehat/EscapeOS>。同样用配对文件 + LocalDevVPN + installation_proxy，源码 `EscapeOS/Engine/AppDiscovery.swift`、`EscapeOS/Tunnel/applist.m`。其中 `getAllAppsInfo` 获取原始字典；但程序还包含跨 App 数据容器修改与删除，**不宜直接搬进本项目**。README 的真机验证是 iOS 26.5.1；iOS 27 后续版本不应推定兼容。
3. **StikDebug27**：<https://github.com/Xarber/StikDebug27>，公开源码 `StikDebug/Features/InstalledApps/InstalledAppsViewModel.swift`。代码调用 `JITEnableContext.shared.getAppList()`、`getAllApps()`、`getHiddenSystemApps()`；可借鉴其更新的设备通信实现。README 标记 iOS 26+ 支持，但仅能看到部分 App；iOS 27 有配对/隧道故障案例，不能宣称已适配用户真机。该项目本身包含 JIT、进程控制等多余能力，**不直接使用现有全功能包作为诊断工具**。

底层 `idevice` 提供纯查询的 `InstallationProxyClient.get_apps` 与 `browse`：
<https://idevice.wiki/docs/service-reference/files-apps/installation-proxy/>。
`Browse` 可以获取设备返回的原始 App 字典，不保证一定包含 `CFBundleURLTypes`。后者是 Apple Info.plist 中声明 Scheme 的字段（<https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleurltypes>），而 **Scheme 存在不证明某一 URL path 有效，也不证明支持 x-callback-url**。

## 设计边界（绝对不要扩展）

- **单独的小工具**，不得修改、覆盖 PYVoiceAgent.py 或 `agent_core_1_7_8.py`，不得动五项首页、快捷指令、日历或提醒事项。
- 只建立 `installation_proxy` 查询会话（如实际可用）；不开放安装、卸载、启动 App、JIT、容器访问、文件写入或设备管理接口。
- 不抓取私有 App 数据、设备标识、签名凭据、账号、消息内容。
- 设备配对文件是敏感认证材料，**只留在本机，不上传 GitHub / ChatGPT / 第三方服务器，不写入日志**。
- 本地 JSON 只保存用户可理解的 `name`、`bundle_id`、`app_type`、`version`、可选 `declared_schemes`、`source`、`confidence`；自动脱敏并剔除 app Container / Path / UUID / Entitlements。
- 禁止在没有用户单独点击确认时执行任何 Scheme URL；枚举与行为测试是两个阶段。

## 真机验证关卡

### P0：验证 iOS 27 配对及只读通信是否可用

- 一次性配对、手机 Wi-Fi、LocalDevVPN；注意需要暂时停用可能占用同一 VPN 接口的网络代理。
- 首先验证只读 `installation_proxy` 是否能建立连接；失败则记录错误类型（配对过期、VPN/网络连接、端口不通、协议不支持），**立即停止**，不反复尝试私有 API。
- 有 App 数据才进入 P1。**未返回不等于未安装。**

### P1：导出应用名称与 Bundle ID

- 区分用户/系统 App；可选仅导出用户 App。
- 记录本次可见数量、服务响应状态和遗漏风险。
- 在手机 Files 中导出 CSV / JSON，不自动上传。

### P2：调查 URL Scheme

- 对每个 Bundle ID 尝试从只读返回字典寻找 `CFBundleURLTypes[].CFBundleURLSchemes`。
- 若不存在该字段，标注 `not_provided`，**不是** `no_scheme`。
- 再结合应用的官方文档 / GitHub Scheme 数据库查找已公开 Scheme，并注明版本、出处和是否仍可用。
- `x-callback-url` 需有供应商文档或用户明确授权的成功回调测试才标记为 supported。

### P3：PYVoiceAgent 使用接口资料

- 输出 `app-capabilities.json` 能力表供 AI 规划**参考**；不因为存在 Scheme 就自动调起 App。
- 单个动作需要白名单、用户动作或授权、必要参数、失败后不得误报已完成。

## 当前状态

源代码与官方服务文档已核实；**尚未在用户 iOS 27 上完成配对、安装列表读回或 Scheme 取证**。不得声称本方案已在手机上成功。

## 参考来源

- Antrag: https://github.com/claration/antrag
- EscapeOS: https://github.com/pwnapplehat/EscapeOS
- StikDebug27: https://github.com/Xarber/StikDebug27
- idevice / installation_proxy: https://idevice.wiki/docs/service-reference/files-apps/installation-proxy/
- Apple CFBundleURLTypes: https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleurltypes
- iOS 27 连接问题实例：https://github.com/StikDebug/StikDebug/issues/469
