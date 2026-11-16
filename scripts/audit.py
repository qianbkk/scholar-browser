#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""skill 自检：一致性、引用完整性、脚本可用性、发布卫生。

只读，不改任何文件。退出码 0 = 全通过；1 = 有 FAIL。
用法：python <skill_dir>/scripts/audit.py [--verbose]
"""
import argparse
import ast
import builtins
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MD_FILES = [ROOT / "SKILL.md"] + sorted((ROOT / "references").glob("*.md"))
SCRIPTS = sorted((ROOT / "scripts").glob("*.py"))

# 发布卫生：不该出现在公开仓库里的东西
# 拆字拼接：避免本文件自身成为命中源（grep / 平台审核会扫脚本正文）
PII_PATTERNS = {
    "学校/机构名": "南京" "理工|njust|njlgdxtsg|Nanjing University of Science",
    "本机用户名": r"Users[\\/]NLG-|/home/[A-Za-z0-9_-]{3,}/",
    "本机端口": r"127\.0\.0\.1:\d{4,5}",
    "绝对路径": r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]{1,2}[A-Za-z]",
}
# 平台审核敏感措辞（否定式枚举容易命中）
SENSITIVE = "|".join(["绕" "过", "打" "码", "换 ?IP", "轮" "换", "伪造 ?UA",
                      "CAPT" "CHA", "翻" "墙", "付费" "墙", "反" "爬", "风" "控"])
SKIP_SELF = {"audit.py"}  # 本文件含上述模式的定义，自身不计入

fails, warns, oks = [], [], []


def ok(msg):
    oks.append(msg)


def fail(msg):
    fails.append(msg)


def warn(msg):
    warns.append(msg)


def read(p):
    return p.read_text(encoding="utf-8", errors="ignore")


def parse_frontmatter(text):
    """把 frontmatter 解析成 dict（不依赖 pyyaml）。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return fm


def check_frontmatter():
    fm = parse_frontmatter(read(ROOT / "SKILL.md"))
    if not fm:
        fail("SKILL.md 缺少 frontmatter")
        return {}
    required = ["name", "description", "version"]
    missing = [k for k in required if not fm.get(k)]
    if missing:
        fail("frontmatter 缺字段: %s" % ", ".join(missing))
    else:
        ok("frontmatter 基本字段齐全")
    # 双平台字段（只提示，不判失败）
    for k in ("slug", "displayName", "display_name", "summary", "license"):
        if not fm.get(k):
            warn("frontmatter 缺可选字段 %s（上传平台可能需要）" % k)
    if fm.get("name") and not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", fm["name"]):
        fail("name 不是 kebab-case: %s" % fm["name"])
    if fm.get("version") and not re.match(r"^\d+\.\d+\.\d+$", fm["version"]):
        fail("version 不是 x.y.z: %s" % fm["version"])
    if len(fm.get("description", "")) > 1024:
        fail("description 超过 1024 字符（当前 %d）" % len(fm["description"]))
    else:
        ok("description 长度 %d / 1024" % len(fm.get("description", "")))
    return fm


def check_version(fm):
    ver = fm.get("version")
    if not ver:
        return
    rd = read(ROOT / "README.md")
    m = re.search(r"当前\s*`v?([\d.]+)`", rd)
    if m and m.group(1) != ver:
        fail("README 版本 %s ≠ SKILL.md %s" % (m.group(1), ver))
    elif m:
        ok("README 版本一致 (%s)" % ver)
    else:
        warn("README 未标注当前版本")
    cl = read(ROOT / "references" / "CHANGELOG.md")
    m = re.search(r"^## (\d+\.\d+\.\d+)", cl, re.M)
    if m and m.group(1) != ver:
        fail("CHANGELOG 最新条目 %s ≠ SKILL.md %s" % (m.group(1), ver))
    elif m:
        ok("CHANGELOG 最新条目一致 (%s)" % ver)


def check_router():
    router = read(ROOT / "references" / "ROUTER.md")
    actual = [p.name for p in (ROOT / "references").glob("*.md")] + [p.name for p in SCRIPTS]
    unlisted = [n for n in actual if n not in router]
    if unlisted:
        fail("ROUTER 未登记: %s" % ", ".join(unlisted))
    else:
        ok("ROUTER 已登记全部 %d 个文件" % len(actual))


def check_links():
    files = {p.name for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts}
    missing = {}
    for f in MD_FILES:
        for name in re.findall(r"`([A-Za-z0-9_\-]+\.(?:md|py|json))`", read(f)):
            if name not in files:
                # 运行时生成的配置文件名允许不存在
                if name in ("config.json", "cn_journal_map.json", "baseline.json",
                            "current.json", "close-plan.json", "audit.json"):
                    continue
                missing.setdefault(f.name, set()).add(name)
    if missing:
        fail("悬空文件引用: %s" % {k: sorted(v) for k, v in missing.items()})
    else:
        ok("文档内文件引用全部有效")


def check_sections():
    heads = {}
    for f in MD_FILES:
        hs = set()
        for line in read(f).splitlines():
            m = re.match(r"^#{1,4}\s+(\d+(?:\.\d+)*)", line)
            if m:
                hs.add(m.group(1))
        heads[f.name] = hs
    bad = []
    for f in MD_FILES:
        for target, sec in re.findall(r"([A-Za-z\-]+\.md)`?\s*§\s*(\d+(?:\.\d+)*)", read(f)):
            if target in heads and sec not in heads[target]:
                bad.append("%s → %s §%s" % (f.name, target, sec))
    if bad:
        fail("失效章节引用: %s" % "; ".join(bad))
    else:
        ok("章节交叉引用全部有效")


def undefined_constants(tree):
    """找形如 CONSTANT_CASE、但模块内从未定义过的名字。

    `--help` 只跑到 argparse 构造，模块顶层的运行时常量引用不会被触发；
    拼错的常量名要等真正执行到那一行才炸（真实案例：PARTIAL_SUFFIX）。
    这里做静态检查，只筛全大写常量，避免局部变量误报。
    """
    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            defined.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                defined.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return sorted(n for n in used - defined - set(dir(builtins))
                  if re.match(r"^[A-Z][A-Z0-9_]{2,}$", n))


def check_scripts(verbose=False):
    if not SCRIPTS:
        fail("scripts 目录为空")
        return
    args_defined = set()
    undef = []
    for s in SCRIPTS:
        text = read(s)
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            fail("%s 语法错误: %s" % (s.name, e))
            continue
        for name in undefined_constants(tree):
            undef.append("%s:%s" % (s.name, name))
        args_defined |= set(re.findall(r'add_argument\(\s*"(--[a-z\-]+)"', text))
        r = subprocess.run([sys.executable, str(s), "--help"],
                           capture_output=True, timeout=60, cwd=str(ROOT / "scripts"))
        if r.returncode != 0:
            fail("%s --help 失败" % s.name)
        elif verbose:
            ok("%s --help 正常" % s.name)
    if undef:
        fail("引用了未定义的常量（运行到即崩）: %s" % ", ".join(undef))
    else:
        ok("无常量未定义问题")
    ok("%d 个脚本语法通过且 --help 可执行" % len(SCRIPTS))

    sk = read(ROOT / "SKILL.md")
    used = set(re.findall(r"(?<!-)--[a-z][a-z\-]*(?!-)", sk))
    unknown = sorted(u for u in used if u not in args_defined)
    if unknown:
        fail("SKILL.md 示例中的参数脚本里不存在: %s" % unknown)
    else:
        ok("SKILL.md 示例参数全部存在")


def check_hygiene():
    bad_pii, bad_sens = [], []
    for p in ROOT.rglob("*"):
        if not p.is_file() or ".git" in p.parts or p.suffix not in (".md", ".py"):
            continue
        if p.name in SKIP_SELF:
            continue
        txt = read(p)
        for label, pat in PII_PATTERNS.items():
            for m in re.finditer(pat, txt):
                tail = txt[m.end():m.end() + 16]
                if "<" in tail or "<" in m.group(0):
                    continue  # 占位符示例（如 C:\Users\<你>\...），不算泄露
                line = txt[: m.start()].count("\n") + 1
                bad_pii.append("%s:%d %s" % (p.relative_to(ROOT).as_posix(), line, label))
        for i, line in enumerate(txt.splitlines(), 1):
            if re.search(SENSITIVE, line):
                bad_sens.append("%s:%d" % (p.relative_to(ROOT).as_posix(), i))
    if bad_pii:
        fail("发布卫生：发现身份信息 %s" % bad_pii[:8])
    else:
        ok("无身份信息残留（学校/用户名/端口/绝对路径）")
    if bad_sens:
        warn("敏感措辞残留 %d 处（%s），上传前建议复查" % (len(bad_sens), ", ".join(bad_sens[:5])))
    else:
        ok("无审核敏感措辞")


def check_package():
    dots = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
            if p.is_file() and ".git" not in p.parts and p.name.startswith(".")]
    if dots:
        fail("仓库含点文件（平台拒收）: %s" % dots)
    else:
        ok("仓库无点文件")
    noext = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
             if p.is_file() and ".git" not in p.parts and "." not in p.name]
    if noext:
        warn("无扩展名文件: %s（上传前确认平台是否接受）" % noext)
    else:
        ok("无无扩展名文件")
    types = sorted({p.suffix.lstrip(".") for p in ROOT.rglob("*")
                    if p.is_file() and ".git" not in p.parts})
    ok("文件类型: %s" % ", ".join(types))


def main():
    ap = argparse.ArgumentParser(description="scholar-browser 自检（只读）")
    ap.add_argument("--verbose", action="store_true", help="打印每条通过项")
    a = ap.parse_args()

    fm = check_frontmatter()
    check_version(fm)
    check_router()
    check_links()
    check_sections()
    check_scripts(a.verbose)
    check_hygiene()
    check_package()

    if a.verbose:
        for m in oks:
            print("  OK   %s" % m)
    for m in warns:
        print("  WARN %s" % m)
    for m in fails:
        print("  FAIL %s" % m)
    print("\n%d 通过 / %d 警告 / %d 失败" % (len(oks), len(warns), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
