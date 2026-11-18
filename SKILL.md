---
name: scholar-browser
slug: scholar-browser
displayName: 学术文献获取
summary: 宽泛发现 + 开放获取直取 + 浏览器协作，检索学术文献并自动归集到工作区
license: MIT
agent_created: true
display_name: 学术文献获取
display_name_en: Scholar Literature Fetcher
description: 学术文献检索与获取工作流，五通道分层路由：先宽泛发现（开放学术 API + 通用搜索）拿到题名与 DOI/PMID/arXiv ID，再尝试开放获取直取 PDF（魔数闸门校验），未成功则在用户自己的浏览器（Edge/Chrome 扩展）中按平台流程逐页操作，覆盖知网 CNKI、万方、维普、Google Scholar、Web of Science、PubMed/PMC、arXiv、ScienceDirect；拿不到全文时回填题录与摘要；文件自动校验、去重、规范命名后归集到工作区。**适用人群**：本技能的完整能力面向**有机构登录态**的用户（在校学生/教师、科研院所人员，校园网或 CARSI 漫游）以及**已购个人订阅**者——此时订阅刊与知网/万方全文均可获取；**无机构登录态**的普通用户只能使用开放获取通道，英文约 1/3 可直取、中文限开放获取刊，订阅刊仅给题录+摘要+可打开链接。**不代替、不索取任何机构权限**，登录只在用户自己的浏览器里完成。**触发词分两级**：**强触发**（单独出现即触发）——查文献、检索文献、搜论文、找文献、下载论文、下载文献、文献综述、文献归集、导出题录、OA 全文、浏览器取全文、这篇能不能下；**弱触发**（须与“文献/论文/期刊/全文/DOI”同句共现）——知网、CNKI、万方、维普、Web of Science、PubMed、arXiv、ScienceDirect、Google Scholar、高级检索、检索式、已登录浏览器。**不适用于**通用网页抓取、表单填写、站点测试、软件/视频/素材下载、商品或社媒数据采集、专利与标准检索（那类需求改用通用浏览器技能）。
description_zh: 五通道分层路由的学术文献获取：发现 → 中文期刊官网 → 开放获取直取 → 浏览器协作 → 摘要回填，自动归集到工作区。完整能力面向有机构登录态（学生/教师/科研院所）或已购订阅的用户；无机构登录态时仅开放获取通道可用，订阅刊给题录+摘要+链接。
description_en: Five-channel literature workflow - broad discovery, Chinese journal sites, open-access direct fetch with magic-byte validation, browser-assisted retrieval in the user's own session, then abstract backfill; auto-adopts downloads into the workspace. Full coverage assumes institutional access (campus network or CARSI) or a personal subscription; without it only open-access channels apply, and subscription articles are delivered as metadata + abstract + working links. Not for general web scraping, form filling, site QA, or product/social scraping.
version: 3.5.1
---

# 学术文献获取工作流（五通道分层路由）

铁律：**能直取就不开浏览器；开了浏览器就逐页真人式操作；任何文件先过魔数闸门；只按本次新增识别文件、绝不碰历史文件；不编造平台文案。**

`<skill_dir>` = 本文件所在目录（用户级装在 `~/.workbuddy/skills/scholar-browser`，换机器按实际位置替换，**不要照抄示例路径**）。
`<workspace>` = 当前工作区根目录。Python 用 PATH 上的 `python`（3.9+，仅标准库）。
**运行环境**：脚本层（L1 / L1.5 / L1.6 / L2 / 归集）任何 agent 都可用；**L3 浏览器段按 WorkBuddy 的 browser-use 插件写成**，其他方案未适配——工具名不同时按 `browser-adapters.md` 映射（7 个动作 + 降级）。

## 1. 定位与适用边界（先看这张表，决定值不值得用）

本技能解决的不是"能不能搜到"，而是"**在你已有的访问权限内，把文献自动拿到手，并归集成可引用的库**"。

| 你的账号状态 | 能用到哪层 | 实际效果 |
|---|---|---|
| **有机构登录态**（在校学生/教师、科研院所；校园网或 CARSI 漫游） | L1 → L3 全通 | 订阅刊（ScienceDirect / Wiley / Springer 等）与知网、万方可下全文。**这是本技能设计的主要场景，功能最完整** |
| **已购个人订阅**（学会会员、单刊订阅） | L1 → L3，按订阅范围 | 有权限的刊同上；无权限的刊退回「题录 + 摘要 + 链接」 |
| **无机构、无订阅**（独立研究者、社会用户） | 仅 L1 / L1.5（开放获取刊）/ L2 / L1.6 | 英文约 **1/3** 可直取 OA 全文（3 DOI 实测 33%，与第三方 123-DOI 的 33%/39% 同量级）；中文限开放获取刊官网 PDF；**订阅刊一律只给题录 + 摘要 + 可打开链接** |

两句必须说清的话：

- 本技能**不提供、不索取、不代替**任何机构权限。登录只在用户自己的浏览器里完成，不读取、不保存、不回显凭据（§4）。
- 无登录态时**不是失败，是降级**：文件拿不到，但题录 / 摘要 / 至少一个可打开链接必须给（§7）。

## 2. 五通道（按执行顺序，L1.6 兜底）

| 通道 | 做什么 | 用什么 | 何时用 |
|---|---|---|---|
| **L1 发现** | 主题 → 题名 + DOI/PMID/arXiv ID | `oa_fetch.py` 的 `search` / `cite` + 开放 API + WebSearch + 中文站内检索 | 一开始，永远先做 |
| **L1.5 中文期刊官网** | DOI → 官网真 PDF（**比知网好**） | `fetch_cn_journal.py` | 中文期刊 DOI 到手就试，早于 L3 |
| **L2 直取** | 标识符 → 过闸门的 PDF | `oa_fetch.py` 的 `resolve` / `fetch` / `batch` | 拿到 DOI 立刻试 |
| **L3 浏览器协作** | 需登录或需交互的全文 | `mcp__browser__*` + 平台 SOP | L2 失败且原因指向"需浏览器" |
| **L1.6 摘要回填**（兜底） | 全文拿不到 → 补齐题录 + **摘要原文** | 按 `abstract-recovery.md` 手工走（不是脚本活） | 任何阶段确认拿不到全文后 |

**判定顺序（不要颠倒）**

1. 已知 DOI/PMID/arXiv ID → 直接 L2。
2. 只有主题 → L1 拿标识符 → L2。
3. L2 失败看 `reason`：要交互的（登录墙、校验页、订阅确认页）→ L3；页面可解析却没给 PDF（`html_landing`/`not_found`）→ 换候选再试，耗尽才 L3。
4. 目标是**知网 / 万方 / 维普** → 跳过 L2，直接 L3（中文订阅库直连无意义）。
5. 中文文献有 DOI → 先 L1.5 官网，再万方，最后知网：官网与万方给**真 PDF**，知网多给 KDH/CAJ（需阅读器）。
6. 确认拿不到全文、或只缺摘要 → L1.6 兜底。**先怀疑入口，不要先怀疑权限**。

**省时间的四条**：先标识符后翻页；先题录后全文；**权限前置**（先看机构名 / `View PDF` / 无锁图标，见到 `Get Access` 或跳登录即判无权限，不反复试探）；L2 失败要把 `reason` 带进 L3，别重复踩同一个坑。

## 3. 平台速查（细节在 `platforms-*.md`）

**能出 PDF 的三条路**：中文 → 期刊官网（L1.5）＞ 万方（给真 PDF）＞ 知网（多 KDH/CAJ）；英文 OA → arXiv / PMC / Unpaywall（L2）；英文订阅 → SD 批量 ZIP 或机构 L3。

**已知不能自动化**：维普（DOM/CUA 持续超时）、Web of Science（输入写不进）。**其余平台只作发现与核验，不要当下载站用**。

表外平台（SpringerLink、Wiley、IEEE、Scopus、读秀、百度学术、专利库等）**不在保证范围**：用户点名时按统一字段模板临时试，**不得声称已验证**。等级 A = 真实点击实测通过 / B = 入口字段有依据但流程不完整 / C = 仅收录；逐平台实到哪一步见 `ROUTER.md` 平台映射与对应平台文件。

## 4. 红线（完整版见 `limits.md`）

1. **凭据归用户**：登录只在用户自己的浏览器里完成，不读取、不保存、不回显任何凭据。
2. **尊重访问限制**：只获取公开可用的、或用户本人有权访问的内容；遇登录墙、校验页、订阅确认页即停止该条目，转正规渠道（校园网 / 图书馆文献传递 / OA 版本 / 向作者索取）。
3. **人工节奏**：逐篇检索、逐篇点击、串行、留间隔；API 侧串行 + 限速 + 缓存。
4. **遇阻停机**：访问受限、限流、跳登录页 → 停队列标「需人工」，同一动作最多重试一次。
5. **不误伤文件、不编造**：只处理本轮基线后新增 + 白名单 + 魔数通过的文件；没实测的文案/字段/URL 一律标「待实测」。
6. **浏览器需授权才启动**：用户说「启动我的浏览器 / 用浏览器下载 / 可以启动」时才启动。启动不改变前 5 条；**不 taskkill、不反复重启**。

## 5. 流水线

| 阶段 | 执行者 | 动作 |
|---|---|---|
| A 基线 | 脚本 | `init-baseline` — **任何下载前必做** |
| B 发现 | AI | L1：按 `discovery.md` §2 选渠道 → 题名 + 标识符 → Crossref 核验 |
| C 直取 | 脚本 | L2：`fetch` → 过闸门才落盘 |
| D 浏览器 | AI + 浏览器 | L3：按平台 SOP 逐篇单击 → 核验落盘 |
| E 归集 | 脚本 | `scan-new` → `adopt` → `verify` → `report` |
| F 清场 | AI + 浏览器 | **只关本轮新增的标签页**，用户原有页一律不动（`runtime.md` §1） |

**固定开场（每次任务重新取标识）**：`browsers_list → browser_info → user_open_tabs → snapshot 存基线 → tabs_new`。
必须选 `type: "extension"`（带真实登录态）；内置无登录态实例不可用。**取到 `user_open_tabs` 就立刻存基线再开新页**——顺序反了，收尾分不清哪些页是我开的。

## 6. 常用命令

```bash
# 诊断与自检
python "<skill_dir>/scripts/oa_fetch.py" config          # 每项配置实际生效的位置与来源
python "<skill_dir>/scripts/audit.py"                     # 只读自检，一个命令出结论

# L1 发现
python "<skill_dir>/scripts/oa_fetch.py" search --query "<关键词>" --from-year 2020 --limit 25 --out <dir>/q1.json
python "<skill_dir>/scripts/oa_fetch.py" cite --doi <种子DOI> --direction cited_by --limit 30

# L2 直取
python "<skill_dir>/scripts/oa_fetch.py" resolve --doi <DOI>
python "<skill_dir>/scripts/oa_fetch.py" fetch --doi <DOI> --out "<workspace>/文献/<主题>/xx.pdf"
python "<skill_dir>/scripts/oa_fetch.py" batch --list <DOI清单> --out-dir "<workspace>/.workbuddy/tmp/oa-batch" --interval 2
python "<skill_dir>/scripts/oa_fetch.py" check --file "<path>"

# L1.5 中文期刊官网真 PDF
python "<skill_dir>/scripts/fetch_cn_journal.py" --csv "<workspace>/文献/00_索引与报告/文献总清单.csv" --dest "<workspace>/文献/中文期刊全文-官网PDF" --out <dir>/cn.json

# 取不到 → 可点击清单，交用户手动另存
python "<skill_dir>/scripts/oa_fetch.py" checklist --list <DOI清单> --out "<workspace>/文献/待下载清单.md"

# 订阅刊批量 ZIP 导入（流程见 sd-batch.md） / RIS 题录+摘要
python "<skill_dir>/scripts/sd_zip.py" --zip "<下载目录>/ScienceDirect_articles_*.zip" --target-dir "<workspace>/文献/<主题>" [--dry-run]
python "<skill_dir>/scripts/ris_meta.py" --ris "<下载目录>/ScienceDirect_citations_*.ris" --md "<workspace>/文献/导出题录与摘要.md"

# 归集
python "<skill_dir>/scripts/litadopt.py" init-baseline --workspace "<workspace>"
python "<skill_dir>/scripts/litadopt.py" scan-new --workspace "<workspace>" --target-dir "<workspace>/文献/<主题>"
python "<skill_dir>/scripts/litadopt.py" adopt --plan <plan> --workspace "<workspace>" --target-dir "<workspace>/文献/<主题>" [--move-sources]
python "<skill_dir>/scripts/litadopt.py" verify --workspace "<workspace>"
python "<skill_dir>/scripts/litadopt.py" report --workspace "<workspace>" --format table
```

`--move-sources` 把本次新增文献移入隔离区（可逆、有日志、可 `rollback`），**仅当用户明确说过「默认下载目录不留」**才用；否则先出清单请确认。**格式优先级 PDF > CAJ > KDH**，按魔数判真实格式（后缀不可信），**不为换格式反复重下**（每次下载都计配额，间隔 ≥3–5 秒）。

## 7. 交付标准：每篇都要给出「能自己继续」的东西

**这是本技能的目的，不是为了"下载成功"而下载。** 每篇无论拿到全文与否都要产出一条记录：

| 情况 | 交付内容 |
|---|---|
| **拿到 PDF** | 文件落盘 + 校验通过 + 记录（含 OA 状态、版本、来源、`via`） |
| **没拿到全文** | 题名、作者、来源、年份、DOI/PMID/arXiv ID、**摘要（有多少给多少）**、**至少一个可打开链接**、**为什么没拿到**（需订阅 / 需校验 / 需机构 / 找不到） |

- **摘要优先级**：出版商/期刊落地页（原文，最准）→ RIS 导出 → 中文走期刊官网 / 知网 DOI / 知网 cdmd / 镜像站 → OpenAlex → S2 → Crossref。全无则如实写「该库未提供摘要」+ 链接，**不编造**。打法见 `abstract-recovery.md`。
- **「主要内容」不是摘要翻译**：压成"做了什么 + 什么方法 + 关键数字 + 对本课题何用"的 2–4 句；每条摘要标来源；**DOI 与卷期取自已核验清单，不凭印象写**。
- **判断标准：用户拿着这条记录能自己点开链接继续。** 只回一句"下不了"不合格。替代路径按序给：OA 副本 → 出版商/PubMed/arXiv 链接 → 同主题替代文献（说清替代了什么）→ 校园网 / CARSI / 文献传递 / 向作者索取。
- **落盘规范**：`<workspace>/文献/<主题>/`，命名 `NN_题名_作者_来源.{pdf|caj}`，序号接目录最大值，MD5 去重，同名不同内容不覆盖；状态与日志在 `<workspace>/.litadopt/`。汇报要区分「直取(L2)」还是「浏览器(L3)」，并说明是否 OA、是否 preprint。

## 8. 按需加载（渐进式披露）

**任何任务先读 `ROUTER.md` + `limits.md`；之后一次任务最多再加载 3 个 reference。** 高频四条：

| 想做的事 | 读 |
|---|---|
| 判断能不能直下、要不要开浏览器 | `discovery.md` |
| 拿中文期刊真 PDF / 补中文摘要 | `platforms-cn-journal.md`、`abstract-recovery.md` |
| 开浏览器（基线、清场、代理、邮箱） | `runtime.md` |
| 全文拿不到但要写清"讲了什么" | `abstract-recovery.md` |

其余（检索式、各平台 SOP、订阅刊批量、分级标准、派子代理模板）见 `ROUTER.md` 的路由表，**不要全量加载**。

## 9. 已知限制（完整版见 `limits.md`）

- **订阅型单篇 PDF 不能自动写盘**（进阅读器 → 系统另存为）→ 走 SD 批量 ZIP（`sd-batch.md`）；批量通道随站点/账号状态变化，失败最多重试一次。
- 无 CAJViewer / caj2pdf → 真 CAJ 转不了；知网可能给 **KDH**，需官方阅读器。脚本只用魔数判格式。
- **摘要是"渲染后才有"的内容**：直接请求 ScienceDirect 被 403 拦下；部分站点 WAF 挑战页连渲染抓取也过不去，只能交用户点一次。万方与部分镜像站有人机校验，中文摘要优先换百度学术、维普高校镜像等转载源（`abstract-recovery.md` §6）。
- 开放获取站点也可能因 TLS 指纹被拒（L2 固有上限，不是 bug）；`mcp__browser__*` 无下载管理与本地读文件能力，下载靠点击、文件侧全交脚本。
- **浏览器段仅适配 WorkBuddy**，换方案需自行映射（`browser-adapters.md`）；只对 §3 提到的平台负责。

版本与变更历史见 `CHANGELOG.md`。
