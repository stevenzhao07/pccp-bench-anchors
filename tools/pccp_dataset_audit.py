#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pccp_dataset_audit.py —— 对公开题集做红队自审：它到底能不能区分对错。

审四件事：
  1  布尔标志的变异（True/False 各多少）——只出现一种取值的标志是"装饰"，不是判据
  2  答案分布，以及"永远答某个值"的傻瓜基线得分
  3  负例比例的 Wilson 95% 置信区间（别把点估计当能力）
  4  题面长度与真实监管记录（PMA 批准说明）长度的对比

只用标准库。用法：
  python tools/pccp_dataset_audit.py --zip pcb010.zip
"""
import argparse
import json
import math
import zipfile
from collections import Counter


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    s = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - s) / d, (c + s) / d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--member", default="dataset/cases_public.json")
    ap.add_argument("--corpus-median", type=int, default=463,
                    help="FDA PMA 批准说明文本长度中位数，取自 47 条 PCCP 语料")
    a = ap.parse_args()

    cases = json.loads(zipfile.ZipFile(a.zip).read(a.member))["cases"]
    n = len(cases)
    print("n =", n)

    flags = [k for k in cases[0] if isinstance(cases[0][k], bool)]
    print("\n%-32s %-6s %-6s %s" % ("flag", "True", "False", "力"))
    zero, live = [], []
    for k in flags:
        t = sum(1 for c in cases if c.get(k) is True)
        f = sum(1 for c in cases if c.get(k) is False)
        tag = "零方差" if t == 0 or f == 0 else "有"
        (zero if tag == "零方差" else live).append(k)
        print("%-32s %-6d %-6d %s" % (k, t, f, tag))
    print("\n零方差 %d 个 / 有判别力 %d 个：%s" % (len(zero), len(live), ", ".join(live)))

    verdicts = Counter(c.get("expected_verdict") for c in cases)
    print("\n答案分布:", verdicts.most_common())
    top_k, top_n = verdicts.most_common(1)[0]
    print("傻瓜基线（永远答 %s）= %d/%d = %.4f" % (top_k, top_n, n, top_n / n))
    lo, hi = wilson(top_n, n)
    print("该基线比例的 Wilson 95%% CI = [%.3f, %.3f]" % (lo, hi))

    L = [len(c.get("device_description", "")) for c in cases]
    L.sort()
    print("\n题面长度 min/median/max = %d/%d/%d；FDA 语料中位 = %d"
          % (L[0], L[len(L) // 2], L[-1], a.corpus_median))
    print("\n判据力不足的判据：零方差标志只有装饰作用，不能算考过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
