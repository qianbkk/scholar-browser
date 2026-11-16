# 运行期配置：标签页会话管理 + 代理与邮箱

> 何时读：任务要开浏览器（§1）、或直取/检索报 `timeout`、或要配 `SCHOLAR_EMAIL`（§2）。

## 1. 标签页会话管理（开始前存基线，结束只关自己开的）

**为什么必须做**：残留标签会自己"活过来"。2026-11-16 实测——万方点「下载」弹出的 `oss.wanfangdata.com.cn` 中转页，用户一点开/切过去，页面 JS 重新执行，**把整批 PDF 又下一次**（浏览器自动加 `(1)` 后缀），13 篇白下 154.6 MB，且重新消耗一次机构下载计数。不清场 = 给用户留一堆会自己跑的页面。

**流程（三步，别省）**

```bash
S="<skill_dir>/scripts/tab_session.py"
D="<workspace>/.workbuddy/tmp/browser-session"

# 1) 控制前：把 user_open_tabs 的返回原样存成基线
python "$S" snapshot --tabs '<user_open_tabs 的 JSON>' --out "$D/baseline.json"

# 2) 收尾：再取一次，存当前
python "$S" snapshot --tabs '<user_open_tabs 的 JSON>' --out "$D/current.json"

# 3) 比对：只关「我开的」，用户中途自己开的一律不碰
python "$S" plan --baseline "$D/baseline.json" --current "$D/current.json" \
    --own-ids "5,7,9" \
    --own-pattern "oss\.wanfangdata|kns\.cnki\.net|ship-research" \
    --keep-pattern "webvpn|登录|login" \
    --json-out "$D/close-plan.json"
```

**为什么默认 `safe` 而不是「不在基线就关」**：用户很可能在我操作期间自己新开标签（查资料、看邮件）。基线比对单独用会把这些误杀，所以判定顺序是「在基线内 → 保留」→「命中 keep-pattern → 保留」→「在我给的 tab_id / own-pattern 里 → 关闭」→「其余 → 标 ASK，默认不关」。只有确认整个会话期间用户没碰浏览器时，才用 `--mode strict`。

**执行纪律**
- 只对 `plan` 输出里 `CLOSE` 的 tab_id 调 `tabs_close`；**串行、间隔 300ms、单次失败重试 1 次**，失败项记进汇报（并行会互相超时）。
- `ASK` 项一律不关，汇报里列出来让用户自己判断。
- **基线文件不存在**（首次或用户中途关掉全部标签）→ 只用 `--own-pattern` + `--own-ids` 判定，拿不准就不关。
- 收尾时顺带汇报：关了几个、留了几个、为什么留。
- 若用户说「不用管标签」可跳过，但要在汇报里说明没清。
- **已知会自己弹页的站点**（务必写进 `--own-pattern`）：万方 `oss.wanfangdata.com.cn`（每点一次下载弹一个，留着会重跑下载）。
- **查扣费/追踪参数时先别关页**：中转页 URL 里的 `transaction` 参数是唯一账单线索，先 `tabs_claim` 读 URL 再关。

## 2. 环境配置（Skill 不内置任何端口或邮箱）

| 项 | 怎么配 | 用途 | 不配会怎样 |
|---|---|---|---|
| **代理** | **默认直连**（不读环境变量）。要代理时用 `--proxy http://127.0.0.1:<端口>`；或 `--auto-proxy`（先直连，网络层失败才降一级到环境变量里的代理） | 直连不通的境外站点（Google Scholar、部分出版商） | 直连超时 → 记 `timeout`，提示用户检查网络；**境外站点再考虑 `--auto-proxy` 或显式 `--proxy`**，不要记 blocked |
| **邮箱** | `--email you@example.com`，或设 `SCHOLAR_EMAIL` | Unpaywall 必需（它要真实联系邮箱，占位会被 422 拒）；Crossref polite pool 用它能拿到更稳的限速 | 自动跳过 Unpaywall，只用 OpenAlex，候选会变少 |

**邮箱用什么**：任何你日常能收信的邮箱都行（QQ、163、Gmail、学校邮箱均可）。它不用于登录，只是 Unpaywall/Crossref 要求的"出问题时能联系到你"的标识，也会被写进请求的 UA。**不要用别人的邮箱，也不要用明显假的地址。**

### 代理四条注意

1. 走代理访问公开 OA 资源 = 正常联网，**不属于"绕过"**（见 `limits.md` §1.1）。
2. **不得轮换代理 IP 规避平台限速或封禁**——那是红线，不是配置问题。
3. 代理若做 TLS 中间人，会出现 `SSLCertVerificationError` → 让用户换 HTTP 代理或关闭证书替换；**不要自己关证书校验**。
4. ★ **代理会摧毁机构授权（本机实测）**：开代理后出口 IP 变成境外节点（本例 Japan/G-Core），ScienceDirect 直接弹「Are you a robot?」并记录该境外 IP，机构订阅失效 + 触发反爬。
   → **分区策略**：公开资源（GS / PubMed / arXiv / OpenAlex）走代理；**机构订阅库（Elsevier / Springer / Wiley / 知网 / 万方）必须直连**。
   → 真下不了时，正确动作是**请用户关代理或给订阅域名加 DIRECT 规则**（具体做法见 `limits.md` §1.1 的 `ProxyOverride` 片段），不是换节点重试。
