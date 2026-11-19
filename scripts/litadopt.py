#!/usr/bin/env python3
"""litadopt - 浏览器下载文献归集工具（Python 3.9+，仅标准库）。

只处理「本轮基线之后新增」且通过文献白名单的文件；源目录的历史文件永不触碰。
所有写操作发生在工作区；--move-sources 只是把源移到隔离区（可逆），不删除。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "litadopt/1"
MAGIC_PDF = b"%PDF-"
MAGIC_CAJ = b"CAJ\x00\x01\x00\x02"
MAGIC_KDH = b"KDH"          # 知网 KDH 2.00（实测文件头 "KDH 2.00"），CAJViewer / E-Study 可开
MAGIC_KDH_ALT = b"\x4b\x44\x48"
DOC_EXTS = {".pdf", ".caj", ".kdh", ".nh", ".teb"}
PENDING_SUFFIXES = (".crdownload", ".part", ".partial", ".download",
                    ".opdownload", ".tmp", ".!ut", ".td")
ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
GUID_DOWNLOADS = ("{374DE290-123F-4565-9164-39C4925E467B}",
                  "{7D83EE9B-2244-4E70-B1F5-5393042AF1E4}")


# ---------- 基础工具 ----------

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


LAST_CODE = {"code": 0}  # main() 用它把 exit_code 传回 shell


def emit(obj, pretty=False):
    try:
        LAST_CODE["code"] = int(obj.get("exit_code") or 0)
    except (TypeError, ValueError):
        LAST_CODE["code"] = 0
    text = json.dumps(obj, ensure_ascii=False,
                      indent=2 if pretty else None,
                      separators=None if pretty else (",", ":"))
    try:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except UnicodeEncodeError:
        sys.stdout.write(json.dumps(obj, ensure_ascii=True) + "\n")


def fail(cmd, code, msg, **extra):
    emit({"schema": SCHEMA, "cmd": cmd, "exit_code": code,
          "error": msg, "ts": utc_now(), **extra})
    raise SystemExit(code)


def md5sum(path, limit=None):
    h = hashlib.md5()
    read = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            if limit is not None and read + len(chunk) > limit:
                chunk = chunk[:limit - read]
            h.update(chunk)
            read += len(chunk)
            if limit is not None and read >= limit:
                break
    return h.hexdigest()


def resolve_root(explicit=None):
    """解析浏览器下载目录。禁止硬编码 C:\\Users\\<user>\\Downloads。"""
    if explicit:
        p = Path(explicit)
        return p, "cli"
    local = os.environ.get("LOCALAPPDATA", "")
    # 0) Edge 组策略 DownloadDirectory
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                k = winreg.OpenKey(hive, r"SOFTWARE\Policies\Microsoft\Edge")
                v, _ = winreg.QueryValueEx(k, "DownloadDirectory")
                k.Close()
                if v:
                    p = Path(os.path.expandvars(v))
                    if p.is_dir():
                        return p, "policy:DownloadDirectory"
            except FileNotFoundError:
                continue
    except Exception:
        pass
    # 1) Edge / Chrome Preferences 显式配置
    for rel in ("Microsoft/Edge/User Data/Default/Preferences",
                "Google/Chrome/User Data/Default/Preferences"):
        fp = Path(local) / rel
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                cfg = json.load(f)
            for key in (("download", "default_directory"),
                        ("savefile", "default_directory")):
                v = cfg.get(key[0], {}).get(key[1]) if isinstance(cfg.get(key[0]), dict) else None
                if v:
                    p = Path(os.path.expandvars(v))
                    if p.is_dir():
                        return p, "preferences:" + ".".join(key)
        except (OSError, ValueError, AttributeError):
            pass
    # 2) Windows 已知文件夹（本机实证来源）
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        for name in GUID_DOWNLOADS:
            try:
                v, _ = winreg.QueryValueEx(key, name)
                p = Path(os.path.expandvars(v))
                if p.is_dir():
                    return p, "known_folder:" + name
            except FileNotFoundError:
                continue
        key.Close()
    except Exception:
        pass
    return Path.home() / "Downloads", "fallback"


def history_index():
    """Edge History 辅助佐证；读不到就返回 None，不作为唯一事实源。"""
    local = os.environ.get("LOCALAPPDATA", "")
    fp = Path(local) / "Microsoft/Edge/User Data/Default/History"
    if not fp.exists():
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro&immutable=1" % fp.as_posix(), uri=True)
        rows = con.execute("SELECT target_path, state, received_bytes, total_bytes FROM downloads").fetchall()
        con.close()
        idx = {}
        for target, state, received, total in rows:
            if not target:
                continue
            name = Path(target).name
            idx.setdefault(name, []).append(bool(state == 1 and received == total and total > 0))
        return idx
    except Exception:
        return None


def state_dir_for(workspace, explicit=None):
    return Path(explicit) if explicit else Path(workspace) / ".litadopt"


def ensure_state(sd):
    for sub in ("baselines", "plans", "batches", "staging", "quarantine", ".trash"):
        (sd / sub).mkdir(parents=True, exist_ok=True)


def log_op(sd, rec):
    rec = {"ts": utc_now(), **rec}
    with open(sd / "operations.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_ops(sd):
    fp = sd / "operations.jsonl"
    if not fp.exists():
        return []
    out = []
    with open(fp, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


class Lock:
    def __init__(self, sd, force=False):
        self.fp = sd / "lock"
        self.force = force
        self.token = uuid.uuid4().hex
        self.held = False

    def __enter__(self):
        if self.fp.exists() and self.force:
            self.fp.unlink()
            log_op(self.fp.parent, {"action": "force_unlock"})
        if self.fp.exists():
            fail("lock", 3, "另一个 litadopt 正在运行；如确认是残留锁，加 --force-unlock",
                 lock=str(self.fp))
        try:
            fd = os.open(str(self.fp), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "token": self.token, "ts": utc_now()}, f)
            self.held = True
        except FileExistsError:
            fail("lock", 3, "锁创建失败", lock=str(self.fp))
        return self

    def __exit__(self, *exc):
        if self.held:
            try:
                data = json.loads(self.fp.read_text(encoding="utf-8"))
                if data.get("token") != self.token:
                    return False
            except Exception:
                return False
            try:
                self.fp.unlink()
            except OSError:
                pass
        return False


def sanitize(s):
    s = ILLEGAL.sub("_", s or "").strip().rstrip(".")
    return s[:120]


def split_name(name):
    stem = Path(name).stem
    stem = re.sub(r"\s*\(\d+\)$", "", stem)
    for ch in ("—", "–", "‐", "－"):
        stem = stem.replace(ch, "-")
    if "_" in stem:
        title, author = stem.rsplit("_", 1)
    else:
        title, author = stem, ""
    return sanitize(title), sanitize(author)


def cnki_meta(tail):
    text = tail.decode("utf-8", "ignore")

    def g(tag):
        m = re.search(r"<%s>(.*?)</%s>" % (tag, tag), text, re.S)
        return m.group(1).strip() if m else ""

    return {"doi": g("Doi"), "filename": g("FileName"),
            "table": g("TableName"), "type": g("Type")}


def probe(path, settle):
    """完成判定 + 格式判定。返回 dict 或 {'status':'pending'|'excluded', 'reason':...}"""
    name = path.name
    lower = name.lower()
    if any(lower.endswith(s) for s in PENDING_SUFFIXES) or name.startswith("~"):
        return {"status": "pending", "reason": "中间态文件"}
    if path.suffix.lower() not in DOC_EXTS:
        return {"status": "excluded", "reason": "非文献扩展名"}
    try:
        st1 = path.stat()
        if settle > 0:
            time.sleep(settle)
        st2 = path.stat()
    except OSError as e:
        return {"status": "pending", "reason": "stat 失败: %s" % e}
    if (st1.st_size, st1.st_mtime_ns) != (st2.st_size, st2.st_mtime_ns):
        return {"status": "pending", "reason": "大小/mtime 仍在变化"}
    size = st2.st_size
    if size <= 0:
        return {"status": "pending", "reason": "0 字节"}
    try:
        with open(path, "rb") as f:
            head = f.read(8)
            f.seek(max(0, size - 1024))
            tail = f.read(1024)
    except OSError as e:
        return {"status": "pending", "reason": "读取失败(可能占用): %s" % e}
    if head.startswith(MAGIC_PDF):
        fmt, ext = "pdf", ".pdf"
    elif head.startswith(MAGIC_CAJ):
        fmt, ext = "caj", ".caj"
    elif head.startswith(MAGIC_KDH):
        # 知网 KDH 2.00：扩展名常给 .caj，内容实为 KDH；CAJViewer/E-Study 可开
        fmt, ext = "kdh", ".kdh"
    else:
        return {"status": "excluded", "reason": "文件头不是 PDF/CAJ/KDH 魔数"}
    trailer_closed = (b"</FileProperty>" in tail or (fmt == "pdf" and b"%%EOF" in tail))
    if not trailer_closed:
        return {"status": "pending", "reason": "尾部闭合哨兵缺失，下载可能未完成"}
    if fmt == "pdf" and b"%%EOF" not in tail:
        # 知网期刊 PDF 尾部带 FileProperty，%%EOF 可能落在末 1KB 之外
        with open(path, "rb") as f:
            f.seek(max(0, size - 8192))
            if b"%%EOF" not in f.read(8192):
                return {"status": "pending", "reason": "PDF 缺少 %%EOF"}
    return {
        "status": "ok", "size": size, "mtime_ns": st2.st_mtime_ns,
        "head": head.decode("latin-1", "ignore"), "format": fmt, "ext": ext,
        "trailer_closed": True, "cnki": cnki_meta(tail),
    }


def existing_md5s(target_dir):
    out = {}
    td = Path(target_dir)
    if not td.is_dir():
        return out
    for p in td.iterdir():
        if p.is_file():
            try:
                out.setdefault(md5sum(p), []).append(p.name)
            except OSError:
                continue
    return out


def next_index(target_dir):
    td = Path(target_dir)
    mx = 0
    if td.is_dir():
        for p in td.iterdir():
            m = re.match(r"^(\d+)_", p.name)
            if m:
                mx = max(mx, int(m.group(1)))
    return mx + 1


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ---------- 命令 ----------

def cmd_init_baseline(a):
    sd = state_dir_for(a.workspace, a.state_dir)
    ensure_state(sd)
    root, via = resolve_root(a.root)
    if not root.is_dir():
        fail("init-baseline", 2, "下载目录不存在", root=str(root))
    entries = []
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        try:
            st = p.stat()
            entries.append({"name": p.name, "size": st.st_size,
                            "mtime_ns": st.st_mtime_ns, "is_dir": p.is_dir()})
        except OSError:
            continue
    sid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    base = {"schema": SCHEMA, "session_id": sid, "created_at_ns": time.time_ns(),
            "root": str(root), "root_resolved_via": via,
            "baseline_ts_ns": time.time_ns(), "entries": entries}
    write_json(sd / "baselines" / (sid + ".json"), base)
    write_json(sd / "baseline.json", base)
    log_op(sd, {"action": "init_baseline", "session_id": sid,
                "root": str(root), "root_resolved_via": via, "entries": len(entries)})
    emit({"schema": SCHEMA, "cmd": "init-baseline", "exit_code": 0,
          "session_id": sid, "root": str(root), "root_resolved_via": via,
          "entries": len(entries), "state_dir": str(sd), "ts": utc_now()})


def cmd_scan_new(a):
    sd = state_dir_for(a.workspace, a.state_dir)
    ensure_state(sd)
    bpath = Path(a.baseline) if a.baseline else sd / "baseline.json"
    if not bpath.exists():
        fail("scan-new", 2, "缺少基线，请先执行 init-baseline", baseline=str(bpath))
    base = load_json(bpath)
    root = Path(a.root) if a.root else Path(base["root"])
    if not root.is_dir():
        fail("scan-new", 2, "下载目录不存在", root=str(root))
    target = Path(a.target_dir) if a.target_dir else Path(a.workspace) / "文献"
    target.mkdir(parents=True, exist_ok=True)
    bmap = {e["name"]: e for e in base["entries"]}
    hist = None if a.no_history else history_index()
    warnings = []
    if hist is None and not a.no_history:
        warnings.append("History 不可读或不存在，已降级为纯文件系统判定")

    items = []
    for p in sorted(root.iterdir(), key=lambda x: (x.stat().st_mtime_ns, x.name)):
        if p.is_dir():
            continue
        name = p.name
        old = bmap.get(name)
        if old:
            try:
                st = p.stat()
                same = (old["size"] == st.st_size and old["mtime_ns"] == st.st_mtime_ns)
            except OSError:
                same = False
            items.append({"name": name, "src": str(p),
                          "status": "historical" if same else "modified",
                          "reason": "基线中已存在" if same else "基线文件被改写，交人工"})
            continue
        pr = probe(p, a.settle)
        rec = {"name": name, "src": str(p), **pr}
        if pr["status"] != "ok":
            items.append(rec)
            continue
        rec["md5"] = md5sum(p)
        rec["title"], rec["author"] = split_name(name)
        confirmed = bool(hist and any(hist.get(name, [])))
        rec["history_confirmed"] = confirmed
        rec["status"] = "new" if confirmed or hist is None else "manual_drop"
        if rec["status"] == "manual_drop":
            rec["reason"] = "基线后出现但无浏览器下载记录，交人工确认"
            if a.allow_unconfirmed:
                rec["status"] = "new"
                rec["confirmed_by_flag"] = True
                rec["reason"] = "无 History 佐证，已由 --allow-unconfirmed 显式确认"
        items.append(rec)

    # 按 MD5 分组：与工作区比对 + 组内取最新为 canonical
    have = existing_md5s(target)
    groups = {}
    for it in items:
        if it.get("md5"):
            groups.setdefault(it["md5"], []).append(it)
    for md5, grp in groups.items():
        grp.sort(key=lambda x: x.get("mtime_ns", 0), reverse=True)
        canonical = grp[0]
        for it in grp:
            it["group_md5"] = md5
            it["group_size"] = len(grp)
            it["canonical"] = it is canonical
            if md5 in have:
                it["status"] = "already_adopted"
                it["workspace_match"] = have[md5]
            elif it is not canonical:
                it["status"] = "duplicate"
                it["reason"] = "同 MD5 重复副本，按 mtime 取最新一份"

    counts = {}
    for it in items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    selected = [it for it in items if it["status"] == "new" and it.get("canonical")]
    sid = base.get("session_id", "unknown")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:4]
    plan_path = sd / "plans" / (stamp + ".json")
    plan = {"schema": SCHEMA, "session_id": sid, "created_at": utc_now(),
            "root": str(root), "target_dir": str(target), "items": items,
            "selected": [i["src"] for i in selected],
            "summary": {"scanned": len(items), **counts, "selected": len(selected)},
            "warnings": warnings}
    write_json(plan_path, plan)
    log_op(sd, {"action": "scan_new", "session_id": sid,
                "plan": str(plan_path), "summary": plan["summary"]})
    code = 3 if any(k in counts for k in ("modified", "manual_drop", "pending")) else 0
    emit({"schema": SCHEMA, "cmd": "scan-new", "exit_code": code,
          "session_id": sid, "root": str(root), "plan": str(plan_path),
          "summary": plan["summary"], "warnings": warnings,
          "items": items, "ts": utc_now()})


def cmd_adopt(a):
    sd = state_dir_for(a.workspace, a.state_dir)
    ensure_state(sd)
    if not a.plan:
        fail("adopt", 2, "缺少 --plan")
    plan = load_json(a.plan)
    target = Path(a.target_dir) if a.target_dir else Path(plan.get("target_dir", Path(a.workspace) / "文献"))
    target.mkdir(parents=True, exist_ok=True)
    batch = "b-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:4]
    staging = sd / "staging" / batch
    quarantine = sd / "quarantine" / batch
    src_map = {}
    source_map = {}
    if a.source_map:
        try:
            source_map = load_json(a.source_map)
        except Exception as e:
            fail("adopt", 2, "--source-map 读取失败: %s" % e)
    selected = [it for it in plan["items"]
                if it.get("status") == "new" and it.get("canonical")]
    movable = [it for it in plan["items"]
               if it.get("status") in ("new", "duplicate", "already_adopted")]

    if a.dry_run:
        emit({"schema": SCHEMA, "cmd": "adopt", "exit_code": 0,
              "dry_run": True, "batch_id": batch,
              "would_adopt": [i["src"] for i in selected],
              "would_move_sources": [i["src"] for i in movable],
              "target_dir": str(target), "ts": utc_now()})
        return

    staging.mkdir(parents=True, exist_ok=True)
    adopted, moved, problems = [], [], []
    idx = next_index(target)
    # ★ 全局 MD5 去重：目标目录已有同内容文件（无论叫什么名）就不再新建副本。
    #   修复前只做“同名比对”，同一 plan 重复 adopt 会生成 19_/20_… 的重复副本。
    seen_md5 = existing_md5s(target)

    for it in selected:
        src = Path(it["src"])
        if not src.is_file():
            problems.append({"src": str(src), "result": "missing"})
            continue
        # TOCTOU：复核与 plan 一致
        try:
            if src.stat().st_size != it["size"] or src.stat().st_mtime_ns != it["mtime_ns"] \
                    or md5sum(src) != it["md5"]:
                problems.append({"src": str(src), "result": "toctou_skip"})
                continue
        except OSError as e:
            problems.append({"src": str(src), "result": "stat_failed:%s" % e})
            continue
        if it["md5"] in seen_md5:
            existing = seen_md5[it["md5"]][0]
            adopted.append({"src": str(src), "dst": str(target / existing), "md5": it["md5"],
                            "format": it["format"], "cnki": it.get("cnki", {}),
                            "name": existing, "skipped": "duplicate_md5"})
            src_map[str(src)] = existing
            continue
        tmp = staging / src.name
        try:
            shutil.copy2(src, tmp)
        except OSError as e:
            problems.append({"src": str(src), "result": "copy_failed:%s" % e})
            continue
        if md5sum(tmp) != it["md5"]:
            tmp.unlink(missing_ok=True)
            problems.append({"src": str(src), "result": "verify_failed"})
            continue
        title, author = it.get("title"), it.get("author")
        cnki = it.get("cnki", {})
        source = source_map.get(src.name) or source_map.get(title) \
            or cnki.get("filename") or cnki.get("type") or "DOC"
        dst_name = "%02d_%s_%s_%s%s" % (idx, title or "untitled", author or "unknown",
                                        sanitize(source), it["ext"])
        dst = target / dst_name
        while dst.exists():
            alt = md5sum(dst) if dst.is_file() else ""
            if alt == it["md5"]:
                break
            idx += 1
            dst_name = "%02d_%s_%s_%s%s" % (idx, title or "untitled", author or "unknown",
                                            sanitize(source), it["ext"])
            dst = target / dst_name
        if not dst.exists():
            shutil.copy2(tmp, dst)
            if md5sum(dst) != it["md5"]:
                dst.unlink(missing_ok=True)
                problems.append({"src": str(src), "result": "verify_failed_final"})
                continue
            idx += 1
            seen_md5.setdefault(it["md5"], []).append(dst_name)
        adopted.append({"src": str(src), "dst": str(dst), "md5": it["md5"],
                        "format": it["format"], "cnki": cnki, "name": dst_name})
        log_op(sd, {"action": "adopted", "batch_id": batch, "session_id": plan.get("session_id"),
                    "src": str(src), "dst": str(dst), "md5": it["md5"],
                    "size": it["size"], "name": dst_name})
        src_map[str(src)] = dst_name

    # 从下载目录移走（可逆，移到隔离区；绝不 unlink）
    if a.move_sources:
        quarantine.mkdir(parents=True, exist_ok=True)
        for chunk_start in range(0, len(movable), a.batch_size):
            chunk = movable[chunk_start:chunk_start + a.batch_size]
            for it in chunk:
                src = Path(it["src"])
                if not src.is_file():
                    continue
                try:
                    st = src.stat()
                    if st.st_size != it.get("size") or st.st_mtime_ns != it.get("mtime_ns") \
                            or md5sum(src) != it.get("md5"):
                        problems.append({"src": str(src), "result": "toctou_skip_move"})
                        continue
                except OSError:
                    problems.append({"src": str(src), "result": "stat_failed_move"})
                    continue
                q = quarantine / src.name
                try:
                    shutil.move(str(src), str(q))
                except OSError as e:
                    problems.append({"src": str(src), "result": "move_failed:%s" % e})
                    continue
                moved.append({"src": str(src), "quarantine": str(q)})
                log_op(sd, {"action": "moved", "batch_id": batch,
                            "session_id": plan.get("session_id"), "src": str(src),
                            "quarantine": str(q), "md5": it.get("md5"), "size": it.get("size")})

    batch_obj = {"batch_id": batch, "session_id": plan.get("session_id"),
                 "created_at": utc_now(), "plan": str(a.plan), "target_dir": str(target),
                 "adopted": adopted, "moved": moved, "problems": problems,
                 "move_sources": bool(a.move_sources)}
    write_json(sd / "batches" / (batch + ".json"), batch_obj)
    shutil.rmtree(staging, ignore_errors=True)
    code = 4 if any(p["result"] == "verify_failed" for p in problems) else (3 if problems else 0)
    if code == 0 and not adopted and movable:  # 有目标却一条都没落位 = 失败，不许静默成功
        code = 3
    emit({"schema": SCHEMA, "cmd": "adopt", "exit_code": code, "batch_id": batch,
          "session_id": plan.get("session_id"), "target_dir": str(target),
          "summary": {"adopted": len(adopted), "moved_to_quarantine": len(moved),
                      "problems": len(problems), "not_moved": len(movable) - len(moved)},
          "adopted": adopted, "moved": moved, "problems": problems,
          "rollback_cmd": "litadopt.py rollback --batch %s --workspace <workspace>" % batch,
          "ts": utc_now()})


def _rolled_back_dsts(sd):
    """已回滚批次里被 trash 掉的 dst；verify 不该把它们算成 missing。"""
    out = set()
    for o in read_ops(sd):
        if o.get("action") != "rollback" or not o.get("batch_id"):
            continue
        try:
            b = json.loads((sd / "batches" / (o["batch_id"] + ".json")).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for ad in b.get("adopted", []):
            if ad.get("dst"):
                out.add(ad["dst"])
    return out


def cmd_verify(a):
    sd = state_dir_for(a.workspace, a.state_dir)
    ops = read_ops(sd)
    rolled_back = _rolled_back_dsts(sd)
    adopted = [o for o in ops if o.get("action") == "adopted" and o.get("dst") not in rolled_back]
    seen, missing, mismatch = {}, [], []
    for o in adopted:
        dst = Path(o["dst"])
        if not dst.is_file():
            missing.append(o["dst"])
            continue
        try:
            h = md5sum(dst)
        except OSError:
            missing.append(o["dst"])
            continue
        if h != o.get("md5"):
            mismatch.append(o["dst"])
        else:
            seen[o["dst"]] = h
    code = 4 if (missing or mismatch) else 0
    emit({"schema": SCHEMA, "cmd": "verify", "exit_code": code,
          "summary": {"records": len(adopted), "matched": len(seen),
                      "missing": len(missing), "mismatch": len(mismatch)},
          "missing": missing, "mismatch": mismatch, "ts": utc_now()})


def cmd_report(a):
    sd = state_dir_for(a.workspace, a.state_dir)
    ops = read_ops(sd)
    counts = {}
    for o in ops:
        counts[o.get("action", "?")] = counts.get(o.get("action", "?"), 0) + 1
    sessions = sorted({o.get("session_id") for o in ops if o.get("session_id")})
    if a.format == "table":
        print("actions        : " + ", ".join("%s=%d" % kv for kv in sorted(counts.items())))
        print("sessions       : " + ", ".join(sessions))
        print("state_dir      : %s" % sd)
        print("operations.jsonl: %d records" % len(ops))
    emit({"schema": SCHEMA, "cmd": "report", "exit_code": 0,
          "sessions": sessions, "actions": counts, "records": len(ops),
          "state_dir": str(sd), "ts": utc_now()})


def cmd_rollback(a):
    sd = state_dir_for(a.workspace, a.state_dir)
    if not a.batch:
        fail("rollback", 2, "缺少 --batch")
    ops = [o for o in read_ops(sd) if o.get("batch_id") == a.batch]
    restored, trashed, problems = [], [], []
    for o in reversed(ops):
        if o.get("action") == "moved":
            q, src = Path(o["quarantine"]), Path(o["src"])
            if not q.is_file():
                problems.append({"quarantine": str(q), "result": "missing"})
                continue
            src.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(q), str(src))
                restored.append(str(src))
            except OSError as e:
                problems.append({"quarantine": str(q), "result": "restore_failed:%s" % e})
        elif o.get("action") == "adopted":
            dst = Path(o["dst"])
            if dst.is_file():
                try:
                    shutil.move(str(dst), str(sd / ".trash" / dst.name))
                    trashed.append(str(dst))
                except OSError as e:
                    problems.append({"dst": str(dst), "result": "trash_failed:%s" % e})
    log_op(sd, {"action": "rollback", "batch_id": a.batch,
                "restored": len(restored), "trashed": len(trashed), "problems": len(problems)})
    emit({"schema": SCHEMA, "cmd": "rollback", "exit_code": 3 if problems else 0,
          "batch_id": a.batch, "restored": restored, "trashed": trashed,
          "problems": problems, "ts": utc_now()})


def cmd_purge(a):
    """清理隔离区（`--move-sources` 留下的源副本）。默认只列清单，需 --confirm 才真删。

    只动 <state>/quarantine/<batch>/ 下的文件，不碰工作区、不碰下载目录、不碰其他批次。
    """
    sd = state_dir_for(a.workspace, a.state_dir)
    qroot = sd / "quarantine"
    if not qroot.is_dir():
        emit({"schema": SCHEMA, "cmd": "purge", "exit_code": 0,
              "items": [], "total_files": 0, "total_bytes": 0,
              "note": "隔离区为空", "ts": utc_now()})
        return
    batches = [a.batch] if a.batch else sorted(p.name for p in qroot.iterdir() if p.is_dir())
    items, total_files, total_bytes = [], 0, 0
    for b in batches:
        qd = qroot / b
        if not qd.is_dir():
            continue
        fs = [p for p in qd.rglob("*") if p.is_file()]
        size = sum(p.stat().st_size for p in fs)
        items.append({"batch": b, "files": len(fs), "bytes": size})
        total_files += len(fs)
        total_bytes += size
    if not a.confirm:
        emit({"schema": SCHEMA, "cmd": "purge", "exit_code": 0, "dry_run": True,
              "items": items, "total_files": total_files, "total_bytes": total_bytes,
              "note": "未加 --confirm，未删除任何文件", "ts": utc_now()})
        return
    removed = []
    for b in batches:
        qd = qroot / b
        if not qd.is_dir():
            continue
        fs = [p for p in qd.rglob("*") if p.is_file()]
        for p in fs:
            try:
                p.unlink()
                removed.append(str(p))
            except OSError:
                pass
        try:
            for d in sorted([x for x in qd.rglob("*") if x.is_dir()], reverse=True):
                d.rmdir()
            qd.rmdir()
        except OSError:
            pass
    log_op(sd, {"action": "purge", "batches": batches,
                "removed": len(removed), "bytes": total_bytes})
    emit({"schema": SCHEMA, "cmd": "purge", "exit_code": 0,
          "items": items, "removed_files": len(removed), "total_bytes": total_bytes,
          "ts": utc_now()})


# ---------- 入口 ----------

def build_parser():
    p = argparse.ArgumentParser(prog="litadopt.py", description="浏览器下载文献归集工具")
    # 公共参数放在子命令之后（与 SKILL.md 示例一致）：
    # litadopt.py <cmd> --workspace <dir> ...
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace", required=True, help="工作区根目录")
    common.add_argument("--state-dir", help="状态目录，默认 <workspace>/.litadopt")
    common.add_argument("--root", help="下载目录，默认自动解析")
    common.add_argument("--target-dir", help="文献归集目录，默认 <workspace>/文献")
    common.add_argument("--json", action="store_true", help="（默认即为 JSON 输出）")
    common.add_argument("--force-unlock", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-baseline", parents=[common])

    s = sub.add_parser("scan-new", parents=[common])
    s.add_argument("--baseline")
    s.add_argument("--settle", type=float, default=1.0, help="大小稳定采样间隔秒，测试可设 0")
    s.add_argument("--no-history", action="store_true")
    s.add_argument("--allow-unconfirmed", action="store_true",
                    help="把无 History 佐证的新文件也视为本次下载；仅在已确认这些文件确由本次下载产生时使用")

    s = sub.add_parser("adopt", parents=[common])
    s.add_argument("--plan", required=True)
    s.add_argument("--source-map", help="JSON：原文件名或题名 -> 中文来源名")
    s.add_argument("--move-sources", action="store_true", help="把源移到隔离区（可逆），需用户已授权")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--batch-size", type=int, default=10)

    sub.add_parser("verify", parents=[common])
    s = sub.add_parser("report", parents=[common])
    s.add_argument("--format", choices=("json", "table"), default="json")
    s = sub.add_parser("rollback", parents=[common])
    s.add_argument("--batch", required=True)
    s = sub.add_parser("purge", parents=[common])
    s.add_argument("--batch", help="只清理该批次；缺省清理全部隔离区")
    s.add_argument("--confirm", action="store_true", help="真正删除；不加则只列清单")
    return p


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    a = build_parser().parse_args()
    sd = state_dir_for(a.workspace, a.state_dir)
    ensure_state(sd)
    with Lock(sd, force=a.force_unlock):
        handlers = {"init-baseline": cmd_init_baseline, "scan-new": cmd_scan_new,
                    "adopt": cmd_adopt, "verify": cmd_verify,
                    "report": cmd_report, "rollback": cmd_rollback,
                    "purge": cmd_purge}
        try:
            handlers[a.cmd](a)
        except SystemExit:
            raise
        except Exception as e:
            fail(a.cmd, 1, "%s: %s" % (type(e).__name__, e))
    return LAST_CODE["code"]


if __name__ == "__main__":
    sys.exit(main() or 0)
