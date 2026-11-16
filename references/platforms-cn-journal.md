# 中文期刊官网 PDF 直取 SOP（实测）

> 适用：**有官网全文的中文期刊**（力学、物理、工程类等）。举例：力学学报、计算物理、建筑结构学报、北京理工大学学报、计算力学学报。
> **优先级高于知网**——官网给的是真 PDF（可直接读），知网多给 KDH/CAJ（需阅读器）。

## 为什么优先走官网

| 通道 | 产出 | 可读性 | 速度 |
|---|---|---|---|
| **期刊官网 `citation_pdf_url` / `href`** | 真 PDF（`%PDF-1.4/1.6`） | ✅ 任何阅读器 | 每篇 3–6 s |
| 知网（机构登录态） | `.caj`，内容多为 **KDH 2.00** | ❌ 需 CAJViewer / E-Study | 每篇 5–10 s |
| 万方 | —— | —— | ❌ CUA 超时，不可脚本化 |

实测：一轮跑通 **12 篇**，全部过魔数校验。

## 核心方法：三步

```
S1 用 DOI 拼文章页 URL（按 DOI 前缀映射，见下表）
S2 curl 抓文章页 HTML → 同时解析两类 PDF 线索：
     a) href="....pdf"            ← 真正的 PDF，优先，含 /article/pdf/preview/
     b) <meta name="citation_pdf_url" content="...">  ← 常常就是文章页 URL，别盲信
S3 候选逐个 curl 直取（最多 4 个）→ 读前 4 字节 == b"%PDF" 才算成功
```

## 五个必须避开的坑（全部实测踩过）

### 1. `citation_pdf_url` 通常不是 PDF 地址

实测：多本刊的该 meta 值**等于文章页 URL 本身**。
→ 必须**同时**解析 `href` 里的 `.pdf`，两者合并成候选列表，按 `preview` 优先排序，逐个试。

### 2. 绝不能带自定义 UA、不能加 `--compressed`

本机代理（`http://127.0.0.1:<端口>`）会把非默认 UA 打回：
```
upstream connect failed: 不知道这样的主机。(os error 11001)
HTTP/2 502
```
**curl 默认 UA 反而 100% 通。** 命令只保留 `-sL --max-time N -o FILE -w "%{http_code}|%{content_type}" URL`。

### 3. PDF 地址要规范化

页面里常见 `http://lxxb.cstam.org.cn:80//article/pdf/preview/xxx.pdf`（带 `:80` 与双斜杠）：
- `^http://([^/:]+):80/+` → `https://\1/`
- 合并多余斜杠
- 非 ASCII 路径用 `quote()`

### 4. 魔数比较

`head = f.read(5)` 后写 `head == b"%PDF"` **永远不成立**（5 字节 vs 4 字节）。用 `head[:4] == b"%PDF"`。

### 5. 重复点击会产生副本

知网点一次下载图标即写盘；连点 N 次 → `(1)~(N)` 后缀的同 MD5 副本。**每篇只点一次**，用 `litadopt.py` 去重。

## DOI 前缀 → 文章页模板（内置）

| DOI 前缀 | 期刊 | 模板 | 状态 |
|---|---|---|---|
| `10.6052` | 力学学报 | `https://lxxb.cstam.org.cn/article/doi/{doi}` | ⚠ PDF 链接返回 HTML |
| `10.19596` | 计算物理 | `https://cjcp.org.cn/cn/article/doi/{doi}` | ⚠ HTTPS 握手失败 |
| `10.15918` | 北京理工大学学报 | `https://journal.bit.edu.cn/zr/cn/article/doi/{doi}` | ⚠ 页面 4.7 KB 壳，无 PDF 链接 |
| `10.14006` | 建筑结构学报 | `https://jzjgxb.com/cn/article/doi/{doi}` | ⚠ 域名解析失败 |
| `10.7511` | 计算力学学报 | `https://cvl.cstam.org.cn/article/doi/{doi}` | 待实测 |

> 表里多是"⚠"很正常：**官网可用性随站点改版漂移**，别指望内置表长期有效。表的作用是给出"怎么拼 URL"的范式，不是保证能下。

## 加你自己的刊（用户级映射，不随技能升级丢失）

内置表只放通用刊。你自己的目标刊写进用户级配置，脚本启动时自动合并：

```json
// ~/.scholar-browser/cn_journal_map.json   ← 只在某个项目用就放 <项目>/.scholar-browser/
{
  "10.xxxxx": "https://<刊官网>/cn/article/doi/{doi}",
  "10.yyyyy": "https://<刊官网>/hncl/article/html/{tail}"
}
```

- 占位符：`{doi}` 完整 DOI（已 URL 编码）、`{tail}` DOI 斜杠后的部分
- 生效顺序：`<项目>/.scholar-browser/cn_journal_map.json` > `~/.scholar-browser/cn_journal_map.json` > 内置 5 本
- 文件缺失或 JSON 写错 → 只打印一行 `config skipped`，用内置表继续跑，不会崩
- 查当前生效的路径与合并条数：`python <skill_dir>/scripts/oa_fetch.py config`

## 站点异常处置

| 现象 | 处置 |
|---|---|
| 滑块验证（"您的访问频率较高"） | **停机**，不破解；告知用户手动过一次验证后继续 |
| 59 B `<script>` 响应 | JS 挑战页，判"需浏览器"，不要重试 |
| 域名 DNS 失败 | 很可能已换域名，先搜官方站再试，别死磕 |
| 全站 502（`upstream connect failed`） | 代理侧问题，直连（`--noproxy '*'`）也失败则跳过 |

## 三个跨刊通用坑（与具体刊无关，务必照做）

### 坑 1：DOI 少一位就 404，但 HTTP 仍是 200

清单里的 DOI 常被截断/粘连（例如末尾少一位）。用错误 DOI 拼文章页 →
**HTTP 200，但页面正文是 `Error 404`**，别被状态码迷惑。
- 正确做法：**从检索结果页拿 DOI**，不要用清单里抄来的
- 校验：页面里应能解析到标题或 `.pdf` 链接，两样都没有就判 DOI 错

### 坑 2：搜索页的「PDF」链接常是 JS 绑定，坐标点击会开新标签

- 结果页 `[PDF xxxxKB]` 是 `<a>` 但 DOM 快照可能为空，坐标点击**不落盘**而是**新开标签**
- `tabs_list` 看不到它（不在受控集合），必须 `user_open_tabs` → `tabs_claim` → `tab_url` 才能拿到真实 URL
- 拿到详情页 URL 后从中取完整 DOI，这是最可靠的来源

### 坑 3：大文件会被截断，必须给足超时

- `--max-time 60` 可能只下到 3 MB（页面标注 9000+ KB），**没有 `%%EOF`**，`pypdf` 报 `Stream has ended unexpectedly`
- 正确：`curl -sL --max-time 240 --retry 1`，9 MB 约需 183 秒
- **判定不能只看 `%PDF` 头**——必须同时满足 `b'%%EOF' in data[-8192:]`（8 KB 而非 4 KB，完整判定见 `limits.md` §1.0.2）

## 脚本

`scripts/fetch_cn_journal.py`（本 skill 内置，可改 DOI 清单直接重跑）：

```bash
python <skill_dir>/scripts/fetch_cn_journal.py \
  --csv "文献/00_索引与报告/文献总清单.csv" \
  --dest "文献/中文期刊全文-官网PDF" \
  --out  "./cn-pdf-result.json"
```

脚本行为：读 CSV 中未取得全文的中文 DOI → 按前缀路由（内置 5 本 + 本地映射）→ 抓页面 → 多候选 PDF → 魔数校验 → 落盘 → 写 JSON 结果表。
