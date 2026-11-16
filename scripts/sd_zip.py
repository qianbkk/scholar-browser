# -*- coding: utf-8 -*-
"""sd_zip.py — ScienceDirect「Download N articles」ZIP 导入器

背景：SD 搜索结果页多选（≥2 篇）后点 `Download N articles`，站点会**直接下载一个 ZIP**
（不经过 PDF 阅读器、不弹系统另存为）。这是订阅型 PDF 唯一可自动落盘的通道。

本脚本：解压 ZIP → 魔数校验 → 与目标目录 MD5 去重 → 按 `NN_` 序号改名落位 → 输出 JSON。

用法：
  python sd_zip.py --zip <zip> --target-dir <dir> [--start-index N] [--dry-run]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import zipfile

MAGIC = ((b"%PDF-", "pdf"), (b"KDH", "kdh"), (b"CAJ", "caj"))


def md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sniff(path):
    with open(path, "rb") as f:
        head = f.read(8)
    for m, name in MAGIC:
        if head.startswith(m):
            return name
    return None


def safe_name(name):
    name = os.path.basename(name)
    name = re.sub(r"\.(pdf|caj|kdh)$", "", name, flags=re.I)
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]", "_", name)
    return name.strip()[:140] or "untitled"


def next_index(target):
    mx = 0
    if os.path.isdir(target):
        for f in os.listdir(target):
            m = re.match(r"^(\d+)_", f)
            if m:
                mx = max(mx, int(m.group(1)))
    return mx + 1


def main():
    ap = argparse.ArgumentParser(prog="sd_zip.py", description="导入 ScienceDirect 批量下载 ZIP")
    ap.add_argument("--zip", required=True)
    ap.add_argument("--target-dir", required=True)
    ap.add_argument("--start-index", type=int, help="覆盖起始序号，默认接目录最大值 +1")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-zip", action="store_true", help="保留源 ZIP（默认保留，不自动删）")
    a = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    out = {"zip": a.zip, "target_dir": a.target_dir, "dry_run": a.dry_run,
           "imported": [], "skipped": [], "problems": [], "exit_code": 0}

    if not os.path.isfile(a.zip):
        out["problems"].append({"error": "zip_not_found"})
        out["exit_code"] = 2
        print(json.dumps(out, ensure_ascii=False))
        return 2

    target = a.target_dir
    os.makedirs(target, exist_ok=True)
    idx = a.start_index or next_index(target)

    # 目标目录已有内容的 MD5，用于全局去重
    seen = {}
    for f in os.listdir(target):
        p = os.path.join(target, f)
        if os.path.isfile(p):
            try:
                seen[md5(p)] = f
            except OSError:
                pass

    tmp = os.path.join(target, ".sd_zip_tmp")
    os.makedirs(tmp, exist_ok=True)

    try:
        z = zipfile.ZipFile(a.zip)
    except Exception as e:
        out["problems"].append({"error": "bad_zip:%s" % type(e).__name__})
        out["exit_code"] = 3
        print(json.dumps(out, ensure_ascii=False))
        return 3

    for info in z.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if not re.search(r"\.(pdf|caj|kdh)$", name, re.I):
            out["skipped"].append({"name": name, "reason": "not_document_ext"})
            continue
        base = safe_name(name)
        ext = os.path.splitext(name)[1].lower()
        staging = os.path.join(tmp, base + ext)
        try:
            with z.open(info) as src, open(staging, "wb") as dst:
                dst.write(src.read())
        except Exception as e:
            out["problems"].append({"name": name, "error": "extract:%s" % type(e).__name__})
            continue

        fmt = sniff(staging)
        if not fmt:
            out["skipped"].append({"name": name, "reason": "magic_fail"})
            os.remove(staging)
            continue

        h = md5(staging)
        if h in seen:
            out["skipped"].append({"name": name, "reason": "duplicate_md5", "same_as": seen[h]})
            os.remove(staging)
            continue

        final = "%02d_%s.%s" % (idx, base, fmt)
        dst_path = os.path.join(target, final)
        if a.dry_run:
            out["imported"].append({"planned": final, "bytes": os.path.getsize(staging), "format": fmt})
            # 空跑也要把哈希记进 seen，否则同一 ZIP 里的重复项会被算成「将导入」，
            # 导致 --dry-run 的预测数和真实导入数不一致。
            seen[h] = final
            os.remove(staging)
        else:
            os.replace(staging, dst_path)
            seen[h] = final
            out["imported"].append({"file": final, "bytes": os.path.getsize(dst_path), "format": fmt})
        idx += 1

    try:
        os.rmdir(tmp)
    except OSError:
        pass

    if out["problems"]:
        out["exit_code"] = 5
    print(json.dumps(out, ensure_ascii=False))
    return out["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
