# -*- coding: utf-8 -*-
"""中文期刊官网 PDF 自动抓取（通用版，本机实测 2026-11-15）。

用法：
    python fetch_cn_journal.py --csv <文献总清单.csv> --dest <输出目录> [--out result.json] [--force]

关键实测结论（改动前先读 references/platforms-cn-journal.md）：
  * citation_pdf_url 的 meta 值常是文章页本身 → 必须同时解析 href 里的 .pdf
  * curl 不能带自定义 UA、不能加 --compressed（本机代理会打回 502）
  * PDF 地址里 http://host:80//path 要规范化成 https://host/path
  * 魔数比较用 head[:4] == b"%PDF"
"""
import argparse, csv, hashlib, json, os, re, subprocess, sys, time
from urllib.parse import quote

TPL = {
    "10.11883": "https://www.bzycj.cn/cn/article/doi/{doi}",          # 爆炸与冲击
    "10.12382": "https://www.co-journal.com/zh/article/doi/{doi}",     # 兵工学报
    "10.6052":  "https://lxxb.cstam.org.cn/article/doi/{doi}",         # 力学学报
    "10.19596": "https://cjcp.org.cn/cn/article/doi/{doi}",            # 计算物理
    "10.15918": "https://journal.bit.edu.cn/zr/cn/article/doi/{doi}",  # 北京理工大学学报
    "10.11943": "https://www.energetic-materials.org.cn/hncl/article/html/{tail}",  # 含能材料
    "10.19693": "https://ship-research.com/cn/article/doi/{doi}",      # 中国舰船研究（cjsr.com.cn 已废）
    "10.14006": "https://jzjgxb.com/cn/article/doi/{doi}",             # 建筑结构学报
    "10.11993": "https://sxwrxtxb.xml-journal.net/cn/article/doi/{doi}",  # 水下无人系统学报
    "10.7511":  "https://cvl.cstam.org.cn/cn/article/doi/{doi}",       # 计算力学学报
}


def curl(url, out=None, timeout=60, referer=None):
    cmd = ["curl", "-sL", "--max-time", str(timeout),
           "-w", "%{http_code}|%{content_type}", "-o", out or "-", url]
    if referer:
        cmd[1:1] = ["-e", referer]
    p = subprocess.run(cmd, capture_output=True)
    code, _, ct = p.stdout.decode("utf-8", "ignore").strip().partition("|")
    return code, ct


def norm(u, base):
    u = u.strip().replace("&amp;", "&")
    if u.startswith("//"):
        u = "https:" + u
    elif u.startswith("/"):
        u = re.match(r"(https?://[^/]+)", base).group(1) + u
    u = re.sub(r"^http://([^/:]+):80/+", r"https://\1/", u)
    u = re.sub(r"^http://", "https://", u)
    u = re.sub(r"(?<!:)//+", "/", u)
    return quote(u, safe=":/?&=#%+,;@!$'()*[]")


def pdf_candidates(html, page):
    cands = re.findall(r'(?:href|src)="([^"]*?\.pdf[^"]*)"', html, re.I)
    cands += re.findall(r'<meta[^>]+name="citation_pdf_url"[^>]+content="([^"]+)"', html)
    seen, out = set(), []
    for c in cands:
        u = norm(c, page)
        if u in seen:
            continue
        seen.add(u)
        if re.search(r"(cover|mulu|contents|qikanjieshao|notice)", u, re.I):
            continue
        out.append(u)
    out.sort(key=lambda u: 0 if "/pdf/preview/" in u else (1 if ".pdf" in u.split("?")[0] else 2))
    return out[:4]


def load(csv_path, force):
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    seen, out = set(), []
    for r in rows:
        doi = (r.get("DOI/标识") or "").strip()
        if not doi.startswith("10.") or doi in seen:
            continue
        pref = ".".join(doi.split("/")[0].split(".")[:2])
        if pref not in TPL:
            continue
        cat = r.get("类别", "")
        if not force and (cat.startswith("A") or cat.startswith("B")):
            continue
        seen.add(doi)
        out.append({"doi": doi, "title": r.get("题名", ""), "src": r.get("来源", ""), "seq": r.get("序号", "")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--out", default="cn-pdf-result.json")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.dest, exist_ok=True)
    ts = load(a.csv, a.force)
    print("targets:", len(ts))
    res = []
    for i, t in enumerate(ts, 1):
        doi, title = t["doi"], t["title"]
        pref = ".".join(doi.split("/")[0].split(".")[:2])
        page = TPL[pref].format(doi=quote(doi, safe="/."), tail=doi.split("/")[-1])
        rec = dict(t, page=page, status="", pdf_url="", bytes=0, md5="", saved="", reason="")
        tmp = os.path.join(os.path.dirname(os.path.abspath(a.out)), "_page.html")
        code, ct = curl(page, tmp, timeout=40)
        html = ""
        if os.path.exists(tmp):
            html = open(tmp, "rb").read().decode("utf-8", "ignore")
            os.remove(tmp)
        if code != "200":
            rec.update(status="page_%s" % code, reason="文章页 HTTP %s" % code)
            print(i, doi, rec["status"]); res.append(rec); time.sleep(1.2); continue
        cands = pdf_candidates(html, page)
        if not cands:
            rec.update(status="no_pdf_link", reason="页面无 .pdf 链接（可能需浏览器/JS）")
            print(i, doi, "no_pdf_link"); res.append(rec); time.sleep(1.2); continue
        fn = re.sub(r'[\\/:*?"<>|]', "", title)[:70] + "_" + doi.split("/")[-1] + ".pdf"
        path = os.path.join(a.dest, fn)
        ok, tried = False, []
        for pdf in cands:
            code2, ct2 = curl(pdf, path, timeout=90, referer=page)
            head = b""
            if os.path.exists(path):
                head = open(path, "rb").read(5)
            tried.append("%s:%s" % (code2, ct2[:18]))
            if code2 == "200" and head[:4] == b"%PDF":
                data = open(path, "rb").read()
                rec.update(status="ok", pdf_url=pdf, bytes=len(data),
                           md5=hashlib.md5(data).hexdigest(), saved=path)
                print(i, doi, "OK", round(len(data) / 1024, 1), "KB"); ok = True
                break
            if os.path.exists(path):
                os.remove(path)
            time.sleep(0.8)
        if not ok:
            rec.update(status="pdf_fail", pdf_url=cands[0], reason=" | ".join(tried))
            print(i, doi, "pdf_fail", " | ".join(tried)[:56])
        res.append(rec)
        time.sleep(1.2)

    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    from collections import Counter
    print("\nok %d/%d" % (sum(1 for r in res if r["status"] == "ok"), len(res)))
    print(Counter(r["status"] for r in res))


if __name__ == "__main__":
    main()
