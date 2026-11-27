#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""judge_negative_control.py —— 给"判器 51/51"配一条负向可控。

为什么：51/51 只说明"在这些题上判器与标签一致"。它不说明判器的判决**依赖哪些字段**。
一条题如果对任何单字段的翻转都无动于衷，那它在打分里等于"白送"——分数很好看，
但那道题实际没考任何东西。C6 的做法（profile 自检里那条）推广到题集线，就是这个。

三项统计（全部用包内 adapter + 包内判器，隔离运行）：

  1  SINGLE_FLIP   逐题、逐布尔字段翻一位，看判决或标签是否变化
                   → 每题"敏感字段数"；敏感数为 0 的题单独列出（白送风险）
  2  FLIP_ALL      把一题的全部布尔字段一起翻，判决是否变化
                   → 若某题全翻都不变，说明该题与判器脱钩，必须查
  3  WRONG_ANSWER  把标签改成"永远 go"，看它还能骗到多少分
                   → 给出"假模型下限"，用来给 51/51 标刻度

用法：
  python judge_negative_control.py --pkg "%TEMP%\\iso_v031" --json out\\judge_negctl_v031.json
"""
import argparse
import glob
import importlib.util
import json
import os
import sys


def load_adapter(pkg):
    p = os.path.join(pkg, "dataset", "adapter_reference.py")
    spec = importlib.util.spec_from_file_location("adapter_reference", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["adapter_reference"] = mod
    spec.loader.exec_module(mod)
    return mod


def bool_keys(ctx):
    return [k for k, v in ctx.items()
            if isinstance(v, bool) and not k.startswith("expected_")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkg", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()

    adapter = load_adapter(a.pkg)
    raw = open(os.path.join(a.pkg, "dataset", "cases_public.json"), "rb").read()
    doc = json.loads(raw.decode("utf-8"))
    cases = doc.get("cases", doc)

    rows = []
    total_pairs = 0
    total_flips = 0
    zero_cases = []
    allflip_unchanged = []

    for c in cases:
        ctx0 = {k: v for k, v in c.items() if not k.startswith("expected_")}
        base = adapter.evaluate(dict(ctx0))
        keys = bool_keys(ctx0)
        sensitive = []
        for k in keys:
            ctx = dict(ctx0)
            ctx[k] = not ctx[k]
            r = adapter.evaluate(ctx)
            if (r.get("verdict"), r.get("tag")) != (base.get("verdict"), base.get("tag")):
                sensitive.append(k)
        total_pairs += len(keys)
        total_flips += len(sensitive)
        if not sensitive:
            zero_cases.append(c["case_id"])

        ctx_all = dict(ctx0)
        for k in keys:
            ctx_all[k] = not ctx_all[k]
        r_all = adapter.evaluate(ctx_all)
        if (r_all.get("verdict"), r_all.get("tag")) == (base.get("verdict"), base.get("tag")):
            allflip_unchanged.append(c["case_id"])

        rows.append({
            "case_id": c["case_id"],
            "baseline": base.get("verdict"),
            "label": c.get("expected_verdict"),
            "n_bool": len(keys),
            "n_sensitive": len(sensitive),
            "sensitive_flags": sensitive,
            "flip_all_moves": (r_all.get("verdict"), r_all.get("tag")) != (base.get("verdict"), base.get("tag")),
            "flip_all_verdict": r_all.get("verdict"),
        })

    # 假模型下限：永远 go
    always_go = sum(1 for c in cases if c.get("expected_verdict") == "go") / len(cases)

    out = {
        "package": os.path.abspath(a.pkg),
        "cases": len(cases),
        "single_flip": {
            "pairs": total_pairs,
            "flips": total_flips,
            "rate": round(total_flips / total_pairs, 4),
            "mean_per_case": round(total_flips / len(cases), 2),
            "cases_with_zero_sensitivity": zero_cases,
        },
        "flip_all": {
            "unchanged": allflip_unchanged,
            "n_unchanged": len(allflip_unchanged),
        },
        "baseline_always_go": round(always_go, 4),
        "rows": rows,
    }
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True) if os.path.dirname(a.json) else None
        json.dump(out, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"题数 {len(cases)}   布尔字段对 {total_pairs}")
    print(f"SINGLE_FLIP   翻一位就改判的比例 {out['single_flip']['rate']}（每题均值 {out['single_flip']['mean_per_case']} 个字段）")
    print(f"零敏感题      {len(zero_cases)} 条" + (("  " + ", ".join(zero_cases)) if zero_cases else ""))
    print(f"FLIP_ALL     全翻仍不变 {len(allflip_unchanged)} 条" + (("  " + ", ".join(allflip_unchanged)) if allflip_unchanged else ""))
    print(f"永远 go 基线  {out['baseline_always_go']}")
    low = [r for r in rows if r["n_sensitive"] <= 1]
    print(f"敏感字段 ≤1 的题 {len(low)} 条")
    for r in low[:12]:
        print(f"  {r['case_id']:<28} base={r['baseline']:<7} 敏感={r['n_sensitive']}/{r['n_bool']}")
    print("NEGCTL_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
