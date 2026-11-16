# 订阅型 PDF：落盘边界与 ScienceDirect 批量 ZIP 通道

> 何时读：目标文献在订阅出版商（SD / Springer / Wiley / SAGE）且已有机构权限，要判断「能不能自动拿到 PDF」。
> 配套：`limits.md` §5（单篇为什么走不通的完整排除记录）。

## 1. 结论先行

| 路径 | 能否自动落盘 | 说明 |
|---|---|---|
| 单篇 `View PDF` | **不能** | 进 Edge 内置阅读器，存盘要过系统「另存为」对话框，Agent 碰不到 |
| 多选 ≥2 篇 → `Download N articles` | **能（SD 实测）** | 服务端打包，ZIP 直接落下载目录，无对话框 |
| 单篇的 `pdfft` 直链 curl | 不能 | 即使带签名、无 cookie，仍被站点拦（`Security verification`） |

**三条可自动写盘的路径**只有：OA 直取（L2）、知网下载（L3）、SD 批量 ZIP（L3）。

## 2. ScienceDirect 批量 ZIP 流程

1. 结果页（`/search?qs=...`）每行有勾选框，**选 ≥2 篇**，顶部按钮变成 `Download N articles`
2. 点它 → 生成 `ScienceDirect_articles_<日期>.zip` 落到下载目录（实测 3 篇 = 41 MB，无对话框）
3. 导入：`python "<skill_dir>/scripts/sd_zip.py" --zip <zip> --target-dir "<workspace>/文献/<主题>"`
   —— 解压 + 魔数校验 + MD5 去重 + 按 `NN_` 接续序号落位，ZIP 里的文件名本身就是题名

**标准流程**：SD 上用**主题检索**（别逐篇精确题名）→ 勾选目标 → `Download N articles` → `sd_zip.py` 导入 → 剩下的用 `oa_fetch.py batch` / `checklist` 兜底。

## 3. 限制（全部实测）

- **只选 1 篇不给 ZIP**，会开新标签页把 PDF 渲染在阅读器里 → 单篇目标要**连带选一篇相邻文献**一起下。
- **「全选」只在「一个都没选中」时点一次有效**；已部分选中时点它不生效 → 刷新页面回空状态再点；仍不行就逐行点行勾选框（行勾选框稳定）。
- 打包在服务端做：3 篇 ≈ 8 秒/41 MB，**24 篇 ≈ 80 秒/403 MB**；等 `ScienceDirect_*.zip` 出现，别盯 `.crdownload`。
- 服务器会剔除无权限条目并弹窗说明「24 articles of the 25 requested」→ **权限过滤由站点做，不用自己预判**。

## 4. 可靠性警告（2026-11-15 复测）

机构 IP 直连、页面显示 `<学校> Institutional Access` 时，**25 篇与 2 篇批量下载均返回 `Something went wrong. Please try again.`，72 秒内无 ZIP 落盘**；单篇 `pdfft` 直链仍 403。

→ **批量通道不是恒定能力，随站点/账号状态变化。** 失败时同一操作最多重试一次，然后按 `SKILL.md` §7 交付题录 + 摘要 + 链接并转人工另存，**不要反复死磕**。

## 5. 没有批量通道的站点

Springer / Wiley / SAGE 等单篇仍进阅读器 → 走 `oa_fetch.py checklist` 生成可点击清单，交用户手动另存；存完由 `litadopt.py` 归集改名。

**不要**为"下全"反复试探同站；**也不要**改用无头浏览器反复试（`limits.md` §5 记录了 8 条失败方案，别重走）。
