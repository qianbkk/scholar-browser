# -*- coding: utf-8 -*-
"""配置分层解析（内部模块，不是 CLI）：项目级 > 用户级 > 内置模板。

为什么要分层：
  * 技能目录是可替换的"程序"（会被 zip 覆盖、git pull、SkillHub 更新），
    个人配置放进去必然在升级时丢失；
  * 同一个技能可能在多个课题/项目里用，需要"跨项目默认 + 单项目覆盖"。

查找顺序（后者覆盖前者）
  1. <skill_dir>/...                内置模板，随技能发行，只读
  2. ~/.scholar-browser/            用户级（跨项目、跨升级；长住）
  3. <workspace>/.scholar-browser/  项目级（单项目特化）
  另有 legacy 位置（<skill_dir>/ 里的 *.local.*）仍被识别，但会提示迁移。

环境变量
  SCHOLAR_CONFIG_DIR   覆盖用户级目录（测试 / 多身份切换用）
  SCHOLAR_WORKSPACE    覆盖项目根目录探测起点

对外函数（全部只读，从不写文件）
  user_dir() / project_dir() / find() / report()
"""
import os
from pathlib import Path

WORKDIR_NAME = ".scholar-browser"
LEGACY_TRIAGE = "references/triage.local.md"          # 旧位置，仅兼容
LEGACY_JSON_TPL = "scripts/%s.local.json"             # 旧位置，仅兼容


def user_dir():
    env = os.environ.get("SCHOLAR_CONFIG_DIR")
    if env:
        return Path(os.path.expanduser(env))
    return Path.home() / WORKDIR_NAME


def project_dir(start=None, exclude=None):
    """向上找项目根：优先已存在的 .scholar-browser；否则以 .git / .workbuddy 为界。

    exclude：要跳过的目录（传 skill_dir）——技能自己也是 git 仓库，
    不跳过的话在技能目录里跑脚本会把自己的 .git 误判成项目根。
    返回候选路径（可能不存在），供诊断显示"预期位置"；找不到边界返回 None。
    """
    raw = start or os.environ.get("SCHOLAR_WORKSPACE") or os.getcwd()
    p = Path(raw).resolve()
    ex = Path(exclude).resolve() if exclude else None
    for cand in [p, *p.parents]:
        if ex and (cand == ex or ex in cand.parents):
            continue
        if (cand / WORKDIR_NAME).is_dir():
            return cand / WORKDIR_NAME
        if (cand / ".git").exists() or (cand / ".workbuddy").is_dir():
            return cand / WORKDIR_NAME
    return None


def effective_project_dir(start=None, skill_dir=None):
    """项目级目录；与用户级重合（或落在技能目录内）时视为"无项目级"。"""
    pj = project_dir(start, exclude=skill_dir)
    if pj is None:
        return None
    try:
        if pj.resolve() == user_dir().resolve():
            return None
    except Exception:
        pass
    return pj


def find(name, skill_dir, legacy=None, start=None):
    """按 项目 > 用户 > legacy > 内置 顺序找文件。

    返回 (path|None, source)，source ∈ project / user / legacy-local / none。
    """
    candidates = []
    pj = project_dir(start)
    if pj is not None:
        candidates.append((pj / name, "project"))
    candidates.append((user_dir() / name, "user"))
    if legacy:
        candidates.append((Path(skill_dir) / legacy, "legacy-local"))
    for path, src in candidates:
        if path.is_file():
            return path, src
    return None, "none"


def all_paths(name, skill_dir, legacy=None, start=None):
    """诊断用：列出该配置项的所有候选位置及是否存在。"""
    out = []
    pj = effective_project_dir(start, skill_dir)
    if pj is not None:
        out.append({"layer": "project", "path": str(pj / name), "exists": (pj / name).is_file()})
    ud = user_dir()
    out.append({"layer": "user", "path": str(ud / name), "exists": (ud / name).is_file()})
    if legacy:
        lp = Path(skill_dir) / legacy
        out.append({"layer": "legacy-local", "path": str(lp), "exists": lp.is_file()})
    return out


def hint_legacy(source, layer):
    """legacy 位置被命中时给出一次性提示文案（返回 None 表示不需要提示）。"""
    if source != "legacy-local":
        return None
    return ("[deprecated] 正在使用技能目录内的本地配置（%s）；"
            "建议迁移到 %s，否则技能升级时会被覆盖。" % (layer, user_dir()))


def find_all(name, skill_dir, legacy=None, start=None):
    """合并型配置用：按 低 → 高 优先级返回**所有存在**的文件。

    顺序：legacy-local → user → project。调用方依次覆盖，后者赢。
    """
    out = []
    if legacy:
        lp = Path(skill_dir) / legacy
        if lp.is_file():
            out.append((lp, "legacy-local"))
    ud = user_dir() / name
    if ud.is_file():
        out.append((ud, "user"))
    pj = effective_project_dir(start, skill_dir)
    if pj is not None and (pj / name).is_file():
        out.append((pj / name, "project"))
    return out
