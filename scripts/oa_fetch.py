#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OA 直取器（L2 层）：标识符 -> OA 候选 -> 闸门校验 -> 落盘。

零依赖，仅用 Python 标准库。设计原则来自实测与调研：
- 不信任文件后缀，只信任 status + Content-Type + 文件头 %PDF 魔数 + 尾部闭合。
- 串行、限速、可缓存；请求按工具自身标识发出，不做浏览器伪装。
- 失败要给出**可编码的原因**（login_wall / cloudflare / captcha / paywall / html_landing ...），
  供上层决定是否回退到登录态浏览器（L3）。

子命令：
  resolve --doi <DOI> [--email <mail>]        解析 OA 候选（不下载）
  fetch   --doi <DOI> --out <path>            解析并逐个尝试下载，过闸门才落盘
  fetch   --url <url> --out <path>            直接给 URL 走同一套闸门
  probe   --url <url>                         只探测前若干字节，不落盘
  check   --file <path>                       校验本地文件是否真 PDF

退出码：0 成功 / 2 参数或 IO / 3 有候选但全部未通过 / 4 校验失败 / 1 其他异常
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import _config  # 同目录内部模块：配置分层解析（项目 > 用户 > 内置）

PDF_MAGIC = b"%PDF-"
# 未下完的临时后缀：命中即判 partial，不做完整性校验
PARTIAL_SUFFIX = (".part", ".partial", ".crdownload", ".download", ".tmp")
UA_TMPL = "scholar-browser/3.0 (academic OA fetch; contact: {email})"
DEFAULT_UA = "scholar-browser/3.0 (academic OA fetch)"

# 代理策略（默认直连）：
#   ""            = 强制直连（**默认**，不读环境变量，避免被系统代理悄悄改出口 IP）
#   "http://..."  = 显式代理
#   None          = 跟随环境变量 HTTPS_PROXY/HTTP_PROXY（仅在用户显式要求时）
PROXY = ""
# 直连失败（网络层）时是否自动降级到环境变量里的代理，且只降一级、只重试一次。
AUTO_PROXY = False
_PROXY_FALLBACK_NOTE = []


def env_proxy():
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        v = os.environ.get(k)
        if v:
            return v
    return ""


def set_proxy(value, auto=False):
    """value: '' 直连 / None 跟随环境变量 / 'http://host:port' 显式代理。auto=直连失败降级。"""
    global PROXY, AUTO_PROXY
    PROXY = value
    AUTO_PROXY = bool(auto)


def proxy_notes():
    return list(_PROXY_FALLBACK_NOTE)


def _open(req, timeout):
    """统一出口：默认直连；开启 auto 时仅在网络层失败后降级环境代理一次。

    HTTPError（403/404/429…）是业务结果，**不降级**——那是平台在回答，不是网络不通。
    """
    global _PROXY_FALLBACK_NOTE

    def direct():
        return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout)

    def via(px):
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": px, "https": px})).open(req, timeout=timeout)

    if AUTO_PROXY and PROXY == "":
        try:
            return direct()
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            px = env_proxy()
            if not px:
                raise
            note = "direct_failed(%s)→env_proxy %s" % (type(e).__name__, px)
            _PROXY_FALLBACK_NOTE.append(note)
            sys.stderr.write("[proxy] %s\n" % note)
            return via(px)

    if PROXY is None:
        return urllib.request.urlopen(req, timeout=timeout)
    if PROXY == "":
        return direct()
    return via(PROXY)


def jout(obj, code=0):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return code


def _top_reason(reasons):
    """顶层 reason：单候选失败时直接给出该候选的原因，多候选才用 no_candidate_passed。

    否则调用方拿到 `no_candidate_passed` 无法判断该停机还是该转 L3（2026-11-18 实测踩过）。
    """
    rs = [r for r in (reasons or []) if r]
    if not rs:
        return "no_candidate"
    if len(rs) == 1:
        return rs[0]
    return "no_candidate_passed"


def ua(email):
    return UA_TMPL.format(email=email) if email else DEFAULT_UA


def _req(url, email=None, timeout=25, extra_accept=None):
    headers = {
        "User-Agent": ua(email),
        "Accept": extra_accept or "application/pdf,application/json;q=0.9,*/*;q=0.8",
    }
    return urllib.request.Request(url, headers=headers)


def _sniff(head, status, ctype, final_url):
    """根据响应头与正文片段判定失败原因。返回值可直接写进 JSON 供决策。"""
    if head.startswith(PDF_MAGIC):
        return "ok"
    text = head[:6000].decode("utf-8", "replace").lower()
    if status == 401:
        return "need_auth"
    if status == 403:
        if "just a moment" in text or "cf_clearance" in text or "challenge-platform" in text:
            return "cloudflare_challenge"
        return "forbidden_403"
    if status == 429:
        return "rate_limited_429"
    if status == 404:
        return "not_found_404"
    if status >= 500:
        return "server_error_%d" % status
    if "captcha" in text or "turnstile" in text or "人机验证" in text:
        return "captcha"
    if ctype == "application/json":
        return "json_error_body"
    if ctype in ("text/html", "application/xhtml+xml"):
        if "<html" in text or "<!doctype" in text:
            if "sign in" in text or "log in" in text or "登录" in text:
                return "login_wall"
            if "get access" in text or "purchase" in text or "subscribe" in text:
                return "paywall_landing"
            return "html_landing"
    if ctype == "application/octet-stream":
        return "not_pdf_octet"
    return "not_pdf"


def failure_hint(reasons, proxy_mode=None):
    """失败时给出可执行的下一步。只生成提示，不改 reason 码、不改契约。

    设计要点：403 与网络错的最常见误判是「这篇没有 OA 版本」——实际往往是
    出口或通道问题。这里把「可试什么」直接写进输出，避免调用方误判后收手。
    """
    rs = [r or "" for r in (reasons or [])]
    joined = " ".join(rs)
    if any(r.startswith("network_error") for r in rs):
        return "network_error: 可显式指定代理重试（--proxy <url>），或换候选源"
    if "cloudflare_challenge" in rs or "captcha" in rs:
        return "challenge: 属站点人机校验，停机转 L3 浏览器逐页操作；不要重复撞同一页"
    if "forbidden_403" in joined:
        if proxy_mode == "direct(default)":
            return "forbidden_403: 当前为默认直连；可显式指定代理重试（--proxy <url>），或换 OA 绿版候选；403 不重试同一 URL"
        return "forbidden_403: 已用代理仍 403，多为站点指纹或机构出口限制；换候选或交 L3，不要反复重试"
    if "login_wall" in rs or "paywall_landing" in rs or "need_auth" in rs:
        return "access: 需机构权限，转 L3 用你自己的浏览器；拿不到则回填题录+摘要+链接"
    if any(r.startswith("not_found") or r in ("html_landing", "not_pdf", "json_error_body") for r in rs):
        return "landing: 页面不是 PDF，换候选；耗尽后转 L3 或回填题录"
    return "见 attempts[].reason 分流；同一动作不要重试超过 1 次"


def probe(url, email=None, timeout=25, nbytes=8192):
    rec = {
        "url": url,
        "status": None,
        "final_url": None,
        "content_type": None,
        "content_length": None,
        "magic": None,
        "valid": False,
        "reason": "",
    }
    try:
        with _open(_req(url, email, timeout), timeout) as r:
            rec["status"] = r.status
            rec["final_url"] = r.geturl()
            rec["content_type"] = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            cl = r.headers.get("Content-Length")
            rec["content_length"] = int(cl) if cl and cl.isdigit() else None
            head = r.read(nbytes)
            rec["magic"] = head[:8].decode("latin-1", "replace")
            rec["reason"] = _sniff(head, r.status, rec["content_type"], rec["final_url"])
            rec["valid"] = rec["reason"] == "ok"
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        rec["final_url"] = e.geturl() if hasattr(e, "geturl") else url
        try:
            body = e.read(6000)
        except Exception:
            body = b""
        rec["content_type"] = (e.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        rec["magic"] = body[:8].decode("latin-1", "replace")
        rec["reason"] = _sniff(body, e.code, rec["content_type"], rec["final_url"])
    except urllib.error.URLError as e:
        rec["reason"] = "network_error:%s" % type(getattr(e, "reason", e)).__name__
    except Exception as e:
        rec["reason"] = "network_error:%s" % type(e).__name__
    return rec


def _download(url, out_path, email=None, timeout=120, max_mb=150):
    """流式下载 + 魔数闸门。先写 .part，通过校验才原子改名。"""
    rec = {
        "url": url,
        "status": None,
        "final_url": None,
        "content_type": None,
        "bytes": 0,
        "sha256": None,
        "magic": None,
        "end_marker": False,
        "page_estimate": None,
        "valid": False,
        "reason": "",
    }
    tmp = out_path + ".part"
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    try:
        with _open(_req(url, email, timeout), timeout) as r:
            rec["status"] = r.status
            rec["final_url"] = r.geturl()
            rec["content_type"] = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            cl = r.headers.get("Content-Length")
            expect = int(cl) if cl and cl.isdigit() else None
            h = hashlib.sha256()
            first = b""
            tail = b""
            total = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    if not first:
                        first = chunk[:8192]
                        if not first.startswith(PDF_MAGIC):
                            rec["magic"] = first[:8].decode("latin-1", "replace")
                            rec["reason"] = _sniff(first, r.status, rec["content_type"], rec["final_url"])
                            f.close()
                            _safe_unlink(tmp)
                            return rec
                        rec["magic"] = first[:8].decode("latin-1", "replace")
                    f.write(chunk)
                    h.update(chunk)
                    total += len(chunk)
                    tail = (tail + chunk)[-8192:]
                    if total > max_mb * 1024 * 1024:
                        f.close()
                        _safe_unlink(tmp)
                        rec["reason"] = "too_large"
                        rec["bytes"] = total
                        return rec
            rec["bytes"] = total
            rec["sha256"] = h.hexdigest()
            rec["end_marker"] = b"%%EOF" in tail
            rec["page_estimate"] = tail.count(b"/Type /Page") + tail.count(b"/Type/Page")
            if expect is not None and total != expect:
                rec["reason"] = "size_mismatch"
                _safe_unlink(tmp)
                return rec
            if total < 5120:
                rec["reason"] = "too_small_%d" % total
                _safe_unlink(tmp)
                return rec
            if not rec["end_marker"]:
                rec["reason"] = "truncated_no_eof"
                _safe_unlink(tmp)
                return rec
            rec["valid"] = True
            rec["reason"] = "ok"
            os.replace(tmp, out_path)
    except urllib.error.HTTPError as e:
        rec["status"] = e.code
        try:
            body = e.read(6000)
        except Exception:
            body = b""
        rec["content_type"] = (e.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        rec["magic"] = body[:8].decode("latin-1", "replace")
        rec["reason"] = _sniff(body, e.code, rec["content_type"], rec["final_url"] or url)
        _safe_unlink(tmp)
    except urllib.error.URLError as e:
        rec["reason"] = "network_error:%s" % type(getattr(e, "reason", e)).__name__
        _safe_unlink(tmp)
    except Exception as e:
        rec["reason"] = "network_error:%s" % type(e).__name__
        _safe_unlink(tmp)
    return rec


def _safe_unlink(p):
    try:
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass


def _get_json(url, email=None, timeout=25):
    try:
        with _open(_req(url, email, timeout, "application/json"), timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as e:
        return None, "http_%d" % e.code
    except Exception as e:
        return None, "network_error:%s" % type(e).__name__


def _get_text(url, email=None, timeout=25):
    try:
        with _open(_req(url, email, timeout, "text/plain,*/*"), timeout) as r:
            return r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return None, "http_%d" % e.code
    except Exception as e:
        return None, "network_error:%s" % type(e).__name__


def norm_doi(s):
    s = (s or "").strip()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I)
    return s.strip()


def resolve_candidates(doi, email=None, use_cache=None, quiet=False):
    """按可靠性排序返回候选：Unpaywall -> OpenAlex -> arXiv -> doi.org 落地页 meta。"""
    doi = norm_doi(doi)
    out = {"doi": doi, "candidates": [], "sources": {}, "notes": []}
    seen = set()

    def add(url, via, **kw):
        if not url:
            return
        u = url.strip()
        if not u.lower().startswith(("http://", "https://")):
            return
        key = u.split("#")[0]
        if key in seen:
            return
        seen.add(key)
        rec = {"url": u, "via": via}
        rec.update({k: v for k, v in kw.items() if v})
        out["candidates"].append(rec)

    # 1) Unpaywall（需要真实 email，无 key）
    if email:
        d, err = _get_json(
            "https://api.unpaywall.org/v2/%s?email=%s" % (urllib.parse.quote(doi, safe="/"), urllib.parse.quote(email))
        )
        if d:
            out["sources"]["unpaywall"] = {
                "is_oa": d.get("is_oa"),
                "oa_status": d.get("oa_status"),
                "genre": d.get("genre"),
                "year": d.get("year"),
            }
            best = d.get("best_oa_location") or {}
            add(best.get("url_for_pdf"), "unpaywall_best_pdf", version=best.get("version"), host=best.get("host_type"))
            add(best.get("url"), "unpaywall_best_landing", version=best.get("version"))
            for loc in (d.get("oa_locations") or []):
                add(loc.get("url_for_pdf"), "unpaywall_oa_pdf", version=loc.get("version"), host=loc.get("host_type"))
        else:
            out["notes"].append("unpaywall:%s" % err)
    else:
        out["notes"].append("unpaywall:skipped_no_email")

    # 2) OpenAlex
    oa_url = "https://api.openalex.org/works/https://doi.org/%s" % urllib.parse.quote(doi, safe="/")
    if email:
        oa_url += "?mailto=" + urllib.parse.quote(email)
    d, err = _get_json(oa_url, email)
    if d:
        o = d.get("open_access") or {}
        out["sources"]["openalex"] = {
            "is_oa": o.get("is_oa"),
            "oa_status": o.get("oa_status"),
            "title": (d.get("title") or "")[:200],
            "year": d.get("publication_year"),
            "cited_by_count": d.get("cited_by_count"),
            "type": d.get("type"),
        }
        best = d.get("best_oa_location") or {}
        add(best.get("pdf_url"), "openalex_best_pdf", version=best.get("version"), host=best.get("source", {}).get("type") if isinstance(best.get("source"), dict) else None)
        add(o.get("oa_url"), "openalex_oa_url")
        for loc in (d.get("locations") or []):
            add(loc.get("pdf_url"), "openalex_loc_pdf", version=loc.get("version"))
    else:
        out["notes"].append("openalex:%s" % err)

    # 3) arXiv 派生 DOI（10.48550/arXiv.xxxx）
    m = re.match(r"^10\.48550/arxiv\.(.+)$", doi, flags=re.I)
    if m:
        aid = m.group(1)
        add("https://arxiv.org/pdf/%s" % aid, "arxiv_pdf")
        out["notes"].append("arxiv_id:%s（abs 页仅作元数据入口，不进下载候选）" % aid)

    # 4) doi.org 落地页，尝试从 meta 里取 citation_pdf_url
    try:
        req = _req("https://doi.org/%s" % urllib.parse.quote(doi, safe="/"), email, 25, "text/html")
        with _open(req, 25) as r:
            final = r.geturl()
            html = r.read(262144).decode("utf-8", "replace")
        out["sources"]["doi_org"] = {"final_url": final}
        for m2 in re.finditer(
            r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']', html, flags=re.I
        ):
            add(m2.group(1), "doi_landing_citation_pdf_url")
        if "citation_pdf_url" not in html.lower():
            out["notes"].append("doi_org:no_citation_pdf_url")
    except Exception as e:
        out["notes"].append("doi_org:%s" % type(e).__name__)

    # 候选排序：PDF 直链优先，OA url / 落地页靠后（落地页几乎必然被闸门判 html_landing）
    rank = {
        "unpaywall_best_pdf": 0,
        "openalex_best_pdf": 0,
        "arxiv_pdf": 0,
        "unpaywall_oa_pdf": 1,
        "openalex_loc_pdf": 1,
        "doi_landing_citation_pdf_url": 2,
        "openalex_oa_url": 3,
        "unpaywall_best_landing": 4,
    }
    out["candidates"].sort(key=lambda c: rank.get(c["via"], 5))
    for i, c in enumerate(out["candidates"], 1):
        c["order"] = i

    return out


def _rebuild_abstract(inv):
    """OpenAlex 的 abstract_inverted_index -> 正常段落文本。"""
    if not isinstance(inv, dict):
        return ""
    pos = []
    for word, idxs in inv.items():
        if isinstance(idxs, list):
            for i in idxs:
                if isinstance(i, int):
                    pos.append((i, word))
    pos.sort(key=lambda x: x[0])
    return " ".join(w for _, w in pos).strip()


def _strip_jats(s):
    """Crossref 的摘要常带 JATS 标签，剥掉。"""
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def meta_record(doi, email=None):
    """只取元数据：题名/作者/年/来源/OA 状态/摘要/可打开链接。不下全文。

    用途：即便拿不到 PDF，也要能给用户「这是什么 + 去哪看」。摘要来源优先级
    Crossref JATS -> OpenAlex inverted index -> Semantic Scholar。
    """
    doi = norm_doi(doi)
    rec = {
        "doi": doi,
        "record": {
            "title": "", "authors": [], "year": None, "venue": "",
            "volume": "", "issue": "", "pages": "", "type": "",
            "publisher": "", "cited_by": None, "is_oa": None, "oa_status": "",
            "license": "", "abstract": "", "abstract_source": "", "keywords": [],
            "ids": {"doi": doi},
        },
        "links": [],
        "sources": {},
        "notes": [],
    }
    R = rec["record"]
    seen = set()

    def add_link(rel, url, label):
        if not url or not str(url).lower().startswith(("http://", "https://")):
            return
        k = str(url).split("#")[0]
        if k in seen:
            return
        seen.add(k)
        rec["links"].append({"rel": rel, "url": url, "label": label})

    # 1) Crossref：权威题录
    d, err = _get_json("https://api.crossref.org/works/%s" % urllib.parse.quote(doi, safe="/"), email)
    if d and d.get("message"):
        m = d["message"]
        rec["sources"]["crossref"] = "ok"
        R["title"] = R["title"] or (m.get("title") or [""])[0]
        for a in m.get("author") or []:
            nm = " ".join(x for x in [a.get("given"), a.get("family")] if x) or (a.get("name") or "")
            if nm:
                R["authors"].append(nm)
        R["year"] = R["year"] or ((m.get("issued", {}).get("date-parts") or [[None]])[0] or [None])[0]
        R["venue"] = R["venue"] or (m.get("container-title") or [""])[0]
        R["volume"] = R["volume"] or (m.get("volume") or "")
        R["issue"] = R["issue"] or (m.get("issue") or "")
        R["pages"] = R["pages"] or (m.get("page") or "")
        R["type"] = R["type"] or (m.get("type") or "")
        R["publisher"] = R["publisher"] or (m.get("publisher") or "")
        if not R["abstract"]:
            ab = _strip_jats(m.get("abstract"))
            if ab:
                R["abstract"], R["abstract_source"] = ab, "crossref"
        for sub in m.get("subject") or []:
            if sub not in R["keywords"]:
                R["keywords"].append(sub)
        if not R["license"]:
            for li in m.get("license") or []:
                if li.get("URL"):
                    R["license"] = li["URL"]
                    break
    else:
        rec["sources"]["crossref"] = err or "not_found"

    # 2) OpenAlex：OA 状态 + 摘要重建 + 标识符
    oa_url = "https://api.openalex.org/works/https://doi.org/%s" % urllib.parse.quote(doi, safe="/")
    if email:
        oa_url += "?mailto=" + urllib.parse.quote(email)
    d2, err2 = _get_json(oa_url, email)
    if d2:
        rec["sources"]["openalex"] = "ok"
        R["title"] = R["title"] or (d2.get("title") or "")
        R["year"] = R["year"] or d2.get("publication_year")
        R["type"] = R["type"] or (d2.get("type") or "")
        R["cited_by"] = d2.get("cited_by_count")
        o = d2.get("open_access") or {}
        R["is_oa"] = o.get("is_oa")
        R["oa_status"] = o.get("oa_status") or ""
        if not R["abstract"]:
            ab = _rebuild_abstract(d2.get("abstract_inverted_index"))
            if ab:
                R["abstract"], R["abstract_source"] = ab, "openalex"
        ids = d2.get("ids") or {}
        for key in ("pmid", "pmcid"):
            if ids.get(key) and not R["ids"].get(key):
                R["ids"][key] = str(ids[key]).rsplit("/", 1)[-1]
        if not R["venue"]:
            loc = (d2.get("primary_location") or {}).get("source") or {}
            R["venue"] = loc.get("display_name", "") or ""
        best = d2.get("best_oa_location") or {}
        add_link("oa_pdf", best.get("pdf_url"), "开放获取 PDF（直链）")
        add_link("oa_landing", best.get("landing_page_url"), "开放获取页面")
        # locations 可能返回十几个转载位置，只取前几条 PDF/落地页，避免链接噪音
        n_pdf = n_land = 0
        for loc in (d2.get("locations") or []):
            loc_oa = bool(loc.get("is_oa"))
            if loc.get("pdf_url") and n_pdf < 3:
                add_link(
                    "oa_pdf" if loc_oa else "loc_pdf",
                    loc.get("pdf_url"),
                    "开放获取 PDF" if loc_oa else "PDF 位置（可能需订阅）",
                )
                n_pdf += 1
            if loc.get("landing_page_url") and n_land < 3:
                add_link(
                    "oa_landing" if loc_oa else "loc_landing",
                    loc.get("landing_page_url"),
                    "开放获取页面" if loc_oa else "该平台位置（可能需订阅）",
                )
                n_land += 1
    else:
        rec["sources"]["openalex"] = err2 or "not_found"

    # 3) Semantic Scholar：补摘要/标识符（无 key 常 429，失败不影响主流程）
    s2 = (
        "https://api.semanticscholar.org/graph/v1/paper/DOI:%s"
        "?fields=title,abstract,year,venue,citationCount,externalIds,openAccessPdf"
    ) % urllib.parse.quote(doi, safe="")  # S2 要求斜杠编码，否则 404
    d3, err3 = _get_json(s2, email)
    if not d3 and err3 and "429" in str(err3):
        time.sleep(4)  # S2 无 key 时频繁 429，退避后重试一次
        d3, err3 = _get_json(s2, email)
    if d3:
        rec["sources"]["semanticscholar"] = "ok"
        R["title"] = R["title"] or (d3.get("title") or "")
        if not R["abstract"] and d3.get("abstract"):
            R["abstract"], R["abstract_source"] = d3["abstract"], "semanticscholar"
        if R["cited_by"] is None:
            R["cited_by"] = d3.get("citationCount")
        ext = d3.get("externalIds") or {}
        for src_key, dst_key in (("PubMed", "pmid"), ("ArXiv", "arxiv")):
            if ext.get(src_key) and not R["ids"].get(dst_key):
                R["ids"][dst_key] = ext[src_key]
        add_link("oa_pdf", (d3.get("openAccessPdf") or {}).get("url"), "开放获取 PDF（S2）")
    else:
        rec["sources"]["semanticscholar"] = err3 or "unavailable"

    # 3.5) PubMed 摘要兜底（E-utilities，免费无 key；生物医学文献基本都能拿到）
    # 用 XML 而不是 text：text 版部分记录不打 "Abstract" 标签，正则抓不准。
    if not R["abstract"] and R["ids"].get("pmid"):
        txt, err4 = _get_text(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            "?db=pubmed&id=%s&rettype=abstract&retmode=xml" % R["ids"]["pmid"],
            email,
        )
        if txt:
            parts = re.findall(r"(?is)<AbstractText[^>]*>(.*?)</AbstractText>", txt)
            if parts:
                ab = re.sub(r"\s+", " ", " ".join(_strip_jats(p) for p in parts)).strip()
                if len(ab) > 60:
                    R["abstract"], R["abstract_source"] = ab, "pubmed"
            rec["sources"]["pubmed_efetch"] = "ok"
        else:
            rec["sources"]["pubmed_efetch"] = err4 or "unavailable"

    # 4) 兜底链接：永远给出，下载不了也能打开看题录
    add_link("doi", "https://doi.org/%s" % urllib.parse.quote(doi, safe="/"), "DOI 解析（出版商页，可能需订阅）")
    if R["ids"].get("pmid"):
        add_link("pubmed", "https://pubmed.ncbi.nlm.nih.gov/%s/" % R["ids"]["pmid"], "PubMed 题录")
    if R["ids"].get("pmcid"):
        add_link("pmc", "https://pmc.ncbi.nlm.nih.gov/articles/%s/" % R["ids"]["pmcid"], "PMC 全文（开放）")
    if R["ids"].get("arxiv"):
        add_link("arxiv", "https://arxiv.org/abs/%s" % R["ids"]["arxiv"], "arXiv 题录")
        add_link("arxiv_pdf", "https://arxiv.org/pdf/%s" % R["ids"]["arxiv"], "arXiv PDF（直链）")
    if R["title"]:
        add_link(
            "scholar",
            "https://scholar.google.com/scholar?q=%s" % urllib.parse.quote(R["title"][:300]),
            "Google Scholar（人工点开核对，勿自动抓取）",
        )

    # 4) 兜底链接：无论前面成没成，至少保证「DOI 能点开」+「有人工检索入口」
    urls = [(l.get("url") or "") for l in rec["links"]]
    if not any("doi.org" in u for u in urls):
        add_link("doi_landing", "https://doi.org/%s" % doi, "DOI 解析（出版商页，可能需订阅）")
    if R["title"] and not any("scholar.google" in u for u in urls):
        add_link(
            "scholar_search",
            "https://scholar.google.com/scholar?q=%s" % urllib.parse.quote(R["title"]),
            "Google Scholar（人工核对 / 找其他副本）",
        )

    rec["ok"] = bool(R["title"] or rec["links"])
    # meta 从不取全文：ok 只代表"题录可取"。全文状态必须单独给，否则调用方会把 ok:true 当"拿到了全文"
    rec["fulltext"] = False
    rec["deliverable"] = "metadata_only"
    return rec


def meta_markdown(rec):
    """把记录渲染成可直接贴给用户看的一段。"""
    R = rec["record"]
    out = ["### %s" % (R["title"] or "(题名缺失)")]
    if R["authors"]:
        out.append("- 作者：" + "、".join(R["authors"][:8]) + (" 等" if len(R["authors"]) > 8 else ""))
    bits = [x for x in [R["venue"], str(R["year"]) if R["year"] else "", ("卷 %s" % R["volume"]) if R["volume"] else "", ("期 %s" % R["issue"]) if R["issue"] else "", ("页 %s" % R["pages"]) if R["pages"] else ""] if x]
    if bits:
        out.append("- 来源：" + "，".join(bits))
    out.append("- DOI：`%s`" % rec["doi"])
    flags = ["OA" if R["is_oa"] else "非 OA"]
    if R["oa_status"]:
        flags.append("状态 %s" % R["oa_status"])
    if R["cited_by"] is not None:
        flags.append("被引 %s" % R["cited_by"])
    if R["type"]:
        flags.append(R["type"])
    out.append("- 属性：" + " | ".join(flags))
    if R["abstract"]:
        out.append("- 摘要（来源 %s）：%s" % (R["abstract_source"], R["abstract"]))
    else:
        out.append("- 摘要：未获取到，需打开链接查看")
    if rec["links"]:
        out.append("- 可打开链接：")
        for L in rec["links"]:
            out.append("  - [%s] %s" % (L["label"], L["url"]))
    out.append("- 全文：**未获取**（本条只给题录 + 摘要 + 链接；`fulltext=false`）")
    return "\n".join(out)


def crossref_search(query, from_year=None, limit=25, email=None, sort="relevance"):
    """OpenAlex 不可用时的兜底检索（Crossref 免费、不需 key，但无 OA 字段）。

    OpenAlex 自 2026 起对无 API key 的请求按 **出口 IP 共享日额度**，额度耗尽即 429
    （`$0 remaining; resets at midnight UTC`）。所以检索必须能落到 Crossref。
    """
    params = {
        "query": query,
        "rows": max(1, min(int(limit), 50)),
        "select": "DOI,title,author,container-title,issued,is-referenced-by-count,type",
    }
    filt = []
    if from_year:
        filt.append("from-pub-date:%d-01-01" % int(from_year))
    if filt:
        params["filter"] = ",".join(filt)
    if sort == "cited":
        params["sort"] = "is-referenced-by-count"
        params["order"] = "desc"
    if email:
        params["mailto"] = email
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    d, err = _get_json(url, email)
    out = {"query": query, "from_year": from_year, "sort": sort, "field": "crossref",
           "source": "crossref", "total": 0, "items": [], "error": None}
    if not d:
        out["error"] = err
        return out
    msg = d.get("message") or {}
    out["total"] = msg.get("total-results", 0)
    for w in msg.get("items") or []:
        ttl = (w.get("title") or [""])[0] if isinstance(w.get("title"), list) else (w.get("title") or "")
        cj = w.get("container-title") or []
        yr = ((w.get("issued") or {}).get("date-parts") or [[None]])[0][0]
        out["items"].append({
            "title": (ttl or "").strip(),
            "year": yr,
            "venue": (cj[0] if cj else "") or "",
            "doi": (w.get("DOI") or "").lower(),
            "cited_by": w.get("is-referenced-by-count"),
            "is_oa": None,
            "oa_status": "",
            "type": w.get("type") or "",
            "oa_url": "",
            "id": "",
        })
    return out


def search_works(query, from_year=None, limit=25, email=None, sort="relevance", field="all"):
    """L1 发现：按关键词检索 OpenAlex，返回结构化候选列表（不下载、不解析全文）。

    field=title_abstract 时可避开一词多义的噪音（例如 "coupling" 在爆破工程里
    指"不耦合装药"，会把岩石爆破论文混进来）。
    OpenAlex 额度耗尽（429）时自动降级到 Crossref，并在 `fallback` 字段标注。
    """
    params = {"per-page": max(1, min(int(limit), 50))}
    filt = []
    if field == "title_abstract":
        filt.append("title_and_abstract.search:%s" % query)
    elif field == "title":
        filt.append("title.search:%s" % query)
    else:
        params["search"] = query
    if from_year:
        filt.append("from_publication_date:%d-01-01" % int(from_year))
    if filt:
        params["filter"] = ",".join(filt)
    if sort == "cited":
        params["sort"] = "cited_by_count:desc"
    if email:
        params["mailto"] = email
    oa_key = os.environ.get("SCHOLAR_OPENALEX_KEY")
    if oa_key:
        params["api_key"] = oa_key
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    d, err = _get_json(url, email)
    out = {
        "query": query,
        "from_year": from_year,
        "sort": sort,
        "field": field,
        "total": 0,
        "items": [],
        "error": None,
    }
    if not d:
        # OpenAlex 不可用（无 key 的 IP 日额度耗尽 / 429 / 网络）→ 降级 Crossref
        sys.stderr.write("[fallback] openalex unavailable (%s) -> crossref\n" % err)
        fb = crossref_search(query, from_year, limit, email, sort)
        fb["fallback_from"] = "openalex:%s" % err
        return fb
    out["total"] = (d.get("meta") or {}).get("count", 0)
    for w in d.get("results") or []:
        o = w.get("open_access") or {}
        src = (w.get("primary_location") or {}).get("source") or {}
        out["items"].append(
            {
                "title": (w.get("title") or "").strip(),
                "year": w.get("publication_year"),
                "venue": src.get("display_name") or "",
                "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
                "cited_by": w.get("cited_by_count"),
                "is_oa": o.get("is_oa"),
                "oa_status": o.get("oa_status") or "",
                "type": w.get("type") or "",
                "authors": [
                    (a.get("author") or {}).get("display_name", "")
                    for a in (w.get("authorships") or [])
                ][:6],
                "openalex_id": w.get("id", ""),
            }
        )
    return out


def search_markdown(res, top=12):
    lines = [
        "查询：%s ｜ 起始年 %s ｜ %s 排序 ｜ 命中 %d 条"
        % (
            res["query"],
            res.get("from_year") or "不限",
            "被引" if res.get("sort") == "cited" else "相关度",
            res.get("total", 0),
        )
    ]
    if res.get("error"):
        lines.append("错误：%s" % res["error"])
        return "\n".join(lines)
    for i, it in enumerate(res["items"][:top], 1):
        lines.append("%2d. [%s] %s" % (i, it["year"] or "----", it["title"] or "(无题名)"))
        lines.append(
            "    %s ｜被引 %s ｜%s ｜doi:%s"
            % ((it["venue"] or "?")[:44], it["cited_by"], "OA" if it["is_oa"] else "非OA", it["doi"] or "-")
        )
    return "\n".join(lines)


def _slim_work(w):
    o = w.get("open_access") or {}
    src = (w.get("primary_location") or {}).get("source") or {}
    return {
        "title": (w.get("title") or "").strip(),
        "year": w.get("publication_year"),
        "venue": src.get("display_name") or "",
        "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
        "cited_by": w.get("cited_by_count"),
        "is_oa": o.get("is_oa"),
        "openalex_id": (w.get("id") or "").split("/")[-1],
    }


def cite_works(doi, direction="cited_by", limit=25, email=None):
    """引文滚雪球：从一个种子 DOI 出发，往"谁引用了它"或"它引用了谁"扩候选。

    这是替代 Google Scholar Cited by 的合规做法（OpenAlex 官方开放数据）。
    """
    doi = norm_doi(doi)
    seed, err = _get_json("https://api.openalex.org/works/https://doi.org/%s" % urllib.parse.quote(doi, safe="/"), email)
    out = {"seed_doi": doi, "direction": direction, "seed": None, "total": 0, "items": [], "error": None}
    if not seed:
        out["error"] = err or "seed_not_found"
        return out
    wid = (seed.get("id") or "").split("/")[-1]
    out["seed"] = {
        "openalex_id": wid,
        "title": (seed.get("title") or "")[:200],
        "year": seed.get("publication_year"),
        "cited_by": seed.get("cited_by_count"),
    }
    n = max(1, min(int(limit), 50))
    if direction == "cited_by":
        url = "https://api.openalex.org/works?filter=cites:%s&per-page=%d&sort=publication_date:desc" % (wid, n)
        if email:
            url += "&mailto=" + urllib.parse.quote(email)
        d, e = _get_json(url, email)
        if not d:
            out["error"] = e
            return out
        out["total"] = (d.get("meta") or {}).get("count", 0)
        out["items"] = [_slim_work(w) for w in (d.get("results") or [])]
        return out

    # references：先取种子的参考文献 id 列表，再批量查（单次最多 50）
    ref_ids = [r.split("/")[-1] for r in (seed.get("referenced_works") or [])][:n]
    out["total"] = len(seed.get("referenced_works") or [])
    if not ref_ids:
        out["error"] = "no_referenced_works"
        return out
    url = "https://api.openalex.org/works?filter=openalex_id:%s&per-page=%d" % ("|".join(ref_ids), n)
    if email:
        url += "&mailto=" + urllib.parse.quote(email)
    d, e = _get_json(url, email)
    if not d:
        out["error"] = e
        return out
    out["items"] = [_slim_work(w) for w in (d.get("results") or [])]
    return out


def check_file(path):
    rec = {"file": path, "exists": os.path.exists(path), "size": None, "magic": None,
           "end_marker": False, "page_estimate": None, "sha256": None, "valid": False, "reason": ""}
    if not rec["exists"]:
        rec["reason"] = "missing"
        return rec
    rec["size"] = os.path.getsize(path)
    if path.lower().endswith(PARTIAL_SUFFIX):
        rec["reason"] = "partial_suffix"
        return rec
    with open(path, "rb") as f:
        head = f.read(8192)
        f.seek(max(0, rec["size"] - 8192))
        tail = f.read()
    rec["magic"] = head[:8].decode("latin-1", "replace")
    if not head.startswith(PDF_MAGIC):
        # 机构订阅主通道（知网/万方）给的是 KDH / CAJ 私有格式，且常被写成 .caj 后缀
        fmt = "kdh" if head.startswith(b"KDH") else ("caj" if (head.startswith(b"CAJ") or head.startswith(b"HZ ")) else None)
        if fmt:
            rec["format"] = fmt
            rec["requires_reader"] = "CAJViewer/E-Study"
            rec["valid"] = rec["size"] >= 10240
            rec["reason"] = "" if rec["valid"] else "too_small_%d" % rec["size"]
            return rec
        rec["reason"] = "not_pdf_magic"
        return rec
    rec["format"] = "pdf"
    rec["end_marker"] = b"%%EOF" in tail
    rec["page_estimate"] = tail.count(b"/Type /Page") + tail.count(b"/Type/Page")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    rec["sha256"] = h.hexdigest()
    if rec["size"] < 5120:
        rec["reason"] = "too_small_%d" % rec["size"]
        return rec
    if not rec["end_marker"]:
        rec["reason"] = "truncated_no_eof"
        return rec
    rec["valid"] = True
    rec["reason"] = "ok"
    return rec


def read_doi_list(path):
    """读 DOI 清单。支持 .json（列表或 {"items":[...]}）与纯文本（每行 DOI，可用 TAB 分隔 title/venue/year/priority）。"""
    items = []
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    txt = raw.lstrip()
    if path.lower().endswith(".json") or txt.startswith(("[", "{")):
        d = json.loads(raw)
        if isinstance(d, dict):
            d = d.get("items") or d.get("records") or d.get("works") or []
        for x in d:
            if isinstance(x, str):
                items.append({"doi": x})
            elif isinstance(x, dict) and x.get("doi"):
                items.append(x)
    else:
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("\t")]
            rec = {"doi": parts[0]}
            if len(parts) > 1 and parts[1]:
                rec["title"] = parts[1]
            if len(parts) > 2 and parts[2]:
                rec["venue"] = parts[2]
            if len(parts) > 3 and parts[3]:
                rec["year"] = parts[3]
            if len(parts) > 4 and parts[4].isdigit():
                rec["priority"] = int(parts[4])
            items.append(rec)
    # 统一 DOI 形态
    out = []
    for r in items:
        d = norm_doi(r["doi"])
        if d:
            r = dict(r)
            r["doi"] = d
            out.append(r)
    return out


def safe_name(s):
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]", "_", s or "")
    return s.strip()[:150] or "untitled"


def batch_fetch(items, out_dir, email, interval=2.0):
    """批量 L2：逐个 resolve -> 下载第一个过闸门的候选。失败也如实记因，不静默。"""
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for i, it in enumerate(items, 1):
        doi = it["doi"]
        target = os.path.join(out_dir, safe_name(doi.replace("/", "_")) + ".pdf")
        rec = {"n": i, "doi": doi, "title": (it.get("title") or "")[:120], "ok": False,
               "file": None, "bytes": 0, "reason": "", "via": ""}
        try:
            res = resolve_candidates(doi, email)
            cands = res.get("candidates") or []
            if not cands:
                rec["reason"] = "no_candidate"
            else:
                for k, c in enumerate(cands):
                    if k:
                        time.sleep(interval)
                    r = _download(c["url"], target, email)
                    if r["valid"]:
                        rec.update(ok=True, file=target, bytes=r.get("bytes") or os.path.getsize(target),
                                   via=c.get("via", ""))
                        break
                    rec["reason"] = r.get("reason") or "rejected"
        except Exception as e:
            rec["reason"] = "error:%s" % type(e).__name__
        if rec["ok"]:
            sys.stderr.write("[%d/%d] OK   %s\n" % (i, len(items), doi))
        else:
            sys.stderr.write("[%d/%d] FAIL %-40s %s\n" % (i, len(items), doi, rec["reason"]))
        results.append(rec)
        if i < len(items):
            time.sleep(interval)
    ok = [r for r in results if r["ok"]]
    return {"total": len(results), "ok": len(ok), "failed": len(results) - len(ok),
            "out_dir": out_dir, "items": results}


def make_checklist(items, title="待下载清单", email=None):
    """把取不到的文献生成可点击清单：用户手动另存后，再交给 litadopt.py 归集。

    纯 DOI 清单没有题名/年份，这里对空项调 meta_record 回填，避免交付一张
    「题名空、年份问号」的清单——那种清单用户拿着没法继续。回填失败仍保留
    DOI 链接，不编造题录。
    """
    label = {0: "P0 必读", 1: "P1 高度相关", 2: "P2 方法学", 3: "P3 结构响应", 4: "P4 背景"}
    for it in items:
        if it.get("title") and it.get("year"):
            continue
        try:
            rec = meta_record(it["doi"], email)
        except Exception:
            continue
        r = (rec or {}).get("record") or {}
        if not it.get("title") and r.get("title"):
            it["title"] = r["title"]
        if not it.get("venue") and r.get("venue"):
            it["venue"] = r["venue"]
        if not it.get("year") and r.get("year"):
            it["year"] = r["year"]
    L = ["# %s" % (title if ("（" in title or "(" in title) else "%s（%d 篇）" % (title, len(items))), ""]
    L.append("> 这些文献在当前工具链下**无法自动写盘**（订阅型出版商 + 系统另存为对话框）。")
    L.append("> 用法：点 DOI 链接 → 页面点 `View PDF` → 阅读器里点保存 → 存到目标文献目录。")
    L.append("> 篇间建议间隔 5–10 秒；存完执行 `litadopt.py scan-new` 自动归集改名去重。")
    L.append("")
    ordered = sorted(items, key=lambda x: (x.get("priority") if isinstance(x.get("priority"), int) else 9,
                                           -(x.get("cited") or 0)))
    cur = None
    for i, it in enumerate(ordered, 1):
        p = it.get("priority")
        head = label.get(p, "其他") if isinstance(p, int) else "其他"
        if head != cur:
            L += ["", "## %s" % head, "", "| # | 题名 | 来源 / 年 | DOI |", "|---|---|---|---|"]
            cur = head
        t = (it.get("title") or "").replace("|", "/")[:110]
        v = ("%s / %s" % (it.get("venue") or "?", it.get("year") or "?"))[:44].replace("|", "/")
        L.append("| %d | %s | %s | [%s](https://doi.org/%s) |" % (i, t, v, it["doi"], it["doi"]))
    return "\n".join(L) + "\n"


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_email(cli_value):
    """邮箱来源：--email > SCHOLAR_EMAIL > config.json（项目 > 用户 > 无）。"""
    if cli_value:
        return cli_value, "cli"
    env = (os.environ.get("SCHOLAR_EMAIL") or "").strip()
    if env:
        return env, "env"
    path, src = _config.find("config.json", SKILL_DIR)
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                v = (json.load(f) or {}).get("email")
            if isinstance(v, str) and "@" in v:
                return v.strip(), "config(%s)" % src
        except Exception:
            pass
    return None, "none"


def _mask_mail(m):
    if not m or "@" not in m:
        return m
    u, d = m.split("@", 1)
    return (u[:1] + "***@" + d) if u else "***@" + d


def _map_count(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return len(d) if isinstance(d, dict) else 0
    except Exception:
        return 0


def build_config_report(email, email_src, a):
    """各项配置的实际来源（诊断用）：只报路径与条数，不打印文件内容。"""
    items = {}
    for name, legacy in (
        ("triage.md", "references/triage.local.md"),
        ("cn_journal_map.json", "scripts/cn_journal_map.local.json"),
        ("config.json", None),
    ):
        path, src = _config.find(name, SKILL_DIR, legacy=legacy)
        items[name] = {
            "source": src,
            "path": str(path) if path else None,
            "candidates": _config.all_paths(name, SKILL_DIR, legacy=legacy),
        }
    map_files = _config.find_all("cn_journal_map.json", SKILL_DIR,
                                 legacy="scripts/cn_journal_map.local.json")
    builtin = 5
    extra = sum(_map_count(p) for p, _ in map_files)
    items["cn_journal_map.json"]["merged_from"] = [
        {"source": src, "path": str(p), "count": _map_count(p)} for p, src in map_files
    ]
    jm = items["cn_journal_map.json"]
    if getattr(a, "proxy", None):
        pmode = "explicit(%s)" % a.proxy
    elif getattr(a, "auto_proxy", False):
        pmode = "auto(direct->env)"
    else:
        pmode = "direct(default)"
    pj = _config.effective_project_dir(skill_dir=SKILL_DIR)
    return {
        "skill_dir": SKILL_DIR,
        "user_config_dir": str(_config.user_dir()),
        "project_config_dir": str(pj) if pj else None,
        "items": items,
        "journal_map": {"builtin": builtin, "extra": extra, "merged": builtin + extra},
        "email": {"value": _mask_mail(email), "source": email_src},
        "proxy": pmode,
        "hint": _config.hint_legacy(jm["source"], jm["path"] or ""),
    }


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    p = argparse.ArgumentParser(
        prog="oa_fetch.py",
        description="OA 直取 + 元数据：标识符 -> 候选 -> 魔数闸门 -> 落盘；拿不到全文时至少给题录、摘要与可打开链接",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_net(sp):
        sp.add_argument("--email", help="真实邮箱（Unpaywall 必需、Crossref polite pool 建议）；缺省依次读 SCHOLAR_EMAIL、config.json")
        sp.add_argument("--proxy", help="显式代理，如 http://127.0.0.1:<端口>（默认直连，不用代理）")
        sp.add_argument("--no-proxy", action="store_true", help="强制直连（默认即直连，保留兼容）")
        sp.add_argument(
            "--auto-proxy",
            action="store_true",
            help="直连网络失败时自动降级到环境变量里的代理，只降一级、只重试一次（用于直连不可达的境外站点）",
        )

    s = sub.add_parser("search", help="按关键词检索文献候选（L1 发现，OpenAlex）")
    s.add_argument("--query", required=True)
    s.add_argument("--from-year", type=int, help="只取该年及以后（近年文献必用）")
    s.add_argument("--limit", type=int, default=25, help="返回条数，上限 50")
    s.add_argument("--sort", choices=("relevance", "cited"), default="relevance")
    s.add_argument(
        "--field",
        choices=("all", "title_abstract", "title"),
        default="all",
        help="限定检索字段；title_abstract 可避开一词多义的噪音",
    )
    s.add_argument("--out", help="把完整结果写成 JSON 文件")
    s.add_argument("--format", choices=("md", "json"), default="md")
    add_net(s)

    s = sub.add_parser("cite", help="引文滚雪球：种子 DOI -> 谁引用了它 / 它引用了谁")
    s.add_argument("--doi", required=True)
    s.add_argument("--direction", choices=("cited_by", "references"), default="cited_by")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--out", help="把完整结果写成 JSON 文件")
    add_net(s)

    s = sub.add_parser("meta", help="只取题录/摘要/链接，不下全文（下载不了时用它兜底）")
    s.add_argument("--doi", required=True)
    s.add_argument("--format", choices=("json", "md"), default="json")
    add_net(s)

    s = sub.add_parser("resolve", help="解析 OA 候选，不下载")
    s.add_argument("--doi", required=True)
    add_net(s)

    s = sub.add_parser("fetch", help="解析并下载第一个通过闸门的候选")
    s.add_argument("--doi")
    s.add_argument("--url")
    s.add_argument("--out", required=True)
    s.add_argument("--interval", type=float, default=1.0, help="候选之间间隔秒")
    s.add_argument("--dry-run", action="store_true", help="只探测不落盘")
    add_net(s)

    s = sub.add_parser("probe", help="探测单个 URL，不落盘")
    s.add_argument("--url", required=True)
    add_net(s)

    s = sub.add_parser("check", help="校验本地文件")
    s.add_argument("--file", required=True)

    s = sub.add_parser("batch", help="批量 L2 直取：读 DOI 清单，逐个下载能拿到的 OA 全文")
    s.add_argument("--list", required=True, help="DOI 清单（.json 或每行 DOI 的文本）")
    s.add_argument("--out-dir", required=True, help="落盘目录")
    s.add_argument("--interval", type=float, default=2.0, help="篇间间隔秒，默认 2")
    add_net(s)

    s = sub.add_parser("checklist", help="把取不到的文献生成可点击清单（供用户手动另存）")
    s.add_argument("--list", required=True)
    s.add_argument("--out", required=True, help="输出 Markdown 路径")
    s.add_argument("--title", default="待下载清单")

    sub.add_parser("config", help="打印各项配置的实际来源（诊断用，不改任何文件）")

    a = p.parse_args()
    email, email_src = resolve_email(getattr(a, "email", None))
    # 默认直连；显式 --proxy 用代理；--auto-proxy 先直连、网络层失败再降级环境代理
    if getattr(a, "proxy", None):
        set_proxy(a.proxy)
    elif getattr(a, "auto_proxy", False):
        set_proxy("", auto=True)
    else:
        set_proxy("")  # 默认直连（含 --no-proxy）

    if a.cmd == "config":
        return jout(build_config_report(email, email_src, a), 0)

    if a.cmd == "search":
        res = search_works(a.query, a.from_year, a.limit, email, a.sort, a.field)
        if a.out:
            os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        if a.format == "json":
            return jout(res, 0 if res["items"] else 3)
        sys.stdout.write(search_markdown(res) + "\n")
        if a.out:
            sys.stdout.write("（完整 %d 条已写入 %s）\n" % (len(res["items"]), a.out))
        return 0 if res["items"] else 3

    if a.cmd == "cite":
        res = cite_works(a.doi, a.direction, a.limit, email)
        if a.out:
            os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
            with open(a.out, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        if res.get("error"):
            return jout(res, 3)
        seed = res.get("seed") or {}
        sys.stdout.write(
            "种子：[%s] %s（库内被引 %s）｜方向 %s ｜共 %d 条\n"
            % (seed.get("year"), (seed.get("title") or "")[:90], seed.get("cited_by"), res["direction"], res["total"])
        )
        for i, it in enumerate(res["items"][:20], 1):
            sys.stdout.write(
                "%2d. [%s] %s | %s | 引%s | %s\n"
                % (i, it["year"], (it["title"] or "")[:100], (it["venue"] or "?")[:30], it["cited_by"], it["doi"] or "-")
            )
        if a.out:
            sys.stdout.write("（完整结果已写入 %s）\n" % a.out)
        return 0

    if a.cmd == "meta":
        rec = meta_record(a.doi, email)
        if a.format == "md":
            sys.stdout.write(meta_markdown(rec) + "\n")
            return 0 if rec["ok"] else 3
        return jout(rec, 0 if rec["ok"] else 3)

    if a.cmd == "check":
        rec = check_file(a.file)
        return jout(rec, 0 if rec["valid"] else 4)

    if a.cmd == "batch":
        items = read_doi_list(a.list)
        if not items:
            return jout({"ok": False, "error": "empty_list", "list": a.list}, 2)
        res = batch_fetch(items, a.out_dir, email, a.interval)
        os.makedirs(os.path.dirname(os.path.abspath(a.out_dir)) or ".", exist_ok=True)
        with open(os.path.join(a.out_dir, "batch-result.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        return jout(res, 0 if res["ok"] == res["total"] else 5)

    if a.cmd == "checklist":
        items = read_doi_list(a.list)
        if not items:
            return jout({"ok": False, "error": "empty_list"}, 2)
        md = make_checklist(items, a.title, email)
        filled = sum(1 for x in items if x.get("title"))
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
        return jout({"ok": True, "out": a.out, "count": len(items),
                     "titles_filled": filled, "lines": md.count("\n")}, 0)

    if a.cmd == "probe":
        rec = probe(a.url, email)
        return jout(rec, 0 if rec["valid"] else 3)

    if a.cmd == "resolve":
        res = resolve_candidates(a.doi, email)
        res["ok"] = bool(res["candidates"])
        return jout(res, 0 if res["candidates"] else 3)

    # fetch
    t0 = time.time()
    if a.url:
        cands = [{"url": a.url, "via": "direct"}]
        doi = None
    elif a.doi:
        res = resolve_candidates(a.doi, email)
        cands = res["candidates"]
        doi = res["doi"]
        src = res["sources"]
    else:
        return jout({"ok": False, "error": "need --doi or --url"}, 2)

    attempts = []
    if not cands:
        return jout({"ok": False, "doi": doi, "reason": "no_candidate", "attempts": []}, 3)

    for i, c in enumerate(cands):
        if i:
            time.sleep(a.interval)
        if a.dry_run:
            r = probe(c["url"], email)
            r["via"] = c["via"]
            attempts.append(r)
            continue
        r = _download(c["url"], a.out, email)
        r["via"] = c["via"]
        attempts.append(r)
        if r["valid"]:
            r["elapsed_s"] = round(time.time() - t0, 2)
            return jout(
                {"ok": True, "doi": doi, "chosen": c, "file": a.out,
                 "verify": {k: r[k] for k in ("magic", "bytes", "end_marker", "sha256", "page_estimate", "content_type", "final_url")},
                 "attempts": attempts, "sources": src if doi else {}, "elapsed_s": r["elapsed_s"]},
                0,
            )

    reasons = [x.get("reason") for x in attempts]
    pmode = "explicit(%s)" % a.proxy if getattr(a, "proxy", None) else (
        "auto(direct->env)" if getattr(a, "auto_proxy", False) else "direct(default)")
    return jout(
        {"ok": False, "doi": doi, "reason": _top_reason(reasons), "attempts": attempts,
         "sources": src if doi else {}, "elapsed_s": round(time.time() - t0, 2),
         "reasons": reasons, "hint": failure_hint(reasons, pmode)},
        3,
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
