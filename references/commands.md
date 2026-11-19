# 批量与专项命令

> 由 `SKILL.md` §6 分出：这些命令按需使用，不属于每次任务的必经步骤。参数含义与退出码契约见 `toolchain.md`。

## L2 批量直取

```bash
python "<skill_dir>/scripts/oa_fetch.py" batch --list <DOI清单> --out-dir "<workspace>/.workbuddy/tmp/oa-batch" --interval 2
```

串行 + 间隔（默认 2 秒），逐条输出 reason；某条失败不影响后续条目。适合"一次拿一批 DOI"的场景，**不适合**把同一站点几十篇连续拉——那会把站点会话升温到校验页（`limits.md` §5.1）。

## L1.5 中文期刊官网真 PDF

```bash
python "<skill_dir>/scripts/fetch_cn_journal.py" --csv "<workspace>/文献/00_索引与报告/文献总清单.csv" --dest "<workspace>/文献/中文期刊全文-官网PDF" --out <dir>/cn.json [--force]
```

- CSV 必须有列 `DOI/标识`（也可用 `题名/来源/年份/类别/序号`），编码 UTF-8 带 BOM 亦可。
- **只处理内置刊名映射表里有的 DOI 前缀**；前缀不在表内的行会被跳过，跳过原因写在输出的 `status` / `reason` 字段（`skipped_no_template`），**不再静默丢弃**。
- `类别` 以 A/B 开头的行默认不处理（已人工判定过），需强制时加 `--force`。
- 退出码：全部成功 `0`；有行失败或跳过 `3`。

## 取不到全文 → 可点击清单

```bash
python "<skill_dir>/scripts/oa_fetch.py" checklist --list <DOI清单> --out "<workspace>/文献/待下载清单.md"
```

交用户手动另存用。清单里每行带 DOI、题录与可点链接，用户在浏览器里点一次即可，不需要 agent 再介入。

## 订阅刊批量 ZIP 导入

```bash
python "<skill_dir>/scripts/sd_zip.py" --zip "<下载目录>/ScienceDirect_articles_*.zip" --target-dir "<workspace>/文献/<主题>" [--dry-run]
```

解压 → 魔数校验 → MD5 去重 → `NN_` 落位。先 `--dry-run` 看清单再执行。流程与实测限制见 `sd-batch.md`。

## RIS 题录 + 摘要

```bash
python "<skill_dir>/scripts/ris_meta.py" --ris "<下载目录>/ScienceDirect_citations_*.ris" --md "<workspace>/文献/导出题录与摘要.md"
```

出版商 RIS 导出里的摘要是**原文**，比二手源可靠；拿不到全文时优先走这条。
