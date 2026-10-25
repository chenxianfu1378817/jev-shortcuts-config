# Unified Personal Automation API (V1.0)

面向 iPhone「快捷指令」的统一云端判断与路由接口，源代码在 GitHub，运行于 Cloudflare Workers。

- Worker: **personal-shortcuts-api**
- API: https://personal-shortcuts-api.cxfoffice.workers.dev/api
- 时区：Asia/Shanghai（北京时间）
- 当前功能为**只读判断/路由**，不在云端执行 iOS 联系人、日历、微信等写入操作。
- **原有休息日判断 URL 不变：** https://cn-restday-shortcuts.cxfoffice.workers.dev/?format=plain

## 1. 接口列表

| 任务 | 方法 | URL | 返回 |
| --- | --- | --- | --- |
| 工作日判断 | GET | /api?task=workday | 工作日 \`1\`，其余空白 |
| 指定日期工作日判断 | GET | /api?task=workday&date=2026-10-10 | 工作日 \`1\`，其余空白 |
| 工作日调试 | GET | /api?task=workday&format=json | JSON：known、reason、shouldRun |
| 当前北京时间日期 | GET | /api?task=date | YYYY-MM-DD |
| 接口清单 | GET | /api?task=config | JSON |
| 在线状态 | GET | /api?task=health | JSON（仅证明本 Worker 可访问） |
| 任务路由 | POST | /api?task=route | JSON（仅决定目标功能，尚不执行） |
| 条件比较 | POST | /api?task=compare | 规则成立 \`1\`，不成立空白 |

上述接口也支持 \`/api/workday\`、\`/api/health\` 等路径风格。除 POST 任务外，直接从快捷指令「获取 URL 内容」调用 GET 即可。

**工作日数据处理：** 本项目的 WORKDAY_SERVICE 是 Cloudflare 内部服务绑定，指向已上线的 \`cn-restday-shortcuts\` Worker。既有服务继续负责国务院休假与补班规则、GitHub Actions 更新、云端 KV 缓存。新接口只调用它，不复制或自建第二份日历。如果上游不确定，返回空白，不会误认工作日。

## 2. iPhone 快捷指令：工作日才执行

1. 「URL」输入 \`https://personal-shortcuts-api.cxfoffice.workers.dev/api?task=workday\`
2. 「获取 URL 内容」设置 GET
3. 「如果」→ 获取 URL 内容 **等于 1** → 执行原来的任务
4. 「否则」→ 停止此快捷指令

手机里**已经使用旧工作日接口的快捷指令无须改动**。如果 URL 读取错误、超时、返回空白，都不应执行任务。

调试工作日：\`https://personal-shortcuts-api.cxfoffice.workers.dev/api?task=workday&date=2026-10-10&format=json\`。

## 3. 任务路由（V1 为本地关键词规则）

POST \`/api?task=route\`

JSON 请求：
~~~json
{"text":"查询明天的日程"}
~~~

JSON 响应示例：
~~~json
{
  "ok": true,
  "route": "calendar.list",
  "recognized": true,
  "engine": "local-rules-v1",
  "requiresReview": false,
  "executed": false,
  "input": "查询明天的日程"
}
~~~

现有 route ID：
- \`calendar.list\`、\`calendar.create\`
- \`todo.create\`
- \`notes.create\`
- \`contacts.search\`、\`contacts.create_from_text\`
- \`maps.open\`、\`clipboard.process\`、\`wechat.scan\`
- 不可识别：\`manual.review\`

返回的 route 是**建议交给哪个快捷指令动作处理**，不是已经执行。V1 不调用 DeepSeek、Pythonista，也不写入个人账户或 iPhone。通讯录录入标记 \`requiresReview:true\`，防止解析错误直接写入。

若需要只返回路由文本，使用 \`/api?task=route&format=plain\`（仍需 POST），不可识别时返回空白。

## 4. 条件比较（用于价格或其他数值触发）

POST \`/api?task=compare\`

请求：
~~~json
{"value":4510,"threshold":4500,"operator":"gte"}
~~~

响应正文：\`1\`（满足条件）；不满足为空白。

支持 \`gt\` 大于、\`gte\` 大于等于、\`lt\` 小于、\`lte\` 小于等于、\`eq\` 等于、\`ne\` 不等于。必须由调用方提供数字：**接口不自动获取市场价格**。调试可加 \`format=json\`。

## 5. 安全边界和部署

- 这是公开 HTTP 接口，**不要发送敏感个人数据、API Key、银行信息或完整客户名片**。未来写入日历、通讯录等操作必须使用鉴权，不应直接开放给匿名互联网用户。
- 不会绕过 iOS 系统权限。客户端快捷指令仍负责 iOS 原生操作和许可。
- 目前从已连接账户通过 Cloudflare API 部署，**修改 GitHub 代码不会自动部署**。后续可以加入正式 CI/CD（需要合适的 Cloudflare 令牌/授权）。
- Cloudflare 内部服务绑定：
  - 类型 \`service\`
  - 变量名称 \`WORKDAY_SERVICE\`
  - 目标 Worker \`cn-restday-shortcuts\`
- Worker JavaScript 源码：\`worker.js\`。
- 当前部署已经确认成功，已启用 \`workers.dev\` 子域名及绑定。业务逻辑进行了模拟请求测试；当前执行环境无法从公网 DNS 直接访问 workers.dev，因此**尚未完成真实手机端请求验证**。

## 6. 扩展约定

未来增加一个功能时，在同一个 Worker 中增加可验证的任务类型，不建议为每个判断都建一个新网站。

- 简单任务返回 \`1\` 或空白，并且在失败时默认空白
- 复杂任务返回 JSON，如 \`route\`、\`parameters\`、\`requiresReview\`
- 实际设备动作在 iOS 快捷指令或 Pythonista 完成
- 涉及账户写操作要先设计鉴权、审计和重放保护
