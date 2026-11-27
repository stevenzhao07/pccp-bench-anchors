#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kappa.py —— 两位评审的一致性系数（Cohen's κ），带自检与负向对照。

为什么单独做这一件：
我们所有的 PASS 都是"判器与标签一致"——那是同一位作者的自我一致，不是独立标注。
要把"独立标注"这件事变成可读的量，就得有 κ：它把"碰巧一致的部分"从一致率里扣掉。
没有 κ，任何"51/51 一致"都说不清是本事还是碰巧。

用法：
  python kappa.py --a raterA.csv --b raterB.csv [--label-col verdict] [--id-col case_id] [--json out.json]
  python kappa.py --selftest

CSV 需含两列：case_id, verdict（取值 go / hold / reject；缺失记 __MISSING__）。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter

LABELS = ["go", "hold", "reject"]
LABELS_WITH_MISSING = LABELS + ["__MISSING__"]


def read_csv(path: str, id_col: str = "case_id", label_col: str = "verdict") -> dict[str, str]:
    out: dict[str, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            cid = (row.get(id_col) or "").strip()
            lab = (row.get(label_col) or "").strip().lower()
            if not cid:
                continue
            out[cid] = lab if lab in LABELS else "__MISSING__"
    return out


def cohen_kappa(a: dict[str, str], b: dict[str, str]) -> dict:
    ids = sorted(set(a) & set(b))
    n = len(ids)
    if n == 0:
        return {"n": 0, "error": "no overlapping case_id"}

    cats = [c for c in LABELS_WITH_MISSING if any(a[i] == c or b[i] == c for i in ids)]
    ca = Counter(a[i] for i in ids)
    cb = Counter(b[i] for i in ids)
    po = sum(1 for i in ids if a[i] == b[i]) / n
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    kappa = 0.0 if pe == 1.0 else (po - pe) / (1 - pe)

    per_label = {}
    for c in cats:
        tp = sum(1 for i in ids if a[i] == c and b[i] == c)
        fa = sum(1 for i in ids if a[i] != c and b[i] == c)
        fn = sum(1 for i in ids if a[i] == c and b[i] != c)
        per_label[c] = {
            "agree": tp,
            "b_says_only": fa,
            "a_says_only": fn,
            "a_count": ca[c],
            "b_count": cb[c],
            "a_share": round(ca[c] / n, 3),
            "b_share": round(cb[c] / n, 3),
        }

    warnings = []
    if n < 20:
        warnings.append("n=%d 偏小：κ 的置信区间会很宽，只能作参考，不能当结论" % n)
    for c in cats:
        share = max(ca[c], cb[c]) / n
        if share > 0.8:
            warnings.append(
                "κ 悖论风险：类别 %s 占比 %.0f%%（一致率可能很高但 κ 很低，属正常现象）"
                % (c, share * 100))
    missing = sum(1 for i in ids if a[i] == "__MISSING__" or b[i] == "__MISSING__")
    if missing:
        warnings.append("%d 例有一方留空，已按 __MISSING__ 计入，未丢弃" % missing)

    return {"n": n, "po": round(po, 4), "pe": round(pe, 4), "kappa": round(kappa, 4),
            "categories": cats, "per_label": per_label, "warnings": warnings,
            "disagreements": [{"case_id": i, "a": a[i], "b": b[i]}
                              for i in ids if a[i] != b[i]]}


def selftest() -> int:
    """三个解析可验的算例，任何一个不符就报错退出。"""
    ok = True

    # ① 教科书算例：50 例，2×2 表 [[20,5],[10,15]]
    #    po = (20+15)/50 = 0.7
    #    pe = (25*30 + 25*20)/50^2 = (750+500)/2500 = 0.5
    #    κ = (0.7-0.5)/(1-0.5) = 0.4
    a1, b1 = {}, {}
    for i in range(20):
        a1["c%d" % i] = "go"; b1["c%d" % i] = "go"
    for i in range(20, 25):
        a1["c%d" % i] = "go"; b1["c%d" % i] = "hold"
    for i in range(25, 35):
        a1["c%d" % i] = "hold"; b1["c%d" % i] = "go"
    for i in range(35, 50):
        a1["c%d" % i] = "hold"; b1["c%d" % i] = "hold"
    r1 = cohen_kappa(a1, b1)
    if not (abs(r1["po"] - 0.7) < 1e-9 and abs(r1["pe"] - 0.5) < 1e-9
            and abs(r1["kappa"] - 0.4) < 1e-9):
        print("SELFTEST_FAIL 教科书算例：", r1); ok = False
    else:
        print("SELFTEST_OK   教科书算例 po=0.7 pe=0.5 κ=0.4")

    # ② 完全一致 → κ = 1
    a2 = {("c%d" % i): ("go" if i % 3 == 0 else "hold") for i in range(30)}
    r2 = cohen_kappa(a2, dict(a2))
    if abs(r2["kappa"] - 1.0) < 1e-9:
        print("SELFTEST_OK   完全一致 κ=1.0")
    else:
        print("SELFTEST_FAIL 完全一致应为 1.0，实得", r2["kappa"]); ok = False

    # ③ 系统性反向（A 全 go / B 全 hold）→ pe=0 → κ = po = 0
    a3 = {"c%d" % i: "go" for i in range(10)}
    b3 = {"c%d" % i: "hold" for i in range(10)}
    r3 = cohen_kappa(a3, b3)
    if abs(r3["kappa"]) < 1e-9:
        print("SELFTEST_OK   系统性反向 κ=0.0")
    else:
        print("SELFTEST_FAIL 系统性反向应为 0.0，实得", r3["kappa"]); ok = False

    # ④ 负向对照：随机扰动 30%（κ 必须显著低于 1，且低于 0.8）
    a4 = {("c%d" % i): ("go" if i % 4 == 0 else ("reject" if i % 4 == 1 else "hold"))
          for i in range(40)}
    b4 = dict(a4)
    for i in range(0, 40, 3)[:5]:               # 5 例固定扰动，可复现
        b4["c%d" % i] = "hold" if b4["c%d" % i] != "hold" else "go"
    r4 = cohen_kappa(a4, b4)
    if r4["kappa"] < 0.8 and len(r4["disagreements"]) == 5:
        print("SELFTEST_OK   负向对照（5 例扰动）κ=%.3f < 0.8" % r4["kappa"])
    else:
        print("SELFTEST_FAIL 负向对照：", r4["kappa"], len(r4["disagreements"])); ok = False

    print("\nKAPPA_SELFTEST_ALL_PASS" if ok else "\nKAPPA_SELFTEST_HAS_FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--id-col", default="case_id")
    ap.add_argument("--label-col", default="verdict")
    ap.add_argument("--json")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest or not (args.a and args.b):
        return selftest()

    a = read_csv(args.a, args.id_col, args.label_col)
    b = read_csv(args.b, args.id_col, args.label_col)
    r = cohen_kappa(a, b)
    print("n=%s  po=%s  pe=%s  κ=%s" % (r.get("n"), r.get("po"), r.get("pe"), r.get("kappa")))
    for k, v in (r.get("per_label") or {}).items():
        print("  %-8s A=%d B=%d 同判=%d 仅B=%d 仅A=%d"
              % (k, v["a_count"], v["b_count"], v["agree"], v["b_says_only"], v["a_says_only"]))
    for w in r.get("warnings") or []:
        print("  WARN", w)
    d = r.get("disagreements") or []
    for x in d:
        print("  差异 %-28s A=%s B=%s" % (x["case_id"], x["a"], x["b"]))
    if args.json:
        json.dump(r, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
