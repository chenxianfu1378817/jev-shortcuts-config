# 中国大陆休息日判断接口 V2：每年自动更新

iPhone 快捷指令查询中国大陆国务院公布的节假日、调休补班安排；接口网址和返回协议与 V1 完全兼容。

## 接口地址

纯文本（快捷指令）：
https://cn-restday-shortcuts.cxfoffice.workers.dev/?format=plain

详细 JSON：
https://cn-restday-shortcuts.cxfoffice.workers.dev/

指定日期：
https://cn-restday-shortcuts.cxfoffice.workers.dev/?date=2026-10-10&format=plain

查询年份数据是否准备好：
https://cn-restday-shortcuts.cxfoffice.workers.dev/status?year=2027

日期缺省按照北京时间（Asia/Shanghai）判断。

| 返回 | 含义 | 推荐行为 |
| --- | --- | --- |
| 0 | 工作日，包括周末调休补班 | 执行 |
| 1 | 周末或官方节假日 | 停止 |
| UNKNOWN / HTTP 422 | 年度官方数据不完整、未公布或验证失败 | 停止 |

**快捷指令只在严格等于 0 时执行，其他情况都安全停止。**

## 自动更新机制

- **GitHub Actions 每天北京时间 08:37 检查一次，包含每年12月31日**；如果数据尚未发布，次日自动重试。
- 每年9–12月自动抓取**下一年**的国务院节假日数据，1月补查上一年可能出现的跨年调整。
- 数据来自 [NateScarlet/holiday-cn](https://github.com/NateScarlet/holiday-cn)，其自动采集国务院公告并保存政府原文链接。只有含有效 .gov.cn 公告、完整日期及补班信息的年表才会接受；空白占位文件不接受。
- 校验成功后写入本仓库的 rest-day-api/data/YYYY.json。Cloudflare Worker 通过这一持久化副本及上游备用来源读取数据。
- Worker 使用 Cloudflare KV 缓存已核验的年表，并在客户端查询时每24小时尝试重新校验，以接收后续公告变动。
- GitHub Actions 每月更新 rest-day-api/data/heartbeat.json 以减少公共仓库因60天无活动而停用工作流的可能。
- GitHub 定时任务可能延迟、因仓库设置暂停或因服务故障失败。校验失败不把下一年误判为正常工作日，返回 UNKNOWN，避免误执行。

Cloudflare 免费套餐的 Cron 触发器名额已满，所以**实际定时任务由 GitHub Actions 执行**，未新增 Cloudflare Cron 配额用量。Worker 的 scheduled 处理器已预留，将来可以启用。

## 快捷指令步骤

1. 「URL」：粘贴上述纯文本接口地址。
2. 「获取 URL 内容」：GET。
3. 「如果 URL 内容 等于 0」，执行你原有的任务；「否则」停止此快捷指令。

不能用「不等于1就执行」——UNKNOWN 不应该执行。

## 官方来源与年度限制

2026 年已根据[国务院办公厅关于2026年部分节假日安排的通知](https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm)核验（包括1/4、2/14、2/28、5/9、9/20、10/10的补班）。

截至2026-10-25，上游2027年文件仍为空，尚不能判断2027年官方调休；等公告发布且数据更新、通过核验后，自动启用。

## 代码位置

- rest-day-api/worker.js：接口、缓存、数据校验
- rest-day-api/sync.py：Python 标准库自动数据同步脚本
- rest-day-api/data/YYYY.json：已核验的数据
- .github/workflows/cn-restday-sync.yml：真正运行的自动更新工作流

查看 Actions 运行记录：https://github.com/chenxianfu1378817/jev-shortcuts-config/actions/workflows/cn-restday-sync.yml
