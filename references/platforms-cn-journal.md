# 中文期刊官网 PDF 直取 SOP（本机实测 · 2026-11-15）

> 适用：中文期刊（兵工学报、爆炸与冲击、含能材料、中国舰船研究、力学学报、计算物理、北理工学报…）。
> **优先级高于知网**——官网给的是真 PDF（可直接读），知网多给 KDH/CAJ（需阅读器）。

## 为什么优先走官网

| 通道 | 产出 | 可读性 | 速度 |
|---|---|---|---|
| **期刊官网 `citation_pdf_url` / `href`** | 真 PDF（`%PDF-1.4/1.6`） | ✅ 任何阅读器 | 每篇 3–6 s |
| 知网（机构登录态） | `.caj`，内容多为 **KDH 2.00** | ❌ 需 CAJViewer / E-Study | 每篇 5–10 s |
| 万方 | —— | —— | ❌ CUA 超时，不可脚本化 |

实测：2026-11-15 一轮跑通 **12 篇**（兵工学报 4、爆炸与冲击 8），全部过魔数校验。

## 核心方法：三步

```
S1 用 DOI 拼文章页 URL（按域名前缀映射，见下表）
S2 curl 抓文章页 HTML → 同时解析两类 PDF 线索：
     a) href="....pdf"            ← 真正的 PDF，优先，含 /article/pdf/preview/
     b) <meta name="citation_pdf_url" content="...">  ← 常常就是文章页 URL，别盲信
S3 候选逐个 curl 直取（最多 4 个）→ 读前 4 字节 == b"%PDF" 才算成功
```

## 五个必须避开的坑（全部实测踩过）

### 1. `citation_pdf_url` 通常不是 PDF 地址

本机实测：爆炸与冲击、力学学报的该 meta 值**等于文章页 URL 本身**。
→ 必须**同时**解析 `href` 里的 `.pdf`，两者合并成候选列表，按 `preview` 优先排序，逐个试。

### 2. 绝不能带自定义 UA、不能加 `--compressed`

本机代理（`http://127.0.0.1:<端口>`）会把非默认 UA 打回：
```
upstream connect failed: 不知道这样的主机。(os error 11001)
HTTP/2 502
```
**curl 默认 UA 反而 100% 通。** 命令只保留 `-sL --max-time N -o FILE -w "%{http_code}|%{content_type}" URL`。

### 3. PDF 地址要规范化

页面里常见 `http://www.bzycj.cn:80//cn/article/pdf/preview/xxx.pdf`（带 `:80` 与双斜杠）：
- `^http://([^/:]+):80/+` → `https://\1/`
- 合并多余斜杠
- 非 ASCII 路径用 `quote()`

### 4. 魔数比较

`head = f.read(5)` 后写 `head == b"%PDF"` **永远不成立**（5 字节 vs 4 字节）。用 `head[:4] == b"%PDF"`。

### 5. 重复点击会产生副本

知网点一次下载图标即写盘；连点 N 次 → `(1)~(N)` 后缀的同 MD5 副本。**每篇只点一次**，用 `litadopt.py` 去重。

## 域名前缀 → 文章页模板（实测）

| DOI 前缀 | 期刊 | 模板 | 状态 |
|---|---|---|---|
| `10.11883` | 爆炸与冲击 | `https://www.bzycj.cn/cn/article/doi/{doi}` | ✅ 8/8 |
| `10.12382` | 兵工学报 | `https://www.co-journal.com/zh/article/doi/{doi}` | ✅ 4/4 |
| `10.11943` | 含能材料 | `https://www.energetic-materials.org.cn/hncl/article/html/{tail}` | ⚠ PDF 返回 59B JS 挑战 |
| `10.19693` | 中国舰船研究 | `https://ship-research.com/article/pdf/preview/{doi}.pdf`（**无 www、无 /cn**） | ✅ 2026-11-16 实测（8.96 MB / 15 页） |
| `10.6052` | 力学学报 | `https://lxxb.cstam.org.cn/article/doi/{doi}` | ⚠ PDF 链接返回 HTML |
| `10.19596` | 计算物理 | `https://cjcp.org.cn/cn/article/doi/{doi}` | ⚠ HTTPS 握手失败 |
| `10.14006` | 建筑结构学报 | `https://jzjgxb.com/cn/article/doi/{doi}` | ⚠ 域名解析失败 |
| `10.15918` | 北理工学报 | `https://journal.bit.edu.cn/zr/cn/article/doi/{doi}` | ⚠ 页面 4.7 KB 壳，无 PDF 链接 |
| `10.11809` / `10.15892` | 兵器装备工程学报 / 弹箭与制导学报 | 知网托管，官网无 PDF | → 走知网 |

## 站点异常处置

| 现象 | 处置 |
|---|---|
| 滑块验证（ship-research.com "您的访问频率较高"） | **停机**，不破解；告知用户手动过一次验证后继续 |
| 59 B `<script>` 响应 | JS 挑战页，判"需浏览器"，不要重试 |
| 域名 DNS 失败 | 很可能已换域名，先搜官方站再试，别死磕 |
| 全站 502（`upstream connect failed`） | 代理侧问题，直连（`--noproxy '*'`）也失败则跳过 |

## 中国舰船研究（ship-research.com）专项：DOI 必须完整

2026-11-16 实测踩坑，务必按此顺序：

### 坑 1：DOI 少一位就 404

清单里的 DOI 常被截断/粘连，例如 `10.19693/j.issn.1673-3185.0496` 少了末尾的 `3`，真实 DOI 是 `...04963`。
- 用错误 DOI 拼 `/article/doi/...` → **HTTP 200 但页面是 `Error 404`**（不是 404 状态码，别被迷惑）
- 正确做法：**从检索结果页拿 DOI**，不要用清单里抄来的

### 坑 2：搜索页的「PDF」链接是 JS 绑定，坐标点击会开新标签

- 搜索结果里 `[PDF 9171KB]` 是 `<a>` 但 DOM 快照为空（`dom_cua_get_visible_dom` 返回 `""`），坐标点击**不会**直接落盘，而是**新开一个标签**
- `tabs_list` 看不到它（不在受控集合），必须 `user_open_tabs` → `tabs_claim` → `tab_url` 才能拿到真实 URL
- 从 `tab_url` 拿到的详情页 URL 里就有完整 DOI，这才是可靠来源

### 正确流程

```
S1 tabs_new https://ship-research.com/ → 首页「分类检索」输入题名 → 点放大镜
S2 结果页点「发表时间」排序 → 目标通常在第 1 条
S3 直接 curl 拼好的 PDF 直链（推荐，比点按钮可靠）：
   https://ship-research.com/article/pdf/preview/<完整DOI>.pdf
S4 校验：%PDF 头 + **%%EOF 在末尾** + 字节数 ≈ 页面标注的「PDF xxxxKB」
```

### 坑 3：大文件会被截断，必须给足超时

- `--max-time 60` 只下到 3 MB（页面标注 9171 KB），**没有 `%%EOF`**，`pypdf` 报 `Stream has ended unexpectedly`
- 正确：`curl -sL --max-time 240 --retry 1`，9 MB 文件约需 183 秒
- **判定标准不能只看 `%PDF` 头**——必须同时满足 `b'%%EOF' in data[-8192:]`（用 8 KB 而非 4 KB，尾部可能有填充；完整判定见 `limits.md` §1.0.2）

### 坑 4：curl 高频会触发滑块

- 连续多次 curl 该站会跳 `captcha/page`；**浏览器正常打开无验证**（用户实测确认）
- 一次会话控制在 3 次 curl 以内，间隔 ≥3 秒；触发后改走浏览器，不要重试

## 脚本

`scripts/fetch_cn_journal.py`（本 skill 内置，可改 DOI 清单直接重跑）：

```bash
python <skill_dir>/scripts/fetch_cn_journal.py \
  --csv "文献/00_索引与报告/文献总清单.csv" \
  --dest "文献/中文期刊全文-官网PDF" \
  --out  "./cn-pdf-result.json"
```

脚本行为：读 CSV 中未取得全文的中文 DOI → 按前缀路由 → 抓页面 → 多候选 PDF → 魔数校验 → 落盘 → 写 JSON 结果表。
