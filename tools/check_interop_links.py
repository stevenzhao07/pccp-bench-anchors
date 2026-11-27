#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_interop_links.py —— 互操作台账的链接活体检查。

为什么单独做：上一轮 Muse 给的 11 个入口里 1 个 404、2 个不可判定，
"编路径"比"没路径"更贵。所以任何写进台账的入口，先在这里过一遍。

三态（沿用 Muse 通道的纪律）：
  LIVE     HTTP 200/204 —— 可用
  AUTH     401/403      —— 存在但要登录，不算"可发"
  DEAD     404/410/451  —— 死链
  UNKNOWN  超时/DNS/5xx —— 不可判定；不可判定 ≠ 可用

用法：
  python check_interop_links.py --targets interop_targets.json --out out/interop_links.json
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; pccp-bench-interop-check/1.0)"
TIMEOUT = 12


def probe(url):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            return "LIVE", r.status, ""
    except urllib.error.HTTPError as e:
        code = e.code
        if code in (401, 403, 429):
            return "AUTH", code, "需登录/受限"
        if code in (404, 410, 451):
            return "DEAD", code, "死链"
        return "UNKNOWN", code, "HTTP %d" % code
    except Exception as e:                    # DNS / timeout / TLS
        return "UNKNOWN", 0, type(e).__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", default="interop_targets.json")
    ap.add_argument("--out", default="out/interop_links.json")
    a = ap.parse_args()

    data = json.load(open(a.targets, encoding="utf-8"))
    rows = []
    for t in data["targets"]:
        state, code, note = probe(t["channel"])
        rows.append({"id": t["id"], "name": t["name"], "kind": t["kind"],
                     "priority": t["priority"], "channel": t["channel"],
                     "state": state, "http": code, "note": note})

    for r in rows:
        print("%-4s %-6s %-14s P%d %-52s %s" % (
            r["id"], r["state"], "HTTP %s" % (r["http"] or "-"), r["priority"],
            r["name"][:48], r["note"]))

    counts = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    live_p1 = sum(1 for r in rows if r["state"] == "LIVE" and r["priority"] == 1)
    print("\n合计 %d 项：%s；其中 P1 可用 %d 项" % (len(rows), counts, live_p1))

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump({"checked_at_note": "本机现取，12s 超时；UNKNOWN 不等于可用",
               "counts": counts, "rows": rows},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
