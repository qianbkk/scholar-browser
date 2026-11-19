#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""行为级回归用例执行器（只读，不改任何文件）。

用法：
    python tests/run_cases.py            # 全跑
    python tests/run_cases.py --only A   # 只跑 A 组（前缀匹配 case id）
    python tests/run_cases.py --json     # 机器可读输出

依赖：优先用 PyYAML；没有则用内置极简解析器（仅支持本文件用到的 schema）。
分成两类断言，含义不同，不要混：
  * reason_classify  —— 真行为：直接调用 scripts/oa_fetch.py 的 _sniff() 喂响应特征，看分类结果
  * 其余 contract 组  —— 文档合同：断言 SKILL.md 里的决议表/降级出口/优先级是否与脚本实际一致
退出码：0 全通过；1 有失败（CI 用 --only + 退出码即可 block）。
"""
import argparse
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"
CASES = ROOT / "tests" / "cases.yaml"


def load_cases(path):
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        pass
    # 极简回退：只解析 "cases:" 下的 "- id: / kind: / key: value" 与一层 input
    cases, cur, sub = [], None, None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("meta:") or line.startswith("#") or not line.strip():
            continue
        if line.lstrip().startswith("- id:"):
            cur = {"id": line.split(":", 1)[1].strip()}
            cases.append(cur)
            sub = None
            continue
        if cur is None:
            continue
        m = re.match(r"^(\s+)(\w+):\s*(.*)$", line)
        if not m:
            continue
        indent, key, val = m.groups()
        if key == "input" and not val:
            cur["input"], sub = {}, "input"
            continue
        if sub == "input" and len(indent) >= 6:
            cur["input"][key] = _scalar(val)
            continue
        sub = None
        if val == "":
            cur[key] = []
        elif val.startswith("[") or val.startswith('"'):
            cur[key] = _scalar(val)
        else:
            cur[key] = _scalar(val)
    return {"cases": cases}


def _scalar(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [_scalar(x) for x in v[1:-1].split(",") if x.strip()]
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if re.match(r"^-?\d+$", v):
        return int(v)
    return v


def load_oa():
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))  # oa_fetch import 同目录 _config
    spec = importlib.util.spec_from_file_location("oa_fetch", ROOT / "scripts" / "oa_fetch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def script_reasons():
    """从 oa_fetch.py 里精确抽出「能作为 reason 出现」的字面量。

    只认三种写法，避免把 `cf_clearance`/`purchase` 这类嗅探关键词误当 reason：
      1. `_sniff()` 里的 `return "..."`
      2. `rec["reason"] = "..."` / `out["reason"] = "..."`
      3. 字典字面量 `"reason": "..."`
    """
    import ast
    src = (ROOT / "scripts" / "oa_fetch.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    codes = set()

    class V(ast.NodeVisitor):
        def __init__(self):
            self.in_sniff = 0

        def visit_FunctionDef(self, node):
            if node.name == "_sniff":
                self.in_sniff += 1
                self.generic_visit(node)
                self.in_sniff -= 1
            else:
                self.generic_visit(node)

        def visit_Return(self, node):
            if self.in_sniff and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                codes.add(node.value.value)
            self.generic_visit(node)

        def visit_Assign(self, node):
            for t in node.targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant)
                        and t.slice.value == "reason"
                        and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                    codes.add(node.value.value)
            self.generic_visit(node)

        def visit_Dict(self, node):
            for k, v in zip(node.keys, node.values):
                if (isinstance(k, ast.Constant) and k.value == "reason"
                        and isinstance(v, ast.Constant) and isinstance(v.value, str)):
                    codes.add(v.value)
            self.generic_visit(node)

    V().visit(tree)
    return {c for c in codes if re.match(r"^[a-z][a-z0-9_%]*$", c) and c != "ok"}


def norm(code):
    return code.replace("_%d", "_")


def frontmatter_desc():
    txt = SKILL.read_text(encoding="utf-8")
    m = re.search(r"^description:\s*(.+)$", txt, re.M)
    return m.group(1).strip() if m else ""


def run(cases, only=None):
    results = []
    oa = None

    def add(cid, kind, ok, detail):
        results.append({"id": cid, "kind": kind, "pass": bool(ok), "detail": detail})

    for c in cases:
        cid, kind = c.get("id", "?"), c.get("kind", "?")
        if only and not cid.startswith(only):
            continue

        if kind == "reason_classify":
            if oa is None:
                oa = load_oa()
            inp = c["input"]
            head = str(inp["head"]).encode("utf-8", "replace")
            got = oa._sniff(head, int(inp["status"]), inp.get("ctype") or "", "https://example.com/x")
            add(cid, kind, got == c["expect"], "expect=%s got=%s" % (c["expect"], got))

        elif kind == "top_reason":
            if oa is None:
                oa = load_oa()
            rs = str(c["input"]["reasons"]).split("|") if c["input"].get("reasons") else []
            got = oa._top_reason(rs)
            add(cid, kind, got == c["expect"], "expect=%s got=%s" % (c["expect"], got))

        elif kind == "taxonomy_coverage":
            sk = SKILL.read_text(encoding="utf-8")
            codes = sorted(script_reasons())
            missing = [x for x in codes if norm(x) not in sk]
            add(cid, kind, not missing, "未在 SKILL.md 出现的 reason: %s（共 %d 个码）"
                % (missing, len(codes)))

        elif kind == "taxonomy_toplevel":
            sk = SKILL.read_text(encoding="utf-8")
            missing = [t for t in c["must_include"] if t not in sk]
            add(cid, kind, not missing, "缺 %s" % missing if missing else "顶层 reason 均可分流")

        elif kind in ("degraded_signal", "degraded_signal_shape"):
            sk = SKILL.read_text(encoding="utf-8")
            toks = c.get("tokens") or [c.get("token")]
            missing = [t for t in toks if t not in sk]
            add(cid, kind, not missing, "缺 %s" % missing if missing else "降级信号已定义")

        elif kind == "cn_priority_order":
            sk = SKILL.read_text(encoding="utf-8")
            # 找同时含三者、且描述中文优先级的行
            lines = [l for l in sk.splitlines() if all(t in l for t in c["order"])]
            if not lines:
                add(cid, kind, False, "没有一行同时交代 官网/万方/知网 的先后")
            else:
                l = lines[0]
                pos = [l.find(t) for t in c["order"]]
                add(cid, kind, pos == sorted(pos), "顺序位置=%s（%s）" % (pos, l.strip()[:60]))

        elif kind == "cn_skip_l2":
            sk = SKILL.read_text(encoding="utf-8")
            hit = [l for l in sk.splitlines() if all(t in l for t in c["tokens"])]
            add(cid, kind, bool(hit), "命中行: %s" % (hit[0].strip()[:60] if hit else "无"))

        elif kind == "source_token":
            f = ROOT / c["file"]
            txt = f.read_text(encoding="utf-8") if f.is_file() else ""
            missing = [t for t in c["tokens"] if t not in txt]
            add(cid, kind, not missing, "缺 %s" % missing if missing else "%s 已标注" % c["file"])

        elif kind == "contract_token":
            sk = SKILL.read_text(encoding="utf-8")
            missing = [t for t in c["tokens"] if t not in sk]
            add(cid, kind, not missing, "缺 %s" % missing if missing else "契约已写明")

        elif kind == "description_has":
            d = frontmatter_desc()
            missing = [a for a in c["anchors"] if a not in d]
            add(cid, kind, not missing, "缺锚点 %s（当前 %d 字符）" % (missing, len(d)))

        elif kind == "description_max":
            d = frontmatter_desc()
            add(cid, kind, len(d) <= c["max_chars"],
                "当前 %d 字符 / 上限 %d" % (len(d), c["max_chars"]))

        elif kind == "skill_md_max":
            n = SKILL.stat().st_size
            add(cid, kind, n <= c["max_bytes"], "当前 %d 字节 / 上限 %d" % (n, c["max_bytes"]))

        elif kind == "no_crlf":
            # Windows 脚本写文件会把 LF 静默变 CRLF，字节数凭空 +行数，F03 会假性逼近上限
            bad = []
            for name in c["files"]:
                b = (ROOT / name).read_bytes()
                if b"\r\n" in b:
                    bad.append("%s(%d)" % (name, b.count(b"\r\n")))
            add(cid, kind, not bad, "含 CRLF: %s" % bad if bad else "全部为 LF")

        else:
            add(cid, kind, False, "未知用例类型")

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只跑 id 前缀匹配的用例")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    doc = load_cases(CASES)
    cases = doc.get("cases") or []
    th = int((doc.get("meta") or {}).get("block_threshold", 0))
    res = run(cases, a.only)

    if a.json:
        print(json.dumps({"results": res, "threshold": th}, ensure_ascii=False, indent=1))
    else:
        for r in res:
            print("  %s  %-22s %-4s %s" % ("PASS" if r["pass"] else "FAIL", r["id"], "", r["detail"]))
        nf = sum(1 for r in res if not r["pass"])
        print("\n%d 通过 / %d 失败（阈值 %d）" % (len(res) - nf, nf, th))
    return 1 if sum(1 for r in res if not r["pass"]) > th else 0


if __name__ == "__main__":
    sys.exit(main())
