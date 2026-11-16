# 浏览器工具适配参考（其他 agent 用）

> **这是一份参考笔记，不是保证可用的适配层。** 下表"本 Skill"一列来自本机实测；其余列凭公开文档整理，**未验证**，工具名也会随版本变化——最终以目标环境 `tools/list` 实际返回为准。
> 适配的判定标准与降级方案见 `toolchain.md` §1；本文件只解决"名字对不上"。

## 0. 三步移植，别照抄名字

1. **先看手上有什么**：让 agent 打印自己的浏览器工具清单，或查它的 MCP server 配置。
2. **按 §1 对号入座**：7 个动作逐个找，找到记下名字；找不到看 §3 怎么退化。
3. **改 SOP 里依赖它的步骤**：缺哪项，就把 `platforms-*.md` 中对应步骤改成"提示用户手动完成"。

## 1. 七个动作的映射

| # | 动作 | 本 Skill（WorkBuddy，实测） | Playwright 类 MCP（参考） | DevTools 协议类 MCP（参考） |
|---|---|---|---|---|
| 1 | 列出浏览器 / 确认是否带登录态 | `browsers_list`、`browser_info` | 无等价概念：启动即是独立实例 | `list_pages` |
| 2 | 取用户已有标签 | `user_open_tabs` | 无（看不到用户手开的页） | `list_pages` |
| 3 | 新建 / 切换 / 关闭标签 | `tabs_new`、`tab_focus`、`tabs_close` | `browser_tabs`（list/new/select/close） | `new_page`、`select_page`、`close_page` |
| 4 | 读页面结构 | `dom_cua_get_visible_dom` | `browser_snapshot`（可访问性树） | `take_snapshot` |
| 5 | 点击 / 输入 / 滚动 | `cua_click`、`dom_cua_click`、`dom_cua_type`、`cua_scroll` | `browser_click`、`browser_type` | `click`、`fill`、`hover` |
| 6 | 截图 | `tab_screenshot` | `browser_take_screenshot` | `take_screenshot` |
| 7 | 导航 / 取 URL 与标题 | `tab_goto`、`tab_reload`、`tab_url`、`tab_title` | `browser_navigate`、`browser_navigate_back` | `navigate_page` |

**执行代码也算一条路**：如果 agent 能跑命令、只是没装浏览器 MCP，直接用 Playwright / Selenium 写脚本反而更可控（可 `saveAs` 到指定路径、可等待下载完成）。

## 2. 比名字更重要的语义差异

- **"借用登录态"多数方案做不到**。这里靠浏览器扩展接管你已登录的会话；Playwright 类启动的是干净实例，要用得自己登录一个持久化 profile，或导出 `storageState` 传入。缺这一条，知网/万方/ScienceDirect 的登录态场景基本回到手工。
- **"取用户已有标签"缺失反而少一类风险**：§1 第 8 条（不动用户原有页面）自动满足，因为根本没有"用户原有页面"；但也意味着收尾清场那套基线比对不再适用，`tab_session.py` 可以不用。
- **下载机制不同**。这里靠点击触发浏览器真实下载、脚本再去下载目录收件；能直接指定保存路径的方案，第 5 步之后可以跳过 `litadopt.py` 的"基线 → 扫描新增"流程，改为直接校验目标文件。
- **截图不一定是必须的**。它在本 Skill 里是为了双验（SPA 场景 URL 不可信）。若目标方案能稳定拿到 DOM 文本与状态码，可用文本断言替代，但要相应降低对"成功"的判定口径。

## 3. 缺能力时的降级

| 缺失 | 降级做法 | 影响 |
|---|---|---|
| 无浏览器工具 | 只走 L1 / L1.5 / L2；拿不到全文时用 `oa_fetch.py checklist` 生成可点击清单交用户手动另存 | 覆盖率降到 L2 命中率（实测约 1/3） |
| 有浏览器但无登录态 | 让用户自己在该浏览器登录一次，再继续同一会话；或退回手工下载 | 中文订阅库基本手工 |
| 无 DOM 读取，只有截图 | 只能"看图操作"，定位不准、易错点；建议放弃自动化，转人工 | 不建议 |
| 无截图 | 用 DOM 文本 + HTTP 状态码判定，但要放宽口径并如实标注"未截图核验" | 判断可靠性下降 |
| 无标签管理 | 只有一个页面时可行，多篇需串行重开；务必确认不会覆盖用户当前浏览 | 多篇任务效率低 |

## 4. 移植后先验这四条

别急着跑全流程，先用一个无害页面（如 `example.com`）确认：

1. 能列出/启动浏览器，并说清**是否带登录态**；
2. 能从页面取到一段已知文本；
3. 能截图，且图里内容与你看到的一致；
4. 能关闭自己开的页面，且用户原有的页面**没有**被动过。

四条都过，再去跑真正的平台 SOP；任何一条不过，按 §3 降级，别硬试。
