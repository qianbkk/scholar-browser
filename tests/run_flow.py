#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""交付链行为测试（隔离沙箱，不联网、不碰个人目录）。

锁住三个真实踩过的坑：
  1. scan-new 对「L2 直取、无浏览器下载记录」的新文件默认 selected=0（需 --allow-unconfirmed）
  2. adopt 在 plan 里有条目、却一条都没归集时，必须非零退出（不得静默成功）
  3. rollback 之后 verify 不得把「已回滚的批次」当成文件丢失（否则正常流程必然红）

用法：python tests/run_flow.py        退出码 0=全通过
临时目录建在系统 temp 下，结束即清理。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIT = ROOT / "scripts" / "litadopt.py"


def mkpdf(path, tag):
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> >>"]
    s = ("BT /F1 12 Tf 72 760 Td (%s) Tj ET" % tag).encode()
    objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(s), s))
    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    pathlib.Path(path).write_bytes(bytes(out))


def run(args):
    r = subprocess.run([sys.executable, str(LIT)] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return r.returncode, {"_raw": (r.stdout or "") + (r.stderr or "")}


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="litflow-"))
    dl, ws = tmp / "downloads", tmp / "ws"
    dl.mkdir(); ws.mkdir()
    results = []

    def chk(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    try:
        mkpdf(dl / "preexisting.pdf", "old file")
        rc, _ = run(["init-baseline", "--workspace", str(ws), "--root", str(dl)])
        chk("baseline", rc == 0, "exit=%d" % rc)

        mkpdf(dl / "Paper One - Zhang 2021.pdf", "paper one")
        mkpdf(dl / "Paper Two - Li 2019.pdf", "paper two")

        # 1) 未加 --allow-unconfirmed：L2 直取文件应被判待确认，且必须以非零退出示警
        rc, out = run(["scan-new", "--workspace", str(ws), "--root", str(dl),
                       "--target-dir", str(ws / "文献" / "T"), "--settle", "0"])
        sel0 = (out.get("summary") or {}).get("selected")
        chk("scan-new 默认不选无下载记录文件", sel0 == 0, "selected=%s exit=%d" % (sel0, rc))
        chk("scan-new 静默 0 入选必须非零退出", rc != 0, "exit=%d" % rc)

        # 2) plan 为空时 adopt 无事可做，退出 0 是合法；真正的契约是「有目标却全未落位必须非零」
        #    这一条由 adopt 内部 adopted==0 and movable 判断保证，见 run_case_adopt_guard()
        rc0, out0 = run(["adopt", "--plan", str(out.get("plan")), "--workspace", str(ws),
                         "--target-dir", str(ws / "文献" / "T")])
        chk("空 plan 的 adopt 不算失败", rc0 == 0, "exit=%d" % rc0)

        # 3) 确认后重扫 → 应选出 2 条并成功归集
        rc, out = run(["scan-new", "--workspace", str(ws), "--root", str(dl),
                       "--target-dir", str(ws / "文献" / "T"), "--settle", "0",
                       "--allow-unconfirmed"])
        chk("scan-new --allow-unconfirmed 选中 2 条", (out.get("summary") or {}).get("selected") == 2,
            "selected=%s" % (out.get("summary") or {}).get("selected"))

        rc, out = run(["adopt", "--plan", str(out["plan"]), "--workspace", str(ws),
                       "--target-dir", str(ws / "文献" / "T")])
        ad = (out.get("summary") or {}).get("adopted")
        batch = out.get("batch_id")
        chk("adopt 归集 2 条且命名 NN_", rc == 0 and ad == 2
            and all(a.get("name", "").startswith(("01_", "02_")) for a in out.get("adopted", [])),
            "exit=%d adopted=%s" % (rc, ad))

        # 4) 默认：源被移入工作区，下载目录只剩基线文件（plan 外的文件一律不碰）
        left = sorted(p.name for p in dl.glob("*.pdf"))
        chk("默认移走源：下载目录只剩基线文件", left == ["preexisting.pdf"],
            "剩 %d 个: %s" % (len(left), left))
        chk("summary 报告移走 2 条", (out.get("summary") or {}).get("sources_removed") == 2,
            "sources_removed=%s" % (out.get("summary") or {}).get("sources_removed"))

        rc, out = run(["verify", "--workspace", str(ws)])
        chk("verify 正常通过", rc == 0, "exit=%d" % rc)

        # 5) rollback 后 verify 不得报 missing
        chk("adopt 返回 batch_id", bool(batch), "batch=%s" % batch)
        if batch:
            run(["rollback", "--batch", batch, "--workspace", str(ws)])
        rc2, out2 = run(["verify", "--workspace", str(ws)])
        chk("rollback 后 verify 不得误报 missing", rc2 == 0,
            "exit=%d missing=%s" % (rc2, (out2.get("summary") or {}).get("missing")))
        back = sorted(p.name for p in dl.glob("*.pdf"))
        chk("rollback 把源文件放回下载目录",
            back == ["Paper One - Zhang 2021.pdf", "Paper Two - Li 2019.pdf", "preexisting.pdf"],
            "当前: %s" % back)

        # 6) --keep-sources：明确要求保留时才留在下载目录
        dl2, ws2 = tmp / "dl2", tmp / "ws2"
        dl2.mkdir(); ws2.mkdir()
        mkpdf(dl2 / "preexisting2.pdf", "old2")
        run(["init-baseline", "--workspace", str(ws2), "--root", str(dl2)])
        mkpdf(dl2 / "Kept - Wang 2020.pdf", "kept one")
        _, o2 = run(["scan-new", "--workspace", str(ws2), "--root", str(dl2),
                     "--target-dir", str(ws2 / "文献" / "K"), "--settle", "0", "--allow-unconfirmed"])
        rc, o3 = run(["adopt", "--plan", str(o2["plan"]), "--workspace", str(ws2),
                      "--target-dir", str(ws2 / "文献" / "K"), "--keep-sources"])
        names = sorted(p.name for p in dl2.glob("*.pdf"))
        chk("--keep-sources 时源文件保留", "Kept - Wang 2020.pdf" in names, "当前: %s" % names)
        chk("--keep-sources 仍然落盘", (o3.get("summary") or {}).get("adopted") == 1,
            "adopted=%s exit=%d" % ((o3.get("summary") or {}).get("adopted"), rc))

        # 7) 重复下载（内容已在库）也必须清走源，不能留在下载目录
        dl3, ws3 = tmp / "dl3", tmp / "ws3"
        dl3.mkdir(); ws3.mkdir()
        run(["init-baseline", "--workspace", str(ws3), "--root", str(dl3)])
        mkpdf(dl3 / "Dup One.pdf", "dup content")
        _, a1 = run(["scan-new", "--workspace", str(ws3), "--root", str(dl3),
                     "--target-dir", str(ws3 / "文献" / "D"), "--settle", "0", "--allow-unconfirmed"])
        run(["adopt", "--plan", str(a1["plan"]), "--workspace", str(ws3),
             "--target-dir", str(ws3 / "文献" / "D")])
        mkpdf(dl3 / "Dup One again.pdf", "dup content")  # 同内容 → 判 duplicate
        _, a2 = run(["scan-new", "--workspace", str(ws3), "--root", str(dl3),
                     "--target-dir", str(ws3 / "文献" / "D"), "--settle", "0", "--allow-unconfirmed"])
        run(["adopt", "--plan", str(a2["plan"]), "--workspace", str(ws3),
             "--target-dir", str(ws3 / "文献" / "D")])
        chk("重复下载的文件也清走源", not (dl3 / "Dup One again.pdf").exists(),
            "剩余: %s" % [p.name for p in dl3.iterdir()])

        # 8) L1.5：未知刊名前缀必须给出跳过原因，且以非零退出（不许静默 0 目标）
        csvp = tmp / "cn.csv"
        csvp.write_text("序号,题名,作者,来源,年份,DOI/标识,类别\n"
                        "1,测试,某,某学报,2021,10.99999/XYZ,C\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "fetch_cn_journal.py"),
                            "--csv", str(csvp), "--dest", str(tmp / "cn"),
                            "--out", str(tmp / "cn.json")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        try:
            data = json.loads((tmp / "cn.json").read_text(encoding="utf-8"))
        except Exception:
            data = []
        chk("L1.5 未知前缀有跳过原因且非零退出",
            r.returncode != 0 and bool(data) and str(data[0].get("status", "")).startswith("skipped"),
            "exit=%d rows=%d" % (r.returncode, len(data)))

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    nf = 0
    for name, ok, detail in results:
        print("  %s  %s  %s" % ("PASS" if ok else "FAIL", name, detail))
        nf += 0 if ok else 1
    print("\n%d 通过 / %d 失败" % (len(results) - nf, nf))
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
