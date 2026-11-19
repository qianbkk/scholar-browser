---
name: scholar-browser
slug: scholar-browser
displayName: 学术文献获取
summary: 宽泛发现 + 开放获取直取 + 浏览器协作，检索学术文献并自动归集到工作区
license: MIT
agent_created: true
display_name: 学术文献获取
display_name_en: Scholar Literature Fetcher
description: 学术文献检索与获取：从主题或 DOI 出发，先宽泛发现拿标识符，再开放获取直取 PDF（魔数校验），中文先试期刊官网，需登录时才用你自己的浏览器逐页操作，拿不到全文则回填题录与摘要；文件自动校验、去重、规范命名后归集到工作区。覆盖知网 CNKI、万方、维普、Google Scholar、Web of Science、PubMed/PMC、arXiv、ScienceDirect。**强触发**（单独出现即触发）：查文献、检索文献、搜论文、找文献、下载论文、下载文献、文献综述、文献归集、导出题录、OA 全文、浏览器取全文、这篇能不能下。**弱触发**（须与「文献/论文/期刊/全文/DOI」同句共现）：知网、CNKI、万方、维普、Web of Science、PubMed、arXiv、ScienceDirect、Google Scholar、高级检索、检索式、已登录浏览器。**不适用于**通用网页抓取、表单填写、站点测试、软件/视频/素材下载、商品社媒采集、专利与标准检索。
description_zh: 五通道分层路由的文献获取：发现 → 中文期刊官网 → 开放获取直取 → 浏览器协作 → 摘要回填，自动归集。无登录态时仅 OA 通道可用，订阅刊给题录+摘要+链接。
description_en: Five-channel literature workflow - discovery, Chinese journal sites, open-access fetch with magic-byte validation, browser-assisted retrieval, abstract backfill; auto-adopts into the workspace. Not for general scraping, form filling, or site QA.
version: 3.5.2
---

# 学术文献获取工作流（五通道分层路由）

铁律：**能直取就不开浏览器；开了就逐页真人式操作；文件先过魔数闸门；只认本次新增、不碰历史；不编造平台文案；失败必带 reason，不静默。**

`<skill_dir>` = 本文件所在目录（换机器按实际位置替换）。`<workspace>` = 工作区根目录。Python 用 PATH 上的 `python`（3.9+，仅标准库）。
**运行环境**：脚本层（L1–L2 / L1.6 / 归集）任何 agent 可用；**L3 段按 WorkBuddy 的 browser-use 写成**，换方案按 `browser-adapters.md` 映射；**L3 不可用按 §10 降级，不许静默失败**。

## 1. 定位与适用边界

本技能解决的不是"能不能搜到"，而是"**在你已有的访问权限内，把文献自动拿到手，并归集成可引用的库**"。

| 你的账号状态 | 能用到哪层 | 实际效果 |
|---|---|---|
| **有机构登录态**（校园网或 CARSI 漫游） | L1 → L3 全通 | 订阅刊与知网、万方可下全文。**设计主场景** |
| **已购个人订阅** | L1 → L3，按订阅范围 | 有权限的同左；无权限退回「题录 + 摘要 + 链接」 |
| **无机构、无订阅** | L1 / L1.5 / L2 / L1.6 | 英文 OA 可直取一部分（n=3 小样本实测 1/3，仅作量级参考）；中文限 OA 刊官网 PDF；订阅刊只给题录 + 摘要 + 链接 |

两句说清：本技能**不提供、不索取、不代替**任何机构权限，登录只在用户自己的浏览器里完成，不读取、不保存、不回显凭据（§4）。无登录态**不是失败，是降级**：文件拿不到，题录 / 摘要 / 链接必须给（§7）。

## 2. 五通道（按执行顺序，L1.6 兜底）

| 通道 | 做什么 | 用什么 |
|---|---|---|
| **L1 发现** | 主题 → 题名 + DOI/PMID/arXiv ID | `oa_fetch.py search` / `cite` + 开放 API + WebSearch + 中文站内检索 |
| **L1.5 中文期刊官网** | DOI → 官网真 PDF（**比知网好**） | `fetch_cn_journal.py` |
| **L2 直取** | 标识符 → 过闸门的 PDF | `oa_fetch.py resolve` / `fetch` / `batch` |
| **L3 浏览器协作** | 需登录或需交互的全文 | `mcp__browser__*` + 平台 SOP |
| **L1.6 摘要回填**（兜底） | 全文拿不到 → 补齐题录 + **摘要原文** | 按 `abstract-recovery.md` 手工走（不是脚本活） |

**判定顺序（不要颠倒）**

1. 已知 DOI/PMID/arXiv ID → 直接 L2。
2. 只有主题 → L1 拿标识符 → L2。
3. L2 失败看 `attempts[].reason`（§2.1）：要交互的（登录墙、校验页、订阅确认页）→ L3；页面可解析却没给 PDF（`html_landing`/`not_found_*`）→ 换候选，耗尽才 L3。
4. 目标是**知网 / 万方 / 维普** → 跳过 L2，直接 L3（中文订阅库直连无意义）。
5. 中文文献有 DOI → 先 L1.5 官网，再万方，最后知网：官网与万方给**真 PDF**，知网多给 KDH/CAJ（需阅读器）。
6. 确认拿不到全文、或只缺摘要 → L1.6 兜底。**先怀疑入口，不要先怀疑权限**。

**省时间**：先标识符再翻页；先题录后全文；**权限前置**（见到 `Get Access`、锁图标或跳登录即判无权限）；L2 失败把 reason 带进 L3，别重复踩同一个坑。

### 2.1 reason 码 → 下一步（**分流看 `attempts[]`，不是只看顶层 `reason`**）

顶层 `reason`：**单候选失败时就是该候选的真实原因**；**多候选全失败时才是 `no_candidate_passed`**，此时必须读 `reasons[]` / `attempts[].reason` 分流。

| reason | 含义 | 下一步 | 可重试 |
|---|---|---|---|
| `ok` | 通过闸门 | 完成，记 `via` | — |
| `html_landing` | 返回网页 | 换候选；耗尽 → L3 | 不重试 |
| `cloudflare_challenge` | JS 挑战页 | 直接 L3（真实浏览器常自动过） | 不重试 |
| `captcha` | 人机校验 | **停机**标「需人工」 | 不重试 |
| `login_wall` / `need_auth` | 登录页 / 401 | L3 | 不重试 |
| `paywall_landing` | 订阅页 | 有机构权限 → L3；无权限转正规渠道 | 不重试 |
| `forbidden_403` | 拒绝访问 | 停该条目记「需人工」 | **不重试** |
| `rate_limited_429` | 限流 | 退避一次再试；仍 429 → 停 | **1 次** |
| `not_found_404` / `server_error_*` | 失效 / 服务异常 | 换候选 | 不重试 |
| `not_pdf` / `not_pdf_octet` / `not_pdf_magic` / `json_error_body` | 拿到的不是 PDF | 换候选 | 不重试 |
| `too_large` / `partial_suffix` / `truncated_no_eof` / `size_mismatch` / `missing` | 文件不完整 | 重下一次；仍坏 → 换源 | **1 次** |
| `network_error:*` | 连接层（含 TLS 证书） | 换候选；全失败 → L3。证书错多为代理中间人，提示用户关代理，**不要自己关校验** | 不重试 |
| `no_candidate` / `no_candidate_passed` | 无 OA 位置 / 有候选全失败 | 前者直接 L3；后者**回头读 `reasons[]`** 按上表分流 | — |

## 3. 平台速查（细节在 `platforms-*.md`）

能出 PDF 的三条路：中文 → 官网（L1.5）＞ 万方 ＞ 知网；英文 OA → arXiv / PMC / Unpaywall（L2）；英文订阅 → SD 批量 ZIP 或机构 L3。**维普、Web of Science 已知不能自动化**，其余平台只作发现与核验，**不要当下载站用**。表外平台（SpringerLink、Wiley、IEEE、Scopus、读秀、百度学术、专利库等）**不在保证范围**：用户点名时按统一字段模板临时试，**不得声称已验证**。

## 4. 红线（完整版见 `limits.md`）

1. **凭据归用户**：登录只在用户自己的浏览器里完成，不读取、不保存、不回显任何凭据。
2. **尊重访问限制**：只获取公开可用的、或用户本人有权访问的内容；遇登录墙、校验页、订阅确认页即停该条目，转正规渠道。
3. **人工节奏**：逐篇检索、逐篇单击、串行、留间隔；API 侧串行 + 限速 + 缓存。
4. **遇阻停机**：访问受限、校验页、跳登录 → 停队列标「需人工」。**重试只允许两种**：429 退避 1 次、链路抖动 1 次；`403` 与校验页**不重试**。
5. **不误伤文件、不编造**：只处理本轮基线后新增 + 白名单 + 魔数通过的文件；没实测的文案/字段/URL 标「待实测」。
6. **浏览器需授权才启动**：用户说「启动我的浏览器 / 用浏览器下载 / 可以启动」时才启动；不 taskkill、不反复重启。**未获授权按 §10 交付，不得擅自开**。

## 5. 流水线

`init-baseline`（下载前必做，目录非系统默认时加 `--root`）→ **B 发现**（L1，`discovery.md` §2）→ **C 直取**（`fetch`，过闸门才落盘）→ **D 浏览器**（L3 逐篇单击）→ **E 归集**（`scan-new`→`adopt`→`verify`→`report`）→ **F 清场**（只关本轮新增页）。

开浏览器前先按 `runtime.md` §1 存基线再开新页（必须 `type: "extension"`）；顺序反了，收尾分不清哪些页是我开的。

## 6. 常用命令

```bash
# 诊断：配置实际生效位置 / 只读自检
python "<skill_dir>/scripts/oa_fetch.py" config
python "<skill_dir>/scripts/audit.py"

# L1 发现
python "<skill_dir>/scripts/oa_fetch.py" search --query "<关键词>" --from-year 2020 --limit 25 --out <dir>/q1.json
python "<skill_dir>/scripts/oa_fetch.py" cite --doi <种子DOI> --direction cited_by --limit 30

# 兜底交付（拿不到全文必跑）
python "<skill_dir>/scripts/oa_fetch.py" meta --doi <DOI> --format md

# L2 直取
python "<skill_dir>/scripts/oa_fetch.py" resolve --doi <DOI>
python "<skill_dir>/scripts/oa_fetch.py" fetch --doi <DOI> --out "<workspace>/文献/<主题>/xx.pdf"
python "<skill_dir>/scripts/oa_fetch.py" fetch --url "<pdf-url>" --out "<path>"
python "<skill_dir>/scripts/oa_fetch.py" check --file "<path>"

# 归集（scan-new 输出的 `plan` 字段就是下一步 --plan 的入参）
python "<skill_dir>/scripts/litadopt.py" init-baseline --workspace "<workspace>" [--root "<下载目录>"]
python "<skill_dir>/scripts/litadopt.py" scan-new --workspace "<workspace>" --target-dir "<workspace>/文献/<主题>" [--allow-unconfirmed]
python "<skill_dir>/scripts/litadopt.py" adopt --plan <plan> --workspace "<workspace>" --target-dir "<workspace>/文献/<主题>" [--move-sources]
python "<skill_dir>/scripts/litadopt.py" verify --workspace "<workspace>"
python "<skill_dir>/scripts/litadopt.py" report --workspace "<workspace>" --format table
```

批量与专项命令（`batch` / `fetch_cn_journal` / `checklist` / `sd_zip` / `ris_meta`）见 `commands.md`。

- **`scan-new` 对 L2 直取 / 手工放入的文件默认判 `manual_drop`（`selected=0`）**——这类文件没有浏览器下载记录。核对确由本轮产生后加 `--allow-unconfirmed` 重扫，不要手改 plan。
- **`adopt` 出现 `adopted=0` 且 `not_moved>0` 视为失败（退出码 3）**，不许当成功继续；`verify` 非 0、或 `report` 的会话不是本轮 `session_id`，同样按失败处理。
- `--move-sources` 把本次新增移入隔离区（可逆、有日志、可 `rollback`），**仅当用户明确说过「默认下载目录不留」**才用。**格式优先级 PDF > CAJ > KDH**，按魔数判真实格式（后缀不可信），不为换格式反复重下（每次下载都计配额，间隔 ≥3–5 秒）。

## 7. 交付标准：每篇都要给出「能自己继续」的东西

每篇无论拿到全文与否都要产出一条记录——**目的是让用户能自己继续，不是为了"下载成功"而下载**：

| 情况 | 交付内容 |
|---|---|
| **拿到 PDF** | 文件落盘 + 校验通过 + 记录（含 OA 状态、版本、来源、`via`） |
| **没拿到全文** | 题名、作者、来源、年份、DOI/PMID/arXiv ID、**摘要（有多少给多少）**、**至少一个可打开链接**、**`fail_reason`**。注：`meta` 的 `ok:true` 只代表题录可取，全文状态看 `fulltext` |

`fail_reason` 只取四值，不要自由发挥：`need_subscription` / `need_verify` / `need_institution` / `not_found`。

- **摘要优先级**：出版商/期刊落地页（最准）→ RIS 导出 → 中文官网 / 知网 DOI / cdmd / 镜像站 → OpenAlex → S2 → Crossref。全无则写「该库未提供摘要」+ 链接，**不编造**（`abstract-recovery.md`）。
- **「主要内容」不是摘要翻译**：压成"做了什么 + 什么方法 + 关键数字 + 对本课题何用"2–4 句；每条标来源；DOI 与卷期取自已核验清单。
- **判断标准：用户拿着这条记录能自己点开链接继续。** 只回一句"下不了"不合格。替代路径按序给：OA 副本 → 出版商/PubMed/arXiv 链接 → 同主题替代文献（说清替代了什么）→ 校园网 / CARSI / 文献传递 / 向作者索取。
- **落盘**：`<workspace>/文献/<主题>/`，命名 `NN_题名_作者_来源.{pdf|caj}`，序号接目录最大值，MD5 去重，同名不同内容不覆盖；状态与日志在 `<workspace>/.litadopt/`。**作者取不到写 `unknown`，不编造**（`resolve` 无作者，`meta` 有）。KDH/CAJ 须注明需官方阅读器。汇报区分「直取(L2)」与「浏览器(L3)」，并说明是否 OA、是否 preprint。

## 8. 按需加载（渐进式披露）

**任何任务先读 `ROUTER.md` + `limits.md`；之后一次任务最多再加载 3 个 reference。**

| 想做的事 | 读 |
|---|---|
| 判断能不能直下、要不要开浏览器 | `discovery.md` |
| 拿中文期刊真 PDF / 补中文摘要 | `platforms-cn-journal.md`、`abstract-recovery.md` |
| 开浏览器（基线、清场、代理、邮箱） | `runtime.md` |
| 归集报错 / 回滚 | `toolchain.md` §4–§5 |

其余（检索式、平台 SOP、分级标准、派子代理模板）见 `ROUTER.md` 路由表，**不要全量加载**。

## 9. 已知限制

- **L2 单篇时间预算 90 秒**：慢网下 `fetch` 可能长时间无输出（实测单篇 254 秒）。用外层超时 90 秒包住，超时记 `network_error:timeout` 并降级，**别把卡住当成还在跑**。
- **订阅型单篇 PDF 不能自动写盘**（进阅读器 → 系统另存为）→ 走 SD 批量 ZIP（`sd-batch.md`），失败最多重试一次。无 CAJViewer / caj2pdf → 真 CAJ 转不了；知网可能给 **KDH**，需官方阅读器。
- **摘要多是"渲染后才有"**：直接请求 ScienceDirect 被 403，部分站点 WAF 连渲染也过不去，只能交用户点一次。OA 站点也可能因 TLS 指纹被拒——L2 固有上限，不是 bug。
- `mcp__browser__*` 无下载管理与读本地文件能力，下载靠点击、文件侧交脚本。**浏览器段仅适配 WorkBuddy**。

## 10. 确定性出口（L3 不可用 / 部分失败时怎么收）

调用方**不该读中间步骤才知道发生了什么**。以下信号是契约：

| 情形 | 信号 |
|---|---|
| L3 不可用（无插件 / 未获启动授权 / 平台不支持） | 交付清单顶层写 `"degraded_to_l1_6": true`，`degraded_reason` 取 `no_browser` / `no_auth` / `unsupported`；仍要给完题录 + 摘要 + 链接 |
| 部分条目拿不到全文 | 该条 `ok: false` + `fail_reason` + `attempts[]` 原样保留 |
| 全部拿不到全文 | `"all_fulltext_failed": true`，每条仍必须给题录 + 摘要 + 链接 |
| 脚本层 | 退出码 `0` 全成功 / `3` 部分成功或待确认 / `4` 校验失败 / `2` 参数错 / `1` 其他；**非 0 不得当成功继续** |

一句话：**降级要出声，失败要带因，空结果不算成功。**

版本与变更历史见 `CHANGELOG.md`。
