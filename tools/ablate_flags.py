#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ablate_flags.py —— 判器对标志的敏感度审计（无需标签）。

两件事：
  A. 置空叙述：把 device_description 全部清成空字符串，看判决是否变化
     → 若不变，说明判器完全不读事实叙述，只读预先编码的标志。
  B. 逐标志消融：把某一标志全部置 None（"未述"），看判决翻转多少条
     → 数字越大，说明该标志承载的判决权越重。
"""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))

FLAGS = ["pccp_authorized", "change_within_pccp_scope", "affects_intended_use",
         "change_class_described", "acceptance_criteria_met", "validation_documented",
         "labeling_version_history", "udi_updated", "remains_se_to_predicate"]


def load_bench(dataset_dir):
    spec = importlib.util.spec_from_file_location("pccp_bench", os.path.join(dataset_dir, "bench.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pccp_bench"] = mod
    spec.loader.exec_module(mod)
    return mod


def verdicts(bench, adapter, cases):
    out = []
    for c in cases:
        v, _ = bench.ask(adapter, dict(c))
        out.append(v)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset-zip", required=True)
    ap.add_argument("--adapter", default=os.path.join(HERE, "repro", "adapter_reference.py"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "ablation_flags.json"))
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="pccp_abl_")
    with zipfile.ZipFile(a.dataset_zip) as z:
        z.extractall(tmp)
    dd = os.path.join(tmp, "dataset")
    bench = load_bench(dd)
    adapter = bench.load_adapter(os.path.abspath(a.adapter))
    cases = json.load(open(os.path.join(dd, "cases_public.json"), encoding="utf-8"))
    cases = cases.get("cases", cases) if isinstance(cases, dict) else cases

    base = verdicts(bench, adapter, cases)

    blank = [dict(c, device_description="") for c in cases]
    nb = verdicts(bench, adapter, blank)
    blank_flip = [(c["case_id"], b, n) for c, b, n in zip(cases, base, nb) if b != n]

    abl = {}
    for f in FLAGS:
        mod = [dict(c, **{f: None}) for c in cases]
        vm = verdicts(bench, adapter, mod)
        flips = [(c["case_id"], b, m) for c, b, m in zip(cases, base, vm) if b != m]
        abl[f] = {"flips": len(flips), "detail": flips}

    res = {
        "n": len(cases),
        "verdict_mix": {k: base.count(k) for k in ("go", "hold", "reject")},
        "blank_narrative": {"flips": len(blank_flip), "detail": blank_flip},
        "flag_ablation": abl,
    }
    json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: (v if not isinstance(v, dict) else
                          ({kk: vv for kk, vv in v.items() if kk != "detail"} if "flips" in v else v))
                      for k, v in res.items()}, ensure_ascii=False, indent=1))
    print("\n--- 逐标志翻转 ---")
    for f, d in abl.items():
        print("%-28s %2d" % (f, d["flips"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
