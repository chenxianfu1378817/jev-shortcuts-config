# PYVoiceAgent V1.5.1 — 节省 DeepSeek Token 的一次性规划版

**状态：** 原固定入口自动更新的手机验收版。GitHub Actions 对最终源文件执行 62 项离线测试和语法检查并通过；真实 DeepSeek 回复及 iOS 完整联动仍需手机验收。

## 用户日常操作

- 原来的 `iCloud/PYVoiceAgent.py` 固定入口、DeepSeek Key、`PYAgentNotes`、`PYAgentCalendar` 和 `PYAgentHub` **保持不变**。
- 菜单 1、2、3（语音、手动输入、粘贴任务）默认一次调用 DeepSeek，得到最多 5 项完整可执行计划。
- 用户确认一次计划后，Pythonista 逐项操作提醒、本地笔记，或自动启动已验收的苹果备忘录、日历快捷指令。收到成功回调继续执行后面的动作，不再调用 DeepSeek。最后由本地代码生成真实执行结果摘要。
- 执行报告/菜单 5 显示 DeepSeek API 返回的实际输入、输出、总 Token，以及 API 提供时的缓存命中 Token；**不根据字符数猜测计费**。
- 新增菜单 18「复杂任务逐步 AI 模式（更多 Token）」，需要分析剪贴板、读写之间有依赖、或其他不支持一次规划的任务时，由用户主动选择旧的多轮规划方式；菜单 19 退出。
- 如果任务要求的日期不明确、缺结束时间、不支持或者涉及步骤依赖，新模式会请求补充，不执行不完整的计划，以防错误写入。

## 为什么减少 Token

旧版两项操作通常调用 DeepSeek 三次：第一次规划、第二次规划、第三次 task.finish；每次还发送整段提示词和执行历史。
新版可独立执行的简单操作统一为 **一次 DeepSeek 请求**，使用精简系统说明和已授权工具清单，不传历史执行日志。最终完成状态由 Pythonista 本地汇报，不调用 AI。
这减少的是调用次数和请求上下文，**实际 Token 由 DeepSeek 的 usage 返回值决定，不保证每个任务固定消耗量**。

## 第一次真机验收

1. 主动运行原来的 `PYVoiceAgent.py`，确认标题显示 V1.5.1。固定入口每约 6 小时检查更新，也可按原安全流程重置 `update_meta.json` 的 `last_checked` 后重新运行；不要打开缓存目录下的 `engine/current.py`。
2. 确认第 10 项已登记的 PYAgentNotes/PYAgentCalendar 仍显示“已验收启用”；首次登记数据继承 V1.5.0。
3. 菜单第 2 项输入一次测试：“在苹果备忘录创建标题为‘一次规划Token验收1017’的备忘录，正文是‘测试V1.5.1一次AI规划及真实Token统计’。只创建一次，按实际结果汇报。”
4. 核实苹果备忘录是否出现准确正文；随后在 Pythonista 菜单第 5 项查看“DeepSeek 1 次；输入…Token；输出…Token；总计…Token”以及实际工具结果。
5. 如果出现错误，请保留截图，不要重试同一个写入目标，防止重复创建。

## 不变的安全规则

- 仅已启用的系统模块可以操作；写入风险不确定时阻止自动重试。
- 真机可弹出系统授权框；用户已经明确请求写入时，在 AI 操作计划层确认一次，不再为每个动作重复弹框。
- 仅允许一次性规划的四类工具：`apple_notes.create`、`calendar.create`、`reminder.create`、`local_note.save`。其他复杂操作请用菜单 18。
- 之前的 V1.5.0 引擎仍保留在 GitHub 中；永久入口的回滚保护保持原状。

## 验证和文件

- 完整核心：`pyvoiceagent/agent_core_1_5_1.py`
- 更新清单：`pyvoiceagent/manifest.json`（sequence 151）
- GitHub Actions：`https://github.com/chenxianfu1378817/jev-shortcuts-config/actions/runs/39015276178`
- V1.5.1 开发分支：`dev/pyvoiceagent-v1-5-1`
