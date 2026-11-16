# CNKI 知网 SOP（A 级 · 本机实测）

唯一有完整步骤级实测支撑的平台。其他平台不得套用这里的按钮文案。

**开工前先花 5 秒**：知道 DOI 的话先跑 `oa_fetch.py resolve --doi <DOI>`。多数中文期刊没有 OA 副本，但若命中就省掉整条浏览器链路；查无也不亏（一次请求）。

## 依据

【实】2026-11-12 本机实测：Edge 扩展登录态、4 篇文献真实下载、登录墙、`title` 状态变化、文件格式陷阱。
【联】CNKI 官方 FAQ（学位论文全文只提供 CAJ）、使用手册（专业检索字段）。

## 入口与登录态

| 项 | 值 |
|---|---|
| home | `https://www.cnki.net/` |
| 检索 | `https://kns.cnki.net/kns8s/search`；一框式结果页 `kns.cnki.net/kns8s/defaultresult/index?...&kw=<URL编码检索词>` |
| 学位论文 | 首页选「学位论文」子库；海外版 `oversea.cnki.net` 提供 PDF 整本（【联】，未实测） |
| 机构登录 | CARSI `fsso.cnki.net`；本机页面右上角显示机构名 |
| 登录有效 | 结果页下载链接 `title="下载"` |
| 登录失效 | 下载链接 `title="未登录"` → 点击跳 `login.cnki.net` |

**不要代用户登录**。登录页有「IP 登录」按钮，本机两次点击（DOM 点击 + 坐标点击）均**无响应**；用户手动登录后刷新页面，链接状态即恢复。失效时停机交人工。

## 页面操作 SOP

```
S1 browsers_list → browser_info → user_open_tabs → tabs_claim（必须 type=extension）
S2 tab_goto 到检索页 / 或复用已打开的结果页
S3 dom_cua_get_visible_dom → 找一框式 input[type=text]（placeholder 含「若检索词含*、+、-等特殊符号」）
     搜索框左侧有「主题 ▼」字段下拉，截图可见但 DOM 快照不返回 → 需截图或坐标判断
S4 【按序容错，三轮实测】
     1) cua_execute 真实坐标：click 输入框 → ctrl+a → type 检索词 → Enter
        ★ run-cn-1（2026-11-13）：一次即写入，读回 value 与输入一致，Enter 提交成功
        ★ run-1：重试后生效；run-2：两次均未写入（value 空、整页被 ctrl+a 全选 = click 未聚焦）
        → 说明这是**时序抖动**，不是稳定失败；第 1 级仍是首选，但"读回 value"是硬约束
     2) 每次提交前必须读回 input.value 或截图确认检索词已写入；value 为空就别按 Enter
     3) 未写入 → 分步真实 CUA 事件（cua_click 聚焦 + cua_type 输入），再读回 value
     4) 仍失败 → 按 selftest.md §2.1 用 tab_goto 直达结果页，
        标注 URL 是「页面实测 href」还是「按 SOP 模式+参数构造」（构造类 evidence=未验证）
     5) dom_cua_click + dom_cua_type 仅作最后备选，同样须读回 value
     注意：检索词含 * + - 等特殊符号需加半角引号
S5 重新读 DOM（提交后节点全部失效）→ 读取结果页
     ★ CNKI 是 SPA：提交成功后 tab_url / tab_title 完全不变，不能用 URL/标题判成功，以 DOM/截图为准
S6 结果页可读字段：题名链接、作者链接、来源期刊链接、被引数、下载数、下载链接、HTML/原版阅读链接
     左侧「主要主题」分面（联合作用 / 毁伤效应 / 耦合作用 / 爆炸载荷…）可用来扩检索词
     顶部分类：总库 / 学术期刊 / 学位论文 / 会议（实测 288 条时 105 期刊 + 183 学位）
S7 详情页入口：**不要点题名**
     ★ 实测（run-cn-1）：dom_cua_click 点题名链接返回 applied=true，但页面不跳转、tabs_list 无新标签页、tab_url 不变；
       改真实坐标点题名文本，同样无任何反应。→ 旧写法「点题名可能新标签页」是错的
     正确做法：读结果页题名的实测 href（`kcms2/article/abstract?v=...`）→ tabs_new 直达，标 detail_entry=unknown
     摘要仍是静态文本，DOM 快照读不到 → tab_screenshot
S8 权限判断：下载链接 title="下载" 才继续；"未登录" 停机
     详情页无下载按钮（复证），但存在 `x.cnki.net/web/page/auth-check?redirectsource=zkjbj&redirectjump=yxread&...&filename=<filename>`
     的阅读鉴权链接（对应 HTML阅读 / 原版阅读）→ 可作「阅读权限走单独鉴权域」的判据，**不点击**
S9 点下载链接（bar.cnki.net/bar/download/order?id=...）→ **直落**，不在浏览器内渲染
S10 立刻核验下载目录出现新文件、无 .crdownload；再交给 litadopt.py
```

### 自测回填（2026-11-12，status=ok，24 步）

- **DOM 可读**：机构名 `div[title=<机构名>]`、一框式输入框、提交 `input[type=button]`（value 空无文案）、分类计数（总库 1 / 学术期刊 1 / 学位论文 0）、题名链接 `kcms2/article/abstract?v=...`、5 位作者链接、来源链接「中国舰船研究」、被引 67 / 下载 836、下载链接 `title="下载"`、`title="HTML阅读"`、主题/来源类别/学科分面 checkbox、详情页来源/年份卷期/作者/机构/关键词/基金/AI 推荐问题链接。
- **DOM 读不到（须截图 / `tab_title`）**：详情页题名（静态 h1）、摘要段落、结果数「共找到 1 条结果」、字段下拉「主题 ▼」、排序/显示条数/视图切换。
- **权限标识**：结果页下载链接 `title="下载"`、`title="HTML阅读"`；机构名可见。
- **详情页没有下载按钮**，下载链接在结果页（S9 不要去详情页找）。
- DOM 出现 `input[name=CookieName]` 疑似会话令牌 → 按 `limits.md` §1 过滤，不读值。

## 高效要点（实测有效）

- **完整题名一框式检索可精确命中唯一结果**（总库 1），比宽泛检索省大量翻页。本机 4 篇都用这招。
- 宽泛检索（多个词并列，动辄两三百条）前几条常不相关；先加词收敛或直接精确题名。
- 「结果中检索」可在现有集合内二次收敛，不重发全库检索。
- 先在结果页读题名/作者/来源/被引/下载数决定是否要全文，再点下载。
- 一次会话逐篇下载，篇与篇之间留间隔；**每篇只点一次**，重复点击会产生 `(1)~(4)` 同 MD5 副本（本机实测 5 份完全相同）。

## 下载与文件（实测）

| 项 | 值 |
|---|---|
| 触发编码 | `直落`（点击即写盘，无二次确认、不在浏览器内渲染）【实·2026-11-13：连续 11 篇一次点击全部落盘】 |
| 期刊论文 | 文件名 `.caj`，但**内容格式不固定**：或为 `%PDF-1.6`（如 2015 年《中国舰船研究》那篇），或为 **`KDH 2.00`**（头 `4b444820322e3030`，2026 年新下的 11 篇全是）→ **必须按魔数判**，`litadopt.py` 会自动改成 `.pdf` / `.kdh`【实】 |
| 学位论文 | 真 CAJ（头 `CAJ\0\x01\x00\x02`）或 KDH，有「整本下载 / 分章下载」，需 CAJViewer / 知网 E-Study |
| 尾部 | `<FileProperty>…<TableName>CJFDTotal</TableName><Type>JOURNAL\|DISSERTATION</Type></FileProperty>`；期刊 `%%EOF` 距尾约 142 字节 |
| 完成判定 | 末 1KB 内 `</FileProperty>` 闭合 + 头魔数 + 大小稳定（见 `toolchain.md`） |
| 下载目录 | 由 `litadopt.py` 自动解析（注册表 `User Shell Folders`），**不硬编码**；不同机器可能是任意盘符路径，用 `--root` 可覆盖 |
| ★ **格式优先级** | **PDF 优先**。同一篇若同时提供 `PDF下载` / `CAJ下载` / `下载`，**先点 PDF**；只有一种就点它，不要为了换格式反复重下（每次下载都计配额）。下完一律按**魔数**判定真实格式，不信任后缀 |
| ★ **KDH/CAJ 打不开怎么办** | 本机实测未装 CAJViewer。三种正路：① 装知网官方 CAJViewer / E-Study（免费）；② 用页面上的「HTML阅读」看正文；③ 找该刊的 OA/预印本版本走 L2。**不要反复重新下载同一篇换格式** |

### ★ 批量下载最短路径（2026-11-13 实测，11 篇 5 分 50 秒）
比"输入检索词 → 回车"快得多，**免掉最容易失败的一步**：

1. `tabs_new` 直接打开构造 URL（`kw` 放 URL 编码后的题名）：
   `https://kns.cnki.net/kns8s/search?classid=WD0FTY92&korder=SU&kw=<encoded>`
   （`classid=WD0FTY92` 总库；`korder=SU` 主题）
2. 等 2–3 秒 → `tab_screenshot` 看命中条数与首条题名（**不要读 DOM 找题名，读不到**）
3. `cua_click` 点**首行操作列第 1 个图标**（向下箭头 = 下载）。1513×732 视口实测坐标 **(1264, 369)**；操作列 4 个图标从右往左是 `下载(↓) / HTML阅读 / 收藏 / 引用`
4. 等 3–5 秒 → `ls` 核验落盘
5. `tabs_close` 关页，篇间留 4–6 秒

**效率红线**：单篇 ≤6 步、≤2 张截图、90 秒无进展即跳过。上一轮执行者因反复重试 `tabs_close` 与过度截图，45 分钟只下 1 篇；改用本路径后 11 篇 5 分 50 秒全成。
**机构身份**：右上角显示「南京理...」即有效；**开代理也有效**（与 Elsevier 不同）。

## 偏离通用模板之处

- 结果页是**分组浏览 + 主题分面**，不是标准翻页控件。
- `直落` → 没有「详情页下载按钮」这一步，下载链接在结果页。
- 多域：`kns.cnki.net`（检索）、`www.cnki.net`（首页）、`bar.cnki.net`（下载）、`login.cnki.net`（登录）、`fsso.cnki.net`（CARSI）、`oversea.cnki.net`（海外版）。
- 名实不符：扩展名不可信，一律按文件头判定。

## blockers（实测 / 已知）

| 现象 | 处置 |
|---|---|
| 下载链接 `title="未登录"` | 停机交人工登录，不重试、不代登录 |
| `DOM node_id is stale`（下载点击后常见） | 重新读 DOM |
| `provider invocation timed out` | 同一操作最多重试一次 |
| `tabs_finalize` 超时 | 不影响页面与交付，记录即可 |
| CAPTCHA / 403 / 异常流量 | 停止队列，标记需人工 |

## 待实测（不要写成确定事实）

- 下载链接是否仍为「直落」：run-cn-1 只观察到 href 形态 `bar.cnki.net/bar/download/order?id=…`，**未点击复验**（红线）【未】。
- CNKI 国内版 `kns.cnki.net` 是否支持 `DOI=` / `TKA=` 字段【未】。
- 学位论文「分章下载」的文件结构与整本是否一致【未】。
- 海外版 PDF 整本下载是否对当前机构开放【未】。
- 详情页顶部「印刷版 ▾」下拉的具体项【未】。
- 本校具体已购库清单【未】。
