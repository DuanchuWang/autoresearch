#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
literature_search.py — autoresearch deterministic literature search (stdlib-only)

定位：S2–S5 / rehab 文献重锚定的强制真实检索与确定性加工层。stdlib-only（无第三方依赖），
一切确定性步骤（检索、去重、合并、模式统计、OOD 门禁）都在脚本内完成，
LLM 只负责判断类步骤（相关度分舱、模式标注、瓶颈诊断、候选生成）。

数据源（可配置，任一失败只记录 [Source Unavailable]，不阻断）：
  openalex          期刊 + arXiv 预印本，免 key（主源）
  crossref          期刊覆盖，免 key
  arxiv             官方 API，多端点回退（https/http × export.arxiv.org / arxiv.org/api）
  semanticscholar   尽力而为；无 key 限流时自动降级，ARW_FIND_S2_KEY 可配

子命令：
  search    --query "..." [--window 2024-2026 | --months N] [--cap N] [--out PATH] [--no-cache] [--sources a,b]
  collision --signature "terms" --alias "terms" [--cap N] [--out PATH] [--no-cache]
  stats     --lit <lit_table.json> [--top-terms 30] [--out PATH]  模式分布 + 高频术语回填（确定性）
  gate      --raw <lit_raw.json> --partition <relevance_partition.json> [--min-core 3] [--out PATH]
  gold      --gold <gold_set.txt> [lit_*.json ...] [--dir PATH] [--out PATH]  召回审计（确定性，领域无关）
  check     连通性探测（诊断用）

环境变量：
  ARW_FIND_SOURCES      源顺序，默认 openalex,crossref,arxiv,semanticscholar
  ARW_FIND_TIMEOUT      单请求超时秒，默认 15
  ARW_FIND_CACHE_DIR    缓存目录，默认 ~/.cache/autoresearch/find（TTL 24h）
  ARW_FIND_MAILTO       OpenAlex/Crossref 礼貌池邮箱
  ARW_FIND_S2_KEY       Semantic Scholar API key（可选）

输出：UTF-8 JSON（--out）；stdout 只给摘要行，省 token。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

VERSION = "v1.1"
DEFAULT_UA = "Mozilla/5.0 (autoresearch/literature_search)"
TIMEOUT = int(os.environ.get("ARW_FIND_TIMEOUT", "15"))
CACHE_DIR = Path(os.environ.get(
    "ARW_FIND_CACHE_DIR", str(Path.home() / ".cache" / "autoresearch" / "find")))
CACHE_TTL_S = 24 * 3600
MAILTO = os.environ.get("ARW_FIND_MAILTO", "autoresearch@example.com")
S2_KEY = os.environ.get("ARW_FIND_S2_KEY") or None
DOWN_TTL_S = 600  # 源失败后的负缓存窗口


# ---------------------------------------------------------------- helpers

def http_get(url: str, timeout: int = TIMEOUT, retries: int = 1) -> bytes:
    last: Exception | None = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if i < retries:
                time.sleep(3 * (i + 1))
    raise last  # type: ignore[misc]


def norm_title(title: str) -> str:
    return re.sub(r"[^\w]+", "", (title or "").lower())


def cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def cache_key(*parts: str) -> Path:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]
    return cache_dir() / f"{h}.json"


def cache_get(key: Path) -> dict | None:
    if not key.exists():
        return None
    try:
        obj = json.loads(key.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    if time.time() - obj.get("ts", 0) > CACHE_TTL_S:
        return None
    return obj.get("data")


def cache_put(key: Path, data: dict) -> None:
    key.write_text(
        json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False),
        encoding="utf-8",
    )


def source_down(name: str, mark: bool = False) -> bool:
    p = cache_dir() / f"_down_{name}.json"
    if mark:
        p.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
        return False
    try:
        obj = json.loads(p.read_text(encoding="utf-8-sig"))
        return time.time() - obj.get("ts", 0) < DOWN_TTL_S
    except Exception:  # noqa: BLE001
        return False


def write_out(path: str | None, payload: dict) -> str | None:
    if not path:
        return None
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def parse_window(win: str) -> tuple[str, str, str]:
    """返回 (mode, lo, hi)。mode=years -> 年份；mode=dates -> ISO 日期。"""
    if win.startswith("months:"):
        n = int(win.split(":", 1)[1])
        end = date.today()
        start = end - timedelta(days=int(n * 30.44))
        return "dates", start.isoformat(), end.isoformat()
    if "-" in win:
        y0, y1 = win.split("-", 1)
        return "years", y0.strip(), y1.strip()
    raise ValueError(f"无法解析窗口：{win}（用 2024-2026 或 months:10）")


def env_sources() -> list[str]:
    order = os.environ.get("ARW_FIND_SOURCES", "openalex,crossref,arxiv,semanticscholar")
    return [s.strip() for s in order.split(",") if s.strip()]


# ---------------------------------------------------------------- sources

def _abstract_from_inverted(inv: dict | None) -> str:
    if not inv:
        return ""
    pos: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        for i in idxs:
            pos.append((i, word))
    pos.sort()
    return " ".join(w for _, w in pos)


def _paper_id(rec: dict) -> str:
    pid = rec.get("id") or ""
    if not pid:
        pid = hashlib.sha256(
            f"{norm_title(rec.get('title'))}|{rec.get('year')}".encode("utf-8")).hexdigest()[:12]
    return pid


def _collect_ids(rec: dict) -> list[str]:
    """收集记录的全部稳定标识符（arXiv ID / DOI / URL），供 gold 审计跨源匹配。"""
    ids: list[str] = []
    for key in ("paper_id", "id", "url"):
        v = str(rec.get(key) or "").strip()
        if not v:
            continue
        if "arxiv.org/abs/" in v:
            v = v.split("arxiv.org/abs/")[-1].split("?")[0]
            v = re.sub(r"v\d+$", "", v)
        elif v.lower().startswith("https://doi.org/"):
            v = v[len("https://doi.org/"):].lower()
        elif v.lower().startswith("10."):
            v = v.lower()
        if v and v not in ids:
            ids.append(v)
    return ids


def fetch_openalex(query: str, win: tuple[str, str, str], cap: int) -> list[dict]:
    mode, lo, hi = win
    filt = f"publication_year:{lo}-{hi}" if mode == "years" else f"from_publication_date:{lo},to_publication_date:{hi}"
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode({
        "search": query,
        "filter": filt,
        "per-page": cap,
        "sort": "relevance_score:desc",
        "mailto": MAILTO,
    })
    data = json.loads(http_get(url).decode("utf-8-sig"))
    out: list[dict] = []
    for it in data.get("results", []):
        src = it.get("primary_location") or {}
        srcname = (src.get("source") or {}).get("display_name") or ""
        rec = {
            "title": it.get("title") or "",
            "year": it.get("publication_year"),
            "date": it.get("publication_date") or "",
            "venue": srcname,
            "abstract": _abstract_from_inverted(it.get("abstract_inverted_index")),
            "url": it.get("doi") or it.get("id") or "",
            "id": it.get("id") or "",
            "source": "openalex",
            "cited_by_count": it.get("cited_by_count", 0),
        }
        rec["paper_id"] = _paper_id(rec)
        out.append(rec)
    return out


def fetch_crossref(query: str, win: tuple[str, str, str], cap: int) -> list[dict]:
    mode, lo, hi = win
    if mode == "years":
        filt = f"from-pub-date:{lo}-01-01,until-pub-date:{hi}-12-31"
    else:
        filt = f"from-pub-date:{lo},until-pub-date:{hi}"
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode({
        "query": query,
        "filter": filt,
        "rows": cap,
        "select": "title,DOI,URL,abstract,container-title,published,score",
    })
    data = json.loads(http_get(url, timeout=min(25, TIMEOUT + 5)).decode("utf-8-sig"))
    out: list[dict] = []
    for it in data.get("message", {}).get("items", []):
        title = (it.get("title") or [""])[0]
        parts = ((it.get("published") or {}).get("date-parts") or [[None]])[0]
        year = parts[0] if parts else None
        venue = (it.get("container-title") or [""])[0]
        abstract = re.sub(r"<[^>]+>", " ", it.get("abstract") or "").strip()
        rec = {
            "title": title,
            "year": year,
            "date": "",
            "venue": venue,
            "abstract": abstract,
            "url": it.get("URL") or f"https://doi.org/{it.get('DOI', '')}",
            "id": it.get("DOI") or "",
            "source": "crossref",
            "cited_by_count": 0,
        }
        rec["paper_id"] = _paper_id(rec)
        out.append(rec)
    return out


_ARXIV_STOP = {
    "a", "an", "the", "of", "in", "on", "for", "to", "with", "and", "or",
    "from", "by", "at", "is", "are", "was", "were", "be", "been", "its",
    "their", "this", "that", "using", "via", "our", "results", "study",
    "across", "based", "show", "shows", "present", "presents", "proposed",
    "propose", "several", "various",
}


def _arxiv_query(query: str) -> str:
    """构造 arXiv API 可用的多词查询。

    arXiv 对不带引号的多词 `all:` 查询按 OR 处理（实测返回全库最新论文），
    整句加引号或全量 AND 又过于严格（长关键词常命中 0）。这里取前 3 个
    非停用词做显式 AND，在召回与精度之间取平衡。URL 编码由调用方负责。
    """
    terms = [t for t in query.split() if t.lower() not in _ARXIV_STOP][:3]
    if not terms:
        return f"all:{query}"
    return " AND ".join(f"all:{t}" for t in terms)


def fetch_arxiv(query: str, win: tuple[str, str, str], cap: int) -> list[dict]:
    mode, lo, hi = win
    endpoints = [
        "https://export.arxiv.org/api/query",
        "http://export.arxiv.org/api/query",
        "https://arxiv.org/api/query",
    ]
    qs = urllib.parse.urlencode({
        "search_query": _arxiv_query(query),
        "start": 0,
        "max_results": cap * 2,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }, quote_via=urllib.parse.quote)
    time.sleep(3)  # arXiv 礼貌策略：两次请求间隔 ≥3s
    ns = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}
    last: Exception | None = None
    for ep in endpoints:
        try:
            data = http_get(f"{ep}?{qs}", timeout=min(10, TIMEOUT))
            root = ET.fromstring(data.decode("utf-8", errors="replace"))
            out: list[dict] = []
            for entry in root.findall("a:entry", ns):
                title = " ".join((entry.findtext("a:title", "", ns) or "").split())
                published = (entry.findtext("a:published", "", ns) or "")[:10]
                year = int(published[:4]) if len(published) >= 4 else None
                if mode == "years" and not (int(lo) <= (year or 0) <= int(hi)):
                    continue
                if mode == "dates" and published and not (lo <= published <= hi):
                    continue
                summary = " ".join((entry.findtext("a:summary", "", ns) or "").split())
                link = ""
                for lnk in entry.findall("a:link", ns):
                    if lnk.get("rel") == "alternate":
                        link = lnk.get("href") or ""
                        break
                jref = entry.findtext("ar:journal_ref", "", ns) or ""
                rec = {
                    "title": title,
                    "year": year,
                    "date": published,
                    "venue": jref.strip() or "arXiv",
                    "abstract": summary,
                    "url": link,
                    "id": link,
                    "source": "arxiv",
                    "cited_by_count": 0,
                }
                rec["paper_id"] = _paper_id(rec)
                out.append(rec)
                if len(out) >= cap:
                    break
            return out
        except Exception as exc:  # noqa: BLE001
            last = exc
            continue
    raise last  # type: ignore[misc]


def fetch_s2(query: str, win: tuple[str, str, str], cap: int) -> list[dict]:
    mode, lo, hi = win
    params = {
        "query": query,
        "fields": "title,year,venue,abstract,url,externalIds",
        "limit": cap,
    }
    if S2_KEY:
        params["apiKey"] = S2_KEY
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(params)
    data = json.loads(http_get(url, timeout=min(20, TIMEOUT + 5), retries=2).decode("utf-8-sig"))
    out: list[dict] = []
    for it in data.get("data", []):
        y = it.get("year")
        if mode == "years" and not (int(lo) <= (y or 0) <= int(hi)):
            continue
        if mode == "dates" and y and not (int(lo[:4]) <= y <= int(hi[:4])):
            continue
        ext = it.get("externalIds") or {}
        rec = {
            "title": it.get("title") or "",
            "year": y,
            "date": "",
            "venue": it.get("venue") or "",
            "abstract": it.get("abstract") or "",
            "url": it.get("url") or "",
            "id": ext.get("ArXiv") or ext.get("DOI") or "",
            "source": "semanticscholar",
            "cited_by_count": 0,
        }
        rec["paper_id"] = _paper_id(rec)
        out.append(rec)
    return out


def build_sources() -> list[tuple[str, object]]:
    fns: dict[str, object] = {
        "openalex": fetch_openalex,
        "crossref": fetch_crossref,
        "arxiv": fetch_arxiv,
        "semanticscholar": fetch_s2,
    }
    return [(n, fns[n]) for n in env_sources() if n in fns]


def fetch_all(query: str, win: tuple[str, str, str], cap: int) -> tuple[dict[str, dict], list[dict]]:
    merged: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    for name, fn in build_sources():
        if source_down(name):
            meta[name] = {"ok": False, "error": f"negative-cache（{DOWN_TTL_S}s 内失败跳过）"}
            continue
        try:
            rows = fn(query, win, cap)  # type: ignore[operator]
            meta[name] = {"ok": True, "hits": len(rows)}
        except Exception as exc:  # noqa: BLE001
            source_down(name, mark=True)
            meta[name] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:80]}"}
            rows = []
        for r in rows:
            k = norm_title(r["title"])
            if not k:
                continue
            if k not in merged:
                r["ids"] = _collect_ids(r)
                merged[k] = r
            else:
                if not merged[k].get("abstract") and r.get("abstract"):
                    merged[k]["abstract"] = r["abstract"]
                for extra in _collect_ids(r):
                    if extra not in merged[k].get("ids", []):
                        merged[k].setdefault("ids", []).append(extra)
                merged[k]["source"] = merged[k]["source"] + "+" + r["source"]
    records = sorted(merged.values(), key=lambda r: -(r.get("year") or 0))
    return meta, records


# ---------------------------------------------------------------- commands

def cmd_check(_args: argparse.Namespace) -> int:
    for name, fn in build_sources():
        try:
            rows = fn("point cloud", ("years", "2024", "2026"), 1)  # type: ignore[operator]
            print(f"[OK] {name}（{len(rows)} 条）")
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {name}: {type(exc).__name__}: {str(exc)[:100]}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    win = parse_window(args.window)
    key = cache_key("search", args.query, args.window, str(args.cap), ",".join(env_sources()))
    data = None if args.no_cache else cache_get(key)
    if data is None:
        meta, records = fetch_all(args.query, win, args.cap)
        data = {"meta": meta, "records": records}
        cache_put(key, data)
    payload = {
        "tool": "literature_search.py search",
        "version": VERSION,
        "query": args.query,
        "window": args.window,
        "cap": args.cap,
        "sources": env_sources(),
        "meta": data["meta"],
        "uncovered_sources": [n for n, m in data["meta"].items() if not m.get("ok")],
        "records": data["records"],
    }
    out = write_out(args.out, payload)
    print(f"[SEARCH] 去重后 {len(data['records'])} 条")
    for n, m in data["meta"].items():
        status = f"ok · {m.get('hits')} hits" if m.get("ok") else f"unavailable · {m.get('error', '')}"
        print(f"  [{n}] {status}")
    if out:
        print(f"[WROTE] {out}")
    return 0


def cmd_collision(args: argparse.Namespace) -> int:
    sig_win = f"months:{args.signature_months}"
    ali_win = f"months:{args.alias_months}"
    channels: list[dict] = []
    for label, terms, window, cap in (
        ("signature", args.signature, sig_win, args.cap),
        ("alias", args.alias, ali_win, args.cap),
    ):
        key = cache_key("collision", label, terms, window, str(cap), ",".join(env_sources()))
        data = None if args.no_cache else cache_get(key)
        if data is None:
            meta, records = fetch_all(terms, parse_window(window), cap)
            for r in records:
                r["channel"] = label
                r["matched_terms"] = terms
            data = {"meta": meta, "records": records}
            cache_put(key, data)
        channels.extend(data["records"])
    payload = {
        "tool": "literature_search.py collision",
        "version": VERSION,
        "signature": args.signature,
        "alias": args.alias,
        "signature_window": sig_win,
        "alias_window": ali_win,
        "cap": args.cap,
        "channels": channels,
    }
    out = write_out(args.out, payload)
    n_sig = sum(1 for c in channels if c["channel"] == "signature")
    n_ali = sum(1 for c in channels if c["channel"] == "alias")
    print(f"[COLLISION] signature {n_sig} 条 / alias {n_ali} 条")
    for c in channels[:6]:
        print(f"  [{c['channel']}] ({c.get('year')}) {c['title'][:80]}")
    if out:
        print(f"[WROTE] {out}")
    return 0


def _token_terms(text: str) -> list[str]:
    """从标题/摘要抽取候选术语（供词表回填），过滤停用词与过短 token。"""
    return [t for t in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", (text or "").lower())
            if t not in _ARXIV_STOP]


def cmd_stats(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.lit).read_text(encoding="utf-8-sig"))
    rows = raw.get("records") if isinstance(raw, dict) and "records" in raw else raw
    rows = [r for r in rows if isinstance(r, dict)]
    core = [r for r in rows if r.get("relevance") == "core"]
    all_cnt: Counter[str] = Counter()
    core_cnt: Counter[str] = Counter()
    for r in rows:
        for p in (r.get("patterns") or []):
            all_cnt[p] += 1
    for r in core:
        for p in (r.get("patterns") or []):
            core_cnt[p] += 1
    names = sorted(set(all_cnt) | set(core_cnt))
    density = {p: {"total": all_cnt[p], "core": core_cnt[p]} for p in names}
    rare = sorted([p for p in names if core_cnt[p] > 0], key=lambda p: core_cnt[p])[:5]
    term_cnt: Counter[str] = Counter()
    for r in rows:
        text = " ".join([r.get("title", "") or "", r.get("abstract", "") or ""])
        for t in _token_terms(text):
            term_cnt[t] += 1
    top_terms = [t for t, _ in term_cnt.most_common(args.top_terms)]
    payload = {
        "tool": "literature_search.py stats",
        "version": VERSION,
        "papers": len(rows),
        "core_papers": len(core),
        "pattern_density": density,
        "rare_patterns": rare,
        "top_terms": top_terms,
    }
    out = write_out(args.out, payload)
    print(f"[STATS] papers {len(rows)} / core {len(core)}")
    for p in sorted(density, key=lambda x: density[x]["core"], reverse=True):
        d = density[p]
        print(f"  {p}: core {d['core']} / total {d['total']}")
    print(f"[STATS] 稀模式（core 最少，生成机会）: {', '.join(rare) if rare else '无'}")
    print(f"[STATS] 高频术语（词表回填，前 {len(top_terms)}）: {', '.join(top_terms[:15])}")
    if out:
        print(f"[WROTE] {out}")
    return 0


_ARXIV_ID_RE = re.compile(r"^\d{4}\.\d{4,5}(v\d+)?$")


def _norm_gold_id(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace("https://arxiv.org/abs/", "").replace("http://arxiv.org/abs/", "")
    s = re.sub(r"v\d+$", "", s)
    return s.lower()


def cmd_gold(args: argparse.Namespace) -> int:
    """召回审计：用 gold set 对照已有检索产物，报告每篇命中/漏检与召回率。"""
    items: list[dict] = []
    for ln in Path(args.gold).read_text(encoding="utf-8-sig").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        tokens = [a for a in re.split(r"[\s|,]+", s) if a]
        if any(_ARXIV_ID_RE.match(a) or a.lower().startswith("10.") for a in tokens):
            aliases, kind = tokens, "id"
        else:
            aliases, kind = [s], "title"  # 标题按整行短语匹配，禁止拆词
        items.append({"item": s, "aliases": aliases, "kind": kind,
                      "matched": False, "matched_in": [], "matched_title": ""})
    files: list[Path] = []
    if args.dir:
        files = sorted(Path(args.dir).glob("lit_*.json"))
    files += [Path(p) for p in args.files]
    if not files:
        print("[GOLD] 未提供任何结果文件（位置参数或 --dir）")
        return 2
    uncovered: set[str] = set()
    for fp in files:
        data = json.loads(fp.read_text(encoding="utf-8-sig"))
        for n, m in (data.get("meta") or {}).items():
            if not m.get("ok"):
                uncovered.add(n)
        for g in items:
            if g["matched"]:
                continue
            for r in data.get("records") or []:
                cand_ids = {_norm_gold_id(x) for x in
                            ([r.get("paper_id"), r.get("id"), r.get("url")]
                             + list(r.get("ids") or [])) if x}
                title = (r.get("title") or "").lower()
                if g["kind"] == "id":
                    hit = bool({_norm_gold_id(a) for a in g["aliases"]} & cand_ids)
                else:
                    hit = any(a.lower() in title for a in g["aliases"])
                if hit:
                    g["matched"] = True
                    g["matched_in"].append(fp.name)
                    g["matched_title"] = r.get("title", "")
                    break
    n_hit = sum(1 for g in items if g["matched"])
    recall = n_hit / len(items) if items else 0.0
    payload = {
        "tool": "literature_search.py gold",
        "version": VERSION,
        "gold_count": len(items),
        "recalled": n_hit,
        "recall_rate": round(recall, 4),
        "files": [str(fp) for fp in files],
        "uncovered_sources": sorted(uncovered),
        "items": items,
    }
    out = write_out(args.out, payload)
    for g in items:
        mark = "命中" if g["matched"] else "漏检"
        print(f"[GOLD] {mark}  {g['item']}  → {g['matched_title'][:70] or '(未命中)'}")
    print(f"[GOLD] recall {n_hit}/{len(items)} = {recall:.0%}")
    if uncovered:
        print(f"[GOLD] 未覆盖源：{', '.join(sorted(uncovered))}")
    if n_hit < len(items):
        missed = [g["item"] for g in items if not g["matched"]]
        print(f"[GOLD] 漏检 {len(items) - n_hit} 项 → 补命名探测/换词表重跑：{'；'.join(missed)}")
    if out:
        print(f"[WROTE] {out}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8-sig"))
    partition = json.loads(Path(args.partition).read_text(encoding="utf-8-sig"))
    rel = {p["paper_id"]: p["relevance"] for p in partition}
    counts = {"core": 0, "adjacent": 0, "off_topic": 0, "unknown": 0}
    for rec in raw.get("records", []):
        r = rel.get(rec.get("paper_id"), "unknown")
        counts[r] += 1
    ood = counts["core"] < args.min_core
    unavailable = [k for k, v in raw.get("meta", {}).items() if not v.get("ok")]
    payload = {
        "tool": "literature_search.py gate",
        "version": VERSION,
        "min_core": args.min_core,
        "counts": counts,
        "ood": ood,
        "unavailable_sources": unavailable,
    }
    out = write_out(args.out, payload)
    print(f"[GATE] core {counts['core']} / adjacent {counts['adjacent']} / "
          f"off_topic {counts['off_topic']} / unknown {counts['unknown']}")
    print(f"[GATE] OOD = {'TRUE' if ood else 'false'}（core < {args.min_core}）")
    if unavailable:
        print(f"[GATE] 降级源：{', '.join(unavailable)}")
    if out:
        print(f"[WROTE] {out}")
    return 0


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="literature_search.py",
    description=f"autoresearch literature_search（{VERSION}）——stdlib-only、多源回退、缓存",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="连通性探测")
    p_check.set_defaults(func=cmd_check)

    p_search = sub.add_parser("search", help="语料检索（多源合并）")
    p_search.add_argument("--query", required=True)
    p_search.add_argument("--window", default="2023-2026", help="2024-2026 或 months:N")
    p_search.add_argument("--cap", type=int, default=20)
    p_search.add_argument("--sources", help="覆盖 ARW_FIND_SOURCES")
    p_search.add_argument("--out")
    p_search.add_argument("--no-cache", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_col = sub.add_parser("collision", help="碰撞双窗检索（签名 + 别名）")
    p_col.add_argument("--signature", required=True)
    p_col.add_argument("--alias", required=True)
    p_col.add_argument("--signature-months", type=int, default=10)
    p_col.add_argument("--alias-months", type=int, default=48)
    p_col.add_argument("--cap", type=int, default=15)
    p_col.add_argument("--sources", help="覆盖 ARW_FIND_SOURCES")
    p_col.add_argument("--out")
    p_col.add_argument("--no-cache", action="store_true")
    p_col.set_defaults(func=cmd_collision)

    p_stats = sub.add_parser("stats", help="模式分布统计（确定性）")
    p_stats.add_argument("--lit", required=True)
    p_stats.add_argument("--top-terms", type=int, default=30, help="词表回填：输出前 N 个高频术语")
    p_stats.add_argument("--out")
    p_stats.set_defaults(func=cmd_stats)

    p_gate = sub.add_parser("gate", help="OOD 门禁与覆盖判定（确定性）")
    p_gate.add_argument("--raw", required=True)
    p_gate.add_argument("--partition", required=True)
    p_gate.add_argument("--min-core", type=int, default=3)
    p_gate.add_argument("--out")
    p_gate.set_defaults(func=cmd_gate)

    p_gold = sub.add_parser("gold", help="召回审计：gold set 对照（确定性）")
    p_gold.add_argument("--gold", required=True,
                        help="gold set 文本文件：每行一个或多个标识符/标题子串（空格或 | 分隔，# 注释行跳过）")
    p_gold.add_argument("--dir", help="目录，自动读取 lit_*.json")
    p_gold.add_argument("files", nargs="*", help="检索产物 JSON（可多个）")
    p_gold.add_argument("--out")
    p_gold.set_defaults(func=cmd_gold)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
