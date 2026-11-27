#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""normalize_v03.py —— v0.3 事实 → 现行判器输入（不动判器一行）。

背景（第二十二轮实测）：判器只读标志、不读叙述。所以"标志兼义"这种缺陷的修法不必改判器，
只要把两个被压扁的标志**拆开表达**，再在编码层映射回去。

v0.3 事实新增四个字段：
  claimed_pccp_coverage   厂商是否主张本次变更走 PCCP（主张，不是事实）
  actually_within_scope   PCCP 授权文本是否真的覆盖本次变更（事实）
  criteria_measured       验收指标是否按 PCCP 要求的方式测过
  criteria_met            测过的结果是否达标

映射（三处，全部有据）：
  change_within_pccp_scope = claimed AND (actual OR NOT authorized)
      · 有授权、主张、实际在范围 → True（正常 go 路）
      · 有授权、主张、实际不在范围 → False（落 hold：出范围，须按 807.81(a)(3) 判）
      · 无授权、主张            → True（让 P-CRIT-01 开火 → reject）
      · 无授权、不主张           → False（hold：根本没走 PCCP 路）
  acceptance_criteria_met = None  若 criteria_measured 不为 True（未按类型测 → hold）
                           = criteria_met 若测过（实测未达 → reject）
其余七个标志一一对应。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS9 = ["affects_intended_use", "change_class_described", "validation_documented",
         "labeling_version_history", "udi_updated", "remains_se_to_predicate"]


def expand(facts: dict) -> dict:
    """把 v0.3 事实展开成现行判器认识的标志向量。"""
    f = dict(facts)
    auth = f.get("pccp_authorized")
    claim = f.get("claimed_pccp_coverage")
    actual = f.get("actually_within_scope")
    # 老题没有新字段时，退化为原标志（保证兼容）
    if claim is None:
        claim = f.get("change_within_pccp_scope")
    if actual is None:
        actual = f.get("change_within_pccp_scope")

    f["change_within_pccp_scope"] = bool(claim) and (bool(actual) or auth is False)

    measured = f.get("criteria_measured")
    met = f.get("criteria_met")
    if measured is None:                      # 老题没有新字段：按原值
        f["acceptance_criteria_met"] = f.get("acceptance_criteria_met")
    elif measured is not True:
        f["acceptance_criteria_met"] = None   # 未按类型测 → 未证明，不是未达
    else:
        f["acceptance_criteria_met"] = met    # 测过 → 如实报达/未达
    return f


def load_bench(dataset_dir):
    spec = importlib.util.spec_from_file_location("pccp_bench", os.path.join(dataset_dir, "bench.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pccp_bench"] = mod
    spec.loader.exec_module(mod)
    return mod


def to_v03(case: dict) -> dict:
    """由老题标志反推一套 v0.3 事实（用于兼容性回归）。"""
    c = dict(case)
    c["claimed_pccp_coverage"] = case.get("change_within_pccp_scope")
    c["actually_within_scope"] = case.get("change_within_pccp_scope")
    c["criteria_measured"] = None if case.get("acceptance_criteria_met") is None else True
    c["criteria_met"] = case.get("acceptance_criteria_met")
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-zip", required=True)
    ap.add_argument("--adapter", default=os.path.join(HERE, "repro", "adapter_reference.py"))
    ap.add_argument("--boundary", default=os.path.join(HERE, "v03_boundary_cases.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "v03_compat.json"))
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="pccp_v03_")
    with zipfile.ZipFile(a.dataset_zip) as z:
        z.extractall(tmp)
    dd = os.path.join(tmp, "dataset")
    bench = load_bench(dd)
    adapter = bench.load_adapter(os.path.abspath(a.adapter))
    cases = json.load(open(os.path.join(dd, "cases_public.json"), encoding="utf-8"))
    cases = cases.get("cases", cases) if isinstance(cases, dict) else cases

    # 1) 兼容性：老标志 → v0.3 事实 → 展开 → 判器，判决应与原来逐条相同
    regress = []
    for c in cases:
        v0, _ = bench.ask(adapter, dict(c))
        v1, _ = bench.ask(adapter, expand(to_v03(c)))
        if v0 != v1:
            regress.append({"case_id": c["case_id"], "before": v0, "after": v1})

    # 2) 边界题：按更正后的 v0.3 事实重判
    boundary = json.load(open(a.boundary, encoding="utf-8"))["cases"] if os.path.exists(a.boundary) else []
    bres = []
    for c in boundary:
        v, tag = bench.ask(adapter, expand(c))
        bres.append({"case_id": c["case_id"], "expected": c.get("expected_verdict"),
                     "v03_verdict": v, "v03_tag": tag,
                     "match": v == c.get("expected_verdict")})

    res = {"n": len(cases), "regressions": len(regress), "regression_detail": regress,
           "boundary": bres}
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"n": len(cases), "regressions": len(regress),
                      "regression_detail": regress,
                      "boundary_hit": "%d/%d" % (sum(1 for b in bres if b["match"]), len(bres))},
                     ensure_ascii=False, indent=1))
    for b in bres:
        print("  %-34s expected=%-7s v03=%-7s tag=%-24s %s"
              % (b["case_id"], b["expected"], b["v03_verdict"], b["v03_tag"],
                 "OK" if b["match"] else "MISS"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
