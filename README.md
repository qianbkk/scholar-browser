# scholar-browser

学术文献检索与获取工作流（WorkBuddy / Claude Code 兼容的 `SKILL.md` 技能）。

三级路由：**先宽泛发现**拿到 DOI/PMID/arXiv ID → **再尝试 OA 直取**（魔数闸门校验）→ **失败才用真实浏览器登录态**逐页操作。下载文件自动校验、去重、规范命名后归集到工作区。

## 为什么不是"一键下载"

文献获取的真实瓶颈不是解析网页，而是**判断哪条路能走通**：

| 层 | 做什么 | 典型命中率 |
|---|---|---|
| L1 宽泛发现 | 主题 → 题名 + 标识符（OpenAlex / Crossref / 站内检索） | 高 |
| L1.5 中文期刊官网 | 中文 DOI → 官网真 PDF（可读、非加密，优于知网） | 取决于刊 |
| L2 OA 直取 | DOI → PDF，脚本发标准 HTTP 请求，不开浏览器 | **实测 33%**（3 个真实 DOI） |
| L3 登录态兜底 | 需机构权限/交互的全文，用用户自己已登录的浏览器 | 取决于权限 |

L2 只有三分之一命中，所以 L3 不能省——但也不该默认走。先判 `reason` 码再决定开不开浏览器，是这个技能的主要价值。

## 安装

**方式一：WorkBuddy 上传技能（推荐）**

技能 → 添加技能 → 上传技能 → 选本目录打成的 zip。

**方式二：手动放目录**

```bash
git clone <this-repo> ~/.workbuddy/skills/scholar-browser
```

Windows 对应 `C:\Users\<你>\.workbuddy\skills\scholar-browser`。放好后新开一个会话即可生效。

**方式三：Claude Code / 其他兼容 agent**

放进对应 agent 的 skills 目录（同为 `SKILL.md` 格式）。

## 目录结构

```
SKILL.md                 入口：三级路由 + 命令速查 + 交付标准（~180 行）
references/
  ROUTER.md              加载预算与路由表（任何任务先读）
  limits.md              合规红线、登录态信号、文件安全契约
  discovery.md           L1/L2/L3 判定与渠道优先级
  toolchain.md           浏览器工具边界、DOM/输入策略、失败回退
  syntax.md             8 平台检索式与精确直达
  platforms-cnki.md      知网 SOP
  platforms-cn.md        万方 / 维普
  platforms-cn-journal.md 中文期刊官网
  platforms-global.md    GS / WoS / PubMed / arXiv / ScienceDirect
  sd-batch.md            订阅型 PDF 落盘边界 + 批量 ZIP
  runtime.md             标签页会话基线 + 代理/邮箱
  triage.md              文献价值分级（方法模板，可按自己课题替换）
  selftest.md            平台 SOP 自测协议
  executor-brief.md      派子代理的指令模板
  CHANGELOG.md           版本记录
scripts/                 六个零依赖脚本（仅 Python 标准库）
  oa_fetch.py            L1 检索 / L2 直取 / meta / batch / checklist / check
  fetch_cn_journal.py    L1.5 中文期刊官网 PDF
  litadopt.py            下载归集（基线 → 扫描 → 归集 → 校验 → 回滚）
  sd_zip.py              ScienceDirect 批量 ZIP 导入
  ris_meta.py            RIS 题录 + 出版商原文摘要
  tab_session.py         标签页基线快照与关闭计划
```

渐进式披露：SKILL.md 常驻上下文，references 按需加载（单次任务最多再加载 3 个）。

## 环境要求

- Python 3.9+，**无第三方依赖**
- 浏览器兜底需要 WorkBuddy 的浏览器扩展（Chrome / Edge）并使用**你自己的登录态**
- 可选：`SCHOLAR_EMAIL`（Unpaywall 要求真实邮箱，不配则跳过，候选变少）
- 可选：`--proxy` / `--auto-proxy`（**机构订阅库必须直连**，代理会让机构授权失效）

## 覆盖范围与能力边界

8 个平台：知网 CNKI、万方、维普、Google Scholar、Web of Science、PubMed/PMC、arXiv、ScienceDirect，外加中文期刊官网通道。

**真正能端到端拿到 PDF 的只有三条路**：OA 直取、知网下载、ScienceDirect 批量 ZIP。

其余价值在**发现与核验**，不在下载——把发现型平台当下载站用只会浪费时间。维普当前不可自动化（DOM/CUA 持续超时）；WoS 能开检索页但输入写不进。这些是实测结论，不是待办事项。

## 合规红线

本技能只用于**获取你有合法访问权限的文献**：

- 不读取、不导出、不回显任何 Cookie / 口令 / 令牌；登录只能用户自己完成
- 不绕过 CAPTCHA、付费墙、机构认证、Cloudflare；不换 IP、不伪造 UA、不接打码
- 逐篇、串行、留间隔，不做批量轰炸
- 遇阻（验证码 / 403 / 429 / 跳登录）立即停机标「需人工」，不做反复试探
- 拿不到全文时，交付**题录 + 摘要 + 可打开链接**，并给出正规替代路径（OA 副本、机构文献传递、向作者索取），而不是"下不了"三个字

## 版本

当前 `3.1.0`。变更记录见 `references/CHANGELOG.md`。

## License

MIT
