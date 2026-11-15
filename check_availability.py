#!/usr/bin/env python3
"""
自维护源探活脚本（照抄 awesome-zhuiju-free 的每日检测思路，做减法）
- 读取同目录 sources.txt（每行: URL | 名称 | 分类可选，# 开头为注释）
- 并发探测，结果写入 reports/availability.json
- 本地跑: python check_availability.py
- GitHub Actions 里跑: 自动 commit 报告
"""
import json
import time
import urllib.request
import urllib.error
import urllib.parse
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
SOURCES = HERE / "sources.txt"
REPORT_DIR = HERE / "reports"
TIMEOUT = 12
WORKERS = 16

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


def parse_sources():
    rows = []
    for line in SOURCES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        url = parts[0]
        name = parts[1] if len(parts) > 1 else url
        cat = parts[2] if len(parts) > 2 else ""
        rows.append({"url": url, "name": name, "category": cat})
    return rows


def normalize_url(u):
    """中文域名/非 ASCII 路径转成 urllib 能用的形式 (IDN + percent-encode)"""
    try:
        p = urllib.parse.urlsplit(u)
        host = p.hostname or ""
        try:
            host = host.encode("idna").decode()
        except UnicodeError:
            pass
        netloc = host
        try:
            if p.port:
                netloc += f":{p.port}"
        except ValueError:
            pass
        path = urllib.parse.quote(p.path, safe="/%:@!$&'()*+,;=~-._")
        return urllib.parse.urlunsplit((p.scheme, netloc, path, p.query, ""))
    except Exception:
        return u


def probe(row):
    url, attempts, err = normalize_url(row["url"]), 0, None
    while attempts < 2:
        attempts += 1
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                code = resp.status
                final = resp.geturl()
            ms = int((time.monotonic() - t0) * 1000)
            if 200 <= code < 400:
                status = "reachable"
            elif code in (401, 403, 429, 451):
                status = "restricted"  # 有响应但被拦（风控/地区/防火墙）
            else:
                status = "unreachable"
            return {**row, "status": status, "http_status": code, "final_url": final,
                    "response_ms": ms, "attempts": attempts, "checked_at": now(), "error": None}
        except urllib.error.HTTPError as e:
            code = e.code
            ms = int((time.monotonic() - t0) * 1000)
            if code in (401, 403, 429, 451):
                return {**row, "status": "restricted", "http_status": code, "final_url": url,
                        "response_ms": ms, "attempts": attempts, "checked_at": now(), "error": None}
            err = f"HTTP {code}"
        except Exception as e:  # 兜底: 任何单源异常都不炸全局
            err = f"{type(e).__name__}: {str(e)[:120]}"
        time.sleep(1.5)  # 失败重试间隔
    return {**row, "status": "unreachable", "http_status": None, "final_url": url,
            "response_ms": None, "attempts": attempts, "checked_at": now(), "error": err}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def main():
    rows = parse_sources()
    print(f"[i] 共 {len(rows)} 个源，{WORKERS} 并发探测中 ...")
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(probe, r): r for r in rows}
        for f in as_completed(futs):
            r = f.result()
            mark = {"reachable": "🟢", "restricted": "🟡", "unreachable": "🔴"}[r["status"]]
            extra = f" ({r['error']})" if r.get("error") else ""
            print(f"  {mark} {r['name']:<12} {r['status']:<12} HTTP {r['http_status']}{extra}")
            results.append(r)
    results.sort(key=lambda x: (x["category"], x["name"]))
    REPORT_DIR.mkdir(exist_ok=True)
    report = {"version": 1, "generated_at": now(),
              "summary": {s: sum(1 for r in results if r["status"] == s)
                          for s in ("reachable", "restricted", "unreachable")},
              "results": results}
    out = REPORT_DIR / "availability.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    s = report["summary"]
    print(f"\n[done] {out}  🟢{s['reachable']} 🟡{s['restricted']} 🔴{s['unreachable']}")


if __name__ == "__main__":
    main()
