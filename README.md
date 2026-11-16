# scholar-browser

学术文献检索与获取工作流（`SKILL.md` 格式技能）。**完整支持 WorkBuddy**；其他 agent 的浏览器方案尚未适配，见下方[兼容性](#兼容性)。

三级路由：**先宽泛发现**拿到 DOI/PMID/arXiv ID → **再尝试 OA 直取**（魔数闸门校验）→ **未成功再在你的浏览器里**按平台流程逐页操作。下载文件自动校验、去重、规范命名后归集到工作区。

## 为什么不是"一键下载"

文献获取的真实瓶颈不是解析网页，而是**判断哪条路能走通**：

| 层 | 做什么 | 典型命中率 |
|---|---|---|
| L1 宽泛发现 | 主题 → 题名 + 标识符（OpenAlex / Crossref / 站内检索） | 高 |
| L1.5 中文期刊官网 | 中文 DOI → 官网真 PDF（可读、非加密，优于知网） | 取决于刊 |
| L2 OA 直取 | DOI → PDF，脚本发标准 HTTP 请求，不开浏览器 | **实测 33%**（3 个真实 DOI） |
| L3 浏览器协作 | 需登录或需交互的全文，在你自己的浏览器里逐页操作 | 取决于权限 |

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

可以放，但要清楚边界：**脚本层（发现、直取、题录、归集校验）只依赖 Python 标准库，直接可用**；**L3 浏览器段按 WorkBuddy 的 browser-use 插件写成，其他 agent 未做适配**——工具名不同时需自行映射，未必完全可用。详见[兼容性](#兼容性)。

## 配置放哪（升级不丢）

技能目录是"程序"，会被 zip 覆盖、`git pull`、市场更新替换。**个人配置不要放进去。**

```
<项目>/.scholar-browser/<文件名>     ← 最高优先级，只在当前项目生效
~/.scholar-browser/<文件名>          ← 用户级，跨项目复用（推荐）
<技能目录>/...                       ← 内置模板，只读，随升级替换
```

| 文件 | 作用 |
|---|---|
| `triage.md` | 你的文献分级标准（内置模板在 `references/triage.md`） |
| `cn_journal_map.json` | DOI 前缀 → 期刊官网模板，扩展内置的 5 本刊 |
| `config.json` | 默认邮箱：`{"email": "you@example.com"}` |

查任何一项**实际生效**的位置与来源：

```bash
python <skill_dir>/scripts/oa_fetch.py config
```

首次使用建议：`cp references/triage.md ~/.scholar-browser/triage.md` 再改成自己的课题。

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
  runtime.md             标签页会话基线 + 网络出口 / 邮箱
  triage.md              文献价值分级（方法模板，可按自己课题替换）
  selftest.md            平台 SOP 自测协议
  executor-brief.md      派子代理的指令模板
  CHANGELOG.md           版本记录
scripts/                 零依赖脚本（仅 Python 标准库）
  oa_fetch.py            L1 检索 / L2 直取 / meta / batch / checklist / check
  fetch_cn_journal.py    L1.5 中文期刊官网 PDF
  litadopt.py            下载归集（基线 → 扫描 → 归集 → 校验 → 回滚）
  sd_zip.py              ScienceDirect 批量 ZIP 导入
  ris_meta.py            RIS 题录 + 出版商原文摘要
  tab_session.py         标签页基线快照与关闭计划
  audit.py               自检：一致性 / 引用完整性 / 脚本可用性 / 发布卫生
  _config.py             内部模块（非 CLI）：配置分层解析
```

渐进式披露：SKILL.md 常驻上下文，references 按需加载（单次任务最多再加载 3 个）。

## 兼容性

| 层 | 适用范围 | 说明 |
|---|---|---|
| 脚本层（L1 发现 / L1.5 中文期刊官网 / L2 直取 / 题录摘要 / 归集校验） | **任何 agent** | 8 个 Python 文件只用标准库，无 MCP 依赖 |
| L3 浏览器协作 | **仅 WorkBuddy** | 工具名来自其 browser-use 插件（`tabs_new` / `user_open_tabs` / `dom_cua_get_visible_dom` / `cua_click` / `tab_screenshot` / `tabs_close` 等） |
| 其他 agent 的浏览器方案 | **未适配** | Playwright MCP、DevTools 封装、agent 内置浏览器等均未测试，**未必完全可用** |

移植要做的事：把 L3 的 7 个语义动作（列浏览器 / 标签管理 / 读页面结构 / 交互 / 截图 / 导航 / 关标签）映射到目标方案，见 `references/toolchain.md` §1。两点无法靠改名解决——**登录态复用**（这里靠浏览器扩展借用你已登录的会话，换方案通常要自己登录持久化 profile）与**下载落盘**（这里靠点击触发真实下载再由脚本收件，有的方案可直接存到指定路径，归集逻辑要相应调整）。

## 环境要求

- Python 3.9+，**无第三方依赖**
- 浏览器段（L3）需要 WorkBuddy + 其浏览器扩展（Chrome / Edge），使用**你自己的登录态**；其他 agent 无等价方案时，L3 相关平台只能走手动另存
- 可选：`SCHOLAR_EMAIL`（Unpaywall 要求真实邮箱，不配则跳过，候选变少）
- 可选：`--proxy` / `--auto-proxy`（**机构订阅库必须直连**，代理会让机构授权失效）

## 覆盖范围与能力边界

8 个平台：知网 CNKI、万方、维普、Google Scholar、Web of Science、PubMed/PMC、arXiv、ScienceDirect，外加中文期刊官网通道。

**真正能端到端拿到 PDF 的只有三条路**：OA 直取、知网下载、ScienceDirect 批量 ZIP。

其余价值在**发现与核验**，不在下载——把发现型平台当下载站用只会浪费时间。维普当前不可自动化（DOM/CUA 持续超时）；WoS 能开检索页但输入写不进。这些是实测结论，不是待办事项。

## 合规红线

本技能只用于**获取你有合法访问权限的文献**：

- 登录凭据始终留在你自己的浏览器里：本技能不读取、不保存、不回显
- 只获取公开可用的，或你本人有权访问的内容；遇到登录墙、校验页、订阅确认页即停止该条目
- 逐篇、串行、留间隔，不做批量轰炸
- 遇阻（校验页 / 403 / 429 / 跳登录）立即停机标「需人工」，不做反复试探
- 拿不到全文时，交付**题录 + 摘要 + 可打开链接**，并给出正规替代路径（OA 副本、机构文献传递、向作者索取），而不是"下不了"三个字

## 打包约定

**仓库里不放任何点开头的配置文件**（`.gitignore`、`.gitattributes` 等）——平台的技能包只接受源码与文档，这类文件会被判为"不允许的文件类型"。

忽略规则改放在 `.git/info/exclude`（本地生效、不进仓库、不会被上传）。重新 clone 后如需要，把这几行追加进去：

```bash
cat >> .git/info/exclude <<'EOF'
__pycache__/
*.py[cod]
*.log
tmp/
dist/
*.zip
EOF
```

打 zip 时同样排除所有点开头文件与 `__pycache__`；许可证用 `LICENSE.md`（带扩展名，平台的白名单认它）。

## 自检

改完技能或发布前跑一次，只读、不改文件：

```bash
python <skill_dir>/scripts/audit.py          # 只看结论
python <skill_dir>/scripts/audit.py --verbose # 逐项列出
```

查这些：frontmatter 字段与格式、三处版本号是否一致、ROUTER 是否漏登记文件、文档引用的文件是否存在、`§x.y` 交叉引用是否有效、是否有未定义的常量、脚本能否编译并响应 `--help`、示例参数是否真实定义、是否混入身份信息或点文件。退出码 0 表示全通过。

## 版本

当前 `3.4.1`。变更记录见 `references/CHANGELOG.md`。

## License

MIT
