#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pccp_corpus_openfda.py —— 从 openFDA 拉"已授权 PCCP"的 PMA 补充记录，做边界样本语料。

为什么做这个：上一轮查监管时发现，PCCP 的公开语料不在新闻里，而在 PMA 补充的
批准说明（ao_statement）里——那里写着这条 PCCP 覆盖什么、以什么为前提。
把这类记录抓成结构化文件，就能回答"PCCP 范围写到什么颗粒度才算具体"。

只用标准库。查询可复现：任何人在网址栏粘同一条 API 也能拿到同一批。

用法：
  python pccp_corpus_openfda.py --out out/pccp_corpus.json [--max 600]
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter

API = "https://api.fda.gov/device/pma.json"
# 口径说明：实测 "predetermined change control plan" 命中 39 条，"PCCP" 命中 47 条，
# 后者多出 8 条是只写缩写、没写全称的记录。取更全的那个。
QUERY = 'ao_statement:"PCCP"'


def fetch(skip, limit):
    u = f"{API}?search={urllib.parse.quote(QUERY)}&limit={limit}&skip={skip}"
    return json.loads(urllib.request.urlopen(u, timeout=40).read())


def normalize(row):
    stmt = (row.get("ao_statement") or "").replace("\u200b", "").strip()
    stmt = re.sub(r"\s+", " ", stmt)
    return {
        "pma": row.get("pma_number"),
        "supplement": row.get("supplement_number"),
        "applicant": row.get("applicant"),
        "trade_name": row.get("trade_name"),
        "generic_name": row.get("generic_name"),
        "product_code": row.get("product_code"),
        "decision_date": row.get("decision_date"),
        "supplement_type": row.get("supplement_type"),
        "supplement_reason": row.get("supplement_reason"),
        "ao_statement": stmt,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/pccp_corpus.json")
    ap.add_argument("--max", type=int, default=600)
    a = ap.parse_args()

    first = fetch(0, 100)
    total = first["meta"]["results"]["total"]
    rows = [normalize(r) for r in first["results"]]
    skip = 100
    while len(rows) < min(total, a.max):
        page = fetch(skip, 100)
        rows += [normalize(r) for r in page["results"]]
        skip += 100
        if len(page["results"]) < 100:
            break

    years = Counter((r["decision_date"] or "")[:4] for r in rows)
    applicants = Counter(r["applicant"] for r in rows)
    reasons = Counter(r["supplement_reason"] for r in rows)

    corpus = {
        "source": API,
        "query": QUERY,
        "reproduce_url": f"{API}?search={urllib.parse.quote(QUERY)}&limit=100",
        "total_hits": total,
        "captured": len(rows),
        "by_year": dict(sorted(years.items())),
        "top_applicants": applicants.most_common(10),
        "by_reason": reasons.most_common(10),
        "records": rows,
    }
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=1)

    print(json.dumps({k: corpus[k] for k in
                      ("total_hits", "captured", "by_year", "top_applicants", "by_reason")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
