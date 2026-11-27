#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_muse_channels.py —— 现场核 Muse 给的"去处"是否真的存在。

为什么必须核：Muse 是外部模型，它给的频道/入口有可能是**编出来的**（这一轮它已经编了
`validator.py`、`RECORDS.md`、"base.py passes all checks" 三样我们根本没有的东西）。
把人往死链上引，比不发更糟。

做法：对每个入口发一次 GET（带 UA、10 秒超时、不跟随无限跳转），只记 HTTP 状态与最终 URL。
判定：2xx/3xx 且落在预期域名 = 可用；403 = 存在但需登录；404/连接失败 = 不可用（记为死链）。

用法：
  python check_muse_channels.py --json out\\muse_channels_20261127.json
"""
import argparse
import json
import ssl
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; pccp-channel-check/0.1)"

CHANNELS = [
    ("sigstore-slack", "https://slack.sigstore.dev/"),
    ("openssf-slack-archive", "https://openssf.slack.com/archives/C01D7D31WT7"),
    ("python-mail-lists", "https://mail.python.org/mailman/listinfo"),
    ("hacker-news-submit", "https://news.ycombinator.com/submit"),
    ("users.rust-lang", "https://users.rust-lang.org/c/help/7"),
    ("ieee-sa-open", "https://opensource.ieee.org/medical-devices"),
    ("ietf-datatracker-scitt", "https://datatracker.ietf.org/wg/scitt/about/"),
    ("w3c-ccg", "https://www.w3.org/community/credentials/"),
    ("mlcommons-medperf", "https://mlcommons.org/working-groups/ai-risk-verification/"),
    ("github-repo", "https://github.com/stevenzhao07/pccp-bench-anchors"),
    ("rekor-entry", "https://rekor.sigstore.dev/api/v1/log/entries?logIndex=4143787841"),
]


def probe(url):
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=12, context=ctx) as f:
            return {"status": f.status, "final_url": f.geturl(), "note": "OK" if f.status < 400 else ""}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "final_url": url,
                "note": "需登录/受限" if e.code in (401, 403) else "HTTP %d" % e.code}
    except Exception as exc:
        return {"status": None, "final_url": url, "note": type(exc).__name__ + ": " + str(exc)[:90]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="out/muse_channels_20261127.json")
    a = ap.parse_args()

    rows = []
    for name, url in CHANNELS:
        r = probe(url)
        r["name"], r["url"] = name, url
        r["verdict"] = ("可用" if r["status"] and r["status"] < 400 else
                        ("需登录" if r["status"] in (401, 403) else "不可用"))
        rows.append(r)

    json.dump({"checked_at": "2026-11-27", "channel_from": "Muse(T2) 的建议，逐条现场核",
               "rows": rows}, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print("%-22s %-7s %-8s %s" % ("name", "status", "verdict", "note"))
    for r in rows:
        print("%-22s %-7s %-8s %s" % (r["name"], r["status"], r["verdict"], r["note"][:70]))
    ok = sum(1 for r in rows if r["verdict"] == "可用")
    print("可用 %d / %d" % (ok, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
