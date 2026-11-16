# 子代理自测协议（v2.0）

> 目的：让子代理按统一动作序列在真实环境试跑，回报**结构化 JSON**，主会话据此定位「要改哪一行」。
> v2.0 变更：平台收窄到 8 个；新增 L2（`oa_fetch.py`）验证段，因为"能不能直取"也是要被验证的能力。

## 0. 给主会话的调用约定

派子代理时把本文件指给它，并明确：
- 浏览器工具通过 `ToolSearch(tool_names=["mcp__browser__browsers_list", ...])` 加载 schema，再用 `DeferExecuteTool` 调用；**不用命令行浏览器 / CDP / agent-browser CLI**。
- 每次任务重新 `browsers_list → browser_info → user_open_tabs → tabs_new（不 claim 用户页）`，必须选 `type: "extension"`。
- 回报 JSON **写到** `<workspace>/.workbuddy/tmp/scholar-selftest/run-<n>.json`（目录不存在就建），回复只给 10 行以内摘要。
- 除该 JSON 外不写任何文件；不修改 Skill（改由主会话做）。

## 1. 试验对象

### 1.1 L2 直取验证（不需要浏览器，先跑）

用 3 个 DOI 覆盖「成功 / gold 失败 / 订阅失败」三种分支，全部真实请求：

```bash
python "<skill_dir>/scripts/oa_fetch.py" resolve --doi <DOI>
python "<skill_dir>/scripts/oa_fetch.py" fetch  --doi <DOI> --out "<tmp>/<name>.pdf"
python "<skill_dir>/scripts/oa_fetch.py" check  --file "<tmp>/<name>.pdf"
```

| # | DOI | 预期 |
|---|---|---|
| L2-1 | `10.48550/arXiv.1706.03762` | 成功（arXiv 仓储 PDF，~2.2 MB） |
| L2-2 | `10.7717/peerj.4375` | gold OA 但可能失败（PMC 返 HTML / Cloudflare 403） |
| L2-3 | `10.1038/nature14539` | 失败（订阅刊，`html_landing` 链路） |

记录：`candidates` 数量、`chosen.via`、`verify.magic`、`attempts[].reason`、耗时。
**验证点**：失败时**不得留下任何文件**（含 `.part`）。

### 1.2 平台页面验证（串行，按预算裁剪）

| # | 平台 | 覆盖意图 | 入口 | 低风险检索式 | 等级 |
|---|---|---|---|---|---|
| 1 | CNKI | 中文付费库 + 登录态（A 级回归） | `kns.cnki.net` 一框式 | 完整题名（挑一篇你手头已有的中文论文题名，应命中唯一结果） | A |
| 2 | 万方 | 中文第二库 | `www.wanfangdata.com.cn` | `石墨烯 传感器` | B |
| 3 | 维普 | 中文第三库 | `www.cqvip.com` | `石墨烯` | B |
| 4 | Google Scholar | 发现层（**只读一屏，禁翻页**） | `scholar.google.com` | `"graphene sensor"` | B |
| 5 | Web of Science | 外文索引 / 非全文宿主 | 机构入口 | `TI=(graphene AND sensor)` | B |
| 6 | PubMed | 字段标签 + 摘要 | `pubmed.ncbi.nlm.nih.gov` | `"machine learning"[ti]` | B |
| 7 | arXiv | OA 预印本 / 静态摘要 | `arxiv.org` | `ti:"diffusion model"` | B |
| 8 | ScienceDirect | 出版商 / 两步下载 | `sciencedirect.com` | `"graphene oxide membrane"` | B |

> 检索式用**中性领域词**，只为验证 SOP 通不通，与任何具体课题无关。换成自己的词也一样——这里测的是流程，不是相关性。

预算不足时按 1/2/6/7/8 裁剪（覆盖中文/索引/OA/出版商四类），被裁的在 `summary.skipped` 列出。

## 2. 每平台最小动作序列

```
开场（每平台重来，不复用 browser_id/tab_id）：
  browsers_list → browser_info → user_open_tabs → tabs_new（不 claim 用户页）
S1 tabs_new / tab_goto 到入口（新建受控标签页，禁止覆盖或关闭用户原有标签页）
S2 dom_cua_get_visible_dom → 记录搜索框是否命中、登录态标识是否可见
S3 输入检索式（记录字段下拉是否需操作、联想下拉是否干扰）
S4 提交（记录 enter 还是按钮；按钮文案只在实测看到时才记）
S5 结果页重读 DOM → 记录可读字段、结果数、翻页/筛选控件
S6 进第 1 条详情 → 读题名/作者/来源/年份/摘要；读不到则 tab_screenshot 一次
S7 只读权限标识（View PDF / 下载 / Get Access / 锁图标 / Free PMC article）
S8 tabs_finalize（超时不判失败）
```

### 2.1 标注规则（实测后补充，必须遵守）

| 情况 | 标注要求 |
|---|---|
| 用 ID / DOI 直达 | S3/S4 不适用；`submit_method` 写 `unknown（直达）`，未验证的语法入 `unverified_items`。**不得据此判为走完 S1–S8** |
| 表单提交不生效 | 允许 `tab_goto` 直达结果页继续；必须写清 URL 是「页面实测 href」还是「按参数构造」，**构造类 `evidence=未验证`** |
| 详情页靠 `tab_goto` 进入 | `detail_entry=unknown`，不算"点击题名"；只有真点题名并观察到新标签/模态才写 `new_tab`/`modal` |
| 导出/批量按钮 | **只观察不点击**，在 `findings` 注明"存在但未点击" |
| `user_open_tabs` 为空或 claim 失败 | 直接用 `tabs_new` 新建受控标签页（带 url 即完成 S1）；不 claim/不操作/不关闭用户标签页 |
| `user_open_tabs` **非空且都是用户自己的页面** | **一律 `tabs_new` 新建受控页**，不 claim。`claim` 只在用户明确说"接手这个页面"时才用——claim 会接管用户正在看的页面，`finalize` 可能把它关掉 |
| `tabs_finalize` 保留的页回到 observed 池，同一页可能出现两个 tab_id | 下一轮开场忽略重复页，不要"看到有内容就 claim" |
| DOM 出现凭据类元素 | 不读值、不回显、不写日志（`limits.md` §1） |
| 结果页题名是 `span` 无 href，点击会新开**用户**标签页 | S6 允许只读结果页题录，标 `detail_entry=unknown`；**不得为凑流程去构造 URL 或操作用户标签页** |
| Google Scholar | 只允许**一屏**：不翻页、不爬 Cited by、不循环检索；发现 challenge 立即停 |

## 3. 量化指标

| 指标 | 定义 |
|---|---|
| `steps.total` | 工具调用总数（含开场 4 步），分 `opening/navigate/dom_snapshots/status_reads/clicks/screenshots/finalize`；单平台上限 25 |
| `errors[]` | 失败与重试；区分链路抖动（超时）vs 页面拒绝（403/CAPTCHA） |
| `screenshot_fallback` | 0/1：是否因 DOM 读不到摘要而必须截图 |
| `dom_sufficiency` | `sufficient`（题名+作者+来源+年份+摘要前 100 字全可读）/ `partial` / `insufficient` |
| `login_valid` | `valid`（机构名可见/无锁/可下载态）/ `invalid` / `unknown` |
| `elapsed_bucket` | `<30s` / `30–90s` / `90–180s` / `>180s` |
| `blockers[]` | `cookie_banner` `choose_org` `captcha` `login_redirect` `403` `429` `paywall` `overlay` `js_challenge` `stale_tab` `timeout` |
| L2 指标 | `candidates_count` / `chosen.via` / `attempts[].reason` / `leftover_files`（必须为 0） |

## 4. 回报 JSON

```json
{
  "run": {"protocol_version":"2.0","date":"","agent":"","browser_type":"extension",
          "download_performed":false,"platforms_attempted":8,"skipped":[]},
  "l2": {
    "cases":[{"doi":"","ok":true,"candidates_count":0,"chosen_via":"","reasons":[],
              "verify_magic":"","bytes":0,"leftover_files":0,"elapsed_s":0}],
    "verdict":""
  },
  "platforms": [{
    "platform_id":"cnki","entry_url":"","query":"",
    "status":"ok | partial | blocked | login_required | not_subscribed | timeout",
    "steps":{"total":0,"opening":4,"navigate":0,"dom_snapshots":0,"status_reads":0,"clicks":0,"screenshots":0,"finalize":1},
    "errors":[{"stage":"","tool":"","message":"","retried":false,"resolved":false}],
    "findings":{"login_valid":"","dom_sufficiency":"","readable_fields":[],"missing_fields":[],
                "screenshot_fallback":false,"submit_method":"","submit_button_text":"",
                "detail_entry":"","abstract_locator":"","permission_label":"",
                "download_trigger_observed":"","blockers":[],"elapsed_bucket":"",
                "evidence_type":"实测"},
    "suggestions":[{"file":"references/platforms-cn.md","field":"download.button_text",
                    "current":"","proposed":"","evidence":"实测 | 未验证"}]
  }],
  "summary":{"status_counts":{},"platforms_ok":0,"needs_file_changes":[],
             "common_gaps":[],"unverified_items":[],"risk_notes":[]}
}
```

`file + field` 让主会话直接定位待改行；`evidence` 强制标依据；`common_gaps` 支持横向对比（如「4/8 平台缺 `search_box.submit`」→ 优先改通用模板）。

## 5. 安全约束（不可协商）

1. **不并发**：串行，一次一平台一标签页，平台间留自然间隔。
2. **不批量**：不勾选多篇、不走批量下载/导出、不循环脚本化点击、API 侧不并发不刷限速。
3. **不绕过登录**：不代登录、不读/回显 Cookie、不伪造 UA、不换 IP、不接打码、不构造内部接口。
4. **遇阻即停**：`captcha`/`unusual traffic`/`403`/`429`/跳登录页/JS 校验页 → 该平台 `status=blocked`，停队列不重放。同一动作最多重试一次。
5. **收尾要清场**：只在自己新建的标签页操作；**结束后用 `tabs_close` 把自己开的所有页关掉**（除非用户明确要求留着看）。`tabs_finalize` 只用于保留交付页。**用户原有标签页一律不关**。`tabs_close` 报超时是假失败，用 `user_open_tabs` 复核即可（`limits.md` §1.8）。
6. **不产生文献文件**：平台验证段全程禁止点击下载/导出/PDF 保存；不跑 `litadopt` 任何命令。
   **例外**：L2 段（§1.1）允许真实下载，但**只能下到临时目录**，且必须验证"失败时无残留"。
7. **只读题录**：不把结果写回除回报 JSON 外的任何位置。
8. **超时兜底**：`tabs_finalize` 超时不判失败；单平台超 25 步或 180s 强制收尾标 `partial`。跨轮对比时，finalize 超时仍计入 `errors[]` 但注明「协议规定不计失败」。

## 6. 主会话如何据回报迭代

1. 读 `run-<n>.json` → 看 `summary.needs_file_changes` 与 `common_gaps`；L2 看 `l2.verdict` 与各 `reasons`。
2. 只把 `evidence=实测` 的 `proposed` 回填对应文件；`未验证` 的留在「待实测」。
3. 通用缺口改 `toolchain.md` / `discovery.md` 的通用段；单平台缺口改该平台卡片。
4. **升 A 的硬条件**：`status=ok` 且 S3 输入、S4 提交、S6 详情入口都是真实点击/输入实测（不能是直达或构造 URL），且 S1–S8 全走完。
5. 必要时派第二次复测，对比 `steps.total` / `errors[]` / `dom_sufficiency` / `l2` 命中率。
6. 每次迭代把变更摘要追加到工作区日志，不改 `limits.md` 的红线部分。
