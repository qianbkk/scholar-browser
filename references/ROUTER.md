# 参考文件路由（每次任务先读本文件）

## 加载预算（硬规则）

1. **必读**：本文件 + `limits.md`。
2. **一次任务最多再加载 3 个** reference。渐进式披露一旦退化成全量加载就失去意义。
3. 平台文件**只在确定要操作该平台时**读，不要为了"了解一下"全读。
4. 标「待实测」的字段不得据推测下结论，要按 `selftest.md` 实测一次再补。

## 文件清单

| 文件 | 放什么 | 何时读 |
|---|---|---|
| `ROUTER.md` | 本文件 | 任何任务开始 |
| `limits.md` | 合规红线、登录态失效信号、文件安全契约、诚实边界 | 任何任务开始 |
| `discovery.md` | **三级路由**：L1 渠道优先级与坑、L2 闸门与 reason 码、L3 触发判定、工具取舍 | 找文献 / 判断能否直取 / 决定要不要开浏览器 |
| `toolchain.md` | 浏览器工具边界、DOM 与输入策略、失败回退、下载目录与回滚 | DOM 读不到 / 节点失效 / 超时 / 输入不生效 / 跑脚本 |
| `sd-batch.md` | 订阅型 PDF 落盘边界 + ScienceDirect 批量 ZIP 全流程与实测限制 | 要判断订阅 PDF 能否自动拿到 / 走 SD 批量下载 |
| `runtime.md` | 标签页会话基线（snapshot/plan）+ 代理与邮箱配置 | 要开浏览器 / 报 timeout / 配 `SCHOLAR_EMAIL` |
| `CHANGELOG.md` | 版本变更记录（3.0.0 → 3.1.0） | 判断手上这份是不是最新 / 对照他人版本 |
| `syntax.md` | 8 个平台的检索字段与运算符 + 精确直达矩阵 | 需要构造检索式或精确直达 |
| `platforms-cn-journal.md` | 中文期刊官网真 PDF（L1.5，实测 12 篇） | 拿到中文期刊 DOI、要先试官网 |
| `platforms-cnki.md` | CNKI 详细 SOP（A 级，本机实测） | 操作知网 |
| `platforms-cn.md` | 万方 + 维普（B 级） | 操作中文非知网平台 |
| `platforms-global.md` | Google Scholar / WoS / PubMed+PMC / arXiv / ScienceDirect（B 级） | 操作外文平台 |
| `triage.md` | 文献价值分级**内置模板**（A/B/C/D + 关键词翻译法），不含任何具体课题 | 检索回来一堆结果、要决定下哪些/读哪些 |
| `selftest.md` | 子代理自测协议（含 L2 验证）+ 回报 JSON | 要验证或迭代某平台 SOP |
| `executor-brief.md` | **派子代理的指令模板**：硬预算、四条死法、停机条件、回报结构、验收清单 | 每次要派执行者做检索/下载/归集 |
| `scripts/fetch_cn_journal.py` | L1.5：中文期刊 DOI → 官网真 PDF（按刊名前缀路由 + 多候选 + 魔数校验 + JSON 结果表） | 由 SKILL.md 命令直接调用，不需阅读理解 |
| `scripts/oa_fetch.py` | L1：`search` 关键词检索 / `cite` 引文滚雪球；L2：`meta` 元数据兜底 / `resolve`+`fetch` 单篇直取 / `batch` 批量直取 / `checklist` 生成手动另存清单 / `check` 文件校验 / `config` 配置诊断 | 由 SKILL.md 命令直接调用，不需阅读理解 |
| `scripts/sd_zip.py` | ScienceDirect 批量下载 ZIP 导入：解压 + 魔数校验 + MD5 去重 + `NN_` 编号落位 | 由 SKILL.md 命令直接调用，不需阅读理解 |
| `scripts/ris_meta.py` | 出版商 RIS 导出解析：题录 + 出版商原文摘要，输出 JSON/Markdown | 拿不到全文、要补全面准确的摘要时 |
| `scripts/litadopt.py` | 下载归集 CLI：`init-baseline` / `scan-new` / `adopt` / `verify` / `report` / `rollback` / `purge` | 由 SKILL.md 命令直接调用，不需阅读理解 |
| `scripts/tab_session.py` | 标签页会话基线：`snapshot`（存 user_open_tabs）/ `plan`（比对后只关本轮新增页，输出 CLOSE/ASK） | 控制浏览器前后各跑一次 |
| `scripts/_config.py` | 内部模块（非 CLI）：配置分层解析，项目级 > 用户级 `~/.scholar-browser` > 内置；全部只读 | 由其它脚本 import，不直接调用 |

## 路由表

| 触发条件 | 必读 | 按需再读 |
|---|---|---|
| 任何任务开始 | `ROUTER.md` + `limits.md` | — |
| 「找几篇关于 X 的文献」 | `discovery.md` §2 | `syntax.md` |
| 「这篇能不能下 / 有没有全文」 | `discovery.md` §3–§4 | — |
| 有 DOI / PMID / arXiv ID | `discovery.md` §3 | — |
| 用户点名平台 | 对应 `platforms-*.md` | `syntax.md` 对应节 |
| 构造高级检索式 | `syntax.md` | 对应平台文件 |
| 摘要读不到 / 跳转后节点失效 | `toolchain.md` | — |
| 输入不生效 / 提交无反应 | `toolchain.md` §2 | — |
| 要开浏览器（存基线、清场、代理、邮箱） | `runtime.md` | — |
| 订阅型 PDF 能不能自动落盘 / SD 批量下载 | `sd-batch.md` | `limits.md` §5 |
| 判断这份技能是不是最新 | `CHANGELOG.md` | — |
| 跑了下载但目录没文件 | 对应平台 `download` 段 | `toolchain.md` §4 |
| 登录态信号 / CAPTCHA / 403 / 429 | `limits.md` §2 | — |
| 要验证某平台 SOP | `selftest.md` | 对应平台文件 |
| **要派子代理干检索/下载/归集** | `executor-brief.md` | 对应平台文件 |
| `--move-sources` / 回滚 | `toolchain.md` §5 | — |

## 平台 → 文件映射

| 平台 | 文件 | 等级 |
|---|---|---|
| 中国知网 CNKI（期刊/学位/海外版/CARSI） | `platforms-cnki.md` | A |
| 万方数据 | `platforms-cn.md` §万方 | B |
| 维普 CQVIP | `platforms-cn.md` §维普 | B |
| Google Scholar | `platforms-global.md` §GS | B（仅人工核对） |
| Web of Science | `platforms-global.md` §WoS | B |
| PubMed / PMC | `platforms-global.md` §PubMed | B |
| arXiv | `platforms-global.md` §arXiv | B |
| ScienceDirect | `platforms-global.md` §SD | B |

**不在表内的平台**：按 `platforms-global.md` 末尾的通用 SOP 模板临时试，但不得声称已验证。

## 目录结构与维护约定

```
scholar-browser/
├── SKILL.md                 ← 唯一入口：frontmatter + 三级路由 + 命令清单 + 交付标准
├── references/              ← 按需加载的知识（一次任务最多再读 3 个）
│   ├── ROUTER.md            ← 本文件：路由表 + 加载预算
│   ├── limits.md            ← 合规红线（必读）
│   ├── discovery.md         ← L1 / L2 / L3 判定与渠道优先级
│   ├── syntax.md            ← 8 平台检索式语法与精确直达
│   ├── toolchain.md         ← 浏览器工具边界、DOM/截图、失败回退、回滚
│   ├── sd-batch.md          ← 订阅型 PDF 落盘边界 + SD 批量 ZIP
│   ├── runtime.md           ← 标签页会话基线 + 代理/邮箱
│   ├── CHANGELOG.md         ← 版本变更记录
│   ├── platforms-cn-journal.md  ← 中文期刊官网 L1.5（比知网好）
│   ├── platforms-cnki.md    ┐
│   ├── platforms-cn.md      ├ 平台 SOP：确定要操作该平台时才读
│   ├── platforms-global.md  ┘
│   ├── triage.md            ← 分级**内置模板**（个人定制放 ~/.scholar-browser/triage.md）
│   ├── selftest.md          ← 平台 SOP 自测协议
│   └── executor-brief.md    ← 派子代理的指令模板
└── scripts/                 ← 零依赖 CLI（仅 Python 标准库），由 SKILL.md 直接调用
    ├── oa_fetch.py          ← L1 检索 / L2 直取 / meta / batch / checklist / check
    ├── fetch_cn_journal.py  ← L1.5 中文期刊官网真 PDF
    ├── sd_zip.py            ← ScienceDirect 批量 ZIP 导入
    ├── ris_meta.py          ← RIS 题录 + 出版商原文摘要解析
    ├── litadopt.py          ← 下载归集（含 rollback / purge）
    ├── tab_session.py       ← 标签页基线快照 / 关闭计划（snapshot / plan）
    └── _config.py           ← 配置分层解析（内部模块，非 CLI）
```

1. **此目录只放 Skill 本体**：1 个 `SKILL.md` + `references/*.md` + `scripts/*.py`（+ 仓库文件 `README.md` / `LICENSE` / `.gitignore` / `.gitattributes`）。不存检索结果、下载文件、报告、备份、截图——那些归 `<workspace>/文献/` 与 `<workspace>/.workbuddy/tmp/`。
   - **技能目录不放任何个人配置**：分级标准、期刊映射、邮箱等一律放 `~/.scholar-browser/`（用户级）或 `<workspace>/.scholar-browser/`（项目级）。这样技能目录可被 zip 覆盖 / `git pull` / 市场更新而无损。查找顺序由 `scripts/_config.py` 统一实现（项目 > 用户 > 内置），`oa_fetch.py config` 可打印实际来源。
2. **不留编译缓存**：`__pycache__/`、`.pyc`、临时脚本、日志都不放这里（可再生，且会让人误以为是第五个脚本）。
3. **增删文件必须同步本文件的「文件清单」表**；改结论要同步 `SKILL.md`、`limits.md`、对应 `platforms-*.md` 三处，不要只改一处留矛盾。
4. 每次改动后跑一遍验收：脚本语法编译、各脚本 `--help`、文档里的 Markdown 文件引用是否都存在；验收脚本样例见 `<workspace>/.workbuddy/tmp/lit-search/acceptance.py`。
5. 文档**不写本机绝对路径、端口、IP、用户名**，统一用 `<skill_dir>` / `<workspace>` / `<用户端口>` 占位，保证换机器可复用。

## 现成工具生态（仅被问到时展开）

- 开放元数据：OpenAlex、Crossref、Semantic Scholar、Unpaywall（`/v2/search` 已于 2026-09-18 退役，搜索职能转 OpenAlex）。
- 中文学术 MCP：万方数据 MCP（检索 + 全文下载）、CNKI AI LINK（`mcp.cnki.net` 试运行，仅检索无全文）、维普技能包、社区 GeoScholar/文溯。
- **未找到**「官方 + 复用用户真实浏览器登录态 + 覆盖知网/万方全文下载」的单一 MCP → 故本 Skill 用「开放 API 直取 + 浏览器兜底 + 本地脚本归集」组合。
- 商业学术搜索产品（Elicit/Consensus/Scite 等）的机制取舍见 `discovery.md` §5。
