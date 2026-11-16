# 变更记录

> 只在需要判断"手上这份是不是最新"或对照朋友那份版本时读。版本语义：major = 行为模式重写；minor = 新增通道/结构调整；patch = 修正与措辞。

## 3.2.0（2026-11-16）配置分层：技能目录与个人数据彻底分离

**动机**：原先个人定制文件（`triage.local.md`、`cn_journal_map.local.json`）放在技能目录里，用 zip 覆盖升级或 `git pull` 时会一并丢失。

- 新增 `scripts/_config.py`（内部模块）：统一实现 **项目级 `<workspace>/.scholar-browser/` > 用户级 `~/.scholar-browser/` > 内置模板** 的查找；自动跳过技能目录自身（技能也是 git 仓库，否则会把自己的 `.git` 误判成项目根）；项目级与用户级重合时视为无项目级。
- 新增 `oa_fetch.py config` 诊断命令：打印每项配置的实际路径与来源、期刊映射合并条数、邮箱来源（脱敏）、代理模式。
- `fetch_cn_journal.py`：映射改为分层加载（`cn_journal_map.json`），支持 `{doi}` / `{tail}` 两种占位符；旧位置 `scripts/cn_journal_map.local.json` 仍识别但提示迁移。
- 邮箱来源扩展：`--email` > `SCHOLAR_EMAIL` > `config.json`（允许把常用邮箱写进用户级配置）。
- 文档同步：`README` 新增「配置放哪」；`ROUTER` 维护约定改为「技能目录不放任何个人配置」；`triage.md` 明确标注为内置模板；`platforms-cn-journal.md` 的扩展映射改指用户级路径。

**升级提示**：旧版本把配置放在技能目录里的用户，把 `references/triage.local.md` 移到 `~/.scholar-browser/triage.md`、`scripts/cn_journal_map.local.json` 移到 `~/.scholar-browser/cn_journal_map.json`。旧位置仍能跑，但升级会覆盖。

## 3.1.1（2026-11-16）个性信息再收敛 + 脚本可扩展，**无行为变更**

- 中文期刊官网 SOP 重写：删掉指向性强的一批刊名与整节站点专项，只保留 **5 本通用刊**（力学/物理/工程类）作示例。
- 三个**跨刊通用坑**单独成节（DOI 截断导致 200 但页面 404、结果页 PDF 链接是 JS 绑定、大文件截断需 8 KB 尾窗），不再绑定具体站点。
- `fetch_cn_journal.py` 刊名映射**外部化**：内置 5 本通用刊，其余走 `scripts/cn_journal_map.local.json`（已 `.gitignore`），启动时自动合并；文件缺失或 JSON 写错只提示一行，不影响内置表。本地原有 10 本刊全部可用。
- 补「首次使用怎么填自己的 webvpn 与机构名」三步指引（`limits.md` §1.0.4），说明 Skill 不保存域名与 hash、需要时向用户索取。

## 3.1.0（2026-11-16）结构精简，**无行为变更**

SKILL.md 从 289 行压到 178 行，把"只在特定场景才需要"的细节移到 references，让入口文件只留路由、命令与交付标准。

- 新增 `references/sd-batch.md`：订阅型 PDF 落盘边界 + SD 批量 ZIP 全流程（原 SKILL §7.1 + §8 首条）。
- 新增 `references/runtime.md`：标签页会话基线管理（原 SKILL §4 子节）+ 代理与邮箱配置（原 SKILL §9）。
- 新增 `references/CHANGELOG.md`：本文件（原 SKILL §10）。
- `SKILL.md` 的 §2 平台表、§3 红线、§8 已知限制改为"摘要 + 指针"，细节仍在 `limits.md` / `toolchain.md` / `platforms-*.md`。
- frontmatter 补 `display_name` / `display_name_en`（开放平台 / SkillHub 上架的必填字段，本地使用不受影响）。
- **公开前安全脱敏**：移除学校名、机构码、webvpn 真实 hash、本机代理端口，统一改为 `<学校域名>` / `<机构码>` / `<端口>` 占位（原则：机构凭据与本校入口一律不入库）。
- **课题信息与仓库解耦**：`triage.md` 改为通用模板（分级方法保留，课题坐标改为占位；个人定制版另存 `triage.local.md`，已 `.gitignore`）；`selftest.md` / `discovery.md` / `platforms-cnki.md` 的检索示例换成中性领域词。
- 新增仓库文件：`README.md`、`LICENSE`（MIT）、`.gitignore`、`.gitattributes`；仓库根目录即技能目录，可直接被 SkillHub / 开放平台从 GitHub 导入。
- 同步 `ROUTER.md` 文件清单与目录树。

## 3.0.1（2026-11-16）文档一致性整理，**无行为变更**

- `toolchain.md` 代理说明改正：与代码一致——**默认直连**（不读环境变量），`--proxy` 显式代理，`--auto-proxy` 才降级读环境变量；`--no-proxy` 仅兼容保留。
- `toolchain.md` 本机 PDF 库现状更新：`pypdf` / `PyMuPDF` 已装（脚本仍零依赖，只用魔数）。
- `ROUTER.md` 补登 `platforms-cn-journal.md` / `fetch_cn_journal.py` / `tab_session.py`（此前被 SKILL.md 调用但未进清单）。
- `limits.md` 章节编号重排为 1.0.1 浏览器启动 / 1.0.2 PDF 完成判定 / 1.0.3 代理拦 UA / 1.0.4 校园 webvpn（此前两个 1.0.1 且顺序颠倒）。
- PDF 完整性判定的尾部窗口统一为 **8 KB**（`platforms-cn-journal.md` 原写 4 KB）。
- §2 标题与表格对齐（8 个平台 + 中文期刊官网）；固定开场补「先存标签基线再开新页」。

## 3.0.0（2026-11-15）三级路由基线

L1 发现 / L1.5 中文期刊官网 / L2 OA 直取 / L3 登录态兜底，配 `oa_fetch` `fetch_cn_journal` `litadopt` `sd_zip` `ris_meta` `tab_session` 六个零依赖脚本。更早的 2.x 变更未逐条记录。
