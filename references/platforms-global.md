# 外文平台 SOP

> Google Scholar / Web of Science / PubMed+PMC / arXiv / ScienceDirect。
> 依据标签见 `limits.md` §4；「实测」= 本机真在页面上看到的（2026-11-12 run-1、2026-11-13 run-intl-1）。

> **本文件结构**：通用提示 · arXiv · PubMed / PMC · ScienceDirect (Elsevier) · Web of Science · Google Scholar · 不在表内的平台怎么处理

## 通用提示

- 英文站多为普通跳转（非 SPA）→ `tab_url` 可辅助验证，但**必须与截图双验**（PubMed 校验页会让 URL 看起来像成功）。
- **可读性按站点不同**：ScienceDirect 题名/期刊/`View PDF` DOM 可读；arXiv 作者/链接可读；摘要与结果数基本都要截图。详见 `toolchain.md` §2。
- **能走 L2 就先走 L2**：这几个站都有 DOI/ID/PII，`oa_fetch.py fetch --doi` 常比开浏览器快。
- 权限判据：`View PDF` / `Free PMC article` = 可下；`Get Access` / 锁图标 = 订阅范围外；**截图空白不等于无权限**。

---

## arXiv

| 字段 | 值 |
|---|---|
| entry | `https://arxiv.org`；**首页没有自由文本检索框**（只有 `name=group` 学科下拉 + `input[type=button][value=Search]`）→ 必须进 `/search/`【实测】 |
| search_box | `/search/` 下 `input[name=query][placeholder="Search term..."]` + `select[name=searchtype]`（All fields / Title / Author(s) / Abstract / DOI / arXiv identifier）+ `button` 文本 `Search`【实测】 |
| submit | `cua_execute` 真实坐标 click→type 一次写入（读回 `value` 成功），再点 Search 按钮生效；URL 变为 `/search/?query=...&searchtype=all&abstracts=show&order=-announced_date_first&size=50`【实测】 |
| 结果页 | 每条是 **`[pdf, ps, other]` 三链接**，`pdf` 的 href 就是 `https://arxiv.org/pdf/{id}`（**DOM 可读**）；作者是作者检索链接（DOM 可读）；**题名不是链接**，真正的详情入口是 `arXiv:{id}` 锚点；结果数「Showing 1–17 of 17 results」只能截图【实测】 |
| detail | `arXiv:{id}` 锚点点击**同标签页**跳转（`same_tab`）；`/abs` 页摘要**静态 → 必须截图**；DOI 在详情页可读（`https://doi.org/10.48550/arXiv.{id}`）【实测】 |
| download | **`View PDF` 只出现在 `/abs` 详情页右侧 `Access Paper:` 侧栏**（DOM 可读，href=`/pdf/{id}`）；**结果页没有 View PDF**。有 ID 时**直接取这条 href 走 L2 `fetch --url`**，不必进详情页【实测】 |
| 语法 | `ti:` `au:` `abs:` `co:` `jr:` `cat:` `rn:` `id:` `all:`；`AND/OR/ANDNOT`；`""` 短语；`?` 单字符、`*` 任意（不能在首位）【联】 |
| 限速 | 官方 API TOU：每 3 秒 1 次、单连接；持续超额 429；禁规避/轮换 IP【联】 |
| 备注 | `10.48550/arXiv.{id}` 是 DataCite DOI，指向**预印本**，不是期刊正式版；引用要区分 |

**待实测**：`View PDF` 点击后是浏览器内渲染还是落盘（红线未点）；`select[name=searchtype]=Title` 与 `query` 里写 `ti:` 是否等价。

---

## PubMed / PMC

| 字段 | 值 |
|---|---|
| entry | `pubmed.ncbi.nlm.nih.gov`（题录/摘要）；`pmc.ncbi.nlm.nih.gov`（OA 全文） |
| 直达 | `https://pubmed.ncbi.nlm.nih.gov/{PMID}/`；`https://pmc.ncbi.nlm.nih.gov/articles/PMC{id}/` |
| search_box | 首页 `input[name=term]`（`type=search, role=combobox`）+ submit `<button aria-label="Search">`；**首页无字段下拉，字段只能写进 term**，如 `"surrogate model"[ti]`【实测】 |
| 输入 | `dom_cua_type` **有效**（少数有效的站）；`cua_execute` 坐标 click+type 本轮也一次成功 → **两种都行**【实测】 |
| submit | ⚠ **同一站不同轮次结果相反**：run-1 `dom_cua_click(submit)`+Enter **两次不触发**；run-3 `dom_cua_click` 点 `aria-label=Search` **立即生效**（URL 变 `/?term=...`）→ **不能写成定论**，提交后必须双验 |
| ⚠ 提交后陷阱 | 直连时曾跳「正在检查浏览器以便让您访问…」校验页（run-intl-1）：此时 **`tab_url` 已是 `/?term=...`（看似成功）**，正文却是校验页 → **URL + 截图双验**，判 `blocked` 则本轮该平台结果页/详情页全部不可采信，不点手动重定向、不重放。**开代理后复测未复现**（2026-11-13：直接导航 `?term=` 正常返回 204 results）→ **遇到校验页先试代理**，不要当站点永久限制【实测】 |
| 列表视图 | **新版 PubMed 默认列表视图，不显示摘要**，只给作者/出处/DOI/PMID + `Free PMC article` 标识 → 要摘要得进详情页【实测】 |
| detail | 摘要静态 → 截图；右侧 `Full text links` 指出版商 |
| download | PubMed 多数只有摘要 + 出版商链接；**只有 PMC 有 PDF** |
| 字段语法 | `[ti]` `[tiab]` `[au]` `[ta]` `[mh]` `[pmid]` `[aid]` `[lid]` `[tw]` `[la]`；**官方清单无 `[DOI]`** → DOI 走 `[aid]`/`[lid]` 或直接粘 DOI 让 citation sensor 映射【联】 |
| 红线 | 官方要求自动化批量检索走 E-utilities / OAI-PMH；本 Skill 的人工式逐页操作不走批量通道【联】 |

**待实测**：结果页可读字段、`Free PMC article` 徽标是否 DOM 可读、`Full text links` 位置。

---

## ScienceDirect (Elsevier)

| 字段 | 值 |
|---|---|
| entry | `https://www.sciencedirect.com`；**首页是三框快速检索**，不是高级检索表单【实测】 |
| search_box | `input[name=qs]`（Find articles with these terms）/ `input[name=pub]`（journal or book title）/ `input[name=authors]`；提交 `aria-label="Submit quick search"`（文本 `Search`）；高级检索入口 `a[href="/search/entry?origin=home&zone=qSearch"]`【实测】 |
| ⚠ autosuggest | `qs` 框有联想，联想项以 `<li role="option">` **进入 DOM 快照** → 提交前**不要误点联想项**（否则会直接跳到某篇文章）【实测】 |
| submit | `cua_execute` 坐标 click+type 一次写入 → 点 Search → URL 变 `/search?qs=...`【实测】 |
| auth | 机构订阅 IP / Shibboleth / 个人账号；**机构名 DOM 可读**（`button aria-label="<学校> Institutional Access"`）【实测】 |
| ⚠ **代理致命** | **必须走机构 IP 直连**。本机实测：开代理后 `doi.org` → `sciencedirect.com` 直接弹「Are you a robot? Please confirm you are a human…」，挑战页 `IP Address` 记录的正是**代理出口**（境外云节点），而直连出口是国内教育网/运营商 IP。→ **机构 IP 授权失效 + 触发反爬，双重失败**。处置：先让用户关代理或给 `sciencedirect.com`/`elsevier.com`/`doi.org` 设 DIRECT 规则，再重试；**不要换节点重试**（换节点＝换了个更可疑的 IP）【实测】 |
| 机构入口 | 若直连后仍显示 `Get Access`：找 `Access through your institution` / `Choose Organization` → 选机构 → 走机构登录（CARSI/Shibboleth）。**这一步必须用户本人输账号**，Agent 只负责把页面导航到那里 |
| results | **题名 DOM 可读**（`a[href="/science/article/pii/{PII}"]`）、**期刊名可读**（`/science/journal/{id}`）、**`View PDF` 可读**；结果数「105 results」、作者名、出版日期、`Full text access` 徽标**只能截图**【实测】 |
| detail_entry | **点题名有效，同标签页跳转**（`same_tab`）【实测】 |
| ⚠ 详情页 | 正文可能**整块不绘制**（2 次截图全空白，只有左下 `Reading Assistant (LeapSpace)` 面板可见），而 DOM 里题录/作者/DOI/`View PDF` 齐全 → 判 `render_blank`，**按 DOM 读**，摘要标 `unknown` 交人工，不反复截图【实测】 |
| download | **★ 优先走批量 ZIP（实测可行，唯一能自动落盘的通道）**：结果页「全选」勾选框 → 顶部按钮 `Download N articles` → 站点**服务端打包**后浏览器直接下载 `ScienceDirect_articles_<ddMonyyyy>_<hh-mm-ss>.zip`【实测】 |
| 全选怎么点 | **只在「一个都没选中」的状态下点一次有效**；已部分选中时点它不生效（实测连点 5 次按钮仍是原数字）→ 刷新页面（`tab_goto` 同一 URL）回到空状态再点；仍不行就逐行点行勾选框（行勾选框坐标点击稳定） |
| 打包耗时与体积 | 3 篇 ≈ 8 秒 / 41 MB；**24 篇 ≈ 80 秒 / 403 MB** → 等待时轮询 `ScienceDirect_*.zip`，不要以 `.crdownload` 判断（大包不走中间态文件） |
| 权限过滤 | 服务器会剔除无权限条目并弹提示：「Downloading a zip file containing **24 articles of the 25 requested**. Note: Some of your selections could not be downloaded as you are not subscribed to that content.」→ **权限判断在站点侧，不用自己预筛** |
| 导入 | `scripts/sd_zip.py --zip <zip> --target-dir <dir>`：解压 + 魔数校验 + MD5 去重 + `NN_` 接续编号；同一 ZIP 重复导入会全部标 `duplicate_md5` |
| **★ 题录/摘要导出** | 结果页全选 → `Export`（按钮在 `Download N articles` 右侧）→ 弹窗选 `Export citation to RIS` → 落盘 `ScienceDirect_citations_<时间戳>.ris` → `scripts/ris_meta.py` 解析。**实测 25 条全部带 `AB` 摘要**（1500–2500 字出版商原文），远优于 Crossref/OpenAlex/S2。这是拿不到全文时"给全面准确内容"的首选通道【实测】 |
| RIS 字段坑 | ScienceDirect 用 **`T1`** 做题名字段（不是 `TI`）；`DO` 是完整 DOI URL；`AB` 摘要；`UR` 文章页；解析器已兼容 `TI/T1/BT/CT` |
| 不支持 | 一框式检索**不能用多个 DOI 拼 OR**（`"doi1" OR "doi2"` → No results）；要按 DOI 找文章得用题名检索或从 Crossref 反查 |
| download(单篇) | `View PDF` 的 href 就是 PDF 端点：结果页 `/science/article/pii/{PII}/pdfft?pid=1-s2.0-{PII}-main.pdf`；详情页版带 `md5`。**但点开只会进 reader**（Edge 157 下 `always_open_pdf_externally` 开关无效），存盘必须走系统「另存为」→ Agent 做不到。故单篇目标要**连带一篇相邻文献一起勾选**凑成 ZIP【实测】 |
| 限额 | 官方防滥用：搜索结果页 100 篇/天、期刊期号页 250 篇/天（按每天下载 PDF 总数计）【联】 |
| blockers | 全选勾选框**只在「一个都没选中」时点一次有效**（部分选中状态下连点 5 次都不变）→ 刷新回空状态再点，**不需要用户手动介入**；`Choose Organization`、推荐文献预勾选弹窗、LeapSpace 浮层遮挡；列表按 `Full text access` 过滤，无权限条目下不来 |
| 25 篇全选实测 | **成功**：一次全选 25 篇 → 服务端打包约 80 秒 → 403 MB ZIP，**未触发风控/限额**；ZIP 内**不含**无权限条目（自动剔除 1 篇）→ 见上面「权限过滤」行【实测·2026-11-13】 |

**待实测**：`Get Access` 分支（本轮机构订阅有效，未触发）。

---

## Web of Science

| 字段 | 值 |
|---|---|
| entry | `https://www.webofscience.com` → 302 到 `https://webofscience.clarivate.cn/wos/`（nextgen）【实测】 |
| 三个入口 | ① `/wos/woscc/smart-search`：单框自然语言（`input[name=search-main-box]`，submit `aria-label="Submit your question"` 初始 disabled）② `/wos/woscc/basic-search`：FIELDED SEARCH（数据库 Core Collection、Edition All、字段下拉默认 Topic、`Add row`、`Add date range`、`clear`、`search`）③ `/wos/woscc/advanced-search`：QUERY BUILDER【实测】 |
| ⚠ 语法归属 | **`TI=(...)` 这类字段化语法属 QUERY BUILDER**，写进 FIELDED SEARCH 的单行框只会被当成 Topic 的值【实测】 |
| auth | 机构 IP / CARSI / 个人账号。⚠ **未登录也能打开 basic-search 表单并看到完整检索控件，且页面不显示机构名** → **不能以"能否打开检索页"判断有订阅**；机构名缺失时 `login_valid` 只能记 `unknown`，要看结果页「出版商处的全文」是否出现【实测】 |
| ⚠ 工具可用性 | `dom_cua_type` 对 `name=search-main-box` **两次都写不进**（`applied=true`、`value` 空），同时**整页截图空白**（只有底部中文 cookie 横幅）→ **没有坐标可用**，第 3 级回退无法执行 → 判「不可脚本化·型 B」，转**只读 DOM 模式**【实测】 |
| results / detail | 未到达 → 全部【未】。WoS **不是全文宿主**，价值在精确检索 + 引文，拿到 DOI 就走 L2 或转出版商 |
| blockers | cookie 横幅 `aria-label` 明示「您必须与横幅进行交互才能将其关闭」→ 结构性 blocker，**不要替用户点同意**，交人工 |

**待实测**：机构订阅状态、结果页可读字段、`出版商处的全文` 是否出现、QUERY BUILDER 的输入是否能写入。

---

## Google Scholar

| 字段 | 值 |
|---|---|
| entry | `https://scholar.google.com` |
| ⚠ 网络 | **直连可能不可达**（本机实测 `ERR_CONNECTION_TIMED_OUT`）；**开代理后正常**（2026-11-13 复测：无验证码，检索约 630 条结果，首屏有 `[PDF]` 与 `Cited by`）【实测】 |
| 失败分类 | 网络不可达 → 记 `timeout`，**先提示用户检查代理/网络**；风控拦截（captcha / unusual traffic）→ 记 `blocked`，提示人工核对。**两者处置不同，不要混** |
| 提交方式 | ⚠ **键盘 Enter 不触发提交**，必须点搜索按钮（`btnG`）【实测】 |
| ⚠ URL 陷阱 | 该站用 JS 重写 history，**提交成功后地址栏仍是根路径** → 不能用 `tab_url` / `tab_title` 判成功，只能截图【实测】 |
| 弹层 | 首页右下有 `Scholar PDF Reader` 推广浮层，未交互；坐标点击前注意遮挡【实测】 |
| 官方态度 | **无公开 API**；robots 禁抓 `/scholar`、`/search`、多数 `/citations?`；ToS 要求自动化须书面许可【联】 |
| 本 Skill 定位 | **不作为自动化数据源**。允许：帮用户读**一屏**结果（截图）、把题名交给 L1 用 OpenAlex/Crossref 核 DOI。禁止：循环翻页、批量抓题录、爬 Cited by、用代理/轮换 IP 规避风控 |
| 语法 | `"精确短语"`、`OR`（大写）、`-排除`、`intitle:`、`author:`、`site:`、`filetype:`【联】 |
| 唯一价值 | 灰色文献 / 中文 / 学位论文收录更全，且比 OpenAlex 更早看到新文献 → 开放渠道查不到时让用户手动搜，或读一屏 |

---

## 不在表内的平台怎么处理

按同一套字段模板临时试：`entry / auth / search_box / results / detail / download / blockers`。
**硬要求**：没实测的字段留空或写「待实测」，不要凭经验填按钮文案；用户问"能不能用某平台"时答"可以试，但未验证"。
