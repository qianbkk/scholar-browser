---
name: scholar-browser
display_name: 学术文献获取
display_name_en: Scholar Literature Fetcher
description: 学术文献检索与获取工作流，三级路由：先宽泛发现（开放学术 API + 通用搜索）拿到题名与 DOI/PMID/arXiv ID，再尝试 OA 直取 PDF（魔数闸门校验），失败才用用户真实浏览器登录态（Edge/Chrome 扩展）在知网 CNKI、万方、维普、Google Scholar、Web of Science、PubMed/PMC、arXiv、ScienceDirect 上逐页操作获取全文；下载文件自动校验、去重、规范命名后归集到工作区。触发词：查文献、检索文献、搜论文、找文献、下载论文、下载文献、能不能下、OA 全文、高级检索、检索式、知网、CNKI、万方、维普、Web of Science、PubMed、arXiv、ScienceDirect、Google Scholar、机构登录态、复用浏览器登录、文献归集、下载目录不留。
description_zh: 宽泛发现 + OA 直取 + 真实浏览器登录态兜底，检索与下载学术文献并自动归集到工作区。
description_en: Three-tier literature workflow - broad discovery, open-access direct fetch with magic-byte validation, then signed-in browser fallback across CNKI, Wanfang, VIP, WoS, PubMed, arXiv and ScienceDirect; auto-adopts downloads into the workspace.
version: "3.2.0"
---

# 学术文献获取工作流（三级路由）

铁律：**能直取就不开浏览器；开了浏览器就逐页真人式操作；任何文件先过魔数闸门；只按本次新增识别文件，绝不碰历史文件；不编造平台文案。**

`<skill_dir>` = **本 SKILL.md 所在目录**（用户级安装在 `~/.workbuddy/skills/scholar-browser`；不同机器、不同用户目录不同，**不要照抄任何示例绝对路径**，运行时按实际安装位置替换）。
`<workspace>` = 当前工作区根目录。
Python 用 PATH 上的 `python`（3.9+ 即可，仅标准库，无第三方依赖）。

## 1. 三级路由（先看这里，别一上来就翻页）

| 层 | 做什么 | 用什么 | 何时用 |
|---|---|---|---|
| **L1 宽泛发现** | 主题 → 题名 + DOI/PMID/arXiv ID | `oa_fetch.py search` / `cite` 引文滚雪球 + 开放 API + WebSearch + 中文站内检索 | 一开始，永远先做 |
| **L1.5 中文期刊官网** | DOI → 官网真 PDF（**比知网好**） | `scripts/fetch_cn_journal.py` | 中文期刊 DOI 到手就试，早于 L3 |
| **L2 直接获取** | 标识符 → 过闸门的 PDF | `scripts/oa_fetch.py` | 拿到 DOI 立刻试 |
| **L3 登录态兜底** | 需机构权限/交互的全文 | `mcp__browser__*` + 平台 SOP | L2 失败且原因指向"需浏览器" |

**判定顺序（不要颠倒）**

1. 已知 DOI/PMID/arXiv ID → 直接 L2。
2. 只有主题 → L1 拿标识符 → L2。
3. L2 失败 → 看 `reason` 码：`cloudflare_challenge`/`login_wall`/`paywall_landing`/`captcha` → L3；`html_landing`/`not_found` → 换候选再试，耗尽才 L3。
4. 目标平台是**知网/万方/维普** → **跳过 L2**，直接 L3（中文订阅库直连无意义）。
5. **中文文献（有 DOI）→ 先 L1.5 官网直取，再万方，最后知网**：官网和万方都给**真 PDF**；知网多给 KDH/CAJ，需阅读器。
6. 中文文献 → L1 必须走中文站内检索，开放 API 对中文覆盖弱。

**实测底色（2026-11-13，3 个真实 DOI）**：L2 直取命中 1/3（33%），与第三方 123-DOI 实测 33%/39% 同量级。**所以 L3 不能省**，但也不该默认走。详见 `references/discovery.md`。

**通用策略（省时间的关键）**

- **先标识符后翻页**；**先题录后全文**（摘要多半免费，先判断值不值得下）。
- **权限前置**：先看机构名 / `View PDF` / 无锁图标，再点下载；`Get Access`、锁图标、跳登录页即判未订阅，不反复试探。
- **三张清单去重**：已检索（平台 + 题名/DOI）、已判定不需要、已下载（plan + MD5）。
- **L2 失败要留因**：把 `reason` 码带进 L3，别在浏览器里重复踩同一个坑。

## 2. 平台覆盖：8 个 + 中文期刊官网，各司其职

**关键认知：不要指望一个平台包办"找到 + 下载"。** 平台分两种用途——**发现**（找题名与标识符）和**宿主**（真给 PDF）。把它们都当下载站用只会浪费时间。

| 平台 | 角色 | 实测跑通到哪一步 |
|---|---|---|
| 中国知网 CNKI | 中文全文主通道（L3） | 检索 ✓ 题录 ✓ **全文 ✓**（多为 KDH/CAJ） |
| 万方 | **中文全文首选**（L3） | 检索 ✓ 题录 ✓ **全文 ✓**（12 篇，**给真 PDF**） |
| 中文期刊官网 | 中文真 PDF（L1.5） | 12 篇实测（力学 / 工程类中文刊） |
| 维普 | **当前不可自动化** | 检索 ✗（DOM/CUA 持续超时） |
| Google Scholar | 灰色文献/中文补充（**需代理**） | 检索 ✓；提交须点按钮，Enter 无效 |
| Web of Science | 引文发现（L1），非宿主 | 检索 ✗（输入写不进、截图空白） |
| PubMed / PMC | 题录发现（L1），全文交 L2 | 检索 ✓；列表页无摘要，`Free PMC` 可见 |
| arXiv | 预印本（**L2 优先**） | 检索 ✓ **全文 ✓**（L2 实测 2.2 MB） |
| ScienceDirect | 订阅出版商（L2 优先，L3 兜底） | 题名/期刊/`View PDF` href 全在 DOM |

**端到端能拿到 PDF 的路径**：中文 → CNKI（万方优先）；英文 OA → arXiv / PMC / Unpaywall（L2）；英文订阅 → SD 批量 ZIP 或机构 L3。**其余平台的价值在发现与核验，不在下载。**

不在表内的平台（SpringerLink、Wiley、IEEE、Scopus、读秀、百度学术、专利库等）**不在保证范围**：用户点名时可按同一套字段模板临时试，**不得声称已验证**。等级：A = 真实点击实测通过；B = 入口/字段有依据但流程不完整；C = 仅收录。

## 3. 红线（完整版见 `references/limits.md`）

1. **不碰凭据**：不读/不导出/不回显 Cookie、口令、令牌；登录只能用户自己做。
2. **不绕过**：不破 CAPTCHA、403、付费墙、机构认证、Cloudflare；不换 IP、不伪造 UA、不接打码。
3. **不批量**：逐篇检索、逐篇点击、串行、留间隔；API 侧串行 + 限速 + 缓存。
4. **遇阻停机**：验证码 / unusual traffic / 403 / 429 / 跳登录页 → 停队列标「需人工」，同一动作最多重试一次。
5. **不误伤文件、不编造**：只处理本轮基线后新增 + 白名单 + 魔数通过的文件；没实测的文案/字段/URL 一律标「待实测」。
6. **浏览器需授权才启动**：默认不主动开 GUI 浏览器；用户说「启动我的浏览器 / 用浏览器下载 / 可以启动」时才 `Start-Process msedge <url>`。启动 ≠ 绕过；**不 taskkill、不反复重启**。

## 4. 流水线

| 阶段 | 执行者 | 动作 |
|---|---|---|
| A 基线 | 脚本 | `init-baseline` — **任何下载前必做** |
| B 发现 | AI | L1：查 `discovery.md` §2 选渠道 → 题名 + 标识符 → Crossref 核验 |
| C 直取 | 脚本 | L2：`oa_fetch.py fetch` → 过闸门才落盘 |
| D 浏览器 | AI + 浏览器 | L3：查平台 SOP → 逐篇单击 → 核验落盘 |
| E 归集 | 脚本 | `scan-new` → `adopt` → `verify` → `report` |
| F 清场 | AI + 浏览器 | **只关本轮新增的标签页**；用户原有页一律不动（见 `runtime.md` §1） |

**固定开场（每次任务重新取标识）**

```
browsers_list → browser_info → user_open_tabs → snapshot 存基线 → tabs_new
```
必须选 `type: "extension"`（带真实登录态）；内置 `WorkBuddy Browser` 无登录态。**取到 `user_open_tabs` 就立刻存基线再开新页**——顺序反了，收尾分不清哪些页是我开的。

**浏览器实操只有三条要记**（其余见 `toolchain.md`）：可读性按站点分（DOM 抓链接与 href，截图补静态文本）；输入没有跨站可靠方案（提交前必须读回 `input.value`）；**URL 不能单独当成功判据**，必须 URL + 截图双验（CNKI 是 SPA、PubMed 校验页会伪装成成功）。

### 脚本命令

```bash
# 配置诊断：每项配置实际生效的位置与来源（project / user / 内置）
python "<skill_dir>/scripts/oa_fetch.py" config

# L1 发现
python "<skill_dir>/scripts/oa_fetch.py" search --query "<关键词>" --from-year 2020 --limit 25 --field title_abstract --out <dir>/q1.json
python "<skill_dir>/scripts/oa_fetch.py" cite --doi <种子DOI> --direction cited_by --limit 30

# L2 直取（不需要浏览器）
python "<skill_dir>/scripts/oa_fetch.py" resolve --doi <DOI>
python "<skill_dir>/scripts/oa_fetch.py" fetch --doi <DOI> --out "<workspace>/文献/<主题>/xx.pdf"
python "<skill_dir>/scripts/oa_fetch.py" batch --list <DOI清单> --out-dir "<workspace>/.workbuddy/tmp/oa-batch" --interval 2
python "<skill_dir>/scripts/oa_fetch.py" check --file "<path>"

# L1.5 中文期刊官网真 PDF
python "<skill_dir>/scripts/fetch_cn_journal.py" --csv "<workspace>/文献/00_索引与报告/文献总清单.csv" --dest "<workspace>/文献/中文期刊全文-官网PDF" --out <dir>/cn-pdf-result.json

# 取不到的 → 可点击清单，交用户手动另存
python "<skill_dir>/scripts/oa_fetch.py" checklist --list <DOI清单> --out "<workspace>/文献/待下载清单-<主题>.md"

# 出版商题录导出 → 摘要（下不到全文时的首选）
python "<skill_dir>/scripts/ris_meta.py" --ris "<下载目录>/ScienceDirect_citations_*.ris" --md "<workspace>/文献/导出题录与摘要.md"

# 订阅型 PDF：SD 批量 ZIP 导入（流程见 sd-batch.md）
python "<skill_dir>/scripts/sd_zip.py" --zip "<下载目录>/ScienceDirect_articles_*.zip" --target-dir "<workspace>/文献/<主题>" [--dry-run]

# 下载归集
python "<skill_dir>/scripts/litadopt.py" init-baseline --workspace "<workspace>"
python "<skill_dir>/scripts/litadopt.py" scan-new --workspace "<workspace>" --target-dir "<workspace>/文献/<主题>"
python "<skill_dir>/scripts/litadopt.py" adopt --plan <plan> --workspace "<workspace>" --target-dir "<workspace>/文献/<主题>" [--move-sources]
python "<skill_dir>/scripts/litadopt.py" verify --workspace "<workspace>"
python "<skill_dir>/scripts/litadopt.py" report --workspace "<workspace>" --format table
python "<skill_dir>/scripts/litadopt.py" purge --workspace "<workspace>"            # 只看隔离区占用
python "<skill_dir>/scripts/litadopt.py" purge --workspace "<workspace>" --confirm  # 真删（不可逆）
```

`--move-sources`：把本次新增文献移到隔离区（可逆、有日志、可 `rollback`），**仅当用户明确说过「默认下载目录不留」**；否则先 `--dry-run` 出清单请确认。彻底删除隔离区本 Skill 不做。

**下载目录不硬编码**：`litadopt.py` 按「组策略 → Edge/Chrome `Preferences` → 注册表 `User Shell Folders` → 兜底」解析，换机器自动适配。**接受标准是"文件名 + 大小 + mtime"基线快照**。

**格式优先级 PDF > CAJ > KDH**：下完一律按**魔数**判真实格式（后缀不可信）；**不要为换格式反复重下**——每次下载都计平台配额，间隔 ≥3–5 秒。

## 5. 参考文件路由（硬规则）

**任何任务先读 `references/ROUTER.md` + `references/limits.md`**；之后按需加载，**一次任务最多再加载 3 个**。

| 想做的事 | 读 |
|---|---|
| 找文献、判断能不能直下、要借哪些工具思路 | `discovery.md` |
| 构造检索式 / 精确直达 | `syntax.md` |
| **拿中文期刊真 PDF（优先于知网）** | `platforms-cn-journal.md` |
| 操作知网 | `platforms-cnki.md` |
| 操作万方 / 维普 | `platforms-cn.md` |
| 操作 WoS / PubMed / arXiv / ScienceDirect / GS | `platforms-global.md` |
| **订阅型 PDF 能不能自动落盘 / SD 批量 ZIP** | `sd-batch.md` |
| **要开浏览器：标签页基线 / 代理 / 邮箱** | `runtime.md` |
| **判断某篇值不值得读/存（A/B/C/D 分级）** | 分级标准按序生效：`<项目>/.scholar-browser/triage.md` > `~/.scholar-browser/triage.md` > 内置 `triage.md`（模板） |
| **配置在哪、为什么这次行为和上次不同** | `oa_fetch.py config`（打印每项配置的实际路径与来源） |
| **要派子代理去执行检索/下载/归集** | `executor-brief.md` |
| DOM 读不到、超时、输入不生效、失败回退 | `toolchain.md` |
| 验证/迭代某平台 SOP | `selftest.md` |
| 这份是不是最新 / 对照朋友那份版本 | `CHANGELOG.md` |

## 6. 交付标准：每篇都要给出「能自己继续」的东西

**这是本 Skill 的目的，不是为了"下载成功"而下载。** 每篇无论拿到全文与否，都要产出一条记录（`oa_fetch.py meta --format md` 直接产出）：

| 情况 | 交付内容 |
|---|---|
| **拿到 PDF** | 文件落盘 + 校验通过 + 记录（含 OA 状态、版本、来源、`via`） |
| **没拿到全文** | 题名、作者、来源、年份、DOI/PMID/arXiv ID、**摘要（有多少给多少）**、**至少一个可打开链接**、以及**为什么没拿到**（付费墙 / 验证码 / 需机构 / 找不到） |

**摘要优先级**：① 出版商官方 RIS 导出（最全最准，SD 实测 25/25 有摘要）→ `ris_meta.py`；② Crossref / OpenAlex / PubMed efetch（`meta` 自动依次试）；③ Semantic Scholar（无 key 常 429，退避一次即跳过，不要刷）；④ 全无 → 如实写「该库未提供摘要」+ DOI + GS 链接，**不编造**。

**判断标准：用户拿着这条记录，能自己点开链接继续。** 只回一句"下不了"是不合格的。拿不到全文时按序给替代路径：OA 副本 → 出版商/PubMed/arXiv 可打开链接 → 同主题替代文献（1–2 篇能拿到的，说明替代了什么）→ 校园网 / CARSI / 文献传递 / 向作者索取。

落盘规范：`<workspace>/文献/<主题>/`，命名 `NN_题名_作者_来源.{pdf|caj}`，序号接目录最大值，MD5 去重，同名不同内容不覆盖；状态与日志在 `<workspace>/.litadopt/`。中文期刊名/学校名**不编造**（脚本取知网 `<FileProperty>` 真字段，AI 确认后走 `--source-map`）。汇报要区分「直取(L2)」还是「浏览器(L3)」，并说明是否 OA、是否 preprint——用户需要知道能不能引用。

## 7. 已知限制

- **订阅型单篇 PDF 不能自动写盘**（进阅读器 → 系统另存为）→ 走 SD 批量 ZIP，见 `sd-batch.md`。
- 无 CAJViewer / caj2pdf → 真 CAJ 转不了；知网可能给 **KDH**，需官方阅读器。`pypdf` / `PyMuPDF` 已装，但脚本只用魔数。
- `mcp__browser__*` 无下载管理、无本地文件读取 → 下载靠点击触发落盘，文件侧全交脚本。
- 完全 OA 站点也可能因 TLS 指纹被拒（MDPI/PLOS/PMC 有报告）→ L2 固有上限，不是 bug。
- Edge 扩展偶发超时（claim/DOM/点击/finalize）：同操作最多重试一次，**不 taskkill、不反复重启**；`No current window` 且用户已授权时 `Start-Process msedge <url>`，仍失败请用户点一次扩展图标。
- 只对 §2 列出的平台负责；其余平台不声称验证过。

版本与变更历史见 `references/CHANGELOG.md`。
