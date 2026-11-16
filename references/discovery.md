# 三级路由：宽泛发现 → 直取 → 登录态兜底

> 需要"找文献"、判断"这篇能不能直接下"、或决定"要不要开浏览器"时读本文件。
> 依据标签见 `limits.md` §4。**本文件所有"实测"均来自 2026-11-13 本机 `oa_fetch.py` 实跑**。

## 0. 为什么不是"全都用浏览器"

用登录态浏览器逐页操作，一篇约 6–10 次动作，慢、易被风控、DOM 结构一变就失效。
但反过来"全靠 API/直链"也做不到：OA 理论上限约 28%–50%，而**端到端直链成功率明显更低**。

本机 3 个真实 DOI 实测（2026-11-13）:

| DOI | OpenAlex OA 状态 | 结果 | 失败原因 |
|---|---|---|---|
| `10.48550/arXiv.1706.03762` | 仓储版 | **成功** 2.21 MB，`%PDF-1.5`，1 次候选命中 | — |
| `10.7717/peerj.4375` | gold | 失败 | PMC `/pdf/` 返回 HTML；doi.org→peerj 被 Cloudflare 403 |
| `10.1038/nature14539` | green | 失败 | `citation_pdf_url` 指向文章页；OA url 连接失败 |

**结论：3 个里 1 个能直取（33%），与第三方 123-DOI 实测 33%/39% 同量级【联·二手】。**

**开代理后复测（2026-11-13，`--proxy http://127.0.0.1:<用户端口>`）：结果没变，仍是 1/3。**
- PeerJ：PMC 路径从 `html_landing` 变成 **`captcha`**，doi.org→peerj 仍是 `cloudflare_challenge`
- Nature：仍是 `html_landing`，另一条 OA 位置报 `SSLCertVerificationError`（代理做了 TLS 中间人）

→ **失败原因是站点反自动化（验证码 / Cloudflare / TLS 指纹），不是网络不可达。代理能救"打不开的站"，救不了"不让你程序下载的站"。** 所以看到 L2 失败别以为是网络问题去反复重试。

所以正确结构是三层，不是二选一：能直取就直取，直取失败**带着失败原因**回浏览器。

## 1. 三层分工

| 层 | 做什么 | 工具 | 成本 |
|---|---|---|---|
| **L1 宽泛发现** | 主题/一句话 → 题名 + DOI/PMID/arXiv ID | WebSearch + 开放 API（OpenAlex/Crossref/S2）+ 中文站内检索 | 低，可批量 |
| **L2 直接获取** | 标识符 → 过闸门的 PDF | `scripts/oa_fetch.py` | 低，一次几秒 |
| **L3 登录态兜底** | 需要机构权限/交互/验证的全文 | `mcp__browser__*` + `platforms-*.md` | 高，6–10 动作/篇 |

**先 L1/L2，失败才 L3。** 不要一上来就开浏览器翻页——那是最贵的路径。

## 2. L1 宽泛发现：用什么、别用什么

### 2.1 渠道优先级

| 顺序 | 渠道 | 怎么用 | 依据 |
|---|---|---|---|
| 1 | **OpenAlex** | `oa_fetch.py search` 默认用它 | 【实】本机直连可通；**但已改为按出口 IP 共享免 key 日额度**，额度耗尽返回 429（`$0 remaining; resets at midnight UTC`）。`search` 已内置**自动降级 Crossref**（输出 `source=crossref` + `fallback_from`）。要稳定用请配 `SCHOLAR_OPENALEX_KEY`（免费注册） |
| 2 | **Crossref** | DOI 权威元数据核验（题名/作者/年/卷期），不用于主题发现 | 【联】 |
| 3 | **Semantic Scholar** | 引文滚雪球（`/citations`、`/references`）、TLDR；无 key 易 429 | 【联】 |
| 4 | **PubMed / Europe PMC / arXiv** | 生物医学、预印本的领域内检索，均免费无 key | 【联】 |
| 5 | **通用 WebSearch**（`filetype:pdf`、`site:`、精确题名引号） | 兜底找作者主页/机构库/课题组 PDF | 【联】 |
| 6 | **中文站内检索**（知网/万方/维普） | 中文文献**必须**走这里，开放渠道对中文覆盖弱 | 【经】 |
| — | **Google Scholar** | **只作人工/极低频核对**，见 2.3 | 【联】 |

### 2.2 L1 必查的四个坑

1. **幻觉题名**：AI/摘要生成的引用常有作者、卷期、页码错误 → 拿到候选必须用 Crossref 核一遍。
2. **DOI 错配**：某源查无 ≠ 不存在（只是该源没收录）→ 换源再查，别急着否定。
3. **版本混淆**：preprint / accepted manuscript / 正式版（VoR）三回事，年份可能差一年 → 下载后看首页版本标识，报给用户。
4. **付费墙伪装成 OA**：`citation_pdf_url` 可能指向文章页而不是 PDF（Nature 实测就是），必须过闸门。

### 2.3 Google Scholar 的边界（重要）

- **无官方 API**，robots 明确禁抓 `/scholar`、`/search`，ToS 要求自动化须获书面许可【联】。
- 自动化抓取 = 速率监控 + CAPTCHA + IP 封禁，且**无版本化变更通知**，页面结构随时变【联】。
- → 本 Skill **不把 GS 作为自动化数据源**。可做的是：用户在浏览器里自己看，或极低频人工核对一两屏。
- GS 唯一不可替代的价值是"灰色文献/中文/学位论文收录更全"，遇到开放渠道查不到的中文文献时，可让用户手动搜一次。

### 2.4 怎么做到「全面」而不是查一遍就交差

单次检索必然漏。要"全面"，靠的是**多角度交叉**，不是把同一个词搜十遍：

1. **一题至少三个源**：OpenAlex（覆盖最广）+ Crossref（DOI 权威）+ 一个领域源（PubMed / arXiv / CNKI）。
2. **引文滚雪球**（最有效的一步，替代 GS 的 Cited by）——**用 `oa_fetch.py cite`**，别手写 API：
   - 先定 3–5 篇**种子文献**（最相关的、或综述）
   - 往回：`cite --direction references` → 找奠基工作
   - 往前：`cite --direction cited_by` → 找最新进展（实测一篇 2023 的种子能拉出 46 条 2026 年的后续工作）
   - 一轮通常能把候选从几篇扩到几十篇，且相关性远高于关键词检索
3. **换词不换题**：中英各一套、同义词（blast/explosion/shock wave；fragment/fragmentation）、上下位词（damage → failure mode / residual capacity）。
4. **中文必须单独检索**：开放 API 对中文期刊覆盖弱，中文文献走知网/万方站内检索，别指望 OpenAlex。
5. **补灰色文献**：预印本（arXiv/bioRxiv）、学位论文（CNKI 学位库）、会议论文、机构库、作者主页——这些常常是唯一能免费拿到的版本。
6. **记已检索清单**：(源, 检索式/DOI) 记下来，跨轮不重复；同一篇在多源出现按 DOI 归一。

**判断"够不够全"的实用标准**：新查的 20 条里如果没有一条是之前没见过的，基本就饱和了；连续两轮都这样，可以停。

### 2.5 检索式怎么构造（2026-11-13 实测教训）

`oa_fetch.py search` 走 OpenAlex，词怎么组直接决定信噪比。实测踩过的坑：

| 坑 | 现象 | 正确做法 |
|---|---|---|
| **长组合词** | 五六个词塞进一个 query，只回个位数；拆成「方法词组」+「场景词组」分别跑，各回上千条 | **方法词与场景词分开搜**，各自取候选后取交集 |
| **一词多义** | 同一个词在另一学科里指完全不同的概念（如 `coupling` 在工程与物理里义项不同），把无关文献全搜进来 | 加 `--field title_abstract`，并在词里带上义项（`<词A> and <词B>` 这类双词锚定） |
| **全字段搜索太宽** | 两个常用词全字段检索命中上千条，混进大量同名不同义的领域 | 用 `--field title_abstract`；必要时 `--field title` |
| **过度限定** | 题摘里要求四五个词全中 → 0 条 | 先跑宽词（两三个），再用结果筛 |
| **只跑一次就交差** | 单组最多 50 条，必然漏 | 见 §2.4；另按年份分箱（老文献按被引、新文献按时间） |

**跑完必须做的一步**：把多组结果合并去重，按"命中该主题的词数"和"是否近年"打分分桶。一组结果里反复出现的条目才是核心，只出现一次的通常是噪音。

**验证是否搜全**：补 2–3 组近义词（`synergistic loading`、`multi-hazard`、`multiple damage mechanisms`）。如果新增条目占比很低（实测 201→203），说明接近饱和；如果大幅增长，说明主检索式漏了维度。

## 3. L2 直接获取：`oa_fetch.py`

```bash
# 0) 只要题录 + 摘要 + 可打开链接（下载前判断值不值得下；下载不了时用它兜底）
python "<skill_dir>/scripts/oa_fetch.py" meta --doi <DOI> --format md

# 1) 先看有哪些候选（不下载）
python "<skill_dir>/scripts/oa_fetch.py" resolve --doi 10.7717/peerj.4375

# 2) 逐个尝试，第一个过闸门的落盘
python "<skill_dir>/scripts/oa_fetch.py" fetch --doi <DOI> --out "<workspace>/文献/<主题>/xx.pdf"

# 3) 已知直链（如从页面拿到的 PDF URL）
python "<skill_dir>/scripts/oa_fetch.py" fetch --url "<pdf-url>" --out "<path>"

# 4) 只探测不落盘 / 校验已有文件
python "<skill_dir>/scripts/oa_fetch.py" probe --url "<url>"
python "<skill_dir>/scripts/oa_fetch.py" check --file "<path>"
```

**公共参数**（所有子命令都支持）：`--proxy <url>` / `--no-proxy` / `--email <mail>`。
不传 `--proxy` 时跟随 `HTTPS_PROXY` / `HTTP_PROXY` 环境变量；Skill 不内置任何端口。

### 3.0 `meta`：拿不到全文时的兜底盘

`meta` 只查元数据，**不下全文**，输出：
- 题名 / 作者 / 年份 / 期刊卷期页 / 类型 / 被引数 / **OA 状态**
- **摘要**（来源优先级：Crossref JATS → OpenAlex 倒排索引重建 → Semantic Scholar → PubMed XML）
- **可打开链接**（OA PDF、OA 页面、DOI 解析、PubMed、PMC、arXiv、Google Scholar 人工入口），并**区分"开放获取"与"可能需订阅"**——不要把所有链接都叫 OA

实测：Nature 那篇（订阅刊）能拿到完整摘要 + 7 个链接；即使一个字都下不到，用户也能自己点开继续。
**这是交付底线，不是可选项**（`SKILL.md` §7）。

### 3.1 闸门（为什么不能看后缀）

文件名后缀只说明"你打算怎么存"，不说明服务器给了什么。服务器可以 200 返回登录页、验证码、JSON 错误，浏览器照样存成 `.pdf`。

`oa_fetch.py` 的判定顺序（每一步都实测过）：

1. `status` 必须 2xx（401/403/429/404/5xx 各有独立 reason）
2. `Content-Type` 只能是 `application/pdf` 或 `application/octet-stream`（后者不否定）
3. **前 5 字节必须是 `%PDF-`** ← 硬闸门
4. `Content-Length` 与实际字节数一致
5. 落盘后再查尾部 `%%EOF` + 大小（< 5 KB 直接判失败）
6. 只有全部通过才 `os.replace()` 成正式文件；否则删 `.part`，**不留垃圾**

### 3.2 reason 码 → 下一步做什么

| reason | 含义 | 动作 |
|---|---|---|
| `ok` | 通过 | 完成，记录 `via` |
| `html_landing` | 返回的是网页 | 下一个候选；耗尽 → L3 |
| `cloudflare_challenge` | JS 挑战（"Just a moment"） | **直接 L3**，不要重试 |
| `captcha` | 人机验证 | 停，交人工 |
| `login_wall` | 登录页 | L3（用户登录态可解） |
| `paywall_landing` | 订阅页 | L3（机构权限可解）或转正规渠道 |
| `forbidden_403` / `rate_limited_429` | 拒绝/限流 | 429 退避一次；持续 → L3 |
| `need_auth` | 401 | L3 |
| `not_found_404` / `server_error_*` | 链接失效/服务异常 | 换候选 |
| `too_small_*` / `truncated_no_eof` / `size_mismatch` | 下载不完整 | 重新下，或换源 |
| `network_error:*` | 连接层（URLError / SSLCertVerificationError 等） | 换候选；`SSLCertVerificationError` 多为代理做 TLS 中间人 → 提示用户换 HTTP 代理或关证书替换，**不要自己关校验**；全失败 → L3 |
| `no_candidate` | 没有任何 OA 位置 | 直接 L3 |

### 3.3 已知盲区（别当成失败判据）

- `page_estimate` 对压缩流 PDF 常返回 0，**不能**据此判"不是全文"。
- 无 `SCHOLAR_EMAIL` 时跳过 Unpaywall，只用 OpenAlex → 候选会变少。设了更好（Unpaywall 要求真实邮箱，占位会被 422 拒）【联】。
- 完全 OA 站点也可能因 TLS 指纹被拒（MDPI/PLOS/PMC 均有报告）【联·二手】→ 这是 L2 的固有上限，不是 bug。

## 4. L3 触发判定表（可编码）

| 观测信号 | 判定 | 动作 |
|---|---|---|
| 域名 ∈ 知网 / 万方 / 维普 / 读秀 | 中文订阅库，直连无意义 | **不做 L2，直接 L3** |
| `is_oa=false` 且无任何 OA 副本 | 付费墙 | L3 |
| L2 返回 `cloudflare_challenge` / `captcha` | 需真实浏览器 | L3（captcha 还需人工）。**注意：JS 挑战在真实浏览器里常能自动通过，所以回 L3 不等于失败** |
| L2 返回 `login_wall` / `need_auth` | 需会话 | L3 |
| PDF 只在 viewer 内、需点保存 | 需交互 | L3（ScienceDirect 典型） |
| 候选耗尽且全为 `html_landing` | 无直链 | L3 |
| 429 且无挑战页 | 限流 | **先退避，不立即 L3** |

**到 L3 之后先做权限判读，再决定要不要动手**（实测：不同站可读性不同）：

| 页面看到 | 判定 | 动作 |
|---|---|---|
| `View PDF` + href 是 PDF 端点（如 ScienceDirect 的 `pdfft?pid=...main.pdf`） | 有权限 | **把 href 交给 L2 `fetch --url`**，省掉 viewer 两步 |
| `View PDF` 可读（arXiv `/abs`、SD） | 有权限 | 同上；只有拿不到 href 时才点 |
| `Get Access` / 锁图标 / `查阅权限` | 本馆未订阅 | **不反复试探**，转正规渠道（CARSI / 文献传递 / OA 版本 / 向作者索取） |
| 机构名可见（SD 的 `... Institutional Access` 按钮、CNKI 右上角校名、维普 `qikan` 子站） | 登录态有效 | 继续 |
| 机构名缺失 | **不能直接判失效**（WoS 未登录也能进检索页且不显示机构名） | `login_valid=unknown`，要看结果页是否出现「出版商处的全文」 |
| 截图空白 | **不能判无权限**（SD 详情页、WoS 是 `render_blank`） | 改读 DOM；DOM 也没内容才算失败 |
| 整站 `ERR_CONNECTION_TIMED_OUT` | 网络不可达 | 记 `timeout`，**不要记 `blocked`**。**先试代理**（`--proxy` / `HTTPS_PROXY`）：实测 GS、PubMed 都是直连失败、代理正常 |

## 5. 借鉴了哪些现成工具的机制（客观取舍）

调研了 Elicit / Consensus / Connected Papers / Scite / ResearchRabbit / Zotero 等，结论分三档：

**吸收了（低成本可复刻）**
- **多源并行 + 元数据归一 + 双源核验**（Elicit/Consensus 的发现底座本就是 OpenAlex/S2，不必经产品层）→ 已落在 `resolve` 的多源候选与去重。
- **引文滚雪球**（S2 `/citations`+`/references`，或 OpenAlex `cites:`）替代 GS 的 Cited by → 想扩候选时用，不要爬 GS。
- **Zotero 式 resolver 链**：落地页 `citation_pdf_url` → OA 索引 → 直链 → 引擎兜底 → 已落在候选排序里。
- **统一魔数闸门** → 已落在 `oa_fetch.py`。

**改造后借鉴**
- Consensus 的"宽召回 → 粗排 → top N 精读"：把"期刊影响力"换成**开题相关性 + 是否有全文 + 版本 + 语种**，精读交人工。
- Elicit 的证据表：降级成本地轻量表（题名/DOI/年/来源/OA 状态/版本/是否拿到全文），不做大规模抽取。

**不吸收**
- **Scite**：依赖 44+ 出版社授权全文 + 1.6B 引用语句 + 分类器，专有数据无法复刻，且对"定位并下载"无直接增益。
- **Elicit 的 PRISMA 全流程 / Consensus 的授权全文**：需重算力与付费授权，超出范围。
- **GS Cited by 直连抓取**：违反 ToS + 封 IP 风险，收益不抵代价。

## 6. 每篇文献要记的账（便于事后核对）

不是另建文档，就记在 `litadopt` 的 plan / 报告字段里：

`题名 | DOI | 年 | 来源 | oa_status | 版本 | 摘要(来源+长度) | 获取路径(L1/L2/L3) | via | 校验结果 | 失败原因 | 可打开链接数`

**没拿到全文也必须填满前 7 项**——这是用户能不能自己继续的关键（`SKILL.md` §7）。

汇总指标：L2 命中率、L3 回退率、403/429 次数、非全文检出数、人工确认次数。
**按语种/学科分组看**——OA 率差异极大，不分组的总平均会误导。
