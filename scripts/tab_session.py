#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""标签页会话管理：控制前存基线，控制后只关自己开的。

MCP 的标签工具只能在对话里调用，本脚本负责「记账 + 比对」：
  1. 我拿到 user_open_tabs 的返回后，用 snapshot 存成基线；
  2. 结束时再存一份当前快照；
  3. plan 比对两份，输出「关哪些、留哪些」。

用法：
  python tab_session.py snapshot --tabs '<MCP 返回的 JSON>' --out <dir>/baseline.json
  python tab_session.py snapshot --tabs '<MCP 返回的 JSON>' --out <dir>/current.json
  python tab_session.py plan --baseline <dir>/baseline.json --current <dir>/current.json \
      --keep-pattern "webvpn|登录|login" --json-out <dir>/close-plan.json

退出码：0 正常；2 参数/文件问题。
"""
import argparse
import json
import os
import re
import sys
import time


def _norm_tabs(payload):
    """把 MCP 返回统一成 [{tab_id, title, url}]，兼容几种字段名。"""
    if isinstance(payload, dict):
        for key in ("tabs", "result", "data", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        return []
    out = []
    for t in payload:
        if not isinstance(t, dict):
            continue
        tab_id = t.get("tab_id", t.get("tabId", t.get("id")))
        title = t.get("title", "") or ""
        url = t.get("url", t.get("link", "")) or ""
        if tab_id is None:
            continue
        out.append({"tab_id": str(tab_id), "title": title, "url": url})
    return out


def cmd_snapshot(args):
    raw = args.tabs
    if raw == "-":
        raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        print("ERROR: --tabs 不是合法 JSON：%s" % e, file=sys.stderr)
        return 2
    tabs = _norm_tabs(payload)
    data = {"captured_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(tabs), "tabs": tabs}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("snapshot %d tabs -> %s" % (len(tabs), args.out))
    return 0


def cmd_plan(args):
    def load(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("tabs", [])

    base = load(args.baseline)
    cur = load(args.current)
    base_ids = {t["tab_id"] for t in base}
    keep_re = re.compile(args.keep_pattern, re.I) if args.keep_pattern else None
    own_re = re.compile(args.own_pattern, re.I) if args.own_pattern else None
    own_ids = {s.strip() for s in args.own_ids.split(",") if s.strip()} if args.own_ids else set()

    close, keep, unsure = [], [], []
    for t in cur:
        tid = t["tab_id"]
        if tid in base_ids:
            keep.append(dict(t, reason="控制前已存在"))
        elif keep_re and (keep_re.search(t.get("url", "")) or keep_re.search(t.get("title", ""))):
            keep.append(dict(t, reason="命中保留规则"))
        elif tid in own_ids:
            close.append(dict(t, reason="我创建的（显式 tab_id）"))
        elif own_re and (own_re.search(t.get("url", "")) or own_re.search(t.get("title", ""))):
            close.append(dict(t, reason="命中「我操作产生」特征"))
        elif args.mode == "strict":
            close.append(dict(t, reason="不在基线内（strict 模式）"))
        else:
            # safe 模式：来历不明的一律不动，交给用户决定
            unsure.append(dict(t, reason="不在基线、也不像是我开的 → 默认保留"))

    plan = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": args.mode,
        "baseline_count": len(base),
        "current_count": len(cur),
        "close": close,
        "keep": keep,
        "uncertain": unsure,
    }
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
    print("模式 %s | 基线 %d / 当前 %d -> 关闭 %d，保留 %d，待定 %d"
          % (args.mode, len(base), len(cur), len(close), len(keep), len(unsure)))
    for t in close:
        print("  CLOSE  %-6s %s" % (t["tab_id"], (t["title"] or t["url"])[:74]))
    for t in keep:
        print("  KEEP   %-6s %s  [%s]" % (t["tab_id"], (t["title"] or t["url"])[:62], t["reason"]))
    for t in unsure:
        print("  ASK    %-6s %s  [来历不明，默认不关]" % (t["tab_id"], (t["title"] or t["url"])[:56]))
    return 0


def main():
    ap = argparse.ArgumentParser(description="标签页会话基线/比对")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="保存一份标签快照")
    s.add_argument("--tabs", required=True, help="MCP user_open_tabs 返回的 JSON，或 - 读 stdin")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("plan", help="比对基线，生成关闭清单")
    p.add_argument("--baseline", required=True)
    p.add_argument("--current", required=True)
    p.add_argument("--keep-pattern", default="", help="命中的标签保留（正则，对 url/title）")
    p.add_argument("--own-pattern", default="",
                   help="「我操作产生的标签」特征域名/标题（正则），如 oss\\.wanfangdata|cnki\\.net\\.cn")
    p.add_argument("--own-ids", default="", help="我创建的 tab_id 列表，逗号分隔")
    p.add_argument("--mode", choices=["safe", "strict"], default="safe",
                   help="safe=来历不明的标签不动（默认）；strict=不在基线就关")
    p.add_argument("--json-out", default="")
    p.set_defaults(func=cmd_plan)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
