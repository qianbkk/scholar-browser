# 工具链：浏览器能力边界、DOM 与截图、失败回退、文件归集

> **本文件结构**：1. 浏览器工具能力清单与缺口 · 2. DOM 与截图：两条腿走路（2026-11-13 修正） · 3. 失败回退表 · 4. 下载目录与文件识别（本机实证） · 5. 脚本状态与安全契约 · 6. 命令速查

## 1. 浏览器工具能力清单与缺口

`mcp__browser__*` 共 32 个工具，来自 browser-use 插件的**会话内私有 stdio 子进程**；插件 `.mcp.json` 只有 `command: browser-mcp.exe, args: []`，无 port/url，全机检索未发现 HTTP/WS/CLI 端点。

| 有 | 没有 |
|---|---|
| 标签页枚举/新建/跳转/前进后退/刷新/焦点 | 下载管理（列下载、等待完成、取下载文件路径） |
| DOM 快照（交互元素）与 DOM 点击/输入/滚动/按键 | 读取本地文件内容 |
| 坐标点击/拖拽/滚动/批量动作 | 读取网络响应体、拦截请求 |
| 截图（含整页）、取 URL / 标题 | Cookie / localStorage / 凭据读取 |

→ L3 的「下载」靠**点击触发浏览器真实落盘**；L2 的下载由 `scripts/oa_fetch.py` 用标准库 HTTP 完成（不经浏览器，带 UA 标识 + 串行 + 间隔）。两者落盘后走同一套魔数校验。

**自定义 MCP server 无法复用登录态**：Edge 扩展经 native messaging stdio 与 host 通信，`com.workbuddy.extension.json` 的 `allowed_origins` 只放行三个固定扩展 ID。

### 1.0 从零启动浏览器（用户授权时，2026-11-15 实测）

无窗口时 `tabs_new` 报 `No current window`，即使 `browsers_list` 显示扩展在线。用户授权后按以下顺序恢复：

1. `browsers_list` 确认 `type=extension` 条目存在；
2. PowerShell：`Start-Process msedge "<url>"`，等待 5–8 秒；
3. `browsers_list` 复核扩展仍在（无需重新连接）；
4. `tabs_new` 创建受控页 —— 实测成功，返回 `tab_id=1`，标题为 ScienceDirect 搜索结果页；
5. 若仍报 `No current window`：请用户点一次扩展图标，**不要重启浏览器**。

实测补充：机构 IP 直连时 ScienceDirect 结果页 DOM 可读到机构名、`View PDF` 的 `pdfft` href 与 `Download selected articles` 按钮。

### 1.1 重启浏览器后扩展会断（本机实测）
`browsers_list` 只剩 `WorkBuddy Browser`（type=desktop）、没有 `type=extension` 的条目，说明 **Edge 扩展的 service worker 休眠了，native messaging 通道没接上**。
- **恢复办法**：请用户在 Edge 工具栏点一下 WorkBuddy 扩展图标（Agent 点不到浏览器 UI），随后 `browsers_list` 会重新出现 `browser_id=2`（extension 0.2.8，ID `ndbfelmlimfjklodckmbalfioaehegpc`）。
- **重启 Edge 前先想清楚**：任何 `taskkill msedge` + 重启，都会打断这条通道，必须让用户点一次才能恢复。不要以为重启就自动好了。
- **不要退回内置浏览器**：内置 `WorkBuddy Browser` 的 UA 是 `WorkBuddy/5.9.3 Chrome/138 Electron`，Cloudflare 一眼识别（实测直接弹 reCAPTCHA，即使出口 IP 是正确的国内直连 IP 也没用）。**机构权限 + 反爬对抗只能靠真实 Edge**。

## 2. DOM 与截图：两条腿走路（2026-11-13 修正）

**先纠正一条曾经的错误结论**：早前写「5/5 平台题名/摘要/权限标识全部读不到，只能截图」——**这不成立**。真实情况是**按站点枚举**：

| 站点 | DOM 可读 | 必须截图 |
|---|---|---|
| CNKI | 机构名、一框式输入框、分类计数、题名/作者/来源链接、被引/下载数、下载链接 `title` | 结果数、详情页题名 h1、摘要、字段下拉、排序/条数 |
| 万方 | 检索框、5 个二次检索 input | 题录全部、**按钮组（完全不在快照里）**、结果数、分面 |
| arXiv | arXiv ID、`[pdf, ps, other]` 链接及 href、作者、DOI、`View PDF`（详情页） | 题名、摘要、结果数、Submitted 日期 |
| PubMed | 首页 `input[name=term]`、submit 按钮 | 结果页全部（本轮被校验页拦断，未采信） |
| ScienceDirect | **题名、期刊名、`View PDF`（href 即 pdfft 端点）、DOI、作者按钮、机构名** | 结果数、作者名、出版日期、`Full text access` 徽标、摘要 |
| WoS | 检索控件、字段下拉、按钮文本、三个检索入口 | 结果页全部（正文未绘制） |

→ **两条腿走路**：先读 DOM 找结构化元素（**链接 + href 最有价值**），再截图补静态文本。不要固定先后顺序，哪个有效用哪个。

### 2.1 两种失败方向，别混为一谈

| 症状 | 判定 | 处置 |
|---|---|---|
| **DOM 空/超时，截图正常** | SPA 型（CNKI / 万方 / 维普实测） | 截图读题录；DOM 只用来找控件 |
| **截图空白，DOM 完整** | 页面已加载但正文未绘制（ScienceDirect 详情页、WoS 全站实测） | **按 DOM 读**，标 `render_blank`；**不反复截图重试**，也**不用空白截图推断"无权限"** |

### 2.2 其他硬约束

- **"用 DOM 定位按钮"也不保证成功**：万方结果页的「在线阅读 / 下载 / 全文快报 / 引用 / 收藏」按钮组**完全不在快照里** → 只能截图看位置 + 坐标点击。
- 结果数（CNKI「共找到 1 条结果」、万方「找到 201 条文献」、ScienceDirect「105 results」、arXiv「Showing 1–17 of 17 results」）**一律靠截图**，不进 DOM。
- 快照上限 **20000 字符 / 200 元素**；`node_id` 只在当前快照有效，跳转/提交/弹窗后**必须重读**。
- DOM 可能含凭据类元素（CNKI 结果页实测 `input[name=CookieName]`）：**不读取、不回显、不写日志**。
- **用户装的对页翻译/增强扩展会注入额外节点**（arXiv 实测出现带 `_immersive_translate_auto_translate=1` 的"双语版本"链接）→ 解析规则**按 href 前缀白名单过滤**，不要按"链接数量/位置"硬编码。
- 部分站点有常驻浮层遮挡正文（ScienceDirect 左下 `Reading Assistant (LeapSpace)` 面板）→ 截图看着像"加载失败"，先看 DOM 有没有内容再判。

### 输入与提交（站点相关，不能写成通用可靠步骤）

| 方式 | 实测结果（跨三轮） |
|---|---|
| `dom_cua_type` | CNKI / 万方 / WoS（两页）**无效**（`applied=true` 但 `value` 空）；PubMed `name=term` **有效** |
| `dom_cua_click(type=submit)` | PubMed **run-1 两次不触发、run-3 一次生效** → 同一站不同轮次结果相反，**不能写成定论** |
| `cua_execute` 真实坐标 `click + type` | **arXiv `/search/`、PubMed 首页、ScienceDirect 首页 `name=qs` 本轮一次写入成功**；CNKI/万方多数生效；CNKI run-2 两次失败（整页被 `ctrl+a` 全选 = 未聚焦）；WoS 因截图空白**没有坐标可用**，退无可退 |

→ **没有一种输入方式跨站可靠**。按序执行：
1. `cua_execute` 真实坐标事件（首选）；
2. **每次提交前必须读回 `input.value` 或截图确认写进去了**；`value` 为空就别按 Enter（否则 `ctrl+a` 全选整页）；
3. 未写入 → 分步 `cua_click` 聚焦 + `cua_type`，再次读回 `value`；
4. **截图也空白、拿不到坐标** → 判「不可脚本化」，转只读 DOM 模式（见 §3）；
5. 仍失败 → 用 `tab_goto` 直达结果页，标注 URL 是「页面实测 href」还是「按表单参数构造」，构造类 `evidence=未验证`；
6. `dom_cua_click` + `dom_cua_type` 只作最后备选，同样读回 `value`。

### 提交成功的验证判据（必须双验）

- **SPA**（CNKI 实测）：提交后 `tab_url` / `tab_title` **完全不变** → 只能靠 DOM/截图。
- **普通跳转**（万方 / PubMed / ScienceDirect / arXiv 实测）：URL 会变，`tab_url` 可辅助。
- ⚠ **只看 URL 会误判**：PubMed 出现「正在检查浏览器」校验页时，`tab_url` **已经是** `/?term=...`（看似成功），正文却是检查页 → **必须 URL + 截图双验**。
- **顺手记下结果页 URL 形态**（万方 `s.wanfangdata.com.cn/paper?q=<词>&p=1`、arXiv `/search/?query=...&size=50`、ScienceDirect `/search?qs=...`）——表单提交失败时这是唯一可复用回退；SPA（CNKI）没有，只能靠 DOM/截图。

## 3. 失败回退表

| 现象 | 处置 |
|---|---|
| `provider invocation timed out`（claim / DOM / click / finalize） | **同一操作最多重试一次**；仍失败记录并报告，不循环重试。`tabs_finalize` 超时不影响页面与交付 |
| `tabs_new` 超时 | **先 `tabs_list` 复核再重试**——实测报警时标签页其实已创建，盲目重试会产生重复 tab（实测多出 tab 11/12）。已建就复用 |
| `tabs_close` 超时 | **同样是假失败**（2026-11-13 实测：报 timeout 但页面已关）→ 用 `user_open_tabs` / `tabs_list` 复核，消失了就是成功，不要重复关 |
| 任务结束还有自己开的页面 | 收尾必须清场：`tabs_close` 关掉本轮 `tabs_new` 的所有页；只保留用户明确要看的；用户原有页不动（`limits.md` §1.8） |
| DOM / `cua_execute` / `cua_click` **全部**持续超时，但截图与 `tab_goto` 正常 | 判「该站不可脚本化·型 A」（维普实测，两域均复现）→ 降级为**只读截图模式**：能截到的题录照读，输入类标 `partial`，请用户手工检索一次 |
| DOM 可读、`tab_goto` 正常，但 `dom_cua_type` 写不进 **且**截图空白拿不到坐标 | 判「该站不可脚本化·型 B」（WoS 实测）→ 降级为**只读 DOM 模式**：可读字段照读，输入类标 `partial`，请用户手工检索一次 |
| 截图空白但 DOM 完整 | `render_blank`（ScienceDirect 详情页实测）→ 按 DOM 读，不重试截图，不据此判无权限 |
| `DOM node_id is stale` | 重新 `dom_cua_get_visible_dom`，不用旧标识 |
| `stale_tab` / `browser_not_found` / `extension_disconnected` / `host_restarted` | 从 `browsers_list` 重新开始，不复用标识 |
| 登录失效 / 跳登录页 | 停机，标记「需人工」，请用户在真实浏览器重新登录或重走 CARSI |
| CAPTCHA / unusual traffic / 403 / 429 | 停止当前队列，不重放、不换 IP、不绕过 |
| 「正在检查浏览器」/ JS challenge 中间页 | 停机标 `blocked`，不点手动重定向、不重放（`limits.md` §2）。注意此时 `tab_url` 可能已变，别误判成功 |
| 站点整站不可达（如 `ERR_CONNECTION_TIMED_OUT`） | 记 `timeout`，**不要记 `blocked`**（blocked 留给风控/权限）。**先确认是否需代理**：配了代理就用 `--proxy`/环境变量重试一次——实测 GS 与 PubMed 都是"直连失败、代理后正常" |
| Cookie 横幅 / 机构选择 / 浮层遮挡 | 按 `limits.md` 判断可否关闭；**要求"必须与横幅交互才能关闭"的站点不要替用户点同意**，按结构性 blocker 交人工 |
| 点了下载但目录无新文件 | 先查平台 `download` 段：可能是 `viewer+保存` 需第二步、或新窗口、或二次确认；再查 `.crdownload` |
| 只出现 `.crdownload` / `.part` | 下载未完成，等待或标失败，**不要改后缀当作完成** |
| 任何输入方式后 `input.value` 仍空 | **不提交**；按 §2 顺序换方式，每步读回 `value` 或截图确认 |
| 点提交后页面不变 | 确认是 SPA（URL 不变但内容已变）还是真没提交；真没提交按 §2 回退 |
| `scan-new` 出现 `manual_drop` | 先核对清单；确认确由本次下载产生后加 `--allow-unconfirmed` 重跑，不要手改 plan |

## 4. 下载目录与文件识别（本机实证）

- 真实下载目录由注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders` 的 `{374DE290-...}` / `{7D83EE9B-...}`（`REG_EXPAND_SZ`）决定，**常与 `C:\Users\<用户名>\Downloads` 不一致**（用户改过默认位置）。脚本按「组策略 → Preferences → 注册表 → 兜底」自动解析，不写死路径。
- Edge `Preferences` 里 `download.default_directory` / `prompt_for_download` / `savefile` **均不存在**，组策略键也不存在；Edge 走 OS 已知文件夹 → 脚本按「策略 → Preferences → 注册表 → 兜底」解析，禁止硬编码。
- Edge 运行中 `Preferences` 可读；**被锁的是 History**（需 `mode=ro&immutable=1`，且可能不含 WAL 最新记录，只作辅助佐证）。
- 文件头魔数：期刊 `%PDF-1.6`（扩展名常是 `.caj`）；学位论文 `CAJ\0\x01\x00\x02`。两类尾部都挂知网 `<FileProperty>…<Type>JOURNAL|DISSERTATION</Type></FileProperty>` XML。
  - `%%EOF` 只在期刊类出现且距文件尾约 142 字节；真 CAJ 无 `%%EOF`。
  - **格式只看头 8 字节；完成看末 1KB 内 `</FileProperty>` 闭合（通用 PDF 看 `%%EOF`）**。
- 尾部 XML 可提取 `Doi` / `FileName` / `TableName` / `Type`；**没有中文期刊名、学校名、年份明文**，脚本不编造，用 `--source-map` 由 AI 从页面确认后提供。
- **PDF 库**：本机已装 `pypdf` 与 `PyMuPDF`（2026-11-16 复核，`import fitz` 为 PyMuPDF 2.1）→ 完整性判定可用「头 + 尾 + 能开且首页有文本」三件套（`limits.md` §1.0.2）。但**Skill 脚本本身零依赖**，只用魔数，不 import 这两个库。
- **CAJ**：本机无 CAJViewer / caj2pdf，真 CAJ 需用户自行安装阅读器。
- 中间态后缀：`.crdownload` `.part` `.partial` `.download` `.opdownload` `.tmp` `.!ut` `.td`；同名冲突 Chromium 追加 ` (1)`、` (2)`，**按 mtime 判最新，不按字符串排序**（`(10)` 会排在 `(2)` 前），内容一律按 MD5 去重。

## 5. 脚本状态与安全契约

状态目录 `<workspace>/.litadopt/`：`baseline.json`、`baselines/`、`plans/`、`batches/`、`operations.jsonl`（append-only，回滚依据）、`staging/`、`quarantine/`、`.trash/`、`lock`（`O_EXCL` 原子锁，stale 锁需 `--force-unlock`）。

| 命令 | 写操作 | 可自动 |
|---|---|---|
| `init-baseline` / `scan-new` / `verify` / `report` / `adopt --dry-run` | 只读（除状态目录） | ✅ |
| `adopt` | 工作区内复制 → 校验 → 规范命名 → 落位 | ✅ |
| `adopt --move-sources` | 把本轮 plan 内逐条列出的本次新增文献移到隔离区（可逆，非删除），≤10/批、移前二次校验 size/mtime/MD5 | ⚠️ 需用户已明确授权「默认目录不留」 |
| `rollback --batch <id>` | 隔离区移回原路径、工作区副本移入 `.trash/` | ✅（用户发起） |
| 彻底删除隔离区 | **本 Skill 不提供**，不可逆删除需用户另行明确确认 | ❌ |

退出码：`0` 成功 / `1` 异常 / `2` 参数或 IO / `3` 部分成功或待确认 / `4` 校验失败 / `5` 锁或需确认 / `6` TOCTOU。
任何失败（占用、校验不符、TOCTOU、日志写失败）停止该批并保留现场。

## 6. 命令速查

```bash
# L1 发现：按关键词检索候选（写 --out 存全量，终端只打前 12 条）
python "<skill_dir>/scripts/oa_fetch.py" search --query "<关键词>" --from-year 2020 --limit 25 --field title_abstract --out <dir>/q1.json

# L1 引文滚雪球：种子 DOI -> 谁引用了它（cited_by）/ 它引用了谁（references）
python "<skill_dir>/scripts/oa_fetch.py" cite --doi <DOI> --direction cited_by --limit 50 --out <dir>/cite.json

# L2：先取元数据（下载前判断值不值得下 / 下载不了时兜底）
python "<skill_dir>/scripts/oa_fetch.py" meta --doi <DOI> [--format md]

# L2 直取（不经过浏览器）
python "<skill_dir>/scripts/oa_fetch.py" resolve --doi <DOI> [--email <mail>]
python "<skill_dir>/scripts/oa_fetch.py" fetch --doi <DOI> --out <path> [--dry-run] [--interval 1.0]
python "<skill_dir>/scripts/oa_fetch.py" fetch --url <pdf-url> --out <path>
python "<skill_dir>/scripts/oa_fetch.py" probe --url <url>
python "<skill_dir>/scripts/oa_fetch.py" check --file <path>

# 网络：默认直连（不读环境变量），三者任选其一
#   1) 什么都不加 = 直连（机构订阅库必须走这条）
#   2) --proxy http://127.0.0.1:<端口>   显式代理（公开资源用）
#   3) --auto-proxy                      先直连，网络层失败才降级读 HTTPS_PROXY / HTTP_PROXY
#   --no-proxy 只为兼容保留，等同默认直连
# 邮箱：--email <mail> 或环境变量 SCHOLAR_EMAIL（Unpaywall 必需）

# 下载归集
python "<skill_dir>/scripts/litadopt.py" init-baseline --workspace "<workspace>"
python "<skill_dir>/scripts/litadopt.py" scan-new --workspace "<workspace>" --target-dir "<workspace>/文献/<主题>" [--allow-unconfirmed] [--no-history] [--settle 1.0]
python "<skill_dir>/scripts/litadopt.py" adopt --plan <plan> --workspace "<workspace>" --target-dir "<workspace>/文献/<主题>" [--source-map <json>] [--move-sources] [--dry-run]
python "<skill_dir>/scripts/litadopt.py" verify --workspace "<workspace>"
python "<skill_dir>/scripts/litadopt.py" report --workspace "<workspace>" --format table
python "<skill_dir>/scripts/litadopt.py" rollback --batch <batch-id> --workspace "<workspace>"
```

所有命令 stdout 为单行 JSON；`litadopt.py` 的公共参数必须放在子命令**之后**。
`oa_fetch.py` 退出码：`0` 成功 / `3` 有候选但全未通过或 no_candidate / `4` 校验失败 / `2` 参数错误 / `1` 其他。
`oa_fetch.py` 无 `SCHOLAR_EMAIL` 时自动跳过 Unpaywall（只用 OpenAlex），候选会变少；Unpaywall 要求真实邮箱，占位会被 422 拒。
