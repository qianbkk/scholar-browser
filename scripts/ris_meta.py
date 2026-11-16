# -*- coding: utf-8 -*-
"""ris_meta.py — 解析出版商导出的 RIS 题录（含摘要），输出 JSON / Markdown。

用途：拿不到全文时，用站点官方的「Export citation to RIS」批量拿题录 + 摘要，
     比 Crossref/OpenAlex/S2 更全（实测 ScienceDirect 25 条 RIS 全部带 AB 摘要）。

用法：
  python ris_meta.py --ris <file.ris> [--out <json>] [--md <markdown>] [--match-dois <json>]
"""
import argparse
import json
import os
import re
import sys

FIELD = re.compile(r"^([A-Z][A-Z0-9])\s{2}-\s?(.*)$")


def parse(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        lines = f.read().splitlines()
    records, cur, last = [], None, None
    for line in lines:
        m = FIELD.match(line)
        if m:
            k, v = m.group(1), m.group(2).strip()
            if k == "TY":
                if cur:
                    records.append(cur)
                cur = {}
            if k == "ER":
                if cur:
                    records.append(cur)
                cur, last = None, None
                continue
            if cur is None:
                cur = {}
            last = k
            if v:
                cur.setdefault(k, []).append(v)
        elif cur is not None and last and line.strip():
            # 续行：接到上一个字段末尾
            cur[last][-1] = (cur[last][-1] + " " + line.strip()).strip()
    if cur:
        records.append(cur)

    out = []
    for r in records:
        def one(k, sep=" "):
            return sep.join(r.get(k, [])).strip()

        def many(k):
            return list(r.get(k, []))

        doi = one("DO")
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi).strip()
        out.append({
            "type": one("TY"),
            "title": one("TI") or one("T1") or one("BT") or one("CT"),
            "authors": many("AU") + many("A1") + many("A2"),
            "venue": one("JO") or one("T2") or one("JF"),
            "year": (re.search(r"(19|20)\d{2}", one("PY") + " " + one("Y1")) or [""])[0],
            "volume": one("VL"), "issue": one("IS"),
            "pages": "-".join(x for x in (one("SP"), one("EP")) if x),
            "doi": doi,
            "abstract": one("AB"),
            "keywords": many("KW"),
            "url": one("UR"),
            "publisher": one("PB"),
        })
    return out


def to_markdown(recs, title="导出题录与摘要"):
    L = ["# %s（%d 条）" % (title, len(recs)), "",
         "> 来源：出版商官方 RIS 导出。**摘要为出版商原文**，比第三方 API 更全更准。", ""]
    for i, r in enumerate(recs, 1):
        L += ["## %d. %s" % (i, r["title"] or "(无题名)"), ""]
        L.append("- 作者：%s" % ("；".join(r["authors"][:8]) or "—"))
        L.append("- 来源：%s %s，卷 %s，期 %s，页 %s" % (
            r["venue"] or "?", r["year"] or "?", r["volume"] or "?", r["issue"] or "?", r["pages"] or "?"))
        if r["doi"]:
            L.append("- DOI：[%s](https://doi.org/%s)" % (r["doi"], r["doi"]))
        if r["keywords"]:
            L.append("- 关键词：%s" % "、".join(r["keywords"][:8]))
        L += ["", "**摘要**：", "", "> %s" % (r["abstract"] or "*该条 RIS 未提供摘要*"), ""]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(prog="ris_meta.py")
    ap.add_argument("--ris", required=True)
    ap.add_argument("--out", help="输出 JSON")
    ap.add_argument("--md", help="输出 Markdown")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    recs = parse(a.ris)
    for p in (a.out, a.md):
        if p:
            os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False, indent=1)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write(to_markdown(recs))
    print(json.dumps({
        "ok": True, "ris": a.ris, "count": len(recs),
        "with_abstract": len([r for r in recs if r["abstract"]]),
        "with_doi": len([r for r in recs if r["doi"]]),
        "json": a.out, "md": a.md,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
